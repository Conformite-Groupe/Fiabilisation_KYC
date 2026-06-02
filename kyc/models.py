from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from datetime import datetime
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import models
from django.utils import timezone
from django.conf import settings

from PIL import Image


Type = (
    ('Agent', 'Agent'),
    ('Contrôleur', 'Contrôleur'),
)
FS = (
    ('Flux', 'Flux'),
    ('Stock', 'Stock'),
)

NoteChoices = (
    ('Très Bien', 'Très Bien'),
    ('Bien', 'Bien'),
    ('Passable', 'Passable'),
    ('Insuffisant','Insuffisant'),
)

APPLICABILITY_CHOICES = (
    ('PP', 'Client PP'),
    ('PM', 'Client PM'),
)

DATA_QUALITY_CONTROL_TYPE_CHOICES = (
    ('simple', 'Contrôle simple (Existence / Valeur)'),
    ('composite', 'Règle multi-critères (Composite)'),
)

OPERATOR_CHOICES = (
    ('=', 'Égal à (=)'),
    ('!=', 'Différent de (!=)'),
    ('>', 'Supérieur à (>)'),
    ('<', 'Inférieur à (<)'),
    ('>=', 'Supérieur ou égal (>=)'),
    ('<=', 'Inférieur ou égal (<=)'),
    ('contains', 'Contient'),
    ('regex', 'Expression régulière'),
    ('is_empty', 'Est vide'),
    ('is_not_empty', 'N\'est pas vide'),
    ('expired', 'Est expiré (Date < Aujourd\'hui)'),
    ('age_gt', 'Âge supérieur à'),
    ('age_lt', 'Âge inférieur à'),
    ('min_length', 'Longueur minimum'),
    ('max_length', 'Longueur maximum'),
)

PP_FIELD_CHOICES = (
    ('CODAPE', 'CODAPE'),
    ('IDP', 'IDP'),
    ('PAYNAIS', 'PAYNAIS'),
    ('PROFESSION', 'PROFESSION'),
    ('ADRESSE', 'ADRESSE'),
    ('PAYS_RESID', 'PAYS_RESID'),
    ('NUMID', 'NUMID'),
    ('SALAIRE', 'SALAIRE'),
    ('DATVALID', 'DATVALID'),
    ('DATNAIS', 'DATNAIS'),
    ('TEL', 'TEL'),
    ('DATOUV', 'DATOUV'),
    ('PPE', 'PPE'),
    ('DEVISE', 'DEVISE'),
    ('RESID', 'RESID'),
)

PM_FIELD_CHOICES = (
    ('CODAPE', 'CODAPE'),
    ('AGEC', 'AGEC'),
    ('IDM', 'IDM'),
    ('RCSNO', 'RCSNO'),
    ('CAPITAL', 'CAPITAL'),
    ('CA', 'CA'),
    ('DATOUV', 'DATOUV'),
    ('TEL', 'TEL'),
    ('DEVISE', 'DEVISE'),
    ('RESID', 'RESID'),
)

DATA_QUALITY_FIELD_CHOICES = PP_FIELD_CHOICES + PM_FIELD_CHOICES

class DataQualityRule(models.Model):
    name = models.CharField(max_length=200)
    applicability = models.CharField(max_length=3, choices=APPLICABILITY_CHOICES)
    field_name = models.CharField(max_length=100, choices=DATA_QUALITY_FIELD_CHOICES)
    control_type = models.CharField(max_length=50, choices=DATA_QUALITY_CONTROL_TYPE_CHOICES)
    parameter = models.CharField(blank=True, max_length=200, help_text='Seuil, longueur ou valeur de référence')
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} [{self.applicability}]"

class DataQualityCondition(models.Model):
    rule = models.ForeignKey(DataQualityRule, on_delete=models.CASCADE, related_name='conditions')
    field_name = models.CharField(max_length=100, choices=DATA_QUALITY_FIELD_CHOICES)
    operator = models.CharField(max_length=20, choices=OPERATOR_CHOICES)
    value = models.CharField(max_length=255, blank=True, null=True, help_text="Valeur fixe")

    def __str__(self):
        return f"{self.field_name} {self.operator} {self.value}"

class DataQualityRuleAudit(models.Model):
    rule_name = models.CharField(max_length=200)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=50) # CREATION, MODIFICATION, SUPPRESSION
    details = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']


DOCUMENT_EXTRACTION_TYPE_CHOICES = (
    ('piece_identite', "Piece d'identite"),
    ('passeport', 'Passeport'),
)


class KycDocumentExtraction(models.Model):
    document_type = models.CharField(max_length=30, choices=DOCUMENT_EXTRACTION_TYPE_CHOICES)
    uploaded_file = models.FileField(upload_to='document_extraction/')
    original_filename = models.CharField(max_length=255, blank=True)
    source_filename = models.CharField(max_length=255, blank=True)
    import_batch = models.CharField(max_length=120, blank=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    page_range = models.CharField(max_length=30, blank=True)
    nom = models.CharField(max_length=120, blank=True)
    prenom = models.CharField(max_length=120, blank=True)
    numero_document = models.CharField(max_length=120, blank=True)
    date_naissance = models.CharField(max_length=120, blank=True)
    date_expiration = models.CharField(max_length=120, blank=True)
    nationalite = models.CharField(max_length=120, blank=True)
    pays_naissance = models.CharField(max_length=120, blank=True)
    pays_delivrance = models.CharField(max_length=120, blank=True)
    numero_identification_nationale = models.CharField(max_length=120, blank=True)
    lieu_naissance = models.CharField(max_length=120, blank=True)
    adresse = models.CharField(max_length=255, blank=True)
    origine_revenu = models.CharField(max_length=120, blank=True)
    extracted_text = models.TextField(blank=True)
    extraction_warnings = models.TextField(blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['document_type']),
            models.Index(fields=['numero_document']),
            models.Index(fields=['nom']),
            models.Index(fields=['prenom']),
            models.Index(fields=['date_naissance']),
            models.Index(fields=['date_expiration']),
            models.Index(fields=['nationalite']),
            models.Index(fields=['pays_delivrance']),
            models.Index(fields=['import_batch']),
        ]

    def __str__(self):
        reference = self.numero_document or self.original_filename or str(self.pk)
        return f"{self.get_document_type_display()} - {reference}"


class KycDocumentMatchSettings(models.Model):
    name = models.CharField(max_length=80, default="Parametrage standard", unique=True)
    birth_date_weight = models.PositiveSmallIntegerField(default=35, validators=[MaxValueValidator(100)], verbose_name="Poids date de naissance")
    document_validity_weight = models.PositiveSmallIntegerField(default=35, validators=[MaxValueValidator(100)], verbose_name="Poids date de validite")
    birth_place_weight = models.PositiveSmallIntegerField(default=10, validators=[MaxValueValidator(100)], verbose_name="Poids lieu de naissance")
    nationality_weight = models.PositiveSmallIntegerField(default=20, validators=[MaxValueValidator(100)], verbose_name="Poids nationalite")
    combination_threshold = models.PositiveSmallIntegerField(default=65, validators=[MaxValueValidator(100)], verbose_name="Seuil de correspondance combinee")
    active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parametrage de correspondance KYC ID"
        verbose_name_plural = "Parametrage des correspondances KYC ID"

    def clean(self):
        total = self.birth_date_weight + self.document_validity_weight + self.birth_place_weight + self.nationality_weight
        if total > 100:
            raise ValidationError(
                "La somme des poids de correspondance ne doit pas depasser 100."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def get_active(cls):
        settings = cls.objects.filter(active=True).order_by("-updated_at").first()
        if settings:
            return settings
        return cls(
            name="Parametrage standard",
            birth_date_weight=35,
            document_validity_weight=35,
            birth_place_weight=10,
            nationality_weight=20,
            combination_threshold=65,
            active=True,
        )


class KycExpiredDocumentScanMatch(models.Model):
    STATUS_CHOICES = (
        ("a_valider", "A valider"),
        ("valide", "Valide"),
        ("rejete", "Rejete"),
    )

    client = models.ForeignKey("Kyc_pp", on_delete=models.CASCADE, related_name="expired_document_matches")
    document = models.ForeignKey(KycDocumentExtraction, on_delete=models.CASCADE, related_name="expired_kyc_matches")
    client_code = models.CharField(max_length=200, blank=True)
    idp = models.CharField(max_length=200, blank=True)
    filiale = models.CharField(max_length=200, blank=True)
    agence = models.CharField(max_length=200, blank=True)
    old_validity_date = models.CharField(max_length=120, blank=True)
    document_validity_date = models.CharField(max_length=120, blank=True)
    match_rate = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="a_valider")
    scan_date = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-scan_date"]
        verbose_name = "Correspondance document expire KYC"
        verbose_name_plural = "Correspondances documents expires KYC"
        constraints = [
            models.UniqueConstraint(
                fields=["client", "document"],
                name="unique_expired_kyc_document_match",
            )
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["client_code"]),
            models.Index(fields=["filiale", "agence"]),
            models.Index(fields=["scan_date"]),
        ]

    def __str__(self):
        return f"{self.client_code or self.client_id} - {self.document_validity_date}"


class KycDocumentMatchJob(models.Model):
    STATUS_CHOICES = (
        ("pending", "En attente"),
        ("running", "En cours"),
        ("completed", "Termine"),
        ("failed", "Echec"),
    )

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    scope_params = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    progress_current = models.PositiveIntegerField(default=0)
    progress_total = models.PositiveIntegerField(default=0)
    message = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    @property
    def progress_percent(self):
        if not self.progress_total:
            return 0
        return min(100, int(self.progress_current / self.progress_total * 100))

    def __str__(self):
        return f"Rapprochement documents #{self.pk} - {self.get_status_display()}"


Filiales = (
    ('BOA NE', 'BOA NE'),
    ('BOA CI', 'BOA CI'),
    ('BOA TG', 'BOA TG'),
    ('BOA SN', 'BOA SN'),
    ('BOA ML', 'BOA ML'),
    ('BOA BF', 'BOA BF'),
    ('BOA BJ', 'BOA BJ'),
    ('BOA RDC', 'RDC'),
    ('LCB', 'LCB'),
    ('BCB', 'BCB'),
    ('BOA MR', 'BOA MR'),
    ('BOA MG', 'BOA MG'),
    ('BOA UG', 'BOA UG'),
    ('BOA TZ', 'BOA TZ'),
    ('BOA RW', 'BOA RW'),
    ('BOA KE', 'BOA KE'),
    ('BOA FR', 'BOA FR'),
    ('BOA KM', 'BOA KM'),
    ('BOA GH', 'BOA GH'),
    ('BOA Group', 'BOA Group'),
)




class Person(models.Model):
    username = models.EmailField(blank=True,max_length=30, default='')
    first_name = models.CharField(blank=True,max_length=30, default='')
    last_name = models.CharField(blank=True,max_length=30,  default='')
    email = models.EmailField()
    telephone = models.CharField(blank=True,max_length=20)
    password = models.CharField(blank=True,max_length=32,  default='')
    Photo_profil = models.ImageField(upload_to="media", blank=True, null=True)
    def __str__(self):
        return self.first_name +" "+ self.last_name


class Notation(models.Model):
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notations")
    note = models.CharField(choices=NoteChoices, default="Bien", max_length=15)
    flux_stock = models.CharField(choices=FS, max_length=15, default="")
    # Nouveau champ ajouté ici :
    recommandation = models.TextField(blank=True, null=True)
    date_notation = models.DateTimeField(default=timezone.now)
    note_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        code = getattr(self.agent, "code_expl", "") or getattr(self.agent, "username", "")
        return f"{code} - {self.note} - {self.recommandation[:20]}..."

class Historique(models.Model):
      agent= models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.CASCADE, related_name="historiques")
      notation= models.ForeignKey(Notation,on_delete=models.CASCADE)


class Compte(models.Model):
    TYPE_COMPTE_CHOICES = [
        ('PPE', 'Personne Politiquement Exposée'),
        ('DEV', 'Compte en Devise'),
        ('NON_RES', 'Non Résident'),
        ('scoring', 'Compte scoring'),
    ]
    agent = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comptes")
    type_compte = models.CharField(blank=True,max_length=10, choices=TYPE_COMPTE_CHOICES)
    solde = models.DecimalField(max_digits=15, decimal_places=2)
    devise = models.CharField(blank=True,max_length=3)
    date_ouverture = models.DateField()

    def __str__(self):
        return f"{self.agent.email} - {self.type_compte}"


class Kyc_pm(models.Model):
    FILIALE = models.CharField(blank=True,max_length=200)
    AGENCE = models.CharField(blank=True,max_length=200)
    LIB_AGENCE = models.CharField(blank=True,max_length=50)
    EXPL = models.CharField(blank=True,max_length=200)
    CLIENT = models.CharField(blank=True,max_length=200)
    AGEC = models.CharField(blank=True,max_length=200)
    CODAPE = models.CharField(blank=True,max_length=200)
    IDM = models.CharField(blank=True,max_length=200)
    RCSNO = models.CharField(blank=True,max_length=200)
    CAPITAL = models.CharField(blank=True,max_length=200)
    CA = models.CharField(blank=True,max_length=200)
    RESULTAT = models.CharField(blank=True,max_length=200)
    ORIGINE_REV = models.CharField(blank=True,max_length=200)
    DATOUV = models.CharField(blank=True, max_length=200)
    TEL = models.CharField(blank=True,max_length=200)
    DEVISE = models.CharField(blank=True, max_length=200)
    RESID = models.CharField(blank=True, max_length=200)

    def __str__(self):
        return f"{self.CLIENT} - {self.FILIALE}"

class Kyc_pp(models.Model):
    FILIALE = models.CharField(blank=True,max_length=200)
    AGENCE = models.CharField(blank=True,max_length=200)
    LIB_AGENCE = models.CharField(blank=True,max_length=50)
    EXPL = models.CharField(blank=True,max_length=200)
    CLIENT = models.CharField(blank=True,max_length=200)
    CODAPE = models.CharField(blank=True,max_length=200)
    IDP = models.CharField(blank=True,max_length=200)
    PAYNAIS = models.CharField(blank=True,max_length=200)
    PROFESSION = models.CharField(blank=True,max_length=200)
    ADRESSE = models.CharField(blank=True,max_length=200)
    PAYS_RESID = models.CharField(blank=True,max_length=200)
    NUMID = models.CharField(blank=True,max_length=200)
    SALAIRE = models.CharField(blank=True,max_length=200)
    ORIGINE_REV = models.CharField(blank=True,max_length=200)
    DATVALID = models.CharField(blank=True,max_length=200)
    DATNAIS = models.CharField(blank=True,max_length=200)
    TEL = models.CharField(blank=True,max_length=200)
    DATOUV = models.CharField(blank=True, max_length=200)
    PPE = models.CharField(blank=True,max_length=200)
    DEVISE = models.CharField(blank=True, max_length=200)
    RESID = models.CharField(blank=True, max_length=200)
    def __str__(self):
        return f"{self.CLIENT} - {self.FILIALE}"

#lass Filiale(models.Model):
#   code = models.CharField(blank=True,max_length=5, unique=True)

#   def __str__(self):
#       return self.code

class Anomalie(models.Model):
    FILIALE = models.CharField(blank=True,max_length=200)
    AGENCE = models.CharField(blank=True,max_length=200)
    LIB_AGENCE = models.CharField(blank=True,max_length=50)
    EXPL = models.CharField(blank=True,max_length=200)
    CLIENT = models.CharField(blank=True,max_length=200)
    ANOMALIE_AGE = models.CharField(blank=True,max_length=200)
    ANOMALIE_DATE_EER = models.CharField(blank=True,max_length=200)
    ANOMALIE_CIN = models.CharField(blank=True,max_length=200)
    PPE = models.CharField(blank=True,max_length=200)

    def __str__(self):
        return f"{self.CLIENT} - {self.FILIALE}"

class TauxEvolution(models.Model):
    filiale = models.CharField(blank=True,max_length=10)
    agence   = models.CharField(blank=True,max_length=50,null=True)
    expl     = models.CharField(blank=True,max_length=50)
    date     = models.DateField(blank=True)
    taux     = models.FloatField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    flux_stock = models.CharField(blank=True,max_length=50)
    pp_pm = models.CharField(blank=True,max_length=50)

    class Meta:
        ordering = ['filiale', 'expl', 'date']
    def __str__(self):
        return f"{self.filiale} - {self.expl}"

from django.db import models

class TauxEvolution_filiale(models.Model):
    filiale = models.CharField(blank=True, max_length=10)
    flux_PM = models.FloatField(null=True, blank=True)
    flux_PP = models.FloatField(null=True, blank=True)
    stock_PM = models.FloatField(null=True, blank=True)
    stock_PP = models.FloatField(null=True, blank=True)
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.filiale} – {self.date}"

class DATEREV(models.Model):
    FILIALE = models.CharField(blank=True, max_length=10)
    AGENCE = models.CharField(blank=True, max_length=10)
    LIB_AGENCE = models.CharField(blank=True, max_length=50)
    EXPL = models.CharField(blank=True, max_length=10)
    CLIENT = models.CharField(blank=True, max_length=10)
    DATEREV = models.DateField(blank=True, null=True)
    PPE = models.CharField(blank=True, max_length=20)
    RISQUE = models.CharField(blank=True, max_length=20)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["CLIENT"],
                condition=models.Q(CLIENT__gt=""),
                name="uniq_daterev_client_non_empty",
            ),
        ]

    def __str__(self):
        return f"{self.FILIALE} - {self.EXPL}"



class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    avatar = models.ImageField(default='default.jpg', upload_to='profile_avatars/')
    updated_at = models.DateTimeField(auto_now=True)  # ← ajouté

    def __str__(self):
        return f'{self.user.username} Profile'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            img = Image.open(self.avatar.path)
            if img.height > 300 or img.width > 300:
                output_size = (300, 300)
                img.thumbnail(output_size)
                img.save(self.avatar.path)
        except Exception:
            pass

class Devise(models.Model):

    filiale =models.CharField(choices=Filiales, max_length=10, default='')
    devise = models.CharField(max_length=4, default='')

    def __str__(self):
        return f"{self.filiale} - {self.devise}"

