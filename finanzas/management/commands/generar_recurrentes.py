from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from finanzas.models import Recurrente
from finanzas.services import generar_recurrentes_pendientes


class Command(BaseCommand):
    help = "Genera los movimientos recurrentes vencidos de todos los usuarios. Pensado para cron diario."

    def handle(self, *args, **options):
        usuarios = get_user_model().objects.filter(pk__in=Recurrente.objects.filter(activo=True).values("usuario"))
        total = 0
        for usuario in usuarios:
            total += generar_recurrentes_pendientes(usuario)
        self.stdout.write(self.style.SUCCESS(f"{total} movimientos generados para {usuarios.count()} usuarios."))
