from unittest import mock

from django.test import TestCase

from .easybill import EasybillClient


class EasybillClientTestCase(TestCase):
    @mock.patch.dict('os.environ', {'EASYBILL_API_KEY': 'test-key'}, clear=True)
    def test_request_sends_token_and_bearer_headers(self):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = []

        with mock.patch('core.easybill.requests.request', return_value=response) as mocked_request:
            client = EasybillClient()
            client.list_latest_orders(limit=1)

        headers = mocked_request.call_args[1]['headers']
        self.assertEqual(headers['X-TOKEN'], 'test-key')
        self.assertEqual(headers['Authorization'], 'Bearer test-key')

    @mock.patch.dict(
        'os.environ',
        {
            'EASYBILL_API_KEY': 'test-key',
            'EASYBILL_API_URL': 'https://api.easybill.de/rest/v1',
            'EASYBILL_ORDERS_ENDPOINT': 'https://api.easybill.de/rest/v1/orders',
        },
        clear=True,
    )
    def test_list_latest_orders_supports_absolute_orders_endpoint(self):
        response = mock.Mock()
        response.status_code = 200
        response.json.return_value = []

        with mock.patch('core.easybill.requests.request', return_value=response) as mocked_request:
            client = EasybillClient()
            client.list_latest_orders(limit=1)

        self.assertEqual(
            mocked_request.call_args[0][1],
            'https://api.easybill.de/rest/v1/orders',
        )
