from django import template

register = template.Library()

SPECIALS = {
    'NE': 'NE', 'CI': 'CI', 'TG': 'TG', 'SN': 'SN', 'ML': 'ML', 'BF': 'BF',
    'BJ': 'BJ', 'RDC': 'CD', 'CG': 'CG', 'BCB': 'BI', 'MR': 'MR', 'MG': 'MG',
    'UG': 'UG', 'TZ': 'TZ', 'RW': 'RW', 'KE': 'KE', 'FR': 'FR',
    'GROUP': 'SN', 'GH': 'GH',
}

@register.filter
def filiale_iso(filiale):
    if not filiale:
        return ""
    key = str(filiale).strip().upper()
    if key.startswith("BOA "):
        key = key[4:].strip()
    if "GROUPE" in key:
        key = "GROUP"
    iso = SPECIALS.get(key)
    if not iso and len(key) == 2 and key.isalpha():
        iso = key
    return iso or ""

@register.filter
def filiale_flag_path(filiale):
    """Retourne le chemin statique vers le drapeau"""
    iso = filiale_iso(filiale)
    if not iso:
        return ""
    return f"flags/{iso.lower()}.svg"
