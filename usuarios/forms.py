from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Usuario


class RegistroForm(UserCreationForm):
    class Meta:
        model = Usuario
        fields = ["email"]

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya hay una cuenta con ese email.")
        return email


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autofocus": True}))

    def clean(self):
        if self.cleaned_data.get("username"):
            self.cleaned_data["username"] = self.cleaned_data["username"].lower()
        return super().clean()
