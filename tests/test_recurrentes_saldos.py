from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from finanzas import services
from finanzas.models import Transaccion

from .factories import CuentaFactory, RecurrenteFactory, TransaccionFactory


def fechas(recurrente):
    return list(Transaccion.objects.filter(recurrente=recurrente).order_by("fecha").values_list("fecha", flat=True))


class TestRecurrentes:
    def test_dia_31_genera_28_de_febrero(self, usuario):
        r = RecurrenteFactory(usuario=usuario, dia_del_mes=31, ultimo_generado=date(2026, 1, 31))
        services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 31))
        assert fechas(r) == [date(2026, 2, 28), date(2026, 3, 31)]
        r.refresh_from_db()
        assert r.ultimo_generado == date(2026, 3, 31)

    def test_29_de_febrero_en_bisiesto(self, usuario):
        r = RecurrenteFactory(usuario=usuario, dia_del_mes=31, ultimo_generado=date(2028, 1, 31))
        services.generar_recurrentes_pendientes(usuario, hasta=date(2028, 2, 29))
        assert fechas(r) == [date(2028, 2, 29)]

    def test_no_duplica_si_se_corre_dos_veces(self, usuario):
        r = RecurrenteFactory(usuario=usuario)
        assert services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 15)) == 2
        assert services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 15)) == 0
        assert len(fechas(r)) == 2

    def test_no_duplica_aunque_ultimo_generado_quede_atrasado(self, usuario):
        """Simula dos procesos: el segundo ve el ultimo_generado viejo pero la restricción única lo frena."""
        r = RecurrenteFactory(usuario=usuario)
        services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 15))
        type(r).objects.filter(pk=r.pk).update(ultimo_generado=date(2026, 1, 10))
        assert services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 15)) == 0
        assert len(fechas(r)) == 2

    def test_genera_todos_los_meses_faltantes(self, usuario):
        r = RecurrenteFactory(usuario=usuario, ultimo_generado=date(2025, 11, 10))
        services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 5, 9))
        assert fechas(r) == [
            date(2025, 12, 10),
            date(2026, 1, 10),
            date(2026, 2, 10),
            date(2026, 3, 10),
            date(2026, 4, 10),
        ]

    def test_detenido_no_genera(self, usuario):
        r = RecurrenteFactory(usuario=usuario)
        services.detener_recurrente(r)
        assert services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 6, 1)) == 0

    def test_sin_ultimo_generado_arranca_en_el_mes_de_alta(self, usuario):
        r = RecurrenteFactory(usuario=usuario, ultimo_generado=None, dia_del_mes=1)
        services.generar_recurrentes_pendientes(usuario, hasta=r.creado.date())
        assert fechas(r) == [r.creado.date().replace(day=1)]

    def test_usd_usa_el_ultimo_tipo_de_cambio_del_usuario(self, usuario):
        r = RecurrenteFactory(usuario=usuario, moneda="USD", monto=Decimal("10"), tipo_cambio=Decimal("900"))
        services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 2, 10))
        assert Transaccion.objects.get(recurrente=r).monto_ars == Decimal(
            "9000.00"
        )  # sin dato del usuario: el del alta
        usuario.ultimo_tipo_cambio = Decimal("1100")
        usuario.save()
        services.generar_recurrentes_pendientes(usuario, hasta=date(2026, 3, 10))
        assert Transaccion.objects.get(recurrente=r, fecha=date(2026, 3, 10)).monto_ars == Decimal("11000.00")

    def test_comando_diario(self, usuario, otro_usuario, capsys):
        RecurrenteFactory(usuario=usuario, ultimo_generado=date(2020, 1, 10))
        RecurrenteFactory(usuario=otro_usuario, activo=False)
        call_command("generar_recurrentes")
        assert "para 1 usuarios" in capsys.readouterr().out
        assert Transaccion.objects.filter(usuario=usuario).count() > 60
        assert not Transaccion.objects.filter(usuario=otro_usuario).exists()


class TestSaldoAHoy:
    def test_cuota_futura_no_afecta_el_saldo(self, usuario):
        cuenta = CuentaFactory(usuario=usuario, saldo_inicial=Decimal("1000"), tipo="tarjeta")
        TransaccionFactory(usuario=usuario, cuenta=cuenta, monto=Decimal("100"), fecha=date(2026, 11, 1))
        TransaccionFactory(usuario=usuario, cuenta=cuenta, monto=Decimal("100"), fecha=date(2026, 12, 1))
        TransaccionFactory(usuario=usuario, cuenta=cuenta, tipo="ingreso", monto=Decimal("50"), fecha=date(2026, 11, 7))
        assert services.saldo_a_hoy(cuenta, al=date(2026, 11, 7)) == Decimal("950.00")

    def test_cuenta_usd_con_movimientos_en_ambas_monedas(self, usuario):
        cuenta = CuentaFactory(usuario=usuario, moneda="USD", saldo_inicial=Decimal("100"))
        TransaccionFactory(
            usuario=usuario, cuenta=cuenta, moneda="USD", monto=Decimal("10"), tipo_cambio=Decimal("1000")
        )
        TransaccionFactory(
            usuario=usuario, cuenta=cuenta, moneda="ARS", monto=Decimal("5000"), tipo_cambio=Decimal("1000")
        )
        assert services.saldo_a_hoy(cuenta, al=date(2026, 11, 30)) == Decimal("85.00")

    def test_cuenta_ars_con_gasto_en_usd(self, usuario):
        cuenta = CuentaFactory(usuario=usuario)
        TransaccionFactory(
            usuario=usuario, cuenta=cuenta, moneda="USD", monto=Decimal("1"), tipo_cambio=Decimal("1000")
        )
        assert services.saldo_a_hoy(cuenta, al=date(2026, 11, 30)) == Decimal("-1000.00")


@pytest.mark.django_db
def test_monto_ars_se_calcula_al_guardar():
    tx = TransaccionFactory(moneda="USD", monto=Decimal("3"), tipo_cambio=Decimal("1000.333"))
    assert tx.monto_ars == Decimal("3001.00")
