from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from finanzas import services
from finanzas.models import Categoria, Cuenta, Recurrente, Transaccion
from finanzas.services import DatosMovimiento

from .conftest import categoria_de
from .factories import CuentaFactory, TransaccionFactory


def datos(cuenta, categoria, **extra):
    base = {"tipo": "gasto", "monto": Decimal("1000"), "fecha": date(2026, 11, 5)}
    return DatosMovimiento(cuenta=cuenta, categoria=categoria, **{**base, **extra})


class TestCrearMovimiento:
    def test_simple_calcula_monto_ars_y_recuerda_cuenta(self, usuario, efectivo, comida):
        [tx] = services.crear_movimiento(usuario, datos(efectivo, comida))
        assert tx.monto_ars == Decimal("1000.00")
        usuario.refresh_from_db()
        assert usuario.ultima_cuenta == efectivo
        assert usuario.ultimo_tipo_cambio is None

    def test_usd_convierte_y_recuerda_tipo_de_cambio(self, usuario, efectivo, comida):
        [tx] = services.crear_movimiento(
            usuario, datos(efectivo, comida, moneda="USD", monto=Decimal("10"), tipo_cambio=Decimal("1200.5"))
        )
        assert tx.monto_ars == Decimal("12005.00")
        usuario.refresh_from_db()
        assert usuario.ultimo_tipo_cambio == Decimal("1200.5")

    def test_usd_sin_tipo_de_cambio_es_invalido(self, usuario, efectivo, comida):
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(efectivo, comida, moneda="USD"))
        assert not Transaccion.objects.exists()

    def test_ars_en_cuenta_usd_pide_tipo_de_cambio(self, usuario, comida):
        cuenta_usd = CuentaFactory(usuario=usuario, moneda="USD")
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(cuenta_usd, comida))

    def test_monto_cero_es_invalido(self, usuario, efectivo, comida):
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(efectivo, comida, monto=Decimal("0")))

    def test_rechaza_cuenta_o_categoria_ajena(self, usuario, otro_usuario, comida):
        ajena = Cuenta.objects.de(otro_usuario).first()
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(ajena, comida))

    def test_repetir_crea_recurrente(self, usuario, efectivo, comida):
        [tx] = services.crear_movimiento(usuario, datos(efectivo, comida, repetir=True, fecha=date(2026, 1, 31)))
        r = Recurrente.objects.get()
        assert tx.recurrente == r
        assert r.dia_del_mes == 31 and r.ultimo_generado == date(2026, 1, 31) and r.activo

    def test_cuotas_y_repetir_a_la_vez_es_invalido(self, usuario, tarjeta, comida):
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(tarjeta, comida, cuotas=3, repetir=True))


class TestCuotas:
    def test_100000_en_3_cuotas(self, usuario, tarjeta, comida):
        filas = services.crear_movimiento(usuario, datos(tarjeta, comida, monto=Decimal("100000"), cuotas=3))
        assert [f.monto for f in filas] == [Decimal("33333.33"), Decimal("33333.33"), Decimal("33333.34")]
        assert [f.cuota for f in filas] == [1, 2, 3]
        assert {f.cuotas for f in filas} == {3}
        assert len({f.grupo_id for f in filas}) == 1
        assert [f.fecha for f in filas] == [date(2026, 11, 5), date(2026, 12, 5), date(2027, 1, 5)]
        assert filas[0].descripcion == "Alimentación (1/3)"

    @pytest.mark.parametrize("monto,n", [("100", 7), ("0.05", 3), ("99999.99", 12), ("1", 60)])
    def test_la_suma_es_siempre_el_total(self, monto, n):
        partes = services.dividir_en_cuotas(Decimal(monto), n)
        assert sum(partes) == Decimal(monto)
        assert len(partes) == n

    def test_fin_de_mes_se_recorta(self, usuario, tarjeta, comida):
        filas = services.crear_movimiento(usuario, datos(tarjeta, comida, cuotas=2, fecha=date(2026, 1, 31)))
        assert [f.fecha for f in filas] == [date(2026, 1, 31), date(2026, 2, 28)]

    def test_rechaza_cuenta_que_no_es_tarjeta(self, usuario, efectivo, comida):
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(efectivo, comida, cuotas=3))

    def test_rechaza_ingreso_en_cuotas(self, usuario, tarjeta, comida):
        with pytest.raises(ValidationError):
            services.crear_movimiento(usuario, datos(tarjeta, comida, tipo="ingreso", cuotas=3))

    def test_rechaza_demasiadas_cuotas(self, usuario, tarjeta, comida):
        with pytest.raises(ValidationError):
            services.crear_en_cuotas(usuario, datos(tarjeta, comida), 61)


class TestEditarYBorrar:
    def test_actualizar_recalcula_monto_ars(self, usuario, efectivo, comida):
        [tx] = services.crear_movimiento(usuario, datos(efectivo, comida))
        services.actualizar_movimiento(
            tx, datos(efectivo, comida, moneda="USD", monto=Decimal("2"), tipo_cambio=Decimal("1000"))
        )
        tx.refresh_from_db()
        assert tx.monto_ars == Decimal("2000.00")

    def test_borrar_todo_el_grupo_o_una_cuota(self, usuario, tarjeta, comida):
        filas = services.crear_movimiento(usuario, datos(tarjeta, comida, cuotas=4))
        assert services.borrar_movimiento(filas[0], todo_el_grupo=False) == 1
        assert Transaccion.objects.count() == 3
        assert services.borrar_movimiento(filas[1], todo_el_grupo=True) == 3
        assert not Transaccion.objects.exists()

    def test_borrar_grupo_no_toca_otro_usuario(self, usuario, otro_usuario):
        tx = TransaccionFactory(usuario=usuario, grupo_id="00000000-0000-0000-0000-000000000001")
        TransaccionFactory(usuario=otro_usuario, grupo_id="00000000-0000-0000-0000-000000000001")
        services.borrar_movimiento(tx, todo_el_grupo=True)
        assert Transaccion.objects.count() == 1


class TestBorrarCategoriaYCuenta:
    def test_sin_uso_se_borra_directo(self, usuario):
        cat = categoria_de(usuario, "Otros")
        services.reasignar_y_borrar(cat)
        assert not Categoria.objects.filter(pk=cat.pk).exists()

    def test_con_uso_pide_destino_y_reasigna(self, usuario, efectivo, comida):
        services.crear_movimiento(usuario, datos(efectivo, comida, repetir=True))
        with pytest.raises(ValidationError):
            services.reasignar_y_borrar(comida)
        with pytest.raises(ValidationError):
            services.reasignar_y_borrar(comida, comida)
        otros = categoria_de(usuario, "Otros")
        services.reasignar_y_borrar(comida, otros)
        assert Transaccion.objects.get().categoria == otros
        assert Recurrente.objects.get().categoria == otros

    def test_destino_de_otro_usuario_o_moneda(self, usuario, otro_usuario, efectivo, comida):
        services.crear_movimiento(usuario, datos(efectivo, comida))
        with pytest.raises(ValidationError):
            services.reasignar_y_borrar(comida, Categoria.objects.de(otro_usuario).first())
        with pytest.raises(ValidationError):
            services.reasignar_y_borrar(efectivo, CuentaFactory(usuario=usuario, moneda="USD"))
        services.reasignar_y_borrar(efectivo, Cuenta.objects.get(usuario=usuario, nombre="Tarjeta"))
        assert services.cantidad_de_usos(Cuenta.objects.get(usuario=usuario, nombre="Tarjeta")) == 1
