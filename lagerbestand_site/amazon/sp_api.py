from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List

import requests

import time
import random


class AmazonSpApiError(Exception):
    pass


@dataclass
class AmazonCredentials:
    client_id: str
    client_secret: str
    refresh_token: str


class SellingPartnerClient:
    def __init__(self, credentials: AmazonCredentials, endpoint: str | None = None):
        self.credentials = credentials
        self.endpoint = endpoint or 'https://sellingpartnerapi-eu.amazon.com'
        self._access_token: str | None = None
        self._token_expires_at: dt.datetime | None = None

    def list_orders(
        self,
        marketplace_id: str,
        created_after: dt.datetime,
        created_before: dt.datetime | None = None,
    ) -> Iterable[Dict[str, Any]]:
        # Amazon will UTC with Z (z.B. 2025-12-08T17:31:14Z)
        if created_after.tzinfo is None:
            created_after = created_after.replace(tzinfo=dt.timezone.utc)
        created_after_utc = created_after.astimezone(dt.timezone.utc).replace(microsecond=0)
        created_after_str = created_after_utc.isoformat().replace("+00:00", "Z")

        params = {
            "MarketplaceIds": marketplace_id,
            "CreatedAfter": created_after_str,
        }
        if created_before:
            if created_before.tzinfo is None:
                created_before = created_before.replace(tzinfo=dt.timezone.utc)
            created_before_utc = created_before.astimezone(dt.timezone.utc).replace(microsecond=0)
            params["CreatedBefore"] = created_before_utc.isoformat().replace("+00:00", "Z")
        return self._paginate("/orders/v0/orders", params, "Orders")

    def list_order_items(self, amazon_order_id: str) -> List[Dict[str, Any]]:
        path = f'/orders/v0/orders/{amazon_order_id}/orderItems'
        response = self._request('GET', path)
        payload = response.json()
        return payload.get('payload', {}).get('OrderItems', [])

    def _paginate(self, path: str, params: Dict[str, Any], result_key: str) -> Iterable[Dict[str, Any]]:
        next_token: str | None = None

        while True:
            if next_token:
                # NextToken-Call: MarketplaceIds muss mit, Filter wie CreatedAfter nicht mehr mitsenden
                query_params = {
                    "MarketplaceIds": params.get("MarketplaceIds"),
                    "NextToken": next_token,
                }
            else:
                query_params = params.copy()

            response = self._request("GET", path, params=query_params)
            data = response.json()
            payload = data.get("payload") or {}

            for entry in payload.get(result_key, []):
                yield entry

            next_token = payload.get("NextToken")
            if not next_token:
                break





    def _request(self, method: str, path: str, params=None, body=None):
        params = params or {}
        self._ensure_access_token()
        url = f"{self.endpoint}{path}"
        headers = {
            "x-amz-access-token": self._access_token or "",
            "accept": "application/json",
            "content-type": "application/json",
        }

        json_payload = None
        if method.upper() not in {"GET", "DELETE"} and body is not None:
            json_payload = body

        # Retry-Policy (429 / 503)
        max_attempts = 6
        base_sleep = 1.0

        for attempt in range(1, max_attempts + 1):
            resp = requests.request(
                method, url, headers=headers, params=params, json=json_payload, timeout=30
            )

            if resp.status_code in (429, 503):
                # Exponential backoff + jitter
                sleep_s = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 0.25)
                # optional: falls Header existiert
                retry_after = resp.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    sleep_s = max(sleep_s, float(retry_after))
                time.sleep(sleep_s)
                continue

            if not resp.ok:
                raise AmazonSpApiError(f"SP-API {resp.status_code}: {resp.text[:1000]}")
            return resp

        raise AmazonSpApiError(f"SP-API 429/503: Retry limit exceeded for {path}")




    def _ensure_access_token(self) -> None:
        if self._access_token and self._token_expires_at and self._token_expires_at > dt.datetime.utcnow():
            return
        token_url = 'https://api.amazon.com/auth/o2/token'
        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': self.credentials.refresh_token,
            'client_id': self.credentials.client_id,
            'client_secret': self.credentials.client_secret,
        }
        response = requests.post(token_url, data=payload, timeout=30)
        if not response.ok:
            raise AmazonSpApiError('Konnte kein Access Token abrufen.')
        data = response.json()
        self._access_token = data.get('access_token')
        expires_in = int(data.get('expires_in', 0))
        self._token_expires_at = dt.datetime.utcnow() + dt.timedelta(seconds=expires_in - 60)


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')
