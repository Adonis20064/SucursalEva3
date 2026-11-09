from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .models import Categoria, Cliente, DetalleVenta, Sucursal, Venta

PASSWORD = "Clave-Segura-123"


class BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("crear_grupos", verbosity=0)
        from django.contrib.auth.models import Group

        cls.admin = User.objects.create_user("admin1", password=PASSWORD)
        cls.admin.groups.add(Group.objects.get(name="Administrador"))
        cls.operador = User.objects.create_user("oper1", password=PASSWORD)
        cls.operador.groups.add(Group.objects.get(name="Operador"))
        cls.sin_rol = User.objects.create_user("sinrol", password=PASSWORD)

        cls.cat = Categoria.objects.create(nombre="General", descripcion="x")
        cls.item = Sucursal.objects.create(
            categoria=cls.cat, sku="A-1", nombre="Uno", precio=Decimal("10.00"), stock=5
        )

    def datos(self, **extra):
        d = {
            "sku": "B-2",
            "nombre": "Dos",
            "categoria": str(self.cat.pk),
            "precio": "19.90",
            "stock": "3",
            "activo": "on",
        }
        d.update(extra)
        return d


class AccesoTests(BaseTest):
    def test_anonimo_es_redirigido_al_login(self):
        urls = [
            reverse("sucursales:lista"),
            reverse("sucursales:crear"),
            reverse("sucursales:editar", args=[self.item.pk]),
        ]
        for url in urls:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn(reverse("sucursales:login"), r["Location"])

    def test_anonimo_no_puede_eliminar(self):
        r = self.client.post(reverse("sucursales:eliminar", args=[self.item.pk]))
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())

    def test_usuario_sin_rol_recibe_403(self):
        self.client.force_login(self.sin_rol)
        self.assertEqual(self.client.get(reverse("sucursales:lista")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sucursales:crear")).status_code, 403)

    def test_superusuario_sin_grupo_recibe_403(self):
        su = User.objects.create_superuser("root", password=PASSWORD)
        self.client.force_login(su)
        for nombre in ("lista", "crear", "reportes"):
            self.assertEqual(self.client.get(reverse(f"sucursales:{nombre}")).status_code, 403, nombre)
        r = self.client.post(reverse("sucursales:eliminar", args=[self.item.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())

    def test_operador_no_puede_eliminar_en_servidor(self):
        self.client.force_login(self.operador)
        r = self.client.post(reverse("sucursales:eliminar", args=[self.item.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())

    def test_operador_no_ve_boton_eliminar(self):
        self.client.force_login(self.operador)
        r = self.client.get(reverse("sucursales:lista"))
        self.assertNotContains(r, "Eliminar")

    def test_administrador_ve_boton_eliminar(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("sucursales:lista"))
        self.assertContains(r, "Eliminar")


class MetodosYCsrfTests(BaseTest):
    def test_eliminar_por_get_no_permitido(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("sucursales:eliminar", args=[self.item.pk]))
        self.assertEqual(r.status_code, 405)
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())

    def test_logout_por_get_no_permitido(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("sucursales:logout")).status_code, 405)

    def test_post_sin_csrf_es_rechazado(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        r = c.post(reverse("sucursales:eliminar", args=[self.item.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())
        r = c.post(reverse("sucursales:crear"), self.datos())
        self.assertEqual(r.status_code, 403)

    def test_formularios_incluyen_csrf_token(self):
        self.client.force_login(self.admin)
        for url in (
            reverse("sucursales:crear"),
            reverse("sucursales:editar", args=[self.item.pk]),
            reverse("sucursales:lista"),
        ):
            self.assertContains(self.client.get(url), "csrfmiddlewaretoken")
        self.client.logout()
        self.assertContains(self.client.get(reverse("sucursales:login")), "csrfmiddlewaretoken")


class CrudTests(BaseTest):
    def test_crear_ok(self):
        self.client.force_login(self.operador)
        r = self.client.post(reverse("sucursales:crear"), self.datos(), follow=True)
        self.assertRedirects(r, reverse("sucursales:lista"))
        self.assertContains(r, "creado correctamente")
        nuevo = Sucursal.objects.get(sku="B-2")
        self.assertEqual(nuevo.precio, Decimal("19.90"))
        self.assertTrue(nuevo.activo)

    def test_crear_acepta_coma_decimal(self):
        self.client.force_login(self.operador)
        self.client.post(reverse("sucursales:crear"), self.datos(precio="5,5"))
        self.assertEqual(Sucursal.objects.get(sku="B-2").precio, Decimal("5.50"))

    def test_validaciones_rechazan_datos_invalidos(self):
        self.client.force_login(self.operador)
        casos = [
            {"precio": "-1"},
            {"precio": "abc"},
            {"precio": "NaN"},
            {"precio": "1.999"},
            {"precio": "99999999999"},
            {"stock": "-3"},
            {"stock": "2.5"},
            {"stock": ""},
            {"nombre": "   "},
            {"sku": ""},
            {"sku": "a-1"},  # duplicado (sin distinguir mayúsculas)
            {"categoria": "999"},
            {"categoria": "x"},
        ]
        for caso in casos:
            r = self.client.post(reverse("sucursales:crear"), self.datos(**caso))
            self.assertEqual(r.status_code, 200, caso)
            self.assertContains(r, "Revisa los campos marcados", msg_prefix=str(caso))
        self.assertEqual(Sucursal.objects.count(), 1)

    def test_editar_ok_y_sku_propio_permitido(self):
        self.client.force_login(self.operador)
        r = self.client.post(
            reverse("sucursales:editar", args=[self.item.pk]),
            self.datos(sku="A-1", nombre="Renombrado"),
            follow=True,
        )
        self.assertContains(r, "actualizado correctamente")
        self.item.refresh_from_db()
        self.assertEqual(self.item.nombre, "Renombrado")

    def test_editar_desmarcar_activo(self):
        self.client.force_login(self.operador)
        datos = self.datos(sku="A-1")
        datos.pop("activo")
        self.client.post(reverse("sucursales:editar", args=[self.item.pk]), datos)
        self.item.refresh_from_db()
        self.assertFalse(self.item.activo)

    def test_editar_inexistente_404(self):
        self.client.force_login(self.operador)
        self.assertEqual(self.client.get(reverse("sucursales:editar", args=[9999])).status_code, 404)

    def test_administrador_elimina(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("sucursales:eliminar", args=[self.item.pk]), follow=True)
        self.assertContains(r, "eliminado correctamente")
        self.assertFalse(Sucursal.objects.filter(pk=self.item.pk).exists())

    def test_eliminar_protegido_muestra_error(self):
        cliente = Cliente.objects.create(rut="1-9", nombre="C", email="c@x.cl", telefono="1")
        venta = Venta.objects.create(cliente=cliente, estado="ok", total=Decimal("10"))
        DetalleVenta.objects.create(
            venta=venta, sucursal=self.item, cantidad=1,
            precio_unitario=Decimal("10"), subtotal=Decimal("10"),
        )
        self.client.force_login(self.admin)
        r = self.client.post(reverse("sucursales:eliminar", args=[self.item.pk]), follow=True)
        self.assertContains(r, "ventas asociadas")
        self.assertTrue(Sucursal.objects.filter(pk=self.item.pk).exists())


class LoginTests(BaseTest):
    def test_login_correcto(self):
        r = self.client.post(
            reverse("sucursales:login"), {"username": "admin1", "password": PASSWORD}
        )
        self.assertRedirects(r, reverse("sucursales:lista"))

    def test_login_incorrecto(self):
        r = self.client.post(
            reverse("sucursales:login"), {"username": "admin1", "password": "mala"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Usuario o contraseña incorrectos")

    def test_next_externo_es_ignorado(self):
        r = self.client.post(
            reverse("sucursales:login"),
            {"username": "admin1", "password": PASSWORD, "next": "https://evil.example/"},
        )
        self.assertRedirects(r, reverse("sucursales:lista"))

    def test_next_interno_se_respeta(self):
        destino = reverse("sucursales:crear")
        r = self.client.post(
            reverse("sucursales:login"),
            {"username": "admin1", "password": PASSWORD, "next": destino},
        )
        self.assertRedirects(r, destino, fetch_redirect_response=False)

    def test_logout_cierra_sesion(self):
        self.client.force_login(self.admin)
        r = self.client.post(reverse("sucursales:logout"))
        self.assertRedirects(r, reverse("sucursales:login"))
        self.assertEqual(self.client.get(reverse("sucursales:lista")).status_code, 302)


# ======================================================================
# Reportes (ORM)
# ======================================================================
from datetime import date, timedelta  # noqa: E402

from django.utils import timezone  # noqa: E402


class ReportesTests(BaseTest):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        Sucursal.objects.all().delete()
        hoy = timezone.localdate()
        cls.hoy = hoy
        cls.otra = Categoria.objects.create(nombre="Snacks", descripcion="y")

        cls.p1 = Sucursal.objects.create(categoria=cls.cat, sku="P1", nombre="P1", precio=Decimal("1000"), stock=3)
        cls.p2 = Sucursal.objects.create(categoria=cls.cat, sku="P2", nombre="P2", precio=Decimal("2500"), stock=20)
        cls.p3 = Sucursal.objects.create(categoria=cls.otra, sku="P3", nombre="P3", precio=Decimal("500"), stock=4)
        cls.p4 = Sucursal.objects.create(categoria=cls.otra, sku="P4", nombre="P4", precio=Decimal("9000"), stock=50)

        cls.c1 = Cliente.objects.create(rut="1-1", nombre="Cli Uno", email="a@a.cl", telefono="1")
        cls.c2 = Cliente.objects.create(rut="2-2", nombre="Cli Dos", email="b@a.cl", telefono="2")
        cls.c3 = Cliente.objects.create(rut="3-3", nombre="Cli Tres", email="c@a.cl", telefono="3")

        def venta(cliente, fecha, lineas):
            v = Venta.objects.create(cliente=cliente, estado="Pagada", total=Decimal("0"))
            total = Decimal("0")
            for prod, cant in lineas:
                sub = prod.precio * cant
                DetalleVenta.objects.create(
                    venta=v, sucursal=prod, cantidad=cant, precio_unitario=prod.precio, subtotal=sub
                )
                total += sub
            Venta.objects.filter(pk=v.pk).update(fecha=fecha, total=total)
            return v

        cls.v1 = venta(cls.c1, hoy, [(cls.p1, 2), (cls.p2, 1)])      # 4500
        cls.v2 = venta(cls.c1, hoy, [(cls.p2, 3)])                   # 7500
        cls.v3 = venta(cls.c2, date(hoy.year - 1, 6, 15), [(cls.p3, 10)])  # 5000

    def filas(self, numero, **params):
        self.client.force_login(self.operador)
        r = self.client.get(reverse("sucursales:reporte", args=[numero]), params)
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.context["resultado"], r.context.get("campos"))
        return r.context["resultado"]["rows"]

    def test_los_20_reportes_responden_200(self):
        params = {
            2: {"categoria": self.cat.pk},
            3: {"precio_min": "0", "precio_max": "100000"},
            6: {"cliente": self.c1.pk},
            7: {"venta": self.v1.pk},
            8: {"desde": "2000-01-01", "hasta": "2100-01-01"},
            10: {"fecha": self.hoy.isoformat()},
            18: {"anio": self.hoy.year},
            19: {"anio": self.hoy.year},
        }
        for n in range(1, 21):
            self.filas(n, **params.get(n, {}))

    def test_r1_a_r5(self):
        self.assertEqual(len(self.filas(1)), 4)
        self.assertEqual({f[1] for f in self.filas(2, categoria=self.otra.pk)}, {"P3", "P4"})
        self.assertEqual({f[1] for f in self.filas(3, precio_min="600", precio_max="2500")}, {"P1", "P2"})
        self.assertEqual(self.filas(4)[0][1], "P4")
        self.assertEqual(self.filas(5), [[3]])

    def test_r6_a_r12(self):
        self.assertEqual(len(self.filas(6, cliente=self.c1.pk)), 2)
        self.assertEqual({f[1] for f in self.filas(7, venta=self.v1.pk)}, {"P1", "P2"})
        r8 = self.filas(8, desde=self.hoy.isoformat(), hasta=self.hoy.isoformat())
        self.assertEqual(r8[0][2], 2)
        self.assertEqual({f[1] for f in self.filas(9)}, {"P1", "P3"})
        r10 = self.filas(10, fecha=self.hoy.isoformat())
        self.assertEqual((r10[0][1], r10[0][2]), (2, Decimal("12000")))
        r11 = self.filas(11)
        self.assertEqual((r11[0][1], r11[0][2]), ("P3", 10))
        r12 = self.filas(12)
        self.assertEqual((r12[0][1], r12[0][2]), ("Cli Uno", 2))

    def test_r13_a_r17(self):
        r13 = {f[1]: f[2] for f in self.filas(13)}
        self.assertEqual(r13, {"Cli Uno": Decimal("12000"), "Cli Dos": Decimal("5000"), "Cli Tres": Decimal("0")})
        self.assertEqual([f[1] for f in self.filas(14)], ["P4"])
        self.assertEqual(self.filas(15)[0][1], Decimal("5666.67"))
        r16 = self.filas(16)
        self.assertEqual((r16[0][0], r16[0][1]), (self.cat.nombre, Decimal("12000")))
        r17 = {f[1]: f[2] for f in self.filas(17)}
        self.assertEqual((r17["P2"], r17["P3"], r17["P4"]), (4, 0, 0))

    def test_r18_a_r20(self):
        r18 = self.filas(18, anio=self.hoy.year)
        self.assertEqual((r18[0][1], r18[0][2]), ("Cli Uno", Decimal("12000")))
        r19 = self.filas(19, anio=self.hoy.year)
        self.assertEqual(len(r19), 12)
        mes = r19[self.hoy.month - 1]
        self.assertEqual((mes[1], mes[2]), (2, Decimal("12000")))
        r20 = self.filas(20)
        self.assertEqual((r20[0][1], r20[0][2]), ("P2", Decimal("10000")))

    def test_parametros_invalidos_no_ejecutan(self):
        self.client.force_login(self.operador)
        url = reverse("sucursales:reporte", args=[3])
        r = self.client.get(url, {"precio_min": "abc", "precio_max": "10"})
        self.assertIsNone(r.context["resultado"])
        r = self.client.get(url, {"precio_min": "500", "precio_max": "10"})
        self.assertIsNone(r.context["resultado"])
        self.assertContains(r, "no puede ser mayor")
        r = self.client.get(reverse("sucursales:reporte", args=[19]), {"anio": "1"})
        self.assertIsNone(r.context["resultado"])

    def test_reporte_inexistente_404(self):
        self.client.force_login(self.operador)
        self.assertEqual(self.client.get(reverse("sucursales:reporte", args=[99])).status_code, 404)

    def test_reportes_exigen_login_y_rol(self):
        url = reverse("sucursales:reporte", args=[1])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.sin_rol)
        self.assertEqual(self.client.get(url).status_code, 403)
