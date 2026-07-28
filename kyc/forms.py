from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
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
            'agent': forms.HiddenInput(),                                                

            'note': forms.Select(attrs={
                'class': ' border border-gray-300 rounded-lg shadow-lg'
            }),
            'flux_stock': forms.Select(attrs={
                'class': 'mt-6 border border-gray-300 rounded-lg shadow-lg'
            })
        }

class DataQualityRuleForm(forms.ModelForm):
                                                                                           
    ALL_FILIALES_SENTINEL = '__ALL__'

    filiale = forms.ChoiceField(
        required=False,
        label="Filiale concernée",
        help_text="Une seule filiale (seuils propres au pays) ou « Toutes les filiales ».",
        widget=forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-3 text-sm'}),
    )

    class Meta:
        model = DataQualityRule
        fields = ['name', 'applicability', 'filiale', 'description', 'active', 'control_type', 'field_name', 'parameter']
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
        filiale_choices = kwargs.pop('filiale_choices', None)
        super().__init__(*args, **kwargs)
        self.fields['field_name'].required = False
        self.fields['parameter'].required = False
        self.fields['control_type'].initial = 'composite'
        if filiale_choices is None:
            from kyc.models import Filiales as ModelFiliales
            filiale_choices = [f[0] for f in ModelFiliales]

        concrete = [f for f in (filiale_choices or []) if f]
        raw_current = getattr(self.instance, 'filiale', '') or ''
        current_filiales = self._parse_filiales(raw_current)

        choices = []
                                                                                            
                                                                               
        allow_all = len(concrete) != 1
        if allow_all:
            choices.append((self.ALL_FILIALES_SENTINEL, 'Toutes les filiales'))
        for f in concrete:
            choices.append((f, f))

        existing_values = {value for value, _ in choices}
        if len(current_filiales) > 1:
                                                                                        
                                                                                           
            label = ", ".join(current_filiales) + "  (multi — à scinder par filiale)"
            choices.append((raw_current, label))
            self.initial['filiale'] = raw_current
        elif len(current_filiales) == 1:
            cf = current_filiales[0]
            if cf not in existing_values:
                choices.append((cf, cf))
            self.initial['filiale'] = cf
        else:
                                                                                            
            self.initial['filiale'] = self.ALL_FILIALES_SENTINEL if allow_all else (concrete[0] if concrete else '')

        self.fields['filiale'].choices = choices

    @staticmethod
    def _parse_filiales(value):
        raw = (value or '').strip()
        if not raw:
            return []
        if raw.startswith('|') and raw.endswith('|'):
            return [item for item in raw.strip('|').split('|') if item]
        if ',' in raw:
            return [item.strip() for item in raw.split(',') if item.strip()]
        return [raw]

    @staticmethod
    def _serialize_filiales(values):
        cleaned = []
        for value in values or []:
            item = str(value or '').strip()
            if item and item not in cleaned:
                cleaned.append(item)
        return f"|{'|'.join(cleaned)}|" if cleaned else ''

    def clean_filiale(self):
        value = (self.cleaned_data.get('filiale') or '').strip()
                                                                                         
        if value in ('', self.ALL_FILIALES_SENTINEL):
            return ''
                                                                     
        if value.startswith('|') and value.endswith('|'):
            return value
                                     
        return self._serialize_filiales([value])

class DataQualityConditionForm(forms.ModelForm):
    class Meta:
        model = DataQualityCondition
        fields = ['logic', 'field_name', 'operator', 'value']
        widgets = {
            'logic': forms.Select(attrs={'class': 'js-cond-logic block w-full rounded-xl border border-gray-200 p-2 text-xs font-bold'}),
            'field_name': forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs'}),
            'operator': forms.Select(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs'}),
            'value': forms.TextInput(attrs={'class': 'block w-full rounded-xl border border-gray-200 p-2 text-xs', 'placeholder': 'Valeur ou champ'}),
        }

from django.forms import inlineformset_factory
DataQualityConditionFormSet = inlineformset_factory(
    DataQualityRule, DataQualityCondition,
    form=DataQualityConditionForm,
    fields=['logic', 'field_name', 'operator', 'value'],
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
                                                        
        current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)

                                           
        if current_user and current_user.organe == "DSI":
                                                         
            self.fields['filiale'].initial = current_user.filiale
            self.fields['filiale'].widget.attrs['readonly'] = True
            self.fields['filiale'].disabled = True                           

                                                                                      
        if current_user and current_user.organe != "PASS":
                                                                              
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
                                                                      
        current_user = kwargs.pop('current_user', None)
        super(UserEditForm, self).__init__(*args, **kwargs)

                                                    
        if current_user and current_user.organe == "DSI":
            self.fields['filiale'].disabled = True
            self.fields['filiale'].widget.attrs.update({
                'readonly': True,
                'class': self.fields['filiale'].widget.attrs.get('class', '') + ' bg-gray-100 cursor-not-allowed'
            })

                                                    
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

                                                                          
                                                                                
                                                                             
        if new_password:
            validate_password(new_password, self.instance)
        return cleaned_data

class ProfileForm(forms.ModelForm):
    class Meta:
        model = ProfileV
        fields = ["avatar"]
