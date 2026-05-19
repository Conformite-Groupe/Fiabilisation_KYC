from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from urllib.parse import urlencode

from .models import TauxEvolution, Devise
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin

from django.core.mail import send_mail, BadHeaderError

from .models import TauxEvolution_filiale
import json
import csv


import openpyxl
from django.template.loader import get_template
try:
    from xhtml2pdf import pisa
except ImportError:
    pisa = None
from kyc.models import (
    Notation, Historique, Kyc_pm, Kyc_pp, Anomalie, TauxEvolution, DATEREV,
    DataQualityRule, DataQualityRuleAudit, KycDocumentExtraction,
    DOCUMENT_EXTRACTION_TYPE_CHOICES,
)
from django.utils import timezone
from django.utils.decorators import method_decorator

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, FileResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from oauthlib.oauth2.rfc6749.endpoints import token

from django.db.models import Max, Avg, Count, F, Q
from django.db.models.functions import TruncDate

from django.http import JsonResponse
from .models import Kyc_pp

from accounts.models import ProfileV, UserLoginHistory
from django.core.cache import cache
from kyc import forms
from kyc.forms import CustomUserCreationForm, LoginForm, ResetPasswordForm, UserEditForm, VoyageurProfileForm, \
    CambProfileForm, \
    ProfileModify, NotationForm, ProfileForm
from django.contrib.sessions.models import Session
from django.utils.timezone import now
from django.utils.dateparse import parse_date, parse_datetime

from io import BytesIO
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from datetime import datetime, timedelta
from .models import Kyc_pp
from django.conf import settings
from django.core.files.base import ContentFile
import os
import re
import sys
import subprocess
import hashlib
import math
import uuid
import zipfile
from .document_extraction import SUPPORTED_EXTENSIONS, extract_document_data, extract_pdf_grouped_documents

def floor_one_decimal(value):
    return math.floor(value * 10) / 10

def compliance_rate_floor(ok_count, total, fail_count=0):
    if not total:
        return None

    rate = floor_one_decimal(ok_count / total * 100)
    if fail_count > 0 and rate >= 100:
        return 99.9
    return rate

def _pdf_link_callback(uri, rel):
    """Resolve static/media URIs for xhtml2pdf on local filesystem."""
    if uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
    elif uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        if not os.path.isfile(path):
            path = os.path.join(settings.BASE_DIR, "static", uri.replace(settings.STATIC_URL, ""))
    else:
        return uri

    if not os.path.isfile(path):
        raise Exception(f"Media URI must start with {settings.MEDIA_URL} or {settings.STATIC_URL}: {uri}")
    return path


def format_date_for_export(value, output_format="%d/%m/%Y", empty_value="-"):
    """Format date/datetime/string values safely for exports."""
    if value in (None, ""):
        return empty_value

    if hasattr(value, "strftime"):
        try:
            return value.strftime(output_format)
        except Exception:
            pass

    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return empty_value

        parsed_dt = parse_datetime(cleaned)
        if parsed_dt:
            return parsed_dt.strftime(output_format)

        parsed_d = parse_date(cleaned)
        if parsed_d:
            return parsed_d.strftime(output_format)

        for input_format in ("%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y%m%d"):
            try:
                return datetime.strptime(cleaned, input_format).strftime(output_format)
            except ValueError:
                continue

        return cleaned

    return str(value)

def get_data_quality_field_options():
    return {
        'PP': [
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
        ],
        'PM': [
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
        ],
    }


def evaluate_data_quality_scope(user):
    """Détermine le périmètre de calcul qualité selon l'organe utilisateur."""
    organe = (getattr(user, 'organe', '') or '').strip()
    filiale = (getattr(user, 'filiale', '') or '').strip()
    agence = (getattr(user, 'agence', '') or '').strip()
    code_expl = (getattr(user, 'code_expl', '') or '').strip()

    if organe == 'Chargé Client':
        return {
            'filiale': filiale or None,
            'agence': agence or None,
            'expl': code_expl or None,
            'label': 'Mon portefeuille',
        }
    if organe == 'Directeur Agence':
        return {
            'filiale': filiale or None,
            'agence': agence or None,
            'expl': None,
            'label': f"Agence {agence}" if agence else 'Mon agence',
        }
    if organe == 'PASS' or 'Groupe' in organe:
        return {
            'filiale': None,
            'agence': None,
            'expl': None,
            'label': 'GROUPE (toutes filiales)',
        }

    return {
        'filiale': filiale or None,
        'agence': None,
        'expl': None,
        'label': filiale or 'Ma filiale',
    }


def evaluate_data_quality_rule(rule, filiale=None, agence=None, expl=None):
    model = Kyc_pp if rule.applicability == 'PP' else Kyc_pm
    field_names = [f.name for f in model._meta.get_fields() if not f.many_to_many and not f.one_to_many]
    if rule.control_type != 'composite' and rule.field_name not in field_names and rule.control_type not in ['expired_document', 'codape_agec_match']:
        return {'total': 0, 'fail_count': 0, 'ok_count': 0, 'clients': [], 'message': 'Champ de contrôle invalide'}

    queryset = model.objects.all()
    if filiale and filiale != 'GROUPE':
        queryset = queryset.filter(FILIALE=filiale)
    if agence:
        queryset = queryset.filter(AGENCE=agence)
    if expl:
        queryset = queryset.filter(EXPL=expl)
        
    total = queryset.count()
    if total == 0:
        return {'total': 0, 'fail_count': 0, 'ok_count': 0, 'clients': [], 'message': 'Aucune donnée disponible pour ce segment'}

    failures = []
    today = datetime.today().date()
    client_fields = ['CLIENT', 'EXPL', 'FILIALE', 'AGENCE']

    def safe_parse_date(value):
        if not value: return None
        if hasattr(value, 'date'): return value.date()
        if isinstance(value, str):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    continue
        return None

    def calculate_age(birth_date_str):
        parsed = safe_parse_date(birth_date_str)
        if not parsed: return None
        today_date = datetime.today().date()
        return today_date.year - parsed.year - ((today_date.month, today_date.day) < (parsed.month, parsed.day))

    def build_clients_from_values(rows, value_key):
        return [{
            'client': row.get('CLIENT', ''),
            'expl': row.get('EXPL', ''),
            'filiale': row.get('FILIALE', ''),
            'agence': row.get('AGENCE', ''),
            'field_value': str(row.get(value_key, '') or ''),
        } for row in rows]

    if rule.control_type == 'simple':
        param = (rule.parameter or '').strip().lower()
        
        # Determine if it's existence, length, or value match
        if not param or param == 'existence':
            # Existence check (is empty?)
            failures = queryset.filter(Q(**{f"{rule.field_name}__isnull": True}) | Q(**{f"{rule.field_name}": ""}))
            fail_count = failures.count()
            clients = build_clients_from_values(list(failures.values(*client_fields, rule.field_name)[:15]), rule.field_name)
        
        elif param.isdigit() or (param.startswith('len') or param.startswith('long')):
            # Length check
            try:
                # Extract number from param if it's like 'length:10'
                import re
                match = re.search(r'\d+', param)
                target_len = int(match.group()) if match else int(param)
                
                fail_count = 0
                clients = []
                for row in queryset.values(*client_fields, rule.field_name).iterator(chunk_size=2000):
                    val = str(row.get(rule.field_name) or '')
                    if len(val) != target_len:
                        fail_count += 1
                        if len(clients) < 15:
                            clients.append({
                                'client': row.get('CLIENT', ''),
                                'expl': row.get('EXPL', ''),
                                'filiale': row.get('FILIALE', ''),
                                'agence': row.get('AGENCE', ''),
                                'field_value': val,
                            })
            except:
                return {'total': total, 'fail_count': 0, 'ok_count': total, 'clients': [], 'message': 'Paramètre de longueur invalide'}
        
        else:
            # Value match check
            failures = queryset.exclude(**{f"{rule.field_name}": rule.parameter})
            fail_count = failures.count()
            clients = build_clients_from_values(list(failures.values(*client_fields, rule.field_name)[:15]), rule.field_name)

        ok_count = total - fail_count
        return {
            'total': total,
            'fail_count': fail_count,
            'ok_count': ok_count,
            'clients': clients,
            'message': '',
        }

    elif rule.control_type == 'composite':
        conditions = rule.conditions.all()
        if not conditions.exists():
            return {'total': total, 'fail_count': 0, 'ok_count': total, 'clients': [], 'message': 'Pas de conditions'}
        
        fail_count = 0
        clients = []
        needed_fields = set(client_fields)
        for c in conditions:
            needed_fields.add(c.field_name)
        for row in queryset.values(*needed_fields).iterator(chunk_size=2000):
            all_match = True
            for cond in conditions:
                val = str(row.get(cond.field_name, '') or '').strip()
                target = (cond.value or '').strip()
                
                match = False
                op = cond.operator
                if op == '=': match = val == target
                elif op == '!=': match = val != target
                elif op == '>':
                    try: match = float(val.replace(',','.')) > float(target.replace(',','.'))
                    except: match = False
                elif op == '<':
                    try: match = float(val.replace(',','.')) < float(target.replace(',','.'))
                    except: match = False
                elif op == '>=':
                    try: match = float(val.replace(',','.')) >= float(target.replace(',','.'))
                    except: match = False
                elif op == '<=':
                    try: match = float(val.replace(',','.')) <= float(target.replace(',','.'))
                    except: match = False
                elif op == 'contains': match = target.lower() in val.lower()
                elif op == 'is_empty': match = not val
                elif op == 'is_not_empty': match = bool(val)
                elif op == 'expired':
                    p = safe_parse_date(val)
                    match = p and p < today
                elif op == 'age_gt':
                    age = calculate_age(val)
                    try: match = age is not None and age > int(target)
                    except: match = False
                elif op == 'age_lt':
                    age = calculate_age(val)
                    try: match = age is not None and age < int(target)
                    except: match = False
                elif op == 'min_length':
                    try: match = len(val) < int(target) # C'est un échec si la longueur est inférieure au min
                    except: match = False
                elif op == 'max_length':
                    try: match = len(val) > int(target) # C'est un échec si la longueur est supérieure au max
                    except: match = False
                
                if not match:
                    all_match = False
                    break
            
            if all_match:
                fail_count += 1
                if len(clients) < 15:
                    clients.append({
                        'client': row.get('CLIENT', ''),
                        'expl': row.get('EXPL', ''),
                        'filiale': row.get('FILIALE', ''),
                        'agence': row.get('AGENCE', ''),
                        'field_value': 'Multi-critères',
                    })
        
        ok_count = total - fail_count
        return {
            'total': total,
            'fail_count': fail_count,
            'ok_count': ok_count,
            'clients': clients,
            'message': '',
        }

    return {
        'total': total,
        'fail_count': 0,
        'ok_count': total,
        'clients': [],
        'message': '',
    }


@login_required
def quality_control_view(request):
    user = request.user
    allowed_organs = ['Contrôle Permanent', 'Conformité', 'Qualité', 'DSI', 'Risques', 'DAI']
    if user.organe not in allowed_organs:
        messages.error(request, "Accès non autorisé au contrôle qualité.")
        return redirect('accueil')

    from kyc.forms import DataQualityRuleForm, DataQualityConditionFormSet

    # Vérification des droits de gestion
    user_organe = getattr(request.user, 'organe', '')
    can_manage = user_organe in ['Conformité', 'Contrôle Permanent', 'PASS']
    user_filiale = getattr(request.user, 'filiale', '')
    
    if request.method == 'POST' and can_manage:
        form = DataQualityRuleForm(request.POST)
        formset = DataQualityConditionFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            rule = form.save(commit=False)
            rule.created_by = request.user
            rule.save()
            formset.instance = rule
            formset.save()
            
            # Audit creation
            DataQualityRuleAudit.objects.create(
                rule_name=rule.name,
                user=request.user,
                action='CREATION',
                details=f"Création de la règle '{rule.name}' ({rule.applicability})"
            )
            
            current_version = cache.get('quality_control_rules_version', 1)
            cache.set('quality_control_rules_version', current_version + 1, timeout=None)
            messages.success(request, 'Règle de qualité enregistrée.')
            return redirect('kyc:quality_control')
    else:
        form = DataQualityRuleForm()
        formset = DataQualityConditionFormSet()

    rules = list(
        DataQualityRule.objects.all()
        .order_by('-active', '-created_at')
        .prefetch_related('conditions')
    )
    cache_ttl_seconds = 86400  # Cache journalier: donnees mises a jour 1 fois/jour
    rules_version = cache.get('quality_control_rules_version', 1)
    data_refresh_bucket = timezone.localdate().isoformat()
    stats = []
    
    # Portée de l'évaluation : vision groupe pour PASS et les organes Groupe
    group_organs = ['PASS', 'Conformité Groupe', 'Contrôle Permanent Groupe']
    eval_filiale = None if user_organe in group_organs else user_filiale

    for rule in rules:
        rule_signature = f"{rule.id}|{rule.name}|{rule.applicability}|{rule.field_name}|{rule.control_type}|{rule.parameter}|{rule.active}|{eval_filiale}"
        rule_hash = hashlib.md5(rule_signature.encode('utf-8')).hexdigest()
        rule_cache_key = f"quality_control:stat:v{rules_version}:d{data_refresh_bucket}:{rule_hash}"
        stat = cache.get(rule_cache_key)
        if stat is None:
            stat = evaluate_data_quality_rule(rule, filiale=eval_filiale)
            cache.set(rule_cache_key, stat, timeout=cache_ttl_seconds)
        stats.append(stat)
    for stat in stats:
        total = stat.get('total', 0)
        stat['compliance_rate'] = compliance_rate_floor(stat['ok_count'], total, stat.get('fail_count', 0))
    rules_with_stats = []
    for rule, stat in zip(rules, stats):
        grouped_conditions = {}
        for cond in rule.conditions.all():
            group_key = (cond.field_name, cond.operator)
            if group_key not in grouped_conditions:
                grouped_conditions[group_key] = {
                    'field_name': cond.field_name,
                    'operator_display': cond.get_operator_display(),
                    'values': [],
                }

            value = (cond.value or '').strip()
            if value and value not in grouped_conditions[group_key]['values']:
                grouped_conditions[group_key]['values'].append(value)

        rules_with_stats.append({
            'rule': rule,
            'stat': stat,
            'condition_groups': list(grouped_conditions.values()),
        })

    field_options = get_data_quality_field_options()
    total_rules = len(rules)
    active_rules = sum(1 for rule in rules if rule.active)
    inactive_rules = total_rules - active_rules
    total_failures = sum(stat['fail_count'] for stat in stats)
    total_ok = sum(stat['ok_count'] for stat in stats)
    total_evaluated = sum(stat['total'] for stat in stats)
    global_compliance_rate = compliance_rate_floor(total_ok, total_evaluated, total_failures)

    return render(request, 'quality_control.html', {
        'form': form,
        'formset': formset,
        'rules': rules_with_stats,
        'field_options': field_options,
        'total_rules': total_rules,
        'active_rules': active_rules,
        'inactive_rules': inactive_rules,
        'total_failures': total_failures,
        'global_compliance_rate': global_compliance_rate,
        'form_has_errors': bool(form.errors),
        'can_manage': can_manage,
        'user_organe': user_organe,
    })

@login_required
def delete_quality_rule(request, pk):
    user_organe = getattr(request.user, 'organe', '')
    if user_organe not in ['Conformité', 'Contrôle Permanent', 'PASS']:
        messages.error(request, "Accès refusé.")
        return redirect('kyc:quality_control')
        
    rule = get_object_or_404(DataQualityRule, pk=pk)
    
    # Vérification filiale si pas PASS
    if user_organe != 'PASS' and rule.created_by and rule.created_by.filiale != request.user.filiale:
        messages.error(request, "Vous ne pouvez supprimer que les règles de votre filiale.")
        return redirect('kyc:quality_control')

    rule_name = rule.name
    DataQualityRuleAudit.objects.create(
        rule_name=rule_name,
        user=request.user,
        action='SUPPRESSION',
        details=f"Suppression de la règle '{rule_name}'"
    )
    
    rule.delete()
    current_version = cache.get('quality_control_rules_version', 1)
    cache.set('quality_control_rules_version', current_version + 1, timeout=None)
    messages.success(request, f"Règle '{rule_name}' supprimée.")
    return redirect('kyc:quality_control')

@login_required
def edit_quality_rule(request, pk):
    user_organe = getattr(request.user, 'organe', '')
    if user_organe not in ['Conformité', 'Contrôle Permanent', 'PASS']:
        messages.error(request, "Accès refusé.")
        return redirect('kyc:quality_control')
        
    rule = get_object_or_404(DataQualityRule, pk=pk)
    
    # Vérification filiale si pas PASS
    if user_organe != 'PASS' and rule.created_by and rule.created_by.filiale != request.user.filiale:
        messages.error(request, "Vous ne pouvez modifier que les règles de votre filiale.")
        return redirect('kyc:quality_control')

    from kyc.forms import DataQualityRuleForm, DataQualityConditionFormSet
    
    if request.method == 'POST':
        form = DataQualityRuleForm(request.POST, instance=rule)
        formset = DataQualityConditionFormSet(request.POST, instance=rule)
        if form.is_valid() and formset.is_valid():
            changes = []
            if form.has_changed():
                for field in form.changed_data:
                    old = getattr(rule, field)
                    new = form.cleaned_data.get(field)
                    changes.append(f"{field}: {old} -> {new}")
            
            form.save()
            formset.save()
            
            DataQualityRuleAudit.objects.create(
                rule_name=rule.name,
                user=request.user,
                action='MODIFICATION',
                details="; ".join(changes) if changes else "Modification des conditions"
            )
            
            current_version = cache.get('quality_control_rules_version', 1)
            cache.set('quality_control_rules_version', current_version + 1, timeout=None)
            messages.success(request, "Règle mise à jour.")
            return redirect('kyc:quality_control')
    else:
        form = DataQualityRuleForm(instance=rule)
        formset = DataQualityConditionFormSet(instance=rule)
        
    return render(request, 'quality_rule_edit.html', {
        'form': form,
        'formset': formset,
        'rule': rule
    })

@login_required
def quality_control_audits(request):
    user_organe = getattr(request.user, 'organe', '')
    if user_organe not in ['Conformité', 'Contrôle Permanent', 'PASS']:
        messages.error(request, "Accès refusé.")
        return redirect('kyc:quality_control')
        
    if user_organe == 'PASS':
        audits = DataQualityRuleAudit.objects.all().order_by('-timestamp')
    else:
        # Inclure aussi les audits systeme (user null) pour eviter une page vide
        audits = DataQualityRuleAudit.objects.filter(
            Q(user__filiale=request.user.filiale) | Q(user__isnull=True)
        ).order_by('-timestamp')
        
    audits = list(audits)
    for audit in audits:
        raw_rule_name = (audit.rule_name or "")
        audit.rule_name_display = raw_rule_name.strip() or "N/A"
        audit.time_display = audit.timestamp.strftime("%H:%M:%S") if audit.timestamp else "--:--:--"
    return render(request, 'quality_control_audits.html', {'audits': audits})

@login_required
def export_audits_excel(request):
    user_organe = getattr(request.user, 'organe', '')
    if user_organe not in ['Conformité', 'Contrôle Permanent', 'PASS']:
        return HttpResponseForbidden()
        
    if user_organe == 'PASS':
        audits = DataQualityRuleAudit.objects.all().order_by('-timestamp')
    else:
        audits = DataQualityRuleAudit.objects.filter(
            Q(user__filiale=request.user.filiale) | Q(user__isnull=True)
        ).order_by('-timestamp')
        
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audit des Contrôles"
    ws.append(["Date & Heure", "Utilisateur", "Règle", "Action", "Détails"])
    for audit in audits:
        ws.append([audit.timestamp.strftime("%d/%m/%Y %H:%M:%S"), audit.user.username if audit.user else "System", audit.rule_name, audit.action, audit.details])
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = 'attachment; filename=audit_controles.xlsx'
    wb.save(response)
    return response

@login_required
def export_audits_pdf(request):
    user_organe = getattr(request.user, 'organe', '')
    if user_organe not in ['Conformité', 'Contrôle Permanent', 'PASS']:
        return HttpResponseForbidden()
        
    if user_organe == 'PASS':
        audits = DataQualityRuleAudit.objects.all().order_by('-timestamp')
    else:
        audits = DataQualityRuleAudit.objects.filter(
            Q(user__filiale=request.user.filiale) | Q(user__isnull=True)
        ).order_by('-timestamp')
        
    template_path = 'quality_control_audits_pdf.html'
    logo_rel_path = "images/boa.png"
    logo_full_path = os.path.join(settings.MEDIA_ROOT, logo_rel_path)
    context = {
        'audits': audits,
        'logo_path': logo_full_path if os.path.exists(logo_full_path) else None
    }
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="audit_controles.pdf"'
    template = get_template(template_path)
    html = template.render(context)
    if not pisa:
        return HttpResponse("L'exportation PDF n'est pas disponible sur ce serveur (dépendances manquantes).")
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=_pdf_link_callback)
    if pisa_status.err: return HttpResponse('Erreur PDF')
    return response

@login_required
def export_rule_failures(request, rule_id):
    rule = get_object_or_404(DataQualityRule, pk=rule_id)
    user_organe = getattr(request.user, 'organe', '')
    user_filiale = getattr(request.user, 'filiale', '')
    
    # Portée de l'évaluation
    group_organs = ['PASS', 'Conformité Groupe', 'Contrôle Permanent Groupe']
    eval_filiale = None if user_organe in group_organs else user_filiale
    
    # Re-évaluer pour obtenir TOUS les échecs (sans limite de 15)
    model = Kyc_pp if rule.applicability == 'PP' else Kyc_pm
    queryset = model.objects.all()
    if eval_filiale and eval_filiale != 'GROUPE':
        queryset = queryset.filter(FILIALE=eval_filiale)
        
    # Logic similar to evaluate_data_quality_rule but without chunking for building all failures
    # To avoid memory issues with huge datasets, we'll stream the response or just use values().iterator()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anomalies"
    
    # Headers dynamiques
    headers = ["CLIENT", "EXPL", "FILIALE", "AGENCE"]
    if rule.control_type == 'simple':
        headers.append(rule.field_name.upper())
    else:
        # Composite: tous les champs des conditions
        cond_fields = list(rule.conditions.values_list('field_name', flat=True))
        # Nettoyage des doublons tout en gardant l'ordre
        seen = set()
        unique_fields = [f for f in cond_fields if not (f in seen or seen.add(f))]
        for f in unique_fields:
            headers.append(f.upper())
            
    ws.append(headers)
    
    if rule.control_type == 'simple':
        param = (rule.parameter or '').strip().lower()
        if not param or param == 'existence':
            failures = queryset.filter(Q(**{f"{rule.field_name}__isnull": True}) | Q(**{f"{rule.field_name}": ""}))
            for row in failures.values("CLIENT", "EXPL", "FILIALE", "AGENCE", rule.field_name).iterator():
                ws.append([row['CLIENT'], row['EXPL'], row['FILIALE'], row['AGENCE'], str(row.get(rule.field_name) or '')])
        
        elif param.isdigit() or (param.startswith('len') or param.startswith('long')):
            import re
            match = re.search(r'\d+', param)
            target_len = int(match.group()) if match else int(param)
            for row in queryset.values("CLIENT", "EXPL", "FILIALE", "AGENCE", rule.field_name).iterator():
                val = str(row.get(rule.field_name) or '')
                if len(val) != target_len:
                    ws.append([row['CLIENT'], row['EXPL'], row['FILIALE'], row['AGENCE'], val])
        else:
            failures = queryset.exclude(**{f"{rule.field_name}": rule.parameter})
            for row in failures.values("CLIENT", "EXPL", "FILIALE", "AGENCE", rule.field_name).iterator():
                ws.append([row['CLIENT'], row['EXPL'], row['FILIALE'], row['AGENCE'], str(row.get(rule.field_name) or '')])
                
    elif rule.control_type == 'composite':
        conditions = rule.conditions.all()
        fields_to_fetch = ["CLIENT", "EXPL", "FILIALE", "AGENCE"]
        cond_fields = [c.field_name for c in conditions]
        unique_cond_fields = list(dict.fromkeys(cond_fields))
        fields_to_fetch.extend(unique_cond_fields)
        
        today = datetime.today().date()

        for row in queryset.values(*set(fields_to_fetch)).iterator():
            all_match = True
            for cond in conditions:
                val = str(row.get(cond.field_name, '') or '').strip()
                target = str(cond.value or '').strip()
                
                match = False
                op = cond.operator
                if op == '=': match = val == target
                elif op == '!=': match = val != target
                elif op == '>': 
                    try: match = float(val.replace(',','.')) > float(target.replace(',','.'))
                    except: match = False
                elif op == '<':
                    try: match = float(val.replace(',','.')) < float(target.replace(',','.'))
                    except: match = False
                elif op == '>=':
                    try: match = float(val.replace(',','.')) >= float(target.replace(',','.'))
                    except: match = False
                elif op == '<=':
                    try: match = float(val.replace(',','.')) <= float(target.replace(',','.'))
                    except: match = False
                elif op == 'contains': match = target.lower() in val.lower()
                elif op == 'is_empty': match = not val
                elif op == 'is_not_empty': match = bool(val)
                elif op == 'expired':
                    p = safe_parse_date(val)
                    match = p and p < today
                elif op == 'age_gt':
                    age = calculate_age(val)
                    try: match = age is not None and age > int(target)
                    except: match = False
                elif op == 'age_lt':
                    age = calculate_age(val)
                    try: match = age is not None and age < int(target)
                    except: match = False
                elif op == 'min_length':
                    try: match = len(val) < int(target)
                    except: match = False
                elif op == 'max_length':
                    try: match = len(val) > int(target)
                    except: match = False
                
                if not match:
                    all_match = False
                    break
            
            if all_match:
                line = [row['CLIENT'], row['EXPL'], row['FILIALE'], row['AGENCE']]
                for f in unique_cond_fields:
                    line.append(str(row.get(f) or ''))
                ws.append(line)

    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = f'attachment; filename=anomalies_{rule.id}.xlsx'
    wb.save(response)
    return response


@login_required
def export_rules_pdf(request):
    # Récupérer les règles avec la même logique que la vue principale
    user_organe = getattr(request.user, 'organe', '')
    user_filiale = getattr(request.user, 'filiale', '')
    group_organs = ['PASS', 'Conformité Groupe', 'Contrôle Permanent Groupe']
    
    if user_organe == 'PASS':
        rules_qs = DataQualityRule.objects.all().order_by('-created_at')
    elif user_organe in ['Conformité Groupe', 'Contrôle Permanent Groupe']:
        rules_qs = DataQualityRule.objects.all().order_by('-created_at')
    else:
        # Filtrer par filiale
        rules_qs = DataQualityRule.objects.filter(
            Q(created_by__filiale=user_filiale) | Q(created_by__isnull=True)
        ).order_by('-created_at')

    # Évaluation avec CACHE pour la rapidité
    import hashlib
    from django.core.cache import cache
    
    rules_with_stats = []
    eval_filiale = None if user_organe in group_organs else user_filiale
    rules_version = cache.get('quality_control_rules_version', 1)
    cache_ttl = 86400
    data_refresh_bucket = timezone.localdate().isoformat()

    for rule in rules_qs:
        # Signature identique à la vue principale pour réutiliser le cache
        rule_signature = f"{rule.id}|{rule.name}|{rule.applicability}|{rule.field_name}|{rule.control_type}|{rule.parameter}|{rule.active}|{eval_filiale}"
        rule_hash = hashlib.md5(rule_signature.encode('utf-8')).hexdigest()
        rule_cache_key = f"quality_control:stat:v{rules_version}:d{data_refresh_bucket}:{rule_hash}"
        
        stat = cache.get(rule_cache_key)
        if stat is None:
            stat = evaluate_data_quality_rule(rule, filiale=eval_filiale)
            cache.set(rule_cache_key, stat, timeout=cache_ttl)
            
        # Calcul du taux
        total = stat.get('total', 0)
        stat['compliance_rate'] = compliance_rate_floor(stat['ok_count'], total, stat.get('fail_count', 0)) if total else 0
        
        rules_with_stats.append({
            'rule': rule,
            'stat': stat
        })

    template_path = 'quality_rules_pdf.html'
    logo_path = os.path.join(settings.MEDIA_ROOT, "images", "boa.png")
    context = {
        'rules': rules_with_stats,
        'user': request.user,
        'date': timezone.now(),
        'filiale': user_filiale if user_organe not in group_organs else "GROUPE",
        'logo_path': logo_path if os.path.exists(logo_path) else None,
    }
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="regles_qualite_kyc.pdf"'
    
    template = get_template(template_path)
    html = template.render(context)
    
    if not pisa:
        return HttpResponse("L'exportation PDF n'est pas disponible sur ce serveur (dépendances manquantes).")
        
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=_pdf_link_callback)
    if pisa_status.err:
        return HttpResponse('Erreur lors de la génération du PDF')
        
    return response


@login_required
def accueil(request):
    user = request.user

    if user.is_authenticated:
        if user.organe == "Chargé Client":
            return redirect('non_rens')
        else:
            return redirect('agent')
    if not user.is_authenticated:
        return redirect('login_kyc')

    return render(request, 'accueil.html')


@login_required
def import_page(request):
    if not request.user.is_superuser:
        return redirect('accueil')
    log_dir = os.path.join(settings.BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    history_path = os.path.join(log_dir, "import_history.log")
    run_dir = os.path.join(log_dir, "import_runs")
    os.makedirs(run_dir, exist_ok=True)

    def read_history(limit=50):
        if not os.path.exists(history_path):
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            return [ln.rstrip("\n") for ln in lines[-limit:]]
        except Exception:
            return []

    def list_run_logs(limit=20):
        try:
            files = [f for f in os.listdir(run_dir) if f.endswith(".log")]
            files.sort(reverse=True)
            return files[:limit]
        except Exception:
            return []

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        data_dir = (request.POST.get("data_dir") or "").strip()
        filiales = (request.POST.get("filiales") or "").strip()
        only = (request.POST.get("only") or "").strip()
        bulk_size = (request.POST.get("bulk_size") or "").strip()
        taux_clear = request.POST.get("taux_clear") == "on"

        script = None
        if action == "run_kyc":
            script = "import_kyc.py"
        elif action == "run_premier":
            script = "import_premier.py"

        if not script:
            messages.error(request, "Action d'import inconnue.")
        else:
            env = os.environ.copy()
            if data_dir:
                env["KYC_DATA_DIR"] = data_dir
            if filiales:
                env["KYC_FILIALES"] = filiales
            if bulk_size:
                env["KYC_BULK_SIZE"] = bulk_size
            if only:
                env["KYC_ONLY"] = only
            if taux_clear:
                env["KYC_TAUX_CLEAR"] = "1"
            elif "KYC_TAUX_CLEAR" in env:
                env.pop("KYC_TAUX_CLEAR", None)

            cmd = [sys.executable, str(settings.BASE_DIR / script)]
            start_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            detail_path = os.path.join(run_dir, f"{action}_{run_id}.log")
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(settings.BASE_DIR),
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                status = "SUCCESS" if result.returncode == 0 else "FAILED"
                with open(detail_path, "w", encoding="utf-8") as df:
                    df.write(f"CMD: {cmd}\n")
                    df.write(f"START: {start_ts}\n")
                    df.write(f"RETURN: {result.returncode}\n")
                    df.write(f"DATA_DIR: {data_dir}\n")
                    df.write(f"FILIALES: {filiales}\n")
                    df.write(f"ONLY: {only}\n")
                    df.write(f"BULK_SIZE: {bulk_size}\n")
                    df.write(f"TAUX_CLEAR: {taux_clear}\n")
                    df.write("\n--- STDOUT ---\n")
                    df.write(result.stdout or "")
                    df.write("\n--- STDERR ---\n")
                    df.write(result.stderr or "")

                with open(history_path, "a", encoding="utf-8") as hf:
                    hf.write(f"{start_ts} | {action} | {status} | log={detail_path}\n")

                if status == "SUCCESS":
                    # Invalider le cache des règles de qualité après un import réussi
                    current_v = cache.get('quality_control_rules_version', 1)
                    cache.set('quality_control_rules_version', current_v + 1, timeout=None)
                    messages.success(request, "Import terminé avec succès.")
                else:
                    messages.error(request, f"Import échoué (code {result.returncode}).")

            except Exception as e:
                messages.error(request, f"Erreur d'exécution: {e}")

    context = {
        "history": read_history(),
        "run_logs": list_run_logs(),
        "history_log_name": "import_history.log",
    }
    return render(request, 'import.html', context)


DOCUMENT_EXTRACTION_FIELD_LABELS = [
    ("prenom", "Prenom"),
    ("nom", "Nom"),
    ("date_naissance", "Date de naissance"),
    ("lieu_naissance", "Lieu de naissance"),
    ("sexe", "Sexe"),
    ("pays_naissance", "Pays de naissance"),
    ("pays_delivrance", "Pays de delivrance"),
    ("date_expiration", "Date d'expiration"),
    ("adresse", "Adresse"),
    ("origine_revenu", "Origine du revenu"),
    ("numero_identification_nationale", "Numero identification nationale"),
    ("numero_document", "Numero document"),
    ("nationalite", "Nationalite"),
]

DOCUMENT_EXTRACTION_SEARCH_FIELDS = [
    ("all", "Tous les champs"),
    ("import_batch", "Lot d'import"),
    ("original_filename", "Nom du fichier"),
    ("source_filename", "Fichier source"),
    *DOCUMENT_EXTRACTION_FIELD_LABELS,
    ("extracted_text", "Texte extrait"),
]

KYC_PP_DOCUMENT_FIELD_MAP = [
    ("NUMID", "numero_identification_nationale", "NIN"),
    ("NUMID", "numero_document", "Numero document"),
    ("DATNAIS", "date_naissance", "Date de naissance"),
    ("PAYNAIS", "pays_naissance", "Pays de naissance"),
    ("DATVALID", "date_expiration", "Date d'expiration"),
    ("ADRESSE", "adresse", "Adresse"),
    ("ORIGINE_REV", "origine_revenu", "Origine du revenu"),
]


def _normalize_match_value(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


COUNTRY_ALIASES = {
    "SENEGAL": {"SENEGAL", "SEN", "SN", "BOASN"},
    "BENIN": {"BENIN", "BEN", "BJ", "BOABJ"},
    "COTE D IVOIRE": {"COTEDIVOIRE", "CIV", "CI", "IVOIRE", "BOACI"},
    "BURKINA FASO": {"BURKINAFASO", "BFA", "BF", "BOABF"},
    "MALI": {"MALI", "MLI", "ML", "BOAML"},
    "TOGO": {"TOGO", "TGO", "TG", "BOATG"},
    "NIGER": {"NIGER", "NER", "NE", "BOANE"},
}


def _country_key(value):
    normalized = _normalize_match_value(value)
    if not normalized:
        return ""
    for country, aliases in COUNTRY_ALIASES.items():
        if normalized in aliases or any(alias and alias in normalized for alias in aliases):
            return country
    return normalized


def _countries_are_compatible(left, right):
    left_key = _country_key(left)
    right_key = _country_key(right)
    return not left_key or not right_key or left_key == right_key


def _document_country_guard_passes(document, client):
    if document.pays_naissance and getattr(client, "PAYNAIS", "") and not _countries_are_compatible(document.pays_naissance, client.PAYNAIS):
        return False
    return True


def _is_empty_kyc_value(value):
    normalized = str(value or "").strip().lower()
    return normalized in {"", "-", "na", "n/a", "none", "null", "nan"}


def _document_identity_keys(document):
    return {
        key for key in [
            _normalize_match_value(document.numero_document),
            _normalize_match_value(document.numero_identification_nationale),
        ] if key
    }


def _document_client_haystack(document):
    return _normalize_match_value(
        " ".join([
            document.original_filename or "",
            document.source_filename or "",
            document.import_batch or "",
        ])
    )


def _document_client_tokens(document):
    raw_value = " ".join([
        document.original_filename or "",
        document.source_filename or "",
        document.import_batch or "",
    ]).upper()
    return {_normalize_match_value(token) for token in re.split(r"[^A-Z0-9]+", raw_value) if len(token) >= 4}


def _document_unique_key(document):
    identity_keys = sorted(_document_identity_keys(document))
    if identity_keys:
        country_parts = [
            _country_key(document.pays_delivrance),
            _country_key(document.pays_naissance),
        ]
        country_scope = "|".join([part for part in country_parts if part])
        if country_scope:
            return "identity:" + country_scope + ":" + "|".join(identity_keys)
        return "identity:" + "|".join(identity_keys)
    return "file:" + _normalize_match_value(
        "|".join([
            document.original_filename or "",
            document.source_filename or "",
            document.import_batch or "",
            document.page_range or "",
        ])
    )


def _client_dedup_key(client):
    normalized_idp = _normalize_match_value(getattr(client, "IDP", ""))
    if normalized_idp:
        return f"idp:{normalized_idp}"
    normalized_client = _normalize_match_value(getattr(client, "CLIENT", ""))
    if normalized_client:
        return f"client:{normalized_client}"
    return f"pk:{client.pk}"


def _build_kyc_pp_document_matches(document_queryset, limit=3000, result_limit=200):
    documents_for_match = list(document_queryset.order_by("-created_at")[:limit])
    if not documents_for_match:
        return [], {"documents_checked": 0, "documents_matched": 0, "clients_matched": 0, "suggestions_count": 0, "match_rate": 0}

    document_keys = set()
    for document in documents_for_match:
        document_keys.update(_document_identity_keys(document))

    kyc_candidates = {}
    if document_keys:
        for client in Kyc_pp.objects.exclude(NUMID="").only(
            "id", "FILIALE", "AGENCE", "CLIENT", "IDP", "NUMID", "DATNAIS", "PAYNAIS", "DATVALID", "ADRESSE", "ORIGINE_REV"
        ):
            normalized_numid = _normalize_match_value(client.NUMID)
            if normalized_numid in document_keys:
                kyc_candidates.setdefault(normalized_numid, []).append(client)

    client_by_code = {}
    for client in Kyc_pp.objects.only(
        "id", "FILIALE", "AGENCE", "CLIENT", "IDP", "NUMID", "DATNAIS", "PAYNAIS", "DATVALID", "ADRESSE", "ORIGINE_REV"
    )[:50000]:
        normalized_client = _normalize_match_value(client.CLIENT)
        if normalized_client:
            client_by_code.setdefault(normalized_client, []).append(client)

    matches = []
    client_match_index = {}
    matched_client_ids = set()
    matched_document_ids = set()
    for document in documents_for_match:
        candidate_clients = []
        for identity_key in _document_identity_keys(document):
            candidate_clients.extend(kyc_candidates.get(identity_key, []))

        for client_token in _document_client_tokens(document):
            candidate_clients.extend(client_by_code.get(client_token, []))

        unique_clients = {}
        for client in candidate_clients:
            if not _document_country_guard_passes(document, client):
                continue
            unique_clients[client.pk] = client

        for client in unique_clients.values():
            suggestions = []
            used_kyc_fields = set()
            empty_comparable_fields = {
                kyc_field for kyc_field, _, _ in KYC_PP_DOCUMENT_FIELD_MAP
                if _is_empty_kyc_value(getattr(client, kyc_field, ""))
            }
            for kyc_field, document_field, label in KYC_PP_DOCUMENT_FIELD_MAP:
                document_value = getattr(document, document_field, "")
                if not document_value or not _is_empty_kyc_value(getattr(client, kyc_field, "")):
                    continue
                if kyc_field in used_kyc_fields:
                    continue
                used_kyc_fields.add(kyc_field)
                suggestions.append({
                    "field": kyc_field,
                    "label": label,
                    "document_value": document_value,
                })

            if suggestions:
                match_rate = 0
                if empty_comparable_fields:
                    match_rate = round((len({suggestion["field"] for suggestion in suggestions}) / len(empty_comparable_fields)) * 100, 1)
                client_dedup_key = _client_dedup_key(client)
                if client_dedup_key in client_match_index:
                    existing_match = matches[client_match_index[client_dedup_key]]
                    if _document_unique_key(existing_match["document"]) != _document_unique_key(document):
                        continue
                    existing_fields = {suggestion["field"] for suggestion in existing_match["suggestions"]}
                    for suggestion in suggestions:
                        if suggestion["field"] not in existing_fields:
                            existing_match["suggestions"].append(suggestion)
                            existing_fields.add(suggestion["field"])
                    existing_match["match_rate"] = max(existing_match["match_rate"], match_rate)
                    continue

                matched_client_ids.add(client.pk)
                matched_document_ids.add(document.pk)
                client_match_index[client_dedup_key] = len(matches)
                matches.append({
                    "client": client,
                    "document": document,
                    "suggestions": suggestions,
                    "match_rate": match_rate,
                })

    suggestions_count = sum(len(match["suggestions"]) for match in matches)
    match_rate = round((len(matched_document_ids) / len(documents_for_match)) * 100, 1)

    summary = {
        "documents_checked": len(documents_for_match),
        "documents_matched": len(matched_document_ids),
        "clients_matched": len(client_match_index),
        "suggestions_count": suggestions_count,
        "match_rate": match_rate,
    }
    if result_limit:
        return matches[:result_limit], summary
    return matches, summary


LAST_KYC_PP_MATCH_SESSION_KEY = "document_extraction_last_kyc_pp_match_params"


def _filtered_document_extractions_from_params(params):
    documents = KycDocumentExtraction.objects.select_related("uploaded_by").all()
    valid_document_types = dict(DOCUMENT_EXTRACTION_TYPE_CHOICES)
    selected_document_type = params.get("document_type", "")
    selected_import_batch = (params.get("import_batch") or "").strip()
    search_query = (params.get("q") or "").strip()
    search_field = params.get("field") or "all"
    allowed_search_fields = {field for field, _ in DOCUMENT_EXTRACTION_SEARCH_FIELDS}

    if selected_document_type in valid_document_types:
        documents = documents.filter(document_type=selected_document_type)

    if selected_import_batch:
        documents = documents.filter(import_batch=selected_import_batch)

    if search_field not in allowed_search_fields:
        search_field = "all"

    if search_query:
        if search_field == "all":
            search_filter = Q()
            for field_name, _ in DOCUMENT_EXTRACTION_SEARCH_FIELDS:
                if field_name == "all":
                    continue
                search_filter |= Q(**{f"{field_name}__icontains": search_query})
            documents = documents.filter(search_filter)
        else:
            documents = documents.filter(**{f"{search_field}__icontains": search_query})

    return documents


def _filtered_document_extractions_from_request(request):
    return _filtered_document_extractions_from_params(request.GET)


def _clean_document_match_params(params):
    return {
        key: value
        for key, value in params.items()
        if key not in {"page", "extraction_id", "match_kyc"} and value not in (None, "")
    }


@login_required
def export_document_extraction_matches(request):
    documents = _filtered_document_extractions_from_request(request)
    matches, summary = _build_kyc_pp_document_matches(documents, result_limit=None)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    filename = timezone.localtime(timezone.now()).strftime("correspondances_kyc_pp_%Y%m%d_%H%M.csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "Client",
        "IDP",
        "Agence",
        "Type de document",
        "Champ KYC",
        "Valeur",
        "Numero document",
        "Numero d'identification nationale",
    ])

    for match in matches:
        document = match["document"]
        client = match["client"]
        for suggestion in match["suggestions"]:
            writer.writerow([
                client.CLIENT,
                client.IDP,
                client.AGENCE,
                document.get_document_type_display(),
                suggestion["field"],
                suggestion["document_value"],
                document.numero_document,
                document.numero_identification_nationale,
            ])
    return response


def _build_import_batch_name(request, uploaded_files):
    requested_name = (request.POST.get("batch_name") or "").strip()
    if requested_name:
        return requested_name[:120]

    first_file = uploaded_files[0].name if uploaded_files else "documents"
    timestamp = timezone.localtime(timezone.now()).strftime("%Y%m%d-%H%M%S")
    return f"LOT-{timestamp}-{os.path.splitext(os.path.basename(first_file))[0]}"[:120]


def _format_document_extraction_record(record):
    fields = {
        field_name: getattr(record, field_name, "")
        for field_name, _ in DOCUMENT_EXTRACTION_FIELD_LABELS
    }
    return {
        "id": record.pk,
        "filename": record.original_filename or os.path.basename(record.uploaded_file.name),
        "source_filename": record.source_filename,
        "file_url": record.uploaded_file.url if record.uploaded_file else "",
        "document_type": record.get_document_type_display(),
        "import_batch": record.import_batch,
        "page_number": record.page_number,
        "page_range": record.page_range,
        "text": record.extracted_text,
        "fields": fields,
        "warnings": [warning for warning in record.extraction_warnings.splitlines() if warning],
        "field_rows": [
            {"label": label, "value": fields.get(field_name)}
            for field_name, label in DOCUMENT_EXTRACTION_FIELD_LABELS
            if fields.get(field_name)
        ],
    }


def _fill_document_extraction_fields(record, extraction):
    extracted_fields = extraction.get("fields") or {}
    for field_name, _ in DOCUMENT_EXTRACTION_FIELD_LABELS:
        setattr(record, field_name, extracted_fields.get(field_name, ""))
    record.extracted_text = extraction.get("text") or ""
    record.extraction_warnings = "\n".join(extraction.get("warnings") or [])
    record.page_number = extraction.get("page_number") or record.page_number
    record.page_range = extraction.get("page_range") or record.page_range


def _save_uploaded_document_record(uploaded_file, document_type, user, import_batch="", source_filename=""):
    record = KycDocumentExtraction(
        document_type=document_type,
        original_filename=os.path.basename(uploaded_file.name),
        source_filename=source_filename or os.path.basename(uploaded_file.name),
        import_batch=import_batch,
        uploaded_by=user,
    )
    record.uploaded_file.save(uploaded_file.name, uploaded_file, save=False)
    extraction = extract_document_data(record.uploaded_file.path, uploaded_file.name)
    _fill_document_extraction_fields(record, extraction)
    record.save()
    return record, extraction


def _save_zip_document_record(zip_file, member_name, document_type, user, import_batch, archive_name):
    safe_name = os.path.basename(member_name)
    _, extension = os.path.splitext(safe_name)
    if extension.lower() not in SUPPORTED_EXTENSIONS:
        return None, f"Format ignore dans le ZIP: {member_name}"

    with zip_file.open(member_name) as member:
        content = ContentFile(member.read(), name=safe_name)

    record = KycDocumentExtraction(
        document_type=document_type,
        original_filename=safe_name,
        source_filename=os.path.basename(archive_name or "archive.zip"),
        import_batch=import_batch,
        uploaded_by=user,
    )
    record.uploaded_file.save(safe_name, content, save=False)
    extraction = extract_document_data(record.uploaded_file.path, safe_name)
    _fill_document_extraction_fields(record, extraction)
    record.save()
    return record, None


def _save_grouped_pdf_records(uploaded_file, document_type, user, import_batch, pages_per_document):
    if os.path.splitext(uploaded_file.name)[1].lower() != ".pdf":
        raise ValueError("Le mode document groupe accepte uniquement un fichier PDF.")

    shared_file_name = f"grouped_{uuid.uuid4().hex}_{os.path.basename(uploaded_file.name)}"
    base_record = KycDocumentExtraction(
        document_type=document_type,
        original_filename=os.path.basename(uploaded_file.name),
        source_filename=os.path.basename(uploaded_file.name),
        import_batch=import_batch,
        uploaded_by=user,
    )
    base_record.uploaded_file.save(shared_file_name, uploaded_file, save=False)

    grouped_extractions = extract_pdf_grouped_documents(
        base_record.uploaded_file.path,
        uploaded_file.name,
        pages_per_document=pages_per_document,
    )

    records = []
    for extraction in grouped_extractions:
        record = KycDocumentExtraction(
            document_type=document_type,
            uploaded_file=base_record.uploaded_file.name,
            original_filename=os.path.basename(uploaded_file.name),
            source_filename=os.path.basename(uploaded_file.name),
            import_batch=import_batch,
            uploaded_by=user,
        )
        _fill_document_extraction_fields(record, extraction)
        record.save()
        records.append(record)
    return records


@login_required
def document_extraction(request):
    extraction = None
    valid_document_types = dict(DOCUMENT_EXTRACTION_TYPE_CHOICES)

    if request.method == "POST":
        uploaded_files = request.FILES.getlist("documents")
        if not uploaded_files and request.FILES.get("document"):
            uploaded_files = [request.FILES.get("document")]
        document_type = request.POST.get("document_type") or "piece_identite"
        import_mode = request.POST.get("import_mode") or "single"
        try:
            pages_per_document = max(int(request.POST.get("pages_per_document") or 1), 1)
        except ValueError:
            pages_per_document = 1

        if document_type not in valid_document_types:
            messages.error(request, "Veuillez choisir un type de document valide.")
            return redirect("document_extraction")

        if not uploaded_files:
            messages.error(request, "Veuillez selectionner au moins un document a analyser.")
        else:
            import_batch = _build_import_batch_name(request, uploaded_files)
            created_records = []
            errors = []

            if import_mode == "grouped_pdf":
                try:
                    created_records.extend(_save_grouped_pdf_records(
                        uploaded_files[0],
                        document_type,
                        request.user,
                        import_batch,
                        pages_per_document,
                    ))
                except Exception as exc:
                    errors.append(str(exc))
            else:
                for uploaded_file in uploaded_files:
                    extension = os.path.splitext(uploaded_file.name)[1].lower()
                    if extension == ".zip":
                        try:
                            with zipfile.ZipFile(uploaded_file) as archive:
                                for member_name in archive.namelist():
                                    if member_name.endswith("/"):
                                        continue
                                    record, error = _save_zip_document_record(
                                        archive,
                                        member_name,
                                        document_type,
                                        request.user,
                                        import_batch,
                                        uploaded_file.name,
                                    )
                                    if record:
                                        created_records.append(record)
                                    if error:
                                        errors.append(error)
                        except zipfile.BadZipFile:
                            errors.append(f"Archive ZIP invalide: {uploaded_file.name}")
                    else:
                        try:
                            record, _ = _save_uploaded_document_record(
                                uploaded_file,
                                document_type,
                                request.user,
                                import_batch=import_batch,
                            )
                            created_records.append(record)
                        except Exception as exc:
                            errors.append(f"{uploaded_file.name}: {exc}")

            if created_records:
                messages.success(
                    request,
                    f"{len(created_records)} document(s) charge(s), analyse(s) et enregistre(s) dans le lot {import_batch}.",
                )
            if errors:
                messages.warning(request, f"{len(errors)} element(s) non importe(s): " + " | ".join(errors[:5]))
            if created_records:
                return redirect(f"{reverse('document_extraction')}?{urlencode({'uploaded_batch': import_batch})}#charger")

    documents = _filtered_document_extractions_from_request(request)
    selected_document_type = request.GET.get("document_type", "")
    selected_import_batch = (request.GET.get("import_batch") or "").strip()
    uploaded_batch = (request.GET.get("uploaded_batch") or "").strip()
    search_query = (request.GET.get("q") or "").strip()
    search_field = request.GET.get("field") or "all"
    if selected_document_type not in valid_document_types:
        selected_document_type = ""
    if search_field not in {field for field, _ in DOCUMENT_EXTRACTION_SEARCH_FIELDS}:
        search_field = "all"

    selected_extraction_id = request.GET.get("extraction_id")
    if selected_extraction_id and selected_extraction_id.isdigit():
        selected_record = get_object_or_404(KycDocumentExtraction, pk=selected_extraction_id)
        extraction = _format_document_extraction_record(selected_record)

    uploaded_documents = KycDocumentExtraction.objects.none()
    if uploaded_batch:
        uploaded_documents = KycDocumentExtraction.objects.filter(import_batch=uploaded_batch).order_by("-created_at")[:50]

    requested_kyc_pp_matching = request.GET.get("match_kyc") == "1"
    has_last_match_params = LAST_KYC_PP_MATCH_SESSION_KEY in request.session
    last_match_params = request.session.get(LAST_KYC_PP_MATCH_SESSION_KEY) or {}
    active_match_params = None
    if requested_kyc_pp_matching:
        active_match_params = _clean_document_match_params(request.GET)
        request.session[LAST_KYC_PP_MATCH_SESSION_KEY] = active_match_params
        request.session.modified = True
    elif has_last_match_params:
        active_match_params = last_match_params

    run_kyc_pp_matching = active_match_params is not None
    kyc_pp_matches = []
    kyc_pp_match_summary = {
        "documents_checked": 0,
        "documents_matched": 0,
        "clients_matched": 0,
        "suggestions_count": 0,
        "match_rate": 0,
    }
    if run_kyc_pp_matching:
        match_documents = _filtered_document_extractions_from_params(active_match_params)
        kyc_pp_matches, kyc_pp_match_summary = _build_kyc_pp_document_matches(match_documents)

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_params.pop("extraction_id", None)
    query_params.pop("match_kyc", None)

    match_query_params = request.GET.copy()
    match_query_params["match_kyc"] = "1"
    match_query_params.pop("page", None)
    match_query_params.pop("extraction_id", None)

    if active_match_params is not None:
        export_match_querystring = urlencode(active_match_params)
    else:
        export_match_querystring = urlencode(_clean_document_match_params(request.GET))

    context = {
        "extraction": extraction,
        "documents": page_obj,
        "documents_count": documents.count(),
        "uploaded_batch": uploaded_batch,
        "uploaded_documents": uploaded_documents,
        "kyc_pp_matches": kyc_pp_matches,
        "kyc_pp_match_summary": kyc_pp_match_summary,
        "run_kyc_pp_matching": run_kyc_pp_matching,
        "match_querystring": match_query_params.urlencode(),
        "export_match_querystring": export_match_querystring,
        "document_type_choices": DOCUMENT_EXTRACTION_TYPE_CHOICES,
        "selected_document_type": selected_document_type,
        "selected_import_batch": selected_import_batch,
        "search_fields": DOCUMENT_EXTRACTION_SEARCH_FIELDS,
        "search_field": search_field,
        "search_query": search_query,
        "field_labels": DOCUMENT_EXTRACTION_FIELD_LABELS,
        "page_querystring": query_params.urlencode(),
    }
    return render(request, 'document_extraction.html', context)


@login_required
def import_log_download(request, filename):
    if not request.user.is_superuser:
        return redirect('accueil')
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        raise Http404("Invalid file")

    log_dir = os.path.join(settings.BASE_DIR, "logs")
    run_dir = os.path.join(log_dir, "import_runs")
    allowed_paths = [
        os.path.join(run_dir, filename),
        os.path.join(log_dir, filename),
    ]
    file_path = next((p for p in allowed_paths if os.path.isfile(p)), None)
    if not file_path:
        raise Http404("File not found")

    return FileResponse(open(file_path, "rb"), as_attachment=True, filename=filename)


def profile_update(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect("profile")  # redirige après update
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "profile_update.html", {"form": form})


@csrf_exempt
def rechercher_et_noter_agent(request):
    agent = None
    form = None
    message = None

    if request.method == "POST":
        expl = request.POST.get('expl', '')
        if expl:
            try:
                agent = ProfileV.objects.get(code_expl=expl)
            except ProfileV.DoesNotExist:
                message = "Agent introuvable."

            if agent:
                # Si l'utilisateur a le profil "Contrôle permanent"
                if request.user.is_authenticated and request.user.groups.filter(name='Contrôle permanent').exists():
                    form = NoteForm(request.POST or None)
                    if form.is_valid():
                        note = form.save(commit=False)
                        note.agent = agent
                        note.date_notation = timezone.now()  # Enregistrer la date de notation
                        note.save()
                        message = "Notation enregistrée avec succès."
                        form = None  # Reset le formulaire après enregistrement pour éviter la soumission répétée
                else:
                    message = "Vous n'avez pas la permission de noter cet agent."

    return render(request, 'accueil.html', {'agent': agent, 'form': form, 'message': message})


@csrf_exempt
def password_reset_request(request):
    if request.method == "POST":
        password_reset_form = PasswordResetForm(request.POST)
        if password_reset_form.is_valid():
            data = password_reset_form.cleaned_data['email']
            associated_users = ProfileV.objects.filter(Q(username=data))
            if associated_users.exists():
                for user in associated_users:
                    subject = "Password Reset Requested"
                    email_template_name = "password_reset_email.txt"
                    c = {
                        "email": user.username,
                        'domain': '127.0.0.1:8000',
                        'site_name': '',
                        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                        'token': default_token_generator.make_token(user),
                        'protocol': 'http',
                    }
                    email = render_to_string(email_template_name, c)
                    try:
                        send_mail(subject, email, 'mamadou@mamadou.sn', [user.username], fail_silently=False)
                    except BadHeaderError:
                        return HttpResponse('Invalid header found.')
                    return redirect('/password_resete/done')

                    messages.success(request, 'A message with reset password instructions has been sent to your inbox.')
                    return redirect("accueil")
            else:
                errors = 'Votre mail ne figure pas dans notre base.'
                return render(request=request, template_name="password_reset.html",
                              context={"password_reset_form": password_reset_form, "errors": errors})

    password_reset_form = PasswordResetForm()
    return render(request=request, template_name="password_reset.html",
                  context={"password_reset_form": password_reset_form})


@login_required
@csrf_exempt
def profil(request):
    roles_exclus = ["Chargé Client"]
    notes = Notation.objects.filter(flux_stock='Flux')
    user = request.user
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la dernière note par agent
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)

    context = {'roles_exclus': roles_exclus,
               'notation': notation,
               }
    return render(request, 'profil.html', context)


@csrf_exempt
def profile(request):
    if request.method == 'POST':
        user_form = ProfileModify(request.POST, instance=request.user)
        if user_form.is_valid():
            user_form.save()
            messages.success(request, 'Votre profil a été modifié avec succès')
            return redirect('/perso/profil')

    else:
        user_form = ProfileModify(instance=request.user)
    return render(request, 'modify_profil.html', {'user_form': user_form})


@method_decorator(csrf_exempt, name='dispatch')
class ChangePasswordView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'modify_pw.html'
    success_message = "Votre mot de passe a été changé avec succès"
    success_url = reverse_lazy('profil')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ajout du contexte personnalisé
        context['roles_exclus'] = ["Chargé Client"]
        return context


@csrf_exempt
def reset_user_password_b(request, user_id):
    roles_exclus = ["Chargé Client"]
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            # Enregistrer le nouveau mot de passe en le hachant
            new_password = form.cleaned_data['new_password']
            user.password = make_password(new_password)
            user.save()
            return redirect('profil')  # Rediriger vers la liste des utilisateurs après modification
    else:
        form = ResetPasswordForm()

    return render(request, 'modify_pw.html', {'form': form, 'user': user, 'roles_exclus': roles_exclus})


@login_required
def perso(request):
    # Récupérer l'utilisateur connecté
    roles_exclus = ["Chargé Client"]
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        agents = ProfileV.objects.filter(filiale=user.filiale)
    else:
        agents = ProfileV.objects.all()
    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        agents = agents.filter(code_expl__icontains=query)

    return render(request, 'mon_profile.html', {'agents': agents, 'query': query, 'roles_exclus': roles_exclus})


@login_required
@csrf_exempt
def agent(request):
    roles_exclus = ["Chargé Client"]
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Flux')
    elif user.organe in ['Directeur Agence']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Flux')
    else:
        notes = Notation.objects.filter(flux_stock='Flux')

    # Annoter chaque agent avec la dernière date de notation
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la dernière note par agent
    notes = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    notes = notes.order_by('-date_notation')
    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        agents = ProfileV.objects.filter(code_expl__icontains=query)  # Utilisation de icontains pour une recherche partielle
        if agents.exists():
            notes = notes.all().filter(agent__in=agents)
        else:
            # Si aucun agent n'est trouvé, vider le queryset pour ne rien afficher
            notes = notes.none()

    return render(request, 'agent.html', {
        'notes': notes,
        'query': query,
        'roles_exclus': roles_exclus,
    })


def export_agents_excel(request):
    def strip_tz(value):
        if hasattr(value, 'tzinfo'):
            return value.replace(tzinfo=None)
        return value

    user = request.user

    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Flux')
    elif user.organe in ['Directeur Agence']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Flux')
    else:
        donnees = Notation.objects.filter(flux_stock='Flux')

    latest_notes = donnees.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la dernière note par agent
    donnees = donnees.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    donnees = donnees.order_by('-date_notation')

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Flux"

    # Entêtes
    headers = ["FILIALE", "EXPLOITANT", "NOM", "AGENCE", "EMAIL", "NOTE", "Dernière notation", "Noté par le contrôleur",
               "Flux/Stock"]
    ws.append(headers)

    # Données
    for d in donnees:
        agent_nom = f"{d.agent.first_name} {d.agent.last_name}".strip()
        agent_email = d.agent.email or d.agent.username
        ws.append([
            d.note_par.filiale, d.agent.code_expl, agent_nom, d.agent.agence, agent_email, d.note,
            strip_tz(d.date_notation), d.note_par.email, d.flux_stock

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Notation_Flux_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_agents_excel_s(request):
    def strip_tz(value):
        if hasattr(value, 'tzinfo'):
            return value.replace(tzinfo=None)
        return value

    user = request.user

    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Stock')
    elif user.organe in ['Directeur Agence']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Stock')
    else:
        donnees = Notation.objects.filter(flux_stock='Stock')

    latest_notes = donnees.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la dernière note par agent
    donnees = donnees.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    donnees = donnees.order_by('-date_notation')

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # Entêtes
    headers = ["FILIALE", "EXPLOITANT", "NOM", "AGENCE", "EMAIL", "NOTE", "Dernière notation", "Noté par le contrôleur",
               "Flux/Stock"]
    ws.append(headers)

    # Données
    for d in donnees:
        agent_nom = f"{d.agent.first_name} {d.agent.last_name}".strip()
        agent_email = d.agent.email or d.agent.username
        ws.append([
            d.note_par.filiale, d.agent.code_expl, agent_nom, d.agent.agence, agent_email, d.note,
            strip_tz(d.date_notation), d.note_par.email, d.flux_stock

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Notation_Stock_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
def perso_stock(request):
    # Récupérer l'utilisateur connecté
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        notes = Notation.objects.filter(filiale=user.filiale, flux_stock='Stock')
    else:
        notes = Notation.objects.all().filter(flux_stock='Flux')
    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        notes = notes.filter(agent__code_expl__icontains=query)

    return render(request, 'agent_stock.html', {'notes': notes, 'query': query})


@login_required
@csrf_exempt
def agent_stock(request):
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Risques', 'DAI', 'Qualité','DSI']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Stock')
    else:
        notes = Notation.objects.filter(flux_stock='Stock')

    # Annoter chaque agent avec la dernière date de notation
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notes = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    # Filtrer pour obtenir uniquement la dernière note par agent
    notes = notes.order_by('-date_notation')

    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        agents = ProfileV.objects.filter(code_expl__icontains=query)  # Utilisation de icontains pour une recherche partielle
        if agents.exists():
            notes = notes.filter(agent__in=agents)
        else:
            # Si aucun agent n'est trouvé, vider le queryset pour ne rien afficher
            notes = notes.none()

    return render(request, 'agent_stock.html', {'notes': notes, 'query': query})


@csrf_exempt
def notes(request):
    agent = None
    roles_exclus = ["Chargé Client", "Directeur Agence"]
    form = NotationForm()  # Initialisation du formulaire

    if request.method == 'POST':
        if 'search_agent' in request.POST:
            # Rechercher l'agent par son code exploitant
            code_exploitant = request.POST.get('code_exploitant')
            try:
                agent = ProfileV.objects.get(code_expl=code_exploitant, filiale=request.user.filiale)

                # Préremplir le formulaire avec l'agent trouvé
                form = NotationForm(initial={'agent': agent})
            except ProfileV.DoesNotExist:
                agent = None
                error_message = "L'agent avec ce code exploitant n'existe pas."
                return render(request, 'notation.html', {'form': form, 'error_message': error_message})

        else:
            # Soumission du formulaire de notation
            form = NotationForm(request.POST)
            if form.is_valid():
                user = request.user
                # Assigner l'agent à partir du formulaire
                notation = form.save(commit=False)
                notation.filiale = request.user.filiale
                notation.note_par = request.user
                notation.date_notation = timezone.now()
                notation.save()
                messages.success(request, 'La notation a bien été sauvegardée.')

                return redirect('agent')
    else:
        form = NotationForm()  # Afficher un formulaire vide si la requête n'est pas en POST

    return render(request, 'notation.html', {'form': form, 'agent': agent, 'roles_exclus': roles_exclus})


def agent_detail(request, agent_id):
    agent = get_object_or_404(ProfileV, id=agent_id)
    notations = agent.notations.all().order_by('-date_notation')
    return render(request, 'agent_detail.html', {'agent': agent, 'notations': notations})


@login_required
@csrf_exempt
def historique(request):
    roles_exclus = ["Chargé Client", "Directeur Agence"]
    query = request.GET.get('q')

    if query:
        # Filtre les notations en fonction du code exploitant
        notations = Notation.objects.filter(note_par=request.user, agent__code_expl__icontains=query).order_by(
            "-date_notation")
    else:
        # Récupère toutes les notations de l'utilisateur connecté
        notations = Notation.objects.filter(note_par=request.user).order_by("-date_notation")

    # Passe les notations au template
    context = {
        'notations': notations,
        'query': query,
    }  # Pour pré-remplir la barre de recherche
    return render(request, 'historique.html', {'notations': notations, 'roles_exclus': roles_exclus})


def test(request):
    return render(request, 'test.html')


@login_required
def register(request):
    roles_exclus = ["Chargé Client"]
    current_user = request.user

    # 🔒 Vérification des droits d'accès
    if current_user.organe not in ["PASS", "DSI"]:
        messages.error(request, "Vous n’avez pas la permission de créer un compte utilisateur.")
        return redirect('user_list')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)

            # Si l'utilisateur est DSI → forcer la filiale du nouveau compte
            if current_user.organe == "DSI":
                new_user.filiale = current_user.filiale

            new_user.save()
            messages.success(request, "Utilisateur créé avec succès.")
            return redirect('user_list')
    else:
        form = CustomUserCreationForm(current_user=current_user)  # 👈 On passe l’utilisateur connecté au formulaire

    return render(request, 'register.html', {'form': form, 'roles_exclus': roles_exclus})


# Fonction pour vérifier si l'utilisateur appartient à l'organe "PASS"
def is_pass_user(user):
    return user.organe == 'PASS'


# Limiter l'accès à ceux de l'organe 'PASS'


@login_required
def user_list(request):
    user = request.user
    query = request.GET.get('q', '')
    page_number = request.GET.get('page')

    # 1. Filtrage par droits organe
    if user.organe == "PASS":
        users_base = ProfileV.objects.all().order_by('last_name')
    elif user.organe == "DSI":
        users_base = ProfileV.objects.filter(filiale=user.filiale).order_by('last_name')
    else:
        users_base = ProfileV.objects.none()

    # 2. Recherche multi-critères
    if query:
        users_base = users_base.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query)
        )

    # 3. Récupération des connectés (Sessions actives)
    active_sessions = Session.objects.filter(expire_date__gte=now())
    user_ids = []
    for s in active_sessions:
        data = s.get_decoded()
        if '_auth_user_id' in data:
            user_ids.append(data['_auth_user_id'])

    connected_users = users_base.filter(id__in=list(set(user_ids)))

    # 4. Pagination (10 par page)
    paginator = Paginator(users_base, 10)
    page_obj = paginator.get_page(page_number)

    context = {
        'total_users': users_base.count(),
        'connected_count': connected_users.count(),
        'connected_users': connected_users,
        'page_obj': page_obj,
        'query': query,
    }
    return render(request, 'user_list.html', context)



@login_required
def edit_user(request, user_id):
    current_user = request.user
    target_user = get_object_or_404(ProfileV, pk=user_id)

    # 🔒 Règles d’accès
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request, "Vous ne pouvez modifier que les utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous n’avez pas la permission de modifier cet utilisateur.")
            return redirect('user_list')

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target_user, current_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Utilisateur modifié avec succès.")
            return redirect('user_list')
    else:
        form = UserEditForm(instance=target_user, current_user=request.user)

    return render(request, 'edit_user.html', {'form': form, 'user': target_user})


@login_required
def change_user_password(request, user_id):
    current_user = request.user
    target_user = get_object_or_404(ProfileV, pk=user_id)

    # 🔒 Règles d’accès :
    # - PASS : peut changer le mot de passe de tous les utilisateurs
    # - DSI : peut changer le mot de passe uniquement des utilisateurs de sa filiale
    # - Autres : accès refusé
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request, "Vous ne pouvez changer le mot de passe que des utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous n’avez pas la permission de changer ce mot de passe.")
            return redirect('user_list')

    # 🧾 Traitement du formulaire
    if request.method == 'POST':
        form = PasswordChangeForm(target_user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # éviter la déconnexion
            messages.success(request, "Le mot de passe a été modifié avec succès.")
            return redirect('user_list')
    else:
        form = PasswordChangeForm(target_user)

    return render(request, 'change_user_password.html', {'form': form, 'user': target_user})


@login_required
def reset_user_password(request, user_id):
    current_user = request.user
    target_user = get_object_or_404(ProfileV, pk=user_id)

    # 🔒 Règles d’accès :
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request,
                               "Vous ne pouvez réinitialiser que les mots de passe des utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous n’avez pas la permission de réinitialiser ce mot de passe.")
            return redirect('user_list')

    # 🧾 Traitement du formulaire
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            target_user.password = make_password(new_password)
            target_user.force_password_change = form.cleaned_data.get('force_password_change', False)
            target_user.save()
            messages.success(request, "Le mot de passe a été réinitialisé avec succès.")
            return redirect('user_list')
    else:
        form = ResetPasswordForm(initial={
            'force_password_change': target_user.force_password_change
        })

    return render(request, 'reset_user_password.html', {'form': form, 'target_user': target_user})


@login_required
def user_statistics_view(request):
    roles_exclus = ["Chargé Client"]
    current_user = request.user  # utilisateur connecté

    # 🔒 Règles d’accès selon l’organe
    if current_user.organe == "PASS":
        users = ProfileV.objects.all()

    elif current_user.organe == "DSI":
        users = ProfileV.objects.filter(filiale=current_user.filiale)

    else:
        messages.error(request, "Vous n’avez pas la permission d’accéder à cette page.")
        return render(request, 'user_statistics.html', {
            'total_users': 0,
            'connected_count': 0,
            'connected_users': [],
            'users': [],
            'roles_exclus': roles_exclus,
            'connection_history_labels': json.dumps([]),
            'connection_history_values': json.dumps([]),
            'connection_history_rows': [],
            'history_days': 0,
        })

    # Nombre total d'utilisateurs visibles
    total_users = users.count()

    # 🔄 Sessions actives
    active_sessions = Session.objects.filter(expire_date__gte=now())
    user_ids = []
    for session in active_sessions:
        data = session.get_decoded()
        if '_auth_user_id' in data:
            user_ids.append(data['_auth_user_id'])

    # Supprimer les doublons
    user_ids = list(set(user_ids))

    # 👥 Utilisateurs connectés visibles par le user connecté
    connected_users = users.filter(id__in=user_ids)
    connected_count = connected_users.count()

    visible_login_events = UserLoginHistory.objects.filter(user_id__in=users.values("id"))
    first_login_at = visible_login_events.order_by("login_at").values_list("login_at", flat=True).first()

    end_date = timezone.localdate()
    if first_login_at:
        if timezone.is_aware(first_login_at):
            start_date = timezone.localtime(first_login_at).date()
        else:
            start_date = first_login_at.date()
    else:
        start_date = end_date - timedelta(days=6)

    daily_connections = (
        visible_login_events
        .filter(login_at__date__range=(start_date, end_date))
        .annotate(day=TruncDate("login_at"))
        .values("day")
        .annotate(count=Count("user_id", distinct=True))
        .order_by("day")
    )
    daily_connections_map = {row["day"]: row["count"] for row in daily_connections}

    cursor = start_date
    chart_labels = []
    chart_values = []
    history_rows = []

    while cursor <= end_date:
        count = daily_connections_map.get(cursor, 0)
        chart_labels.append(cursor.strftime("%d/%m"))
        chart_values.append(count)
        history_rows.append(
            {
                "date": cursor.strftime("%d/%m/%Y"),
                "count": count,
            }
        )
        cursor += timedelta(days=1)

    # Contexte à envoyer au template
    context = {
        'total_users': total_users,
        'connected_count': connected_count,
        'connected_users': connected_users,
        'users': users,
        'roles_exclus': roles_exclus,
        'connection_history_labels': json.dumps(chart_labels),
        'connection_history_values': json.dumps(chart_values),
        'connection_history_rows': list(reversed(history_rows)),
        'history_days': len(history_rows),
    }

    return render(request, 'user_statistics.html', context)


@login_required
@csrf_exempt
def ppe(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()
    filiale_txt = request.GET.get('filiale_txt', '')
    agence_txt = request.GET.get('agence_txt', '')
    expl_txt = request.GET.get('expl_txt', '')
    client_txt = request.GET.get('client', '')
    risque_txt = request.GET.get('risque', '')
    filiale_txt = request.GET.get('filiale_txt', '')
    agence_txt = request.GET.get('agence_txt', '')
    expl_txt = request.GET.get('expl_txt', '')
    client_txt = request.GET.get('client', '')
    risque_txt = request.GET.get('risque', '')
    filiale_txt = request.GET.get('filiale_txt', '')
    agence_txt = request.GET.get('agence_txt', '')
    lib_agence = request.GET.get('lib_agence', '')
    expl_txt = request.GET.get('expl_txt', '')
    client_txt = request.GET.get('client', '')
    risque_txt = request.GET.get('risque', '')
    filiale_txt = request.GET.get('filiale_txt', '')
    agence_txt = request.GET.get('agence_txt', '')
    lib_agence = request.GET.get('lib_agence', '')
    expl_txt = request.GET.get('expl_txt', '')
    client_txt = request.GET.get('client', '')
    risque_txt = request.GET.get('risque', '')

    donnees = Kyc_pp.objects.filter(PPE__icontains="O")

    # Filtrage automatique selon le rôle
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    if user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    if user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    if user.organe in users_groupe:
        donnees = donnees

    # Filtres manuels via GET
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    if filiale_txt:
        donnees = donnees.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees = donnees.filter(AGENCE__icontains=agence_txt)
    if expl_txt:
        donnees = donnees.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees = donnees.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees = donnees.filter(RISQUE__icontains=risque_txt)
    if filiale_txt:
        donnees = donnees.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees = donnees.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        donnees = donnees.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        donnees = donnees.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees = donnees.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees = donnees.filter(RISQUE__icontains=risque_txt)

    # === Valeurs du formulaire selon le rôle ===
    if user.organe == "Directeur Agence":
        exploitants = donnees.filter(AGENCE=user.agence).values_list('EXPL', flat=True).distinct()
        agences = donnees.filter(AGENCE=user.agence).values_list('AGENCE', flat=True).distinct()
    elif user.organe in users_filiale:
        agences = donnees.filter(FILIALE=user.filiale).values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.filter(FILIALE=user.filiale).values_list('EXPL', flat=True).distinct()
    else:
        exploitants = donnees.values_list('EXPL', flat=True).distinct()
        agences = donnees.values_list('AGENCE', flat=True).distinct()

    filiales = donnees.values_list('FILIALE', flat=True).distinct()

    context = {
        'donnees': donnees,
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
    }

    return render(request, 'ppe.html', context)



def export_ppe(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupérer les filtres GET
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()

    # Base queryset : PPE = "O"
    donnees = Kyc_pp.objects.filter(PPE__icontains="O")

    # Filtrage selon le rôle utilisateur
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    # else: si utilisateur avec rôle “groupe” ou autre --> pas de filtre rôle spécifique

    # Appliquer les filtres GET s’ils sont fournis
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Non rens PPE"

    headers = [
        "FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP",
        "PAYNAIS", "PROFESSION", "ADRESSE", "PAYS_RESID", "NUMID",
        "SALAIRE", "ORIGINE_REV", "DATVALID", "TEL"
    ]
    ws.append(headers)

    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
            d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID,
            d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL
        ])

    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"PPE_non_rens_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def _apply_pp_header_filters(queryset, request, include_pays_resid=False, include_devise=False):
    field_map = {
        "lib_agence": "LIB_AGENCE",
        "client": "CLIENT",
        "idp": "IDP",
        "numid": "NUMID",
        "datnais": "DATNAIS",
        "paynais": "PAYNAIS",
        "adresse": "ADRESSE",
        "codape": "CODAPE",
        "profession": "PROFESSION",
        "salaire": "SALAIRE",
        "origine_rev": "ORIGINE_REV",
        "datvalid": "DATVALID",
        "tel": "TEL",
        "datouv": "DATOUV",
    }
    if include_pays_resid:
        field_map["pays_resid"] = "PAYS_RESID"
    if include_devise:
        field_map["devise"] = "DEVISE"

    for param, field in field_map.items():
        value = request.GET.get(param, "").strip()
        if value:
            queryset = queryset.filter(**{f"{field}__icontains": value})
    return queryset


@login_required
@csrf_exempt
def non_resid(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 🌟 CORRECTION / AMÉLIORATION 🌟
    # Utilisation de __exact pour filtrer strictement les non-résidents ('N')
    # Utilisez __icontains="N" si le champ peut contenir d'autres informations et que "N" suffit.
    donnees = Kyc_pp.objects.filter(RESID__icontains="N")
    # Si vous voulez l'ancienne logique avec moins de sensibilité à la casse :
    # donnees = Kyc_pp.objects.filter(RESID__iexact="N")

    # === Filtrage automatique selon le rôle ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # L'instruction "donnees = donnees" est inutile, on peut laisser le pass ou ne rien faire
        pass

    # === Filtres manuels via GET ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    donnees = _apply_pp_header_filters(donnees, request, include_pays_resid=True)

    # === Calcul des valeurs du formulaire (Listes de filtres) ===
    # On calcule les listes sur le QuerySet filtré par le rôle

    # Par défaut (pour les users_groupe ou si aucun rôle spécifique n'est atteint)
    exploitants = donnees.values_list('EXPL', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()

    # Remplacer par des filtres plus stricts si l'utilisateur a un rôle restreint
    if user.organe == "Directeur Agence":
        # Les filtres par filiale et agence ont déjà été appliqués ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()
    elif user.organe in users_filiale:
        # Le filtre par filiale a déjà été appliqué ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()

    filiales = donnees.values_list('FILIALE', flat=True).distinct()
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    # 2. Obtenir le QuerySet final pour la pagination
    # On utilise 'donnees' qui est le QuerySet filtré
    queryset = donnees

    # Simulation de la variable
    ITEMS_PER_PAGE = 25

    # 3. Appliquer le Paginator
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la première page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la dernière page
        objets_page = paginator.page(paginator.num_pages)

    context = {
        # 'donnees' est maintenant l'objet Page paginé
        "donnees": objets_page,
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
        'get_params': query_params.urlencode(),
    }
    return render(request, 'non_resid.html', context)

def export_non_resid_pp(request):
        user = request.user

        users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
        users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                        "Contrôle Permanent Groupe", "PASS", "GUEST"]

        # Récupération des filtres GET pour la synchronisation
        filiale_param = request.GET.get('filiale', '')
        agence_param = request.GET.get('agence', '')
        expl_param = request.GET.get('expl', '')

        # Début du Queryset
        donnees = Kyc_pp.objects.filter(RESID__icontains="N")


        # === Filtrage automatique selon le rôle (identique à devise) ===
        if user.organe == "Chargé Client":
            donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
        elif user.organe == "Directeur Agence":
            donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
        elif user.organe in users_filiale:
            donnees = donnees.filter(FILIALE=user.filiale)
        elif user.organe in users_groupe:
            pass  # on ne filtre pas davantage

        # === Filtres manuels via GET (synchronisation) ===
        if filiale_param:
            donnees = donnees.filter(FILIALE__icontains=filiale_param)
        if agence_param:
            donnees = donnees.filter(AGENCE__icontains=agence_param)
        if expl_param:
            donnees = donnees.filter(EXPL__icontains=expl_param)
        donnees = _apply_pp_header_filters(donnees, request, include_pays_resid=True)

        # Fin du Queryset filtré

        # Création du classeur Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Comptes Devise PP"  # J'ai renommé le titre

        # Entêtes
        headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP", "PAYNAIS", "PROFESSION", "ADRESSE", "PAYS_RESID",
                   "NUMID", "SALAIRE", "ORIGINE_REV", "DATVALID", "TEL"]
        ws.append(headers)

        # Données
        for d in donnees:
            ws.append([
                d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
                d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID, d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL
            ])

        # Ajustement largeur des colonnes (optionnel)
        for col_num, column_title in enumerate(headers, 1):
            column_letter = get_column_letter(col_num)
            ws.column_dimensions[column_letter].width = 15

        # Préparer la réponse HTTP
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(output.read(),
                                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
        filename = f"Comptes_non_resid_PP_{date_str}.xlsx"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


@login_required
@csrf_exempt

def non_resid_pm(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 🌟 CORRECTION / AMÉLIORATION 🌟
    # Utilisation de __exact pour filtrer strictement les non-résidents ('N')
    # Utilisez __icontains="N" si le champ peut contenir d'autres informations et que "N" suffit.
    donnees = Kyc_pm.objects.filter(RESID__exact="N")
    # Si vous voulez l'ancienne logique avec moins de sensibilité à la casse :
    # donnees = Kyc_pp.objects.filter(RESID__iexact="N")

    # === Filtrage automatique selon le rôle ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # L'instruction "donnees = donnees" est inutile, on peut laisser le pass ou ne rien faire
        pass

    # === Filtres manuels via GET ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # === Calcul des valeurs du formulaire (Listes de filtres) ===
    # On calcule les listes sur le QuerySet filtré par le rôle

    # Par défaut (pour les users_groupe ou si aucun rôle spécifique n'est atteint)
    exploitants = donnees.values_list('EXPL', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()

    # Remplacer par des filtres plus stricts si l'utilisateur a un rôle restreint
    if user.organe == "Directeur Agence":
        # Les filtres par filiale et agence ont déjà été appliqués ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()
    elif user.organe in users_filiale:
        # Le filtre par filiale a déjà été appliqué ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()

    filiales = donnees.values_list('FILIALE', flat=True).distinct()

    # 2. Obtenir le QuerySet final pour la pagination
    # On utilise 'donnees' qui est le QuerySet filtré
    queryset = donnees

    # Simulation de la variable
    ITEMS_PER_PAGE = 25

    # 3. Appliquer le Paginator
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la première page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la dernière page
        objets_page = paginator.page(paginator.num_pages)

    context = {
        # 'donnees' est maintenant l'objet Page paginé
        "donnees": objets_page,
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
        'get_params': query_params.urlencode(),
    }
    return render(request, 'non_resid_pm.html', context)


def export_non_resid_pm(request):
    user = request.user

    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupération des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Début du Queryset
    donnees = Kyc_pm.objects.filter(RESID__icontains="N")

    # === Filtrage automatique selon le rôle (identique à devise) ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # on ne filtre pas davantage

    # === Filtres manuels via GET (synchronisation) ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # Fin du Queryset filtré

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommé le titre

    # Entêtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "AGEC", "CODAPE", "IDM", "RCSNO", "CAPITAL", "CA",
               "RESULTAT", "TEL"]
    ws.append(headers)

    # Données
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.AGEC, d.CODAPE, d.IDM,
            d.RCSNO, d.CAPITAL, d.CA, d.RESULTAT, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Comptes_non_resid_PM_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def scoring(request):
    # 1. Définition des rôles
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau", 'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]

    user = request.user
    today = date.today()

    # 2. Récupération des paramètres
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")
    filiale_txt = request.GET.get("filiale_txt", "").strip()
    agence_txt = request.GET.get("agence_txt", "").strip()
    lib_agence = request.GET.get("lib_agence", "").strip()
    expl_txt = request.GET.get("expl_txt", "").strip()
    client_txt = request.GET.get("client", "").strip()
    daterev_txt = request.GET.get("daterev", "").strip()

    # On commence par TOUT (on retire le filtre isnull pour tester)
    qs = DATEREV.objects.all()

    # 3. Filtrage par Rôle (Sécurité)
    organe = getattr(user, "organe", "")
    if organe == "Chargé Client":
        qs = qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif organe == "Directeur Agence":
        qs = qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif organe in users_filiale:
        qs = qs.filter(FILIALE=user.filiale)
    # Si users_groupe, on ne filtre pas initialement

    # 4. Filtrage par Période
    if periode_param == "today":
        qs = qs.filter(DATEREV__lte=today)
    elif periode_param == "3m":
        qs = qs.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=90))
    elif periode_param == "6m":
        qs = qs.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=180))
    elif periode_param == "1y":
        qs = qs.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=365))

    # 5. Filtres dynamiques de l'interface
    if filiale_param:
        qs = qs.filter(FILIALE=filiale_param)

    if agence_param:
        qs = qs.filter(AGENCE=agence_param)

    if expl_param:
        qs = qs.filter(EXPL=expl_param)
    if filiale_txt:
        qs = qs.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        qs = qs.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        qs = qs.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        qs = qs.filter(EXPL__icontains=expl_txt)
    if client_txt:
        qs = qs.filter(CLIENT__icontains=client_txt)
    if daterev_txt:
        daterev_txt = daterev_txt.strip()
        parsed = parse_date(daterev_txt)
        if not parsed:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(daterev_txt, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
        if parsed:
            qs = qs.filter(DATEREV=parsed)

    # 6. Génération des options pour les menus déroulants (basé sur le QS filtré ou global)
    # Il est souvent préférable de baser les options sur le QS global ou par filiale
    filiales_opts = DATEREV.objects.values_list("FILIALE", flat=True).distinct().order_by("FILIALE")
    agences_opts = qs.values_list("AGENCE", flat=True).distinct().order_by("AGENCE")
    exploitants_opts = qs.values_list("EXPL", flat=True).distinct().order_by("EXPL")

    # 7. Tri et Pagination
    donnees_queryset = qs.order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")

    paginator = Paginator(donnees_queryset, 100)
    page = request.GET.get('page')
    try:
        donnees_page = paginator.page(page)
    except:
        donnees_page = paginator.page(1)

    context = {
        "donnees": donnees_page,
        "filiales": filiales_opts,
        "agences": agences_opts,
        "exploitants": exploitants_opts,
        "periode": periode_param,
        "filiale_param": filiale_param,
        "agence_param": agence_param,
        "expl_param": expl_param,
        "can_pick_filiale": organe in users_groupe,
        "can_pick_agence": (organe in users_groupe or organe in users_filiale or organe == "Directeur Agence"),
        "can_pick_expl": (organe in users_groupe or organe in users_filiale or organe == "Directeur Agence"),
        "get_params": request.GET.urlencode(),
    }
    return render(request, "scoring.html", context)

from io import BytesIO
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from datetime import datetime, date, timedelta
from .models import DATEREV

def export_csv_scoring(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupérer les filtres GET comme dans la vue scoring
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")
    filiale_txt = request.GET.get("filiale_txt", "").strip()
    agence_txt = request.GET.get("agence_txt", "").strip()
    lib_agence = request.GET.get("lib_agence", "").strip()
    expl_txt = request.GET.get("expl_txt", "").strip()
    client_txt = request.GET.get("client", "").strip()
    daterev_txt = request.GET.get("daterev", "").strip()
    filiale_txt = request.GET.get("filiale_txt", "").strip()
    agence_txt = request.GET.get("agence_txt", "").strip()
    lib_agence = request.GET.get("lib_agence", "").strip()
    expl_txt = request.GET.get("expl_txt", "").strip()
    client_txt = request.GET.get("client", "").strip()
    daterev_txt = request.GET.get("daterev", "").strip()

    base_qs = DATEREV.objects.filter(DATEREV__isnull=False)

    if getattr(user, "organe", "") == "Chargé Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        base_qs = base_qs.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # pas de filtre organe → laisse tout (selon ce que tu veux)
        pass
    else:
        # par sécurité, si organe non reconnu, on vide
        base_qs = DATEREV.objects.none()

    # Appliquer le filtre période si défini
    qs_period = base_qs
    today = date.today()
    if periode_param == "today":
        qs_period = qs_period.filter(DATEREV__lte=today)
    elif periode_param == "3m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=90))
    elif periode_param == "6m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=180))
    elif periode_param == "1y":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=365))

    # Filiale
    if filiale_param:
        qs_period = qs_period.filter(FILIALE=filiale_param)

    # Agence
    if agence_param:
        qs_period = qs_period.filter(AGENCE=agence_param)

    # Exploitant
    if expl_param:
        qs_period = qs_period.filter(EXPL=expl_param)
    if filiale_txt:
        qs_period = qs_period.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        qs_period = qs_period.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        qs_period = qs_period.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        qs_period = qs_period.filter(EXPL__icontains=expl_txt)
    if client_txt:
        qs_period = qs_period.filter(CLIENT__icontains=client_txt)
    if daterev_txt:
        parsed = parse_date(daterev_txt)
        if not parsed:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(daterev_txt, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
        if parsed:
            qs_period = qs_period.filter(DATEREV=parsed)
    if filiale_txt:
        qs_period = qs_period.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        qs_period = qs_period.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        qs_period = qs_period.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        qs_period = qs_period.filter(EXPL__icontains=expl_txt)
    if client_txt:
        qs_period = qs_period.filter(CLIENT__icontains=client_txt)
    if daterev_txt:
        parsed = parse_date(daterev_txt)
        if not parsed:
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(daterev_txt, fmt).date()
                    break
                except (ValueError, TypeError):
                    continue
        if parsed:
            qs_period = qs_period.filter(DATEREV=parsed)

    donnees = qs_period

    # Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # Entêtes (vérifie que les noms sont corrects)
    headers = ['FILIALE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    for d in donnees:
        daterev = d.DATEREV
        if hasattr(daterev, 'tzinfo'):
            daterev = daterev.replace(tzinfo=None)
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, daterev, d.PPE, d.RISQUE
        ])

    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"scoring_export_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

def export_csv_scoring_ppe(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupérer les filtres GET comme dans la vue scoring
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    if user.organe == 'Conformité':
        base_qs = DATEREV.objects.filter(FILIALE=user.filiale, PPE__icontains="O", DATEREV__isnull=False)
    elif user.organe == "Conformité Groupe":
        base_qs = DATEREV.objects.filter(PPE__icontains="O", DATEREV__isnull=False)

    # Appliquer le filtre période si défini
    qs_period = base_qs
    today = date.today()
    if periode_param == "today":
        qs_period = qs_period.filter(DATEREV__lte=today)
    elif periode_param == "3m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=90))
    elif periode_param == "6m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=180))
    elif periode_param == "1y":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=365))

    # Filiale
    if filiale_param:
        qs_period = qs_period.filter(FILIALE=filiale_param)

    # Agence
    if agence_param:
        qs_period = qs_period.filter(AGENCE=agence_param)

    # Exploitant
    if expl_param:
        qs_period = qs_period.filter(EXPL=expl_param)

    donnees = qs_period

    # Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # Entêtes (vérifie que les noms sont corrects)
    headers = ['FILIALE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    for d in donnees:
        daterev = d.DATEREV
        if hasattr(daterev, 'tzinfo'):
            daterev = daterev.replace(tzinfo=None)
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, daterev, d.PPE, d.RISQUE
        ])

    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"scoring_PPE_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def clients_scorer(request):
    # Rôles
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]

    user = request.user

    notes = Notation.objects.filter(flux_stock='Flux')

    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la dernière note par agent
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)


    # Params GET
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    # Récupérer les paramètres GET pour les conserver dans les liens de pagination
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']

    base_qs = DATEREV.objects.all()

    # --- LOGIQUE DE FILTRAGE PAR RÔLE ---
    if getattr(user, "organe", "") == "Chargé Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        base_qs = base_qs.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # Pas de filtre initial pour le groupe

    # --- LOGIQUE DE FILTRAGE PAR PÉRIODE ---
    today = date.today()
    qs_period = base_qs
    if periode_param == "today":
        qs_period = qs_period.filter(DATEREV__lte=today)
    elif periode_param == "3m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=90))
    elif periode_param == "6m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=180))
    elif periode_param == "1y":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=365))

    # --- LOGIQUE DE FILTRAGE DYNAMIQUE (FILIALE, AGENCE, EXPL) ---

    can_pick_filiale = user.organe in users_groupe
    selected_filiale = filiale_param if can_pick_filiale else getattr(user, "filiale", "")
    filiales_opts = qs_period.values_list("FILIALE", flat=True).distinct().order_by("FILIALE")
    qs_filiale = qs_period
    if selected_filiale:
        qs_filiale = qs_filiale.filter(FILIALE=selected_filiale)

    can_pick_agence = (user.organe in users_groupe) or (user.organe in users_filiale) or (
            user.organe == "Directeur Agence")
    if user.organe == "Directeur Agence":
        selected_agence = getattr(user, "agence", "")
    else:
        selected_agence = agence_param
    agences_opts = qs_filiale.values_list("AGENCE", flat=True).distinct().order_by("AGENCE")
    qs_agence = qs_filiale
    if selected_agence:
        qs_agence = qs_agence.filter(AGENCE=selected_agence)

    can_pick_expl = (user.organe in users_groupe) or (user.organe in users_filiale) or (
            user.organe == "Directeur Agence")
    if getattr(user, "organe", "") == "Chargé Client":
        selected_expl = getattr(user, "code_expl", "")
    else:
        selected_expl = expl_param
    exploitants_opts = qs_agence.values_list("EXPL", flat=True).distinct().order_by("EXPL")

    donnees_queryset = qs_agence  # Renommé pour clarté avant le filtre final
    if selected_expl:
        donnees_queryset = donnees_queryset.filter(EXPL=selected_expl)

    # Evite les doublons visibles si des doublons historiques existent en base
    donnees_queryset = (
        donnees_queryset
        .values("FILIALE", "AGENCE", "LIB_AGENCE", "EXPL", "CLIENT", "DATEREV", "PPE", "RISQUE")
        .distinct()
        .order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")
    )

    # --- DÉBUT DE LA LOGIQUE DE PAGINATION ---

    paginator = Paginator(donnees_queryset, 100)  # 100 éléments par page
    page = request.GET.get('page')

    try:
        donnees_page = paginator.page(page)
    except PageNotAnInteger:
        donnees_page = paginator.page(1)
    except EmptyPage:
        donnees_page = paginator.page(paginator.num_pages)

    # --- FIN DE LA LOGIQUE DE PAGINATION ---

    context = {
        # On passe l'objet Page au template
        "donnees": donnees_page,

        # Options de filtres
        "filiales": filiales_opts,
        "agences": agences_opts,
        "exploitants": exploitants_opts,
        "notation": notation,
        # Sélections courantes
        "periode": periode_param,
        "filiale_param": selected_filiale,
        "agence_param": selected_agence,
        "expl_param": selected_expl,

        # Rôles
        "users_groupe": users_groupe,
        "users_filiale": users_filiale,

        # Droits d'édition des selects
        "can_pick_filiale": can_pick_filiale,
        "can_pick_agence": can_pick_agence,
        "can_pick_expl": can_pick_expl,

        # Paramètres GET pour la pagination
        'get_params': get_params.urlencode(),
    }
    return render(request, "clients_scorer.html", context)


def export_csv_scoring_clients(request):
    def strip_tz(value):
        if hasattr(value, 'tzinfo'):
            return value.replace(tzinfo=None)
        return value

    user = request.user

    donnees = (
        DATEREV.objects
        .filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
        .values("FILIALE", "AGENCE", "EXPL", "CLIENT", "DATEREV", "PPE", "RISQUE")
        .distinct()
        .order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")
    )

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # Entêtes
    headers = ['AGENCE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    # Données
    for d in donnees:
        ws.append([
            d["FILIALE"], d["AGENCE"], d["EXPL"], d["CLIENT"], d["DATEREV"], d["PPE"], d["RISQUE"]

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Revue_scoring_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@csrf_exempt
def sans_classe(request):
    user = request.user

    # 1. Rôles et paramètres
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]

    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    lib_agence = request.GET.get('lib_agence', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()

    # 2. Filtrage de base (Sécurité par rôle + Condition CLASSE vide)
    # On commence par le filtre "CLASSE vide ou nulle"
    donnees_queryset = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Restriction du périmètre selon l'organe de l'utilisateur
    if user.organe == "Chargé Client":
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale)

    # 3. Filtres manuels via le formulaire (GET)
    if filiale_param:
        donnees_queryset = donnees_queryset.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees_queryset = donnees_queryset.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees_queryset = donnees_queryset.filter(EXPL__icontains=expl_param)
    if filiale_txt:
        donnees_queryset = donnees_queryset.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees_queryset = donnees_queryset.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        donnees_queryset = donnees_queryset.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        donnees_queryset = donnees_queryset.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees_queryset = donnees_queryset.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees_queryset = donnees_queryset.filter(RISQUE__icontains=risque_txt)

    # Tri cohérent pour la pagination
    donnees_queryset = donnees_queryset.order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")

    # 4. Options pour les menus déroulants (respectant le périmètre)
    options_qs = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))
    if user.organe == "Chargé Client":
        options_qs = options_qs.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        options_qs = options_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        options_qs = options_qs.filter(FILIALE=user.filiale)

    filiales = options_qs.values_list('FILIALE', flat=True).distinct().order_by('FILIALE')
    agences = options_qs.values_list('AGENCE', flat=True).distinct().order_by('AGENCE')
    exploitants = options_qs.values_list('EXPL', flat=True).distinct().order_by('EXPL')

    # 5. Logique de pagination
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']

    paginator = Paginator(donnees_queryset, 100)
    page = request.GET.get('page')

    try:
        donnees_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        donnees_page = paginator.page(1)

    context = {
        'donnees': donnees_page,
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
        'get_params': get_params.urlencode(),
        'filiale_param': filiale_param,
        'agence_param': agence_param,
        'expl_param': expl_param,
    }

    return render(request, 'sans_classe.html', context)


def export_sans_classe(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupérer les filtres GET
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Base queryset — uniquement ceux avec un RISQUE non nul
    donnees = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Filtrage selon le rôle
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # donnees reste DATEREV.objects.filter(CLASSE__isnull=False)
        pass
    else:
        # Si organe non reconnu ou pas autorisé — optionnel : renvoyer vide
        donnees = DATEREV.objects.none()

    # Appliquer les filtres GET si présents
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    if filiale_txt:
        donnees = donnees.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees = donnees.filter(AGENCE__icontains=agence_txt)
    if lib_agence:
        donnees = donnees.filter(LIB_AGENCE__icontains=lib_agence)
    if expl_txt:
        donnees = donnees.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees = donnees.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees = donnees.filter(RISQUE__icontains=risque_txt)

    # Création du fichier Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Sans_Classe_Export"

    headers = ['FILIALE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    for d in donnees:
        daterev = d.DATEREV
        if hasattr(daterev, 'tzinfo'):
            daterev = daterev.replace(tzinfo=None)
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, daterev, d.PPE, d.RISQUE
        ])

    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Sans_Classe_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


from django.db.models import Q, Max


def sans_classe_s(request):
    user = request.user

    # 1. Rôles et paramètres
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]

    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 2. Gestion des Notations (Dernière note par agent selon périmètre)
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    # Sécurisation de l'affichage des notes
    if user.organe == "Chargé Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe in users_filiale:
        notation = notation.filter(agent__filiale=user.filiale)
    # Pour le Groupe, on voit toutes les notes (ou filtrer selon besoin)

    # 3. Filtrage du QuerySet Principal (Uniquement CLASSE non vide)
    # Correction : On exclut les vides ET les nuls
    donnees_queryset = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Filtrage automatique selon le rôle (Sécurité)
    if user.organe == "Chargé Client":
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees_queryset = donnees_queryset.filter(FILIALE=user.filiale)

    # Filtres manuels via le formulaire (GET)
    if filiale_param:
        donnees_queryset = donnees_queryset.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees_queryset = donnees_queryset.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees_queryset = donnees_queryset.filter(EXPL__icontains=expl_param)
    if filiale_txt:
        donnees_queryset = donnees_queryset.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees_queryset = donnees_queryset.filter(AGENCE__icontains=agence_txt)
    if expl_txt:
        donnees_queryset = donnees_queryset.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees_queryset = donnees_queryset.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees_queryset = donnees_queryset.filter(RISQUE__icontains=risque_txt)

    donnees_queryset = donnees_queryset.order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")

    # 4. Valeurs du formulaire (Options des filtres)
    options_qs = DATEREV.objects.all()
    if user.organe == "Chargé Client":
        options_qs = options_qs.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        options_qs = options_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        options_qs = options_qs.filter(FILIALE=user.filiale)

    filiales = options_qs.values_list('FILIALE', flat=True).distinct().order_by('FILIALE')
    agences = options_qs.values_list('AGENCE', flat=True).distinct().order_by('AGENCE')
    exploitants = options_qs.values_list('EXPL', flat=True).distinct().order_by('EXPL')

    # 5. Pagination
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']

    paginator = Paginator(donnees_queryset, 100)
    page = request.GET.get('page')

    try:
        donnees_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        donnees_page = paginator.page(1)

    context = {
        'donnees': donnees_page,
        'filiales': filiales,
        'notation': notation,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
        'get_params': get_params.urlencode(),
        'filiale_param': filiale_param,
        'agence_param': agence_param,
        'expl_param': expl_param,
    }

    return render(request, 'sans_classe_s.html', context)


def export_sans_classe_s(request):
    def strip_tz(value):
        if hasattr(value, 'tzinfo'):
            return value.replace(tzinfo=None)
        return value

    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')
    filiale_txt = request.GET.get('filiale_txt', '').strip()
    agence_txt = request.GET.get('agence_txt', '').strip()
    expl_txt = request.GET.get('expl_txt', '').strip()
    client_txt = request.GET.get('client', '').strip()
    risque_txt = request.GET.get('risque', '').strip()

    donnees = DATEREV.objects.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)

    donnees = donnees.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    if filiale_txt:
        donnees = donnees.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees = donnees.filter(AGENCE__icontains=agence_txt)
    if expl_txt:
        donnees = donnees.filter(EXPL__icontains=expl_txt)
    if client_txt:
        donnees = donnees.filter(CLIENT__icontains=client_txt)
    if risque_txt:
        donnees = donnees.filter(RISQUE__icontains=risque_txt)


    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clients non classés"

    # Entêtes
    headers = ['AGENCE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    # Données
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.DATEREV, d.PPE, d.RISQUE

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Clients sans classe de risque {date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response




ITEMS_PER_PAGE = 100  # Nombre d'éléments à charger par page

from django.shortcuts import render
from django.db.models import Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Kyc_pm, Notation  # Assurez-vous que les imports correspondent à vos fichiers

# --- 1. FONCTION DE SÉCURITÉ PM (Périmètre de données) ---
def get_filtered_queryset_pm(request):
    """Garantit que l'utilisateur ne voit que les entreprises (PM) de son périmètre."""
    user = request.user
    queryset = Kyc_pm.objects.all()

    if user.organe == "Chargé Client":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)

    elif user.organe in ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        queryset = queryset.filter(FILIALE=user.filiale)

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]:
        # Accès total pour le Groupe
        pass

    return queryset.order_by('id')

# --- 2. FONCTION DES LISTES DE FILTRES PM ---
def get_filter_lists_pm(user, request):
    """Génère les options des menus déroulants PM selon les droits d'accès."""
    filiale_list, agence_list, expl_list, datouv_list = [], [], [], []
    base_qs = Kyc_pm.objects.all()

    # Restriction de la base de données selon le rôle
    if user.organe == "Chargé Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        base_qs = base_qs.filter(FILIALE=user.filiale)

    # 1. Liste des Filiales (Uniquement pour le Groupe)
    filiale_list = Kyc_pm.objects.values_list("FILIALE", flat=True).distinct().order_by("FILIALE")

    # 2. Logique dynamique des Agences et Exploitants
    f_filiale = request.GET.get("filiale")
    f_agence = request.GET.get("agence")

    # Agences
    if f_filiale:
        agence_list = Kyc_pm.objects.filter(FILIALE=f_filiale).values_list("AGENCE", flat=True).distinct()
    elif user.organe in ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        agence_list = base_qs.values_list("AGENCE", flat=True).distinct()

    # Exploitants
    if f_agence:
        expl_list = Kyc_pm.objects.filter(AGENCE=f_agence).values_list("EXPL", flat=True).distinct()
    elif user.organe == "Directeur Agence":
        expl_list = base_qs.values_list("EXPL", flat=True).distinct()
    elif not f_agence and (f_filiale or user.organe in ["DSI", "Conformité", "Contrôle Permanent"]):
        expl_list = base_qs.values_list("EXPL", flat=True).distinct()

    # 3. Dates d'ouverture
    datouv_list = base_qs.exclude(DATOUV__isnull=True).values_list("DATOUV", flat=True).distinct().order_by('-DATOUV')

    return filiale_list, agence_list, expl_list, datouv_list

# --- 3. VUE PRINCIPALE PM ---
def non_rens_pm(request):
    user = request.user

    # A. Sécurité : Queryset restreint au rôle (PM)
    queryset = get_filtered_queryset_pm(request)

    # B. Application des filtres du formulaire
    f_filiale = request.GET.get('filiale')
    f_agence = request.GET.get('agence')
    f_expl = request.GET.get('expl')
    f_datouv = request.GET.get('datouv')
    f_lib_agence = request.GET.get('lib_agence')
    f_client = request.GET.get('client')
    f_idm = request.GET.get('idm')
    f_agec = request.GET.get('agec')
    f_codape = request.GET.get('codape')
    f_rcsno = request.GET.get('rcsno')
    f_capital = request.GET.get('capital')
    f_ca = request.GET.get('ca')
    f_resultat = request.GET.get('resultat')

    if f_filiale: queryset = queryset.filter(FILIALE=f_filiale)
    if f_agence: queryset = queryset.filter(AGENCE=f_agence)
    if f_expl: queryset = queryset.filter(EXPL=f_expl)
    if f_datouv: queryset = queryset.filter(DATOUV=f_datouv)
    if f_lib_agence: queryset = queryset.filter(LIB_AGENCE__icontains=f_lib_agence)
    if f_client: queryset = queryset.filter(CLIENT__icontains=f_client)
    if f_idm: queryset = queryset.filter(IDM__icontains=f_idm)
    if f_agec: queryset = queryset.filter(AGEC__icontains=f_agec)
    if f_codape: queryset = queryset.filter(CODAPE__icontains=f_codape)
    if f_rcsno: queryset = queryset.filter(RCSNO__icontains=f_rcsno)
    if f_capital: queryset = queryset.filter(CAPITAL__icontains=f_capital)
    if f_ca: queryset = queryset.filter(CA__icontains=f_ca)
    if f_resultat: queryset = queryset.filter(RESULTAT__icontains=f_resultat)

    # C. Notations (Même logique de sécurité que PP)
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    if user.organe == "Chargé Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "GUEST"]:
        notation = notation.filter(agent__filiale=user.filiale)

    # D. Listes pour les menus déroulants
    filiale_list, agence_list, expl_list, datouv_list = get_filter_lists_pm(user, request)

    # E. Pagination et conservation des paramètres
    query_params = request.GET.copy()
    if 'page' in query_params: del query_params['page']
    get_params = query_params.urlencode()

    paginator = Paginator(queryset, 30)
    page_number = request.GET.get('page')
    try:
        objets_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        objets_page = paginator.page(1)

    context = {
        "donnees": objets_page,
        "get_params": get_params,
        "filiale_list": filiale_list,
        "agence_list": agence_list,
        "expl_list": expl_list,
        "datouv_list": datouv_list,
        "notation": notation,
        "users_filiale": ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité'],
        "users_groupe": ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"],
    }

    return render(request, "non_rens_pm.html", context)

from datetime import datetime
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from io import BytesIO
from .models import Kyc_pm  # Vérifiez le nom de votre modèle


def export_csv_pm(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # 1. Base de données initiale
    donnees = Kyc_pm.objects.all()

    # 2. Récupération des paramètres de filtrage depuis l'URL
    f_filiale = request.GET.get("filiale")
    f_agence = request.GET.get("agence")
    f_expl = request.GET.get("expl")
    f_datouv = request.GET.get("datouv")
    f_lib_agence = request.GET.get("lib_agence")
    f_client = request.GET.get("client")
    f_idm = request.GET.get("idm")
    f_agec = request.GET.get("agec")
    f_codape = request.GET.get("codape")
    f_rcsno = request.GET.get("rcsno")
    f_capital = request.GET.get("capital")
    f_ca = request.GET.get("ca")
    f_resultat = request.GET.get("resultat")

    # 3. Sécurité par rôle (Périmètre de l'utilisateur)
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)

    # 4. Application des filtres de recherche choisis par l'utilisateur
    if f_filiale:
        donnees = donnees.filter(FILIALE=f_filiale)
    if f_agence:
        donnees = donnees.filter(AGENCE=f_agence)
    if f_expl:
        donnees = donnees.filter(EXPL=f_expl)
    if f_lib_agence:
        donnees = donnees.filter(LIB_AGENCE__icontains=f_lib_agence)
    if f_client:
        donnees = donnees.filter(CLIENT__icontains=f_client)
    if f_idm:
        donnees = donnees.filter(IDM__icontains=f_idm)
    if f_agec:
        donnees = donnees.filter(AGEC__icontains=f_agec)
    if f_codape:
        donnees = donnees.filter(CODAPE__icontains=f_codape)
    if f_rcsno:
        donnees = donnees.filter(RCSNO__icontains=f_rcsno)
    if f_capital:
        donnees = donnees.filter(CAPITAL__icontains=f_capital)
    if f_ca:
        donnees = donnees.filter(CA__icontains=f_ca)
    if f_resultat:
        donnees = donnees.filter(RESULTAT__icontains=f_resultat)

    # 5. Conversion et Filtrage par DATE (Crucial pour éviter l'export vide)
    if f_datouv and f_datouv.strip():
        try:
            # On tente de convertir "12/01/2026" en objet date Python
            date_objet = datetime.strptime(f_datouv.strip(), '%d/%m/%Y').date()
            donnees = donnees.filter(DATOUV=date_objet)
        except (ValueError, TypeError):
            # Si la date dans l'URL n'est pas au bon format, on ignore ce filtre
            pass

    # 6. Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Export KYC PM"

    # En-têtes (Headers)
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "AGEC", "CODAPE", "IDM",
               "RCSNO", "CAPITAL", "CA", "RESULTAT", "ORIGINE_REV", "TEL", "DATE_OUV"]
    ws.append(headers)

    # Remplissage des lignes
    for d in donnees:
        ws.append([
            str(d.FILIALE or ""),
            str(d.AGENCE or ""),
            str(d.EXPL or ""),
            str(d.CLIENT or ""),
            str(d.AGEC or ""),
            str(d.CODAPE or ""),
            str(d.IDM or ""),
            str(d.RCSNO or ""),
            d.CAPITAL,
            d.CA,
            d.RESULTAT,
            str(d.ORIGINE_REV or ""),
            str(d.TEL or ""),
            format_date_for_export(d.DATOUV)
        ])

    # Mise en forme : Ajustement automatique de la largeur des colonnes
    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 18

    # 7. Préparation de la réponse HTTP pour le téléchargement
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Export_KYC_PM_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    return response

from django.shortcuts import render
from django.db.models import Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# Assurez-vous que Kyc_pp et Notation sont importés
# from .models import Kyc_pp, Notation

# --- CONSTANTE DE TAILLE DE PAGE ---
ITEMS_PER_PAGE = 100  # Nombre d'éléments à charger par page
from django.shortcuts import render
from django.db.models import Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Kyc_pp, Notation  # Vérifiez le nom de vos modèles


# --- 1. FONCTION DE SÉCURITÉ (Périmètre de données) ---
def get_filtered_queryset(request):
    """Garantit que l'utilisateur ne voit que son périmètre autorisé."""
    user = request.user
    queryset = Kyc_pp.objects.all()

    if user.organe == "Chargé Client":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)

    elif user.organe in ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        queryset = queryset.filter(FILIALE=user.filiale)

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]:
        # Le groupe voit tout par défaut, le filtrage se fera via le formulaire
        pass

    return queryset.order_by('id')


# --- 2. FONCTION DES LISTES DE FILTRES (Menus déroulants) ---
def get_filter_lists(user, request):
    """Génère les options des menus déroulants selon les droits d'accès."""
    filiale_list, agence_list, expl_list, datouv_list = [], [], [], []
    base_queryset = Kyc_pp.objects.all()

    if user.organe == "Chargé Client":
        base_queryset = base_queryset.filter(FILIALE=user.filiale, AGENCE= user.agence, EXPL=user.code_expl)
        expl_list = [user.code_expl]

    elif user.organe == "Directeur Agence":
        base_queryset = base_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)
        expl_list = base_queryset.values_list("EXPL", flat=True).distinct()

    elif user.organe in ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        base_queryset = base_queryset.filter(FILIALE=user.filiale)
        agence_list = base_queryset.values_list("AGENCE", flat=True).distinct()

        agence_filter = request.GET.get("agence")
        if agence_filter:
            expl_list = base_queryset.filter(AGENCE=agence_filter).values_list("EXPL", flat=True).distinct()
        else:
            expl_list = base_queryset.values_list("EXPL", flat=True).distinct()

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]:
        filiale_list = Kyc_pp.objects.values_list("FILIALE", flat=True).distinct()

        filiale_filter = request.GET.get("filiale")
        agence_filter = request.GET.get("agence")

        if filiale_filter:
            base_queryset = base_queryset.filter(FILIALE=filiale_filter)
            agence_list = base_queryset.values_list("AGENCE", flat=True).distinct()
        if agence_filter:
            expl_list = base_queryset.filter(AGENCE=agence_filter).values_list("EXPL", flat=True).distinct()

    datouv_list = base_queryset.exclude(DATOUV__isnull=True).values_list("DATOUV", flat=True).distinct().order_by(
        '-DATOUV')

    return filiale_list, agence_list, expl_list, datouv_list


# --- 3. VUE PRINCIPALE ---
def non_rens(request):
    user = request.user

    # A. Sécurité de base : Queryset restreint au rôle
    queryset = get_filtered_queryset(request)

    # B. Application des filtres du formulaire (Si renseignés)
    f_filiale = request.GET.get('filiale')
    f_agence = request.GET.get('agence')
    f_expl = request.GET.get('expl')
    f_datouv = request.GET.get('datouv')

    f_lib_agence = request.GET.get('lib_agence')
    f_client = request.GET.get('client')
    f_idp = request.GET.get('idp')
    f_numid = request.GET.get('numid')
    f_datnais = request.GET.get('datnais')
    f_paynais = request.GET.get('paynais')
    f_adresse = request.GET.get('adresse')
    f_codape = request.GET.get('codape')
    f_profession = request.GET.get('profession')
    f_salaire = request.GET.get('salaire')
    f_origine_rev = request.GET.get('origine_rev')
    f_datvalid = request.GET.get('datvalid')
    f_tel = request.GET.get('tel')

    if f_filiale: queryset = queryset.filter(FILIALE=f_filiale)
    if f_agence: queryset = queryset.filter(AGENCE=f_agence)
    if f_expl: queryset = queryset.filter(EXPL=f_expl)
    if f_datouv: queryset = queryset.filter(DATOUV=f_datouv)
    if f_lib_agence: queryset = queryset.filter(LIB_AGENCE__icontains=f_lib_agence)
    if f_client: queryset = queryset.filter(CLIENT__icontains=f_client)
    if f_idp: queryset = queryset.filter(IDP__icontains=f_idp)
    if f_numid: queryset = queryset.filter(NUMID__icontains=f_numid)
    if f_datnais: queryset = queryset.filter(DATNAIS__icontains=f_datnais)
    if f_paynais: queryset = queryset.filter(PAYNAIS__icontains=f_paynais)
    if f_adresse: queryset = queryset.filter(ADRESSE__icontains=f_adresse)
    if f_codape: queryset = queryset.filter(CODAPE__icontains=f_codape)
    if f_profession: queryset = queryset.filter(PROFESSION__icontains=f_profession)
    if f_salaire: queryset = queryset.filter(SALAIRE__icontains=f_salaire)
    if f_origine_rev: queryset = queryset.filter(ORIGINE_REV__icontains=f_origine_rev)
    if f_datvalid: queryset = queryset.filter(DATVALID__icontains=f_datvalid)
    if f_tel: queryset = queryset.filter(TEL__icontains=f_tel)

    # C. Données de notation (Flux) filtrées par périmètre
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    if user.organe == "Chargé Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence,agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "GUEST"]:
        notation = notation.filter(agent__filiale=user.filiale)

    # D. Listes pour les menus déroulants
    filiale_list, agence_list, expl_list, datouv_list = get_filter_lists(user, request)

    # E. Pagination
    query_params = request.GET.copy()
    if 'page' in query_params: del query_params['page']
    get_params = query_params.urlencode()

    paginator = Paginator(queryset, 30)
    page_number = request.GET.get('page')
    try:
        objets_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        objets_page = paginator.page(1)

    context = {
        "donnees": objets_page,
        "get_params": get_params,
        "filiale_list": filiale_list,
        "agence_list": agence_list,
        "expl_list": expl_list,
        "datouv_list": datouv_list,
        'users_groupe': ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"],
        'users_filiale': ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité'],
        'notation': notation,
    }

    return render(request, "non_rens.html", context)

def export_csv_pp(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Partir de tous les objets
    donnees = Kyc_pp.objects.all()

    # Appliquer les mêmes filtres que dans la vue de liste
    # selon l’organe de l’utilisateur + éventuellement les filtres GET
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
        expl_filter = request.GET.get("expl")
        if expl_filter:
            donnees = donnees.filter(EXPL=expl_filter)

    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
        agence_filter = request.GET.get("agence")
        expl_filter = request.GET.get("expl")
        if agence_filter:
            donnees = donnees.filter(AGENCE=agence_filter)
        if expl_filter:
            donnees = donnees.filter(EXPL=expl_filter)

    elif user.organe in users_groupe:
        filiale_filter = request.GET.get("filiale")
        agence_filter = request.GET.get("agence")
        expl_filter = request.GET.get("expl")

        if filiale_filter:
            donnees = donnees.filter(FILIALE=filiale_filter)
        if agence_filter:
            donnees = donnees.filter(AGENCE=agence_filter)
        if expl_filter:
            donnees = donnees.filter(EXPL=expl_filter)

    # Ensuite création du fichier Excel (ou CSV selon ton besoin)
    wb = Workbook()
    ws = wb.active
    ws.title = "Export KYC"

    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP", "PAYNAIS",
               "PROFESSION", "ADRESSE", "PAYS_RESID", "NUMID", "SALAIRE",
               "ORIGINE_REV", "DATVALID", "TEL", "DATOUV"]
    ws.append(headers)

    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
            d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID,
            d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL, format_date_for_export(d.DATOUV)
        ])

    for col_num, _ in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        ws.column_dimensions[col_letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Champs_non_renseignés_PP_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_csv_anom(request):
    user = request.user

    users_filiale = ["DSI", "Conformit??", "Contr??le Permanent", "Directeur R??seau",'Risques', 'DAI', 'Qualit??']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformit?? Groupe", "Contr??le Permanent Groupe", "PASS", "GUEST"]

    # ????????????????????????????????????????????????
    # Logique de filtrage
    # ????????????????????????????????????????????????
    donnees = Anomalie.objects.all()

    filiale_filter = request.GET.get("filiale")
    agence_filter = request.GET.get("agence")
    expl_filter = request.GET.get("expl")

    filiale_txt = request.GET.get("filiale_txt")
    agence_txt = request.GET.get("agence_txt")
    expl_txt = request.GET.get("expl_txt")
    lib_agence = request.GET.get("lib_agence")
    client = request.GET.get("client")

    anom_age = request.GET.get("anom_age")
    anom_eer = request.GET.get("anom_eer")
    anom_cin = request.GET.get("anom_cin")

    if hasattr(user, "organe"):

        if user.organe == "Charg?? Client":
            donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)

        elif user.organe == "Directeur Agence":
            donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
            if expl_filter:
                donnees = donnees.filter(EXPL=expl_filter)

        elif user.organe in users_filiale:
            donnees = donnees.filter(FILIALE=user.filiale)
            if agence_filter:
                donnees = donnees.filter(AGENCE=agence_filter)
            if expl_filter:
                donnees = donnees.filter(EXPL=expl_filter)

        elif user.organe in users_groupe:
            if filiale_filter:
                donnees = donnees.filter(FILIALE=filiale_filter)
            if agence_filter:
                donnees = donnees.filter(AGENCE=agence_filter)
            if expl_filter:
                donnees = donnees.filter(EXPL=expl_filter)

    else:
        if filiale_filter:
            donnees = donnees.filter(FILIALE=filiale_filter)
        if agence_filter:
            donnees = donnees.filter(AGENCE=agence_filter)
        if expl_filter:
            donnees = donnees.filter(EXPL=expl_filter)

    if filiale_txt:
        donnees = donnees.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        donnees = donnees.filter(AGENCE__icontains=agence_txt)
    if expl_txt:
        donnees = donnees.filter(EXPL__icontains=expl_txt)
    if lib_agence:
        donnees = donnees.filter(LIB_AGENCE__icontains=lib_agence)
    if client:
        donnees = donnees.filter(CLIENT__icontains=client)

    if anom_age:
        donnees = donnees.filter(ANOMALIE_AGE=anom_age)
    if anom_eer:
        donnees = donnees.filter(ANOMALIE_DATE_EER=anom_eer)
    if anom_cin:
        donnees = donnees.filter(ANOMALIE_CIN=anom_cin)

    # ????????????????????????????????????????????????
    # Cr??ation du fichier Excel
    # ????????????????????????????????????????????????
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Anomalies"

    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "ANOMALIE_AGE", "ANOMALIE_DATE_EER", "ANOMALIE_CIN"]
    ws.append(headers)

    for obj in donnees:
        ws.append([
            obj.FILIALE,
            obj.AGENCE,
            obj.EXPL,
            obj.CLIENT,
            obj.ANOMALIE_AGE,
            obj.ANOMALIE_DATE_EER,
            obj.ANOMALIE_CIN
        ])

    for idx, col_title in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(idx)].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Champs_en_anomalie_PP_{date_str}.xlsx"

    response = HttpResponse(
        output,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    return response
def export_csv_anom_ppe(request):
    user = request.user
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupérer les filtres GET envoyés par le template
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Base queryset : anomalies avec PPE = 'O'
    donnees = Anomalie.objects.filter(PPE='O')

    # Filtrer selon le rôle de l’utilisateur
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    # Si user dans groupe ou autre, on laisse le queryset PPE='O'

    # Appliquer les filtres GET si fournis
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # Création du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "PPE en Anomalie"

    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT",
               "ANOMALIE_AGE", "ANOMALIE_DATE_EER", "ANOMALIE_CIN"]
    ws.append(headers)

    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT,
            d.ANOMALIE_AGE, d.ANOMALIE_DATE_EER, d.ANOMALIE_CIN
        ])

    for col_num, _ in enumerate(headers, 1):
        letter = get_column_letter(col_num)
        ws.column_dimensions[letter].width = 15

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"PPE_anomalies_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import TauxEvolution, TauxEvolution_filiale, Notation


@login_required
def statistiques(request):
    user = request.user
    # Liste des rôles ayant une vue globale (Groupe)
    user_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]

    # --- 1. GESTION DU MODE (Flux ou Stock) ---
    mode = request.GET.get('mode', 'Flux')
    is_stock = (mode == 'Stock')
    code_flux_stock = "S" if is_stock else "F"

    # --- 2. SÉCURISATION DE LA FILIALE (Verrouillage) ---
    # Par défaut, on prend la filiale de l'utilisateur
    target_filiale = getattr(user, 'filiale', None)
    
    # Si l'utilisateur est "Groupe", il peut choisir une autre filiale via GET
    if user.organe in user_groupe:
        f_get = request.GET.get('filiale')
        if f_get:
            target_filiale = f_get
    else:
        # SÉCURITÉ : On force sa propre filiale pour empêcher l'accès aux autres via l'URL
        target_filiale = user.filiale

    # --- 3. GESTION DE L'EXPLOITANT ---
    if user.organe == "Chargé Client":
        selected_expl = user.code_expl
    else:
        selected_expl = request.GET.get('expl')

    # --- 4. DONNÉES MOYENNES FILIALE ---
    latest_filiale_data = TauxEvolution_filiale.objects.filter(filiale=target_filiale).order_by('-date').first()
    
    if is_stock:
        last_pp_fil = latest_filiale_data.stock_PP if latest_filiale_data else 0
        last_pm_fil = latest_filiale_data.stock_PM if latest_filiale_data else 0
    else:
        last_pp_fil = latest_filiale_data.flux_PP if latest_filiale_data else 0
        last_pm_fil = latest_filiale_data.flux_PM if latest_filiale_data else 0

    # --- 5. DONNÉES HISTORIQUES EXPLOITANT ---
    base_qs_expl = TauxEvolution.objects.filter(
        flux_stock=code_flux_stock,
        filiale=target_filiale,
        expl=selected_expl
    ).order_by('date')

    dates_all = sorted(list(set(base_qs_expl.values_list('date', flat=True))))
    labels_chart = [d.strftime('%b %Y') for d in dates_all]
    labels_table = [d.strftime('%d/%m/%Y') for d in dates_all]

    dict_expl_pp = {obj.date: obj.taux for obj in base_qs_expl.filter(pp_pm="P")}
    dict_expl_pm = {obj.date: obj.taux for obj in base_qs_expl.filter(pp_pm="M")}

    data_expl_pp = [float(dict_expl_pp.get(d, 0)) for d in dates_all]
    data_expl_pm = [float(dict_expl_pm.get(d, 0)) for d in dates_all]

    # Calcul des Variations
    var_pp = round(data_expl_pp[-1] - data_expl_pp[-2], 2) if len(data_expl_pp) > 1 else 0
    var_pm = round(data_expl_pm[-1] - data_expl_pm[-2], 2) if len(data_expl_pm) > 1 else 0

    # --- 6. LISTE DYNAMIQUE DES EXPLOITANTS (Filtre intelligent) ---
    expl_queryset = TauxEvolution.objects.filter(filiale=target_filiale, flux_stock=code_flux_stock)

    if user.organe == "Directeur Agence":
        # On restreint aux agents de SON agence uniquement
        agents_de_lagence = ProfileV.objects.filter(filiale=user.filiale, agence=user.agence).values_list('code_expl', flat=True)
        expl_queryset = expl_queryset.filter(expl__in=agents_de_lagence)
    
    liste_expl = list(expl_queryset.values_list('expl', flat=True).distinct().order_by('expl'))
    profiles_by_expl = {
        p.code_expl: p
        for p in ProfileV.objects.filter(code_expl__in=liste_expl)
    }
    liste_expl_display = []
    for code in liste_expl:
        profile = profiles_by_expl.get(code)
        full_name = f"{getattr(profile, 'first_name', '')} {getattr(profile, 'last_name', '')}".strip() if profile else ""
        label = f"{code} - {full_name}" if full_name else code
        liste_expl_display.append({'code': code, 'label': label})

    # --- 7. NOTATION ET IDENTITÉ ---
    agent_info = ProfileV.objects.filter(filiale=target_filiale, code_expl=selected_expl).first()
    notation_obj = Notation.objects.filter( agent__code_expl=selected_expl, flux_stock=mode).order_by('-date_notation').first()

    # --- 8. LISTE DES FILIALES POUR LE SELECT ---
    if user.organe in user_groupe:
        liste_filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        # L'utilisateur ne voit que sa propre filiale dans la liste
        liste_filiales = [user.filiale] if user.filiale else []

    quality_scope = evaluate_data_quality_scope(user)
    if selected_expl:
        # Sur la page statistiques, les taux qualité doivent suivre l'agent sélectionné.
        quality_scope = {
            'filiale': target_filiale,
            'agence': getattr(agent_info, 'agence', None) if agent_info else None,
            'expl': selected_expl,
            'label': f"Agent {selected_expl}",
        }
    rules_version = cache.get('quality_control_rules_version', 1)

    def compute_quality_rate_by_typology(applicability):
        scope_signature = (
            f"{quality_scope.get('filiale')}|{quality_scope.get('agence')}|"
            f"{quality_scope.get('expl')}|{user.organe}|{applicability}"
        )
        scope_hash = hashlib.md5(scope_signature.encode('utf-8')).hexdigest()
        cache_key = f"quality_control:dashboard_rate:v{rules_version}:{scope_hash}"
        cached_rate = cache.get(cache_key)
        if cached_rate is not None:
            return cached_rate

        rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
        total_ok = 0
        total_evaluated = 0
        for rule in rules:
            stat = evaluate_data_quality_rule(
                rule,
                filiale=quality_scope.get('filiale'),
                agence=quality_scope.get('agence'),
                expl=quality_scope.get('expl'),
            )
            total_ok += stat.get('ok_count', 0)
            total_evaluated += stat.get('total', 0)

        rate = round(total_ok / total_evaluated * 100, 1) if total_evaluated else 0
        cache.set(cache_key, rate, timeout=3600)
        return rate

    quality_rate_pp = compute_quality_rate_by_typology('PP')
    quality_rate_pm = compute_quality_rate_by_typology('PM')

    context = {
        'mode': mode,
        'is_stock': is_stock,
        'selected_filiale': target_filiale,
        'selected_expl': selected_expl,
        'agent_nom': (
            (f"{agent_info.first_name} {agent_info.last_name}".strip() or agent_info.code_expl or agent_info.username)
            if agent_info else selected_expl
        ),
        'agent_note': notation_obj.note if notation_obj else "N/A",
        'labels_json': json.dumps(labels_chart),
        'data_expl_pp': json.dumps(data_expl_pp),
        'data_expl_pm': json.dumps(data_expl_pm),
        'last_pp_expl': data_expl_pp[-1] if data_expl_pp else 0,
        'last_pm_expl': data_expl_pm[-1] if data_expl_pm else 0,
        'last_pp_fil': last_pp_fil,
        'last_pm_fil': last_pm_fil,
        'var_pp': var_pp,
        'var_pm': var_pm,
        'historique': list(reversed(list(zip(labels_table, data_expl_pp, data_expl_pm)))),
        'liste_expl': liste_expl,
        'liste_expl_display': liste_expl_display,
        'user_groupe': user_groupe,
        'liste_filiales': liste_filiales,
        'quality_rate_pp': quality_rate_pp,
        'quality_rate_pm': quality_rate_pm,
        'quality_scope_label': quality_scope.get('label'),
    }
    return render(request, 'statistiques.html', context)
def export_stats_pp(request):
    # même logique de filtrage que dans la vue principale
    user = request.user
    organe = user.organe
    filiale = user.filiale
    expl_user = user.expl

    if organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                  "Contrôle Permanent Groupe", "PASS", "GUEST"]:
        qs = TauxEvolution.objects.all()
    elif organe in ["Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']:
        qs = TauxEvolution.objects.filter(filiale=filiale)
    elif organe == "Directeur Agence":
        qs = TauxEvolution.objects.filter(agence=user.agence)
    elif organe == "Chargé de client":
        qs = TauxEvolution.objects.filter(expl=expl_user)
    else:
        qs = TauxEvolution.objects.none()

    # filtrer éventuellement sur GET param
    selected_expl = request.GET.get('expl')
    if selected_expl:
        qs = qs.filter(expl=selected_expl)

    data = list(qs.values('filiale', 'agence', 'expl', 'date', 'taux'))
    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="rapport_taux.xlsx"'
    df.to_excel(response, index=False)
    return response


def daterev_ppe(request):
    # Rôles
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"]

    user = request.user

    # Params GET
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    base_qs = DATEREV.objects.all().filter(DATEREV__isnull=False, PPE='O')

    if getattr(user, "organe", "") == "Chargé Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        base_qs = base_qs.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass

    today = date.today()
    qs_period = base_qs
    if periode_param == "today":
        qs_period = qs_period.filter(DATEREV__lte=today)
    elif periode_param == "3m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=90))
    elif periode_param == "6m":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=180))
    elif periode_param == "1y":
        qs_period = qs_period.filter(DATEREV__gte=today, DATEREV__lte=today + timedelta(days=365))

    can_pick_filiale = user.organe in users_groupe

    selected_filiale = filiale_param if can_pick_filiale else getattr(user, "filiale", "")

    filiales_opts = qs_period.values_list("FILIALE", flat=True).distinct().order_by("FILIALE")

    qs_filiale = qs_period
    if selected_filiale:
        qs_filiale = qs_filiale.filter(FILIALE=selected_filiale)

    can_pick_agence = (user.organe in users_groupe) or (user.organe in users_filiale) or (
            user.organe == "Directeur Agence")

    if user.organe == "Directeur Agence":
        selected_agence = getattr(user, "agence", "")
    else:
        selected_agence = agence_param

    agences_opts = qs_filiale.values_list("AGENCE", flat=True).distinct().order_by("AGENCE")

    qs_agence = qs_filiale
    if selected_agence:
        qs_agence = qs_agence.filter(AGENCE=selected_agence)

    can_pick_expl = (user.organe in users_groupe) or (user.organe in users_filiale) or (
            user.organe == "Directeur Agence")

    if getattr(user, "organe", "") == "Chargé Client":
        selected_expl = getattr(user, "code_expl", "")
    else:
        selected_expl = expl_param

    exploitants_opts = qs_agence.values_list("EXPL", flat=True).distinct().order_by("EXPL")

    donnees = qs_agence
    if selected_expl:
        donnees = donnees.filter(EXPL=selected_expl)
    count_risque_non_eleve = donnees.exclude(RISQUE="Risque eleve").count()

    context = {
        "donnees": donnees.order_by("FILIALE", "AGENCE", "EXPL", "CLIENT"),
        "total_count": donnees.count(), # Optionnel : le total général
        "count_risque_non_eleve": count_risque_non_eleve, # Le nouveau décompte
        # Options
        "filiales": filiales_opts,
        "agences": agences_opts,
        "exploitants": exploitants_opts,

        # Sélections courantes
        "periode": periode_param,
        "filiale_param": selected_filiale,
        "agence_param": selected_agence,
        "expl_param": selected_expl,

        # Rôles (si tu en as besoin dans le template)
        "users_groupe": users_groupe,
        "users_filiale": users_filiale,

        # Droits d'édition des selects
        "can_pick_filiale": can_pick_filiale,
        "can_pick_agence": can_pick_agence,
        "can_pick_expl": can_pick_expl,
    }
    return render(request, 'daterev_ppe.html', context)


def non_anom_ppe(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    donnees = Anomalie.objects.filter(PPE="O")
    # Filtrage automatique selon le rôle
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    if user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    if user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    if user.organe in users_groupe:
        donnees = donnees

    # Filtres manuels via GET
    if filiale_param:
        donnees = donnees.filter(FILIALE=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL=expl_param)

    # === Valeurs du formulaire selon le rôle ===
    if user.organe == "Directeur Agence":
        exploitants = Anomalie.objects.filter(AGENCE=user.agence).values_list('EXPL', flat=True).distinct()
        agences = Anomalie.objects.filter(AGENCE=user.agence).values_list('AGENCE', flat=True).distinct()
    elif user.organe in users_filiale:
        agences = Anomalie.objects.filter(FILIALE=user.filiale).values_list('AGENCE', flat=True).distinct()
        exploitants = Anomalie.objects.filter(FILIALE=user.filiale).values_list('EXPL', flat=True).distinct()
    else:
        exploitants = Anomalie.objects.values_list('EXPL', flat=True).distinct()
        agences = Anomalie.objects.values_list('AGENCE', flat=True).distinct()

    filiales = Anomalie.objects.values_list('FILIALE', flat=True).distinct()

    context = {
        'donnees': donnees,
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
    }

    return render(request, 'anom_ppe.html', context)

from django.shortcuts import render
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db.models import Max
from .models import Anomalie, Notation

def non_anom(request):
    user = request.user
    users_filiale = ["DSI", "Conformit??", "Contr??le Permanent", "Directeur R??seau",'Risques', 'DAI', 'Qualit??']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "Conformit?? Groupe", "Contr??le Permanent Groupe", "PASS", "GUEST"]

    # ???????????????????????????????????????????????????????????????
    # 1. Notation (champ Flux)
    # ???????????????????????????????????????????????????????????????
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    if hasattr(user, 'filiale') and hasattr(user, 'code_expl'):
        notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)

    # ???????????????????????????????????????????????????????????????
    # 2. Base Queryset des anomalies
    # ???????????????????????????????????????????????????????????????
    queryset = Anomalie.objects.all()

    # ???????????????????????????????????????????????????????????????
    # 3. Filtres GET
    # ???????????????????????????????????????????????????????????????
    filiale_filter = request.GET.get("filiale")
    agence_filter = request.GET.get("agence")
    expl_filter = request.GET.get("expl")

    filiale_txt = request.GET.get("filiale_txt")
    agence_txt = request.GET.get("agence_txt")
    expl_txt = request.GET.get("expl_txt")
    lib_agence = request.GET.get("lib_agence")
    client = request.GET.get("client")

    anom_age = request.GET.get("anom_age")
    anom_eer = request.GET.get("anom_eer")
    anom_cin = request.GET.get("anom_cin")

    filiale_list = []
    agence_list = []
    expl_list = []

    # ???????????????????????????????????????????????????????????????
    # 4. Filtrage selon r??le
    # ???????????????????????????????????????????????????????????????

    if user.organe == "Charg?? Client":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)
        agence_list = Anomalie.objects.filter(FILIALE=user.filiale).values_list("AGENCE", flat=True).distinct()
        if expl_filter:
            queryset = queryset.filter(EXPL=expl_filter)
            expl_list = Anomalie.objects.filter(AGENCE=user.agence).values_list("EXPL", flat=True).distinct()

    elif user.organe in users_filiale:
        queryset = queryset.filter(FILIALE=user.filiale)
        filiale_list = [user.filiale]
        agence_list = Anomalie.objects.filter(FILIALE=user.filiale).values_list("AGENCE", flat=True).distinct()
        if agence_filter:
            queryset = queryset.filter(AGENCE=agence_filter)
            expl_list = Anomalie.objects.filter(AGENCE=agence_filter).values_list("EXPL", flat=True).distinct()
        if expl_filter:
            queryset = queryset.filter(EXPL=expl_filter)

    elif user.organe in users_groupe:
        filiale_list = Anomalie.objects.values_list("FILIALE", flat=True).distinct()
        if filiale_filter:
            queryset = queryset.filter(FILIALE=filiale_filter)
            agence_list = Anomalie.objects.filter(FILIALE=filiale_filter).values_list("AGENCE", flat=True).distinct()
        if agence_filter:
            queryset = queryset.filter(AGENCE=agence_filter)
            expl_list = Anomalie.objects.filter(AGENCE=agence_filter).values_list("EXPL", flat=True).distinct()
        if expl_filter:
            queryset = queryset.filter(EXPL=expl_filter)

    # Filtres texte (colonnes)
    if filiale_txt:
        queryset = queryset.filter(FILIALE__icontains=filiale_txt)
    if agence_txt:
        queryset = queryset.filter(AGENCE__icontains=agence_txt)
    if expl_txt:
        queryset = queryset.filter(EXPL__icontains=expl_txt)
    if lib_agence:
        queryset = queryset.filter(LIB_AGENCE__icontains=lib_agence)
    if client:
        queryset = queryset.filter(CLIENT__icontains=client)

    # Options pour listes d??roulantes (avant filtre anomalie)
    opts_qs = queryset
    anom_age_opts = opts_qs.exclude(ANOMALIE_AGE__isnull=True).exclude(ANOMALIE_AGE="").values_list(
        "ANOMALIE_AGE", flat=True).distinct().order_by("ANOMALIE_AGE")
    anom_eer_opts = opts_qs.exclude(ANOMALIE_DATE_EER__isnull=True).exclude(ANOMALIE_DATE_EER="").values_list(
        "ANOMALIE_DATE_EER", flat=True).distinct().order_by("ANOMALIE_DATE_EER")
    anom_cin_opts = opts_qs.exclude(ANOMALIE_CIN__isnull=True).exclude(ANOMALIE_CIN="").values_list(
        "ANOMALIE_CIN", flat=True).distinct().order_by("ANOMALIE_CIN")

    # Filtres anomalies (via select)
    if anom_age:
        queryset = queryset.filter(ANOMALIE_AGE=anom_age)
    if anom_eer:
        queryset = queryset.filter(ANOMALIE_DATE_EER=anom_eer)
    if anom_cin:
        queryset = queryset.filter(ANOMALIE_CIN=anom_cin)

    # ???????????????????????????????????????????????????????????????
    # 5. Pagination
    # ???????????????????????????????????????????????????????????????
    queryset = queryset.order_by('CLIENT')

    ITEMS_PER_PAGE = 50
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        objets_page = paginator.page(1)
    except EmptyPage:
        objets_page = paginator.page(paginator.num_pages)

    context = {
        "donnees": objets_page,
        "filiale_list": filiale_list,
        "agence_list": agence_list,
        "expl_list": expl_list,
        "users_groupe": users_groupe,
        "users_filiale": users_filiale,
        "notation": notation,
        "anom_age_opts": anom_age_opts,
        "anom_eer_opts": anom_eer_opts,
        "anom_cin_opts": anom_cin_opts,
        "anom_age": anom_age,
        "anom_eer": anom_eer,
        "anom_cin": anom_cin,
    }

    return render(request, "non_anom.html", context)
def devise(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau", 'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]

    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 1. Récupérer LA devise de la filiale (on prend la première trouvée)
    # On récupère juste la valeur (ex: "XOF") pour la comparer aux données Kyc_pp
    devise_obj = Devise.objects.filter(filiale=user.filiale).first()
    devise_valeur = devise_obj.devise if devise_obj else None  # Remplacez 'nom_devise' par le nom réel de votre champ

    # 2. Filtrage de base : Exclure la devise de la filiale et les vides
    donnees = Kyc_pp.objects.exclude(DEVISE=devise_valeur).exclude(DEVISE__isnull=True).exclude(DEVISE="")

    # === Filtrage automatique selon le rôle ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    # Si dans users_groupe, on garde tout (déjà géré par l'absence de filtre)

    # === Filtres manuels via GET ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    donnees = _apply_pp_header_filters(donnees, request, include_devise=True)

    # === Valeurs pour les menus déroulants du formulaire ===
    filiales = donnees.values_list('FILIALE', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()
    exploitants = donnees.values_list('EXPL', flat=True).distinct()
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    # === Paginator ===
    ITEMS_PER_PAGE = 25
    paginator = Paginator(donnees, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        objets_page = paginator.page(1)
    except EmptyPage:
        objets_page = paginator.page(paginator.num_pages)

    context = {
        "donnees": objets_page,
        "devise_filiale": devise_valeur,  # Utile pour l'affichage dans le template
        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
        'get_params': query_params.urlencode(),
    }

    return render(request, 'devise.html', context)


def export_devise_pp(request):
    user = request.user

    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupération des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Début du Queryset
    donnees = Kyc_pp.objects.filter(~Q(DEVISE=""), DEVISE__isnull=False)

    # === Filtrage automatique selon le rôle (identique à devise) ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # on ne filtre pas davantage

    # === Filtres manuels via GET (synchronisation) ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    donnees = _apply_pp_header_filters(donnees, request, include_devise=True)

    # Fin du Queryset filtré

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommé le titre

    # Entêtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP", "PAYNAIS", "PROFESSION", "ADRESSE", "PAYS_RESID",
               "NUMID", "SALAIRE", "ORIGINE_REV", "DATVALID", "TEL"]
    ws.append(headers)

    # Données
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
            d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID, d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Comptes_en_devise_PP_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def devise_pm(request):
    roles_exclus = ["Chargé Client"]
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "Conformité Groupe", "Contrôle Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # =========================================================================
    # 🌟 CORRECTION PRINCIPALE ICI 🌟
    # On filtre pour exclure les enregistrements où DEVISE est vide OU NULL.
    # Ceci revient à dire : DEVISE N'EST PAS vide ET DEVISE N'EST PAS NULL.
    # =========================================================================
    donnees = Kyc_pm.objects.filter(~Q(DEVISE="") & Q(DEVISE__isnull=False))
    # Alternative plus concise si DEVISE est un CharField :
    # donnees = Kyc_pp.objects.exclude(DEVISE="").exclude(DEVISE__isnull=True)

    # === Filtrage automatique selon le rôle ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # on ne filtre pas davantage

    # === Filtres manuels via GET ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # === Valeurs du formulaire selon le rôle ===
    # Ceci doit être recalculé après l'application des filtres pour avoir les listes pertinentes

    # Simuler les listes pour le contexte
    filiales = donnees.values_list('FILIALE', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()
    exploitants = donnees.values_list('EXPL', flat=True).distinct()

    # 2. Obtenir le QuerySet filtré
    # Utilisation de 'donnees' qui contient déjà le QuerySet filtré.
    queryset = donnees

    # 3. Appliquer le Paginator
    # Je vais simuler ITEMS_PER_PAGE pour l'exemple
    ITEMS_PER_PAGE = 25
    paginator = Paginator(queryset, ITEMS_PER_PAGE)

    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la première page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la dernière page
        objets_page = paginator.page(paginator.num_pages)

    context = {
        # 'donnees' est maintenant l'objet Page paginé
        "donnees": objets_page,

        'filiales': filiales,
        'agences': agences,
        'exploitants': exploitants,
        'roles_exclus': roles_exclus,
        'users_groupe': users_groupe,
        'users_filiale': users_filiale,
    }

    return render(request, 'devise_pm.html', context)


def export_devise_pm(request):
    user = request.user

    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "Conformité Groupe",
                    "Contrôle Permanent Groupe", "PASS", "GUEST"]

    # Récupération des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')


    devise_obj = Devise.objects.filter(filiale=user.filiale).first()
    devise_valeur = devise_obj.devise if devise_obj else None  # Remplacez 'nom_devise' par le nom réel de votre champ

    # 2. Filtrage de base : Exclure la devise de la filiale et les vides
    donnees = Kyc_pm.objects.exclude(DEVISE=devise_valeur).exclude(DEVISE__isnull=True).exclude(DEVISE="")

    # === Filtrage automatique selon le rôle (identique à devise) ===
    if user.organe == "Chargé Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # on ne filtre pas davantage

    # === Filtres manuels via GET (synchronisation) ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # Fin du Queryset filtré

    # Création du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommé le titre

    # Entêtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "AGEC", "CODAPE", "IDM", "RCSNO", "CAPITAL", "CA",
               "RESULTAT", "TEL"]
    ws.append(headers)

    # Données
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.AGEC, d.CODAPE, d.IDM,
            d.RCSNO, d.CAPITAL, d.CA, d.RESULTAT, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # Préparer la réponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Comptes_en_devise_PM_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def evolution_taux(request):
    user = request.user

    context = {}

    if user.organe == "Conformité Groupe":
        # Groupe : on récupère toutes les filiales distinctes
        filiales = TauxEvolution_filiale.objects.values_list("filiale", flat=True).distinct()
        data_filiales = {}

        for filiale in filiales:
            qs = TauxEvolution_filiale.objects.filter(filiale=filiale).order_by("id")

            dates = [str(i.id) for i in qs]  # tu peux remplacer par une vraie date si tu en ajoutes une
            taux_pp = [round((t.flux_PP / t.stock_PP) * 100, 2) if t.stock_PP else 0 for t in qs]
            taux_pm = [round((t.flux_PM / t.stock_PM) * 100, 2) if t.stock_PM else 0 for t in qs]

            data_filiales[filiale] = {
                "dates": dates,
                "taux_pp": taux_pp,
                "taux_pm": taux_pm,
            }

        context["data_filiales"] = data_filiales

    elif user.organe == "Conformité":
        # Filiale : uniquement sa propre
        qs = TauxEvolution_filiale.objects.filter(filiale=user.filiale).order_by("id")

        dates = [str(i.id) for i in qs]  # pareil, si tu as un champ Date, utilise-le
        taux_pp = [round((t.flux_PP / t.stock_PP) * 100, 2) if t.stock_PP else 0 for t in qs]
        taux_pm = [round((t.flux_PM / t.stock_PM) * 100, 2) if t.stock_PM else 0 for t in qs]

        context.update({
            "filiale": user.filiale,
            "dates_pp": dates,
            "taux_pp": taux_pp,
            "dates_pm": dates,
            "taux_pm": taux_pm,
        })

    return render(request, "statistiques.html", context)



@login_required
def taux_evolution_view(request):
    user = request.user

    # Définition des accès selon votre logique
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']

    filiale_sel = request.GET.get('filiale')

    # Filtrage des filiales autorisées
    if user.organe in users_filiale:
        filiales = TauxEvolution_filiale.objects.filter(filiale=user.filiale) \
            .values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True) \
            .distinct().order_by('filiale')

    if not filiale_sel and filiales:
        filiale_sel = filiales[0]

    # Récupération des données
    qs = TauxEvolution_filiale.objects.filter(filiale=filiale_sel).order_by('date')

    labels = [obj.date.strftime('%Y-%m-%d') for obj in qs]
    data_pm = [obj.flux_PM or 0 for obj in qs]
    data_pp = [obj.flux_PP or 0 for obj in qs]

    # Calcul des KPIs (Dernier vs Avant-dernier)
    kpi_pm = {'last': 0, 'diff': 0, 'status': 'up'}
    kpi_pp = {'last': 0, 'diff': 0, 'status': 'up'}

    if len(data_pm) >= 1:
        kpi_pm['last'] = round(data_pm[-1], 2)
        if len(data_pm) >= 2:
            kpi_pm['diff'] = round(data_pm[-1] - data_pm[-2], 2)
            kpi_pm['status'] = 'up' if kpi_pm['diff'] >= 0 else 'down'

    if len(data_pp) >= 1:
        kpi_pp['last'] = round(data_pp[-1], 2)
        if len(data_pp) >= 2:
            kpi_pp['diff'] = round(data_pp[-1] - data_pp[-2], 2)
            kpi_pp['status'] = 'up' if kpi_pp['diff'] >= 0 else 'down'

    quality_scope = evaluate_data_quality_scope(user)
    rules_version = cache.get('quality_control_rules_version', 1)

    def compute_quality_rate_by_typology(applicability):
        scope_signature = (
            f"{quality_scope.get('filiale')}|{quality_scope.get('agence')}|"
            f"{quality_scope.get('expl')}|{user.organe}|{applicability}|evolution_filiale"
        )
        scope_hash = hashlib.md5(scope_signature.encode('utf-8')).hexdigest()
        cache_key = f"quality_control:evolution_rate:v{rules_version}:{scope_hash}"
        cached_rate = cache.get(cache_key)
        if cached_rate is not None:
            return cached_rate

        rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
        total_ok = 0
        total_evaluated = 0
        for rule in rules:
            stat = evaluate_data_quality_rule(
                rule,
                filiale=quality_scope.get('filiale'),
                agence=quality_scope.get('agence'),
                expl=quality_scope.get('expl'),
            )
            total_ok += stat.get('ok_count', 0)
            total_evaluated += stat.get('total', 0)

        rate = round(total_ok / total_evaluated * 100, 1) if total_evaluated else 0
        cache.set(cache_key, rate, timeout=3600)
        return rate

    context = {
        'labels_json': json.dumps(labels),
        'data_pm_json': json.dumps(data_pm),
        'data_pp_json': json.dumps(data_pp),
        'filiales': list(filiales),
        'filiale_sel': filiale_sel,
        'kpi_pm': kpi_pm,
        'kpi_pp': kpi_pp,
        'quality_rate_pp': compute_quality_rate_by_typology('PP'),
        'quality_rate_pm': compute_quality_rate_by_typology('PM'),
        'quality_scope_label': quality_scope.get('label'),
        'queryset': qs.reverse()[:10],  # 10 derniers pour le tableau
    }
    return render(request, 'evolution_par_filiale.html', context)


@login_required
def taux_evolution_view_stock(request):
    user = request.user

    # Définition des accès selon votre logique
    users_filiale = ["DSI", "Conformité", "Contrôle Permanent", "Directeur Réseau",'Risques', 'DAI', 'Qualité']

    filiale_sel = request.GET.get('filiale')

    # Filtrage des filiales autorisées
    if user.organe in users_filiale:
        filiales = TauxEvolution_filiale.objects.filter(filiale=user.filiale) \
            .values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True) \
            .distinct().order_by('filiale')

    if not filiale_sel and filiales:
        filiale_sel = filiales[0]

    # Récupération des données
    qs = TauxEvolution_filiale.objects.filter(filiale=filiale_sel).order_by('date')

    labels = [obj.date.strftime('%Y-%m-%d') for obj in qs]
    data_pm = [obj.stock_PM or 0 for obj in qs]
    data_pp = [obj.stock_PP or 0 for obj in qs]

    # Calcul des KPIs (Dernier vs Avant-dernier)
    kpi_pm = {'last': 0, 'diff': 0, 'status': 'up'}
    kpi_pp = {'last': 0, 'diff': 0, 'status': 'up'}

    if len(data_pm) >= 1:
        kpi_pm['last'] = round(data_pm[-1], 2)
        if len(data_pm) >= 2:
            kpi_pm['diff'] = round(data_pm[-1] - data_pm[-2], 2)
            kpi_pm['status'] = 'up' if kpi_pm['diff'] >= 0 else 'down'

    if len(data_pp) >= 1:
        kpi_pp['last'] = round(data_pp[-1], 2)
        if len(data_pp) >= 2:
            kpi_pp['diff'] = round(data_pp[-1] - data_pp[-2], 2)
            kpi_pp['status'] = 'up' if kpi_pp['diff'] >= 0 else 'down'

    quality_scope = evaluate_data_quality_scope(user)
    rules_version = cache.get('quality_control_rules_version', 1)

    def compute_quality_rate_by_typology(applicability):
        scope_signature = (
            f"{quality_scope.get('filiale')}|{quality_scope.get('agence')}|"
            f"{quality_scope.get('expl')}|{user.organe}|{applicability}|evolution_filiale_stock"
        )
        scope_hash = hashlib.md5(scope_signature.encode('utf-8')).hexdigest()
        cache_key = f"quality_control:evolution_stock_rate:v{rules_version}:{scope_hash}"
        cached_rate = cache.get(cache_key)
        if cached_rate is not None:
            return cached_rate

        rules = list(DataQualityRule.objects.filter(active=True, applicability=applicability))
        total_ok = 0
        total_evaluated = 0
        for rule in rules:
            stat = evaluate_data_quality_rule(
                rule,
                filiale=quality_scope.get('filiale'),
                agence=quality_scope.get('agence'),
                expl=quality_scope.get('expl'),
            )
            total_ok += stat.get('ok_count', 0)
            total_evaluated += stat.get('total', 0)

        rate = round(total_ok / total_evaluated * 100, 1) if total_evaluated else 0
        cache.set(cache_key, rate, timeout=3600)
        return rate

    context = {
        'labels_json': json.dumps(labels),
        'data_pm_json': json.dumps(data_pm),
        'data_pp_json': json.dumps(data_pp),
        'filiales': list(filiales),
        'filiale_sel': filiale_sel,
        'kpi_pm': kpi_pm,
        'kpi_pp': kpi_pp,
        'quality_rate_pp': compute_quality_rate_by_typology('PP'),
        'quality_rate_pm': compute_quality_rate_by_typology('PM'),
        'quality_scope_label': quality_scope.get('label'),
        'queryset': qs.reverse()[:10],  # 10 derniers pour le tableau
    }
    return render(request, 'evolution_par_filiale_stock.html', context)


import csv
import io
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required

User = get_user_model()


@login_required
def bulk_user_upload(request):
    if request.method == "POST":
        csv_file = request.FILES.get('file')

        if not csv_file or not csv_file.name.endswith('.csv'):
            messages.error(request, "Veuillez sélectionner un fichier CSV valide.")
            return redirect('bulk_user_upload')

        try:
            # Lecture du fichier
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            next(io_string)  # Sauter l'en-tête

            users_created = 0
            errors = 0

            for row in csv.reader(io_string, delimiter=',', quotechar='"'):
                # row[0]=username, row[1]=first_name, row[2]=last_name, etc.
                # Adaptez les index selon l'ordre de vos colonnes CSV
                try:
                    user, created = User.objects.get_or_create(
                        username=row[0],
                        defaults={
                            'first_name': row[1],
                            'last_name': row[2],
                            'organe': row[3],
                            'téléphone': row[4],
                            'agence': row[6],
                            'code_expl': row[7],
                        }
                    )
                    if created:
                        user.set_password(row[5])  # password1
                        user.save()
                        users_created += 1
                except Exception:
                    errors += 1
                    continue

            messages.success(request, f"{users_created} utilisateurs créés avec succès. ({errors} erreurs)")

        except Exception as e:
            messages.error(request, f"Erreur lors du traitement : {e}")

    return render(request, 'bulk_upload.html')


from openpyxl import Workbook
from django.http import HttpResponse


def download_excel_template(request):
    # Création d'un nouveau classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Import Utilisateurs"

    # En-têtes conformes à votre script
    headers = ['username', 'first_name', 'last_name', 'organe', 'téléphone', 'password', 'agence', 'expl']
    ws.append(headers)

    # Exemple de données
    ws.append(['m.diop', 'Moussa', 'Diop', 'Conformité', '771234567', 'Boa2026!', 'Agence Dakar', 'EXPL001'])

    # Préparation de la réponse HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="template_kyc_bulk.xlsx"'

    wb.save(response)
    return response





