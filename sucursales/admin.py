from django.contrib import admin

from .models import Categoria, Cliente, DetalleVenta, Sucursal, Venta


@admin.register(Sucursal)
class SucursalAdmin(admin.ModelAdmin):
    list_display = ("nombre", "sku", "categoria", "precio", "stock", "activo")
    list_filter = ("activo", "categoria")
    search_fields = ("nombre", "sku")


admin.site.register(Categoria)
admin.site.register(Cliente)
admin.site.register(Venta)
admin.site.register(DetalleVenta)
