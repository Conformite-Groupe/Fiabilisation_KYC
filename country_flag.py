from django import template

register = template.Library()

@register.filter
def filiale_to_iso(filiale):
    mapping = {
        'BOA NE': 'NE', 'CI': 'CI', 'TG': 'TG', 'SN': 'SN',
        'ML': 'ML', 'BOA BF': 'BF', 'BJ': 'BJ', 'RDC': 'CD',
        'BOA CD': 'CD', 'CD': 'CD',
        'CG': 'CG', 'BCB': 'BI', 'MR': 'MR', 'MG': 'MG',
        'UG': 'UG', 'TZ': 'TZ', 'RW': 'RW', 'KE': 'KE',
        'FR': 'FR', 'GH': 'GH',
    }
    return mapping.get(filiale, '')
