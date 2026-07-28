from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .audit import log_audit
from .models import AuditEvent, ProfileV, UserLoginHistory


@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    if user and user.is_authenticated:
        UserLoginHistory.objects.create(user=user)
        log_audit(
            request,
            category=AuditEvent.CAT_CONNEXION,
            action="Connexion",
            target=user.username,
            details=f"Connexion reussie ({user.organe or '-'} / {user.filiale or '-'}).",
            user=user,
        )


@receiver(user_logged_out)
def track_user_logout(sender, request, user, **kwargs):
    if user is not None:
        log_audit(
            request,
            category=AuditEvent.CAT_CONNEXION,
            action="Deconnexion",
            target=getattr(user, "username", ""),
            details="Deconnexion de la plateforme.",
            user=user,
        )


@receiver(user_login_failed)
def track_login_failed(sender, credentials, request=None, **kwargs):
    tried = (credentials or {}).get("username") or (credentials or {}).get("email") or ""
    log_audit(
        request,
        category=AuditEvent.CAT_SECURITE,
        action="Echec de connexion",
        target=tried,
        details="Tentative d'authentification refusee (identifiant ou mot de passe invalide).",
        username=tried,
        success=False,
    )


                                                                               

def _user_label(instance):
    full = f"{instance.first_name} {instance.last_name}".strip()
    return f"{instance.username}{f' ({full})' if full else ''}"


@receiver(post_save, sender=ProfileV)
def track_user_account(sender, instance, created, **kwargs):
    if kwargs.get("raw"):
        return
                                                                                        
    update_fields = kwargs.get("update_fields")
    if update_fields and set(update_fields) <= {"last_login"}:
        return
    log_audit(
        category=AuditEvent.CAT_HABILITATION,
        action="Creation de compte" if created else "Modification de compte",
        target=_user_label(instance),
        details=(f"Organe : {instance.organe or '-'} | Filiale : {instance.filiale or '-'} | "
                 f"Agence : {instance.agence or '-'} | Actif : {'oui' if instance.is_active else 'non'}"),
        user=instance,
        username=instance.username,
    )


@receiver(post_delete, sender=ProfileV)
def track_user_deleted(sender, instance, **kwargs):
    log_audit(
        category=AuditEvent.CAT_HABILITATION,
        action="Suppression de compte",
        target=_user_label(instance),
        details=f"Organe : {instance.organe or '-'} | Filiale : {instance.filiale or '-'}",
        username=instance.username,
    )


                                                                               

@receiver(post_save, sender="kyc.KycScreeningAccess")
def track_screening_access(sender, instance, created, **kwargs):
    perms = ", ".join(p for p in instance.ALL_PERMS if getattr(instance, p, False)) or "aucun droit"
    log_audit(
        category=AuditEvent.CAT_HABILITATION,
        action="Creation habilitation Screening" if created else "Modification habilitation Screening",
        target=f"Organe {instance.organe}",
        details=f"Droits actifs : {perms}",
    )


@receiver(post_delete, sender="kyc.KycScreeningAccess")
def track_screening_access_deleted(sender, instance, **kwargs):
    log_audit(
        category=AuditEvent.CAT_HABILITATION,
        action="Suppression habilitation Screening",
        target=f"Organe {instance.organe}",
        details="Retour au comportement d'habilitation par defaut.",
    )
