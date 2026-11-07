from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from finanzas.models import Categoria, Cuenta, Recurrente, Transaccion
from metas.models import MetaAhorro
from usuarios.hashers import SupabaseBcryptHasher

from .factories import MetaFactory, RecurrenteFactory, TransaccionFactory

HTMX = {"HTTP_HX_REQUEST": "true"}


class TestRegistroYLogin:
    def test_registro_crea_5_categorias_y_3_cuentas(self, client, db):
        r = client.post(
            reverse("registro"),
            {"email": "Nuevo@Ejemplo.com", "password1": "una-clave-larga-9", "password2": "una-clave-larga-9"},
        )
        assert r.status_code == 302
        usuario = get_user_model().objects.get(email="nuevo@ejemplo.com")
        assert sorted(Categoria.objects.de(usuario).values_list("nombre", flat=True)) == [
            "Alimentación", "Otros", "Salario", "Transporte", "Vivienda",
        ]  # fmt: skip
        assert Cuenta.objects.de(usuario).count() == 3
        assert client.get(reverse("reportes:dashboard")).status_code == 200

    def test_registro_rechaza_email_repetido_y_clave_debil(self, client, usuario):
        r = client.post(reverse("registro"), {"email": usuario.email.upper(), "password1": "123", "password2": "123"})
        assert r.status_code == 200
        assert "email" in r.context["form"].errors and "password2" in r.context["form"].errors

    def test_login_por_email_genera_recurrentes(self, client, usuario):
        RecurrenteFactory(usuario=usuario, ultimo_generado=date(2026, 1, 10))
        r = client.post(reverse("login"), {"username": usuario.email.upper(), "password": "clave-segura-123"})
        assert r.status_code == 302
        assert Transaccion.objects.filter(usuario=usuario).exists()

    def test_login_con_hash_de_supabase_y_rehash(self, client, usuario):
        import bcrypt

        hash_supabase = bcrypt.hashpw(b"clave-vieja", bcrypt.gensalt(rounds=4, prefix=b"2a")).decode()
        usuario.password = SupabaseBcryptHasher.desde_supabase(hash_supabase)
        usuario.save()
        assert client.post(reverse("login"), {"username": usuario.email, "password": "otra"}).status_code == 200
        assert client.post(reverse("login"), {"username": usuario.email, "password": "clave-vieja"}).status_code == 302
        usuario.refresh_from_db()
        assert not usuario.password.startswith("supabase_bcrypt$")
        assert usuario.check_password("clave-vieja")

    def test_hasher_no_genera_hashes_y_resume(self):
        hasher = SupabaseBcryptHasher()
        encoded = hasher.desde_supabase("$2a$10$" + "a" * 53)
        assert hasher.safe_summary(encoded)["algoritmo"] == "supabase_bcrypt"
        assert hasher.verify("x", "supabase_bcrypt$basura") is False
        with pytest.raises(NotImplementedError):
            hasher.encode("x", "sal")

    def test_logout_por_post(self, cliente):
        assert cliente.post(reverse("logout")).status_code == 302
        assert cliente.get(reverse("reportes:dashboard")).status_code == 302

    def test_password_reset_manda_mail(self, client, usuario):
        r = client.post(reverse("password_reset"), {"email": usuario.email})
        assert r.status_code == 302
        assert len(mail.outbox) == 1 and "/password-reset/" in mail.outbox[0].body

    @pytest.mark.parametrize(
        "nombre", ["reportes:dashboard", "finanzas:movimientos", "finanzas:cuentas", "metas:lista", "reportes:reportes"]
    )
    def test_requiere_login(self, client, db, nombre):
        r = client.get(reverse(nombre))
        assert r.status_code == 302 and r.url.startswith("/login/")


class TestAislamiento:
    """Un usuario B que pide un objeto del usuario A recibe 404."""

    @pytest.fixture
    def objetos_de_a(self, usuario):
        return {
            "movimiento": TransaccionFactory(usuario=usuario),
            "cuenta": Cuenta.objects.de(usuario).first(),
            "categoria": Categoria.objects.de(usuario).first(),
            "recurrente": RecurrenteFactory(usuario=usuario),
            "meta": MetaFactory(usuario=usuario),
        }

    RUTAS = [
        ("finanzas:movimiento_editar", "movimiento", "get"),
        ("finanzas:movimiento_editar", "movimiento", "post"),
        ("finanzas:movimiento_borrar", "movimiento", "get"),
        ("finanzas:movimiento_borrar", "movimiento", "post"),
        ("finanzas:cuenta_editar", "cuenta", "get"),
        ("finanzas:cuenta_editar", "cuenta", "post"),
        ("finanzas:cuenta_borrar", "cuenta", "get"),
        ("finanzas:cuenta_borrar", "cuenta", "post"),
        ("finanzas:categoria_editar", "categoria", "get"),
        ("finanzas:categoria_editar", "categoria", "post"),
        ("finanzas:categoria_borrar", "categoria", "get"),
        ("finanzas:categoria_borrar", "categoria", "post"),
        ("finanzas:recurrente_detener", "recurrente", "post"),
        ("metas:editar", "meta", "get"),
        ("metas:editar", "meta", "post"),
        ("metas:borrar", "meta", "get"),
        ("metas:borrar", "meta", "post"),
        ("metas:aportar", "meta", "post"),
    ]

    @pytest.mark.parametrize("ruta,clave,metodo", RUTAS)
    def test_404_sobre_datos_ajenos(self, client, otro_usuario, objetos_de_a, ruta, clave, metodo):
        client.force_login(otro_usuario)
        r = getattr(client, metodo)(reverse(ruta, args=[objetos_de_a[clave].pk]), {"monto": "1"})
        assert r.status_code == 404

    def test_los_datos_de_a_siguen_intactos(self, client, otro_usuario, objetos_de_a):
        client.force_login(otro_usuario)
        for ruta, clave, metodo in self.RUTAS:
            if metodo == "post":
                client.post(reverse(ruta, args=[objetos_de_a[clave].pk]), {"monto": "1"})
        assert Transaccion.objects.filter(pk=objetos_de_a["movimiento"].pk).exists()
        assert Recurrente.objects.get(pk=objetos_de_a["recurrente"].pk).activo
        assert MetaAhorro.objects.get(pk=objetos_de_a["meta"].pk).monto_actual == Decimal("250")

    def test_listas_y_formularios_no_muestran_datos_ajenos(self, client, usuario, otro_usuario, objetos_de_a):
        client.force_login(otro_usuario)
        Cuenta.objects.filter(usuario=usuario, nombre="Efectivo").update(nombre="Secreta de A")
        r = client.get(reverse("reportes:dashboard"))
        assert "Secreta de A" not in r.content.decode()
        assert client.get(reverse("finanzas:movimientos") + "?mes=2026-11").context["movimientos"].count() == 0

    def test_no_acepta_ids_ajenos_en_el_form(self, client, usuario, otro_usuario):
        client.force_login(otro_usuario)
        r = client.post(
            reverse("finanzas:movimiento_nuevo"),
            {
                "tipo": "gasto", "monto": "10", "fecha": "2026-11-05", "moneda": "ARS", "cuotas": "1",
                "categoria": Categoria.objects.de(usuario).first().pk, "cuenta": Cuenta.objects.de(usuario).first().pk,
            },
        )  # fmt: skip
        assert r.status_code == 200
        assert set(r.context["form"].errors) == {"categoria", "cuenta"}
        assert not Transaccion.objects.exists()


def form_movimiento(usuario, **extra):
    datos = {
        "tipo": "gasto",
        "monto": "1500",
        "fecha": "2026-11-05",
        "moneda": "ARS",
        "tipo_cambio": "",
        "cuotas": "1",
        "categoria": Categoria.objects.get(usuario=usuario, nombre="Alimentación").pk,
        "cuenta": Cuenta.objects.get(usuario=usuario, nombre="Efectivo").pk,
        "descripcion": "Súper",
    }
    return {**datos, **extra}


class TestMovimientos:
    def test_dashboard_precarga_ultima_cuenta_y_tc(self, cliente, usuario, tarjeta):
        usuario.ultima_cuenta, usuario.ultimo_tipo_cambio = tarjeta, Decimal("1234.5")
        usuario.save()
        form = cliente.get(reverse("reportes:dashboard")).context["form"]
        assert form.initial["cuenta"] == tarjeta.pk and form.initial["tipo_cambio"] == Decimal("1234.5")

    def test_alta_simple_redirige_al_mes(self, cliente, usuario):
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario))
        assert r.status_code == 302 and r.url == "/movimientos/?mes=2026-11"
        assert Transaccion.objects.get().monto_ars == Decimal("1500")

    def test_alta_respeta_next_seguro(self, cliente, usuario):
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, next="/?mes=2026-11"))
        assert r.url == "/?mes=2026-11"
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, next="https://malo.com/"))
        assert r.url == "/movimientos/?mes=2026-11"

    def test_tipo_de_cambio_oculto_se_ignora_en_ars(self, cliente, usuario):
        cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, tipo_cambio="1000"))
        assert Transaccion.objects.get().tipo_cambio is None

    def test_usd_sin_tipo_de_cambio_muestra_error(self, cliente, usuario):
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, moneda="USD"))
        assert r.status_code == 200 and "tipo_cambio" in r.context["form"].errors

    def test_cuotas_en_tarjeta(self, cliente, usuario, tarjeta):
        cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, cuenta=tarjeta.pk, cuotas="3"))
        assert Transaccion.objects.count() == 3

    def test_cuotas_ocultas_se_ignoran_si_no_es_tarjeta(self, cliente, usuario):
        cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, cuotas="3"))
        assert Transaccion.objects.count() == 1

    def test_cuotas_y_repetir_es_error(self, cliente, usuario, tarjeta):
        datos = form_movimiento(usuario, cuenta=tarjeta.pk, cuotas="3", repetir="on")
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), datos)
        assert "repetir" in r.context["form"].errors

    def test_repetir(self, cliente, usuario):
        r = cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, repetir="on"))
        assert r.status_code == 302 and Recurrente.objects.filter(usuario=usuario).count() == 1

    def test_listado_y_edicion(self, cliente, usuario):
        cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario))
        tx = Transaccion.objects.get()
        r = cliente.get(reverse("finanzas:movimientos") + "?mes=2026-11")
        assert "Súper" in r.content.decode()
        assert cliente.get(reverse("finanzas:movimiento_editar", args=[tx.pk])).status_code == 200
        r = cliente.post(reverse("finanzas:movimiento_editar", args=[tx.pk]), form_movimiento(usuario, monto="99"))
        assert r.status_code == 302
        tx.refresh_from_db()
        assert tx.monto == Decimal("99")

    def test_edicion_invalida(self, cliente, usuario):
        tx = TransaccionFactory(usuario=usuario, cuenta=Cuenta.objects.get(usuario=usuario, nombre="Efectivo"))
        r = cliente.post(reverse("finanzas:movimiento_editar", args=[tx.pk]), form_movimiento(usuario, moneda="USD"))
        assert r.status_code == 200

    def test_borrar_con_htmx_devuelve_vacio(self, cliente, usuario):
        tx = TransaccionFactory(usuario=usuario)
        r = cliente.post(reverse("finanzas:movimiento_borrar", args=[tx.pk]), **HTMX)
        assert r.status_code == 200 and r.content == b""
        assert not Transaccion.objects.exists()

    def test_borrar_grupo_pregunta_y_borra_todo(self, cliente, usuario, tarjeta):
        cliente.post(reverse("finanzas:movimiento_nuevo"), form_movimiento(usuario, cuenta=tarjeta.pk, cuotas="3"))
        tx = Transaccion.objects.first()
        assert "Todas las cuotas" in cliente.get(reverse("finanzas:movimiento_borrar", args=[tx.pk])).content.decode()
        cliente.post(reverse("finanzas:movimiento_borrar", args=[tx.pk]), {"todo_el_grupo": "1"})
        assert not Transaccion.objects.exists()


class TestPantallas:
    def test_dashboard_con_alertas_y_graficos(self, cliente, usuario, comida):
        comida.tope_mensual = Decimal("100")
        comida.save()
        TransaccionFactory(usuario=usuario, categoria=comida, monto=Decimal("150"), fecha=date(2026, 11, 2))
        html = cliente.get(reverse("reportes:dashboard") + "?mes=2026-11").content.decode()
        assert "Tope superado" in html and 'id="datos-grafico"' in html and "$ 150,00" in html

    def test_reportes(self, cliente, usuario):
        TransaccionFactory(usuario=usuario, fecha=date(2026, 10, 2))
        r = cliente.get(reverse("reportes:reportes") + "?mes=2026-11")
        assert r.status_code == 200 and len(r.context["meses"]) == 6

    def test_exportar(self, cliente, usuario):
        TransaccionFactory(usuario=usuario)
        r = cliente.get(reverse("reportes:exportar_mes") + "?mes=2026-11")
        assert r["Content-Disposition"] == 'attachment; filename="movimientos-2026-11.csv"'
        assert b"".join(r.streaming_content).startswith("﻿".encode())
        r = cliente.get(reverse("reportes:exportar_backup"))
        assert r["Content-Disposition"].startswith('attachment; filename="movimientos-backup-')

    def test_cuentas_crud(self, cliente, usuario):
        assert cliente.get(reverse("finanzas:cuentas")).status_code == 200
        r = cliente.post(
            reverse("finanzas:cuenta_nueva"),
            {"nombre": "Dólares", "tipo": "efectivo", "moneda": "USD", "saldo_inicial": "100"},
        )
        assert r.status_code == 302
        cuenta = Cuenta.objects.get(usuario=usuario, nombre="Dólares")
        r = cliente.post(
            reverse("finanzas:cuenta_nueva"),
            {"nombre": "dólares", "tipo": "efectivo", "moneda": "USD", "saldo_inicial": "0"},
        )
        assert "nombre" in r.context["form"].errors
        cliente.post(
            reverse("finanzas:cuenta_editar", args=[cuenta.pk]),
            {"nombre": "USD", "tipo": "efectivo", "moneda": "USD", "saldo_inicial": "5"},
        )
        cuenta.refresh_from_db()
        assert cuenta.nombre == "USD" and cuenta.saldo_inicial == 5
        assert cliente.post(reverse("finanzas:cuenta_borrar", args=[cuenta.pk])).status_code == 302
        assert not Cuenta.objects.filter(pk=cuenta.pk).exists()

    def test_no_cambia_moneda_de_cuenta_con_movimientos(self, cliente, usuario, efectivo):
        TransaccionFactory(usuario=usuario, cuenta=efectivo)
        r = cliente.post(
            reverse("finanzas:cuenta_editar", args=[efectivo.pk]),
            {"nombre": "Efectivo", "tipo": "efectivo", "moneda": "USD", "saldo_inicial": "0"},
        )
        assert "moneda" in r.context["form"].errors

    def test_categoria_con_movimientos_se_reasigna(self, cliente, usuario, comida):
        TransaccionFactory(usuario=usuario, categoria=comida)
        r = cliente.get(reverse("finanzas:categoria_borrar", args=[comida.pk]))
        assert "Pasar los movimientos a" in r.content.decode()
        r = cliente.post(reverse("finanzas:categoria_borrar", args=[comida.pk]))
        assert r.status_code == 200 and Categoria.objects.filter(pk=comida.pk).exists()
        otros = Categoria.objects.get(usuario=usuario, nombre="Otros")
        r = cliente.post(reverse("finanzas:categoria_borrar", args=[comida.pk]), {"destino": otros.pk})
        assert r.status_code == 302 and Transaccion.objects.get().categoria == otros

    def test_categorias_con_consumo_y_alta(self, cliente, usuario):
        assert cliente.get(reverse("finanzas:categorias")).status_code == 200
        cliente.post(reverse("finanzas:categoria_nueva"), {"nombre": "Salidas", "tope_mensual": "5000"})
        assert Categoria.objects.get(usuario=usuario, nombre="Salidas").tope_mensual == 5000
        cat = Categoria.objects.get(usuario=usuario, nombre="Salidas")
        r = cliente.post(
            reverse("finanzas:categoria_editar", args=[cat.pk]), {"nombre": "Salidas!", "tope_mensual": ""}
        )
        assert r.status_code == 302

    def test_recurrentes_detener_con_htmx(self, cliente, usuario):
        r = RecurrenteFactory(usuario=usuario)
        assert cliente.get(reverse("finanzas:recurrentes")).status_code == 200
        respuesta = cliente.post(reverse("finanzas:recurrente_detener", args=[r.pk]), **HTMX)
        assert "Detenido" in respuesta.content.decode()
        r.refresh_from_db()
        assert not r.activo

    def test_recurrente_detener_sin_htmx(self, cliente, usuario):
        r = RecurrenteFactory(usuario=usuario)
        assert cliente.post(reverse("finanzas:recurrente_detener", args=[r.pk])).status_code == 302

    def test_metas_completas(self, cliente, usuario):
        r = cliente.post(
            reverse("metas:nueva"),
            {"titulo": "Auto", "monto_objetivo": "1000", "monto_actual": "0", "por_que": "Libertad"},
        )
        assert r.status_code == 302
        meta = MetaAhorro.objects.get(usuario=usuario)
        assert "Libertad" in cliente.get(reverse("metas:lista")).content.decode()
        r = cliente.post(reverse("metas:aportar", args=[meta.pk]), {"monto": "250"}, **HTMX)
        assert "25%" in r.content.decode()
        r = cliente.post(reverse("metas:aportar", args=[meta.pk]), {"monto": "-1"}, **HTMX)
        assert r.status_code == 200
        cliente.post(reverse("metas:aportar", args=[meta.pk]), {"monto": "-1"})
        cliente.post(
            reverse("metas:editar", args=[meta.pk]),
            {"titulo": "Auto nuevo", "monto_objetivo": "2000", "monto_actual": "250"},
        )
        meta.refresh_from_db()
        assert meta.titulo == "Auto nuevo" and meta.monto_actual == 250
        assert cliente.post(reverse("metas:borrar", args=[meta.pk]), **HTMX).content == b""
        assert not MetaAhorro.objects.exists()

    def test_meta_objetivo_invalido(self, cliente):
        r = cliente.post(reverse("metas:nueva"), {"titulo": "X", "monto_objetivo": "0", "monto_actual": "0"})
        assert "monto_objetivo" in r.context["form"].errors
