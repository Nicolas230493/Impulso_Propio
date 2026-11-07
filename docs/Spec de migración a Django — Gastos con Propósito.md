# Spec de migración a Django — Gastos con Propósito

Nov 7, 2026 · @Nicolás

## Resumen y objetivos

La app pasa de un SPA en JavaScript sobre Supabase a un monolito Django con PostgreSQL propio, renderizado del lado del servidor, manteniendo todas las funcionalidades actuales. La lógica que hoy vive en el navegador (cuotas, recurrentes, conversión ARS/USD, saldos, alertas) se mueve al servidor, donde se puede testear y no depende del cliente.

Objetivos:

1. Paridad funcional completa con la versión actual (las 12 funcionalidades del relevamiento).
2. Seguridad por usuario resuelta en Django, sin depender de RLS de Supabase.
3. Lógica de negocio en una capa de servicios con tests automáticos.
4. Corregir los problemas detectados en el relevamiento como parte de la migración, no después.
5. Migrar los datos existentes de Supabase sin pérdida.
6. Mismo stack que el resto de los proyectos Impulso (Python + Django + PostgreSQL), para reutilizar convenciones y despliegue.

## Alcance

Entra todo lo que la app hace hoy, más las correcciones de la sección de problemas. Las funcionalidades nuevas grandes quedan para después del corte.

| Funcionalidad | En la migración | Nota |
| --- | --- | --- |
| Login, registro y logout con email | Sí | Con datos iniciales al registrarse (5 categorías, 3 cuentas) |
| Filtro por mes | Sí | Por querystring `?mes=2026-11` |
| Resumen ingresos, gastos y saldo en ARS | Sí |  |
| Alta de movimiento (USD, cuotas, recurrente, última cuenta) | Sí |  |
| Historial del mes con equivalente ARS | Sí | Se agrega edición |
| Gráficos (dona por categoría, barras) | Sí | Chart.js con versión fija |
| Reportes: mes vs anterior, últimos 6 meses | Sí |  |
| Cuentas ARS/USD con saldo "a hoy" | Sí |  |
| Categorías con tope y alertas 80 % / 100 % | Sí | La alerta respeta el mes filtrado |
| Recurrentes y "Dejar de repetir" | Sí |  |
| Metas de ahorro | Sí | Se completa: actualizar progreso y borrar |
| Exportación CSV (mes y backup) | Sí | Mismo formato: `;`, coma decimal, BOM |
| Transferencias entre cuentas | Opcional (etapa 6) | No existe hoy |
| API REST / app móvil | No | Se puede sumar con DRF después |
| Multimoneda más allá de ARS/USD | No |  |

## Stack objetivo

Django con templates del servidor y HTMX para la interactividad, sin build de frontend, igual que hoy.

| Capa | Hoy | Django |
| --- | --- | --- |
| Lenguaje / framework | JS en el navegador | Python 3.12 + Django 5.2 LTS |
| Base de datos | Supabase (Postgres + RLS) | PostgreSQL 16 propio; SQLite solo para desarrollo local |
| Autenticación | Supabase Auth | `django.contrib.auth` con usuario custom por email |
| UI | `index.html` + JS a mano | Templates Django + HTMX + Alpine.js mínimo |
| Estilos | Tailwind por CDN | Tailwind compilado (`django-tailwind` o CLI standalone) |
| Gráficos | Chart.js sin versión | Chart.js con versión fija, datos vía `json_script` |
| Formularios | Validación en JS | Django Forms (+ `django-widget-tweaks`) |
| Config | `supabaseClient.js` con anon key | `django-environ` + `.env` fuera del repo |
| Tareas periódicas | Al abrir la app | Management command diario (cron) + chequeo al login |
| Tests | No hay | `pytest-django` + `factory_boy` |
| Calidad | — | `ruff`, `pre-commit` |
| Servidor | Estático | Gunicorn + WhiteNoise |

Si más adelante querés app móvil, se suma Django REST Framework sobre la misma capa de servicios sin tocar la lógica.

## Arquitectura

Un proyecto Django (`gastos`) con seis apps. Cada app tiene `models.py`, `services.py` (lógica de negocio), `forms.py`, `views.py` y `templates/`. Las vistas solo validan, llaman a servicios y renderizan; los cálculos no viven en las vistas ni en los templates.

```
gastos/
├── config/              # settings (base, dev, prod), urls, wsgi
├── core/                # UserOwnedModel, mixins, utils de fechas y moneda
├── usuarios/            # User custom, registro, login, datos iniciales
├── finanzas/            # Cuenta, Categoria, Transaccion, Recurrente
├── metas/               # Meta
├── reportes/            # resumen, gráficos, reportes, alertas, CSV
├── templates/           # base.html, parciales HTMX
├── static/
├── scripts/migrar_supabase.py
└── tests/
```

| Archivo actual | Destino en Django |
| --- | --- |
| `index.html` | `templates/base.html` + templates por pantalla y parciales HTMX |
| `supabaseClient.js` | `config/settings` + `.env` (`DATABASE_URL`, `SECRET_KEY`) |
| `auth.js` | app `usuarios` (vistas de auth de Django + señal `post_save` para datos iniciales) |
| `dataService.js` | managers y querysets filtrados por usuario en cada app |
| `utils.js` | `core/fechas.py`, `core/moneda.py` y `finanzas/services.py` |
| `dashboard.js` | app `reportes` (servicios de agregación + vistas + exportación CSV) |
| `app.js` | desaparece: el estado vive en la base y cada request lo consulta |
| `migracion_v1.sql` | migraciones de Django (`makemigrations`), versionadas y completas |

## Modelo de datos

Las cinco tablas actuales pasan a models de Django; el cambio principal es que la categoría de una transacción deja de ser un texto y pasa a ser una clave foránea. Con eso, renombrar una categoría ya no obliga a reescribir movimientos y recurrentes. Montos con `DecimalField`, nunca `float`.

```python
# core/models.py
class UserOwnedModel(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    creado = models.DateTimeField(auto_now_add=True)
    modificado = models.DateTimeField(auto_now=True)
    objects = UserOwnedQuerySet.as_manager()   # .de(usuario)
    class Meta:
        abstract = True

class Moneda(models.TextChoices):
    ARS = "ARS"; USD = "USD"

# finanzas/models.py
class Cuenta(UserOwnedModel):
    class Tipo(models.TextChoices):
        EFECTIVO = "efectivo"; TARJETA = "tarjeta"; TRANSFERENCIA = "transferencia"
    nombre = models.CharField(max_length=80)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    moneda = models.CharField(max_length=3, choices=Moneda.choices, default=Moneda.ARS)
    saldo_inicial = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["usuario", "nombre"], name="cuenta_unica")]

class Categoria(UserOwnedModel):
    nombre = models.CharField(max_length=60)
    tope_mensual = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["usuario", "nombre"], name="categoria_unica")]

class Recurrente(UserOwnedModel):
    tipo = models.CharField(max_length=7, choices=[("gasto", "Gasto"), ("ingreso", "Ingreso")])
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT)
    descripcion = models.CharField(max_length=200, blank=True)
    dia_del_mes = models.PositiveSmallIntegerField()        # 1..31
    ultimo_generado = models.DateField(null=True, blank=True)
    activo = models.BooleanField(default=True)              # "Dejar de repetir"

class Transaccion(UserOwnedModel):
    tipo = models.CharField(max_length=7, choices=[("gasto", "Gasto"), ("ingreso", "Ingreso")])
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    moneda = models.CharField(max_length=3, choices=Moneda.choices)
    tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    monto_ars = models.DecimalField(max_digits=16, decimal_places=2)   # calculado en save()
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT)
    fecha = models.DateField(db_index=True)
    descripcion = models.CharField(max_length=200, blank=True)
    grupo_id = models.UUIDField(null=True, blank=True, db_index=True)  # cuotas
    cuota = models.PositiveSmallIntegerField(null=True, blank=True)
    cuotas = models.PositiveSmallIntegerField(null=True, blank=True)
    recurrente = models.ForeignKey(Recurrente, null=True, blank=True, on_delete=models.SET_NULL)
    class Meta:
        indexes = [models.Index(fields=["usuario", "fecha"])]
        constraints = [models.UniqueConstraint(fields=["recurrente", "fecha"], name="recurrente_una_vez_por_fecha")]

# metas/models.py
class MetaAhorro(UserOwnedModel):   # no se llama Meta para no chocar con class Meta
    titulo = models.CharField(max_length=120)
    monto_objetivo = models.DecimalField(max_digits=14, decimal_places=2)
    monto_actual = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    por_que = models.TextField(blank=True)
    fecha_limite = models.DateField(null=True, blank=True)

# usuarios/models.py
class Usuario(AbstractUser):  # login por email
    username = None
    email = models.EmailField(unique=True)
    ultimo_tipo_cambio = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    ultima_cuenta = models.ForeignKey("finanzas.Cuenta", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    USERNAME_FIELD = "email"; REQUIRED_FIELDS = []
```

Decisiones de modelo:

- `monto_ars` se guarda al crear o editar el movimiento. Los totales del mes se calculan con `Sum("monto_ars")` en la base, sin convertir fila por fila en Python.
- La restricción única `recurrente + fecha` impide que un recurrente se genere dos veces el mismo día, aunque dos requests corran a la vez.
- Borrar una categoría o cuenta con movimientos queda bloqueado (`PROTECT`); la vista ofrece reasignarlos a otra antes de borrar.
- "Último tipo de cambio" y "última cuenta usada", que hoy viven en el navegador, pasan al usuario, así se mantienen entre dispositivos.
- Se usa un modelo de usuario custom desde la primera migración: cambiarlo después en Django es muy costoso.

## Autenticación y aislamiento por usuario

RLS de Supabase se reemplaza por una regla única en código: ningún queryset de datos del usuario se arma sin `.de(request.user)`. Hoy el filtro por `user_id` está en el cliente y la RLS en la base; en Django ambos se concentran en el servidor.

- **Login:** `LoginView`, `LogoutView` (por POST) y una vista de registro propia con formulario por email y contraseña. Validadores de contraseña de Django activos.
- **Datos iniciales:** al crear el usuario, un servicio `crear_datos_iniciales(usuario)` crea las 5 categorías (Alimentación, Transporte, Vivienda, Salario, Otros) y las 3 cuentas (Efectivo, Tarjeta, Transferencia) dentro de una transacción atómica.
- **Acceso:** todas las vistas con `LoginRequiredMixin`. Un `UsuarioQuerysetMixin` define `get_queryset()` como `Modelo.objects.de(self.request.user)`, así un id ajeno devuelve 404 en lugar de datos de otro.
- **Formularios:** los `ModelChoiceField` de cuenta y categoría se filtran por usuario en `__init__`, para que no se pueda mandar el id de una cuenta ajena.
- **Recupero de contraseña:** `PasswordResetView` con envío de mail (SMTP configurable por `.env`). Hoy no existe.
- **Opcional, defensa en profundidad:** si se despliega en Postgres, se puede mantener RLS con `SET app.user_id` por request. No es necesario para el MVP.

Test obligatorio: para cada vista de detalle, edición y borrado, un usuario B que pide un objeto del usuario A recibe 404.

## Lógica de negocio

Todo lo que hoy hace `utils.js` pasa a funciones puras en `services.py`, con las mismas reglas y tests unitarios. Cada servicio que escribe varias filas corre dentro de `transaction.atomic()`.

| Servicio | Regla |
| --- | --- |
| `convertir_a_ars(monto, moneda, tipo_cambio)` | ARS queda igual; USD multiplica por el tipo de cambio. Redondeo `ROUND_HALF_UP` a 2 decimales. USD sin tipo de cambio = error de validación. |
| `crear_movimiento(usuario, datos)` | Valida, calcula `monto_ars`, guarda y actualiza `ultima_cuenta` y `ultimo_tipo_cambio` del usuario. Si viene "repetir", crea también el `Recurrente`. |
| `crear_en_cuotas(usuario, datos, n)` | Solo gastos con cuenta tipo tarjeta. Divide el monto en n partes truncadas a centavos; la última absorbe la diferencia. Una fila por mes desde la fecha elegida, todas con el mismo `grupo_id` y `cuota` 1..n. |
| `borrar_movimiento(tx, todo_el_grupo)` | Si tiene `grupo_id`, la vista pregunta si borrar solo esa cuota o todas. |
| `generar_recurrentes_pendientes(usuario, hasta=hoy)` | Por cada recurrente activo, crea los movimientos faltantes desde `ultimo_generado` hasta hoy. Si el día no existe en el mes, usa el último (31 → 28 en febrero). Usa `get_or_create` sobre `recurrente + fecha` y actualiza `ultimo_generado`. |
| `saldo_a_hoy(cuenta)` | `saldo_inicial` + ingresos − gastos con `fecha <= hoy`, en la moneda de la cuenta. Las cuotas futuras no cuentan. |
| `resumen_mes(usuario, mes)` | Ingresos, gastos y saldo del mes en ARS con `Sum("monto_ars")`. |
| `gastos_por_categoria(usuario, mes)` | Agregado por categoría para la dona y para las alertas. |
| `alertas_presupuesto(usuario, mes)` | Por categoría con tope: amarilla desde 80 %, roja arriba de 100 %. Usa el mes filtrado, no el actual. |
| `comparar_con_mes_anterior(usuario, mes)` | Gastos por categoría de ambos meses y variación %; si el mes anterior es 0, se muestra "nuevo" en vez de dividir por cero. |
| `ultimos_meses(usuario, mes, n=6)` | Ingresos, gastos y variación de los últimos n meses en una sola consulta con `TruncMonth`. |
| `exportar_csv(usuario, mes=None)` | `;` como separador, coma decimal, BOM UTF-8 al inicio. Sin mes = backup completo. Respuesta en streaming para backups grandes. |

Cuándo se generan los recurrentes: al iniciar sesión (como hoy) y además con `python manage.py generar_recurrentes` todos los días por cron, así los reportes están al día aunque el usuario no entre.

Tipo de cambio en recurrentes USD: cada generación usa el `ultimo_tipo_cambio` del usuario en ese momento, no el del día en que se creó el recurrente. El movimiento generado se puede editar para corregirlo.

## Vistas, URLs y frontend

Cada pantalla es una URL con su vista; el mes elegido viaja como `?mes=AAAA-MM` y por defecto es el actual. Las acciones chicas (borrar, dejar de repetir, actualizar meta) responden con un parcial HTMX y no recargan la página.

| URL | Vista | Qué muestra o hace |
| --- | --- | --- |
| `/login/`, `/registro/`, `/logout/`, `/password-reset/` | usuarios | Autenticación |
| `/` | `DashboardView` | Resumen del mes, alertas, dona, barras, form rápido de movimiento |
| `/movimientos/` | `MovimientoListView` | Historial del mes, con equivalente ARS para USD |
| `/movimientos/nuevo/` | `MovimientoCreateView` | Form con moneda, tipo de cambio, cuotas y "repetir" |
| `/movimientos/<id>/editar/` | `MovimientoUpdateView` | Edición (nueva) |
| `/movimientos/<id>/borrar/` | `MovimientoDeleteView` | Confirma y pregunta por el grupo de cuotas |
| `/cuentas/` + crear, editar, borrar | `Cuenta*View` | Cuentas con saldo a hoy |
| `/categorias/` + crear, editar, borrar | `Categoria*View` | Topes y consumo del mes |
| `/recurrentes/` + `<id>/detener/` | `Recurrente*View` | Lista y "Dejar de repetir" |
| `/metas/` + crear, editar, borrar, `<id>/aportar/` | `Meta*View` | Barra de progreso, aporte y borrado |
| `/reportes/` | `ReportesView` | Mes vs anterior, últimos 6 meses |
| `/exportar/?mes=` y `/exportar/backup/` | `ExportarCSVView` | Descarga CSV |

Frontend:

- `base.html` con navbar, selector de mes y bloque de mensajes de Django. Se mantiene el diseño actual en Tailwind.
- El formulario de movimiento muestra el campo tipo de cambio solo si la moneda es USD, y el de cuotas solo si es gasto con tarjeta. Se resuelve con Alpine.js (`x-show`) y se vuelve a validar en el servidor.
- Gráficos: la vista pasa los datos con `{{ datos|json_script:"datos-grafico" }}` y un JS chico dibuja con Chart.js cargado en versión fija (descargado a `static/` o CDN con versión y hash SRI).
- Montos con formato argentino (`$ 1.234,56`) mediante un template filter `ars` y `USE_THOUSAND_SEPARATOR`, `LANGUAGE_CODE = "es-ar"`, `TIME_ZONE = "America/Argentina/Buenos_Aires"`.
- Todos los formularios con CSRF; los borrados solo por POST.

## Migración de datos desde Supabase

Un script idempotente (`scripts/migrar_supabase.py`, corrido como management command) lee la base de Supabase por conexión Postgres directa y escribe en la base Django. Se puede correr varias veces en staging antes del corte real.

1. **Respaldo:** `pg_dump` completo del proyecto Supabase y, además, el CSV de backup de la app por cada usuario.
2. **Usuarios:** leer `auth.users` (id, email, `encrypted_password`, fecha de alta). Crear `Usuario` por email y guardar un mapa `uuid_supabase → id_django`.
3. **Contraseñas:** Supabase guarda hashes bcrypt (`$2a$...`). Se agrega un hasher custom `SupabaseBcryptHasher` en `PASSWORD_HASHERS` que verifica esos hashes; al primer login, Django lo re-hashea a su algoritmo por defecto. Si se prefiere no migrar hashes, alternativa: mandar a cada usuario un mail de "restablecer contraseña".
4. **Cuentas y categorías:** copiar por usuario, mapa de ids viejos a nuevos.
5. **Recurrentes:** copiar resolviendo categoría (por nombre) y cuenta (por id) con los mapas.
6. **Transacciones:** copiar resolviendo categoría por nombre. Si un nombre no existe en las categorías del usuario (por ejemplo, una categoría borrada), se crea con ese nombre y se reporta en el log. Se conservan `grupo_id`, `cuota`, `cuotas`, `tipo_cambio` y se calcula `monto_ars`.
7. **Metas:** copiar tal cual.
8. **Verificación automática:** por usuario y por mes, comparar cantidad de movimientos y suma de ingresos y gastos en ARS entre origen y destino; saldo a hoy de cada cuenta. El script falla si hay cualquier diferencia.
9. **Corte:** congelar la app vieja (mensaje de mantenimiento), correr la migración final, verificar, apuntar el dominio a Django. Dejar Supabase en solo lectura 30 días como plan de vuelta atrás.

Antes de correr el paso 2 conviene revisar en Supabase si hay usuarios que entraron con otro proveedor (Google, magic link): esos no tienen contraseña y van directo a "restablecer contraseña".

## Problemas actuales que se corrigen

Los ocho puntos del relevamiento quedan resueltos en la versión Django; ninguno se arrastra.

| Problema hoy | Solución en Django |
| --- | --- |
| `.gitignore` roto, `node_modules/` subido y `.env` sin ignorar | Repo nuevo con `.gitignore` de Python correcto (`.env`, `.venv/`, `__pycache__/`, `staticfiles/`, `media/`). Rotar la anon key y cualquier secreto que haya quedado en el historial. |
| Dependencias de `package.json` sin uso | No hay `package.json`; dependencias Python en `pyproject.toml` (o `requirements.txt`) con versiones fijas. |
| Metas a medio hacer | CRUD completo, acción "Aportar" que suma a `monto_actual` y borrado con confirmación. |
| La migración SQL no crea `transacciones` ni `metas` | Migraciones de Django desde cero: `migrate` arma la base completa en cualquier entorno. |
| La alerta de presupuesto ignora el filtro de mes | `alertas_presupuesto` recibe el mes filtrado. |
| No hay transferencias ni edición de movimientos | Edición incluida en el MVP; transferencias como etapa opcional (ver decisiones abiertas). |
| Recurrentes USD con tipo de cambio fijo | Cada generación usa el último tipo de cambio del usuario. |
| Chart.js sin versión fija | Versión fija en `static/` o CDN versionado con SRI. |

## Testing y criterios de aceptación

La migración se da por terminada cuando pasan todos los tests y la checklist de aceptación, con cobertura de al menos 90 % en los `services.py`.

Tests unitarios de servicios (casos mínimos):

- Cuotas: 100.000 en 3 cuotas da 33.333,33 + 33.333,33 + 33.333,34; la suma siempre es igual al total. Rechazo de cuotas en cuenta que no es tarjeta.
- Recurrentes: día 31 genera 28/2 (y 29/2 en año bisiesto); no duplica si se corre dos veces; genera todos los meses faltantes tras meses sin entrar; uno detenido no genera nada.
- Saldo a hoy: una cuota con fecha futura no afecta el saldo.
- Conversión: USD sin tipo de cambio es inválido; redondeo a 2 decimales.
- Alertas: 79 % sin alerta, 80 % amarilla, 100 % amarilla, 100,01 % roja; con el mes filtrado.
- Reportes: variación con mes anterior en 0 no divide por cero.
- CSV: empieza con BOM, usa `;`, coma decimal y acentos correctos al abrir en Excel.

Tests de integración:

- Aislamiento: usuario B recibe 404 al ver, editar o borrar datos de A, y no ve opciones de A en los formularios.
- Registro crea exactamente 5 categorías y 3 cuentas.
- Migración de datos: sobre un dump de prueba, el script deja conteos y sumas idénticos.

Aceptación manual:

- [ ] Las 12 funcionalidades del relevamiento funcionan con datos migrados reales.
- [ ] Los totales del mes coinciden con la app vieja para al menos 3 meses.
- [ ] Funciona bien en celular.

## Despliegue

Django deja de ser un sitio estático: necesita un servidor con Python y una base Postgres, y un cron diario para los recurrentes.

- **Opción simple:** un PaaS (Railway, Render o Fly.io) con Postgres administrado. Deploy desde GitHub, variables en el panel.
- **Opción VPS:** el mismo servidor que uses para los otros proyectos Impulso, con Nginx + Gunicorn + systemd y Postgres local, backups con `pg_dump` diario.
- **Opción mixta:** Django en un PaaS y seguir usando Supabase solo como Postgres administrado (sin su Auth ni RLS). Ahorra la migración de la base, pero no la de usuarios.

En todos los casos:

- Variables en `.env`: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, credenciales SMTP.
- `python manage.py check --deploy` sin advertencias: HTTPS, cookies seguras, HSTS.
- `collectstatic` con WhiteNoise; `migrate` en cada deploy.
- Cron diario: `python manage.py generar_recurrentes`.
- Docker opcional con un `Dockerfile` y `docker-compose.yml` (web + db) para desarrollo idéntico a producción.
- CI en GitHub Actions: `ruff` + `pytest` en cada push.

## Plan por etapas

Seis etapas en orden; cada una termina con algo que se puede probar y no se pasa a la siguiente sin sus tests en verde. La app vieja sigue en uso hasta el corte de la etapa 5.

1. **Base del proyecto.** Repo nuevo, settings por entorno, `.env`, usuario custom, Postgres, `ruff`, `pytest`, CI. Entregable: `migrate` y `pytest` corren limpios.
2. **Modelos y servicios.** Todos los models, migraciones y `services.py` con sus tests unitarios (cuotas, recurrentes, saldos, conversión, alertas, reportes, CSV). Sin pantallas. Entregable: cobertura ≥ 90 % en servicios.
3. **Autenticación y pantallas principales.** Registro con datos iniciales, login, dashboard, alta, edición y borrado de movimientos, historial, cuentas, categorías. Entregable: un usuario nuevo puede usar la app completa para el día a día.
4. **Resto de funcionalidades.** Recurrentes, metas completas, reportes, gráficos, exportación CSV, recupero de contraseña, comando `generar_recurrentes`. Entregable: paridad funcional con la app actual.
5. **Migración de datos y corte.** Script de migración probado en staging, verificación de sumas, deploy a producción, cambio de dominio, Supabase en solo lectura. Entregable: checklist de aceptación completa con datos reales.
6. **Mejoras posteriores (opcional).** Transferencias entre cuentas, API con DRF, cotización del dólar automática, presupuestos por período.

## Decisiones abiertas

Cinco puntos para definir antes de la etapa 1; la columna de propuesta es lo que asume este spec.

| Decisión | Propuesta | Alternativa |
| --- | --- | --- |
| Frontend | Templates + HTMX (sin build) | DRF + SPA en React o Vue, más trabajo pero lista para app móvil |
| Dónde vive la base | Postgres propio en el hosting elegido | Seguir con Supabase solo como Postgres |
| Contraseñas de usuarios existentes | Hasher bcrypt custom, re-hash al primer login | Forzar "restablecer contraseña" a todos |
| Transferencias entre cuentas | Etapa 6, como modelo `Transferencia` que genera un gasto y un ingreso vinculados | Incluirlas en el MVP |
| Cotización USD | Manual, como hoy | Consultar una API de cotización (oficial, MEP o blue) y sugerirla en el form |

- [ ] ¿Cuántos usuarios y movimientos hay hoy en Supabase? Define si el corte puede ser en una sola ventana corta.
- [ ] ¿Hay usuarios con login por Google o magic link?
