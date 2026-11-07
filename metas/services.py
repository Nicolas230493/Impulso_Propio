from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import MetaAhorro


@transaction.atomic
def aportar(meta: MetaAhorro, monto) -> MetaAhorro:
    """Suma un aporte al monto actual de la meta (con F() para no pisar aportes simultáneos)."""
    if monto is None or Decimal(monto) <= 0:
        raise ValidationError({"monto": "El aporte tiene que ser mayor a cero."})
    MetaAhorro.objects.filter(pk=meta.pk).update(monto_actual=F("monto_actual") + Decimal(monto))
    meta.refresh_from_db()
    return meta
