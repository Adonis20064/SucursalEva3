from django.contrib.auth.models import Group, Permission, User
from django.core.management.base import BaseCommand

from sucursales.decorators import ADMINISTRADOR, OPERADOR


class Command(BaseCommand):
    help = "Crea los grupos Administrador y Operador (y opcionalmente usuarios de demostración)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--con-usuarios",
            action="store_true",
            help="Crea los usuarios de demo 'administrador' y 'operador'.",
        )
        parser.add_argument("--password", default="Demo12345!", help="Contraseña de los usuarios demo.")

    def handle(self, *args, **opts):
        def perms(*codenames):
            return Permission.objects.filter(
                content_type__app_label="sucursales", codename__in=codenames
            )

        admin_g, _ = Group.objects.get_or_create(name=ADMINISTRADOR)
        oper_g, _ = Group.objects.get_or_create(name=OPERADOR)

        admin_g.permissions.set(
            Permission.objects.filter(content_type__app_label="sucursales")
        )
        oper_g.permissions.set(
            perms("view_sucursal", "add_sucursal", "change_sucursal", "view_categoria")
        )
        self.stdout.write(self.style.SUCCESS("Grupos Administrador y Operador listos."))

        if opts["con_usuarios"]:
            for username, grupo, staff in (
                ("administrador", admin_g, True),
                ("operador", oper_g, False),
            ):
                user, creado = User.objects.get_or_create(
                    username=username, defaults={"is_staff": staff}
                )
                if creado:
                    user.set_password(opts["password"])
                    user.save()
                user.groups.add(grupo)
                estado = "creado" if creado else "ya existía"
                self.stdout.write(f"Usuario {username}: {estado} (grupo {grupo.name}).")
            self.stdout.write(f"Contraseña de los usuarios nuevos: {opts['password']}")
