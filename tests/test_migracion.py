"""La migración sobre un 'dump' de prueba deja conteos y sumas idénticos, y es idempotente."""

from datetime import date, datetime
from decimal import Decimal

import bcrypt
import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command

from finanzas.models import Categoria, Cuenta, Recurrente, Transaccion
from finanzas.services import saldo_a_hoy
from metas.models import MetaAhorro
from reportes.services import resumen_mes
from scripts.migrar_supabase import ErrorMigracion, Reporte, migrar, resumen

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"
HOY = date(2026, 11, 7)


class OrigenFalso:
    def __init__(self, usuarios, tablas):
        self._usuarios, self._tablas = usuarios, tablas

    def usuarios(self):
        return self._usuarios

    def filas(self, tabla):
        return self._tablas.get(tabla, [])


def dump():
    hash_a = bcrypt.hashpw(b"clave-de-a", bcrypt.gensalt(rounds=4, prefix=b"2a")).decode()
    tx = lambda i, **f: {  # noqa: E731
        "id": f"t{i}", "user_id": A, "tipo": "gasto", "monto": "100", "categoria": "Alimentación",
        "fecha": "2026-10-05", "descripcion": None, "cuenta_id": "c-efectivo", "moneda": "ARS",
        "tipo_cambio": 1, "grupo_id": None, "cuota": None, "cuotas": None, "recurrente_id": None, **f,
    }  # fmt: skip
    return OrigenFalso(
        usuarios=[
            {"id": A, "email": "A@Ejemplo.com", "encrypted_password": hash_a, "created_at": datetime(2026, 9, 1)},
            {"id": B, "email": "b@ejemplo.com", "encrypted_password": "", "created_at": None},
            {"id": "sin-email", "email": None},
        ],
        tablas={
            "cuentas": [
                {
                    "id": "c-efectivo",
                    "user_id": A,
                    "nombre": "Efectivo",
                    "tipo": "efectivo",
                    "moneda": "ARS",
                    "saldo_inicial": "5000",
                },
                {
                    "id": "c-tarjeta",
                    "user_id": A,
                    "nombre": "Visa",
                    "tipo": "tarjeta",
                    "moneda": "ARS",
                    "saldo_inicial": 0,
                },
                {
                    "id": "c-usd",
                    "user_id": A,
                    "nombre": "Dólares",
                    "tipo": "efectivo",
                    "moneda": "USD",
                    "saldo_inicial": "300",
                },
            ],
            "categorias": [
                {"id": "k1", "user_id": A, "nombre": "Alimentación", "tope_mensual": "50000"},
                {"id": "k2", "user_id": A, "nombre": "Salario", "tope_mensual": None},
                {"id": "k3", "user_id": B, "nombre": "Otros", "tope_mensual": None},
            ],
            "recurrentes": [
                {
                    "id": "r1",
                    "user_id": A,
                    "tipo": "ingreso",
                    "monto": "900000",
                    "categoria": "Salario",
                    "cuenta_id": "c-efectivo",
                    "moneda": "ARS",
                    "tipo_cambio": 1,
                    "descripcion": "Sueldo",
                    "dia": 31,
                    "ultimo_mes": "2026-10",
                },
            ],
            "transacciones": [
                tx(1),
                tx(
                    2,
                    tipo="ingreso",
                    monto="900000",
                    categoria="Salario",
                    fecha="2026-10-31",
                    recurrente_id="r1",
                    descripcion="Sueldo",
                ),
                tx(3, monto="10", moneda="USD", tipo_cambio="1180.5", cuenta_id="c-usd"),
                tx(
                    4,
                    monto="33333.33",
                    cuenta_id="c-tarjeta",
                    grupo_id="aaaaaaaa-0000-0000-0000-000000000001",
                    cuota=1,
                    cuotas=3,
                ),
                tx(
                    5,
                    monto="33333.33",
                    cuenta_id="c-tarjeta",
                    grupo_id="aaaaaaaa-0000-0000-0000-000000000001",
                    cuota=2,
                    cuotas=3,
                    fecha="2026-11-05",
                ),
                tx(
                    6,
                    monto="33333.34",
                    cuenta_id="c-tarjeta",
                    grupo_id="aaaaaaaa-0000-0000-0000-000000000001",
                    cuota=3,
                    cuotas=3,
                    fecha="2026-12-05",
                ),
                tx(7, categoria="Categoría borrada", cuenta_id=None, descripcion="x" * 250),
                tx(8, monto="2000", moneda="ARS", cuenta_id="c-usd"),  # ARS en cuenta USD con TC 1 (bug viejo)
                tx(9, user_id=B, categoria="Otros", cuenta_id=None, monto="1"),
            ],
            "metas": [
                {
                    "id": "m1",
                    "user_id": A,
                    "titulo": "Viaje",
                    "monto_objetivo": "100000",
                    "monto_actual": "2500",
                    "por_que": "Descansar",
                    "fecha_limite": "2027-01-15",
                },
                {
                    "id": "m2",
                    "user_id": B,
                    "titulo": "Raro",
                    "monto_objetivo": "0",
                    "monto_actual": "0",
                    "por_que": None,
                    "fecha_limite": None,
                },
            ],
        },
    )


@pytest.fixture
def migrado(db):
    return migrar(dump(), al=HOY)


def usuario_a():
    return get_user_model().objects.get(email="a@ejemplo.com")


def test_conteos(migrado):
    assert migrado.usuarios == 2
    assert dict(migrado.conteos) == {"cuentas": 3, "categorias": 3, "recurrentes": 1, "transacciones": 9, "metas": 2}
    a = usuario_a()
    assert Cuenta.objects.de(a).count() == 4  # + "Sin cuenta (migración)"
    assert Categoria.objects.de(a).count() == 3  # + "Categoría borrada"
    assert Transaccion.objects.de(a).count() == 8
    assert "sin-email" in " ".join(migrado.avisos)


def test_no_crea_datos_iniciales_para_migrados(migrado):
    a = usuario_a()
    assert not Categoria.objects.de(a).filter(nombre="Vivienda").exists()


def test_sumas_y_saldos(migrado):
    a = usuario_a()
    octubre = resumen_mes(a, date(2026, 10, 1))
    assert octubre["ingresos"] == Decimal("900000")
    # 100 + 11805 (USD) + 33333.33 + 100 (sin cuenta) + 2000 (ARS en cuenta USD)
    assert octubre["gastos"] == Decimal("47338.33")
    assert saldo_a_hoy(Cuenta.objects.get(usuario=a, nombre="Efectivo"), al=HOY) == Decimal("904900")
    assert saldo_a_hoy(Cuenta.objects.get(usuario=a, nombre="Visa"), al=HOY) == Decimal("-66666.66")
    assert saldo_a_hoy(Cuenta.objects.get(usuario=a, nombre="Dólares"), al=HOY) == Decimal("-1710")


def test_detalles_conservados(migrado):
    a = usuario_a()
    cuotas = Transaccion.objects.de(a).filter(grupo_id__isnull=False).order_by("cuota")
    assert [c.cuota for c in cuotas] == [1, 2, 3] and {c.cuotas for c in cuotas} == {3}
    usd = Transaccion.objects.get(usuario=a, moneda="USD")
    assert usd.tipo_cambio == Decimal("1180.5") and usd.monto_ars == Decimal("11805")
    assert Transaccion.objects.get(usuario=a, monto=100, cuenta__nombre="Efectivo").tipo_cambio is None
    r = Recurrente.objects.get(usuario=a)
    assert r.ultimo_generado == date(2026, 10, 31) and r.dia_del_mes == 31
    assert Transaccion.objects.get(recurrente=r).fecha == date(2026, 10, 31)
    assert len(Transaccion.objects.get(usuario=a, cuenta__nombre__startswith="Sin cuenta").descripcion) == 200
    meta = MetaAhorro.objects.get(usuario=a)
    assert meta.fecha_limite == date(2027, 1, 15) and meta.monto_actual == Decimal("2500")
    assert Categoria.objects.get(usuario=a, nombre="Alimentación").tope_mensual == Decimal("50000")


def test_contrasenas(migrado, client):
    assert migrado.sin_contrasena == ["b@ejemplo.com"]
    assert not get_user_model().objects.get(email="b@ejemplo.com").has_usable_password()
    assert client.login(email="a@ejemplo.com", password="clave-de-a")
    assert not usuario_a().password.startswith("supabase_bcrypt$")


def test_avisos_y_resumen(migrado):
    texto = resumen(migrado)
    assert "Categoría borrada" in texto and "Sin cuenta" in texto and "recortado" in texto
    assert "ARS sobre cuenta USD" in texto and "objetivo 0" in texto
    assert f"{A} -> {usuario_a().pk}" in texto


def test_idempotente(migrado):
    segundo = migrar(dump(), al=HOY)
    assert segundo.conteos == migrado.conteos
    assert Transaccion.objects.count() == 9 and get_user_model().objects.count() == 2


def test_no_pisa_contrasena_ya_cambiada_en_django(migrado):
    a = usuario_a()
    a.set_password("nueva-en-django")
    a.save()
    migrar(dump(), al=HOY)
    assert usuario_a().check_password("nueva-en-django")


def test_recurrente_duplicado_se_migra_sin_vinculo(db):
    origen = dump()
    duplicado = dict(origen._tablas["transacciones"][1], id="t-dup")
    origen._tablas["transacciones"].append(duplicado)
    reporte = migrar(origen, al=HOY)
    assert any("duplicado" in a for a in reporte.avisos)
    assert Transaccion.objects.filter(recurrente__isnull=False).count() == 1


def test_diferencia_en_la_verificacion_revierte_todo(db):
    origen = dump()
    origen._tablas["transacciones"][0]["monto"] = "100.005"  # el destino guarda 2 decimales
    with pytest.raises(ErrorMigracion, match="verificación no cierra"):
        migrar(origen, al=HOY)
    assert not get_user_model().objects.exists() and not Transaccion.objects.exists()


def test_monto_invalido_frena(db):
    origen = dump()
    origen._tablas["transacciones"][0]["monto"] = "0"
    with pytest.raises(ErrorMigracion, match="monto 0"):
        migrar(origen, Reporte(), al=HOY)


def test_comando_sin_origen(db, monkeypatch):
    monkeypatch.setenv("SUPABASE_DATABASE_URL", "")
    with pytest.raises(CommandError, match="Falta --origen"):
        call_command("migrar_supabase")


def test_comando_simulacro_y_real(db, monkeypatch, capsys):
    import scripts.migrar_supabase as modulo
    from core.management.commands import migrar_supabase as comando

    class OrigenComando:
        def __init__(self, url):
            self.interno = dump()

        def usuarios(self):
            return self.interno.usuarios()

        def filas(self, tabla):
            return self.interno.filas(tabla)

        def cerrar(self):
            pass

    monkeypatch.setattr(comando, "OrigenSupabase", OrigenComando)
    monkeypatch.setattr(comando, "migrar", lambda origen: modulo.migrar(origen, al=HOY))
    call_command("migrar_supabase", origen="postgres://falso", simulacro=True)
    assert "Simulacro" in capsys.readouterr().out
    assert not Transaccion.objects.exists()
    call_command("migrar_supabase", origen="postgres://falso")
    assert "verificada" in capsys.readouterr().out
    assert Transaccion.objects.count() == 9

    def falla(origen):
        raise ErrorMigracion("no cierra")

    monkeypatch.setattr(comando, "migrar", falla)
    with pytest.raises(CommandError, match="revertida"):
        call_command("migrar_supabase", origen="postgres://falso")
