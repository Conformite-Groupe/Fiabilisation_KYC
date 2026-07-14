"""
Envoi SMTP des rappels DATEREV — logique réutilisable par la vue web
(`send_daterev_reminders`) et par la tâche planifiée quotidienne.

La configuration SMTP provient du modèle EmailReminderConfig
(« Configuration Rappel DATEREV » dans l'admin).
"""
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from django.template.loader import render_to_string


def open_smtp(cfg):
    """Ouvre une connexion SMTP selon la config (TLS/SSL, auth ou relais interne)."""
    def _conn():
        if cfg.smtp_use_ssl:
            return smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15)
        s = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
        if cfg.smtp_use_tls:
            s.ehlo(); s.starttls(); s.ehlo()
        return s

    srv = _conn()
    if cfg.smtp_user and cfg.smtp_password:
        try:
            srv.login(cfg.smtp_user, cfg.smtp_password)
        except smtplib.SMTPAuthenticationError:
            srv.quit()
            srv = _conn()   # relais interne sans authentification
    return srv


def send_daterev_reminders_core(config, filiale=None, expl=None, only_paid=True):
    """Envoie les rappels DATEREV aux chargés concernés. Retourne (sent, skipped)."""
    from accounts.models import ProfileV
    from kyc.views import _get_exploitants_daterev_expired

    data = _get_exploitants_daterev_expired(filiale or None, config.days_before, only_paid=only_paid)
    sent = skipped = 0
    if not data:
        return sent, skipped

    server = open_smtp(config)

    profiles_index = {}
    for p in ProfileV.objects.exclude(code_expl='').exclude(code_expl__isnull=True):
        profiles_index[(p.filiale.strip().upper(), p.code_expl.strip().upper())] = p

    try:
        for fil, expls in data.items():
            for ex, clients in expls.items():
                if expl and ex.strip().upper() != expl.strip().upper():
                    continue
                user_obj = profiles_index.get((fil.strip().upper(), ex.strip().upper()))
                recipient = user_obj.email if user_obj else None
                if not recipient:
                    skipped += 1
                    continue

                nom = f"{user_obj.first_name} {user_obj.last_name}".strip()
                all_clients = sorted(clients['clients_pp'] + clients['clients_pm'],
                                     key=lambda x: x['daterev'])

                html_body = render_to_string('email_daterev_reminder.html', {
                    'nom': nom, 'expl': ex, 'filiale': fil,
                    'clients': all_clients, 'days_before': config.days_before,
                })

                import openpyxl
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "Clients DATEREV"
                ws.append(['Agence', 'Client', 'IDP/IDM', 'DATEREV', 'Echéance', 'Risque'])
                for c in all_clients:
                    dr = c['daterev']
                    dr_str = dr.strftime('%d/%m/%Y') if hasattr(dr, 'strftime') else str(dr)
                    ws.append([c['agence'], c['client'], c.get('idpm', ''),
                               dr_str, c.get('echeance', c.get('statut', '')),
                               c.get('risque', '')])
                buf = io.BytesIO()
                wb.save(buf)
                buf.seek(0)

                msg = MIMEMultipart('mixed')
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))
                part = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part.set_payload(buf.read())
                encoders.encode_base64(part)
                part.add_header('Content-Disposition', f'attachment; filename="daterev_{ex}_{fil}.xlsx"')
                msg.attach(part)

                msg['Subject'] = f"[KYC BOA] Rappel — Revue de portefeuille client à effectuer ({fil})"
                msg['From'] = f"{config.from_name} <{config.from_email}>"
                msg['To'] = recipient
                server.sendmail(config.from_email, recipient, msg.as_string())
                sent += 1
    finally:
        try:
            server.quit()
        except Exception:
            pass

    return sent, skipped


def parse_recipients(raw):
    """Découpe une liste d'emails séparés par , ; espace ou retour ligne."""
    import re
    if not raw:
        return []
    parts = re.split(r"[,;\s]+", raw.strip())
    return [p for p in parts if p]


def send_html_email(config, recipients, subject, html_body):
    """Envoie un email HTML simple à une liste de destinataires. Retourne le nb de destinataires."""
    recipients = [r for r in (recipients or []) if r]
    if not recipients:
        return 0
    server = open_smtp(config)
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{config.from_name} <{config.from_email}>"
        msg['To'] = ", ".join(recipients)
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        server.sendmail(config.from_email, recipients, msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return len(recipients)
