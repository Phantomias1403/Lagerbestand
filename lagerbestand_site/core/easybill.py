from __future__ import annotations

import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import requests
from django.utils import timezone

from . import models, utils


class EasybillApiError(Exception):
    """Raised when an Easybill API call fails."""


class EasybillClient:
    def __init__(self) -> None:
        self.base_url = (os.environ.get('EASYBILL_API_URL') or 'https://api.easybill.de/rest/v1').rstrip('/')
        self.orders_endpoint = (os.environ.get('EASYBILL_ORDERS_ENDPOINT') or '/orders').strip()
        self.api_key = self._required_env('EASYBILL_API_KEY')

    def _required_env(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise EasybillApiError(f'Fehlende Umgebungsvariable {name}.')
        return value

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                headers={
                    'X-TOKEN': self.api_key,
                    'Accept': 'application/json',
                },
                timeout=30,
            )
        except requests.RequestException as exc:  # pragma: no cover - network failure
            raise EasybillApiError(f'API-Anfrage fehlgeschlagen: {exc}') from exc
        if response.status_code >= 400:
            raise EasybillApiError(f'HTTP {response.status_code}: {response.text[:300]}')
        try:
            return response.json()
        except ValueError as exc:
            raise EasybillApiError('Ungültige API-Antwort (kein JSON).') from exc

    def list_latest_orders(self, since: datetime | None = None, limit: int = 50) -> list[dict[str, Any]]:
        params: dict[str, Any] = {'limit': max(1, min(limit, 100)), 'page': 1}
        if since:
            params['updated_at[from]'] = since.isoformat()
        orders: list[dict[str, Any]] = []
        for page in range(1, 6):
            params['page'] = page
            payload = self._request('GET', self.orders_endpoint, params=params)
            page_items = self._extract_items(payload)
            if not page_items:
                break
            orders.extend(page_items)
            if len(page_items) < params['limit']:
                break
        return orders

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            raw_items = payload.get('items')
            if isinstance(raw_items, list):
                return [item for item in raw_items if isinstance(item, dict)]
            data = payload.get('data')
            if isinstance(data, list):
                return [item for item in data if isinstance(item, dict)]
            if isinstance(data, dict):
                inner_items = data.get('items')
                if isinstance(inner_items, list):
                    return [item for item in inner_items if isinstance(item, dict)]
        return []


class EasybillOrderImporter:
    def __init__(self) -> None:
        self.client = EasybillClient()

    def import_latest_orders(self) -> tuple[int, int]:
        since = timezone.now() - timedelta(days=14)
        orders = self.client.list_latest_orders(since=since)
        created = 0
        updated = 0
        for payload in sorted(orders, key=self._order_sort_key):
            was_created = self._sync_order(payload)
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated

    def _order_sort_key(self, payload: dict[str, Any]) -> datetime:
        return self._parse_datetime(
            payload.get('created_at')
            or payload.get('updated_at')
            or payload.get('document_date')
        )

    def _sync_order(self, payload: dict[str, Any]) -> bool:
        order_number = str(
            payload.get('number')
            or payload.get('order_number')
            or payload.get('document_number')
            or payload.get('id')
            or ''
        ).strip()
        if not order_number:
            return False

        defaults = {
            'customer_name': self._customer_name(payload),
            'customer_address': self._customer_address(payload),
            'status': self._status(payload),
            'marketplace': 'easybill',
            'order_quantity': 0,
            'created_at': self._order_sort_key(payload),
        }
        order, created = models.Order.objects.update_or_create(
            order_number=order_number,
            marketplace='easybill',
            defaults=defaults,
        )
        order.items.all().delete()
        self._create_order_items(order, payload)
        order.order_quantity = sum(item.quantity for item in order.items.all())
        order.save(update_fields=['order_quantity'])
        utils.sync_stock_movements_for_order(order)
        return created

    def _create_order_items(self, order: models.Order, payload: dict[str, Any]) -> None:
        positions = payload.get('items') or payload.get('positions') or []
        if not isinstance(positions, list):
            return
        for item in positions:
            if not isinstance(item, dict):
                continue
            sku = str(item.get('sku') or item.get('number') or '').strip()
            quantity = int(item.get('quantity') or 0)
            if not sku or quantity <= 0:
                continue
            article = models.Article.objects.filter(sku=sku).first()
            if not article:
                continue
            unit_price = self._parse_decimal(item.get('single_price_net') or item.get('single_price_gross') or item.get('price') or 0)
            models.OrderItem.objects.create(
                order=order,
                article=article,
                quantity=quantity,
                unit_price=unit_price,
            )

    def _customer_name(self, payload: dict[str, Any]) -> str:
        customer = payload.get('customer') or {}
        if isinstance(customer, dict):
            first = str(customer.get('first_name') or '').strip()
            last = str(customer.get('last_name') or '').strip()
            combined = f'{first} {last}'.strip()
            if combined:
                return combined
            return str(customer.get('company_name') or '').strip() or 'Easybill Kunde'
        return 'Easybill Kunde'

    def _customer_address(self, payload: dict[str, Any]) -> str:
        customer = payload.get('customer') or {}
        if not isinstance(customer, dict):
            return ''
        parts = [
            customer.get('street'),
            customer.get('zip_code'),
            customer.get('city'),
            customer.get('country'),
        ]
        return '\n'.join(str(part).strip() for part in parts if part)

    def _status(self, payload: dict[str, Any]) -> str:
        status = str(payload.get('status') or '').lower()
        if status in {'cancelled', 'canceled', 'storniert'}:
            return 'storniert'
        if status in {'paid', 'bezahlt'}:
            return 'bezahlt'
        if status in {'done', 'shipped', 'abgeschlossen'}:
            return 'abgeschlossen'
        return 'offen'

    def _parse_decimal(self, value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal('0')

    def _parse_datetime(self, value: Any) -> datetime:
        if not value:
            return timezone.now()
        try:
            dt_value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if timezone.is_naive(dt_value):
                return timezone.make_aware(dt_value, timezone=timezone.utc)
            return dt_value
        except Exception:
            return timezone.now()
