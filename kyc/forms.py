from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from accounts.models import ProfileV
from kyc.models import Person, Notation, Profile, DataQualityRule, DataQualityCondition

NoteChoices = (
    ('4', 'Très Bien'),
    ('3', 'Bien'),
    ('2', 'Passable'),
    ('1', 'Insuffisant'),
)




class LoginForm(forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Mot de passe',
                               widget=forms.PasswordInput)
    def clean(self):
        cleaned_data=super (LoginForm, self).clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")
        if email and password:
            result = Person.objects.filter(password=password,
                                           email=email)
            if len(result) !=1 :
                raise forms.ValidationError("Adresse courriel ou mot de passe erroné.")
        return cleaned_data

class VoyageurProfileForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username', 'first_name', 'last_name', 'téléphone']
        exclude = ('friends',)

class CambProfileForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username', 'first_name', 'last_name', 'filiale', 'téléphone']
        exclude = ('friends',)

class ProfileModify(forms.ModelForm):
    class Meta:
        model = get_user_model()
        fields = ['téléphone']

class NotationForm(forms.ModelForm):
    class Meta:
        model = Notation
        fields = ['agent', 'note', 'flux_stock', 'recommandation']
        widgets = {
            'agent': forms.HiddenInput(),  # Masquer le champ agent, car il est prérempli

            'note': forms.Select(attrs={
                'class': ' border border-gray-300 rounded-lg shadow-lg'
            }),
            'flux_stock': forms.Select(attrs={
                'class': 'mt-6 border border-gray-300 rounded-lg shadow-lg'
            })
        }

class DataQualityRuleForm(forms.ModelForm):
    class Meta:
        model = DataQualityRule
        fields = ['name', 'applicability', 'description', 'active', 'control_type', 'field_name', 'parameter']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-3 text-sm'}),
            'applicability': forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-3 text-sm'}),
            'description': forms.Textarea(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-3 text-sm', 'rows': 4}),
            'active': forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-green-700 border-gray-300 rounded'}),
            'control_type': forms.HiddenInput(),
            'field_name': forms.HiddenInput(),
            'parameter': forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['field_name'].required = False
        self.fields['parameter'].required = False
        self.fields['control_type'].initial = 'composite'

class DataQualityConditionForm(forms.ModelForm):
    class Meta:
        model = DataQualityCondition
        fields = ['field_name', 'operator', 'value']
        widgets = {
            'field_name': forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs'}),
            'operator': forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs'}),
            'value': forms.TextInput(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs', 'placeholder': 'Valeur ou champ'}),
        }

from django.forms import inlineformset_factory
DataQualityConditionFormSet = inlineformset_factory(
    DataQualityRule, DataQualityCondition, 
    form=DataQualityConditionForm, 
    fields=['field_name', 'operator', 'value'],
    extra=1, can_delete=True
)

class SearchForm(forms.Form):
    expl = forms.CharField(label='Code Exploitant', max_length=10, required=False)

class Utilisateur(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ['username', 'first_name', 'last_name', 'organe', 'filiale',  'téléphone']
        exclude = ('friends',)



class CustomUserCreationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        # Récupérer l'utilisateur connecté depuis la vue
        current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)

        # Si l'utilisateur connecté est DSI
        if current_user and current_user.organe == "DSI":
            # Forcer le champ filiale à la filiale du DSI
            self.fields['filiale'].initial = current_user.filiale
            self.fields['filiale'].widget.attrs['readonly'] = True
            self.fields['filiale'].disabled = True  # empêche la modification

        # Si l’utilisateur est autre (non PASS), on peut aussi restreindre des organes
        if current_user and current_user.organe != "PASS":
            # Exemple : interdire de créer des utilisateurs avec organe "PASS"
            self.fields['organe'].choices = [
                (o, o) for o in dict(self.fields['organe'].choices).keys() if o != "PASS"
            ]

    class Meta:
        model = ProfileV
        fields = ('username', 'first_name', 'last_name', 'filiale', 'organe', 'agence', 'code_expl','téléphone', 'password1', 'password2')

        widgets = {
            'username': forms.EmailInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'filiale': forms.Select(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'organe': forms.Select(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),

            'agence': forms.TextInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'code_expl': forms.TextInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),

            'téléphone': forms.TextInput(attrs={
                'class': 'mt-2 mb-4 block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        return user

class UserEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        # ✅ On récupère l’utilisateur connecté avant d’appeler super()
        current_user = kwargs.pop('current_user', None)
        super(UserEditForm, self).__init__(*args, **kwargs)

        # ✅ Si l'utilisateur est DSI → filiale figée
        if current_user and current_user.organe == "DSI":
            self.fields['filiale'].disabled = True
            self.fields['filiale'].widget.attrs.update({
                'readonly': True,
                'class': self.fields['filiale'].widget.attrs.get('class', '') + ' bg-gray-100 cursor-not-allowed'
            })

        # ✅ Si ce n’est ni PASS ni DSI → organe figé
        elif current_user and current_user.organe not in ["PASS", "DSI"]:
            self.fields['organe'].disabled = True
            self.fields['organe'].widget.attrs.update({
                'readonly': True,
                'class': self.fields['organe'].widget.attrs.get('class', '') + ' bg-gray-100 cursor-not-allowed'
            })

    class Meta:
        model = ProfileV
        fields = ('username', 'first_name', 'last_name', 'filiale', 'organe', 'agence', 'code_expl','téléphone')


class ResetPasswordForm(forms.ModelForm):
    new_password = forms.CharField(widget=forms.PasswordInput, label="Nouveau mot de passe")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirmer le mot de passe")
    force_password_change = forms.BooleanField(
        required=False,
        initial=True,
        label="Forcer le changement de mot de passe",
        widget=forms.CheckboxInput(attrs={
            'class': 'h-4 w-4 text-green-600 border-gray-300 rounded focus:ring-green-600'
        })
    )

    class Meta:
        model = ProfileV
        fields = ['new_password', 'confirm_password']
        widgets = {
            'new_password': forms.PasswordInput(attrs={
                'class': ' mt-2 mb-4 text-gray-700 block w-full  rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
            'confirm_password': forms.PasswordInput(attrs={
                'class': ' mt-2 mb-4 text-gray-700 block w-full  rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_password = cleaned_data.get("confirm_password")

        if new_password != confirm_password:
            raise forms.ValidationError("Les mots de passe ne correspondent pas.")
        return cleaned_data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = ProfileV
        fields = ["avatar"]
