from decimal import Decimal

from django.db import models
from django.db.models import Q

from core.models import UserOwnedModel


class MetaAhorro(UserOwnedModel):
    """No se llama Meta para no chocar con `class Meta`."""

    titulo = models.CharField(max_length=120)
    monto_objetivo = models.DecimalField(max_digits=14, decimal_places=2)
    monto_actual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    por_que = models.TextField("el porqué", blank=True)
    fecha_limite = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["fecha_limite", "creado"]
        verbose_name = "meta de ahorro"
        verbose_name_plural = "metas de ahorro"
        constraints = [models.CheckConstraint(condition=Q(monto_objetivo__gt=0), name="meta_objetivo_positivo")]

    def __str__(self):
        return self.titulo

    @property
    def porcentaje(self) -> int:
        if not self.monto_objetivo:
            return 0
        return int(min(self.monto_actual / self.monto_objetivo * 100, Decimal(100)))

    @property
    def falta(self) -> Decimal:
        return max(self.monto_objetivo - self.monto_actual, Decimal(0))
