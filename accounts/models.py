import datetime
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

Organe = (
    ('Directeur Agence', 'Directeur Agence'),
    ('Directeur de Zone', 'Directeur de Zone'),
    ('Chargé Client', 'Chargé Client'),
    ('Contrôle Permanent', 'Contrôle Permanent'),
    ('Directeur Réseau', 'Directeur Réseau'),
    ('Contrôle Permanent Groupe', 'Contrôle Permanent Groupe'),
    ('Conformité', 'Conformité'),
    ('Conformité Groupe', 'Conformité Groupe'),
    ('PASS', 'PASS'),
    ('DSI', 'DSI'),
    ('GUEST', 'GUEST'),
    ('Qualité', 'Qualité'),
    ('DAI', 'DAI'),
    ('Risques', 'Risques'),
)

Filiales = (
    ('BOA NE', 'BOA NE'), ('BOA CI', 'BOA CI'), ('BOA TG', 'BOA TG'),
    ('BOA SN', 'BOA SN'), ('BOA ML', 'BOA ML'), ('BOA BF', 'BOA BF'),
    ('BOA BJ', 'BOA BJ'), ('BOA CD', 'BOA CD'), ('CG', 'CG'),
    ('BCB', 'BCB'), ('BOA MR', 'BOA MR'), ('BOA MG', 'BOA MG'),
    ('BOA UG', 'BOA UG'), ('BOA TZ', 'BOA TZ'), ('BOA RW', 'BOA RW'),
    ('BOA KE', 'BOA KE'), ('BOA FR', 'BOA FR'), ('BOA KM', 'BOA KM'),
    ('BOA GH', 'BOA GH'), ('BOA Group', 'BOA Group'),
)





class ProfileV(AbstractUser):
    USERNAME_FIELD = 'username'
    organe = models.CharField(choices=Organe, max_length=50, default="Chargé Client")
    filiale = models.CharField(choices=Filiales, max_length=10, default="BOA Group")

    code_expl = models.CharField(blank=True, max_length=10, default="")

                                                                                              
                                                                           
    agence = models.CharField(blank=True, max_length=100, default="")

    téléphone = models.CharField(max_length=20, default="")
    avatar = models.ImageField(blank=True, upload_to="profile_avatars/", default="default.jpg")
    updated_at = models.DateTimeField(auto_now=True)
    force_password_change = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.email} - {self.filiale} ({self.organe})"

                                               
    @property
    def expl(self):
        return self.code_expl

    @property
    def nom(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def agence_lib(self):
        return self.agence

class Zone(models.Model):
     """Modèle pour définir les zones par filiale regroupant plusieurs agences"""
     directeur = models.EmailField( max_length=100, blank=True)
     zone = models.CharField(max_length=100, default="")
                                         
     agence = models.CharField(max_length=100, default="")
     filiale = models.CharField(choices=Filiales, max_length=10, default="BOA Group")

     def __str__(self):
         return f"Agence {self.agence} - {self.zone} ({self.filiale})"


class UserLoginHistory(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_events",
    )
    login_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-login_at",)
        indexes = [models.Index(fields=("login_at", "user"))]
        verbose_name = "Historique de connexion"
        verbose_name_plural = "Historiques de connexion"

    def __str__(self):
        return f"{self.user_id} - {self.login_at:%Y-%m-%d %H:%M:%S}"


class AuditEvent(models.Model):
    """Journal d'audit central de la plateforme KYC.

    Alimente l'onglet Administration > Audit : connexions, habilitations,
    imports, mises a jour de donnees, parametrage et actions sensibles.
    """

    CAT_CONNEXION = "CONNEXION"
    CAT_HABILITATION = "HABILITATION"
    CAT_IMPORT = "IMPORT"
    CAT_DONNEES = "DONNEES"
    CAT_CONFIG = "CONFIG"
    CAT_EXPORT = "EXPORT"
    CAT_SCREENING = "SCREENING"
    CAT_NOTATION = "NOTATION"
    CAT_SECURITE = "SECURITE"

    CATEGORIES = (
        (CAT_CONNEXION, "Connexion"),
        (CAT_HABILITATION, "Habilitation"),
        (CAT_IMPORT, "Import de donnees"),
        (CAT_DONNEES, "Mise a jour de donnees"),
        (CAT_CONFIG, "Parametrage"),
        (CAT_EXPORT, "Export"),
        (CAT_SCREENING, "Screening KYC ID"),
        (CAT_NOTATION, "Notation"),
        (CAT_SECURITE, "Securite"),
    )

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="audit_events",
    )
    username = models.CharField(max_length=150, blank=True, default="",
                                help_text="Identifiant saisi (conserve meme si le compte est supprime).")
    filiale = models.CharField(max_length=20, blank=True, default="")
    organe = models.CharField(max_length=50, blank=True, default="")
    category = models.CharField(max_length=20, choices=CATEGORIES, default=CAT_DONNEES, db_index=True)
    action = models.CharField(max_length=120, default="")
    target = models.CharField(max_length=255, blank=True, default="",
                              help_text="Objet concerne (utilisateur, regle, lot, fichier...).")
    details = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    success = models.BooleanField(default=True)

    class Meta:
        ordering = ("-timestamp",)
        verbose_name = "Evenement d'audit"
        verbose_name_plural = "Evenements d'audit"
        indexes = [
            models.Index(fields=("timestamp", "category")),
            models.Index(fields=("user", "timestamp")),
        ]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M:%S} - {self.category} - {self.action}"
