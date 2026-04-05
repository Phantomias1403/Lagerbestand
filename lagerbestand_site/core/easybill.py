from __future__ import annotations

import logging
import os
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from django.db import transaction
from django.db.utils import IntegrityError
from django.utils import timezone

from . import models, utils

logger = logging.getLogger(__name__)


class EasybillApiError(Exception):
    """Raised when an Easybill API call fails."""


class EasybillClient:
    def __init__(self) -> None:
        self.base_url = (
            os.environ.get("EASYBILL_API_URL") or "https://api.easybill.de/rest/v1"
        ).rstrip("/")
        self.api_key = self._required_env("EASYBILL_API_KEY")
        self.auth_mode = (os.environ.get("EASYBILL_AUTH_MODE") or "auto").strip().lower()

    def _required_env(self, name: str) -> str:
        value = os.environ.get(name)
        if not value or not value.strip():
            raise EasybillApiError(f"Fehlende Umgebungsvariable {name}.")
        return value.strip()

    def _build_url(self, path: str) -> str:
        cleaned_path = (path or "").strip()
        if cleaned_path.startswith(("http://", "https://")):
            return cleaned_path
        return f"{self.base_url}/{cleaned_path.lstrip('/')}"

    def _auth_variants(self) -> list[dict[str, Any]]:
        bearer = {
            "headers": {
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            }
        }
        basic = {
            "headers": {"Accept": "application/json"},
            "auth": (self.api_key, ""),
        }

        if self.auth_mode == "bearer":
            return [bearer]
        if self.auth_mode == "basic":
            return [basic]
        return [bearer, basic]

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        retries: int = 4,
    ) -> Any:
        url = self._build_url(path)
        backoff_seconds = 1.0
        last_error: EasybillApiError | None = None

        for attempt in range(retries):
            auth_failed = False

            for auth_variant in self._auth_variants():
                try:
                    response = requests.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json,
                        headers=auth_variant.get("headers"),
                        auth=auth_variant.get("auth"),
                        timeout=30,
                    )
                except requests.RequestException as exc:  # pragma: no cover
                    last_error = EasybillApiError(f"API-Anfrage fehlgeschlagen: {exc}")
                    continue

                if response.status_code == 401:
                    auth_failed = True
                    last_error = EasybillApiError(
                        "HTTP 401: Authentifizierung fehlgeschlagen. Prüfe API-Key und Auth-Methode."
                    )
                    continue

                if response.status_code == 400:
                    raise EasybillApiError(
                        f"HTTP 400: Validierungsfehler: {response.text[:500]}"
                    )
                if response.status_code == 404:
                    raise EasybillApiError("HTTP 404: Ressource nicht gefunden.")
                if response.status_code == 429:
                    last_error = EasybillApiError("HTTP 429: Rate-Limit überschritten.")
                    break
                if response.status_code >= 500:
                    last_error = EasybillApiError(
                        f"HTTP {response.status_code}: Serverfehler: {response.text[:500]}"
                    )
                    break
                if response.status_code >= 400:
                    raise EasybillApiError(
                        f"HTTP {response.status_code}: {response.text[:500]}"
                    )

                if not response.text.strip():
                    return {}

                try:
                    return response.json()
                except ValueError as exc:
                    raise EasybillApiError(
                        "Ungültige API-Antwort (kein JSON)."
                    ) from exc

            if auth_failed and self.auth_mode in {"basic", "bearer"}:
                raise last_error or EasybillApiError(
                    "HTTP 401: Authentifizierung fehlgeschlagen."
                )

            if attempt == retries - 1:
                break

            time.sleep(backoff_seconds)
            backoff_seconds *= 2

        raise last_error or EasybillApiError("Easybill-Anfrage fehlgeschlagen.")

    def get_customers_test(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/customers", params={"page": 1, "limit": 1})
        return self._extract_items(payload)

    def list_documents(
        self,
        *,
        page: int = 1,
        limit: int = 50,
        updated_at_from: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "page": max(1, page),
            "limit": max(1, min(limit, 100)),
        }
        if updated_at_from:
            params["updated_at_from"] = updated_at_from

        payload = self._request("GET", "/documents", params=params)
        return self._extract_items(payload)

    def get_document(self, document_id: int | str) -> dict[str, Any]:
        cleaned_document_id = str(document_id or "").strip()
        if not cleaned_document_id:
            raise EasybillApiError("Es wurde keine Dokument-ID für den Easybill-Abruf übergeben.")

        payload = self._request("GET", f"/documents/{cleaned_document_id}")
        if not isinstance(payload, dict):
            raise EasybillApiError("Ungültige Dokument-Antwort von Easybill.")
        return payload

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]

        if isinstance(payload, dict):
            for key in ("items", "data", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]

        return []


class EasybillOrderImporter:
    def __init__(self) -> None:
        self.client = EasybillClient()

    def import_latest_orders(
        self,
        *,
        days: int = 14,
        limit_per_page: int = 50,
        max_pages: int = 10,
        updated_at_from: date | str | None = None,
    ) -> tuple[int, int]:
        order_date_cutoff: date | None = None
        if updated_at_from:
            if isinstance(updated_at_from, date):
                updated_at_from_value = updated_at_from.isoformat()
                order_date_cutoff = updated_at_from
            else:
                updated_at_from_value = str(updated_at_from).strip()
                order_date_cutoff = self._parse_date(updated_at_from_value)
        else:
            updated_at_from_value = (timezone.now() - timedelta(days=days)).date().isoformat()

        created = 0
        updated = 0
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            document_summaries = self.client.list_documents(
                page=page,
                limit=limit_per_page,
                updated_at_from=updated_at_from_value,
            )
            if not document_summaries:
                break

            for summary in document_summaries:
                document_id = self._document_id_from_payload(summary)
                if not document_id or document_id in seen_ids:
                    continue

                seen_ids.add(document_id)

                payload = self.client.get_document(document_id)
                if not self._looks_like_order(payload):
                    continue
                if order_date_cutoff and self._order_date(payload).date() < order_date_cutoff:
                    continue

                was_created = self._sync_order(payload)
                if was_created:
                    created += 1
                else:
                    updated += 1

            if len(document_summaries) < limit_per_page:
                break

        return created, updated

    def import_order(self, document_id: int | str) -> bool:
        payload = self.client.get_document(document_id)
        if not self._looks_like_order(payload):
            raise EasybillApiError("Das Dokument enthält keine importierbaren Positionen.")
        return self._sync_order(payload)

    def _looks_like_order(self, payload: dict[str, Any]) -> bool:
        positions = payload.get("positions") or payload.get("items") or []
        return isinstance(positions, list) and bool(positions)

    def _sync_order(self, payload: dict[str, Any]) -> bool:
        order_number = self._order_number_from_payload(payload)
        if not order_number:
            raise EasybillApiError("Dokument enthält keine verwertbare Nummer.")
        order_total = self._order_total(payload)

        defaults = {
            "customer_name": self._customer_name(payload),
            "customer_address": self._customer_address(payload),
            "status": self._status(payload),
            "marketplace": "easybill",
            "order_quantity": 0,
            "created_at": self._order_sort_key(payload),
            "external_order_date": self._order_date(payload),
            "external_total_price": order_total,
        }

        with transaction.atomic():
            order, created = models.Order.objects.update_or_create(
                order_number=order_number,
                marketplace="easybill",
                defaults=defaults,
            )

            order.items.all().delete()
            self._create_order_items(order, payload)

            order.order_quantity = sum(item.quantity for item in order.items.all())
            order.save(update_fields=["order_quantity"])
            utils.sync_stock_movements_for_order(order)

        return created

    def _create_order_items(self, order: models.Order, payload: dict[str, Any]) -> None:
        positions = payload.get("positions") or payload.get("items") or []
        if not isinstance(positions, list):
            return

        order_item_fields = {field.name for field in models.OrderItem._meta.get_fields()}
        article_field = None
        if "article" in order_item_fields:
            article_field = models.OrderItem._meta.get_field("article")
        article_nullable = bool(article_field and getattr(article_field, "null", False))

        for item in positions:
            if not isinstance(item, dict):
                continue

            sku = str(item.get("number") or item.get("item_number") or "").strip()

            product_name = str(
                item.get("title")
                or item.get("name")
                or item.get("description")
                or item.get("product_name")
                or item.get("text")
                or ""
            ).strip()

            quantity = self._safe_int(item.get("quantity"), default=0)
            if quantity <= 0:
                continue

            if not sku:
                logger.warning(
                    "Easybill Position ohne SKU übersprungen (order_number=%s, description=%s).",
                    order.order_number,
                    product_name,
                )
                continue

            article = models.Article.objects.filter(sku=sku).first()
            if not article:
                article = self._get_or_create_article_for_item(
                    sku=sku,
                    product_name=product_name,
                )

            unit_price = self._parse_decimal(
                item.get("price")
                or item.get("unit_price")
                or item.get("unit_price_net")
                or item.get("single_price")
                or item.get("single_price_net")
                or item.get("single_price_gross")
                or 0
            )

            create_kwargs: dict[str, Any] = {
                "order": order,
                "quantity": quantity,
                "unit_price": unit_price,
            }

            if article is not None:
                create_kwargs["article"] = article
            elif article_field and not article_nullable:
                continue

            if "product_name" in order_item_fields:
                create_kwargs["product_name"] = (
                    product_name
                    or (article.name if article else "")
                    or sku
                    or "Unbekannter Artikel"
                )

            if "sku_snapshot" in order_item_fields:
                create_kwargs["sku_snapshot"] = sku

            if "external_sku" in order_item_fields:
                create_kwargs["external_sku"] = sku

            if "line_total" in order_item_fields:
                create_kwargs["line_total"] = unit_price * quantity

            models.OrderItem.objects.create(**create_kwargs)

    def _get_or_create_article_for_item(self, *, sku: str, product_name: str) -> models.Article | None:
        derived_sku = (sku or "").strip()
        if not derived_sku:
            return None

        sticker_category = self._get_sticker_category()
        article_defaults = {
            "name": product_name or derived_sku,
            "category": sticker_category,
            "stock": 0,
            "minimum_stock": 0,
            "price": Decimal("0"),
        }
        article, _ = models.Article.objects.get_or_create(
            sku=derived_sku,
            defaults=article_defaults,
        )

        if product_name and article.name != product_name:
            article.name = product_name
            article.save(update_fields=["name"])

        return article

    def _get_sticker_category(self) -> models.Category:
        category = models.Category.objects.filter(name__iexact="Sticker").first()
        if category:
            return category

        try:
            category, _ = models.Category.objects.get_or_create(
                name="Sticker",
                defaults={"prefix": "STICKER"},
            )
            return category
        except IntegrityError:
            category = models.Category.objects.filter(name__iexact="Sticker").first()
            if category:
                return category
            raise EasybillApiError(
                "Kategorie 'Sticker' konnte für den Easybill-Import nicht erstellt werden."
            )

    def _document_id_from_payload(self, payload: dict[str, Any]) -> str:
        for key in ("id", "document_id"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _order_number_from_payload(self, payload: dict[str, Any]) -> str:
        for key in ("document_number", "number", "order_number", "reference_number", "id"):
            value = payload.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _customer_name(self, payload: dict[str, Any]) -> str:
        customer = payload.get("customer") or {}
        if isinstance(customer, dict):
            name = str(customer.get("name") or "").strip()
            if name:
                return name

            first = str(
                customer.get("first_name")
                or customer.get("firstname")
                or ""
            ).strip()
            last = str(
                customer.get("last_name")
                or customer.get("lastname")
                or ""
            ).strip()
            combined = f"{first} {last}".strip()
            if combined:
                return combined

            company = str(customer.get("company_name") or "").strip()
            if company:
                return company

            email = str(customer.get("email") or "").strip()
            if email:
                return email

        for address in (self._shipping_address(payload), self._billing_address(payload)):
            full_name = self._name_from_address(address)
            if full_name:
                return full_name

        shipping_address = self._shipping_address(payload)
        if isinstance(shipping_address, dict):
            shipping_name = str(shipping_address.get("name") or "").strip()
            if shipping_name:
                return shipping_name

        return "Easybill Kunde"

    def _shipping_address(self, payload: dict[str, Any]) -> dict[str, Any]:
        shipping = payload.get("shipping_address")
        if isinstance(shipping, dict):
            return shipping

        customer = payload.get("customer") or {}
        if isinstance(customer, dict):
            nested_shipping = customer.get("shipping_address")
            if isinstance(nested_shipping, dict):
                return nested_shipping

        return {}

    def _billing_address(self, payload: dict[str, Any]) -> dict[str, Any]:
        billing = payload.get("billing_address")
        if isinstance(billing, dict):
            return billing

        customer = payload.get("customer") or {}
        if isinstance(customer, dict):
            nested_billing = customer.get("billing_address")
            if isinstance(nested_billing, dict):
                return nested_billing

        return {}

    def _name_from_address(self, address: dict[str, Any]) -> str:
        if not isinstance(address, dict):
            return ""
        direct_name = str(address.get("name") or "").strip()
        if direct_name:
            return direct_name

        first = str(address.get("first_name") or address.get("firstname") or "").strip()
        last = str(address.get("last_name") or address.get("lastname") or "").strip()
        return f"{first} {last}".strip()

    def _order_sort_key(self, payload: dict[str, Any]) -> datetime:
        return self._parse_datetime(
            payload.get("created_at")
            or payload.get("updated_at")
            or payload.get("document_date")
            or payload.get("ordered_at")
        )

    def _order_date(self, payload: dict[str, Any]) -> datetime:
        return self._parse_datetime(
            payload.get("document_date")
            or payload.get("ordered_at")
            or payload.get("order_date")
            or payload.get("created_at")
            or payload.get("updated_at")
        )

    def _order_total(self, payload: dict[str, Any]) -> Decimal | None:
        for key in (
            "total_price_gross",
            "total_price",
            "total_gross",
            "sum_gross",
            "amount",
            "total",
            "grand_total",
        ):
            value = payload.get(key)
            if value is None or value == "":
                continue
            return self._parse_decimal(value)
        return None

    def _customer_address(self, payload: dict[str, Any]) -> str:
        address = self._shipping_address(payload)
        if not address:
            customer = payload.get("customer") or {}
            if isinstance(customer, dict):
                address = customer

        if not isinstance(address, dict):
            return ""

        parts = [
            address.get("name"),
            address.get("address_1") or address.get("address1") or address.get("street"),
            address.get("address_2") or address.get("address2"),
            address.get("address_3") or address.get("address3"),
            self._join_zip_city(
                address.get("zipcode") or address.get("zip") or address.get("zip_code"),
                address.get("city"),
            ),
            address.get("state"),
            address.get("country") or address.get("country_code"),
        ]
        return "\n".join(str(part).strip() for part in parts if str(part).strip())

    def _status(self, payload: dict[str, Any]) -> str:
        status = str(payload.get("status") or "").strip().lower()
        if status in {"cancelled", "canceled", "storniert"}:
            return "storniert"
        if status in {"paid", "bezahlt"}:
            return "bezahlt"
        if status in {"done", "completed", "shipped", "fulfilled", "abgeschlossen"}:
            return "abgeschlossen"
        return "offen"

    def _join_zip_city(self, zipcode: Any, city: Any) -> str:
        zip_str = str(zipcode or "").strip()
        city_str = str(city or "").strip()
        return f"{zip_str} {city_str}".strip()

    def _parse_decimal(self, value: Any) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    def _safe_int(self, value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _parse_datetime(self, value: Any) -> datetime:
        if not value:
            return timezone.now()

        try:
            dt_value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if timezone.is_naive(dt_value):
                return dt_value.replace(tzinfo=UTC)
            return dt_value
        except Exception:
            return timezone.now()

    def _parse_date(self, value: Any) -> date | None:
        if isinstance(value, date):
            return value
        if value is None:
            return None
        try:
            return date.fromisoformat(str(value).strip())
        except ValueError:
            return None
