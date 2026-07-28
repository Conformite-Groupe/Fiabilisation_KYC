from django import template

register = template.Library()


def _glossary_en():
    """Dictionnaire {terme_fr: terme_en} mis en cache (glossaire admin)."""
    from django.core.cache import cache
    data = cache.get('term_glossary_en')
    if data is None:
        from kyc.models import TermTranslation
        data = {t.terme_fr: t.terme_en
                for t in TermTranslation.objects.all().only('terme_fr', 'terme_en')}
        cache.set('term_glossary_en', data, 600)
    return data


@register.filter(name='t')
def translate_term(value):
    """Traduit un terme selon la langue active :
    - FR : renvoie le texte d'origine ;
    - EN (ou autre) : glossaire admin d'abord, sinon catalogue gettext, sinon FR.
    Usage : {{ "Taux de complétude"|t }}
    """
    if value is None:
        return value
    text = str(value)
    from django.utils import translation
    lang = translation.get_language() or 'fr'
    if lang.startswith('fr'):
        return text
    en = _glossary_en().get(text.strip())
    if en:
        return en
                                                                          
    return translation.gettext(text)

@register.filter
def split(value, arg=None):
    """
    Divise une chaîne de caractères en une liste de sous-chaînes
    en utilisant l'argument comme séparateur.
    """
    if arg is None:
        arg = ' '
    return value.split(arg)

@register.filter
def intersect(list1, list2):
    """
    Retourne la liste des éléments communs (intersection) entre deux listes.
    Utile pour vérifier si deux listes de chaînes ont des éléments en commun.
    """
    if not isinstance(list1, list) or not isinstance(list2, list):
        return []
    return list(set(list1) & set(list2))

@register.filter(name='as_bool')
def as_bool(value):
    """
    Convertit la valeur en booléen.
    Utile pour les vérifications de longueur (0 = False, >0 = True).
    """
    if isinstance(value, int):
        return value > 0
    return bool(value)

@register.filter
def get_item(dictionary, key):
    if not hasattr(dictionary, "get"):
        return ""
    lower_key = str(key).lower()
    return dictionary.get(f"col_{lower_key}", dictionary.get(key, dictionary.get(lower_key, "")))


@register.filter
def attr(obj, name):
    if obj is None:
        return ""
    if isinstance(obj, dict):
        return obj.get(name, "")
    return getattr(obj, name, "")

import json
@register.filter
def to_json(value):
    return json.dumps(value)


@register.filter
def latest_flux_notation(user):
    if not user or not user.is_authenticated:
        return None
    return user.notations.filter(flux_stock='Flux').order_by('-date_notation').first()


@register.filter
def appreciation_for(user):
    """Retourne l'instance Appreciation_globale de l'agent (par filiale + code_expl),
    ou None. Sert à afficher l'appréciation globale et la mesure."""
    if not user:
        return None
    fil = (getattr(user, 'filiale', '') or '').strip()
    expl = (getattr(user, 'code_expl', '') or '').strip()
    if not fil or not expl:
        return None
    from kyc.models import Appreciation_globale
    return (Appreciation_globale.objects
            .filter(filiale__iexact=fil, expl__iexact=expl)
            .first())

