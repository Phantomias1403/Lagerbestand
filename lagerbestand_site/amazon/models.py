from __future__ import annotations

from django.db import models
from django.utils import timezone


class AmazonMarketplace(models.Model):
    name = models.CharField(max_length=120)
    marketplace_id = models.CharField(max_length=32, unique=True)
    country_code = models.CharField(max_length=2)
    active = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Amazon-Marktplatz'
        verbose_name_plural = 'Amazon-Marktplätze'

    def __str__(self) -> str:
        return f"{self.name} ({self.marketplace_id})"


class AmazonOrder(models.Model):
    amazon_order_id = models.CharField(max_length=40, unique=True)
    marketplace = models.ForeignKey(
        AmazonMarketplace,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    ship_to_country = models.CharField(max_length=2, blank=True)
    purchase_date = models.DateTimeField()
    order_status = models.CharField(max_length=40)
    order_total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    order_total_currency = models.CharField(max_length=3)
    imported_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['-purchase_date']
        verbose_name = 'Amazon-Bestellung'
        verbose_name_plural = 'Amazon-Bestellungen'

    def __str__(self) -> str:
        return self.amazon_order_id


class AmazonOrderItem(models.Model):
    order = models.ForeignKey(AmazonOrder, on_delete=models.CASCADE, related_name='items')
    sku = models.CharField(max_length=64)
    quantity = models.PositiveIntegerField()
    item_price_amount = models.DecimalField(max_digits=12, decimal_places=2)
    item_price_currency = models.CharField(max_length=3)
    article = models.ForeignKey(
        'core.Article', on_delete=models.SET_NULL, null=True, blank=True, related_name='amazon_items'
    )

    class Meta:
        verbose_name = 'Amazon-Bestellposition'
        verbose_name_plural = 'Amazon-Bestellpositionen'

    def __str__(self) -> str:
        return f"{self.quantity}x {self.sku}"
