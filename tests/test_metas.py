from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from metas.services import aportar

from .factories import MetaFactory


def test_aportar_suma(usuario):
    meta = aportar(MetaFactory(usuario=usuario), Decimal("100"))
    assert meta.monto_actual == Decimal("350")
    assert meta.porcentaje == 35 and meta.falta == Decimal("650")


@pytest.mark.parametrize("monto", [None, Decimal("0"), Decimal("-5")])
def test_aporte_invalido(usuario, monto):
    with pytest.raises(ValidationError):
        aportar(MetaFactory(usuario=usuario), monto)


def test_porcentaje_tope_100(usuario):
    meta = MetaFactory(usuario=usuario, monto_actual=Decimal("5000"))
    assert meta.porcentaje == 100 and meta.falta == 0
