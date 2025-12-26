from django.contrib import admin

from . import models


@admin.register(models.AmazonMarketplace)
class AmazonMarketplaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'marketplace_id', 'country_code', 'active', 'last_synced_at')
    list_filter = ('active', 'country_code')
    search_fields = ('name', 'marketplace_id')


class AmazonOrderItemInline(admin.TabularInline):
    model = models.AmazonOrderItem
    extra = 0
    readonly_fields = ('sku', 'quantity', 'item_price_amount', 'item_price_currency', 'article')


@admin.register(models.AmazonOrder)
class AmazonOrderAdmin(admin.ModelAdmin):
    list_display = (
        'amazon_order_id',
        'marketplace',
        'purchase_date',
        'order_status',
        'order_total_amount',
        'order_total_currency',
    )
    list_filter = ('marketplace', 'order_status', 'order_total_currency')
    search_fields = ('amazon_order_id',)
    readonly_fields = ('amazon_order_id', 'marketplace', 'purchase_date', 'order_status', 'order_total_amount', 'order_total_currency', 'ship_to_country', 'imported_at')
    inlines = [AmazonOrderItemInline]


@admin.register(models.AmazonOrderItem)
class AmazonOrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'sku', 'quantity', 'item_price_amount', 'item_price_currency', 'article')
    list_filter = ('item_price_currency',)
    search_fields = ('sku', 'order__amazon_order_id')
