from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Usuario
from .services import crear_datos_iniciales


@receiver(post_save, sender=Usuario)
def datos_iniciales_al_registrarse(sender, instance, created, raw=False, **kwargs):
    # La migración desde Supabase marca los usuarios para copiar sus propios datos.
    if created and not raw and not getattr(instance, "omitir_datos_iniciales", False):
        crear_datos_iniciales(instance)


@receiver(user_logged_in)
def generar_recurrentes_al_entrar(sender, request, user, **kwargs):
    from finanzas.services import generar_recurrentes_pendientes

    generar_recurrentes_pendientes(user)
