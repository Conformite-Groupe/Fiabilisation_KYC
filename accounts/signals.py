from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import UserLoginHistory


@receiver(user_logged_in)
def track_user_login(sender, request, user, **kwargs):
    if user and user.is_authenticated:
        UserLoginHistory.objects.create(user=user)
