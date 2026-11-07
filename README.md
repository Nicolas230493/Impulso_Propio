# Gastos con Propósito (Django)

Finanzas personales: ingresos y gastos en ARS/USD, cuotas con tarjeta, movimientos recurrentes,
cuentas con saldo, topes por categoría con alertas, reportes, metas de ahorro y exportación CSV.

Es la migración de la versión SPA + Supabase (commits anteriores de este repo en GitHub) a un
monolito Django, según `docs/Spec de migración a Django — Gastos con Propósito.md`.

## Arranque rápido (desarrollo)

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env              # SQLite y mails por consola por defecto
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Entrá a http://127.0.0.1:8000/registro/. Al registrarte se crean 5 categorías y 3 cuentas.
Para el admin: `python manage.py createsuperuser`.

Con Docker (Postgres 16 incluido): `docker compose up --build` → http://localhost:8000.

## Comandos

| Comando | Para qué |
| --- | --- |
| `pytest` | Tests (SQLite en memoria) |
| `TEST_DATABASE_URL=postgres://… pytest` | Los mismos tests contra PostgreSQL |
| `pytest --cov=core --cov=usuarios --cov=finanzas --cov=metas --cov=reportes --cov=scripts` | Cobertura |
| `ruff check . && ruff format .` | Lint y formato (también vía `pre-commit install`) |
| `scripts/tailwind.sh` (`--watch`) | Recompila `static/css/app.css`. Baja el CLI standalone de Tailwind la primera vez; no usa Node |
| `python manage.py generar_recurrentes` | Genera los recurrentes vencidos de todos los usuarios. Para cron diario |
| `python manage.py migrar_supabase [--simulacro]` | Migración de datos desde Supabase (ver abajo) |

Después de tocar clases de Tailwind en templates hay que correr `scripts/tailwind.sh` y commitear `static/css/app.css`.

## Estructura

```
config/       settings (base, dev, prod, test), urls, wsgi
core/         UserOwnedModel + .de(usuario), fechas, moneda, mixins, filtros de formato
usuarios/     Usuario por email, registro, hasher bcrypt de Supabase, datos iniciales
finanzas/     Cuenta, Categoria, Transaccion, Recurrente + services.py (cuotas, recurrentes, saldos)
metas/        MetaAhorro + aportar
reportes/     dashboard, resumen, alertas, comparaciones, gráficos y CSV
scripts/      migrar_supabase.py
templates/    base.html, pantallas y parciales HTMX
static/       app.css compilado, app.js, htmx/alpine/chart.js en versión fija
tests/        pytest-django + factory_boy
```

Las vistas solo validan, llaman a `services.py` y renderizan. Ningún queryset de datos de usuario
se arma sin `Modelo.objects.de(request.user)`: un id ajeno da 404 (hay un test por cada ruta).

## Reglas de negocio

- **Montos** con `Decimal`. `monto_ars` se calcula al guardar; los totales usan `Sum("monto_ars")`.
- **Tipo de cambio** obligatorio si el movimiento es en USD o si su moneda no coincide con la de la cuenta.
- **Cuotas**: solo gastos con tarjeta, de 2 a 60. Cada cuota se trunca a centavos y la última absorbe la diferencia (100.000 / 3 = 33.333,33 + 33.333,33 + 33.333,34).
- **Recurrentes**: se generan al iniciar sesión, al abrir el inicio y por cron. El día 31 pasa a ser el último día del mes. La restricción única `recurrente + fecha` impide duplicados. En USD usan el último tipo de cambio que cargaste.
- **Saldo a hoy**: solo movimientos con fecha ≤ hoy, así que las cuotas futuras no cuentan.
- **Alertas**: amarilla desde el 80 % del tope (100 % justo incluido), roja si lo supera. Usan el mes filtrado.
- **Borrar categoría o cuenta con movimientos**: primero pide a cuál pasarlos (la cuenta destino tiene que tener la misma moneda).
- **Última cuenta y último tipo de cambio** quedan guardados en el usuario, no en el navegador.

## Despliegue

Variables (`.env` o panel del PaaS): `SECRET_KEY` (50+ caracteres), `DEBUG=False`, `ALLOWED_HOSTS`,
`CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, `EMAIL_URL` (SMTP para recuperar contraseña), `DEFAULT_FROM_EMAIL`.

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy   # sin advertencias
python manage.py collectstatic --noinput
python manage.py migrate --noinput
gunicorn config.wsgi
```

El `Dockerfile` ya hace `collectstatic`, `migrate` y levanta gunicorn. Cron diario:

```
15 3 * * * cd /ruta/gastos && .venv/bin/python manage.py generar_recurrentes
```

CI (`.github/workflows/ci.yml`): ruff, migraciones al día, tests con cobertura ≥ 90 % y tests contra Postgres.

## Migración de datos desde Supabase (etapa 5)

1. **Respaldo**: `pg_dump` del proyecto Supabase y el CSV "Backup completo" de la app vieja de cada usuario.
2. En `.env`, poné `SUPABASE_DATABASE_URL` con la cadena de conexión directa de Supabase (Project Settings → Database).
3. `python manage.py migrar_supabase --simulacro`: migra y verifica todo, pero revierte. Revisá los avisos.
4. Corte: dejá la app vieja en mantenimiento, corré `python manage.py migrar_supabase`, revisá el resumen y apuntá el dominio a Django. Dejá Supabase en solo lectura 30 días.

Qué hace el comando:

- Usuarios por email. El hash bcrypt de Supabase se guarda tal cual y se re-hashea con PBKDF2 en el primer login. Los usuarios sin contraseña (Google o magic link) salen listados para mandarles "restablecer contraseña".
- Copia cuentas, categorías, recurrentes, movimientos (con cuotas, USD y vínculo al recurrente) y metas.
- Si una categoría solo existe en los movimientos, la crea. Los movimientos sin cuenta van a "Sin cuenta (migración)". Todo eso queda en los avisos.
- Verifica, por usuario y por mes, la cantidad de movimientos, los ingresos y gastos en ARS y los montos originales por moneda, y además el saldo a hoy de cada cuenta. Ante cualquier diferencia no guarda nada.
- Es idempotente: vuelve a copiar cada usuario desde cero. **No correrlo después del corte**, porque pisaría lo cargado en la app nueva.

## Pendiente fuera del código

- Rotar la anon key de Supabase, que quedó en el historial de la versión anterior.
- Etapa 6 (opcional): transferencias entre cuentas, API con DRF y cotización automática del dólar.
