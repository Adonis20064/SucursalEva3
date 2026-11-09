from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from .decorators import ADMINISTRADOR, OPERADOR, rol_requerido
from .models import Categoria, Sucursal

MAX_ENTERO = 2_147_483_647  # límite de IntegerField
LIMITE_PRECIO = Decimal(10) ** 10  # DecimalField(max_digits=12, decimal_places=2)


# --------------------------------------------------------------------------
# Autenticación
# --------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("sucursales:lista")

    siguiente = request.POST.get("next") or request.GET.get("next", "")
    error = None
    username = ""

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if not username or not password:
            error = "Ingresa usuario y contraseña."
        else:
            usuario = authenticate(request, username=username, password=password)
            if usuario is None:
                
                error = "Usuario o contraseña incorrectos."
            else:
                login(request, usuario)
                messages.success(request, f"Bienvenido/a, {usuario.get_username()}.")
                if siguiente and url_has_allowed_host_and_scheme(
                    siguiente,
                    allowed_hosts={request.get_host()},
                    require_https=request.is_secure(),
                ):
                    return redirect(siguiente)
                return redirect("sucursales:lista")

    return render(
        request,
        "sucursales/login.html",
        {"error": error, "username": username, "next": siguiente},
    )


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "Sesión cerrada correctamente.")
    return redirect("sucursales:login")


# --------------------------------------------------------------------------
# Validación manual (sin ModelForm): todo se lee desde request.POST
# --------------------------------------------------------------------------
def _validar_sucursal(post, excluir_pk=None):
    """Devuelve (datos_limpios, errores). No toca la base salvo para consultas."""
    errores = {}
    limpios = {}

    sku = post.get("sku", "").strip()
    if not sku:
        errores["sku"] = "El SKU es obligatorio."
    elif len(sku) > 50:
        errores["sku"] = "El SKU no puede superar los 50 caracteres."
    elif Sucursal.objects.filter(sku__iexact=sku).exclude(pk=excluir_pk).exists():
        errores["sku"] = "Ya existe un registro con ese SKU."
    limpios["sku"] = sku

    nombre = post.get("nombre", "").strip()
    if not nombre:
        errores["nombre"] = "El nombre es obligatorio."
    elif len(nombre) > 150:
        errores["nombre"] = "El nombre no puede superar los 150 caracteres."
    limpios["nombre"] = nombre

    categoria = None
    categoria_raw = post.get("categoria", "").strip()
    if not categoria_raw.isdigit():
        errores["categoria"] = "Selecciona una categoría."
    else:
        categoria = Categoria.objects.filter(pk=int(categoria_raw)).first()
        if categoria is None:
            errores["categoria"] = "La categoría seleccionada no existe."
    limpios["categoria"] = categoria

    precio_raw = post.get("precio", "").strip().replace(",", ".")
    precio = None
    try:
        precio = Decimal(precio_raw)
    except InvalidOperation:
        errores["precio"] = "Ingresa un precio numérico válido."
    else:
        if not precio.is_finite():
            errores["precio"] = "Ingresa un precio numérico válido."
        elif precio < 0:
            errores["precio"] = "El precio no puede ser negativo."
        elif precio >= LIMITE_PRECIO:
            errores["precio"] = "El precio es demasiado alto."
        elif precio != precio.quantize(Decimal("0.01")):
            errores["precio"] = "El precio admite como máximo 2 decimales."
    limpios["precio"] = precio

    stock_raw = post.get("stock", "").strip()
    stock = None
    try:
        stock = int(stock_raw)
    except ValueError:
        errores["stock"] = "El stock debe ser un número entero."
    else:
        if stock < 0:
            errores["stock"] = "El stock no puede ser negativo."
        elif stock > MAX_ENTERO:
            errores["stock"] = "El stock es demasiado alto."
    limpios["stock"] = stock

    # Un checkbox solo llega en POST cuando está marcado.
    limpios["activo"] = post.get("activo") == "on"

    return limpios, errores


def _contexto_form(titulo, accion, datos, errores, objeto=None):
    return {
        "titulo": titulo,
        "accion": accion,
        "categorias": Categoria.objects.order_by("nombre"),
        "datos": datos,
        "errores": errores,
        "objeto": objeto,
    }


# --------------------------------------------------------------------------
# CRUD (Administrador: todo · Operador: listar, crear y editar)
# --------------------------------------------------------------------------
@login_required
@rol_requerido(ADMINISTRADOR, OPERADOR)
@require_http_methods(["GET"])
def lista(request):
    sucursales = Sucursal.objects.select_related("categoria").order_by("nombre")
    es_admin = request.user.groups.filter(name=ADMINISTRADOR).exists()
    return render(
        request,
        "sucursales/lista.html",
        {"sucursales": sucursales, "es_admin": es_admin},
    )


@login_required
@rol_requerido(ADMINISTRADOR, OPERADOR)
@require_http_methods(["GET", "POST"])
def crear(request):
    if request.method == "POST":
        limpios, errores = _validar_sucursal(request.POST)
        if not errores:
            Sucursal.objects.create(**limpios)
            messages.success(request, f"«{limpios['nombre']}» fue creado correctamente.")
            return redirect("sucursales:lista")
        messages.error(request, "Revisa los campos marcados.")
        datos = {
            "sku": request.POST.get("sku", ""),
            "nombre": request.POST.get("nombre", ""),
            "categoria": request.POST.get("categoria", ""),
            "precio": request.POST.get("precio", ""),
            "stock": request.POST.get("stock", ""),
            "activo": request.POST.get("activo") == "on",
        }
    else:
        errores = {}
        datos = {"sku": "", "nombre": "", "categoria": "", "precio": "", "stock": "0", "activo": True}

    return render(
        request,
        "sucursales/form.html",
        _contexto_form("Nuevo registro", "Crear", datos, errores),
    )


@login_required
@rol_requerido(ADMINISTRADOR, OPERADOR)
@require_http_methods(["GET", "POST"])
def editar(request, pk):
    objeto = get_object_or_404(Sucursal, pk=pk)

    if request.method == "POST":
        limpios, errores = _validar_sucursal(request.POST, excluir_pk=objeto.pk)
        if not errores:
            for campo, valor in limpios.items():
                setattr(objeto, campo, valor)
            objeto.save()
            messages.success(request, f"«{objeto.nombre}» fue actualizado correctamente.")
            return redirect("sucursales:lista")
        messages.error(request, "Revisa los campos marcados.")
        datos = {
            "sku": request.POST.get("sku", ""),
            "nombre": request.POST.get("nombre", ""),
            "categoria": request.POST.get("categoria", ""),
            "precio": request.POST.get("precio", ""),
            "stock": request.POST.get("stock", ""),
            "activo": request.POST.get("activo") == "on",
        }
    else:
        errores = {}
        datos = {
            "sku": objeto.sku,
            "nombre": objeto.nombre,
            "categoria": str(objeto.categoria_id),
            "precio": str(objeto.precio),
            "stock": str(objeto.stock),
            "activo": objeto.activo,
        }

    return render(
        request,
        "sucursales/form.html",
        _contexto_form("Editar registro", "Guardar cambios", datos, errores, objeto),
    )


@login_required
@rol_requerido(ADMINISTRADOR)
@require_POST
def eliminar(request, pk):
    objeto = get_object_or_404(Sucursal, pk=pk)
    nombre = objeto.nombre
    try:
        objeto.delete()
    except ProtectedError:
        messages.error(
            request,
            f"No se puede eliminar «{nombre}» porque tiene ventas asociadas.",
        )
    else:
        messages.success(request, f"«{nombre}» fue eliminado correctamente.")
    return redirect("sucursales:lista")
