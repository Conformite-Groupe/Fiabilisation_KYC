r"""Diagnostic de la configuration mail (a lancer sur le serveur concerne).

    venv\Scripts\python.exe diag_mail.py

Affiche la configuration REELLEMENT lue en base et teste la chaine de connexion
etape par etape. Le mot de passe n'est jamais affiche en clair.
"""
import os
import smtplib
import socket
import sys

import django

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fiabilisation_kyc.settings")
django.setup()

from kyc.models import EmailReminderConfig          # noqa: E402
from kyc.daterev_mailer import parse_recipients     # noqa: E402


def main():
    print("=" * 66)
    print(" DIAGNOSTIC MAIL - Fiabilisation KYC")
    print("=" * 66)

    total = EmailReminderConfig.objects.count()
    cfg = EmailReminderConfig.objects.filter(active=True).order_by("-updated_at").first()
    print(f"Configurations en base : {total}  |  active retenue : {'oui' if cfg else 'AUCUNE'}")

    if not cfg:
        print("\n[CAUSE TROUVEE] Aucune configuration active.")
        print("  -> Admin Django > Configurations Rappel Scoring : creer la ligne,")
        print("     ou cocher « Actif » sur la ligne existante.")
        return

    masque = "(vide)" if not cfg.smtp_password else f"({len(cfg.smtp_password)} caracteres)"
    print(f"  hote      : {cfg.smtp_host}:{cfg.smtp_port}")
    print(f"  TLS / SSL : {cfg.smtp_use_tls} / {cfg.smtp_use_ssl}")
    print(f"  user      : {cfg.smtp_user or '(vide)'}")
    print(f"  password  : {masque}")
    print(f"  from      : {cfg.from_name} <{cfg.from_email}>")
    print(f"  maj le    : {cfg.updated_at}")

    destinataires = parse_recipients(cfg.notify_emails)
    print(f"  rapport   : {len(destinataires)} destinataire(s) {destinataires or '<< VIDE >>'}")
    if not destinataires:
        print("\n[CAUSE TROUVEE] « Emails de supervision » est vide : les rappels DATEREV")
        print("  partent mais le rapport quotidien n'est jamais envoye.")

    print("-" * 66)
    print(f"1. Ouverture TCP vers {cfg.smtp_host}:{cfg.smtp_port} ...")
    try:
        socket.create_connection((cfg.smtp_host, cfg.smtp_port), timeout=15).close()
        print("   OK - le port est joignable depuis ce serveur.")
    except Exception as e:
        print(f"   ECHEC : {type(e).__name__} : {e}")
        print("\n[CAUSE TROUVEE] Le serveur ne joint pas le relais SMTP.")
        print("  -> Pare-feu / VLAN / proxy sortant. C'est la difference test <-> prod")
        print("     la plus frequente. A faire ouvrir par l'equipe reseau.")
        return

    print("2. Poignee de main SMTP ...")
    try:
        if cfg.smtp_use_ssl:
            srv = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15)
        else:
            srv = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
            if cfg.smtp_use_tls:
                srv.ehlo()
                srv.starttls()
                srv.ehlo()
        print("   OK")
    except Exception as e:
        print(f"   ECHEC : {type(e).__name__} : {e}")
        print("\n[CAUSE TROUVEE] Negociation TLS/SSL. Verifier la coherence port/TLS/SSL :")
        print("  587 -> TLS coche, SSL decoche")
        print("  465 -> SSL coche, TLS decoche")
        print("  25  -> les deux decoches")
        return

    try:
        print("3. Authentification ...")
        if not (cfg.smtp_user and cfg.smtp_password):
            print("   ignoree (pas d'identifiants) - relais suppose ouvert.")
        else:
            try:
                srv.login(cfg.smtp_user, cfg.smtp_password)
                print("   OK")
            except smtplib.SMTPAuthenticationError as e:
                print(f"   ECHEC : {e}")
                print("\n[CAUSE TROUVEE] Identifiants refuses. ATTENTION : open_smtp()")
                print("  rattrape cette erreur et reconnecte SANS authentification :")
                print("  l'envoi echoue donc plus tard, au sendmail, avec un message")
                print("  trompeur. -> Corriger le mot de passe en base sur CE serveur.")
                return
            except smtplib.SMTPNotSupportedError:
                print("   NON SUPPORTE par le relais - on poursuit sans authentification.")
                srv.quit()
                srv = (smtplib.SMTP_SSL if cfg.smtp_use_ssl else smtplib.SMTP)(
                    cfg.smtp_host, cfg.smtp_port, timeout=15)
                if not cfg.smtp_use_ssl and cfg.smtp_use_tls:
                    srv.ehlo()
                    srv.starttls()
                    srv.ehlo()
            except Exception as e:
                print(f"   ECHEC : {type(e).__name__} : {e}")
                return

        print("4. Acceptation expediteur / destinataires (aucun mail envoye) ...")
        try:
            code, msg = srv.mail(cfg.from_email)
            print(f"   MAIL FROM <{cfg.from_email}> -> {code} {msg.decode(errors='replace')}")
            for r in destinataires:
                code, msg = srv.rcpt(r)
                etat = "OK" if code in (250, 251) else "REFUSE"
                print(f"   RCPT TO <{r}> -> {code} {msg.decode(errors='replace')}  [{etat}]")
            srv.rset()
        except Exception as e:
            print(f"   ECHEC : {type(e).__name__} : {e}")
            print("\n[CAUSE TROUVEE] Le relais refuse l'expediteur ou les destinataires.")
            print("  -> Relais interne : l'IP du serveur de prod doit etre autorisee,")
            print("     et l'adresse expeditrice acceptee par le domaine.")
            return
    finally:
        try:
            srv.quit()
        except Exception:
            pass

    print("=" * 66)
    print("Les 4 etapes sont OK : la configuration mail n'est pas en cause.")
    print("Chercher dans logs\run_daily_jobs.log la ligne « Impossible d'envoyer »,")
    print("et verifier que run_daily_jobs va bien jusqu'a la fin.")
    print("=" * 66)


if __name__ == "__main__":
    main()
