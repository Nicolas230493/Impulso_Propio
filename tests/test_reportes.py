from datetime import date
from decimal import Decimal

import pytest

from reportes import services

from .conftest import categoria_de
from .factories import TransaccionFactory

NOV = date(2026, 11, 1)
OCT = date(2026, 10, 1)


@pytest.fixture
def con_tope(usuario):
    cat = categoria_de(usuario, "Alimentación")
    cat.tope_mensual = Decimal("1000")
    cat.save()
    return cat


def gasto(usuario, categoria, monto, fecha=date(2026, 11, 5), **extra):
    return TransaccionFactory(usuario=usuario, categoria=categoria, monto=Decimal(monto), fecha=fecha, **extra)


class TestResumen:
    def test_suma_en_ars_solo_del_mes(self, usuario, comida):
        gasto(usuario, comida, "100")
        gasto(usuario, comida, "2", moneda="USD", tipo_cambio=Decimal("1000"))
        gasto(usuario, comida, "500", tipo="ingreso")
        gasto(usuario, comida, "999", fecha=date(2026, 10, 31))
        assert services.resumen_mes(usuario, NOV) == {
            "ingresos": Decimal("500"), "gastos": Decimal("2100"), "saldo": Decimal("-1600"),
        }  # fmt: skip

    def test_mes_vacio(self, usuario):
        assert services.resumen_mes(usuario, NOV)["saldo"] == 0

    def test_no_mezcla_usuarios(self, usuario, otro_usuario, comida):
        gasto(usuario, comida, "100")
        assert services.resumen_mes(otro_usuario, NOV)["gastos"] == 0


class TestAlertas:
    @pytest.mark.parametrize(
        "gastado,nivel",
        [("790", None), ("800", "amarilla"), ("1000", "amarilla"), ("1000.01", "roja")],
    )
    def test_umbrales(self, usuario, con_tope, gastado, nivel):
        gasto(usuario, con_tope, gastado)
        alertas = services.alertas_presupuesto(usuario, NOV)
        assert [a.nivel for a in alertas] == ([nivel] if nivel else [])

    def test_usa_el_mes_filtrado(self, usuario, con_tope):
        gasto(usuario, con_tope, "1500", fecha=date(2026, 10, 3))
        assert services.alertas_presupuesto(usuario, NOV) == []
        [alerta] = services.alertas_presupuesto(usuario, OCT)
        assert alerta.nivel == "roja" and alerta.porcentaje == 150

    def test_categoria_sin_tope_no_alerta(self, usuario, comida):
        gasto(usuario, comida, "1000000")
        assert services.alertas_presupuesto(usuario, NOV) == []

    def test_ordena_por_porcentaje(self, usuario, con_tope):
        otra = categoria_de(usuario, "Transporte")
        otra.tope_mensual = Decimal("100")
        otra.save()
        gasto(usuario, con_tope, "850")
        gasto(usuario, otra, "200")
        assert [a.categoria.nombre for a in services.alertas_presupuesto(usuario, NOV)] == [
            "Transporte",
            "Alimentación",
        ]


class TestComparaciones:
    def test_variacion_sin_mes_anterior_no_divide_por_cero(self):
        assert services.variacion(Decimal("100"), Decimal("0")) is None
        assert services.variacion(Decimal("0"), Decimal("0")) is None
        assert services.variacion(Decimal("150"), Decimal("100")) == Decimal("50")

    def test_mes_vs_anterior(self, usuario, comida):
        transporte = categoria_de(usuario, "Transporte")
        gasto(usuario, comida, "300")
        gasto(usuario, comida, "200", fecha=date(2026, 10, 1))
        gasto(usuario, transporte, "50", fecha=date(2026, 10, 1))
        r = services.comparar_con_mes_anterior(usuario, NOV)
        filas = {f["categoria"]: f for f in r["filas"]}
        assert filas["Alimentación"]["variacion"] == Decimal("50")
        assert filas["Transporte"]["actual"] == 0 and filas["Transporte"]["variacion"] == Decimal("-100")
        assert r["total"]["actual"] == Decimal("300") and r["total"]["anterior"] == Decimal("250")

    def test_ultimos_6_meses(self, usuario, comida):
        gasto(usuario, comida, "100", fecha=date(2026, 5, 20))  # el mes extra, solo para la variación de junio
        gasto(usuario, comida, "200", fecha=date(2026, 6, 1))
        gasto(usuario, comida, "1000", fecha=date(2026, 11, 30), tipo="ingreso")
        meses = services.ultimos_meses(usuario, NOV)
        assert [m["mes"] for m in meses] == [date(2026, m, 1) for m in range(6, 12)]
        assert meses[0]["gastos"] == Decimal("200") and meses[0]["variacion"] == Decimal("100")
        assert meses[1]["variacion"] == Decimal("-100")
        assert meses[-1]["ingresos"] == Decimal("1000") and meses[-1]["es_actual"]

    def test_datos_graficos(self, usuario, comida):
        gasto(usuario, comida, "100")
        datos = services.datos_graficos(usuario, NOV)
        assert datos["categorias"] == {"etiquetas": ["Alimentación"], "valores": [100.0]}
        assert datos["balance"] == {"ingresos": 0.0, "gastos": 100.0}


class TestCSV:
    def test_formato_para_excel(self, usuario, comida):
        gasto(usuario, comida, "1234.5", descripcion='Café; "rico"')
        gasto(usuario, comida, "10", moneda="USD", tipo_cambio=Decimal("1000"))
        gasto(usuario, comida, "1", fecha=date(2026, 10, 1))
        contenido = "".join(services.exportar_csv(usuario, NOV))
        assert contenido.startswith("﻿Fecha;Tipo;Categoría;Cuenta;Descripción;Moneda;Monto;Tipo de cambio;Monto ARS\r\n")
        lineas = contenido.split("\r\n")
        assert len(lineas) == 4  # encabezado + 2 movimientos + línea final vacía
        assert ';"Café; ""rico""";ARS;1234,50;;1234,50' in lineas[1]
        assert lineas[2].endswith(";USD;10,00;1000,00;10000,00")
        assert contenido.encode("utf-8").startswith(b"\xef\xbb\xbf")

    def test_backup_completo(self, usuario, comida):
        gasto(usuario, comida, "1")
        gasto(usuario, comida, "1", fecha=date(2020, 1, 1))
        assert len(list(services.exportar_csv(usuario))) == 3
