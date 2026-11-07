from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from .models import Moneda

CENTAVO = Decimal("0.01")


def redondear(valor) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def truncar(valor) -> Decimal:
    return Decimal(valor).quantize(CENTAVO, rounding=ROUND_DOWN)


def validar_tipo_cambio(tipo_cambio):
    if tipo_cambio is None or Decimal(tipo_cambio) <= 0:
        raise ValidationError({"tipo_cambio": "Cargá el tipo de cambio para un movimiento en dólares."})


def convertir_a_ars(monto, moneda, tipo_cambio=None) -> Decimal:
    """ARS queda igual; USD se multiplica por el tipo de cambio. Siempre a 2 decimales."""
    if moneda == Moneda.ARS:
        return redondear(monto)
    validar_tipo_cambio(tipo_cambio)
    return redondear(Decimal(monto) * Decimal(tipo_cambio))


def convertir_a_moneda(monto, moneda, tipo_cambio, moneda_destino) -> Decimal:
    """Convierte un monto a la moneda de una cuenta (ARS <-> USD)."""
    if moneda == moneda_destino:
        return Decimal(monto)
    validar_tipo_cambio(tipo_cambio)
    if moneda_destino == Moneda.ARS:
        return Decimal(monto) * Decimal(tipo_cambio)
    return Decimal(monto) / Decimal(tipo_cambio)
