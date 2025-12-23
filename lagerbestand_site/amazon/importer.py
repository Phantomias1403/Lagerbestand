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

    def _build_client(self) -> SellingPartnerClient:
        credentials = AmazonCredentials(
            client_id=os.environ['AMAZON_CLIENT_ID'],
            client_secret=os.environ['AMAZON_CLIENT_SECRET'],
            refresh_token=os.environ['AMAZON_REFRESH_TOKEN'],
            aws_access_key=os.environ['AWS_ACCESS_KEY_ID'],
            aws_secret_key=os.environ['AWS_SECRET_ACCESS_KEY'],
            role_arn=os.environ.get('AWS_ROLE_ARN'),
        )
        return SellingPartnerClient(credentials)

    def import_orders(self) -> int:
        created_orders = 0
        marketplaces = AmazonMarketplace.objects.filter(active=True)
        error_occurred = False
        for marketplace in marketplaces:
            try:
                created_orders += self._import_marketplace_orders(marketplace)
                marketplace.last_synced_at = timezone.now()
                marketplace.save(update_fields=['last_synced_at'])
            except AmazonSpApiError as exc:
                self.logger.log(f"Import fehlgeschlagen || {marketplace.marketplace_id}: {exc}")
                error_occurred = True
        if not error_occurred:
            self.logger.log(f"Import erfolgreich || Anzahl der Bestellungen: {created_orders}")
        return created_orders

    def _import_marketplace_orders(self, marketplace: AmazonMarketplace) -> int:
        created_orders = 0
        since = marketplace.last_synced_at or timezone.now() - timedelta(hours=48)
        for order_payload in self.client.list_orders(marketplace.marketplace_id, since):
            if AmazonOrder.objects.filter(amazon_order_id=order_payload.get('AmazonOrderId')).exists():
                continue
            created = self._store_order(order_payload, marketplace)
            created_orders += 1 if created else 0
        return created_orders

    def _store_order(self, payload: Dict[str, Any], marketplace: AmazonMarketplace) -> bool:
        amazon_order_id = payload.get('AmazonOrderId')
        if not amazon_order_id:
            return False
        total = payload.get('OrderTotal', {}) or {}
        with transaction.atomic():
            order = AmazonOrder.objects.create(
                amazon_order_id=amazon_order_id,
                marketplace=marketplace,
                ship_to_country=(payload.get('ShippingAddress') or {}).get('CountryCode', ''),
                purchase_date=self._parse_datetime(payload.get('PurchaseDate')),
                order_status=payload.get('OrderStatus', ''),
                order_total_amount=parse_decimal(total.get('Amount')),
                order_total_currency=total.get('CurrencyCode', ''),
            )
            for item_payload in self.client.list_order_items(amazon_order_id):
                self._store_item(order, item_payload)
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
