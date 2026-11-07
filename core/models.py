from django.conf import settings
from django.db import models


class UserOwnedQuerySet(models.QuerySet):
    def de(self, usuario):
        """Único punto de entrada a datos de un usuario: nunca armar un queryset sin esto."""
        if not getattr(usuario, "is_authenticated", False):
            return self.none()
        return self.filter(usuario=usuario)


class UserOwnedModel(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)

    objects = UserOwnedQuerySet.as_manager()

    class Meta:
        abstract = True


class Moneda(models.TextChoices):
    ARS = "ARS", "ARS"
    USD = "USD", "USD"


class TipoMovimiento(models.TextChoices):
    GASTO = "gasto", "Gasto"
    INGRESO = "ingreso", "Ingreso"
