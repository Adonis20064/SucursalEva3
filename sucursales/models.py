from django.db import models

# Create your models here.
from django.db import models

# Create your models here.
class Categoria(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    
    
    def __str__(self):
        return self.nombre
    
class Sucursal(models.Model):
    categoria = models.ForeignKey(Categoria, on_delete= models.PROTECT)
    sku = models.CharField(max_length=50)
    nombre = models.CharField(max_length=150)
    precio = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.IntegerField()
    activo = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre
    
    

class Cliente(models.Model):
    rut = models.CharField(max_length=20)
    nombre = models.CharField(max_length=150)
    email = models.EmailField()
    telefono = models.CharField(max_length=30)
    
    def __str__(self):
        return self.nombre
    

class Venta(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    fecha = models.DateField(auto_now_add=True)
    estado = models.CharField(max_length=20)
    total = models.DecimalField(max_digits=14, decimal_places=2)    
    def __str__(self):
        return f"Venta {self.id} - {self.cliente.nombre}"    
    
class DetalleVenta(models.Model):
    venta = models.ForeignKey(Venta, on_delete=models.PROTECT)
    sucursal = models.ForeignKey(Sucursal, on_delete=models.PROTECT)
    cantidad = models.IntegerField()
    precio_unitario = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2)
    
    def __str__(self):
        return f"Detalle de Venta {self.venta.id} - {self.sucursal.nombre}"