from django.urls import path

from . import reportes, views

app_name = "sucursales"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("crear/", views.crear, name="crear"),
    path("reportes/", reportes.indice, name="reportes"),
    path("reportes/<int:numero>/", reportes.detalle, name="reporte"),
    path("<int:pk>/editar/", views.editar, name="editar"),
    path("<int:pk>/eliminar/", views.eliminar, name="eliminar"),
]
