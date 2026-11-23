import json

from django import forms
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from gigs.models import Musician, Band

# ==========================================
# --- HELPER MIXINS ---
# ==========================================

class StyledFormMixin:
    """
    Mixin to automatically apply standard Bootstrap classes and 
    custom CSS variables to all form fields for UI consistency.
    """
    def apply_custom_styles(self):
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-control mb-2'
            field.widget.attrs['style'] = (
                'background-color: var(--card-bg, #2a2a35); '
                'color: #fff; '
                'border: 1px solid var(--border-dim, #444);'
            )


# ==========================================
# --- AUTHENTICATION FORMS ---
# ==========================================

class UserSignUpForm(StyledFormMixin, UserCreationForm):
    """
    Custom user registration form requiring an email address.
    """
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ['username', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_custom_styles()
        
        # Add dynamic placeholders for the signup form specifically
        for field_name, field in self.fields.items():
            if field.label:
                field.widget.attrs['placeholder'] = f'Enter your {field.label.lower()}'


# ==========================================
# --- PROFILE MANAGEMENT FORMS ---
# ==========================================

class MusicianProfileForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a Musician's profile details."""
    class Meta:
        model = Musician
        fields = ['instruments', 'bio', 'age', 'profile_picture', 'media_link', 'location']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_custom_styles()


class BandProfileForm(StyledFormMixin, forms.ModelForm):
    """Form for editing a Band or Venue's profile details."""
    class Meta:
        model = Band
        fields = ['name', 'location', 'bio', 'profile_picture']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_custom_styles()


# ==========================================
# --- PROFILE EDIT (AJAX) INPUT FORMS ---
# ==========================================
# These validate the payload sent by the "My profile" page before anything is
# written. The field names match the keys the page sends, not the model fields.

class AccountEditForm(forms.Form):
    """Account details shared by musicians and bands."""
    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    firstname = forms.CharField(max_length=150, required=False)
    surname = forms.CharField(max_length=150, required=False)

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.exclude(pk=self.user.pk).filter(username=username).exists():
            raise forms.ValidationError('That username is already taken.', code='username_taken')
        return username


class MusicianEditForm(forms.Form):
    about = forms.CharField(max_length=500)
    instruments = forms.CharField(max_length=100)
    # Blank means "leave the saved age unchanged", as before.
    age = forms.IntegerField(required=False, min_value=0, max_value=150)
    profile_picture = forms.ImageField(required=False)
    media_links = forms.Field(required=False)
    delete_media = forms.Field(required=False)

    @staticmethod
    def _json_list(value, field_name):
        if value in (None, ''):
            return []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                raise forms.ValidationError('Must be a list.', code='invalid')
        if not isinstance(value, list):
            raise forms.ValidationError('Must be a list.', code='invalid')
        return value

    def clean_media_links(self):
        url_field = forms.URLField()
        links = []
        for item in self._json_list(self.cleaned_data.get('media_links'), 'media_links'):
            if not isinstance(item, str):
                raise forms.ValidationError('Each link must be text.', code='invalid')
            item = item.strip()
            if item:
                links.append(url_field.clean(item))
        return links

    def clean_delete_media(self):
        ids = []
        for item in self._json_list(self.cleaned_data.get('delete_media'), 'delete_media'):
            # The page may include placeholder ids such as "pending-1" for links not yet saved.
            if isinstance(item, int) and not isinstance(item, bool):
                ids.append(item)
            elif isinstance(item, str) and item.isdigit():
                ids.append(int(item))
        return ids


class BandEditForm(forms.Form):
    about = forms.CharField(max_length=500)
    # Blank means "leave the saved name unchanged", as before.
    band_name = forms.CharField(max_length=50, required=False)
    profile_picture = forms.ImageField(required=False)
