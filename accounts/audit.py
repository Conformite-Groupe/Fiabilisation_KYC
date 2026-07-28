"""Helpers d'ecriture du journal d'audit (Administration > Audit)."""

import logging

logger = logging.getLogger(__name__)


def client_ip(request):
    """IP reelle de l'appelant, en tenant compte d'un eventuel reverse proxy."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def log_audit(request=None, *, category, action, target="", details="",
              user=None, username="", success=True):
    """Enregistre un evenement d'audit.

    Ne doit jamais faire echouer l'action metier appelante : toute erreur
    d'ecriture est journalisee puis ignoree.
    """
    from .models import AuditEvent

    try:
        if user is None and request is not None:
            candidate = getattr(request, "user", None)
            if candidate is not None and getattr(candidate, "is_authenticated", False):
                user = candidate

        agent = ""
        if request is not None:
            agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]

        return AuditEvent.objects.create(
            user=user,
            username=(username or getattr(user, "username", "") or "")[:150],
            filiale=(getattr(user, "filiale", "") or "")[:20],
            organe=(getattr(user, "organe", "") or "")[:50],
            category=category,
            action=(action or "")[:120],
            target=(target or "")[:255],
            details=details or "",
            ip_address=client_ip(request),
            user_agent=agent,
            success=success,
        )
    except Exception:                                                         
        logger.exception("Ecriture du journal d'audit impossible (%s / %s)", category, action)
        return None
