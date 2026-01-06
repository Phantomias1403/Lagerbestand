from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List

import requests


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

    def list_orders(self, marketplace_id: str, created_after: dt.datetime) -> Iterable[Dict[str, Any]]:
        params = {
            'MarketplaceIds': marketplace_id,
            'CreatedAfter': created_after.replace(microsecond=0).isoformat(),
        }
        return self._paginate('/orders/v0/orders', params, 'Orders')

    def list_order_items(self, amazon_order_id: str) -> List[Dict[str, Any]]:
        path = f'/orders/v0/orders/{amazon_order_id}/orderItems'
        response = self._request('GET', path)
        payload = response.json()
        return payload.get('payload', {}).get('OrderItems', [])

    def _paginate(self, path: str, params: Dict[str, Any], result_key: str) -> Iterable[Dict[str, Any]]:
        next_token: str | None = None
        while True:
            query_params = params.copy()
            if next_token:
                query_params = {'NextToken': next_token}
            response = self._request('GET', path, params=query_params)
            data = response.json()
            payload = data.get('payload') or {}
            for entry in payload.get(result_key, []):
                yield entry
            next_token = payload.get('NextToken')
            if not next_token:
                break

    def _request(self, method: str, path: str, params: Dict[str, Any] | None = None, body: Dict[str, Any] | None = None):
        params = params or {}
        body = body or {}
        self._ensure_access_token()
        url = f"{self.endpoint}{path}"
        headers = {
            'x-amz-access-token': self._access_token or '',
            'content-type': 'application/json',
        }
        response = requests.request(method, url, headers=headers, params=params, json=body, timeout=30)
        if not response.ok:
            raise AmazonSpApiError(f"SP-API responded with status {response.status_code}")
        return response

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
