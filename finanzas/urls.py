from django.urls import path

from . import views

app_name = "finanzas"

urlpatterns = [
    path("movimientos/", views.MovimientoListView.as_view(), name="movimientos"),
    path("movimientos/nuevo/", views.MovimientoCreateView.as_view(), name="movimiento_nuevo"),
    path("movimientos/<int:pk>/editar/", views.MovimientoUpdateView.as_view(), name="movimiento_editar"),
    path("movimientos/<int:pk>/borrar/", views.MovimientoDeleteView.as_view(), name="movimiento_borrar"),
    path("cuentas/", views.CuentaListView.as_view(), name="cuentas"),
    path("cuentas/nueva/", views.CuentaCreateView.as_view(), name="cuenta_nueva"),
    path("cuentas/<int:pk>/editar/", views.CuentaUpdateView.as_view(), name="cuenta_editar"),
    path("cuentas/<int:pk>/borrar/", views.CuentaDeleteView.as_view(), name="cuenta_borrar"),
    path("categorias/", views.CategoriaListView.as_view(), name="categorias"),
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_nueva"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_editar"),
    path("categorias/<int:pk>/borrar/", views.CategoriaDeleteView.as_view(), name="categoria_borrar"),
    path("recurrentes/", views.RecurrenteListView.as_view(), name="recurrentes"),
    path("recurrentes/<int:pk>/detener/", views.RecurrenteDetenerView.as_view(), name="recurrente_detener"),
]
