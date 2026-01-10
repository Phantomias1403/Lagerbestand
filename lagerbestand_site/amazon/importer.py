from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from core import models as core_models

from .models import AmazonMarketplace, AmazonOrder, AmazonOrderItem
from .sp_api import AmazonCredentials, AmazonSpApiError, SellingPartnerClient, parse_decimal

User = get_user_model()


class ActivityLogger:
    def __init__(self):
        self.user = self._get_system_user()

    def _get_system_user(self):
        user = User.objects.filter(is_superuser=True).first()
        if not user:
            user = User.objects.order_by('pk').first()
        if not user:
            user = User.objects.create(username='system', is_superuser=False, is_staff=False)
            user.set_unusable_password()
            user.save(update_fields=['password'])
        return user

    def log(self, message: str) -> None:
        core_models.ActivityLog.objects.create(user=self.user, action=message)


class AmazonOrderImporter:
    def __init__(self):
        self.logger = ActivityLogger()
        self.client = self._build_client()
        self.errors: list[str] = []

    def _required_env(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise AmazonSpApiError(f"Fehlende Umgebungsvariable {name}.")
        return value

    def _build_client(self) -> SellingPartnerClient:
        credentials = AmazonCredentials(
            client_id=self._required_env('AMAZON_CLIENT_ID'),
            client_secret=self._required_env('AMAZON_CLIENT_SECRET'),
            refresh_token=self._required_env('AMAZON_REFRESH_TOKEN'),
        )
        return SellingPartnerClient(credentials)

    def import_orders(self) -> int:
        self.errors = []
        created_orders = 0
        marketplaces = AmazonMarketplace.objects.filter(active=True)
        for marketplace in marketplaces:
            try:
                created_orders += self._import_marketplace_orders(marketplace)
                #marketplace.last_synced_at = timezone.now()
                marketplace.save(update_fields=['last_synced_at'])
            except AmazonSpApiError as exc:
                self.logger.log(f"Import fehlgeschlagen || {marketplace.marketplace_id}: {exc}")
                self.errors.append(f"{marketplace.marketplace_id}: {exc}")
        if not self.errors:
            self.logger.log(f"Import erfolgreich || Anzahl der Bestellungen: {created_orders}")
        return created_orders

    def import_latest_orders(self) -> int:
        self.errors = []
        updated_orders = 0
        marketplaces = AmazonMarketplace.objects.filter(active=True)
        for marketplace in marketplaces:
            try:
                updated_orders += self._import_latest_marketplace_order(marketplace)
            except AmazonSpApiError as exc:
                self.logger.log(f"Import fehlgeschlagen || {marketplace.marketplace_id}: {exc}")
                self.errors.append(f"{marketplace.marketplace_id}: {exc}")
        if not self.errors:
            self.logger.log(f"Letzte Bestellung importiert || Anzahl der Bestellungen: {updated_orders}")
        return updated_orders

    def _import_marketplace_orders(self, marketplace: AmazonMarketplace) -> int:
        created_orders = 0

        # Erstimport: mehr Historie holen
        if marketplace.last_synced_at:
            since = marketplace.last_synced_at
        else:
            since = timezone.now() - timedelta(days=30)  # statt 48h

        orders = list(self.client.list_orders(marketplace.marketplace_id, since))
        self.logger.log(f"{marketplace.marketplace_id}: Orders von Amazon erhalten: {len(orders)} (since={since.isoformat()})")

        for order_payload in orders:
            amazon_order_id = order_payload.get("AmazonOrderId")
            if amazon_order_id and AmazonOrder.objects.filter(amazon_order_id=amazon_order_id).exists():
                continue
            created = self._store_order(order_payload, marketplace)
            created_orders += 1 if created else 0

        return created_orders

    def _import_latest_marketplace_order(self, marketplace: AmazonMarketplace) -> int:
        since = marketplace.last_synced_at or timezone.now() - timedelta(hours=48)
        orders = list(self.client.list_orders(marketplace.marketplace_id, since))
        if not orders:
            return 0
        latest_order_payload = max(
            orders,
            key=lambda payload: self._parse_datetime(payload.get('PurchaseDate')),
        )
        return 1 if self._store_order(latest_order_payload, marketplace, allow_update=True) else 0

    def _store_order(self, payload: Dict[str, Any], marketplace: AmazonMarketplace, allow_update: bool = False) -> bool:
        amazon_order_id = payload.get('AmazonOrderId')
        if not amazon_order_id:
            return False
        total = payload.get('OrderTotal', {}) or {}
        with transaction.atomic():
            existing_order = AmazonOrder.objects.filter(amazon_order_id=amazon_order_id).first()
            if existing_order and allow_update:
                existing_order.marketplace = marketplace
                existing_order.ship_to_country = (payload.get('ShippingAddress') or {}).get('CountryCode', '')
                existing_order.purchase_date = self._parse_datetime(payload.get('PurchaseDate'))
                existing_order.order_status = payload.get('OrderStatus', '')
                existing_order.order_total_amount = parse_decimal(total.get('Amount'))
                existing_order.order_total_currency = total.get('CurrencyCode', '')
                existing_order.save(update_fields=[
                    'marketplace',
                    'ship_to_country',
                    'purchase_date',
                    'order_status',
                    'order_total_amount',
                    'order_total_currency',
                ])
                AmazonOrderItem.objects.filter(order=existing_order).delete()

                order = existing_order
            else:
                order = AmazonOrder.objects.create(
                    amazon_order_id=amazon_order_id,
                    marketplace=marketplace,
                    ship_to_country=(payload.get('ShippingAddress') or {}).get('CountryCode', ''),
                    purchase_date=self._parse_datetime(payload.get('PurchaseDate')),
                    order_status=payload.get('OrderStatus', ''),
                    order_total_amount=parse_decimal(total.get('Amount')),
                    order_total_currency=total.get('CurrencyCode', ''),
                )
            core_order = self._sync_core_order(order, payload)
            for item_payload in self.client.list_order_items(amazon_order_id):
                self._store_item(order, item_payload)
                self._store_core_item(core_order, item_payload)
            self._update_core_order_quantity(core_order)
        return True

    def _store_item(self, order: AmazonOrder, payload: Dict[str, Any]) -> None:
        price = (payload.get('ItemPrice') or {})
        sku = payload.get('SellerSKU', '')
        article = core_models.Article.objects.filter(sku=sku).first()
        AmazonOrderItem.objects.create(
            order=order,
            sku=sku,
            quantity=int(payload.get('QuantityOrdered', 0) or 0),
            item_price_amount=parse_decimal(price.get('Amount')),
            item_price_currency=price.get('CurrencyCode', order.order_total_currency),
            article=article,
        )

    def _sync_core_order(self, order: AmazonOrder, payload: Dict[str, Any]) -> core_models.Order:
        status = self._map_order_status(payload.get('OrderStatus'))
        customer_name = self._build_customer_name(payload)
        customer_address = self._build_customer_address(payload)
        core_order, _ = core_models.Order.objects.update_or_create(
            order_number=order.amazon_order_id,
            defaults={
                'customer_name': customer_name,
                'customer_address': customer_address,
                'status': status,
                'marketplace': 'amazon',
                'user': self.logger.user,
                'order_quantity': 0,
                'created_at': order.purchase_date,
            },
        )
        core_order.items.all().delete()
        return core_order

    def _store_core_item(self, order: core_models.Order, payload: Dict[str, Any]) -> None:
        price = payload.get('ItemPrice') or {}
        quantity = int(payload.get('QuantityOrdered', 0) or 0)
        if quantity <= 0:
            return
        sku = payload.get('SellerSKU', '')
        article = core_models.Article.objects.filter(sku=sku).first()
        if not article:
            return
        total_amount = parse_decimal(price.get('Amount'))
        unit_price = total_amount / quantity if quantity else total_amount
        core_models.OrderItem.objects.create(
            order=order,
            article=article,
            quantity=quantity,
            unit_price=unit_price,
        )

    def _update_core_order_quantity(self, order: core_models.Order) -> None:
        order.order_quantity = sum(item.quantity for item in order.items.all())
        order.save(update_fields=['order_quantity'])

    def _build_customer_name(self, payload: Dict[str, Any]) -> str:
        address = payload.get('ShippingAddress') or {}
        return address.get('Name') or payload.get('BuyerName') or 'Amazon Kunde'

    def _build_customer_address(self, payload: Dict[str, Any]) -> str:
        address = payload.get('ShippingAddress') or {}
        parts = [
            address.get('AddressLine1'),
            address.get('AddressLine2'),
            address.get('AddressLine3'),
            address.get('PostalCode'),
            address.get('City'),
            address.get('StateOrRegion'),
            address.get('CountryCode'),
        ]
        return '\n'.join([part for part in parts if part])

    def _map_order_status(self, status: Any) -> str:
        status_value = str(status or '').lower()
        if status_value in {'canceled', 'cancelled'}:
            return 'storniert'
        if status_value in {'shipped', 'delivered', 'closed'}:
            return 'abgeschlossen'
        if status_value in {'paid'}:
            return 'bezahlt'
        return 'offen'


    def _parse_datetime(self, value: Any):
        if not value:
            return timezone.now()
        try:
            dt_value = timezone.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if timezone.is_naive(dt_value):
                return timezone.make_aware(dt_value, timezone=timezone.utc)
            return dt_value
        except Exception:
            return timezone.now()
