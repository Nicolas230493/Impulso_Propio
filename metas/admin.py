from django.contrib import admin

from .models import MetaAhorro


@admin.register(MetaAhorro)
class MetaAhorroAdmin(admin.ModelAdmin):
    list_display = ["titulo", "monto_actual", "monto_objetivo", "fecha_limite", "usuario"]
