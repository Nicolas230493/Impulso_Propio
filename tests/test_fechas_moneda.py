from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from core.fechas import fecha_en_mes, mes_a_texto, parsear_mes, rango_mes, sumar_meses, sumar_meses_a_mes
from core.moneda import convertir_a_ars, convertir_a_moneda, truncar
from core.templatetags.formato import ars, con_mes, dinero, numero, porcentaje


class TestFechas:
    def test_sumar_meses_cruza_anio(self):
        assert sumar_meses_a_mes(date(2026, 11, 1), 3) == date(2027, 2, 1)
        assert sumar_meses_a_mes(date(2026, 1, 1), -1) == date(2025, 12, 1)

    def test_dia_31_se_recorta(self):
        assert fecha_en_mes(date(2026, 2, 1), 31) == date(2026, 2, 28)
        assert fecha_en_mes(date(2028, 2, 1), 31) == date(2028, 2, 29)
        assert sumar_meses(date(2026, 1, 31), 1) == date(2026, 2, 28)
        assert sumar_meses(date(2026, 1, 31), 2) == date(2026, 3, 31)

    def test_rango_y_texto(self):
        assert rango_mes(date(2026, 12, 15)) == (date(2026, 12, 1), date(2027, 1, 1))
        assert mes_a_texto(date(2026, 3, 1)) == "2026-03"

    def test_parsear_mes_invalido_es_el_actual(self, settings):
        assert parsear_mes("2026-07") == date(2026, 7, 1)
        assert parsear_mes("basura") == parsear_mes(None) == parsear_mes("2026-13")
        assert parsear_mes(None).day == 1


class TestMoneda:
    def test_ars_queda_igual(self):
        assert convertir_a_ars(Decimal("10.005"), "ARS") == Decimal("10.01")

    def test_usd_multiplica_y_redondea_half_up(self):
        assert convertir_a_ars(Decimal("10"), "USD", Decimal("1234.5678")) == Decimal("12345.68")
        assert convertir_a_ars(Decimal("0.01"), "USD", Decimal("0.5")) == Decimal("0.01")  # 0.005 -> 0.01

    @pytest.mark.parametrize("tc", [None, Decimal("0"), Decimal("-1")])
    def test_usd_sin_tipo_de_cambio_es_invalido(self, tc):
        with pytest.raises(ValidationError):
            convertir_a_ars(Decimal("10"), "USD", tc)

    def test_convertir_a_moneda_de_cuenta(self):
        assert convertir_a_moneda(Decimal("10"), "USD", Decimal("1000"), "ARS") == Decimal("10000")
        assert convertir_a_moneda(Decimal("1000"), "ARS", Decimal("1000"), "USD") == Decimal("1")
        assert convertir_a_moneda(Decimal("5"), "USD", None, "USD") == Decimal("5")

    def test_truncar(self):
        assert truncar(Decimal("33333.3333")) == Decimal("33333.33")


class TestFormato:
    def test_dinero(self):
        assert dinero(Decimal("1234.5")) == "$ 1.234,50"
        assert dinero(Decimal("-1234567.891"), "USD") == "US$ -1.234.567,89"
        assert ars(None) == "" and dinero("") == "" and numero("x") == ""

    def test_porcentaje(self):
        assert porcentaje(Decimal("12.4")) == "+12 %"
        assert porcentaje(Decimal("-5")) == "-5 %"
        assert porcentaje(None) == ""

    def test_con_mes(self):
        assert con_mes({"mes": "2026-11"}, "/movimientos/") == "/movimientos/?mes=2026-11"
        assert con_mes({"mes": "2026-11"}, "/x/?a=1") == "/x/?a=1&mes=2026-11"
