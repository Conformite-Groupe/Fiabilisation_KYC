"""
Tâche planifiée UNIQUE regroupant tous les traitements quotidiens :
  0a. Worker OCR documents (process_document_ocr --loop, processus détaché)
  0. Imports (import_kyc.py, import_premier.py, import_taux_agent.py)
  1. Calcul des taux de qualité complets (compute_quality_rates)
  2. Préchauffe des caches (warm_ui_caches)
  3. Calcul des appréciations globales (compute_appreciation_globale)
  4. Envoi des rappels DATEREV (filiales payées uniquement)

À la fin, envoie un rapport d'exécution (OK / problèmes) par email à la liste
de supervision (champ « Emails de supervision » de la Configuration Rappel DATEREV),
via la même configuration SMTP.

Planifier UNE seule tâche :
    python manage.py run_daily_jobs
"""
import io
import time
import traceback

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Exécute tous les traitements quotidiens et envoie un rapport par email."

    def add_arguments(self, parser):
        parser.add_argument("--no-mail", action="store_true",
                            help="N'envoie pas le rapport par email (exécution seule).")
        parser.add_argument("--skip", default="",
                            help="Jobs à ignorer, séparés par des virgules : "
                                 "ocr_worker,import_kyc,import_premier,import_taux,quality,warm,appreciation,daterev")
        parser.add_argument("--script-timeout", type=int, default=7200,
                            help="Délai max (secondes) par script d'import (défaut 7200).")
        parser.add_argument("--daterev-filiale", default="",
                            help="Limite l'envoi des rappels DATEREV à cette filiale (ex. « BOA SN »). "
                                 "Vide = toutes les filiales payées.")

    def handle(self, *args, **options):
        from kyc.models import EmailReminderConfig

        skip = {s.strip().lower() for s in (options.get("skip") or "").split(",") if s.strip()}
        results = []
        started = timezone.localtime()

        def run(key, label, fn):
            if key in skip:
                results.append({"label": label, "status": "ignoré", "ok": True, "detail": "", "duration": 0})
                self.stdout.write(f"[SKIP] {label}")
                return
            t0 = time.time()
            self.stdout.write(f"[START] {label}")
            try:
                detail = fn() or ""
                dur = round(time.time() - t0, 1)
                results.append({"label": label, "status": "OK", "ok": True, "detail": str(detail), "duration": dur})
                self.stdout.write(self.style.SUCCESS(f"[OK] {label} ({dur}s) {detail}"))
            except Exception as e:
                dur = round(time.time() - t0, 1)
                tb = traceback.format_exc()
                results.append({"label": label, "status": "ÉCHEC", "ok": False,
                                "detail": f"{type(e).__name__}: {e}", "duration": dur, "trace": tb[-1500:]})
                self.stderr.write(f"[ÉCHEC] {label} ({dur}s) : {e}")

        # ── 0. Scripts d'importation (sous-processus, exécutés en premier) ────
        import os
        import subprocess
        import sys as _sys
        from django.conf import settings

        script_timeout = options.get("script_timeout") or 7200

        def _run_script(filename):
            path = os.path.join(str(settings.BASE_DIR), filename)
            if not os.path.exists(path):
                raise FileNotFoundError(f"Script introuvable : {filename}")
            proc = subprocess.run([_sys.executable, path], cwd=str(settings.BASE_DIR),
                                  capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=script_timeout)
            out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
            tail = out.splitlines()[-1].strip() if out else ""
            if proc.returncode != 0:
                raise RuntimeError(f"code retour {proc.returncode} — {tail[:200]}")
            return (tail[:200] or "Terminé.")

        # ── 0a. Worker OCR documents (processus DÉTACHÉ, non bloquant) ────────
        # Lancé en tout premier : la fonction retourne immédiatement après le spawn,
        # le worker vit ensuite indépendamment des autres jobs (un échec du worker
        # n'affecte pas la suite, et inversement). Garde anti-doublon par fichier PID.
        def _ocr_worker():
            pid_file = os.path.join(str(settings.BASE_DIR), "ocr_worker.pid")
            if os.path.exists(pid_file):
                try:
                    pid = int(open(pid_file).read().strip())
                    check = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                           capture_output=True, timeout=30)
                    if str(pid).encode() in (check.stdout or b""):
                        return f"Worker OCR déjà actif (PID {pid}) — rien à faire."
                except Exception:
                    pass  # PID illisible ou tasklist indisponible : on relance.
            log_handle = open(os.path.join(str(settings.BASE_DIR), "ocr_worker.log"), "ab")
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            proc = subprocess.Popen(
                [_sys.executable, "-X", "utf8", "manage.py", "process_document_ocr",
                 "--loop", "--interval", "5", "--workers", "3"],
                cwd=str(settings.BASE_DIR), stdout=log_handle, stderr=log_handle,
                stdin=subprocess.DEVNULL, creationflags=creationflags, close_fds=True,
            )
            with open(pid_file, "w") as fh:
                fh.write(str(proc.pid))
            return f"Worker OCR lancé en arrière-plan (PID {proc.pid}, log : ocr_worker.log)."
        run("ocr_worker", "Worker OCR documents (process_document_ocr --loop)", _ocr_worker)

        run("import_kyc", "Importation KYC (import_kyc.py)", lambda: _run_script("import_kyc.py"))
        run("import_premier", "Importation évolution / DATEREV / anomalies (import_premier.py)", lambda: _run_script("import_premier.py"))
        run("import_taux", "Importation taux agents (import_taux_agent.py)", lambda: _run_script("import_taux_agent.py"))

        # ── 1a. Taux de qualité complets (TOUS les scopes) ────────────────────
        # À faire AVANT le warm : les dashboards (statistiques) lisent la table
        # TauxQualite. compute_quality_rates couvre tous les scopes actifs alors
        # que warm_ui_caches ne calcule que les ~20 scopes représentatifs.
        def _quality():
            buf = io.StringIO()
            call_command("compute_quality_rates", stdout=buf)
            return buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else "Terminé."
        run("quality", "Calcul des taux de qualité (compute_quality_rates)", _quality)

        # ── 1b. Préchauffe des caches ─────────────────────────────────────────
        def _warm():
            buf = io.StringIO()
            call_command("warm_ui_caches", stdout=buf)
            return buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else "Terminé."
        run("warm", "Préchauffe des caches (warm_ui_caches)", _warm)

        # ── 2. Appréciations globales ─────────────────────────────────────────
        def _appr():
            buf = io.StringIO()
            call_command("compute_appreciation_globale", stdout=buf)
            return buf.getvalue().strip().splitlines()[-1] if buf.getvalue().strip() else "Terminé."
        run("appreciation", "Calcul des appréciations globales", _appr)

        # ── 3. Rappels DATEREV (filiales payées) ──────────────────────────────
        daterev_filiale = (options.get("daterev_filiale") or "").strip()

        def _daterev():
            from kyc.daterev_mailer import send_daterev_reminders_core
            cfg = EmailReminderConfig.objects.filter(active=True).order_by("-updated_at").first()
            if not cfg:
                return "Aucune configuration SMTP active — envoi ignoré."
            # Respect de la fréquence configurée (l'envoi manuel via l'interface
            # n'est pas concerné : il passe directement par send_daterev_reminders_core).
            today = timezone.localdate()
            freq = (cfg.frequency or "manual").lower()
            if freq == "manual":
                return "Fréquence « Manuel » — envoi automatique ignoré."
            if freq == "weekly" and today.weekday() != 0:
                return "Fréquence « Hebdomadaire » — envoi uniquement le lundi, ignoré aujourd'hui."
            if freq == "monthly" and today.day != 1:
                return "Fréquence « Mensuel » — envoi uniquement le 1er du mois, ignoré aujourd'hui."
            sent, skipped = send_daterev_reminders_core(cfg, filiale=daterev_filiale or None, only_paid=True)
            cible = f" pour la filiale « {daterev_filiale} »" if daterev_filiale else ""
            return f"{sent} mail(s) envoyé(s), {skipped} ignoré(s) (email manquant){cible}."
        label_daterev = (f"Envoi des rappels DATEREV — filiale « {daterev_filiale} »"
                         if daterev_filiale else "Envoi des rappels DATEREV (filiales payées)")
        run("daterev", label_daterev, _daterev)

        ended = timezone.localtime()
        all_ok = all(r["ok"] for r in results)
        self.stdout.write(self.style.SUCCESS("=== Traitements quotidiens terminés ===")
                          if all_ok else self.style.ERROR("=== Traitements quotidiens : DES PROBLÈMES ==="))

        # ── Rapport email ─────────────────────────────────────────────────────
        if options.get("no_mail"):
            return
        try:
            self._send_report(results, started, ended, all_ok)
        except Exception as e:
            self.stderr.write(f"Impossible d'envoyer le rapport de supervision : {e}")

    def _send_report(self, results, started, ended, all_ok):
        from kyc.models import EmailReminderConfig
        from kyc.daterev_mailer import parse_recipients, send_html_email

        cfg = EmailReminderConfig.objects.filter(active=True).order_by("-updated_at").first()
        if not cfg:
            self.stderr.write("Aucune configuration SMTP : rapport non envoyé.")
            return
        recipients = parse_recipients(cfg.notify_emails)
        if not recipients:
            self.stderr.write("Aucun email de supervision configuré : rapport non envoyé.")
            return

        date_str = started.strftime("%d/%m/%Y %H:%M")
        statut_global = "✅ TOUT EST OK" if all_ok else "⚠️ PROBLÈMES DÉTECTÉS"
        head_color = "#0a3d2e" if all_ok else "#9a3412"

        rows = ""
        for r in results:
            if r["status"] == "ignoré":
                color, badge = "#94a3b8", "Ignoré"
            elif r["ok"]:
                color, badge = "#059669", "OK"
            else:
                color, badge = "#dc2626", "Échec"
            detail = (r.get("detail") or "").replace("<", "&lt;").replace(">", "&gt;")
            rows += (
                f'<tr>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;font-weight:600;color:#334155;">{r["label"]}</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:center;">'
                f'<span style="background:{color};color:#fff;font-size:11px;font-weight:700;padding:2px 10px;border-radius:100px;">{badge}</span></td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;text-align:right;color:#64748b;">{r["duration"]}s</td>'
                f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#475569;font-size:12px;">{detail}</td>'
                f'</tr>'
            )

        html = f"""
        <div style="font-family:Segoe UI,Arial,sans-serif;max-width:700px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
          <div style="background:{head_color};padding:22px 28px;">
            <h1 style="color:#fff;font-size:17px;margin:0 0 4px;">Rapport des traitements quotidiens — KYC BOA</h1>
            <p style="color:rgba(255,255,255,.7);font-size:12px;margin:0;">Exécution du {date_str} · {statut_global}</p>
          </div>
          <div style="padding:20px 28px;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
              <thead><tr style="background:#065f46;color:#fff;">
                <th style="padding:8px 12px;text-align:left;">Traitement</th>
                <th style="padding:8px 12px;">Statut</th>
                <th style="padding:8px 12px;text-align:right;">Durée</th>
                <th style="padding:8px 12px;text-align:left;">Détail</th>
              </tr></thead>
              <tbody>{rows}</tbody>
            </table>
          </div>
          <div style="background:#f8fafc;padding:14px 28px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;">
            Message automatique · Plateforme Fiabilisation KYC v3.0 · BOA Group
          </div>
        </div>
        """
        subject = f"[KYC BOA] Traitements quotidiens — {'OK' if all_ok else 'PROBLEMES'} ({started.strftime('%d/%m/%Y')})"
        n = send_html_email(cfg, recipients, subject, html)
        self.stdout.write(self.style.SUCCESS(f"Rapport de supervision envoyé à {n} destinataire(s)."))
