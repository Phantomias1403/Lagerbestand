from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Iterable, List
from urllib.parse import urlencode, urlparse

import requests


class AmazonSpApiError(Exception):
    pass


@dataclass
class AmazonCredentials:
    client_id: str
    client_secret: str
    refresh_token: str
    aws_access_key: str
    aws_secret_key: str
    role_arn: str | None = None


class SellingPartnerClient:
    def __init__(self, credentials: AmazonCredentials, endpoint: str | None = None):
        self.credentials = credentials
        self.endpoint = endpoint or 'https://sellingpartnerapi-eu.amazon.com'
        self.region = 'eu-west-1'
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
        amz_date = dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        date_stamp = amz_date[:8]
        canonical_querystring = urlencode(sorted(params.items()))
        payload_hash = hashlib.sha256(json.dumps(body).encode('utf-8')).hexdigest()
        canonical_headers = f"host:{urlparse(self.endpoint).netloc}\n" f"x-amz-date:{amz_date}\n"
        signed_headers = 'host;x-amz-date'
        canonical_request = '\n'.join([
            method,
            path,
            canonical_querystring,
            canonical_headers,
            signed_headers,
            payload_hash,
        ])
        algorithm = 'AWS4-HMAC-SHA256'
        credential_scope = f"{date_stamp}/{self.region}/execute-api/aws4_request"
        string_to_sign = '\n'.join([
            algorithm,
            amz_date,
            credential_scope,
            hashlib.sha256(canonical_request.encode('utf-8')).hexdigest(),
        ])
        signing_key = self._get_signature_key(self.credentials.aws_secret_key, date_stamp, self.region, 'execute-api')
        signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        authorization_header = (
            f"{algorithm} Credential={self.credentials.aws_access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            'x-amz-date': amz_date,
            'Authorization': authorization_header,
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

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()

    def _get_signature_key(self, key: str, date_stamp: str, region_name: str, service_name: str) -> bytes:
        k_date = self._sign(('AWS4' + key).encode('utf-8'), date_stamp)
        k_region = self._sign(k_date, region_name)
        k_service = self._sign(k_region, service_name)
        k_signing = self._sign(k_service, 'aws4_request')
        return k_signing


def parse_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')
