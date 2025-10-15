from django.test import TestCase

from lagerbestand_site.core import models, utils


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

    def test_get_default_minimum_stock(self):
        self.assertEqual(utils.get_default_minimum_stock(self.category), 100)
        self.assertEqual(utils.get_default_minimum_stock(self.other), 20)
