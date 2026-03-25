import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / 'lagerbestand_site'
for path in (str(PROJECT_ROOT), str(APP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lagerbestand_site.settings')
os.environ.setdefault('DB_ENGINE', 'django.db.backends.sqlite3')
os.environ.setdefault('DB_NAME', str(PROJECT_ROOT / 'test.sqlite3'))

import django
django.setup()

from django.core.management import call_command
call_command('migrate', run_syncdb=True, verbosity=0)



from unittest.mock import patch

from django.test import TestCase

from lagerbestand_site.core import models, utils
from lagerbestand_site.core.easybill import EasybillOrderImporter


class UtilsTestCase(TestCase):
    def setUp(self):
        self.category = models.Category.objects.create(name='Sticker', prefix='ST-', default_price=5.0, default_min_stock=100)
        self.other = models.Category.objects.create(name='Schal', prefix='SC-', default_price=15.0, default_min_stock=20)
        self.article = models.Article.objects.create(
            name='Sticker 1',
            sku='ST-001',
            category=self.category,
            stock=10,
            minimum_stock=5,
            price=5.0,
        )

    def test_category_from_sku(self):
        self.assertEqual(utils.category_from_sku('ST-999'), self.category)
        self.assertIsNone(utils.category_from_sku('XX-001'))

    def test_price_from_suffix(self):
        ending = models.EndingCategory.objects.create(category=self.category, suffix='XL', price=20.0, csv_multiplier=2)
        self.assertEqual(utils.price_from_suffix('ST-001XL', self.category), 10.0)
        models.EndingComponent.objects.create(ending=ending, component_sku='BASE', component_quantity=2)
        self.assertEqual(utils.csv_multiplier_from_suffix('ST-001XL', self.category), 1)

    def test_import_articles(self):
        data = [
            {
                'name': 'Sticker 2',
                'sku': 'ST-002',
                'stock': '5',
                'category': 'Sticker',
                'location_primary': 'A1',
                'location_secondary': 'B1',
                'minimum_stock': '3',
                'price': '7.50',
            }
        ]
        utils.import_articles(data)
        article = models.Article.objects.get(sku='ST-002')
        self.assertEqual(article.location_primary, 'A1')
        self.assertEqual(float(article.price), 7.5)
    def test_import_articles_assigns_category_by_prefix(self):
        data = [
            {
                'name': 'Schal 1',
                'sku': 'SC-100',
                'stock': '8',
            }
        ]
        utils.import_articles(data)
        article = models.Article.objects.get(sku='SC-100')
        self.assertEqual(article.category, self.other)
        self.assertEqual(article.minimum_stock, self.other.default_min_stock)
        self.assertEqual(float(article.price), float(self.other.default_price))

    def test_apply_category_defaults(self):
        article = models.Article.objects.create(
            name='Falscher Schal',
            sku='SC-999',
            category=self.category,
            stock=0,
            minimum_stock=1,
            price=0,
        )
        updated = utils.apply_category_defaults(self.other)
        self.assertEqual(updated, 1)
        article.refresh_from_db()
        self.assertEqual(article.category, self.other)
        self.assertEqual(article.minimum_stock, self.other.default_min_stock)
        self.assertEqual(float(article.price), float(self.other.default_price))



    def test_get_default_minimum_stock(self):
        self.assertEqual(utils.get_default_minimum_stock(self.category), 100)
        self.assertEqual(utils.get_default_minimum_stock(self.other), 20)


class EasybillImporterTestCase(TestCase):
    def setUp(self):
        self.category = models.Category.objects.create(name='Sticker', prefix='ST-', default_price=5.0, default_min_stock=100)
        self.article = models.Article.objects.create(
            name='Sticker 1',
            sku='ST-001',
            category=self.category,
            stock=10,
            minimum_stock=1,
            price=5.0,
        )

    @patch('lagerbestand_site.core.easybill.EasybillClient.list_latest_orders')
    @patch('lagerbestand_site.core.easybill.EasybillClient._required_env', return_value='dummy')
    def test_import_latest_orders_updates_stock_without_duplicate_deductions(self, _required_env, mocked_list_orders):
        mocked_list_orders.side_effect = [
            [
                {
                    'id': 123,
                    'number': 'EB-1001',
                    'status': 'paid',
                    'order_date': '2025-01-09T08:00:00Z',
                    'created_at': '2025-01-10T10:00:00Z',
                    'total_gross': '19.96',
                    'customer': {'first_name': 'Max', 'last_name': 'Mustermann'},
                    'items': [{'sku': 'ST-001', 'quantity': 2, 'price': '4.99'}],
                }
            ],
            [
                {
                    'id': 123,
                    'number': 'EB-1001',
                    'status': 'paid',
                    'order_date': '2025-01-09T08:00:00Z',
                    'created_at': '2025-01-10T10:00:00Z',
                    'total_gross': '14.97',
                    'customer': {'first_name': 'Max', 'last_name': 'Mustermann'},
                    'items': [{'sku': 'ST-001', 'quantity': 3, 'price': '4.99'}],
                }
            ],
        ]

        importer = EasybillOrderImporter()
        importer.import_latest_orders()
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock, 8)

        importer.import_latest_orders()
        self.article.refresh_from_db()
        self.assertEqual(self.article.stock, 7)

        order = models.Order.objects.get(order_number='EB-1001', marketplace='easybill')
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.order_quantity, 3)
        self.assertEqual(models.Movement.objects.filter(order=order).count(), 1)
        self.assertEqual(str(order.imported_total_price), '14.97')
        self.assertEqual(order.created_at.date().isoformat(), '2025-01-09')
