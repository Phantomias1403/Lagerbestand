import datetime as dt
from unittest import mock

from django.test import TestCase

from .sp_api import AmazonCredentials, SellingPartnerClient


class AmazonSpApiConnectionTestCase(TestCase):
    """Ensure the Amazon SP-API client establishes a working connection."""

    def setUp(self):
        self.credentials = AmazonCredentials(
            client_id='test-client-id',
            client_secret='test-client-secret',
            refresh_token='test-refresh-token',
            aws_access_key='test-aws-key',
            aws_secret_key='test-aws-secret',
            role_arn='arn:aws:iam::123456789012:role/TestRole',
        )

    def test_amazon_connection_refreshes_token_and_requests_orders(self):
        token_response = mock.Mock()
        token_response.ok = True
        token_response.json.return_value = {'access_token': 'token-abc', 'expires_in': 3600}

        order_response = mock.Mock()
        order_response.ok = True
        order_payload = [{'AmazonOrderId': 'ABC123'}]
        order_response.json.return_value = {'payload': {'Orders': order_payload}}

        with mock.patch('lagerbestand_site.amazon.sp_api.requests.post', return_value=token_response) as mocked_post, \
             mock.patch('lagerbestand_site.amazon.sp_api.requests.request', return_value=order_response) as mocked_request:
            client = SellingPartnerClient(self.credentials)
            since = dt.datetime.utcnow() - dt.timedelta(hours=1)
            orders = list(client.list_orders('TEST_MARKETPLACE', since))

        self.assertEqual(orders, order_payload)
        mocked_post.assert_called_once()
        headers = mocked_request.call_args[1]['headers']
        self.assertEqual(headers['x-amz-access-token'], 'token-abc')
