from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from . import models


@admin.register(models.User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Profil', {'fields': ('display_name', 'gender', 'bio', 'profile_image')}),
    )
    list_display = ['username', 'email', 'is_active', 'is_staff', 'is_superuser']


@admin.register(models.Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'prefix', 'default_price', 'default_min_stock']
    search_fields = ['name', 'prefix']


@admin.register(models.Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'stock', 'minimum_stock', 'price']
    search_fields = ['sku', 'name']
    list_filter = ['category']


@admin.register(models.Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer_name', 'status', 'marketplace', 'created_at']
    list_filter = ['status', 'marketplace', 'created_at']
    search_fields = ['customer_name', 'order_number']


@admin.register(models.OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'article', 'quantity', 'unit_price']


@admin.register(models.Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ['article', 'movement_type', 'quantity', 'created_at']
    list_filter = ['movement_type', 'created_at']


@admin.register(models.EndingCategory)
class EndingCategoryAdmin(admin.ModelAdmin):
    list_display = ['category', 'suffix', 'price', 'csv_multiplier']


@admin.register(models.EndingComponent)
class EndingComponentAdmin(admin.ModelAdmin):
    list_display = ['ending', 'component_sku', 'component_quantity']


@admin.register(models.ArticleMixComponent)
class ArticleMixComponentAdmin(admin.ModelAdmin):
    list_display = ['article', 'component_sku', 'component_quantity']


@admin.register(models.ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'created_at']


@admin.register(models.Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['sender', 'receiver', 'created_at']
