from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scripts.migrar_supabase import ErrorMigracion, OrigenSupabase, migrar, resumen


class _Simulacro(Exception):
    pass


class Command(BaseCommand):
    help = (
        "Copia usuarios, cuentas, categorías, recurrentes, movimientos y metas desde Supabase y verifica "
        "conteos y sumas. Idempotente: repite la copia completa de cada usuario. No correr después del corte."
    )

    def add_arguments(self, parser):
        parser.add_argument("--origen", help="Cadena de conexión Postgres de Supabase (o SUPABASE_DATABASE_URL).")
        parser.add_argument("--simulacro", action="store_true", help="Migra y verifica, pero no guarda nada.")

    def handle(self, *args, origen=None, simulacro=False, **options):
        from config.settings.base import env

        url = origen or env("SUPABASE_DATABASE_URL", default="")
        if not url:
            raise CommandError("Falta --origen o SUPABASE_DATABASE_URL en .env.")
        fuente = OrigenSupabase(url)
        try:
            with transaction.atomic():
                reporte = migrar(fuente)
                if simulacro:
                    self.stdout.write(resumen(reporte))
                    raise _Simulacro
        except _Simulacro:
            self.stdout.write(self.style.WARNING("Simulacro: verificación OK, no se guardó nada."))
            return
        except ErrorMigracion as error:
            raise CommandError(f"Migración revertida. {error}") from error
        finally:
            fuente.cerrar()
        self.stdout.write(resumen(reporte))
        self.stdout.write(self.style.SUCCESS("Migración completa y verificada."))
