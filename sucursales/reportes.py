"""20 reportes comerciales resueltos 100 % con el ORM de Django.

Cada reporte es una función registrada con @reporte(...). Recibe los
parámetros ya validados y devuelve {"columns": [...], "rows": [[...]], "nota": str}.
Los filtros llegan por GET (son consultas de solo lectura) y se validan a mano.
"""
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, ExtractMonth
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .decorators import ADMINISTRADOR, OPERADOR, rol_requerido
from .models import Categoria, Cliente, DetalleVenta, Sucursal, Venta  # Sucursal = producto

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
CERO = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=2))

REPORTES = {}


def P(name, label, tipo):
    return {"name": name, "label": label, "tipo": tipo}


def reporte(numero, nivel, titulo, params=(), validar=None):
    def deco(func):
        REPORTES[numero] = {
            "numero": numero, "nivel": nivel, "titulo": titulo,
            "params": list(params), "validar": validar, "func": func,
        }
        return func
    return deco


def _tabla_productos(qs):
    return {
        "columns": ["SKU", "Nombre", "Categoría", "Precio ($)", "Stock", "Estado"],
        "rows": [
            [s.sku, s.nombre, s.categoria.nombre, s.precio, s.stock,
             "Activo" if s.activo else "Inactivo"]
            for s in qs.select_related("categoria")
        ],
    }


# ======================= BÁSICOS =======================
@reporte(1, "Básico", "Productos disponibles en la tienda")
def r01(p):
    """Disponible = activo y con stock."""
    return _tabla_productos(Sucursal.objects.filter(activo=True, stock__gt=0).order_by("nombre"))


@reporte(2, "Básico", "Productos de una categoría", [P("categoria", "Categoría", "categoria")])
def r02(p):
    return _tabla_productos(Sucursal.objects.filter(categoria=p["categoria"]).order_by("nombre"))


def _val_rango_precio(p):
    if p["precio_min"] > p["precio_max"]:
        return "El precio mínimo no puede ser mayor que el máximo."


@reporte(3, "Básico", "Productos dentro de un rango de precios",
         [P("precio_min", "Precio mínimo", "decimal"), P("precio_max", "Precio máximo", "decimal")],
         validar=_val_rango_precio)
def r03(p):
    qs = Sucursal.objects.filter(precio__range=(p["precio_min"], p["precio_max"])).order_by("precio")
    return _tabla_productos(qs)


@reporte(4, "Básico", "Los 10 productos más caros")
def r04(p):
    return _tabla_productos(Sucursal.objects.order_by("-precio", "nombre")[:10])


@reporte(5, "Básico", "Cantidad de clientes registrados")
def r05(p):
    return {"columns": ["Clientes registrados"], "rows": [[Cliente.objects.count()]]}


# ======================= INTERMEDIOS =======================
@reporte(6, "Intermedio", "Compras de un cliente", [P("cliente", "Cliente", "cliente")])
def r06(p):
    ventas = (
        Venta.objects.filter(cliente=p["cliente"])
        .annotate(items=Count("detalleventa"))
        .order_by("-fecha", "-id")
    )
    return {
        "columns": ["N.º venta", "Fecha", "Estado", "Total ($)", "Líneas de detalle"],
        "rows": [[v.id, v.fecha, v.estado, v.total, v.items] for v in ventas],
        "nota": f"Cliente: {p['cliente'].nombre}",
    }


@reporte(7, "Intermedio", "Productos de una venta determinada", [P("venta", "Venta", "venta")])
def r07(p):
    venta = p["venta"]
    detalles = DetalleVenta.objects.filter(venta=venta).select_related("sucursal").order_by("id")
    return {
        "columns": ["SKU", "Producto", "Cantidad", "Precio unitario ($)", "Subtotal ($)"],
        "rows": [[d.sucursal.sku, d.sucursal.nombre, d.cantidad, d.precio_unitario, d.subtotal]
                 for d in detalles],
        "nota": f"Venta N.º {venta.id} · Cliente: {venta.cliente.nombre} · Fecha: {venta.fecha}",
    }


def _val_rango_fechas(p):
    if p["desde"] > p["hasta"]:
        return "La fecha inicial no puede ser posterior a la final."


@reporte(8, "Intermedio", "Ventas realizadas en un período",
         [P("desde", "Desde", "fecha"), P("hasta", "Hasta", "fecha")], validar=_val_rango_fechas)
def r08(p):
    agg = Venta.objects.filter(fecha__range=(p["desde"], p["hasta"])).aggregate(
        n=Count("id"), monto=Sum("total")
    )
    return {
        "columns": ["Desde", "Hasta", "N.º de ventas", "Monto total ($)"],
        "rows": [[p["desde"], p["hasta"], agg["n"], agg["monto"] or 0]],
    }


@reporte(9, "Intermedio", "Productos con menos de 5 unidades")
def r09(p):
    return _tabla_productos(Sucursal.objects.filter(stock__lt=5).order_by("stock", "nombre"))


@reporte(10, "Intermedio", "Monto vendido en un día", [P("fecha", "Fecha", "fecha")])
def r10(p):
    agg = Venta.objects.filter(fecha=p["fecha"]).aggregate(n=Count("id"), monto=Sum("total"))
    return {
        "columns": ["Fecha", "N.º de ventas", "Monto total ($)"],
        "rows": [[p["fecha"], agg["n"], agg["monto"] or 0]],
    }


@reporte(11, "Intermedio", "Los 5 productos más vendidos (unidades)")
def r11(p):
    qs = (
        Sucursal.objects.annotate(unidades=Sum("detalleventa__cantidad"))
        .filter(unidades__isnull=False)
        .order_by("-unidades", "nombre")[:5]
    )
    return {
        "columns": ["SKU", "Producto", "Unidades vendidas"],
        "rows": [[s.sku, s.nombre, s.unidades] for s in qs],
    }


@reporte(12, "Intermedio", "Los 5 clientes con más compras")
def r12(p):
    qs = (
        Cliente.objects.annotate(compras=Count("venta"))
        .filter(compras__gt=0)
        .order_by("-compras", "nombre")[:5]
    )
    return {
        "columns": ["RUT", "Cliente", "N.º de compras"],
        "rows": [[c.rut, c.nombre, c.compras] for c in qs],
    }


# ======================= AVANZADOS =======================
@reporte(13, "Avanzado", "Monto total comprado por cada cliente")
def r13(p):
    qs = Cliente.objects.annotate(
        monto=Coalesce(Sum("venta__total"), CERO, output_field=DecimalField())
    ).order_by("-monto", "nombre")
    return {
        "columns": ["RUT", "Cliente", "Monto total comprado ($)"],
        "rows": [[c.rut, c.nombre, c.monto] for c in qs],
    }


@reporte(14, "Avanzado", "Productos que nunca se han vendido")
def r14(p):
    return _tabla_productos(Sucursal.objects.filter(detalleventa__isnull=True).order_by("nombre"))


@reporte(15, "Avanzado", "Promedio de dinero gastado por venta")
def r15(p):
    agg = Venta.objects.aggregate(prom=Avg("total"), n=Count("id"))
    prom = Decimal(str(agg["prom"])) if agg["prom"] is not None else Decimal("0")
    return {
        "columns": ["N.º de ventas", "Promedio por venta ($)"],
        "rows": [[agg["n"], prom.quantize(Decimal("0.01"))]],
    }


@reporte(16, "Avanzado", "Categoría que genera más ventas")
def r16(p):
    qs = (
        Categoria.objects.annotate(monto=Sum("sucursal__detalleventa__subtotal"))
        .filter(monto__isnull=False)
        .order_by("-monto", "nombre")
    )
    return {
        "columns": ["Categoría", "Monto vendido ($)"],
        "rows": [[c.nombre, c.monto] for c in qs],
        "nota": "La primera fila es la categoría con mayor monto de ventas.",
    }


@reporte(17, "Avanzado", "Unidades vendidas por producto en el último mes")
def r17(p):
    """Último mes = los últimos 30 días contados desde hoy."""
    desde = timezone.localdate() - timedelta(days=30)
    qs = Sucursal.objects.annotate(
        unidades=Coalesce(
            Sum("detalleventa__cantidad", filter=Q(detalleventa__venta__fecha__gte=desde)), 0
        )
    ).order_by("-unidades", "nombre")
    return {
        "columns": ["SKU", "Producto", "Unidades vendidas"],
        "rows": [[s.sku, s.nombre, s.unidades] for s in qs],
        "nota": f"Período: desde {desde} hasta hoy (30 días).",
    }


# ======================= ANÁLISIS =======================
@reporte(18, "Análisis", "Cliente que más gastó en el año", [P("anio", "Año", "anio")])
def r18(p):
    qs = (
        Cliente.objects.annotate(gasto=Sum("venta__total", filter=Q(venta__fecha__year=p["anio"])))
        .filter(gasto__isnull=False)
        .order_by("-gasto", "nombre")[:5]
    )
    return {
        "columns": ["RUT", "Cliente", f"Gasto en {p['anio']} ($)"],
        "rows": [[c.rut, c.nombre, c.gasto] for c in qs],
        "nota": "Ranking de los 5 mayores; la primera fila es la respuesta.",
    }


@reporte(19, "Análisis", "Ventas por mes en un año", [P("anio", "Año", "anio")])
def r19(p):
    datos = {
        f["mes"]: f
        for f in Venta.objects.filter(fecha__year=p["anio"])
        .annotate(mes=ExtractMonth("fecha"))
        .values("mes")
        .annotate(n=Count("id"), monto=Sum("total"))
        .order_by("mes")
    }
    filas = []
    for i, nombre in enumerate(MESES, start=1):
        d = datos.get(i)
        filas.append([nombre, d["n"] if d else 0, d["monto"] if d else 0])
    return {"columns": ["Mes", "N.º de ventas", "Monto total ($)"], "rows": filas}


@reporte(20, "Análisis", "Los 10 productos que generan más ingresos")
def r20(p):
    qs = (
        Sucursal.objects.annotate(ingresos=Sum("detalleventa__subtotal"))
        .filter(ingresos__isnull=False)
        .order_by("-ingresos", "nombre")[:10]
    )
    return {
        "columns": ["SKU", "Producto", "Ingresos ($)"],
        "rows": [[s.sku, s.nombre, s.ingresos] for s in qs],
    }


# ======================= Validación de parámetros =======================
def _limpiar(param, crudo):
    """Devuelve (valor, error). Valida a mano, sin ModelForm."""
    crudo = (crudo or "").strip()
    tipo = param["tipo"]
    if not crudo:
        return None, "Este campo es obligatorio."

    if tipo in ("categoria", "cliente", "venta"):
        modelo = {"categoria": Categoria, "cliente": Cliente, "venta": Venta}[tipo]
        if not crudo.isdigit():
            return None, "Selección no válida."
        obj = modelo.objects.filter(pk=int(crudo)).first()
        return (obj, None) if obj else (None, "El registro seleccionado no existe.")

    if tipo == "fecha":
        try:
            return date.fromisoformat(crudo), None
        except ValueError:
            return None, "Fecha no válida (use AAAA-MM-DD)."

    if tipo == "decimal":
        try:
            valor = Decimal(crudo.replace(",", "."))
        except InvalidOperation:
            return None, "Ingrese un número válido."
        if not valor.is_finite() or valor < 0 or valor >= Decimal(10) ** 10:
            return None, "Ingrese un monto válido (≥ 0)."
        return valor, None

    if tipo == "anio":
        if not crudo.isdigit() or not (2000 <= int(crudo) <= 2100):
            return None, "Ingrese un año entre 2000 y 2100."
        return int(crudo), None

    return None, "Tipo de parámetro desconocido."


def _opciones(tipo):
    if tipo == "categoria":
        return [(c.pk, c.nombre) for c in Categoria.objects.order_by("nombre")]
    if tipo == "cliente":
        return [(c.pk, f"{c.nombre} ({c.rut})") for c in Cliente.objects.order_by("nombre")]
    if tipo == "venta":
        return [
            (v.pk, f"Venta N.º {v.pk} · {v.cliente.nombre} · {v.fecha}")
            for v in Venta.objects.select_related("cliente").order_by("-fecha", "-id")
        ]
    return None


# ======================= Vistas =======================
@login_required
@rol_requerido(ADMINISTRADOR, OPERADOR)
@require_http_methods(["GET"])
def indice(request):
    niveles = {}
    for r in sorted(REPORTES.values(), key=lambda x: x["numero"]):
        niveles.setdefault(r["nivel"], []).append(r)
    return render(request, "sucursales/reportes_indice.html", {"niveles": niveles})


@login_required
@rol_requerido(ADMINISTRADOR, OPERADOR)
@require_http_methods(["GET"])
def detalle(request, numero):
    rep = REPORTES.get(numero)
    if rep is None:
        raise Http404("Reporte inexistente")

    params = rep["params"]
    enviado = any(p["name"] in request.GET for p in params)
    limpios, errores = {}, {}

    if enviado:
        for p in params:
            valor, error = _limpiar(p, request.GET.get(p["name"]))
            if error:
                errores[p["name"]] = error
            else:
                limpios[p["name"]] = valor
        if not errores and rep["validar"]:
            msg = rep["validar"](limpios)
            if msg:
                errores["__general__"] = msg

    resultado = None
    if (not params) or (enviado and not errores):
        resultado = rep["func"](limpios)

    campos = []
    for p in params:
        valor = request.GET.get(p["name"], "")
        if not valor and not enviado and p["tipo"] == "anio":
            valor = str(timezone.localdate().year)
        campos.append({
            "p": p,
            "valor": valor,
            "opciones": _opciones(p["tipo"]),
            "error": errores.get(p["name"]),
        })

    return render(request, "sucursales/reporte.html", {
        "rep": rep,
        "campos": campos,
        "error_general": errores.get("__general__"),
        "resultado": resultado,
        "enviado": enviado,
    })
