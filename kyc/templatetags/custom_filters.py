from django import template

register = template.Library()

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


from django import template
register = template.Library()

@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)