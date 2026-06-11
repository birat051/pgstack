"""
Signup: ``name`` is stored on ``User.first_name`` (single field mapping per PR checklist).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.services import username_for_normalized_email

User = get_user_model()


class LoginForm(AuthenticationForm):
    """Login fields styled for the design system ``field__input`` widget class."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault('class', 'field__input')


class SignupForm(forms.Form):
    """Collect and validate signup input before ``services.register_user`` creates the ``User``."""

    max_name_len = User._meta.get_field('first_name').max_length

    name = forms.CharField(label='Full name', max_length=max_name_len, strip=True)
    email = forms.EmailField(max_length=User._meta.get_field('email').max_length or 254)
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password_confirm = forms.CharField(
        label='Confirm password',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['name'].widget.attrs.update({
            'class': 'field__input',
            'placeholder': 'Ada Lovelace',
            'autocomplete': 'name',
        })
        self.fields['email'].widget.attrs.update({
            'class': 'field__input',
            'placeholder': 'ada@example.com',
            'autocomplete': 'email',
        })
        for field_name in ('password', 'password_confirm'):
            self.fields[field_name].widget.attrs.update({
                'class': 'field__input',
                'placeholder': '••••••••••••',
            })

    def clean_name(self) -> str:
        name = self.cleaned_data['name'].strip()
        if not name:
            raise ValidationError('Enter your name.')
        return name[: self.max_name_len]

    def clean_email(self) -> str:
        raw = self.cleaned_data['email'].strip()
        normalized = User.objects.normalize_email(raw)
        if normalized == '':
            raise ValidationError('Enter a valid email address.')
        # Unique signup: Django default User.email is non-unique in schema; enforce case-insensitive here.
        if User.objects.filter(username__iexact=username_for_normalized_email(normalized)).exists():
            raise ValidationError('A user with this email already exists.')
        if User.objects.filter(email__iexact=normalized).exists():
            raise ValidationError('A user with this email already exists.')
        return normalized

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password')
        p2 = cleaned.get('password_confirm')
        if p1 or p2:
            if not p2:
                raise ValidationError({'password_confirm': 'Confirm your password.'})
            if not p1:
                raise ValidationError({'password': 'Enter a password.'})
            if p1 != p2:
                raise ValidationError({'password_confirm': 'Passwords do not match.'})
            validate_password(
                p1,
                User(
                    username=username_for_normalized_email(cleaned.get('email', '')),
                    email=cleaned.get('email', ''),
                    first_name=(cleaned.get('name') or '')[: self.max_name_len],
                ),
            )
        return cleaned
