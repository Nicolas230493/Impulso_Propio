from datetime import date
from decimal import Decimal

import factory

from finanzas.models import Categoria, Cuenta, Recurrente, Transaccion
from metas.models import MetaAhorro
from usuarios.models import Usuario


class UsuarioFactory(factory.django.DjangoModelFactory):
    """Al crearse dispara la señal: ya tiene las 5 categorías y 3 cuentas iniciales."""

    class Meta:
        model = Usuario
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"usuario{n}@ejemplo.com")
    password = factory.PostGenerationMethodCall("set_password", "clave-segura-123")

    @factory.post_generation
    def guardar(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class CuentaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Cuenta

    usuario = factory.SubFactory(UsuarioFactory)
    nombre = factory.Sequence(lambda n: f"Cuenta {n}")
    tipo = Cuenta.Tipo.EFECTIVO
    moneda = "ARS"


class CategoriaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Categoria

    usuario = factory.SubFactory(UsuarioFactory)
    nombre = factory.Sequence(lambda n: f"Categoría {n}")


class TransaccionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaccion

    usuario = factory.SubFactory(UsuarioFactory)
    tipo = "gasto"
    monto = Decimal("100")
    moneda = "ARS"
    categoria = factory.LazyAttribute(lambda o: CategoriaFactory(usuario=o.usuario))
    cuenta = factory.LazyAttribute(lambda o: CuentaFactory(usuario=o.usuario))
    fecha = date(2026, 11, 5)


class RecurrenteFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Recurrente

    usuario = factory.SubFactory(UsuarioFactory)
    tipo = "gasto"
    monto = Decimal("1000")
    moneda = "ARS"
    categoria = factory.LazyAttribute(lambda o: CategoriaFactory(usuario=o.usuario))
    cuenta = factory.LazyAttribute(lambda o: CuentaFactory(usuario=o.usuario))
    dia_del_mes = 10
    ultimo_generado = date(2026, 1, 10)


class MetaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MetaAhorro

    usuario = factory.SubFactory(UsuarioFactory)
    titulo = "Viaje"
    monto_objetivo = Decimal("1000")
    monto_actual = Decimal("250")
    por_que = "Conocer el sur"
