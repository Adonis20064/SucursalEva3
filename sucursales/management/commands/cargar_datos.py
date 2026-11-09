import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from sucursales.models import Categoria, Cliente, DetalleVenta, Sucursal, Venta


class Command(BaseCommand):
    help = "Carga datos de demostración (categorías, productos, clientes y ventas) para probar los reportes."

    @transaction.atomic
    def handle(self, *args, **opts):
        if Venta.objects.exists() or Cliente.objects.exists():
            self.stdout.write(self.style.WARNING("Ya hay clientes o ventas; no se cargó nada."))
            return

        rnd = random.Random(42)
        hoy = timezone.localdate()

        cats = {
            n: Categoria.objects.get_or_create(nombre=n, defaults={"descripcion": d})[0]
            for n, d in [
                ("Bebidas", "Bebidas y jugos"),
                ("Snacks", "Snacks y golosinas"),
                ("Aseo", "Artículos de aseo"),
                ("Electrónica", "Accesorios electrónicos"),
            ]
        }

        catalogo = [
            ("BEB-001", "Agua mineral 1.5L", "Bebidas", "990", 120),
            ("BEB-002", "Jugo de naranja 1L", "Bebidas", "1590", 60),
            ("BEB-003", "Bebida cola 2L", "Bebidas", "2190", 3),
            ("SNK-001", "Papas fritas 200g", "Snacks", "1890", 80),
            ("SNK-002", "Galletas de avena", "Snacks", "1290", 4),
            ("SNK-003", "Barra de chocolate", "Snacks", "790", 200),
            ("ASE-001", "Detergente 3L", "Aseo", "6990", 25),
            ("ASE-002", "Jabón líquido", "Aseo", "2490", 2),
            ("ELE-001", "Audífonos básicos", "Electrónica", "12990", 15),
            ("ELE-002", "Cargador USB-C", "Electrónica", "9990", 30),
            ("ELE-003", "Cable HDMI 2m", "Electrónica", "5990", 0),   # nunca vendido
            ("ELE-004", "Mouse inalámbrico", "Electrónica", "14990", 9),  # nunca vendido
        ]
        productos = [
            Sucursal.objects.create(
                categoria=cats[cat], sku=sku, nombre=nom, precio=Decimal(precio), stock=stock, activo=True
            )
            for sku, nom, cat, precio, stock in catalogo
        ]
        vendibles = productos[:-2]  # los dos últimos quedan sin ventas

        clientes = [
            Cliente.objects.create(rut=rut, nombre=nom, email=mail, telefono=tel)
            for rut, nom, mail, tel in [
                ("11.111.111-1", "Ana Pérez", "ana@correo.cl", "+56911111111"),
                ("22.222.222-2", "Bruno Soto", "bruno@correo.cl", "+56922222222"),
                ("33.333.333-3", "Carla Rojas", "carla@correo.cl", "+56933333333"),
                ("44.444.444-4", "Diego Muñoz", "diego@correo.cl", "+56944444444"),
                ("55.555.555-5", "Elena Vega", "elena@correo.cl", "+56955555555"),
                ("66.666.666-6", "Fabián Díaz", "fabian@correo.cl", "+56966666666"),  # sin compras
            ]
        ]
        compradores = clientes[:-1]

        for i in range(40):
            cliente = rnd.choice(compradores)
            # primeras 12 ventas dentro de los últimos 30 días; el resto repartidas en el año
            dias = rnd.randint(0, 29) if i < 12 else rnd.randint(30, max(31, (hoy - hoy.replace(month=1, day=1)).days))
            venta = Venta.objects.create(cliente=cliente, estado="Pagada", total=Decimal("0"))
            Venta.objects.filter(pk=venta.pk).update(fecha=hoy - timedelta(days=dias))  # fecha es auto_now_add

            total = Decimal("0")
            for prod in rnd.sample(vendibles, rnd.randint(1, 4)):
                cant = rnd.randint(1, 5)
                sub = prod.precio * cant
                DetalleVenta.objects.create(
                    venta=venta, sucursal=prod, cantidad=cant,
                    precio_unitario=prod.precio, subtotal=sub,
                )
                total += sub
            Venta.objects.filter(pk=venta.pk).update(total=total)

        self.stdout.write(self.style.SUCCESS(
            f"Datos cargados: {len(cats)} categorías, {len(productos)} productos, "
            f"{len(clientes)} clientes, {Venta.objects.count()} ventas."
        ))
