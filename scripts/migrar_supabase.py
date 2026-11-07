"""Migración de datos desde Supabase a la base Django.

Se corre con `python manage.py migrar_supabase` (ver core/management/commands).

- Idempotente: por cada usuario migrado, borra lo que ya tenga en Django y lo vuelve a copiar.
  Se puede repetir en staging cuantas veces haga falta. NO correr después del corte: pisaría
  los datos cargados en la app nueva.
- Todo corre en una sola transacción: si la verificación final encuentra cualquier diferencia,
  no queda nada escrito.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core.fechas import fecha_en_mes, hoy, parsear_mes
from core.models import Moneda, TipoMovimiento
from core.moneda import redondear
from finanzas.models import Categoria, Cuenta, Recurrente, Transaccion
from finanzas.services import saldo_a_hoy
from metas.models import MetaAhorro
from usuarios.hashers import SupabaseBcryptHasher

TABLAS = ["cuentas", "categorias", "recurrentes", "transacciones", "metas"]
NOMBRE_SIN_CUENTA = "Sin cuenta (migración)"


class ErrorMigracion(Exception):
    pass


class OrigenSupabase:
    """Lee la base de Supabase por conexión Postgres directa (cadena de conexión del proyecto)."""

    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row

        self.conexion = psycopg.connect(url, row_factory=dict_row)

    def usuarios(self) -> list[dict]:
        with self.conexion.cursor() as cur:
            cur.execute("select id, email, encrypted_password, created_at from auth.users order by created_at")
            return cur.fetchall()

    def filas(self, tabla: str) -> list[dict]:
        assert tabla in TABLAS
        with self.conexion.cursor() as cur:
            cur.execute(f"select * from public.{tabla}")  # noqa: S608 (tabla de lista fija)
            return cur.fetchall()

    def cerrar(self):
        self.conexion.close()


@dataclass
class Reporte:
    usuarios: int = 0
    conteos: dict = field(default_factory=lambda: defaultdict(int))
    avisos: list[str] = field(default_factory=list)
    sin_contrasena: list[str] = field(default_factory=list)
    mapa_usuarios: dict = field(default_factory=dict)

    def avisar(self, texto: str):
        self.avisos.append(texto)


def _dec(valor, por_defecto="0") -> Decimal:
    return Decimal(str(valor)) if valor is not None else Decimal(por_defecto)


def _fecha(valor) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _texto(valor, largo: int, reporte: Reporte, contexto: str) -> str:
    texto = (valor or "").strip()
    if len(texto) > largo:
        reporte.avisar(f"{contexto}: texto recortado a {largo} caracteres.")
        texto = texto[:largo]
    return texto


def _necesita_tc(moneda: str, cuenta: Cuenta) -> bool:
    return moneda == Moneda.USD or moneda != cuenta.moneda


def _por_usuario(filas: Iterable[dict]) -> dict:
    agrupadas = defaultdict(list)
    for fila in filas:
        agrupadas[str(fila["user_id"])].append(fila)
    return agrupadas


def _vaciar(usuario):
    """Borra lo que el usuario tenga en Django para volver a copiarlo (idempotencia)."""
    get_user_model().objects.filter(pk=usuario.pk).update(ultima_cuenta=None)
    Transaccion.objects.filter(usuario=usuario).delete()
    Recurrente.objects.filter(usuario=usuario).delete()
    Categoria.objects.filter(usuario=usuario).delete()
    Cuenta.objects.filter(usuario=usuario).delete()
    MetaAhorro.objects.filter(usuario=usuario).delete()


def _migrar_usuario(origen_usuario: dict, reporte: Reporte):
    Usuario = get_user_model()
    email = origen_usuario["email"].strip().lower()
    hash_bcrypt = origen_usuario.get("encrypted_password") or ""
    usuario = Usuario.objects.filter(email__iexact=email).first()
    if usuario is None:
        usuario = Usuario(email=email)
        if alta := origen_usuario.get("created_at"):
            usuario.date_joined = alta if timezone.is_aware(alta) else timezone.make_aware(alta)
        usuario.omitir_datos_iniciales = True  # sus categorías y cuentas vienen de Supabase
        nuevo = True
    else:
        nuevo = False
    # Solo se toca la contraseña si todavía no la cambió en Django.
    if nuevo or not usuario.has_usable_password() or usuario.password.startswith(SupabaseBcryptHasher.algorithm):
        if hash_bcrypt.startswith("$2"):
            usuario.password = SupabaseBcryptHasher.desde_supabase(hash_bcrypt)
        else:
            usuario.set_unusable_password()
            reporte.sin_contrasena.append(email)
    usuario.save()
    return usuario


def migrar(origen, reporte: Reporte | None = None, al: date | None = None) -> Reporte:
    """Copia todo desde `origen` y verifica. Lanza ErrorMigracion (y revierte) si algo no cierra."""
    reporte = reporte or Reporte()
    al = al or hoy()
    datos = {tabla: _por_usuario(origen.filas(tabla)) for tabla in TABLAS}
    with transaction.atomic():
        for origen_usuario in origen.usuarios():
            if not origen_usuario.get("email"):
                reporte.avisar(f"Usuario {origen_usuario['id']} sin email: se omite.")
                continue
            uid = str(origen_usuario["id"])
            usuario = _migrar_usuario(origen_usuario, reporte)
            reporte.mapa_usuarios[uid] = usuario.pk
            reporte.usuarios += 1
            _vaciar(usuario)
            mapa_cuentas = _copiar_datos(usuario, {t: datos[t].get(uid, []) for t in TABLAS}, reporte)
            _verificar(usuario, datos["transacciones"].get(uid, []), datos["cuentas"].get(uid, []), mapa_cuentas, al)
    return reporte


def _copiar_datos(usuario, filas: dict, reporte: Reporte) -> dict:
    email = usuario.email
    cuentas: dict[str, Cuenta] = {}
    for f in filas["cuentas"]:
        cuentas[str(f["id"])] = Cuenta.objects.create(
            usuario=usuario,
            nombre=_texto(f["nombre"], 80, reporte, f"{email} cuenta"),
            tipo=f["tipo"],
            moneda=f.get("moneda") or Moneda.ARS,
            saldo_inicial=_dec(f.get("saldo_inicial")),
        )
    reporte.conteos["cuentas"] += len(cuentas)

    categorias: dict[str, Categoria] = {}
    for f in filas["categorias"]:
        tope = _dec(f["tope_mensual"]) if f.get("tope_mensual") is not None else None
        c = Categoria.objects.create(
            usuario=usuario, nombre=_texto(f["nombre"], 60, reporte, f"{email} categoría"), tope_mensual=tope or None
        )
        categorias[c.nombre] = c
    reporte.conteos["categorias"] += len(categorias)

    def categoria(nombre):
        nombre = (nombre or "Otros").strip()[:60]
        if nombre not in categorias:
            categorias[nombre] = Categoria.objects.create(usuario=usuario, nombre=nombre)
            reporte.avisar(f"{email}: se creó la categoría “{nombre}” (estaba en movimientos pero no en categorías).")
        return categorias[nombre]

    sin_cuenta = None

    def cuenta(cuenta_id, contexto):
        nonlocal sin_cuenta
        if cuenta_id and str(cuenta_id) in cuentas:
            return cuentas[str(cuenta_id)]
        if sin_cuenta is None:
            sin_cuenta = Cuenta.objects.create(usuario=usuario, nombre=NOMBRE_SIN_CUENTA, tipo=Cuenta.Tipo.EFECTIVO)
            reporte.avisar(f"{email}: se creó la cuenta “{NOMBRE_SIN_CUENTA}” para movimientos sin cuenta.")
        reporte.avisar(f"{email}: {contexto} sin cuenta asignada, va a “{NOMBRE_SIN_CUENTA}”.")
        return sin_cuenta

    def tipo_cambio(f, cta, contexto):
        moneda = f.get("moneda") or Moneda.ARS
        if not _necesita_tc(moneda, cta):
            return None
        tc = _dec(f.get("tipo_cambio"), "1")
        if moneda == Moneda.ARS:
            reporte.avisar(f"{email}: {contexto} en ARS sobre cuenta USD con tipo de cambio {tc}; revisarlo.")
        return tc

    recurrentes: dict[str, Recurrente] = {}
    for f in filas["recurrentes"]:
        contexto = f"recurrente {f['id']}"
        cta = cuenta(f.get("cuenta_id"), contexto)
        dia = int(f["dia"])
        recurrentes[str(f["id"])] = Recurrente.objects.create(
            usuario=usuario,
            tipo=f["tipo"],
            monto=_dec(f["monto"]),
            moneda=f.get("moneda") or Moneda.ARS,
            tipo_cambio=tipo_cambio(f, cta, contexto),
            categoria=categoria(f["categoria"]),
            cuenta=cta,
            descripcion=_texto(f.get("descripcion"), 200, reporte, f"{email} {contexto}"),
            dia_del_mes=dia,
            ultimo_generado=fecha_en_mes(parsear_mes(f["ultimo_mes"]), dia),
            activo=True,
        )
    reporte.conteos["recurrentes"] += len(recurrentes)

    vistos = set()
    for f in sorted(filas["transacciones"], key=lambda f: (str(f["fecha"]), str(f["id"]))):
        contexto = f"movimiento {f['id']}"
        if _dec(f["monto"]) <= 0:
            raise ErrorMigracion(
                f"{email}: {contexto} tiene monto {f['monto']}; corregirlo en Supabase antes de migrar."
            )
        cta = cuenta(f.get("cuenta_id"), contexto)
        fecha = _fecha(f["fecha"])
        recurrente = recurrentes.get(str(f.get("recurrente_id")))
        if recurrente and (recurrente.pk, fecha) in vistos:
            reporte.avisar(f"{email}: {contexto} duplicado del recurrente el {fecha}; se migra sin vínculo.")
            recurrente = None
        if recurrente:
            vistos.add((recurrente.pk, fecha))
        Transaccion.objects.create(
            usuario=usuario,
            tipo=f["tipo"],
            monto=_dec(f["monto"]),
            moneda=f.get("moneda") or Moneda.ARS,
            tipo_cambio=tipo_cambio(f, cta, contexto),
            categoria=categoria(f["categoria"]),
            cuenta=cta,
            fecha=fecha,
            descripcion=_texto(f.get("descripcion"), 200, reporte, f"{email} {contexto}"),
            grupo_id=f.get("grupo_id"),
            cuota=f.get("cuota"),
            cuotas=f.get("cuotas"),
            recurrente=recurrente,
        )
        reporte.conteos["transacciones"] += 1

    for f in filas["metas"]:
        objetivo = _dec(f["monto_objetivo"])
        if objetivo <= 0:
            reporte.avisar(f"{email}: meta “{f['titulo']}” con objetivo {objetivo}; se usa 1.")
            objetivo = Decimal(1)
        MetaAhorro.objects.create(
            usuario=usuario,
            titulo=_texto(f["titulo"], 120, reporte, f"{email} meta"),
            monto_objetivo=objetivo,
            monto_actual=_dec(f.get("monto_actual")),
            por_que=f.get("por_que") or "",
            fecha_limite=_fecha(f["fecha_limite"]) if f.get("fecha_limite") else None,
        )
        reporte.conteos["metas"] += 1
    return cuentas


# --- Verificación ---


def _ars_origen(f) -> Decimal:
    """Misma regla que la app vieja (enARS), redondeada por fila como monto_ars."""
    tc = _dec(f.get("tipo_cambio"), "1") if (f.get("moneda") or Moneda.ARS) == Moneda.USD else Decimal(1)
    return redondear(_dec(f["monto"]) * tc)


def _saldo_origen(cuenta_fila: dict, transacciones: list[dict], al: date) -> Decimal:
    """saldoCuenta() de la app vieja: saldo inicial ± movimientos con fecha <= hoy en la moneda de la cuenta."""
    moneda_cuenta = cuenta_fila.get("moneda") or Moneda.ARS
    saldo = _dec(cuenta_fila.get("saldo_inicial"))
    for f in transacciones:
        if str(f.get("cuenta_id")) != str(cuenta_fila["id"]) or _fecha(f["fecha"]) > al:
            continue
        moneda, monto, tc = f.get("moneda") or Moneda.ARS, _dec(f["monto"]), _dec(f.get("tipo_cambio"), "1")
        if moneda_cuenta == Moneda.ARS:
            importe = _ars_origen(f)
        elif moneda == moneda_cuenta:
            importe = monto
        else:
            importe = monto / tc
        saldo += importe if f["tipo"] == TipoMovimiento.INGRESO else -importe
    return saldo.quantize(Decimal("0.01"))


def _verificar(usuario, transacciones: list[dict], cuentas: list[dict], mapa_cuentas: dict, al: date):
    """Por mes: cantidad, ingresos y gastos en ARS y montos originales por moneda. Por cuenta: saldo a hoy."""
    # [cantidad, ingresos ARS, gastos ARS, suma de montos en ARS, suma de montos en USD]
    esperado = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0), Decimal(0)])
    for f in transacciones:
        mes = _fecha(f["fecha"]).strftime("%Y-%m")
        esperado[mes][0] += 1
        esperado[mes][1 if f["tipo"] == TipoMovimiento.INGRESO else 2] += _ars_origen(f)
        esperado[mes][4 if f.get("moneda") == Moneda.USD else 3] += _dec(f["monto"])

    obtenido = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0), Decimal(0)])
    filas = Transaccion.objects.filter(usuario=usuario).values_list("tipo", "fecha", "monto_ars", "monto", "moneda")
    for tipo, fecha, monto_ars, monto, moneda in filas:
        mes = fecha.strftime("%Y-%m")
        obtenido[mes][0] += 1
        obtenido[mes][1 if tipo == TipoMovimiento.INGRESO else 2] += monto_ars
        obtenido[mes][4 if moneda == Moneda.USD else 3] += monto

    diferencias = [
        f"{mes}: origen {esperado[mes]} / destino {obtenido[mes]}"
        for mes in sorted(set(esperado) | set(obtenido))
        if esperado[mes] != obtenido[mes]
    ]
    for f in cuentas:
        origen = _saldo_origen(f, transacciones, al)
        destino = saldo_a_hoy(mapa_cuentas[str(f["id"])], al=al)
        if origen != destino:
            diferencias.append(f"cuenta {f['nombre']}: saldo origen {origen} / destino {destino}")
    if diferencias:
        raise ErrorMigracion(f"{usuario.email}: la verificación no cierra:\n  " + "\n  ".join(diferencias))


def resumen(reporte: Reporte) -> str:
    lineas = [f"Migrados {reporte.usuarios} usuarios a las {timezone.localtime():%H:%M}."]
    lineas += [f"  {tabla}: {n}" for tabla, n in sorted(reporte.conteos.items())]
    if reporte.sin_contrasena:
        lineas.append("Sin contraseña (mandarles 'restablecer contraseña'): " + ", ".join(reporte.sin_contrasena))
    if reporte.avisos:
        lineas.append(f"{len(reporte.avisos)} avisos:")
        lineas += [f"  - {a}" for a in reporte.avisos]
    lineas.append("Mapa uuid Supabase -> id Django:")
    lineas += [f"  {uuid} -> {pk}" for uuid, pk in reporte.mapa_usuarios.items()]
    return "\n".join(lineas)
