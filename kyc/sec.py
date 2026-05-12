import datetime
import hashlib
import json
import struct
from struct import pack
from urllib import request


from django.db.models import Max

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.sites import requests
from django.core.mail import send_mail, BadHeaderError
from django.db.models import Q


from django.shortcuts import render, get_object_or_404, redirect
from django.views import generic

from kyc.models import Notation, Historique
from django.utils import timezone


from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from oauthlib.oauth2.rfc6749.endpoints import token

from accounts.models import ProfileV
from kyc import forms
from kyc.forms import CustomUserCreationForm, LoginForm, ResetPasswordForm, UserEditForm, VoyageurProfileForm, CambProfileForm, \
    ProfileModify, NotationForm




@login_required
def accueil(request):

    return render(request, 'accueil.html')

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


@login_required
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
                        'site_name': 'BuurChange',
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
                              context={"password_reset_form": password_reset_form, "errors":errors})

    password_reset_form = PasswordResetForm()
    return render(request=request, template_name="password_reset.html",
                  context={"password_reset_form": password_reset_form})

@login_required
@csrf_exempt
def profil(request):
    return render(request, 'profil.html')


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


class ChangePasswordView(SuccessMessageMixin,PasswordChangeView):
    template_name = 'modify_pw.html'
    success_message = "Votre mot de passe a été changé avec succès"
    success_url = reverse_lazy('profil')

def reset_user_password(request, user_id):
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            # Enregistrer le nouveau mot de passe en le hachant
            new_password = form.cleaned_data['new_password']
            user.password = make_password(new_password)
            user.save()
            return redirect('user_list')  # Rediriger vers la liste des utilisateurs après modification
    else:
        form = ResetPasswordForm()

    return render(request, 'reset_user_password.html', {'form': form, 'user': user})


@login_required
def perso(request):
    # Récupérer l'utilisateur connecté
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Qualité']:
        agents = ProfileV.objects.filter(filiale=user.filiale)
    else:
        agents = ProfileV.objects.all()
    # Gestion de la recherche par exploitant
    query = request.GET.get('q','')
    if query:
        agents = agents.filter(code_expl__icontains=query)

    return render(request, 'mon_profile.html', {'agents': agents, 'query': query})


@login_required
@csrf_exempt
def agent(request):
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Qualité']:
        notes = Notation.objects.filter(note_par__filiale=user.filiale, flux_stock='Flux')
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

    return render(request, 'agent.html', {'notes': notes, 'query': query})

@csrf_exempt
def perso_stock(request):
    # Récupérer l'utilisateur connecté
    user = request.user

    # Vérifier si l'utilisateur appartient à "Contrôle", "Conformité" ou "Contrôle Groupe"
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Qualité']:
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
    if user.organe in ['Contrôle Permanent', 'Directeur Réseau', 'Conformité','Qualité']:
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
                user =request.user
                # Assigner l'agent à partir du formulaire
                notation = form.save(commit=False)
                notation.filiale = user.filiale
                notation.note_par = request.user
                notation.date_notation= timezone.now()
                notation.save()
                messages.success(request, 'La notation a bien été sauvegardée.')

                return redirect('agent')
    else:
        form = NotationForm()  # Afficher un formulaire vide si la requête n'est pas en POST

    return render(request, 'notation.html', {'form': form, 'agent': agent})


def agent_detail(request, agent_id):
    agent = get_object_or_404(ProfileV, id=agent_id)
    notations = agent.notations.all().order_by('-date_notation')
    return render(request, 'agent_detail.html', {'agent': agent, 'notations': notations})

@login_required
@csrf_exempt
def historique(request):
    query = request.GET.get('q')

    if query:
        # Filtre les notations en fonction du code exploitant
        notations = Notation.objects.filter(note_par=request.user, agent__code_expl__icontains=query).order_by("-date_notation")
    else:
        # Récupère toutes les notations de l'utilisateur connecté
        notations = Notation.objects.filter(note_par=request.user).order_by("-date_notation")

    # Passe les notations au template
    context = {
        'notations': notations,
        'query': query,
    }  # Pour pré-remplir la barre de recherche
    return render(request, 'historique.html', {'notations':notations})

def test(request):
    return render(request, 'test.html')

def register(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            return redirect('user_list')  # Rediriger vers la page d'accueil après l'inscription
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


# Fonction pour vérifier si l'utilisateur appartient à l'organe "PASS"
def is_pass_user(user):
    return user.organe == 'PASS'

  # Limiter l'accès à ceux de l'organe 'PASS'
def user_list(request):
    users = ProfileV.objects.all()  # Récupérer tous les utilisateurs
    return render(request, 'user_list.html', {'users': users})


@user_passes_test(is_pass_user)
def edit_user(request, user_id):
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('user_list')  # Rediriger vers la liste des utilisateurs après modification
    else:
        form = UserEditForm(instance=user)

    return render(request, 'edit_user.html', {'form': form, 'user': user})


@user_passes_test(is_pass_user)
def change_user_password(request, user_id):
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == 'POST':
        form = PasswordChangeForm(user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # Important pour éviter de déconnecter l'utilisateur
            return redirect('user_list')  # Rediriger vers la liste des utilisateurs après modification
    else:
        form = PasswordChangeForm(user)

    return render(request, 'change_user_password.html', {'form': form, 'user': user})



@user_passes_test(is_pass_user)
def reset_user_password(request, user_id):
    user = get_object_or_404(ProfileV, pk=user_id)

    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            # Enregistrer le nouveau mot de passe en le hachant
            new_password = form.cleaned_data['new_password']
            user.password = make_password(new_password)
            user.save()
            return redirect('user_list')  # Rediriger vers la liste des utilisateurs après modification
    else:
        form = ResetPasswordForm()

    return render(request, 'reset_user_password.html', {'form': form, 'user': user})
