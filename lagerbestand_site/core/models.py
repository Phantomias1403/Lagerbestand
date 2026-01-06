from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator

if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager


class User(AbstractUser):
    """Custom user model adding profile metadata used in the legacy Flask app."""

    display_name = models.CharField('Anzeigename', max_length=120, blank=True)
    gender = models.CharField('Geschlecht', max_length=20, blank=True)
    bio = models.TextField('Kurzbeschreibung', max_length=500, blank=True)
    profile_image = models.ImageField('Profilbild', upload_to='profile_pics/', blank=True, null=True)

    class Meta:
        verbose_name = 'Benutzer'
        verbose_name_plural = 'Benutzer'

    def has_staff_rights(self) -> bool:
        return self.is_staff or self.is_superuser


class TimestampedModel(models.Model):
    created_at = models.DateTimeField('Erstellt am', default=timezone.now, editable=False)
    updated_at = models.DateTimeField('Aktualisiert am', auto_now=True)

    class Meta:
        abstract = True


class Category(models.Model):
    id: int
    name = models.CharField(max_length=100, unique=True)
    prefix = models.CharField(max_length=20, unique=True, blank=True)
    default_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    default_min_stock = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['name']
        verbose_name = 'Kategorie'
        verbose_name_plural = 'Kategorien'

    def __str__(self) -> str:
        return self.name


class Article(TimestampedModel):
    id: int
    name = models.CharField(max_length=120)
    sku = models.CharField(max_length=64, unique=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='articles')
    category_id: int
    stock = models.IntegerField(default=0)
    minimum_stock = models.IntegerField(default=0)
    location_primary = models.CharField(max_length=80, blank=True)
    location_secondary = models.CharField(max_length=80, blank=True)
    image = models.URLField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    if TYPE_CHECKING:
        mix_components: RelatedManager["ArticleMixComponent"]
        movements: RelatedManager["Movement"]

    class Meta:
        ordering = ['sku']
        verbose_name = 'Artikel'
        verbose_name_plural = 'Artikel'

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"


class ArticleMixComponent(models.Model):
    id: int
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='mix_components')
    component_sku = models.CharField(max_length=64)
    component_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Mix Komponente'
        verbose_name_plural = 'Mix Komponenten'

    def __str__(self) -> str:
        return f"{self.component_quantity}x {self.component_sku}"


class EndingCategory(models.Model):
    id: int
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='suffix_rules')
    suffix = models.CharField(max_length=20, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    csv_multiplier = models.PositiveIntegerField(default=1)

    if TYPE_CHECKING:
        components: RelatedManager["EndingComponent"]

    class Meta:
        verbose_name = 'Suffix Regel'
        verbose_name_plural = 'Suffix Regeln'

    def __str__(self) -> str:
        return f"{self.category} -> {self.suffix}"


class EndingComponent(models.Model):
    id: int
    ending = models.ForeignKey(EndingCategory, on_delete=models.CASCADE, related_name='components')
    component_sku = models.CharField(max_length=64)
    component_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    class Meta:
        verbose_name = 'Suffix Komponente'
        verbose_name_plural = 'Suffix Komponenten'

    def __str__(self) -> str:
        return f"{self.component_quantity}x {self.component_sku}"


class Order(TimestampedModel):
    id: int
    STATUS_CHOICES = [
        ('offen', 'Offen'),
        ('bezahlt', 'Bezahlt'),
        ('storniert', 'Storniert'),
        ('abgeschlossen', 'Abgeschlossen'),
    ]

    customer_name = models.CharField(max_length=120)
    customer_address = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offen')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    order_number = models.CharField(max_length=100, blank=True)
    order_quantity = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bestellung'
        verbose_name_plural = 'Bestellungen'

    @property
    def total_price(self) -> Decimal:
        return sum((item.quantity * item.unit_price for item in self.items.all()), Decimal('0'))

    if TYPE_CHECKING:
        items: RelatedManager["OrderItem"]
        movements: RelatedManager["Movement"]


class OrderItem(models.Model):
    id: int
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    order_id: int
    article = models.ForeignKey(Article, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = 'Bestellposition'
        verbose_name_plural = 'Bestellpositionen'

    def __str__(self) -> str:
        return f"{self.quantity}x {self.article.sku}"

    @property
    def line_total(self) -> Decimal:
        return self.quantity * self.unit_price


class Movement(TimestampedModel):
    id: int
    MOVEMENT_TYPES = [
        ('Wareneingang', 'Wareneingang'),
        ('Warenausgang', 'Warenausgang'),
        ('Inventur', 'Inventur'),
        ('Verlust', 'Verlust'),
        ('Korrektur', 'Korrektur'),
    ]

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='movements')
    quantity = models.IntegerField()
    note = models.CharField(max_length=200, blank=True)
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES, default='Wareneingang')
    invoice_number = models.CharField(max_length=100, blank=True)
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    order_id: int | None

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bewegung'
        verbose_name_plural = 'Bewegungen'

    def __str__(self) -> str:
        return f"{self.movement_type} {self.quantity} {self.article.sku}"


class Message(TimestampedModel):
    id: int
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages')
    content = models.TextField(max_length=500)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Nachricht'
        verbose_name_plural = 'Nachrichten'

    def __str__(self) -> str:
        return f"{self.sender} -> {self.receiver}"


class ActivityLog(TimestampedModel):
    id: int
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='activity_logs')
    action = models.CharField(max_length=255)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Aktivitätsprotokoll'
        verbose_name_plural = 'Aktivitätsprotokolle'

    def __str__(self) -> str:
        return f"{self.user}: {self.action}"
