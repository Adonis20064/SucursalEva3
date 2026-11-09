"""Decoradores de autorización reutilizables.

La autorización se aplica en el servidor (en cada vista); ocultar un botón
en la plantilla es solo una ayuda visual y nunca reemplaza esta comprobación.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

ADMINISTRADOR = "Administrador"
OPERADOR = "Operador"


def rol_requerido(*roles):
    """Permite el acceso solo a usuarios autenticados que pertenezcan a
    alguno de los grupos indicados. Ni siquiera un superusuario entra
    sin pertenecer a uno de ellos.

    - Sin sesión  -> redirige al login conservando ?next=
    - Sin el rol  -> PermissionDenied (HTTP 403)

    Uso:
        @rol_requerido(ADMINISTRADOR)
        @rol_requerido(ADMINISTRADOR, OPERADOR)
    """

    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            usuario = request.user
            if not usuario.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if usuario.groups.filter(name__in=roles).exists():
                return vista(request, *args, **kwargs)
            raise PermissionDenied("No tienes permisos para realizar esta acción.")

        return envoltura

    return decorador
