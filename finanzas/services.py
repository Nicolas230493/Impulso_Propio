"""Reglas de negocio de movimientos, cuotas, recurrentes y saldos.

Las vistas solo validan formularios y llaman a estas funciones. Todo lo que
escribe varias filas corre dentro de transaction.atomic().
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from core.fechas import fecha_en_mes, hoy, primer_dia, sumar_meses, sumar_meses_a_mes
from core.models import Moneda, TipoMovimiento
from core.moneda import convertir_a_moneda, truncar, validar_tipo_cambio

from .models import Categoria, Cuenta, Recurrente, Transaccion

MAX_CUOTAS = 60


@dataclass
class DatosMovimiento:
    tipo: str
    monto: Decimal
    categoria: Categoria
    cuenta: Cuenta
    fecha: date
    moneda: str = Moneda.ARS
    tipo_cambio: Decimal | None = None
    descripcion: str = ""
    cuotas: int = 1
    repetir: bool = False


def _validar(usuario, datos: DatosMovimiento):
    if datos.monto is None or Decimal(datos.monto) <= 0:
        raise ValidationError({"monto": "El monto tiene que ser mayor a cero."})
    if datos.categoria.usuario_id != usuario.pk or datos.cuenta.usuario_id != usuario.pk:
        raise ValidationError("Categoría o cuenta inválida.")
    # Hace falta tipo de cambio si el movimiento es en USD o si no coincide con la moneda de la cuenta.
    if datos.moneda == Moneda.USD or datos.moneda != datos.cuenta.moneda:
        validar_tipo_cambio(datos.tipo_cambio)
    if datos.cuotas > 1 and datos.repetir:
        raise ValidationError("Un movimiento no puede ser en cuotas y recurrente a la vez.")


def _campos(datos: DatosMovimiento) -> dict:
    return {
        "tipo": datos.tipo,
        "monto": datos.monto,
        "moneda": datos.moneda,
        "tipo_cambio": datos.tipo_cambio if datos.tipo_cambio else None,
        "categoria": datos.categoria,
        "cuenta": datos.cuenta,
        "descripcion": datos.descripcion or "",
    }


def _recordar_preferencias(usuario, datos: DatosMovimiento):
    """Última cuenta y último tipo de cambio, para precargar el próximo formulario."""
    usuario.ultima_cuenta = datos.cuenta
    campos = ["ultima_cuenta"]
    if datos.tipo_cambio:
        usuario.ultimo_tipo_cambio = datos.tipo_cambio
        campos.append("ultimo_tipo_cambio")
    usuario.save(update_fields=campos)


@transaction.atomic
def crear_movimiento(usuario, datos: DatosMovimiento) -> list[Transaccion]:
    """Crea el movimiento (o sus cuotas) y, si se pidió, el recurrente asociado."""
    _validar(usuario, datos)
    if datos.cuotas > 1:
        filas = crear_en_cuotas(usuario, datos, datos.cuotas)
    else:
        recurrente = None
        if datos.repetir:
            recurrente = Recurrente.objects.create(
                usuario=usuario,
                dia_del_mes=datos.fecha.day,
                ultimo_generado=datos.fecha,
                **_campos(datos),
            )
        filas = [
            Transaccion.objects.create(usuario=usuario, fecha=datos.fecha, recurrente=recurrente, **_campos(datos))
        ]
    _recordar_preferencias(usuario, datos)
    return filas


def dividir_en_cuotas(monto: Decimal, n: int) -> list[Decimal]:
    """Partes truncadas a centavos; la última absorbe la diferencia. La suma da siempre el total."""
    monto = Decimal(monto)
    parte = truncar(monto / n)
    return [parte] * (n - 1) + [monto - parte * (n - 1)]


@transaction.atomic
def crear_en_cuotas(usuario, datos: DatosMovimiento, n: int) -> list[Transaccion]:
    if datos.tipo != TipoMovimiento.GASTO or datos.cuenta.tipo != Cuenta.Tipo.TARJETA:
        raise ValidationError({"cuotas": "Las cuotas son solo para gastos con tarjeta."})
    if not 1 < n <= MAX_CUOTAS:
        raise ValidationError({"cuotas": f"Entre 2 y {MAX_CUOTAS} cuotas."})
    grupo = uuid.uuid4()
    base = _campos(datos)
    descripcion = datos.descripcion or datos.categoria.nombre
    return [
        Transaccion.objects.create(
            usuario=usuario,
            **{**base, "monto": monto, "descripcion": f"{descripcion} ({i}/{n})"},
            fecha=sumar_meses(datos.fecha, i - 1),
            grupo_id=grupo,
            cuota=i,
            cuotas=n,
        )
        for i, monto in enumerate(dividir_en_cuotas(datos.monto, n), start=1)
    ]


@transaction.atomic
def actualizar_movimiento(tx: Transaccion, datos: DatosMovimiento) -> Transaccion:
    _validar(tx.usuario, datos)
    for campo, valor in _campos(datos).items():
        setattr(tx, campo, valor)
    tx.fecha = datos.fecha
    tx.save()
    return tx


@transaction.atomic
def borrar_movimiento(tx: Transaccion, todo_el_grupo: bool = False) -> int:
    if todo_el_grupo and tx.grupo_id:
        borrados, _ = Transaccion.objects.de(tx.usuario).filter(grupo_id=tx.grupo_id).delete()
        return borrados
    tx.delete()
    return 1


def _tipo_cambio_para(recurrente: Recurrente):
    """Cada generación usa el último tipo de cambio del usuario; si no tiene, el del recurrente."""
    necesita = recurrente.moneda == Moneda.USD or recurrente.moneda != recurrente.cuenta.moneda
    if not necesita:
        return None
    return recurrente.usuario.ultimo_tipo_cambio or recurrente.tipo_cambio


def generar_recurrentes_pendientes(usuario, hasta: date | None = None) -> int:
    """Crea los movimientos que faltan de cada recurrente activo, hasta `hasta` inclusive.

    Es idempotente: la restricción única recurrente+fecha y get_or_create evitan
    duplicados aunque dos requests corran a la vez.
    """
    hasta = hasta or hoy()
    creados = 0
    for recurrente_id in Recurrente.objects.de(usuario).filter(activo=True).values_list("pk", flat=True):
        creados += _generar_uno(recurrente_id, hasta)
    return creados


@transaction.atomic
def _generar_uno(recurrente_id, hasta: date) -> int:
    r = Recurrente.objects.select_for_update().select_related("usuario", "cuenta").get(pk=recurrente_id)
    if not r.activo:
        return 0
    desde = r.ultimo_generado or r.creado.date()
    mes = sumar_meses_a_mes(primer_dia(desde), 1 if r.ultimo_generado else 0)
    creados = 0
    while mes <= primer_dia(hasta):
        fecha = fecha_en_mes(mes, r.dia_del_mes)
        if fecha > hasta:
            break
        _, nuevo = Transaccion.objects.get_or_create(
            recurrente=r,
            fecha=fecha,
            defaults={
                "usuario": r.usuario,
                "tipo": r.tipo,
                "monto": r.monto,
                "moneda": r.moneda,
                "tipo_cambio": _tipo_cambio_para(r),
                "categoria_id": r.categoria_id,
                "cuenta": r.cuenta,
                "descripcion": r.descripcion,
            },
        )
        creados += nuevo
        r.ultimo_generado = fecha
        mes = sumar_meses_a_mes(mes, 1)
    r.save(update_fields=["ultimo_generado", "modificado"])
    return creados


def detener_recurrente(recurrente: Recurrente):
    """'Dejar de repetir': los movimientos ya generados se conservan."""
    recurrente.activo = False
    recurrente.save(update_fields=["activo", "modificado"])


def saldo_a_hoy(cuenta: Cuenta, al: date | None = None) -> Decimal:
    """Saldo inicial + ingresos − gastos con fecha <= hoy, en la moneda de la cuenta.

    Las cuotas y los movimientos con fecha futura no cuentan.
    """
    al = al or hoy()
    saldo = Decimal(cuenta.saldo_inicial)
    filas = Transaccion.objects.filter(cuenta=cuenta, fecha__lte=al).values_list(
        "tipo", "monto", "moneda", "tipo_cambio", "monto_ars"
    )
    for tipo, monto, moneda, tipo_cambio, monto_ars in filas:
        if cuenta.moneda == Moneda.ARS:
            importe = monto_ars
        else:
            importe = convertir_a_moneda(monto, moneda, tipo_cambio, cuenta.moneda)
        saldo += importe if tipo == TipoMovimiento.INGRESO else -importe
    return saldo.quantize(Decimal("0.01"))


def cantidad_de_usos(objeto: Categoria | Cuenta) -> int:
    campo = "categoria" if isinstance(objeto, Categoria) else "cuenta"
    return Transaccion.objects.filter(**{campo: objeto}).count() + Recurrente.objects.filter(**{campo: objeto}).count()


@transaction.atomic
def reasignar_y_borrar(objeto: Categoria | Cuenta, destino: Categoria | Cuenta | None = None):
    """Borra una categoría o cuenta. Si tiene movimientos, primero los pasa a `destino`."""
    campo = "categoria" if isinstance(objeto, Categoria) else "cuenta"
    if cantidad_de_usos(objeto):
        if destino is None or type(destino) is not type(objeto) or destino.pk == objeto.pk:
            raise ValidationError("Elegí a dónde pasar los movimientos antes de borrar.")
        if destino.usuario_id != objeto.usuario_id:
            raise ValidationError("Destino inválido.")
        if campo == "cuenta" and destino.moneda != objeto.moneda:
            raise ValidationError("La cuenta destino tiene que ser de la misma moneda.")
        Transaccion.objects.filter(**{campo: objeto}).update(**{campo: destino})
        Recurrente.objects.filter(**{campo: objeto}).update(**{campo: destino})
    objeto.delete()
