from django import forms
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login, logout, authenticate
from django.views.decorators.csrf import csrf_exempt

from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash

# Create your views here.
from accounts.models import ProfileV
from kyc.forms import Utilisateur
from kyc.models import Person

User = get_user_model()

# SECURITE: @csrf_exempt retiré — la protection CSRF Django est activée globalement
def register(request):
    formCamb = Utilisateur()
    if len(request.GET) > 0:
        formCamb = Utilisateur(request.GET)
        if formCamb.is_valid():
            formCamb.save()
            return redirect('')
        else:
            return render(request, 'accounts/register.html', {'formCamb': formCamb})
    return render(request, 'accounts/register.html', {'formCamb': formCamb})

# SECURITE: @csrf_exempt retiré — le login doit être protégé contre les attaques CSRF
def login_kyc(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user:
            if user.force_password_change:
                # Rediriger vers le formulaire de changement de mot de passe
                # (ne pas faire login() tout de suite)
                request.session['force_pw_user_id'] = user.id
                return redirect('force_password_change')
            else:
                login(request, user)
                return redirect('profil')
        else:
            error = 'Adresse courriel ou mot de passe invalide.'
            return render(request, 'accounts/login_kyc.html', {'error': error})
    return render(request, 'accounts/login_kyc.html')



User = get_user_model()

def force_password_change(request):
    user_id = request.session.get('force_pw_user_id')
    if not user_id:
        return redirect('login')  # ou autre logique

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
            # mettre à jour le flag
            user.force_password_change = False
            user.save()
            # connecter l'utilisateur
            auth_login(request, user)
            # (optionnel) mettre à jour le hash de session
            update_session_auth_hash(request, user)
            return redirect('profil')
    else:
        form = SetPasswordForm(user)

    return render(request, 'accounts/force_password_change.html', {'form': form})


def logout_user(request):
    logout(request)
    return redirect('/')