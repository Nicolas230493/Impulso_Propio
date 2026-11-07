from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse

from .fechas import mes_de_request


class UsuarioQuerysetMixin(LoginRequiredMixin):
    """Toda vista sobre datos del usuario: un id ajeno da 404."""

    def get_queryset(self):
        return self.model.objects.de(self.request.user)


class FormConUsuarioMixin:
    """Pasa el usuario al form, que filtra sus ModelChoiceField."""

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["usuario"] = self.request.user
        return kwargs


class MesMixin:
    @property
    def mes(self):
        return mes_de_request(self.request)


def es_htmx(request) -> bool:
    return request.headers.get("HX-Request") == "true"


def respuesta_vacia():
    """Para hx-swap='outerHTML' que debe eliminar el elemento."""
    return HttpResponse("")
