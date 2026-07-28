from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login, logout, authenticate
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash

                         
from accounts.models import ProfileV

User = get_user_model()

                                                                                
                                                                           
                                                                            
                                                                         
def login_kyc(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user:
            if user.force_password_change:
                                                                            
                                                      
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
        return redirect('login')                    

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('login')

    if request.method == 'POST':
        form = SetPasswordForm(user, request.POST)
        if form.is_valid():
            form.save()
                                   
            user.force_password_change = False
            user.save()
                                                                        
                                                      
            auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
                                                          
            update_session_auth_hash(request, user)
            return redirect('profil')
    else:
        form = SetPasswordForm(user)

    return render(request, 'accounts/force_password_change.html', {'form': form})


def logout_user(request):
    logout(request)
    return redirect('/')