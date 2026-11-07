from django.contrib import admin

from .models import Categoria, Cuenta, Recurrente, Transaccion


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "tipo", "moneda", "saldo_inicial", "usuario"]
    list_filter = ["tipo", "moneda"]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "tope_mensual", "usuario"]


@admin.register(Recurrente)
class RecurrenteAdmin(admin.ModelAdmin):
    list_display = ["descripcion", "tipo", "monto", "moneda", "dia_del_mes", "ultimo_generado", "activo", "usuario"]
    list_filter = ["activo", "tipo"]


@admin.register(Transaccion)
class TransaccionAdmin(admin.ModelAdmin):
    list_display = ["fecha", "tipo", "monto", "moneda", "monto_ars", "categoria", "cuenta", "usuario"]
    list_filter = ["tipo", "moneda"]
    date_hierarchy = "fecha"
    search_fields = ["descripcion"]
