from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

import requests
from django.db import transaction
from django.utils import timezone

from . import models, utils


class EasybillApiError(Exception):
    """Raised when an Easybill API call fails."""


class EasybillClient:
    def __init__(self) -> None:
        self.base_url = (os.environ.get('EASYBILL_API_URL') or 'https://import.easybill.de/api/v1').rstrip('/')
        self.orders_endpoint = (os.environ.get('EASYBILL_ORDERS_ENDPOINT') or '/orders').strip()
        self.api_key = self._required_env('EASYBILL_API_KEY')
        self.user_id = self._required_env('EASYBILL_USER_ID')
        self.import_manager_user_id = os.environ.get('IMPORT_MANAGER_USER_ID') or os.environ.get('EASYBILL_IMPORT_MANAGER_USER_ID')

    def _build_url(self, path: str) -> str:
        cleaned_path = (path or '').strip()
        if cleaned_path.startswith(('http://', 'https://')):
            return cleaned_path
        return f"{self.base_url}/{cleaned_path.lstrip('/')}"

    def _required_env(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise EasybillApiError(f'Fehlende Umgebungsvariable {name}.')
        return value

    def _headers(self) -> dict[str, str]:
        headers = {
            'HTTP_X_EASYBILL_AUTH_KEY': self.api_key,
            'HTTP_X_EASYBILL_USER_ID': self.user_id,
            'Accept': 'application/json',
        }
        if self.import_manager_user_id:
            headers['HTTP_X_IMPORT_MANAGER_USER_ID'] = self.import_manager_user_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retries: int = 4,
    ) -> Any:
        url = self._build_url(path)
        backoff_seconds = 1.0
        last_error: EasybillApiError | None = None
        for attempt in range(retries):
            try:
                response = requests.request(
                    method,
                    url,
                    params=params,
                    json=json,
                    headers=self._headers(),
                    timeout=30,
                )
            except requests.RequestException as exc:  # pragma: no cover - network failure
                last_error = EasybillApiError(f'API-Anfrage fehlgeschlagen: {exc}')
            else:
                if response.status_code == 401:
                    raise EasybillApiError('HTTP 401: Authentifizierung fehlgeschlagen.')
                if response.status_code == 400:
                    raise EasybillApiError(f'HTTP 400: Validierungsfehler: {response.text[:300]}')
                if response.status_code == 429:
                    last_error = EasybillApiError('HTTP 429: Rate-Limit überschritten.')
                elif response.status_code >= 500:
                    last_error = EasybillApiError(f'HTTP {response.status_code}: Serverfehler: {response.text[:300]}')
                elif response.status_code >= 400:
                    raise EasybillApiError(f'HTTP {response.status_code}: {response.text[:300]}')
                else:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise EasybillApiError('Ungültige API-Antwort (kein JSON).') from exc
            if attempt == retries - 1:
                break
            time.sleep(backoff_seconds)
            backoff_seconds *= 2
        raise last_error or EasybillApiError('Easybill-Anfrage fehlgeschlagen.')

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

    def get_order(self, order_number: str) -> dict[str, Any]:
        cleaned_order_number = str(order_number or '').strip()
        if not cleaned_order_number:
            raise EasybillApiError('Es wurde keine Bestellnummer für den Easybill-Abruf übergeben.')
        payload = self._request('GET', f"{self.orders_endpoint.rstrip('/')}/{cleaned_order_number}")
        if not isinstance(payload, dict):
            raise EasybillApiError('Ungültige Bestell-Antwort von Easybill.')
        return payload

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
        order_summaries = self.client.list_latest_orders(since=since)
        created = 0
        updated = 0
        for order_number in self._iter_order_numbers(order_summaries):
            payload = self.client.get_order(order_number)
            was_created = self._sync_order(payload)
            if was_created:
                created += 1
            else:
                updated += 1
        return created, updated

    def import_order(self, order_number: str) -> bool:
        payload = self.client.get_order(order_number)
        return self._sync_order(payload)

    def _iter_order_numbers(self, order_summaries: Iterable[dict[str, Any]]) -> list[str]:
        order_numbers: list[str] = []
        seen: set[str] = set()
        for payload in order_summaries:
            order_number = self._order_number_from_payload(payload)
            if not order_number or order_number in seen:
                continue
            seen.add(order_number)
            order_numbers.append(order_number)
        return order_numbers

    def _order_sort_key(self, payload: dict[str, Any]) -> datetime:
        return self._parse_datetime(
            payload.get('created_at')
            or payload.get('updated_at')
            or payload.get('document_date')
            or payload.get('shipping_date')
        )

    def _sync_order(self, payload: dict[str, Any]) -> bool:
        order_number = self._order_number_from_payload(payload)
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
        with transaction.atomic():
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
            sku = str(item.get('item_number') or item.get('sku') or item.get('number') or '').strip()
            quantity = int(item.get('quantity') or 0)
            if not sku or quantity <= 0:
                continue
            article = models.Article.objects.filter(sku=sku).first()
            if not article:
                continue
            unit_price = self._parse_decimal(
                item.get('unit_price_net')
                or item.get('single_price_net')
                or item.get('single_price_gross')
                or item.get('price')
                or 0
            )
            models.OrderItem.objects.create(
                order=order,
                article=article,
                quantity=quantity,
                unit_price=unit_price,
            )

    def _order_number_from_payload(self, payload: dict[str, Any]) -> str:
        return str(
            payload.get('order_number')
            or payload.get('number')
            or payload.get('document_number')
            or payload.get('reference_number')
            or payload.get('id')
            or ''
        ).strip()

    def _customer_name(self, payload: dict[str, Any]) -> str:
        customer = payload.get('customer') or {}
        if isinstance(customer, dict):
            name = str(customer.get('name') or '').strip()
            if name:
                return name
            first = str(customer.get('first_name') or '').strip()
            last = str(customer.get('last_name') or '').strip()
            combined = f'{first} {last}'.strip()
            if combined:
                return combined
            return str(customer.get('company_name') or '').strip() or 'Easybill Kunde'
        return 'Easybill Kunde'

    def _customer_address(self, payload: dict[str, Any]) -> str:
        customer = payload.get('shipping_address') or payload.get('customer') or {}
        if not isinstance(customer, dict):
            return ''
        parts = [
            customer.get('name'),
            customer.get('address1') or customer.get('street'),
            customer.get('address2'),
            customer.get('zip') or customer.get('zip_code'),
            customer.get('city'),
            customer.get('country') or customer.get('country_code'),
        ]
        return '\n'.join(str(part).strip() for part in parts if part)

    def _status(self, payload: dict[str, Any]) -> str:
        status = str(payload.get('status') or '').lower()
        if status in {'cancelled', 'canceled', 'storniert'}:
            return 'storniert'
        if status in {'paid', 'bezahlt'}:
            return 'bezahlt'
        if status in {'done', 'shipped', 'fulfilled', 'abgeschlossen'}:
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
