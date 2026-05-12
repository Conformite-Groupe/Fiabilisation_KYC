from django.apps import AppConfig


class KycConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'kyc'


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        import users.signals
