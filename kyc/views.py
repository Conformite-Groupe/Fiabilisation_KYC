from django.core.paginator import Paginator
from django.db import close_old_connections, models
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
    DataQualityRule, DataQualityRuleAudit, KycDocumentExtraction, KycExpiredDocumentScanMatch,
    KycDocumentMatchJob, KycDocumentMatchSettings, DOCUMENT_EXTRACTION_TYPE_CHOICES,
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
import threading
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
    """DÃ©termine le pÃ©rimÃ¨tre de calcul qualitÃ© selon l'organe utilisateur."""
    organe = (getattr(user, 'organe', '') or '').strip()
    filiale = (getattr(user, 'filiale', '') or '').strip()
    agence = (getattr(user, 'agence', '') or '').strip()
    code_expl = (getattr(user, 'code_expl', '') or '').strip()

    if organe == 'ChargÃ© Client':
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
        return {'total': 0, 'fail_count': 0, 'ok_count': 0, 'clients': [], 'message': 'Champ de contrÃ´le invalide'}

    queryset = model.objects.all()
    if filiale and filiale != 'GROUPE':
        queryset = queryset.filter(FILIALE=filiale)
    if agence:
        queryset = queryset.filter(AGENCE=agence)
    if expl:
        queryset = queryset.filter(EXPL=expl)
        
    total = queryset.count()
    if total == 0:
        return {'total': 0, 'fail_count': 0, 'ok_count': 0, 'clients': [], 'message': 'Aucune donnÃ©e disponible pour ce segment'}

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
                return {'total': total, 'fail_count': 0, 'ok_count': total, 'clients': [], 'message': 'ParamÃ¨tre de longueur invalide'}
        
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
                    try: match = len(val) < int(target) # C'est un Ã©chec si la longueur est infÃ©rieure au min
                    except: match = False
                elif op == 'max_length':
                    try: match = len(val) > int(target) # C'est un Ã©chec si la longueur est supÃ©rieure au max
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
                        'field_value': 'Multi-critÃ¨res',
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
    allowed_organs = ['ContrÃ´le Permanent', 'ConformitÃ©', 'QualitÃ©', 'DSI', 'Risques', 'DAI', 'PASS']
    user_organe = (getattr(user, 'organe', '') or '').strip()
    if user_organe not in allowed_organs:
        messages.error(request, "AccÃ¨s non autorisÃ© au contrÃ´le qualitÃ©.")
        return redirect('accueil')

    from kyc.forms import DataQualityRuleForm, DataQualityConditionFormSet

    # VÃ©rification des droits de gestion
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    can_manage = user_organe in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']
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
                details=f"CrÃ©ation de la rÃ¨gle '{rule.name}' ({rule.applicability})"
            )
            
            current_version = cache.get('quality_control_rules_version', 1)
            cache.set('quality_control_rules_version', current_version + 1, timeout=None)
            messages.success(request, 'RÃ¨gle de qualitÃ© enregistrÃ©e.')
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
    
    # PortÃ©e de l'Ã©valuation : vision groupe pour PASS et les organes Groupe
    group_organs = ['PASS', 'ConformitÃ© Groupe']
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
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    if user_organe not in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']:
        messages.error(request, "AccÃ¨s refusÃ©.")
        return redirect('kyc:quality_control')
        
    rule = get_object_or_404(DataQualityRule, pk=pk)
    
    # VÃ©rification filiale si pas PASS
    if user_organe != 'PASS' and rule.created_by and rule.created_by.filiale != request.user.filiale:
        messages.error(request, "Vous ne pouvez supprimer que les rÃ¨gles de votre filiale.")
        return redirect('kyc:quality_control')

    rule_name = rule.name
    DataQualityRuleAudit.objects.create(
        rule_name=rule_name,
        user=request.user,
        action='SUPPRESSION',
        details=f"Suppression de la rÃ¨gle '{rule_name}'"
    )
    
    rule.delete()
    current_version = cache.get('quality_control_rules_version', 1)
    cache.set('quality_control_rules_version', current_version + 1, timeout=None)
    messages.success(request, f"RÃ¨gle '{rule_name}' supprimÃ©e.")
    return redirect('kyc:quality_control')

@login_required
def edit_quality_rule(request, pk):
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    if user_organe not in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']:
        messages.error(request, "AccÃ¨s refusÃ©.")
        return redirect('kyc:quality_control')
        
    rule = get_object_or_404(DataQualityRule, pk=pk)
    
    # VÃ©rification filiale si pas PASS
    if user_organe != 'PASS' and rule.created_by and rule.created_by.filiale != request.user.filiale:
        messages.error(request, "Vous ne pouvez modifier que les rÃ¨gles de votre filiale.")
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
            messages.success(request, "RÃ¨gle mise Ã  jour.")
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
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    if user_organe not in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']:
        messages.error(request, "AccÃ¨s refusÃ©.")
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
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    if user_organe not in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']:
        return HttpResponseForbidden()
        
    if user_organe == 'PASS':
        audits = DataQualityRuleAudit.objects.all().order_by('-timestamp')
    else:
        audits = DataQualityRuleAudit.objects.filter(
            Q(user__filiale=request.user.filiale) | Q(user__isnull=True)
        ).order_by('-timestamp')
        
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Audit des ContrÃ´les"
    ws.append(["Date & Heure", "Utilisateur", "RÃ¨gle", "Action", "DÃ©tails"])
    for audit in audits:
        ws.append([audit.timestamp.strftime("%d/%m/%Y %H:%M:%S"), audit.user.username if audit.user else "System", audit.rule_name, audit.action, audit.details])
    response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = 'attachment; filename=audit_controles.xlsx'
    wb.save(response)
    return response

@login_required
def export_audits_pdf(request):
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    if user_organe not in ['ConformitÃ©', 'ContrÃ´le Permanent', 'PASS']:
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
        return HttpResponse("L'exportation PDF n'est pas disponible sur ce serveur (dÃ©pendances manquantes).")
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=_pdf_link_callback)
    if pisa_status.err: return HttpResponse('Erreur PDF')
    return response

@login_required
def export_rule_failures(request, rule_id):
    rule = get_object_or_404(DataQualityRule, pk=rule_id)
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    user_filiale = getattr(request.user, 'filiale', '')
    
    # PortÃ©e de l'Ã©valuation
    group_organs = ['PASS', 'ConformitÃ© Groupe']
    eval_filiale = None if user_organe in group_organs else user_filiale
    
    # Re-Ã©valuer pour obtenir TOUS les Ã©checs (sans limite de 15)
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
    # RÃ©cupÃ©rer les rÃ¨gles avec la mÃªme logique que la vue principale
    user_organe = (getattr(request.user, 'organe', '') or '').strip()
    user_filiale = getattr(request.user, 'filiale', '')
    group_organs = ['PASS', 'ConformitÃ© Groupe']
    
    if user_organe == 'PASS':
        rules_qs = DataQualityRule.objects.all().order_by('-created_at')
    elif user_organe in ['ConformitÃ© Groupe']:
        rules_qs = DataQualityRule.objects.all().order_by('-created_at')
    else:
        # Filtrer par filiale
        rules_qs = DataQualityRule.objects.filter(
            Q(created_by__filiale=user_filiale) | Q(created_by__isnull=True)
        ).order_by('-created_at')

    # Ã‰valuation avec CACHE pour la rapiditÃ©
    import hashlib
    from django.core.cache import cache
    
    rules_with_stats = []
    eval_filiale = None if user_organe in group_organs else user_filiale
    rules_version = cache.get('quality_control_rules_version', 1)
    cache_ttl = 86400
    data_refresh_bucket = timezone.localdate().isoformat()

    for rule in rules_qs:
        # Signature identique Ã  la vue principale pour rÃ©utiliser le cache
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
        return HttpResponse("L'exportation PDF n'est pas disponible sur ce serveur (dÃ©pendances manquantes).")
        
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=_pdf_link_callback)
    if pisa_status.err:
        return HttpResponse('Erreur lors de la gÃ©nÃ©ration du PDF')
        
    return response


@login_required
def accueil(request):
    user = request.user

    if user.is_authenticated:
        if user.organe == "ChargÃ© Client":
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
                    # Invalider le cache des rÃ¨gles de qualitÃ© aprÃ¨s un import rÃ©ussi
                    current_v = cache.get('quality_control_rules_version', 1)
                    cache.set('quality_control_rules_version', current_v + 1, timeout=None)
                    messages.success(request, "Import terminÃ© avec succÃ¨s.")
                else:
                    messages.error(request, f"Import Ã©chouÃ© (code {result.returncode}).")

            except Exception as e:
                messages.error(request, f"Erreur d'exÃ©cution: {e}")

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


def _values_match(left, right):
    left_value = _normalize_match_value(left)
    right_value = _normalize_match_value(right)
    return bool(left_value and right_value and left_value == right_value)


def _date_values_match(left, right):
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text or not right_text:
        return False

    left_formatted = format_date_for_export(left_text, empty_value="")
    right_formatted = format_date_for_export(right_text, empty_value="")
    if left_formatted and right_formatted and _normalize_match_value(left_formatted) == _normalize_match_value(right_formatted):
        return True

    return _normalize_match_value(left_text) == _normalize_match_value(right_text)


def _date_match_key(value):
    formatted = format_date_for_export(value, empty_value="")
    return _normalize_match_value(formatted or value)


def _nationality_match_key(value):
    return _country_key(value) or _normalize_match_value(value)


def _nationality_values_match(document_value, client_value):
    if not document_value or not client_value:
        return False
    if _countries_are_compatible(document_value, client_value):
        return True
    return _normalize_match_value(document_value) == _normalize_match_value(client_value)


DEFAULT_KYC_DOCUMENT_MATCH_WEIGHTS = {
    "birth_date_weight": 35,
    "document_validity_weight": 35,
    "birth_place_weight": 10,
    "nationality_weight": 30,
    "combination_threshold": 65,
}


def _get_kyc_document_match_weights():
    try:
        settings_obj = KycDocumentMatchSettings.get_active()
        return {
            "birth_date_weight": settings_obj.birth_date_weight,
            "document_validity_weight": settings_obj.document_validity_weight,
            "birth_place_weight": settings_obj.birth_place_weight,
            "nationality_weight": settings_obj.nationality_weight,
            "combination_threshold": settings_obj.combination_threshold,
        }
    except Exception:
        return DEFAULT_KYC_DOCUMENT_MATCH_WEIGHTS.copy()


def _document_client_identity_score(document, client, weights=None):
    weights = weights or DEFAULT_KYC_DOCUMENT_MATCH_WEIGHTS
    client_numid = getattr(client, "NUMID", "")
    if _values_match(document.numero_identification_nationale, client_numid) or _values_match(document.numero_document, client_numid):
        return 100

    score = 0
    checks = [
        (_date_values_match(document.date_naissance, getattr(client, "DATNAIS", "")), weights["birth_date_weight"]),
        (_date_values_match(document.date_expiration, getattr(client, "DATVALID", "")), weights["document_validity_weight"]),
        (_nationality_values_match(document.lieu_naissance, getattr(client, "PAYNAIS", "")), weights["birth_place_weight"]),
        (
            _nationality_values_match(document.nationalite, getattr(client, "PAYNAIS", ""))
            or _nationality_values_match(document.pays_naissance, getattr(client, "PAYNAIS", "")),
            weights["nationality_weight"],
        ),
    ]
    for matched, weight in checks:
        if matched:
            score += weight
    return score


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


def _build_kyc_pp_document_matches(document_queryset, limit=3000, result_limit=200, progress_callback=None):
    documents_for_match = list(document_queryset.order_by("-created_at")[:limit])
    if not documents_for_match:
        return [], {"documents_checked": 0, "documents_matched": 0, "clients_matched": 0, "suggestions_count": 0, "match_rate": 0}
    if progress_callback:
        progress_callback(0, len(documents_for_match), "Preparation du rapprochement")
    match_weights = _get_kyc_document_match_weights()

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
    clients_by_birth_date = {}
    clients_by_validity_date = {}
    clients_by_nationality = {}
    clients_by_birth_place = {}
    for client in Kyc_pp.objects.only(
        "id", "FILIALE", "AGENCE", "CLIENT", "IDP", "NUMID", "DATNAIS", "PAYNAIS", "DATVALID", "ADRESSE", "ORIGINE_REV"
    )[:50000]:
        normalized_client = _normalize_match_value(client.CLIENT)
        if normalized_client:
            client_by_code.setdefault(normalized_client, []).append(client)
        birth_key = _date_match_key(client.DATNAIS)
        if birth_key:
            clients_by_birth_date.setdefault(birth_key, []).append(client)
        validity_key = _date_match_key(client.DATVALID)
        if validity_key:
            clients_by_validity_date.setdefault(validity_key, []).append(client)
        nationality_key = _nationality_match_key(client.PAYNAIS)
        if nationality_key:
            clients_by_nationality.setdefault(nationality_key, []).append(client)
            clients_by_birth_place.setdefault(nationality_key, []).append(client)

    matches = []
    client_match_index = {}
    matched_client_ids = set()
    matched_document_ids = set()
    for index, document in enumerate(documents_for_match, start=1):
        if progress_callback:
            progress_callback(index, len(documents_for_match), f"Analyse document {index}/{len(documents_for_match)}")
        candidate_clients = []
        for identity_key in _document_identity_keys(document):
            candidate_clients.extend(kyc_candidates.get(identity_key, []))

        for client_token in _document_client_tokens(document):
            candidate_clients.extend(client_by_code.get(client_token, []))

        birth_key = _date_match_key(document.date_naissance)
        validity_key = _date_match_key(document.date_expiration)
        nationality_key = _nationality_match_key(document.nationalite or document.pays_naissance)
        birth_place_key = _nationality_match_key(document.lieu_naissance)
        combination_pool = {}
        for client in clients_by_birth_date.get(birth_key, []):
            combination_pool[client.pk] = client
        for client in clients_by_validity_date.get(validity_key, []):
            combination_pool[client.pk] = client
        if birth_key or validity_key:
            for client in clients_by_birth_place.get(birth_place_key, []):
                combination_pool[client.pk] = client
        if birth_key or validity_key:
            for client in clients_by_nationality.get(nationality_key, []):
                combination_pool[client.pk] = client
        for client in combination_pool.values():
            if _document_client_identity_score(document, client, match_weights) >= match_weights["combination_threshold"]:
                candidate_clients.append(client)

        unique_clients = {}
        for client in candidate_clients:
            if not _document_country_guard_passes(document, client):
                continue
            unique_clients[client.pk] = client

        for client in unique_clients.values():
            suggestions = []
            used_kyc_fields = set()
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

            match_rate = _document_client_identity_score(document, client, match_weights)
            if match_rate < 30:
                continue

            candidate_match = {
                "client": client,
                "document": document,
                "suggestions": suggestions,
                "match_rate": match_rate,
            }
            if not _build_kyc_pp_match_action_items(candidate_match):
                continue

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
                existing_extra_actions = existing_match.setdefault("extra_action_items", [])
                existing_action_keys = {
                    (action.get("kind"), (action.get("field") or "").strip().upper())
                    for action in _build_kyc_pp_match_action_items(existing_match)
                }
                for action in _build_kyc_pp_match_action_items(candidate_match):
                    action_key = (action.get("kind"), (action.get("field") or "").strip().upper())
                    if action_key not in existing_action_keys:
                        existing_extra_actions.append(action)
                        existing_action_keys.add(action_key)
                existing_match["match_rate"] = max(existing_match["match_rate"], match_rate)
                continue

            matched_client_ids.add(client.pk)
            matched_document_ids.add(document.pk)
            client_match_index[client_dedup_key] = len(matches)
            matches.append(candidate_match)

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
LAST_KYC_PP_MATCH_RESULT_SESSION_KEY = "document_extraction_last_kyc_pp_match_result"
KYC_PP_MATCHED_BATCHES_SESSION_KEY = "document_extraction_kyc_pp_matched_batches"
LAST_UPLOADED_DOCUMENT_BATCH_SESSION_KEY = "document_extraction_last_uploaded_batch"
KYC_PP_MATCH_RESULT_VERSION = 3


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
        if key not in {"page", "extraction_id", "match_kyc", "match_job", "show_match_results", "result_modal", "child_modal", "tab"} and value not in (None, "")
    }


def _document_match_scope_params(params):
    return {
        key: value
        for key, value in _clean_document_match_params(params).items()
        if key not in KYC_PP_MATCH_FILTER_FIELDS
    }


def _serialize_kyc_pp_matches(matches, summary, params):
    return {
        "version": KYC_PP_MATCH_RESULT_VERSION,
        "params": params,
        "summary": summary,
        "matches": [
            {
                "client_id": match["client"].pk,
                "document_id": match["document"].pk,
                "suggestions": match["suggestions"],
                "extra_action_items": match.get("extra_action_items") or [],
                "match_rate": match["match_rate"],
            }
            for match in matches
        ],
    }


def _hydrate_kyc_pp_match_result(result):
    if not result:
        return [], None, {}
    if result.get("version") != KYC_PP_MATCH_RESULT_VERSION:
        return [], None, result.get("params") or {}

    serialized_matches = result.get("matches") or []
    client_ids = [match.get("client_id") for match in serialized_matches if match.get("client_id")]
    document_ids = [match.get("document_id") for match in serialized_matches if match.get("document_id")]
    clients = Kyc_pp.objects.in_bulk(client_ids)
    documents = KycDocumentExtraction.objects.in_bulk(document_ids)

    matches = []
    for serialized_match in serialized_matches:
        client = clients.get(serialized_match.get("client_id"))
        document = documents.get(serialized_match.get("document_id"))
        if not client or not document:
            continue
        matches.append({
            "client": client,
            "document": document,
            "suggestions": serialized_match.get("suggestions") or [],
            "extra_action_items": serialized_match.get("extra_action_items") or [],
            "match_rate": serialized_match.get("match_rate") or 0,
        })

    return matches, result.get("summary"), result.get("params") or {}


def _merge_kyc_pp_match_lists(match_lists):
    merged = []
    index_by_key = {}

    for matches in match_lists:
        for match in matches:
            client = match.get("client")
            normalized_idp = _normalize_match_value(getattr(client, "IDP", ""))
            client_pk = getattr(client, "pk", None)
            key = (
                ("idp", normalized_idp)
                if normalized_idp
                else ("client", client_pk, _document_unique_key(match.get("document")))
            )
            if key not in index_by_key:
                index_by_key[key] = len(merged)
                merged.append(match)
                continue

            existing_match = merged[index_by_key[key]]
            existing_fields = {
                (suggestion.get("field") or "").strip().upper()
                for suggestion in existing_match.get("suggestions", [])
            }
            for suggestion in match.get("suggestions", []):
                suggestion_field = (suggestion.get("field") or "").strip().upper()
                if suggestion_field and suggestion_field not in existing_fields:
                    existing_match.setdefault("suggestions", []).append(suggestion)
                    existing_fields.add(suggestion_field)

            existing_actions = existing_match.setdefault("extra_action_items", [])
            action_keys = {
                (action.get("kind"), (action.get("field") or "").strip().upper())
                for action in existing_actions
            }
            for action in match.get("extra_action_items", []):
                action_key = (action.get("kind"), (action.get("field") or "").strip().upper())
                if action_key not in action_keys:
                    existing_actions.append(action)
                    action_keys.add(action_key)
            existing_match["match_rate"] = max(existing_match.get("match_rate", 0), match.get("match_rate", 0))

    return merged


def _user_can_access_document_match_job(user, job):
    return bool(user.is_superuser or job.created_by_id == user.pk)


def _run_document_match_job(job_id):
    close_old_connections()
    try:
        job = KycDocumentMatchJob.objects.get(pk=job_id)
        scope_params = job.scope_params or {}
        job.status = "running"
        job.started_at = timezone.now()
        job.message = "Preparation du rapprochement"
        job.save(update_fields=["status", "started_at", "message", "updated_at"])

        last_saved_step = {"value": -1}

        def progress_callback(current, total, message):
            if current != total and current - last_saved_step["value"] < 5:
                return
            last_saved_step["value"] = current
            KycDocumentMatchJob.objects.filter(pk=job_id).update(
                progress_current=current,
                progress_total=total,
                message=message,
                updated_at=timezone.now(),
            )

        documents = _filtered_document_extractions_from_params(scope_params)
        matches, summary = _build_kyc_pp_document_matches(
            documents,
            progress_callback=progress_callback,
        )
        result = _serialize_kyc_pp_matches(matches, summary, scope_params)
        KycDocumentMatchJob.objects.filter(pk=job_id).update(
            status="completed",
            progress_current=summary.get("documents_checked", 0),
            progress_total=summary.get("documents_checked", 0),
            message="Rapprochement termine",
            result=result,
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
    except Exception as exc:
        KycDocumentMatchJob.objects.filter(pk=job_id).update(
            status="failed",
            message="Echec du rapprochement",
            error=str(exc),
            completed_at=timezone.now(),
            updated_at=timezone.now(),
        )
    finally:
        close_old_connections()


@login_required
def start_document_extraction_match_job(request):
    scope_params = _document_match_scope_params(request.GET)
    existing_job = (
        KycDocumentMatchJob.objects
        .filter(created_by=request.user, scope_params=scope_params, status="running")
        .order_by("-created_at")
        .first()
    )
    job = existing_job or KycDocumentMatchJob.objects.create(
        created_by=request.user,
        scope_params=scope_params,
        message="Rapprochement en attente",
    )
    if not existing_job:
        threading.Thread(target=_run_document_match_job, args=(job.pk,), daemon=True).start()

    redirect_params = dict(scope_params)
    redirect_params["match_job"] = job.pk
    return redirect(f"{reverse('document_extraction')}?{urlencode(redirect_params)}#suivi")


@login_required
def document_extraction_match_job_status(request, job_id):
    job = get_object_or_404(KycDocumentMatchJob, pk=job_id)
    if not _user_can_access_document_match_job(request.user, job):
        return JsonResponse({"error": "Acces non autorise"}, status=403)

    total = job.progress_total or 0
    current = job.progress_current or 0
    percent = min(100, int(current / total * 100)) if total else (100 if job.status == "completed" else 0)
    redirect_params = dict(job.scope_params or {})
    redirect_params["match_job"] = job.pk
    result_params = dict(redirect_params)
    result_params["show_match_results"] = "1"
    result_params["result_modal"] = "1"

    return JsonResponse({
        "id": job.pk,
        "status": job.status,
        "message": job.message,
        "error": job.error,
        "current": current,
        "total": total,
        "percent": percent,
        "redirect_url": f"{reverse('document_extraction')}?{urlencode(redirect_params)}#suivi",
        "result_url": f"{reverse('document_extraction')}?{urlencode(result_params)}#suivi",
    })


KYC_PP_MATCH_FILTER_FIELDS = {
    "match_client": "CLIENT",
    "match_idp": "IDP",
    "match_filiale": "FILIALE",
    "match_agence": "AGENCE",
}


def _get_kyc_pp_match_filters(params):
    return {
        key: (params.get(key) or "").strip()
        for key in KYC_PP_MATCH_FILTER_FIELDS
    }


def _filter_kyc_pp_matches(matches, params):
    filters = _get_kyc_pp_match_filters(params)
    active_filters = {
        key: value.lower()
        for key, value in filters.items()
        if value
    }
    if not active_filters:
        return matches

    filtered_matches = []
    for match in matches:
        client = match["client"]
        keep_match = True
        for param_name, filter_value in active_filters.items():
            client_field = KYC_PP_MATCH_FILTER_FIELDS[param_name]
            client_value = str(getattr(client, client_field, "") or "").lower()
            if filter_value not in client_value:
                keep_match = False
                break
        if keep_match:
            filtered_matches.append(match)
    return filtered_matches


def _build_kyc_pp_match_action_items(match):
    document = match["document"]
    client = match["client"]
    actions = []
    action_keys = set()
    fields_with_actions = set()

    def add_action(kind, field, text):
        normalized_field = (field or "").strip().upper()
        key = (kind, normalized_field) if normalized_field else (kind, "", _normalize_match_value(text))
        if not text or key in action_keys:
            return
        action_keys.add(key)
        fields_with_actions.add(normalized_field)
        actions.append({"kind": kind, "field": normalized_field, "text": text})

    for suggestion in match.get("suggestions", []):
        field = (suggestion.get("field") or "").strip().upper()
        document_value = suggestion.get("document_value", "")
        if not field or not document_value:
            continue
        add_action("complete", field, f"{field}: {document_value}")

    fields_in_order = []
    fields_seen = set()
    for kyc_field, _, _ in KYC_PP_DOCUMENT_FIELD_MAP:
        if kyc_field not in fields_seen:
            fields_seen.add(kyc_field)
            fields_in_order.append(kyc_field)

    for kyc_field in fields_in_order:
        mapped_fields = [
            (document_field, label)
            for field_name, document_field, label in KYC_PP_DOCUMENT_FIELD_MAP
            if field_name == kyc_field
        ]
        document_values = [
            (getattr(document, document_field, ""), label)
            for document_field, label in mapped_fields
            if getattr(document, document_field, "")
        ]
        kyc_value = getattr(client, kyc_field, "")
        if not document_values or _is_empty_kyc_value(kyc_value):
            continue

        if kyc_field in {"DATNAIS", "DATVALID"}:
            values_match = any(_date_values_match(document_value, kyc_value) for document_value, _ in document_values)
        elif kyc_field == "PAYNAIS":
            values_match = any(_nationality_values_match(document_value, kyc_value) for document_value, _ in document_values)
        else:
            values_match = any(_values_match(document_value, kyc_value) for document_value, _ in document_values)

        if values_match:
            continue

        document_value, label = document_values[0]
        add_action("modify", kyc_field, f"{label} ({kyc_field}): {kyc_value or '-'} -> {document_value}")

    expired_match = match.get("expired_document_match")
    if expired_match and "DATVALID" not in fields_with_actions:
        add_action(
            "modify",
            "DATVALID",
            f"DATVALID: {expired_match.old_validity_date or '-'} -> {expired_match.document_validity_date or '-'}",
        )

    for action in match.get("extra_action_items") or []:
        add_action(action.get("kind") or "modify", action.get("field") or "", action.get("text") or "")

    return actions


@login_required
def export_document_extraction_matches(request):
    requested_scope_params = _document_match_scope_params(request.GET)
    matches = []

    last_match_result = request.session.get(LAST_KYC_PP_MATCH_RESULT_SESSION_KEY)
    stored_matches, _, stored_params = _hydrate_kyc_pp_match_result(last_match_result)

    if stored_matches and stored_params == requested_scope_params:
        matches = stored_matches
    else:
        documents = _filtered_document_extractions_from_params(requested_scope_params)
        matches, _ = _build_kyc_pp_document_matches(documents, result_limit=None)

    matches = _merge_kyc_pp_match_lists([matches])
    matches = _filter_kyc_pp_matches(matches, request.GET)

    selected_import_batch = (requested_scope_params.get("import_batch") or "").strip()
    expired_document_matches_qs = KycExpiredDocumentScanMatch.objects.select_related("client", "document").filter(
        status="a_valider"
    )
    if selected_import_batch:
        expired_document_matches_qs = expired_document_matches_qs.filter(document__import_batch=selected_import_batch)
    expired_match_by_client_id = {}
    for expired_match in expired_document_matches_qs.order_by("-match_rate", "-scan_date")[:500]:
        if expired_match.client_id in expired_match_by_client_id:
            continue
        expired_match_by_client_id[expired_match.client_id] = expired_match

    for match in matches:
        expired_match = expired_match_by_client_id.pop(match["client"].pk, None)
        if expired_match:
            match["expired_document_match"] = expired_match

    matched_idp_keys = {
        _normalize_match_value(getattr(match["client"], "IDP", "")) or str(match["client"].pk)
        for match in matches
    }
    standalone_expired_matches = []
    for expired_match in expired_match_by_client_id.values():
        expired_idp_key = _normalize_match_value(getattr(expired_match.client, "IDP", "") or expired_match.idp)
        expired_key = expired_idp_key or str(expired_match.client_id)
        if expired_key in matched_idp_keys:
            continue
        matched_idp_keys.add(expired_key)
        standalone_expired_matches.append(expired_match)

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    filename = timezone.localtime(timezone.now()).strftime("correspondances_kyc_pp_%Y%m%d_%H%M.csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")

    writer = csv.writer(response, delimiter=";")
    writer.writerow([
        "CLIENT",
        "IDP",
        "FILIALE",
        "AGENCE",
        "TYPE DE DOCUMENT",
        "TAUX CORRESPONDANCE",
        "A completer / A modifier",
        "Numero document",
        "Numero d'identification nationale",
    ])

    for match in matches:
        document = match["document"]
        client = match["client"]
        action_items = _build_kyc_pp_match_action_items(match)

        writer.writerow([
            client.CLIENT,
            client.IDP,
            client.FILIALE,
            client.AGENCE,
            document.get_document_type_display(),
            match.get("match_rate", 0),
            " | ".join(action["text"] for action in action_items),
            document.numero_document,
            document.numero_identification_nationale,
        ])

    for expired_match in standalone_expired_matches:
        client = expired_match.client
        document = expired_match.document
        writer.writerow([
            getattr(client, "CLIENT", "") or expired_match.client_code,
            getattr(client, "IDP", "") or expired_match.idp,
            getattr(client, "FILIALE", "") or expired_match.filiale,
            getattr(client, "AGENCE", "") or expired_match.agence,
            document.get_document_type_display() if document else "",
            expired_match.match_rate or 0,
            f"DATVALID: {expired_match.old_validity_date or '-'} -> {expired_match.document_validity_date or '-'}",
            getattr(document, "numero_document", "") if document else "",
            getattr(document, "numero_identification_nationale", "") if document else "",
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


DOCUMENT_EXTRACTION_TYPE_LABELS = dict(DOCUMENT_EXTRACTION_TYPE_CHOICES)


def _apply_detected_document_type(record, extraction, requested_type):
    detected_type = extraction.get("detected_document_type") or ""
    if detected_type not in DOCUMENT_EXTRACTION_TYPE_LABELS:
        return

    if detected_type != requested_type:
        warning = (
            "Type ajuste automatiquement: le document semble etre "
            f"{DOCUMENT_EXTRACTION_TYPE_LABELS[detected_type]} alors que "
            f"{DOCUMENT_EXTRACTION_TYPE_LABELS.get(requested_type, requested_type)} avait ete selectionne."
        )
        warnings = extraction.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)
        record.extraction_warnings = "\n".join(warnings)

    record.document_type = detected_type


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
    _apply_detected_document_type(record, extraction, document_type)
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
    _apply_detected_document_type(record, extraction, document_type)
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
        _apply_detected_document_type(record, extraction, document_type)
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
                request.session[LAST_UPLOADED_DOCUMENT_BATCH_SESSION_KEY] = import_batch
                request.session.modified = True
            if errors:
                messages.warning(request, f"{len(errors)} element(s) non importe(s): " + " | ".join(errors[:5]))
            if created_records:
                return redirect(f"{reverse('document_extraction')}?{urlencode({'uploaded_batch': import_batch})}#charger")

    documents = _filtered_document_extractions_from_request(request)
    selected_document_type = request.GET.get("document_type", "")
    selected_import_batch = (request.GET.get("import_batch") or "").strip()
    uploaded_batch = (request.GET.get("uploaded_batch") or "").strip()
    if not uploaded_batch and not request.GET:
        uploaded_batch = (request.session.get(LAST_UPLOADED_DOCUMENT_BATCH_SESSION_KEY) or "").strip()
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
    uploaded_documents_count = 0
    uploaded_quality_alerts = []
    uploaded_quality_alerts_count = 0
    if uploaded_batch:
        uploaded_documents_queryset = KycDocumentExtraction.objects.filter(import_batch=uploaded_batch)
        uploaded_documents_count = uploaded_documents_queryset.count()
        uploaded_quality_alerts_count = uploaded_documents_queryset.exclude(extraction_warnings="").count()
        uploaded_documents = uploaded_documents_queryset.order_by("-created_at")[:50]
        for document in uploaded_documents:
            warnings = [warning for warning in document.extraction_warnings.splitlines() if warning]
            if warnings:
                uploaded_quality_alerts.append({
                    "filename": document.original_filename or os.path.basename(document.uploaded_file.name),
                    "document_type": document.get_document_type_display(),
                    "warnings": warnings[:3],
                })
            if len(uploaded_quality_alerts) >= 5:
                break

    requested_kyc_pp_matching = request.GET.get("match_kyc") == "1"
    selected_match_job = None
    selected_match_job_id = request.GET.get("match_job")
    show_match_job_results = request.GET.get("show_match_results") == "1"
    show_match_result_modal = request.GET.get("result_modal") == "1"
    show_match_child_modal = request.GET.get("child_modal") == "1"
    wants_results_tab = request.GET.get("tab") == "results"
    if selected_match_job_id and selected_match_job_id.isdigit():
        selected_match_job = get_object_or_404(KycDocumentMatchJob, pk=selected_match_job_id)
        if not _user_can_access_document_match_job(request.user, selected_match_job):
            selected_match_job = None

    last_match_result = request.session.get(LAST_KYC_PP_MATCH_RESULT_SESSION_KEY)
    active_match_params = None
    is_global_consultation = not request.GET

    if requested_kyc_pp_matching:
        active_match_params = _document_match_scope_params(request.GET)
        request.session[LAST_KYC_PP_MATCH_SESSION_KEY] = active_match_params

    kyc_pp_matches = []
    kyc_pp_match_summary = {
        "documents_checked": 0,
        "documents_matched": 0,
        "clients_matched": 0,
        "suggestions_count": 0,
        "match_rate": 0,
    }
    if selected_match_job:
        active_match_params = selected_match_job.scope_params or {}
        if selected_match_job.status == "completed" and show_match_job_results:
            kyc_pp_matches, stored_summary, stored_params = _hydrate_kyc_pp_match_result(selected_match_job.result)
            if stored_summary is not None:
                kyc_pp_match_summary = stored_summary
                active_match_params = stored_params
                request.session[LAST_KYC_PP_MATCH_SESSION_KEY] = active_match_params
                request.session[LAST_KYC_PP_MATCH_RESULT_SESSION_KEY] = selected_match_job.result
                request.session.modified = True
        elif selected_match_job.status in {"pending", "running", "completed"}:
            kyc_pp_match_summary = {
                "documents_checked": selected_match_job.progress_total,
                "documents_matched": 0,
                "clients_matched": 0,
                "suggestions_count": 0,
                "match_rate": 0,
            }
    elif requested_kyc_pp_matching:
        match_documents = _filtered_document_extractions_from_params(active_match_params)
        kyc_pp_matches, kyc_pp_match_summary = _build_kyc_pp_document_matches(match_documents)
        request.session[LAST_KYC_PP_MATCH_RESULT_SESSION_KEY] = _serialize_kyc_pp_matches(
            kyc_pp_matches,
            kyc_pp_match_summary,
            active_match_params,
        )
        matched_batch = (active_match_params.get("import_batch") or "").strip()
        if matched_batch:
            matched_batches = set(request.session.get(KYC_PP_MATCHED_BATCHES_SESSION_KEY) or [])
            matched_batches.add(matched_batch)
            request.session[KYC_PP_MATCHED_BATCHES_SESSION_KEY] = sorted(matched_batches)
        request.session.modified = True
    elif wants_results_tab or is_global_consultation:
        stored_matches, stored_summary, stored_params = _hydrate_kyc_pp_match_result(last_match_result)
        if not wants_results_tab and stored_summary is not None and stored_params == {}:
            kyc_pp_matches = stored_matches
            kyc_pp_match_summary = stored_summary
        else:
            if wants_results_tab:
                completed_jobs = KycDocumentMatchJob.objects.filter(
                    created_by=request.user,
                    status="completed",
                ).order_by("-completed_at", "-created_at")
                hydrated_match_lists = []
                documents_checked_total = 0
                for job in completed_jobs:
                    job_matches, job_summary, _ = _hydrate_kyc_pp_match_result(job.result)
                    if job_matches:
                        hydrated_match_lists.append(job_matches)
                    if job_summary:
                        documents_checked_total += job_summary.get("documents_checked", 0)

                kyc_pp_matches = _merge_kyc_pp_match_lists(hydrated_match_lists)
                if kyc_pp_matches:
                    matched_idp_keys = {
                        _normalize_match_value(getattr(match["client"], "IDP", "")) or str(match["client"].pk)
                        for match in kyc_pp_matches
                    }
                    kyc_pp_match_summary = {
                        "documents_checked": documents_checked_total,
                        "documents_matched": len({match["document"].pk for match in kyc_pp_matches}),
                        "clients_matched": len(matched_idp_keys),
                        "suggestions_count": sum(len(_build_kyc_pp_match_action_items(match)) for match in kyc_pp_matches),
                        "match_rate": 0,
                    }
                    request.session[LAST_KYC_PP_MATCH_SESSION_KEY] = {}
                    request.session[LAST_KYC_PP_MATCH_RESULT_SESSION_KEY] = _serialize_kyc_pp_matches(
                        kyc_pp_matches,
                        kyc_pp_match_summary,
                        {},
                    )
                    request.session.modified = True
            else:
                global_job = (
                    KycDocumentMatchJob.objects
                    .filter(created_by=request.user, scope_params={}, status="completed")
                    .order_by("-completed_at", "-created_at")
                    .first()
                )
                if global_job:
                    kyc_pp_matches, stored_summary, stored_params = _hydrate_kyc_pp_match_result(global_job.result)
                    if stored_summary is not None:
                        kyc_pp_match_summary = stored_summary
                        request.session[LAST_KYC_PP_MATCH_SESSION_KEY] = {}
                        request.session[LAST_KYC_PP_MATCH_RESULT_SESSION_KEY] = global_job.result
                        request.session.modified = True
        if kyc_pp_matches:
            active_match_params = {}
    elif not is_global_consultation:
        kyc_pp_matches, stored_summary, stored_params = _hydrate_kyc_pp_match_result(last_match_result)
        stored_batch = (stored_params.get("import_batch") or "").strip()
        if selected_import_batch and stored_batch != selected_import_batch:
            kyc_pp_matches, stored_summary, stored_params = [], None, {}
        if stored_summary is not None:
            kyc_pp_match_summary = stored_summary
            active_match_params = stored_params

    kyc_pp_matches = _merge_kyc_pp_match_lists([kyc_pp_matches])
    run_kyc_pp_matching = active_match_params is not None
    kyc_pp_match_total_count = len(kyc_pp_matches)
    kyc_pp_match_filters = _get_kyc_pp_match_filters(request.GET)
    kyc_pp_matches = _filter_kyc_pp_matches(kyc_pp_matches, request.GET)
    expired_document_matches = KycExpiredDocumentScanMatch.objects.select_related("client", "document").filter(
        status="a_valider"
    )
    if selected_import_batch:
        expired_document_matches = expired_document_matches.filter(document__import_batch=selected_import_batch)
    unique_expired_document_matches = {}
    for expired_match in expired_document_matches.order_by("-match_rate", "-scan_date")[:500]:
        if expired_match.client_id in unique_expired_document_matches:
            continue
        unique_expired_document_matches[expired_match.client_id] = expired_match
        if len(unique_expired_document_matches) >= 100:
            break
    expired_match_by_client_id = unique_expired_document_matches
    for match in kyc_pp_matches:
        expired_match = expired_match_by_client_id.pop(match["client"].pk, None)
        if expired_match:
            match["expired_document_match"] = expired_match
        match["action_items"] = _build_kyc_pp_match_action_items(match)
        match["action_summary"] = " | ".join(action["text"] for action in match["action_items"])
    expired_document_matches = list(expired_match_by_client_id.values())
    matched_batches = set(request.session.get(KYC_PP_MATCHED_BATCHES_SESSION_KEY) or [])
    uploaded_batch_job_done = False
    uploaded_batch_running_job = None
    uploaded_batch_result_url = ""
    if uploaded_batch:
        uploaded_batch_running_job = (
            KycDocumentMatchJob.objects
            .filter(created_by=request.user, scope_params={"import_batch": uploaded_batch}, status__in=["pending", "running"])
            .order_by("-created_at")
            .first()
        )
        if uploaded_batch_running_job:
            follow_params = dict(uploaded_batch_running_job.scope_params or {})
            follow_params["match_job"] = uploaded_batch_running_job.pk
            uploaded_batch_running_job.follow_url = f"{reverse('document_extraction')}?{urlencode(follow_params)}#suivi"
        uploaded_batch_job_done = KycDocumentMatchJob.objects.filter(
            created_by=request.user,
            scope_params={"import_batch": uploaded_batch},
            status="completed",
        ).exists()
        uploaded_batch_completed_job = (
            KycDocumentMatchJob.objects
            .filter(created_by=request.user, scope_params={"import_batch": uploaded_batch}, status="completed")
            .order_by("-completed_at", "-created_at")
            .first()
        )
        if uploaded_batch_completed_job:
            result_params = dict(uploaded_batch_completed_job.scope_params or {})
            result_params["match_job"] = uploaded_batch_completed_job.pk
            result_params["show_match_results"] = "1"
            uploaded_batch_result_url = f"{reverse('document_extraction')}?{urlencode(result_params)}#consulter"
    uploaded_batch_matching_done = bool(uploaded_batch and (uploaded_batch in matched_batches or uploaded_batch_job_done))
    show_document_modal = (bool(extraction) and not show_match_child_modal) or request.GET.get("lot_view") == "1"
    recent_match_jobs = list(KycDocumentMatchJob.objects.filter(created_by=request.user).order_by("-created_at")[:12])
    for job in recent_match_jobs:
        follow_params = dict(job.scope_params or {})
        follow_params["match_job"] = job.pk
        result_params = dict(follow_params)
        result_params["show_match_results"] = "1"
        result_params["result_modal"] = "1"
        job.follow_url = f"{reverse('document_extraction')}?{urlencode(follow_params)}#suivi"
        job.result_url = f"{reverse('document_extraction')}?{urlencode(result_params)}#suivi"
    upload_batch_queue_all = list(
        KycDocumentExtraction.objects
        .filter(uploaded_by=request.user)
        .exclude(import_batch="")
        .values("import_batch")
        .annotate(documents_count=Count("id"), latest_created_at=Max("created_at"))
        .order_by("-latest_created_at")[:12]
    )
    upload_batch_queue = []
    for batch in upload_batch_queue_all:
        batch_name = batch["import_batch"]
        batch["documents_url"] = f"{reverse('document_extraction')}?{urlencode({'import_batch': batch_name})}#base"
        latest_job = (
            KycDocumentMatchJob.objects
            .filter(created_by=request.user, scope_params={"import_batch": batch_name})
            .order_by("-created_at")
            .first()
        )
        batch["job"] = latest_job
        batch["status"] = "pending"
        batch["status_label"] = "En attente"
        batch["start_url"] = f"{reverse('start_document_extraction_match_job')}?{urlencode({'import_batch': batch_name})}"
        batch["follow_url"] = ""
        batch["result_url"] = ""
        if latest_job:
            follow_params = dict(latest_job.scope_params or {})
            follow_params["match_job"] = latest_job.pk
            result_params = dict(follow_params)
            result_params["show_match_results"] = "1"
            result_params["result_modal"] = "1"
            batch["follow_url"] = f"{reverse('document_extraction')}?{urlencode(follow_params)}#suivi"
            batch["result_url"] = f"{reverse('document_extraction')}?{urlencode(result_params)}#suivi"
            if latest_job.status == "completed":
                batch["status"] = "completed"
                batch["status_label"] = "Termine"
            elif latest_job.status in {"pending", "running"}:
                batch["status"] = "running"
                batch["status_label"] = "En cours"
            elif latest_job.status == "failed":
                batch["status"] = "failed"
                batch["status_label"] = "Echec"
        if batch["status"] in {"pending", "failed"}:
            upload_batch_queue.append(batch)

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
        export_match_params = dict(active_match_params)
    else:
        export_match_params = _document_match_scope_params(request.GET)
    match_filter_hidden_params = {
        key: value
        for key, value in export_match_params.items()
        if key not in KYC_PP_MATCH_FILTER_FIELDS
        and key not in {"page", "extraction_id"}
        and value not in (None, "")
    }
    match_reset_params = dict(match_filter_hidden_params)
    if run_kyc_pp_matching:
        match_reset_params["match_kyc"] = "1"
    export_match_params.update({
        key: value
        for key, value in kyc_pp_match_filters.items()
        if value
    })
    export_match_querystring = urlencode(export_match_params)
    match_reset_querystring = urlencode(match_reset_params)
    selected_match_job_result_url = ""
    selected_match_job_follow_url = f"{reverse('document_extraction')}#suivi"
    selected_match_job_parent_modal_url = ""
    if selected_match_job:
        follow_params = dict(selected_match_job.scope_params or {})
        follow_params["match_job"] = selected_match_job.pk
        selected_match_job_follow_url = f"{reverse('document_extraction')}?{urlencode(follow_params)}#suivi"
        result_params = dict(selected_match_job.scope_params or {})
        result_params["match_job"] = selected_match_job.pk
        result_params["show_match_results"] = "1"
        result_params["result_modal"] = "1"
        selected_match_job_result_url = f"{reverse('document_extraction')}?{urlencode(result_params)}#suivi"
        selected_match_job_parent_modal_url = selected_match_job_result_url
    latest_global_match_job = (
        KycDocumentMatchJob.objects
        .filter(created_by=request.user, scope_params={}, status="completed")
        .order_by("-completed_at", "-created_at")
        .first()
    )
    all_match_results_url = f"{reverse('document_extraction')}#consulter"
    if latest_global_match_job:
        all_results_params = {
            "match_job": latest_global_match_job.pk,
            "show_match_results": "1",
            "result_modal": "1",
        }
        all_match_results_url = f"{reverse('document_extraction')}?{urlencode(all_results_params)}#suivi"

    if selected_match_job and show_match_result_modal:
        base_child_params = dict(selected_match_job.scope_params or {})
        base_child_params["match_job"] = selected_match_job.pk
        base_child_params["show_match_results"] = "1"
        base_child_params["result_modal"] = "1"
        base_child_params["child_modal"] = "1"
        for match in kyc_pp_matches:
            child_params = dict(base_child_params)
            child_params["extraction_id"] = match["document"].pk
            match["child_detail_url"] = f"{reverse('document_extraction')}?{urlencode(child_params)}#suivi"

    context = {
        "extraction": extraction,
        "documents": page_obj,
        "documents_count": documents.count(),
        "uploaded_batch": uploaded_batch,
        "uploaded_documents": uploaded_documents,
        "uploaded_documents_count": uploaded_documents_count,
        "uploaded_quality_alerts": uploaded_quality_alerts,
        "uploaded_quality_alerts_count": uploaded_quality_alerts_count,
        "uploaded_batch_matching_done": uploaded_batch_matching_done,
        "uploaded_batch_running_job": uploaded_batch_running_job,
        "uploaded_batch_result_url": uploaded_batch_result_url,
        "upload_batch_queue": upload_batch_queue,
        "show_document_modal": show_document_modal,
        "kyc_pp_matches": kyc_pp_matches,
        "kyc_pp_match_summary": kyc_pp_match_summary,
        "kyc_pp_match_total_count": kyc_pp_match_total_count,
        "kyc_pp_match_filtered_count": len(kyc_pp_matches),
        "expired_document_matches": expired_document_matches,
        "kyc_pp_match_filters": kyc_pp_match_filters,
        "match_filter_hidden_params": match_filter_hidden_params,
        "run_kyc_pp_matching": run_kyc_pp_matching,
        "show_match_actions": run_kyc_pp_matching and not wants_results_tab and (not selected_match_job or show_match_job_results),
        "wants_results_tab": wants_results_tab,
        "selected_match_job": selected_match_job,
        "show_match_job_results": show_match_job_results,
        "show_match_result_modal": show_match_result_modal,
        "show_match_child_modal": show_match_child_modal,
        "selected_match_job_result_url": selected_match_job_result_url,
        "selected_match_job_follow_url": selected_match_job_follow_url,
        "selected_match_job_parent_modal_url": selected_match_job_parent_modal_url,
        "all_match_results_url": all_match_results_url,
        "recent_match_jobs": recent_match_jobs,
        "match_scope_import_batch": (active_match_params or {}).get("import_batch", ""),
        "match_querystring": match_query_params.urlencode(),
        "match_reset_querystring": match_reset_querystring,
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
            return redirect("profile")  # redirige aprÃ¨s update
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
                # Si l'utilisateur a le profil "ContrÃ´le permanent"
                if request.user.is_authenticated and request.user.groups.filter(name='ContrÃ´le permanent').exists():
                    form = NoteForm(request.POST or None)
                    if form.is_valid():
                        note = form.save(commit=False)
                        note.agent = agent
                        note.date_notation = timezone.now()  # Enregistrer la date de notation
                        note.save()
                        message = "Notation enregistrÃ©e avec succÃ¨s."
                        form = None  # Reset le formulaire aprÃ¨s enregistrement pour Ã©viter la soumission rÃ©pÃ©tÃ©e
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
    roles_exclus = ["ChargÃ© Client"]
    notes = Notation.objects.filter(flux_stock='Flux')
    user = request.user
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
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
            messages.success(request, 'Votre profil a Ã©tÃ© modifiÃ© avec succÃ¨s')
            return redirect('/perso/profil')

    else:
        user_form = ProfileModify(instance=request.user)
    return render(request, 'modify_profil.html', {'user_form': user_form})


@method_decorator(csrf_exempt, name='dispatch')
class ChangePasswordView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'modify_pw.html'
    success_message = "Votre mot de passe a Ã©tÃ© changÃ© avec succÃ¨s"
    success_url = reverse_lazy('profil')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ajout du contexte personnalisÃ©
        context['roles_exclus'] = ["ChargÃ© Client"]
        return context


@csrf_exempt
def reset_user_password_b(request, user_id):
    roles_exclus = ["ChargÃ© Client"]
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            # Enregistrer le nouveau mot de passe en le hachant
            new_password = form.cleaned_data['new_password']
            user.password = make_password(new_password)
            user.save()
            return redirect('profil')  # Rediriger vers la liste des utilisateurs aprÃ¨s modification
    else:
        form = ResetPasswordForm()

    return render(request, 'modify_pw.html', {'form': form, 'user': user, 'roles_exclus': roles_exclus})


@login_required
def perso(request):
    # RÃ©cupÃ©rer l'utilisateur connectÃ©
    roles_exclus = ["ChargÃ© Client"]
    user = request.user

    # VÃ©rifier si l'utilisateur appartient Ã  "ContrÃ´le", "ConformitÃ©" ou "ContrÃ´le Groupe"
    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
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
    roles_exclus = ["ChargÃ© Client"]
    user = request.user

    # VÃ©rifier si l'utilisateur appartient Ã  "ContrÃ´le", "ConformitÃ©" ou "ContrÃ´le Groupe"
    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Flux')
    elif user.organe in ['Directeur Agence']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Flux')
    else:
        notes = Notation.objects.filter(flux_stock='Flux')

    # Annoter chaque agent avec la derniÃ¨re date de notation
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
    notes = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    notes = notes.order_by('-date_notation')
    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        agents = ProfileV.objects.filter(code_expl__icontains=query)  # Utilisation de icontains pour une recherche partielle
        if agents.exists():
            notes = notes.all().filter(agent__in=agents)
        else:
            # Si aucun agent n'est trouvÃ©, vider le queryset pour ne rien afficher
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

    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Flux')
    elif user.organe in ['Directeur Agence']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Flux')
    else:
        donnees = Notation.objects.filter(flux_stock='Flux')

    latest_notes = donnees.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
    donnees = donnees.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    donnees = donnees.order_by('-date_notation')

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Flux"

    # EntÃªtes
    headers = ["FILIALE", "EXPLOITANT", "NOM", "AGENCE", "EMAIL", "NOTE", "DerniÃ¨re notation", "NotÃ© par le contrÃ´leur",
               "Flux/Stock"]
    ws.append(headers)

    # DonnÃ©es
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

    # PrÃ©parer la rÃ©ponse HTTP
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

    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Stock')
    elif user.organe in ['Directeur Agence']:
        donnees = Notation.objects.filter(note_par__filiale=user.filiale, agent__agence=user.agence, flux_stock='Stock')
    else:
        donnees = Notation.objects.filter(flux_stock='Stock')

    latest_notes = donnees.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
    donnees = donnees.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    donnees = donnees.order_by('-date_notation')

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # EntÃªtes
    headers = ["FILIALE", "EXPLOITANT", "NOM", "AGENCE", "EMAIL", "NOTE", "DerniÃ¨re notation", "NotÃ© par le contrÃ´leur",
               "Flux/Stock"]
    ws.append(headers)

    # DonnÃ©es
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

    # PrÃ©parer la rÃ©ponse HTTP
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
    # RÃ©cupÃ©rer l'utilisateur connectÃ©
    user = request.user

    # VÃ©rifier si l'utilisateur appartient Ã  "ContrÃ´le", "ConformitÃ©" ou "ContrÃ´le Groupe"
    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
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

    # VÃ©rifier si l'utilisateur appartient Ã  "ContrÃ´le", "ConformitÃ©" ou "ContrÃ´le Groupe"
    if user.organe in ['ContrÃ´le Permanent', 'Directeur RÃ©seau', 'ConformitÃ©','Risques', 'DAI', 'QualitÃ©','DSI']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Stock')
    else:
        notes = Notation.objects.filter(flux_stock='Stock')

    # Annoter chaque agent avec la derniÃ¨re date de notation
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notes = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
    notes = notes.order_by('-date_notation')

    # Gestion de la recherche par exploitant
    query = request.GET.get('q', '')
    if query:
        agents = ProfileV.objects.filter(code_expl__icontains=query)  # Utilisation de icontains pour une recherche partielle
        if agents.exists():
            notes = notes.filter(agent__in=agents)
        else:
            # Si aucun agent n'est trouvÃ©, vider le queryset pour ne rien afficher
            notes = notes.none()

    return render(request, 'agent_stock.html', {'notes': notes, 'query': query})


@csrf_exempt
def notes(request):
    agent = None
    roles_exclus = ["ChargÃ© Client", "Directeur Agence"]
    form = NotationForm()  # Initialisation du formulaire

    if request.method == 'POST':
        if 'search_agent' in request.POST:
            # Rechercher l'agent par son code exploitant
            code_exploitant = request.POST.get('code_exploitant')
            try:
                agent = ProfileV.objects.get(code_expl=code_exploitant, filiale=request.user.filiale)

                # PrÃ©remplir le formulaire avec l'agent trouvÃ©
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
                # Assigner l'agent Ã  partir du formulaire
                notation = form.save(commit=False)
                notation.filiale = request.user.filiale
                notation.note_par = request.user
                notation.date_notation = timezone.now()
                notation.save()
                messages.success(request, 'La notation a bien Ã©tÃ© sauvegardÃ©e.')

                return redirect('agent')
    else:
        form = NotationForm()  # Afficher un formulaire vide si la requÃªte n'est pas en POST

    return render(request, 'notation.html', {'form': form, 'agent': agent, 'roles_exclus': roles_exclus})


def agent_detail(request, agent_id):
    agent = get_object_or_404(ProfileV, id=agent_id)
    notations = agent.notations.all().order_by('-date_notation')
    return render(request, 'agent_detail.html', {'agent': agent, 'notations': notations})


@login_required
@csrf_exempt
def historique(request):
    roles_exclus = ["ChargÃ© Client", "Directeur Agence"]
    query = request.GET.get('q')

    if query:
        # Filtre les notations en fonction du code exploitant
        notations = Notation.objects.filter(note_par=request.user, agent__code_expl__icontains=query).order_by(
            "-date_notation")
    else:
        # RÃ©cupÃ¨re toutes les notations de l'utilisateur connectÃ©
        notations = Notation.objects.filter(note_par=request.user).order_by("-date_notation")

    # Passe les notations au template
    context = {
        'notations': notations,
        'query': query,
    }  # Pour prÃ©-remplir la barre de recherche
    return render(request, 'historique.html', {'notations': notations, 'roles_exclus': roles_exclus})


def test(request):
    return render(request, 'test.html')


@login_required
def register(request):
    roles_exclus = ["ChargÃ© Client"]
    current_user = request.user

    # ðŸ”’ VÃ©rification des droits d'accÃ¨s
    if current_user.organe not in ["PASS", "DSI"]:
        messages.error(request, "Vous nâ€™avez pas la permission de crÃ©er un compte utilisateur.")
        return redirect('user_list')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)

            # Si l'utilisateur est DSI â†’ forcer la filiale du nouveau compte
            if current_user.organe == "DSI":
                new_user.filiale = current_user.filiale

            new_user.save()
            messages.success(request, "Utilisateur crÃ©Ã© avec succÃ¨s.")
            return redirect('user_list')
    else:
        form = CustomUserCreationForm(current_user=current_user)  # ðŸ‘ˆ On passe lâ€™utilisateur connectÃ© au formulaire

    return render(request, 'register.html', {'form': form, 'roles_exclus': roles_exclus})


# Fonction pour vÃ©rifier si l'utilisateur appartient Ã  l'organe "PASS"
def is_pass_user(user):
    return user.organe == 'PASS'


# Limiter l'accÃ¨s Ã  ceux de l'organe 'PASS'


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

    # 2. Recherche multi-critÃ¨res
    if query:
        users_base = users_base.filter(
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(username__icontains=query)
        )

    # 3. RÃ©cupÃ©ration des connectÃ©s (Sessions actives)
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

    # ðŸ”’ RÃ¨gles dâ€™accÃ¨s
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request, "Vous ne pouvez modifier que les utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous nâ€™avez pas la permission de modifier cet utilisateur.")
            return redirect('user_list')

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=target_user, current_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Utilisateur modifiÃ© avec succÃ¨s.")
            return redirect('user_list')
    else:
        form = UserEditForm(instance=target_user, current_user=request.user)

    return render(request, 'edit_user.html', {'form': form, 'user': target_user})


@login_required
def change_user_password(request, user_id):
    current_user = request.user
    target_user = get_object_or_404(ProfileV, pk=user_id)

    # ðŸ”’ RÃ¨gles dâ€™accÃ¨s :
    # - PASS : peut changer le mot de passe de tous les utilisateurs
    # - DSI : peut changer le mot de passe uniquement des utilisateurs de sa filiale
    # - Autres : accÃ¨s refusÃ©
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request, "Vous ne pouvez changer le mot de passe que des utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous nâ€™avez pas la permission de changer ce mot de passe.")
            return redirect('user_list')

    # ðŸ§¾ Traitement du formulaire
    if request.method == 'POST':
        form = PasswordChangeForm(target_user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Ã©viter la dÃ©connexion
            messages.success(request, "Le mot de passe a Ã©tÃ© modifiÃ© avec succÃ¨s.")
            return redirect('user_list')
    else:
        form = PasswordChangeForm(target_user)

    return render(request, 'change_user_password.html', {'form': form, 'user': target_user})


@login_required
def reset_user_password(request, user_id):
    current_user = request.user
    target_user = get_object_or_404(ProfileV, pk=user_id)

    # ðŸ”’ RÃ¨gles dâ€™accÃ¨s :
    if current_user.organe != "PASS":
        if current_user.organe == "DSI":
            if current_user.filiale != target_user.filiale:
                messages.error(request,
                               "Vous ne pouvez rÃ©initialiser que les mots de passe des utilisateurs de votre filiale.")
                return redirect('user_list')
        else:
            messages.error(request, "Vous nâ€™avez pas la permission de rÃ©initialiser ce mot de passe.")
            return redirect('user_list')

    # ðŸ§¾ Traitement du formulaire
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            new_password = form.cleaned_data['new_password']
            target_user.password = make_password(new_password)
            target_user.force_password_change = form.cleaned_data.get('force_password_change', False)
            target_user.save()
            messages.success(request, "Le mot de passe a Ã©tÃ© rÃ©initialisÃ© avec succÃ¨s.")
            return redirect('user_list')
    else:
        form = ResetPasswordForm(initial={
            'force_password_change': target_user.force_password_change
        })

    return render(request, 'reset_user_password.html', {'form': form, 'target_user': target_user})


@login_required
def user_statistics_view(request):
    roles_exclus = ["ChargÃ© Client"]
    current_user = request.user  # utilisateur connectÃ©

    # ðŸ”’ RÃ¨gles dâ€™accÃ¨s selon lâ€™organe
    if current_user.organe == "PASS":
        users = ProfileV.objects.all()

    elif current_user.organe == "DSI":
        users = ProfileV.objects.filter(filiale=current_user.filiale)

    else:
        messages.error(request, "Vous nâ€™avez pas la permission dâ€™accÃ©der Ã  cette page.")
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

    # ðŸ”„ Sessions actives
    active_sessions = Session.objects.filter(expire_date__gte=now())
    user_ids = []
    for session in active_sessions:
        data = session.get_decoded()
        if '_auth_user_id' in data:
            user_ids.append(data['_auth_user_id'])

    # Supprimer les doublons
    user_ids = list(set(user_ids))

    # ðŸ‘¥ Utilisateurs connectÃ©s visibles par le user connectÃ©
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

    # Contexte Ã  envoyer au template
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
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]
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

    # Filtrage automatique selon le rÃ´le
    if user.organe == "ChargÃ© Client":
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

    # === Valeurs du formulaire selon le rÃ´le ===
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
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©rer les filtres GET
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

    # Filtrage selon le rÃ´le utilisateur
    if user.organe == "ChargÃ© Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence , EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    # else: si utilisateur avec rÃ´le â€œgroupeâ€ ou autre --> pas de filtre rÃ´le spÃ©cifique

    # Appliquer les filtres GET sâ€™ils sont fournis
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)

    # CrÃ©ation du classeur Excel
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
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # ðŸŒŸ CORRECTION / AMÃ‰LIORATION ðŸŒŸ
    # Utilisation de __exact pour filtrer strictement les non-rÃ©sidents ('N')
    # Utilisez __icontains="N" si le champ peut contenir d'autres informations et que "N" suffit.
    donnees = Kyc_pp.objects.filter(RESID__icontains="N")
    # Si vous voulez l'ancienne logique avec moins de sensibilitÃ© Ã  la casse :
    # donnees = Kyc_pp.objects.filter(RESID__iexact="N")

    # === Filtrage automatique selon le rÃ´le ===
    if user.organe == "ChargÃ© Client":
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
    # On calcule les listes sur le QuerySet filtrÃ© par le rÃ´le

    # Par dÃ©faut (pour les users_groupe ou si aucun rÃ´le spÃ©cifique n'est atteint)
    exploitants = donnees.values_list('EXPL', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()

    # Remplacer par des filtres plus stricts si l'utilisateur a un rÃ´le restreint
    if user.organe == "Directeur Agence":
        # Les filtres par filiale et agence ont dÃ©jÃ  Ã©tÃ© appliquÃ©s ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()
    elif user.organe in users_filiale:
        # Le filtre par filiale a dÃ©jÃ  Ã©tÃ© appliquÃ© ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()

    filiales = donnees.values_list('FILIALE', flat=True).distinct()
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    # 2. Obtenir le QuerySet final pour la pagination
    # On utilise 'donnees' qui est le QuerySet filtrÃ©
    queryset = donnees

    # Simulation de la variable
    ITEMS_PER_PAGE = 25

    # 3. Appliquer le Paginator
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la premiÃ¨re page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la derniÃ¨re page
        objets_page = paginator.page(paginator.num_pages)

    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    context = {
        # 'donnees' est maintenant l'objet Page paginÃ©
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

        users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
        users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                        "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

        # RÃ©cupÃ©ration des filtres GET pour la synchronisation
        filiale_param = request.GET.get('filiale', '')
        agence_param = request.GET.get('agence', '')
        expl_param = request.GET.get('expl', '')

        # DÃ©but du Queryset
        donnees = Kyc_pp.objects.filter(RESID__icontains="N")


        # === Filtrage automatique selon le rÃ´le (identique Ã  devise) ===
        if user.organe == "ChargÃ© Client":
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

        # Fin du Queryset filtrÃ©

        # CrÃ©ation du classeur Excel
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Comptes Devise PP"  # J'ai renommÃ© le titre

        # EntÃªtes
        headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP", "PAYNAIS", "PROFESSION", "ADRESSE", "PAYS_RESID",
                   "NUMID", "SALAIRE", "ORIGINE_REV", "DATVALID", "TEL"]
        ws.append(headers)

        # DonnÃ©es
        for d in donnees:
            ws.append([
                d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
                d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID, d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL
            ])

        # Ajustement largeur des colonnes (optionnel)
        for col_num, column_title in enumerate(headers, 1):
            column_letter = get_column_letter(col_num)
            ws.column_dimensions[column_letter].width = 15

        # PrÃ©parer la rÃ©ponse HTTP
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
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # ðŸŒŸ CORRECTION / AMÃ‰LIORATION ðŸŒŸ
    # Utilisation de __exact pour filtrer strictement les non-rÃ©sidents ('N')
    # Utilisez __icontains="N" si le champ peut contenir d'autres informations et que "N" suffit.
    donnees = Kyc_pm.objects.filter(RESID__exact="N")
    # Si vous voulez l'ancienne logique avec moins de sensibilitÃ© Ã  la casse :
    # donnees = Kyc_pp.objects.filter(RESID__iexact="N")

    # === Filtrage automatique selon le rÃ´le ===
    if user.organe == "ChargÃ© Client":
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
    # On calcule les listes sur le QuerySet filtrÃ© par le rÃ´le

    # Par dÃ©faut (pour les users_groupe ou si aucun rÃ´le spÃ©cifique n'est atteint)
    exploitants = donnees.values_list('EXPL', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()

    # Remplacer par des filtres plus stricts si l'utilisateur a un rÃ´le restreint
    if user.organe == "Directeur Agence":
        # Les filtres par filiale et agence ont dÃ©jÃ  Ã©tÃ© appliquÃ©s ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()
    elif user.organe in users_filiale:
        # Le filtre par filiale a dÃ©jÃ  Ã©tÃ© appliquÃ© ci-dessus, on peut utiliser donnees
        agences = donnees.values_list('AGENCE', flat=True).distinct()
        exploitants = donnees.values_list('EXPL', flat=True).distinct()

    filiales = donnees.values_list('FILIALE', flat=True).distinct()

    # 2. Obtenir le QuerySet final pour la pagination
    # On utilise 'donnees' qui est le QuerySet filtrÃ©
    queryset = donnees

    # Simulation de la variable
    ITEMS_PER_PAGE = 25

    # 3. Appliquer le Paginator
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    query_params = request.GET.copy()
    if 'page' in query_params:
        del query_params['page']

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la premiÃ¨re page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la derniÃ¨re page
        objets_page = paginator.page(paginator.num_pages)

    context = {
        # 'donnees' est maintenant l'objet Page paginÃ©
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

    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©ration des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # DÃ©but du Queryset
    donnees = Kyc_pm.objects.filter(RESID__icontains="N")

    # === Filtrage automatique selon le rÃ´le (identique Ã  devise) ===
    if user.organe == "ChargÃ© Client":
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

    # Fin du Queryset filtrÃ©

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommÃ© le titre

    # EntÃªtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "AGEC", "CODAPE", "IDM", "RCSNO", "CAPITAL", "CA",
               "RESULTAT", "TEL"]
    ws.append(headers)

    # DonnÃ©es
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.AGEC, d.CODAPE, d.IDM,
            d.RCSNO, d.CAPITAL, d.CA, d.RESULTAT, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # PrÃ©parer la rÃ©ponse HTTP
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
    # 1. DÃ©finition des rÃ´les
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau", 'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    user = request.user
    today = date.today()

    # 2. RÃ©cupÃ©ration des paramÃ¨tres
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

    # 3. Filtrage par RÃ´le (SÃ©curitÃ©)
    organe = getattr(user, "organe", "")
    if organe == "ChargÃ© Client":
        qs = qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif organe == "Directeur Agence":
        qs = qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif organe in users_filiale:
        qs = qs.filter(FILIALE=user.filiale)
    # Si users_groupe, on ne filtre pas initialement

    # 4. Filtrage par PÃ©riode
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

    # 6. GÃ©nÃ©ration des options pour les menus dÃ©roulants (basÃ© sur le QS filtrÃ© ou global)
    # Il est souvent prÃ©fÃ©rable de baser les options sur le QS global ou par filiale
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
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©rer les filtres GET comme dans la vue scoring
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

    if getattr(user, "organe", "") == "ChargÃ© Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        base_qs = base_qs.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # pas de filtre organe â†’ laisse tout (selon ce que tu veux)
        pass
    else:
        # par sÃ©curitÃ©, si organe non reconnu, on vide
        base_qs = DATEREV.objects.none()

    # Appliquer le filtre pÃ©riode si dÃ©fini
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

    # CrÃ©ation du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # EntÃªtes (vÃ©rifie que les noms sont corrects)
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
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©rer les filtres GET comme dans la vue scoring
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    if user.organe == 'ConformitÃ©':
        base_qs = DATEREV.objects.filter(FILIALE=user.filiale, PPE__icontains="O", DATEREV__isnull=False)
    elif user.organe == "ConformitÃ© Groupe":
        base_qs = DATEREV.objects.filter(PPE__icontains="O", DATEREV__isnull=False)

    # Appliquer le filtre pÃ©riode si dÃ©fini
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

    # CrÃ©ation du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # EntÃªtes (vÃ©rifie que les noms sont corrects)
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
    # RÃ´les
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    user = request.user

    notes = Notation.objects.filter(flux_stock='Flux')

    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))

    # Filtrer pour obtenir uniquement la derniÃ¨re note par agent
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])
    notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)


    # Params GET
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    # RÃ©cupÃ©rer les paramÃ¨tres GET pour les conserver dans les liens de pagination
    get_params = request.GET.copy()
    if 'page' in get_params:
        del get_params['page']

    base_qs = DATEREV.objects.all()

    # --- LOGIQUE DE FILTRAGE PAR RÃ”LE ---
    if getattr(user, "organe", "") == "ChargÃ© Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        base_qs = base_qs.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        pass  # Pas de filtre initial pour le groupe

    # --- LOGIQUE DE FILTRAGE PAR PÃ‰RIODE ---
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
    if getattr(user, "organe", "") == "ChargÃ© Client":
        selected_expl = getattr(user, "code_expl", "")
    else:
        selected_expl = expl_param
    exploitants_opts = qs_agence.values_list("EXPL", flat=True).distinct().order_by("EXPL")

    donnees_queryset = qs_agence  # RenommÃ© pour clartÃ© avant le filtre final
    if selected_expl:
        donnees_queryset = donnees_queryset.filter(EXPL=selected_expl)

    # Evite les doublons visibles si des doublons historiques existent en base
    donnees_queryset = (
        donnees_queryset
        .values("FILIALE", "AGENCE", "LIB_AGENCE", "EXPL", "CLIENT", "DATEREV", "PPE", "RISQUE")
        .distinct()
        .order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")
    )

    # --- DÃ‰BUT DE LA LOGIQUE DE PAGINATION ---

    paginator = Paginator(donnees_queryset, 100)  # 100 Ã©lÃ©ments par page
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
        # SÃ©lections courantes
        "periode": periode_param,
        "filiale_param": selected_filiale,
        "agence_param": selected_agence,
        "expl_param": selected_expl,

        # RÃ´les
        "users_groupe": users_groupe,
        "users_filiale": users_filiale,

        # Droits d'Ã©dition des selects
        "can_pick_filiale": can_pick_filiale,
        "can_pick_agence": can_pick_agence,
        "can_pick_expl": can_pick_expl,

        # ParamÃ¨tres GET pour la pagination
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

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Notation_Stock"

    # EntÃªtes
    headers = ['AGENCE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    # DonnÃ©es
    for d in donnees:
        ws.append([
            d["FILIALE"], d["AGENCE"], d["EXPL"], d["CLIENT"], d["DATEREV"], d["PPE"], d["RISQUE"]

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # PrÃ©parer la rÃ©ponse HTTP
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

    # 1. RÃ´les et paramÃ¨tres
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
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

    # 2. Filtrage de base (SÃ©curitÃ© par rÃ´le + Condition CLASSE vide)
    # On commence par le filtre "CLASSE vide ou nulle"
    donnees_queryset = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Restriction du pÃ©rimÃ¨tre selon l'organe de l'utilisateur
    if user.organe == "ChargÃ© Client":
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

    # Tri cohÃ©rent pour la pagination
    donnees_queryset = donnees_queryset.order_by("FILIALE", "AGENCE", "EXPL", "CLIENT")

    # 4. Options pour les menus dÃ©roulants (respectant le pÃ©rimÃ¨tre)
    options_qs = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))
    if user.organe == "ChargÃ© Client":
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
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©rer les filtres GET
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Base queryset â€” uniquement ceux avec un RISQUE non nul
    donnees = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Filtrage selon le rÃ´le
    if user.organe == "ChargÃ© Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    elif user.organe in users_groupe:
        # donnees reste DATEREV.objects.filter(CLASSE__isnull=False)
        pass
    else:
        # Si organe non reconnu ou pas autorisÃ© â€” optionnel : renvoyer vide
        donnees = DATEREV.objects.none()

    # Appliquer les filtres GET si prÃ©sents
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

    # CrÃ©ation du fichier Excel
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

    # 1. RÃ´les et paramÃ¨tres
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]

    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 2. Gestion des Notations (DerniÃ¨re note par agent selon pÃ©rimÃ¨tre)
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    # SÃ©curisation de l'affichage des notes
    if user.organe == "ChargÃ© Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe in users_filiale:
        notation = notation.filter(agent__filiale=user.filiale)
    # Pour le Groupe, on voit toutes les notes (ou filtrer selon besoin)

    # 3. Filtrage du QuerySet Principal (Uniquement CLASSE non vide)
    # Correction : On exclut les vides ET les nuls
    donnees_queryset = DATEREV.objects.filter(Q(RISQUE__isnull=True) | Q(RISQUE=""))

    # Filtrage automatique selon le rÃ´le (SÃ©curitÃ©)
    if user.organe == "ChargÃ© Client":
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
    if user.organe == "ChargÃ© Client":
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


    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Clients non classÃ©s"

    # EntÃªtes
    headers = ['AGENCE', 'AGENCE', 'EXPL', 'CLIENT', 'DATEREV', 'PPE', 'RISQUE']
    ws.append(headers)

    # DonnÃ©es
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.DATEREV, d.PPE, d.RISQUE

        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # PrÃ©parer la rÃ©ponse HTTP
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(output.read(),
                            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"Clients sans classe de risque {date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response




ITEMS_PER_PAGE = 100  # Nombre d'Ã©lÃ©ments Ã  charger par page

from django.shortcuts import render
from django.db.models import Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Kyc_pm, Notation  # Assurez-vous que les imports correspondent Ã  vos fichiers

# --- 1. FONCTION DE SÃ‰CURITÃ‰ PM (PÃ©rimÃ¨tre de donnÃ©es) ---
def get_filtered_queryset_pm(request):
    """Garantit que l'utilisateur ne voit que les entreprises (PM) de son pÃ©rimÃ¨tre."""
    user = request.user
    queryset = Kyc_pm.objects.all()

    if user.organe == "ChargÃ© Client":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)

    elif user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        queryset = queryset.filter(FILIALE=user.filiale)

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]:
        # AccÃ¨s total pour le Groupe
        pass

    return queryset.order_by('id')

# --- 2. FONCTION DES LISTES DE FILTRES PM ---
def get_filter_lists_pm(user, request):
    """GÃ©nÃ¨re les options des menus dÃ©roulants PM selon les droits d'accÃ¨s."""
    filiale_list, agence_list, expl_list, datouv_list = [], [], [], []
    base_qs = Kyc_pm.objects.all()

    # Restriction de la base de donnÃ©es selon le rÃ´le
    if user.organe == "ChargÃ© Client":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        base_qs = base_qs.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        base_qs = base_qs.filter(FILIALE=user.filiale)

    # 1. Liste des Filiales (Uniquement pour le Groupe)
    filiale_list = Kyc_pm.objects.values_list("FILIALE", flat=True).distinct().order_by("FILIALE")

    # 2. Logique dynamique des Agences et Exploitants
    f_filiale = request.GET.get("filiale")
    f_agence = request.GET.get("agence")

    # Agences
    if f_filiale:
        agence_list = Kyc_pm.objects.filter(FILIALE=f_filiale).values_list("AGENCE", flat=True).distinct()
    elif user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        agence_list = base_qs.values_list("AGENCE", flat=True).distinct()

    # Exploitants
    if f_agence:
        expl_list = Kyc_pm.objects.filter(AGENCE=f_agence).values_list("EXPL", flat=True).distinct()
    elif user.organe == "Directeur Agence":
        expl_list = base_qs.values_list("EXPL", flat=True).distinct()
    elif not f_agence and (f_filiale or user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent"]):
        expl_list = base_qs.values_list("EXPL", flat=True).distinct()

    # 3. Dates d'ouverture
    datouv_list = base_qs.exclude(DATOUV__isnull=True).values_list("DATOUV", flat=True).distinct().order_by('-DATOUV')

    return filiale_list, agence_list, expl_list, datouv_list

# --- 3. VUE PRINCIPALE PM ---
def non_rens_pm(request):
    user = request.user

    # A. SÃ©curitÃ© : Queryset restreint au rÃ´le (PM)
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

    # C. Notations (MÃªme logique de sÃ©curitÃ© que PP)
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    if user.organe == "ChargÃ© Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "GUEST"]:
        notation = notation.filter(agent__filiale=user.filiale)

    # D. Listes pour les menus dÃ©roulants
    filiale_list, agence_list, expl_list, datouv_list = get_filter_lists_pm(user, request)

    # E. Pagination et conservation des paramÃ¨tres
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
        "users_filiale": ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©'],
        "users_groupe": ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"],
    }

    return render(request, "non_rens_pm.html", context)

from datetime import datetime
from django.http import HttpResponse
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from io import BytesIO
from .models import Kyc_pm  # VÃ©rifiez le nom de votre modÃ¨le


def export_csv_pm(request):
    user = request.user
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # 1. Base de donnÃ©es initiale
    donnees = Kyc_pm.objects.all()

    # 2. RÃ©cupÃ©ration des paramÃ¨tres de filtrage depuis l'URL
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

    # 3. SÃ©curitÃ© par rÃ´le (PÃ©rimÃ¨tre de l'utilisateur)
    if user.organe == "ChargÃ© Client":
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

    # 5. Conversion et Filtrage par DATE (Crucial pour Ã©viter l'export vide)
    if f_datouv and f_datouv.strip():
        try:
            # On tente de convertir "12/01/2026" en objet date Python
            date_objet = datetime.strptime(f_datouv.strip(), '%d/%m/%Y').date()
            donnees = donnees.filter(DATOUV=date_objet)
        except (ValueError, TypeError):
            # Si la date dans l'URL n'est pas au bon format, on ignore ce filtre
            pass

    # 6. CrÃ©ation du classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Export KYC PM"

    # En-tÃªtes (Headers)
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

    # 7. PrÃ©paration de la rÃ©ponse HTTP pour le tÃ©lÃ©chargement
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

# Assurez-vous que Kyc_pp et Notation sont importÃ©s
# from .models import Kyc_pp, Notation

# --- CONSTANTE DE TAILLE DE PAGE ---
ITEMS_PER_PAGE = 100  # Nombre d'Ã©lÃ©ments Ã  charger par page
from django.shortcuts import render
from django.db.models import Max
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from .models import Kyc_pp, Notation  # VÃ©rifiez le nom de vos modÃ¨les


# --- 1. FONCTION DE SÃ‰CURITÃ‰ (PÃ©rimÃ¨tre de donnÃ©es) ---
def get_filtered_queryset(request):
    """Garantit que l'utilisateur ne voit que son pÃ©rimÃ¨tre autorisÃ©."""
    user = request.user
    queryset = Kyc_pp.objects.all()

    if user.organe == "ChargÃ© Client":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)

    elif user.organe == "Directeur Agence":
        queryset = queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)

    elif user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        queryset = queryset.filter(FILIALE=user.filiale)

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]:
        # Le groupe voit tout par dÃ©faut, le filtrage se fera via le formulaire
        pass

    return queryset.order_by('id')


# --- 2. FONCTION DES LISTES DE FILTRES (Menus dÃ©roulants) ---
def get_filter_lists(user, request):
    """GÃ©nÃ¨re les options des menus dÃ©roulants selon les droits d'accÃ¨s."""
    filiale_list, agence_list, expl_list, datouv_list = [], [], [], []
    base_queryset = Kyc_pp.objects.all()

    if user.organe == "ChargÃ© Client":
        base_queryset = base_queryset.filter(FILIALE=user.filiale, AGENCE= user.agence, EXPL=user.code_expl)
        expl_list = [user.code_expl]

    elif user.organe == "Directeur Agence":
        base_queryset = base_queryset.filter(FILIALE=user.filiale, AGENCE=user.agence)
        expl_list = base_queryset.values_list("EXPL", flat=True).distinct()

    elif user.organe in ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        base_queryset = base_queryset.filter(FILIALE=user.filiale)
        agence_list = base_queryset.values_list("AGENCE", flat=True).distinct()

        agence_filter = request.GET.get("agence")
        if agence_filter:
            expl_list = base_queryset.filter(AGENCE=agence_filter).values_list("EXPL", flat=True).distinct()
        else:
            expl_list = base_queryset.values_list("EXPL", flat=True).distinct()

    elif user.organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                         "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]:
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

    # A. SÃ©curitÃ© de base : Queryset restreint au rÃ´le
    queryset = get_filtered_queryset(request)

    # B. Application des filtres du formulaire (Si renseignÃ©s)
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

    # C. DonnÃ©es de notation (Flux) filtrÃ©es par pÃ©rimÃ¨tre
    notes = Notation.objects.filter(flux_stock='Flux')
    latest_notes = notes.values('agent').annotate(latest_date=Max('date_notation'))
    notation = notes.filter(date_notation__in=[n['latest_date'] for n in latest_notes])

    if user.organe == "ChargÃ© Client":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence,agent__code_expl=user.code_expl)
    elif user.organe == "Directeur Agence":
        notation = notation.filter(agent__filiale=user.filiale, agent__agence=user.agence)
    elif user.organe not in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "GUEST"]:
        notation = notation.filter(agent__filiale=user.filiale)

    # D. Listes pour les menus dÃ©roulants
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
                         "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"],
        'users_filiale': ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©'],
        'notation': notation,
    }

    return render(request, "non_rens.html", context)

def export_csv_pp(request):
    user = request.user
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # Partir de tous les objets
    donnees = Kyc_pp.objects.all()

    # Appliquer les mÃªmes filtres que dans la vue de liste
    # selon lâ€™organe de lâ€™utilisateur + Ã©ventuellement les filtres GET
    if user.organe == "ChargÃ© Client":
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

    # Ensuite crÃ©ation du fichier Excel (ou CSV selon ton besoin)
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
    filename = f"Champs_non_renseignÃ©s_PP_{date_str}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def export_csv_anom(request):
    user = request.user

    users_filiale = ["DSI", "Conformit??", "Contr??le Permanent", "Directeur R??seau",'Risques', 'DAI', 'Qualit??']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

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

        if user.organe == "ChargÃ© Client":
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
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©rer les filtres GET envoyÃ©s par le template
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # Base queryset : anomalies avec PPE = 'O'
    donnees = Anomalie.objects.filter(PPE='O')

    # Filtrer selon le rÃ´le de lâ€™utilisateur
    if user.organe == "ChargÃ© Client":
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

    # CrÃ©ation du classeur Excel
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

def _dashboard_data_cache_version():
    """
    Versionne le cache avec les dates max des tables de taux.
    Quand une injection matinale met Ã  jour les donnÃ©es, la version change.
    """
    latest_filiale = TauxEvolution_filiale.objects.aggregate(last_date=Max('date')).get('last_date')
    latest_expl = TauxEvolution.objects.aggregate(last_date=Max('date')).get('last_date')
    rules_version = cache.get('quality_control_rules_version', 1)
    return f"{latest_filiale or 'none'}|{latest_expl or 'none'}|rules:{rules_version}"


def _build_dashboard_cache_key(prefix, user, request, extra=""):
    scope = "|".join([
        str(getattr(user, "id", "")),
        str(getattr(user, "organe", "")),
        str(getattr(user, "filiale", "")),
        str(getattr(user, "agence", "")),
        str(getattr(user, "code_expl", "")),
        request.GET.urlencode(),
        extra,
        _dashboard_data_cache_version(),
    ])
    scope_hash = hashlib.md5(scope.encode("utf-8")).hexdigest()
    return f"dashboard:{prefix}:{scope_hash}"


@login_required
def statistiques(request):
    context_cache_key = _build_dashboard_cache_key("statistiques", request.user, request)
    cached_context = cache.get(context_cache_key)
    if cached_context is not None:
        return render(request, 'statistiques.html', cached_context)

    user = request.user
    # Liste des roles ayant une vue globale (Groupe)
    user_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]

    # 1. Mode + granularite
    mode = request.GET.get('mode', 'Flux')
    is_stock = (mode == 'Stock')
    code_flux_stock = "S" if is_stock else "F"
    periode = request.GET.get('periode', 'journalier')
    periodes_valides = {'journalier', 'hebdomadaire', 'mensuel', 'annuel'}
    if periode not in periodes_valides:
        periode = 'mensuel'

    # 2. Securisation de la filiale
    target_filiale = getattr(user, 'filiale', None)
    if user.organe in user_groupe:
        f_get = request.GET.get('filiale')
        if f_get:
            target_filiale = f_get
    else:
        target_filiale = user.filiale

    # 3. Exploitant / utilisateur
    selected_user_filter = request.GET.get('utilisateur', '').strip()
    if user.organe == "ChargÃ© Client":
        selected_expl = user.code_expl
    else:
        selected_expl = request.GET.get('expl') or selected_user_filter

    # 4. Donnees moyennes filiale
    latest_filiale_data = TauxEvolution_filiale.objects.filter(filiale=target_filiale).order_by('-date').first()
    if is_stock:
        last_pp_fil = latest_filiale_data.stock_PP if latest_filiale_data else 0
        last_pm_fil = latest_filiale_data.stock_PM if latest_filiale_data else 0
    else:
        last_pp_fil = latest_filiale_data.flux_PP if latest_filiale_data else 0
        last_pm_fil = latest_filiale_data.flux_PM if latest_filiale_data else 0

    # 5. Donnees historiques exploitant selon granularite
    base_qs_expl = TauxEvolution.objects.filter(
        flux_stock=code_flux_stock,
        filiale=target_filiale,
        expl=selected_expl
    ).order_by('date')

    latest_taux_date = (
        TauxEvolution.objects
        .filter(flux_stock=code_flux_stock, filiale=target_filiale)
        .aggregate(last_date=Max('date'))
        .get('last_date')
    )

    def build_period_key(d):
        if periode == 'journalier':
            return d
        if periode == 'hebdomadaire':
            year, week, _ = d.isocalendar()
            return (year, week)
        if periode == 'annuel':
            return d.year
        return (d.year, d.month)

    def format_period_label(key):
        if periode == 'journalier':
            return key.strftime('%d/%m/%Y')
        if periode == 'hebdomadaire':
            return f"S{key[1]}-{key[0]}"
        if periode == 'annuel':
            return str(key)
        return f"{key[1]:02d}/{key[0]}"

    def aggregate_by_period(queryset):
        grouped = {}
        for obj in queryset:
            key = build_period_key(obj.date)
            bucket = grouped.setdefault(key, {"sum": 0.0, "count": 0})
            bucket["sum"] += float(obj.taux or 0)
            bucket["count"] += 1
        return {k: round(v["sum"] / v["count"], 2) for k, v in grouped.items() if v["count"] > 0}

    dict_expl_pp = aggregate_by_period(base_qs_expl.filter(pp_pm="P"))
    dict_expl_pm = aggregate_by_period(base_qs_expl.filter(pp_pm="M"))

    period_keys = sorted(set(dict_expl_pp.keys()) | set(dict_expl_pm.keys()))
    labels_chart = [format_period_label(k) for k in period_keys]
    labels_table = labels_chart[:]
    data_expl_pp = [float(dict_expl_pp.get(k, 0)) for k in period_keys]
    data_expl_pm = [float(dict_expl_pm.get(k, 0)) for k in period_keys]

    var_pp = round(data_expl_pp[-1] - data_expl_pp[-2], 2) if len(data_expl_pp) > 1 else 0
    var_pm = round(data_expl_pm[-1] - data_expl_pm[-2], 2) if len(data_expl_pm) > 1 else 0

    # 6. Liste dynamique des exploitants
    expl_queryset = TauxEvolution.objects.filter(filiale=target_filiale, flux_stock=code_flux_stock)
    if user.organe == "Directeur Agence":
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

    # 7. Notation et identite
    agent_info = ProfileV.objects.filter(filiale=target_filiale, code_expl=selected_expl).first()
    notation_obj = Notation.objects.filter(agent__code_expl=selected_expl, flux_stock=mode).order_by('-date_notation').first()

    # 8. Liste des filiales
    if user.organe in user_groupe:
        liste_filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        liste_filiales = [user.filiale] if user.filiale else []

    quality_scope = evaluate_data_quality_scope(user)
    if selected_expl:
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
        'periode': periode,
        'selected_filiale': target_filiale,
        'selected_expl': selected_expl,
        'selected_user_filter': selected_expl,
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
        'latest_taux_date': latest_taux_date,
    }
    cache.set(context_cache_key, context, timeout=60 * 60 * 8)
    return render(request, 'statistiques.html', context)
def export_stats_pp(request):
    # mÃªme logique de filtrage que dans la vue principale
    user = request.user
    organe = user.organe
    filiale = user.filiale
    expl_user = user.expl

    if organe in ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                  "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]:
        qs = TauxEvolution.objects.all()
    elif organe in ["ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']:
        qs = TauxEvolution.objects.filter(filiale=filiale)
    elif organe == "Directeur Agence":
        qs = TauxEvolution.objects.filter(agence=user.agence)
    elif organe == "ChargÃ© Client":
        qs = TauxEvolution.objects.filter(expl=expl_user)
    else:
        qs = TauxEvolution.objects.none()

    # filtrer Ã©ventuellement sur GET param
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
    # RÃ´les
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    user = request.user

    # Params GET
    periode_param = request.GET.get("periode", "")
    filiale_param = request.GET.get("filiale", "")
    agence_param = request.GET.get("agence", "")
    expl_param = request.GET.get("expl", "")

    base_qs = DATEREV.objects.all().filter(DATEREV__isnull=False, PPE='O')

    if getattr(user, "organe", "") == "ChargÃ© Client":
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

    if getattr(user, "organe", "") == "ChargÃ© Client":
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
        "total_count": donnees.count(), # Optionnel : le total gÃ©nÃ©ral
        "count_risque_non_eleve": count_risque_non_eleve, # Le nouveau dÃ©compte
        # Options
        "filiales": filiales_opts,
        "agences": agences_opts,
        "exploitants": exploitants_opts,

        # SÃ©lections courantes
        "periode": periode_param,
        "filiale_param": selected_filiale,
        "agence_param": selected_agence,
        "expl_param": selected_expl,

        # RÃ´les (si tu en as besoin dans le template)
        "users_groupe": users_groupe,
        "users_filiale": users_filiale,

        # Droits d'Ã©dition des selects
        "can_pick_filiale": can_pick_filiale,
        "can_pick_agence": can_pick_agence,
        "can_pick_expl": can_pick_expl,
    }
    return render(request, 'daterev_ppe.html', context)


def non_anom_ppe(request):
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    donnees = Anomalie.objects.filter(PPE="O")
    # Filtrage automatique selon le rÃ´le
    if user.organe == "ChargÃ© Client":
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

    # === Valeurs du formulaire selon le rÃ´le ===
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
                    "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

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

    if user.organe == "ChargÃ© Client":
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
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau", 'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]

    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # 1. RÃ©cupÃ©rer LA devise de la filiale (on prend la premiÃ¨re trouvÃ©e)
    # On rÃ©cupÃ¨re juste la valeur (ex: "XOF") pour la comparer aux donnÃ©es Kyc_pp
    devise_obj = Devise.objects.filter(filiale=user.filiale).first()
    devise_valeur = devise_obj.devise if devise_obj else None  # Remplacez 'nom_devise' par le nom rÃ©el de votre champ

    # 2. Filtrage de base : Exclure la devise de la filiale et les vides
    donnees = Kyc_pp.objects.exclude(DEVISE=devise_valeur).exclude(DEVISE__isnull=True).exclude(DEVISE="")

    # === Filtrage automatique selon le rÃ´le ===
    if user.organe == "ChargÃ© Client":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence, EXPL=user.code_expl)
    elif user.organe == "Directeur Agence":
        donnees = donnees.filter(FILIALE=user.filiale, AGENCE=user.agence)
    elif user.organe in users_filiale:
        donnees = donnees.filter(FILIALE=user.filiale)
    # Si dans users_groupe, on garde tout (dÃ©jÃ  gÃ©rÃ© par l'absence de filtre)

    # === Filtres manuels via GET ===
    if filiale_param:
        donnees = donnees.filter(FILIALE__icontains=filiale_param)
    if agence_param:
        donnees = donnees.filter(AGENCE__icontains=agence_param)
    if expl_param:
        donnees = donnees.filter(EXPL__icontains=expl_param)
    donnees = _apply_pp_header_filters(donnees, request, include_devise=True)

    # === Valeurs pour les menus dÃ©roulants du formulaire ===
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

    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©ration des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # DÃ©but du Queryset
    donnees = Kyc_pp.objects.filter(~Q(DEVISE=""), DEVISE__isnull=False)

    # === Filtrage automatique selon le rÃ´le (identique Ã  devise) ===
    if user.organe == "ChargÃ© Client":
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

    # Fin du Queryset filtrÃ©

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommÃ© le titre

    # EntÃªtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "CODAPE", "IDP", "PAYNAIS", "PROFESSION", "ADRESSE", "PAYS_RESID",
               "NUMID", "SALAIRE", "ORIGINE_REV", "DATVALID", "TEL"]
    ws.append(headers)

    # DonnÃ©es
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.CODAPE, d.IDP,
            d.PAYNAIS, d.PROFESSION, d.ADRESSE, d.PAYS_RESID, d.NUMID, d.SALAIRE, d.ORIGINE_REV, d.DATVALID, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # PrÃ©parer la rÃ©ponse HTTP
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
    roles_exclus = ["ChargÃ© Client"]
    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = [
        "Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone",
        "ConformitÃ© Groupe", "ContrÃ´le Permanent Groupe", "PASS", "GUEST"
    ]
    user = request.user
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')

    # =========================================================================
    # ðŸŒŸ CORRECTION PRINCIPALE ICI ðŸŒŸ
    # On filtre pour exclure les enregistrements oÃ¹ DEVISE est vide OU NULL.
    # Ceci revient Ã  dire : DEVISE N'EST PAS vide ET DEVISE N'EST PAS NULL.
    # =========================================================================
    donnees = Kyc_pm.objects.filter(~Q(DEVISE="") & Q(DEVISE__isnull=False))
    # Alternative plus concise si DEVISE est un CharField :
    # donnees = Kyc_pp.objects.exclude(DEVISE="").exclude(DEVISE__isnull=True)

    # === Filtrage automatique selon le rÃ´le ===
    if user.organe == "ChargÃ© Client":
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

    # === Valeurs du formulaire selon le rÃ´le ===
    # Ceci doit Ãªtre recalculÃ© aprÃ¨s l'application des filtres pour avoir les listes pertinentes

    # Simuler les listes pour le contexte
    filiales = donnees.values_list('FILIALE', flat=True).distinct()
    agences = donnees.values_list('AGENCE', flat=True).distinct()
    exploitants = donnees.values_list('EXPL', flat=True).distinct()

    # 2. Obtenir le QuerySet filtrÃ©
    # Utilisation de 'donnees' qui contient dÃ©jÃ  le QuerySet filtrÃ©.
    queryset = donnees

    # 3. Appliquer le Paginator
    # Je vais simuler ITEMS_PER_PAGE pour l'exemple
    ITEMS_PER_PAGE = 25
    paginator = Paginator(queryset, ITEMS_PER_PAGE)

    page_number = request.GET.get('page')

    try:
        objets_page = paginator.page(page_number)
    except PageNotAnInteger:
        # Si 'page' n'est pas un entier, afficher la premiÃ¨re page
        objets_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, afficher la derniÃ¨re page
        objets_page = paginator.page(paginator.num_pages)

    context = {
        # 'donnees' est maintenant l'objet Page paginÃ©
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

    users_filiale = ["DSI", "ConformitÃ©", "ContrÃ´le Permanent", "Directeur RÃ©seau",'Risques', 'DAI', 'QualitÃ©']
    users_groupe = ["Directeur Zone UEMOA", "Directeur Zone Centre", "Directeur Zone Anglophone", "ConformitÃ© Groupe",
                    "ContrÃ´le Permanent Groupe", "PASS", "GUEST"]

    # RÃ©cupÃ©ration des filtres GET pour la synchronisation
    filiale_param = request.GET.get('filiale', '')
    agence_param = request.GET.get('agence', '')
    expl_param = request.GET.get('expl', '')


    devise_obj = Devise.objects.filter(filiale=user.filiale).first()
    devise_valeur = devise_obj.devise if devise_obj else None  # Remplacez 'nom_devise' par le nom rÃ©el de votre champ

    # 2. Filtrage de base : Exclure la devise de la filiale et les vides
    donnees = Kyc_pm.objects.exclude(DEVISE=devise_valeur).exclude(DEVISE__isnull=True).exclude(DEVISE="")

    # === Filtrage automatique selon le rÃ´le (identique Ã  devise) ===
    if user.organe == "ChargÃ© Client":
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

    # Fin du Queryset filtrÃ©

    # CrÃ©ation du classeur Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Comptes Devise PP"  # J'ai renommÃ© le titre

    # EntÃªtes
    headers = ["FILIALE", "AGENCE", "EXPL", "CLIENT", "AGEC", "CODAPE", "IDM", "RCSNO", "CAPITAL", "CA",
               "RESULTAT", "TEL"]
    ws.append(headers)

    # DonnÃ©es
    for d in donnees:
        ws.append([
            d.FILIALE, d.AGENCE, d.EXPL, d.CLIENT, d.AGEC, d.CODAPE, d.IDM,
            d.RCSNO, d.CAPITAL, d.CA, d.RESULTAT, d.TEL
        ])

    # Ajustement largeur des colonnes (optionnel)
    for col_num, column_title in enumerate(headers, 1):
        column_letter = get_column_letter(col_num)
        ws.column_dimensions[column_letter].width = 15

    # PrÃ©parer la rÃ©ponse HTTP
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

    if user.organe == "ConformitÃ© Groupe":
        # Groupe : on rÃ©cupÃ¨re toutes les filiales distinctes
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

    elif user.organe == "ConformitÃ©":
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
    context_cache_key = _build_dashboard_cache_key("evolution_filiale", user, request)
    cached_context = cache.get(context_cache_key)
    if cached_context is not None:
        return render(request, 'evolution_par_filiale.html', cached_context)

    users_filiale = ["DSI", "Conformit?", "Contr?le Permanent", "Directeur R?seau", 'Risques', 'DAI', 'Qualit?']

    filiale_sel = request.GET.get('filiale')

    if user.organe in users_filiale:
        filiales = TauxEvolution_filiale.objects.filter(filiale=user.filiale).values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True).distinct().order_by('filiale')

    if not filiale_sel and filiales:
        filiale_sel = filiales[0]

    periode = request.GET.get('periode', 'journalier')
    periodes_valides = {'journalier', 'hebdomadaire', 'mensuel', 'annuel'}
    if periode not in periodes_valides:
        periode = 'journalier'

    rows = list(
        TauxEvolution_filiale.objects
        .filter(filiale=filiale_sel)
        .order_by('date')
        .values_list('date', 'flux_PM', 'flux_PP')
    )
    latest_taux_date = rows[-1][0] if rows else None

    def build_period_key(d):
        if periode == 'journalier':
            return d
        if periode == 'hebdomadaire':
            year, week, _ = d.isocalendar()
            return (year, week)
        if periode == 'annuel':
            return d.year
        return (d.year, d.month)

    def format_period_label(key):
        if periode == 'journalier':
            return key.strftime('%d/%m/%Y')
        if periode == 'hebdomadaire':
            return f"S{key[1]}-{key[0]}"
        if periode == 'annuel':
            return str(key)
        return f"{key[1]:02d}/{key[0]}"

    grouped = {}
    for d, pm, pp in rows:
        key = build_period_key(d)
        bucket = grouped.setdefault(
            key,
            {"sum_pm": 0.0, "sum_pp": 0.0, "count": 0, "latest_date": d},
        )
        bucket["sum_pm"] += float(pm or 0)
        bucket["sum_pp"] += float(pp or 0)
        bucket["count"] += 1
        if d > bucket["latest_date"]:
            bucket["latest_date"] = d

    period_keys = sorted(grouped.keys())
    labels = [format_period_label(k) for k in period_keys]
    data_pm = [round(grouped[k]["sum_pm"] / grouped[k]["count"], 2) for k in period_keys]
    data_pp = [round(grouped[k]["sum_pp"] / grouped[k]["count"], 2) for k in period_keys]
    history_rows = [
        (
            grouped[k]["latest_date"],
            round(grouped[k]["sum_pm"] / grouped[k]["count"], 2),
            round(grouped[k]["sum_pp"] / grouped[k]["count"], 2),
            labels[idx],
        )
        for idx, k in enumerate(period_keys)
    ]

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
        'periode': periode,
        'kpi_pm': kpi_pm,
        'kpi_pp': kpi_pp,
        'quality_rate_pp': compute_quality_rate_by_typology('PP'),
        'quality_rate_pm': compute_quality_rate_by_typology('PM'),
        'quality_scope_label': quality_scope.get('label'),
        'history_rows': list(reversed(history_rows[-10:])),
        'latest_taux_date': latest_taux_date,
    }
    cache.set(context_cache_key, context, timeout=60 * 60 * 8)
    return render(request, 'evolution_par_filiale.html', context)


@login_required
def taux_evolution_view_stock(request):
    user = request.user
    context_cache_key = _build_dashboard_cache_key("evolution_filiale_stock", user, request)
    cached_context = cache.get(context_cache_key)
    if cached_context is not None:
        return render(request, 'evolution_par_filiale_stock.html', cached_context)

    users_filiale = ["DSI", "Conformit?", "Contr?le Permanent", "Directeur R?seau", 'Risques', 'DAI', 'Qualit?']

    filiale_sel = request.GET.get('filiale')

    if user.organe in users_filiale:
        filiales = TauxEvolution_filiale.objects.filter(filiale=user.filiale).values_list('filiale', flat=True).distinct().order_by('filiale')
    else:
        filiales = TauxEvolution_filiale.objects.values_list('filiale', flat=True).distinct().order_by('filiale')

    if not filiale_sel and filiales:
        filiale_sel = filiales[0]

    periode = request.GET.get('periode', 'journalier')
    periodes_valides = {'journalier', 'hebdomadaire', 'mensuel', 'annuel'}
    if periode not in periodes_valides:
        periode = 'journalier'

    rows = list(
        TauxEvolution_filiale.objects
        .filter(filiale=filiale_sel)
        .order_by('date')
        .values_list('date', 'stock_PM', 'stock_PP')
    )
    latest_taux_date = rows[-1][0] if rows else None

    def build_period_key(d):
        if periode == 'journalier':
            return d
        if periode == 'hebdomadaire':
            year, week, _ = d.isocalendar()
            return (year, week)
        if periode == 'annuel':
            return d.year
        return (d.year, d.month)

    def format_period_label(key):
        if periode == 'journalier':
            return key.strftime('%d/%m/%Y')
        if periode == 'hebdomadaire':
            return f"S{key[1]}-{key[0]}"
        if periode == 'annuel':
            return str(key)
        return f"{key[1]:02d}/{key[0]}"

    grouped = {}
    for d, pm, pp in rows:
        key = build_period_key(d)
        bucket = grouped.setdefault(
            key,
            {"sum_pm": 0.0, "sum_pp": 0.0, "count": 0, "latest_date": d},
        )
        bucket["sum_pm"] += float(pm or 0)
        bucket["sum_pp"] += float(pp or 0)
        bucket["count"] += 1
        if d > bucket["latest_date"]:
            bucket["latest_date"] = d

    period_keys = sorted(grouped.keys())
    labels = [format_period_label(k) for k in period_keys]
    data_pm = [round(grouped[k]["sum_pm"] / grouped[k]["count"], 2) for k in period_keys]
    data_pp = [round(grouped[k]["sum_pp"] / grouped[k]["count"], 2) for k in period_keys]
    history_rows = [
        (
            grouped[k]["latest_date"],
            round(grouped[k]["sum_pm"] / grouped[k]["count"], 2),
            round(grouped[k]["sum_pp"] / grouped[k]["count"], 2),
            labels[idx],
        )
        for idx, k in enumerate(period_keys)
    ]

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
        'periode': periode,
        'kpi_pm': kpi_pm,
        'kpi_pp': kpi_pp,
        'quality_rate_pp': compute_quality_rate_by_typology('PP'),
        'quality_rate_pm': compute_quality_rate_by_typology('PM'),
        'quality_scope_label': quality_scope.get('label'),
        'history_rows': list(reversed(history_rows[-10:])),
        'latest_taux_date': latest_taux_date,
    }
    cache.set(context_cache_key, context, timeout=60 * 60 * 8)
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
            messages.error(request, "Veuillez sÃ©lectionner un fichier CSV valide.")
            return redirect('bulk_user_upload')

        try:
            # Lecture du fichier
            data_set = csv_file.read().decode('UTF-8')
            io_string = io.StringIO(data_set)
            next(io_string)  # Sauter l'en-tÃªte

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
                            'tÃ©lÃ©phone': row[4],
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

            messages.success(request, f"{users_created} utilisateurs crÃ©Ã©s avec succÃ¨s. ({errors} erreurs)")

        except Exception as e:
            messages.error(request, f"Erreur lors du traitement : {e}")

    return render(request, 'bulk_upload.html')


from openpyxl import Workbook
from django.http import HttpResponse


def download_excel_template(request):
    # CrÃ©ation d'un nouveau classeur Excel
    wb = Workbook()
    ws = wb.active
    ws.title = "Import Utilisateurs"

    # En-tÃªtes conformes Ã  votre script
    headers = ['username', 'first_name', 'last_name', 'organe', 'tÃ©lÃ©phone', 'password', 'agence', 'expl']
    ws.append(headers)

    # Exemple de donnÃ©es
    ws.append(['m.diop', 'Moussa', 'Diop', 'ConformitÃ©', '771234567', 'Boa2026!', 'Agence Dakar', 'EXPL001'])

    # PrÃ©paration de la rÃ©ponse HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="template_kyc_bulk.xlsx"'

    wb.save(response)
    return response








