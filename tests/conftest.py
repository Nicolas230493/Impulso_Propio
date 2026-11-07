import pytest

from finanzas.models import Categoria, Cuenta

from .factories import UsuarioFactory


@pytest.fixture
def usuario(db):
    return UsuarioFactory()


@pytest.fixture
def otro_usuario(db):
    return UsuarioFactory()


@pytest.fixture
def cliente(client, usuario):
    client.force_login(usuario)
    return client


def cuenta_de(usuario, nombre):
    return Cuenta.objects.get(usuario=usuario, nombre=nombre)


def categoria_de(usuario, nombre):
    return Categoria.objects.get(usuario=usuario, nombre=nombre)


@pytest.fixture
def efectivo(usuario):
    return cuenta_de(usuario, "Efectivo")


@pytest.fixture
def tarjeta(usuario):
    return cuenta_de(usuario, "Tarjeta")


@pytest.fixture
def comida(usuario):
    return categoria_de(usuario, "Alimentación")
