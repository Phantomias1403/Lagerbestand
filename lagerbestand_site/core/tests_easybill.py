from decimal import Decimal
from unittest import mock

from django.test import TestCase

from . import models
from .easybill import EasybillClient, EasybillOrderImporter


class EasybillClientTestCase(TestCase):
    @mock.patch.dict('os.environ', {'EASYBILL_API_KEY': 'test-key'}, clear=True)
    def test_request_uses_bearer_token_for_rest_api(self):
        response = mock.Mock()
        response.status_code = 200
        response.text = '[]'
        response.json.return_value = []

        with mock.patch('core.easybill.requests.request', return_value=response) as mocked_request:
            client = EasybillClient()
            client.get_customers_test()

        headers = mocked_request.call_args[1]['headers']
        self.assertEqual(headers['Authorization'], 'Bearer test-key')
        self.assertEqual(headers['Accept'], 'application/json')

    @mock.patch.dict(
        'os.environ',
        {
            'EASYBILL_API_KEY': 'test-key',
            'EASYBILL_API_URL': 'https://api.easybill.de/rest/v1',
        },
        clear=True,
    )
    def test_get_document_uses_rest_api_documents_route(self):
        response = mock.Mock()
        response.status_code = 200
        response.text = '{"id": 1001}'
        response.json.return_value = {'id': 1001}

        with mock.patch('core.easybill.requests.request', return_value=response) as mocked_request:
            client = EasybillClient()
            payload = client.get_document('1001')

        self.assertEqual(payload['id'], 1001)
        self.assertEqual(
            mocked_request.call_args[1]['url'],
            'https://api.easybill.de/rest/v1/documents/1001',
        )


class EasybillOrderImporterTestCase(TestCase):
    def setUp(self):
        self.category = models.Category.objects.create(name='Sticker', prefix='ST')
        self.article = models.Article.objects.create(
            name='Fan Sticker',
            sku='ST-001',
            category=self.category,
            stock=10,
            minimum_stock=0,
            price=Decimal('3.50'),
        )

    @mock.patch.dict('os.environ', {'EASYBILL_API_KEY': 'test-key'}, clear=True)
    def test_import_order_creates_items_and_adjusts_stock_by_sku(self):
        payload = {
            'order_number': 'EB-1001',
            'status': 'paid',
            'created_at': '2026-03-17T10:30:00Z',
            'document_date': '2026-03-16T08:15:00Z',
            'total_price_gross': '10.50',
            'customer': {
                'name': 'Max Mustermann',
                'email': 'max@example.com',
                'street': 'Musterstraße 1',
                'zip_code': '12345',
                'city': 'Berlin',
                'country': 'DE',
            },
            'items': [
                {
                    'item_number': 'ST-001',
                    'title': 'Fan Sticker',
                    'quantity': 3,
                    'unit_price_net': '3.50',
                }
            ],
        }

        importer = EasybillOrderImporter()
        with mock.patch.object(importer.client, 'get_document', return_value=payload):
            created = importer.import_order('EB-1001')

        self.assertTrue(created)
        order = models.Order.objects.get(order_number='EB-1001', marketplace='easybill')
        item = order.items.get()
        self.article.refresh_from_db()

        self.assertEqual(order.customer_name, 'Max Mustermann')
        self.assertEqual(order.external_total_price, Decimal('10.50'))
        self.assertEqual(order.external_order_date.isoformat(), '2026-03-16T08:15:00+00:00')
        self.assertEqual(order.order_quantity, 3)
        self.assertEqual(item.article, self.article)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(self.article.stock, 7)
        self.assertTrue(models.Movement.objects.filter(order=order, article=self.article, quantity=-3).exists())


    @mock.patch.dict('os.environ', {'EASYBILL_API_KEY': 'test-key'}, clear=True)
    def test_import_order_matches_product_by_name_when_sku_missing(self):
        payload = {
            'order_number': 'EB-1002',
            'status': 'paid',
            'created_at': '2026-03-18T10:30:00Z',
            'total_price': '3.50',
            'customer': {'name': 'Erika Musterfrau'},
            'items': [
                {
                    'title': 'Fan Sticker',
                    'quantity': 1,
                    'unit_price_net': '3.50',
                }
            ],
        }

        importer = EasybillOrderImporter()
        with mock.patch.object(importer.client, 'get_document', return_value=payload):
            created = importer.import_order('EB-1002')

        self.assertTrue(created)
        order = models.Order.objects.get(order_number='EB-1002', marketplace='easybill')
        item = order.items.get()

        self.assertEqual(item.article, self.article)
        self.assertEqual(order.external_total_price, Decimal('3.50'))

    @mock.patch.dict('os.environ', {'EASYBILL_API_KEY': 'test-key'}, clear=True)
    def test_import_latest_orders_fetches_document_details_before_syncing(self):
        importer = EasybillOrderImporter()
        with mock.patch.object(importer.client, 'list_documents', return_value=[{'id': '1001'}]), mock.patch.object(
            importer.client,
            'get_document',
            return_value={
                'order_number': 'EB-1001',
                'status': 'paid',
                'customer': {'name': 'Max Mustermann'},
                'items': [{'item_number': 'ST-001', 'quantity': 1, 'unit_price_net': '3.50'}],
            },
        ) as mocked_get_document:
            created, updated = importer.import_latest_orders()

        self.assertEqual((created, updated), (1, 0))
        mocked_get_document.assert_called_once_with('1001')
