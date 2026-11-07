from django.urls import path

from . import views

app_name = "metas"

urlpatterns = [
    path("", views.MetaListView.as_view(), name="lista"),
    path("nueva/", views.MetaCreateView.as_view(), name="nueva"),
    path("<int:pk>/editar/", views.MetaUpdateView.as_view(), name="editar"),
    path("<int:pk>/borrar/", views.MetaDeleteView.as_view(), name="borrar"),
    path("<int:pk>/aportar/", views.MetaAportarView.as_view(), name="aportar"),
]
