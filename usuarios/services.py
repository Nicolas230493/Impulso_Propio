from django.db import transaction

CATEGORIAS_INICIALES = ["Alimentación", "Transporte", "Vivienda", "Salario", "Otros"]
CUENTAS_INICIALES = [("Efectivo", "efectivo"), ("Tarjeta", "tarjeta"), ("Transferencia", "transferencia")]


@transaction.atomic
def crear_datos_iniciales(usuario):
    from finanzas.models import Categoria, Cuenta

    for nombre in CATEGORIAS_INICIALES:
        Categoria.objects.get_or_create(usuario=usuario, nombre=nombre)
    for nombre, tipo in CUENTAS_INICIALES:
        Cuenta.objects.get_or_create(usuario=usuario, nombre=nombre, defaults={"tipo": tipo})
