import csv
import io
import zipfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from . import models
from .forms import BackupImportForm


@override_settings(ENABLE_USER_MANAGEMENT=False)
class BackupImportViewTestCase(TestCase):
    def setUp(self):
        self.category = models.Category.objects.create(name="Sticker", prefix="ST")

    def _build_backup_zip(self) -> bytes:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            articles_output = io.StringIO()
            writer = csv.writer(articles_output)
            writer.writerow(
                [
                    "name",
                    "sku",
                    "category",
                    "stock",
                    "minimum_stock",
                    "location_primary",
                    "location_secondary",
                    "price",
                ]
            )
            writer.writerow(["Fan Sticker", "ST-001", "Sticker", "20", "2", "", "", "3.50"])
            archive.writestr("articles.csv", articles_output.getvalue())

            orders_output = io.StringIO()
            writer = csv.writer(orders_output)
            writer.writerow(
                [
                    "id",
                    "customer_name",
                    "customer_address",
                    "status",
                    "marketplace",
                    "created_at",
                    "user_id",
                ]
            )
            writer.writerow([100, "Max Mustermann", "Musterstraße 1", "bezahlt", "easybill", "", ""])
            archive.writestr("orders.csv", orders_output.getvalue())

            items_output = io.StringIO()
            writer = csv.writer(items_output)
            writer.writerow(["order_id", "article_sku", "quantity", "unit_price"])
            writer.writerow([100, "ST-001", 3, "3.50"])
            archive.writestr("order_items.csv", items_output.getvalue())

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def test_backup_settings_page_renders_with_include_settings_toggle(self):
        response = self.client.get(reverse("settings_backup"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("include_settings", BackupImportForm().fields)
        self.assertContains(response, "Backup importieren")

    def test_backup_import_restores_articles_and_orders(self):
        payload = self._build_backup_zip()
        upload = SimpleUploadedFile("backup.zip", payload, content_type="application/zip")

        response = self.client.post(
            reverse("settings_backup"),
            {
                "file": upload,
                "include_articles": "on",
                "include_orders": "on",
                "include_settings": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(models.Article.objects.filter(sku="ST-001").count(), 1)
        self.assertEqual(models.Order.objects.filter(pk=100).count(), 1)
        item = models.OrderItem.objects.get(order_id=100)
        self.assertEqual(item.quantity, 3)
        self.assertEqual(item.unit_price, Decimal("3.50"))


    def test_backup_import_updates_existing_article_case_insensitive_sku(self):
        models.Article.objects.create(
            name="Existing Sticker",
            sku="st-001",
            category=self.category,
            stock=1,
            minimum_stock=1,
            price=Decimal("1.00"),
        )

        payload = self._build_backup_zip()
        upload = SimpleUploadedFile("backup.zip", payload, content_type="application/zip")

        response = self.client.post(
            reverse("settings_backup"),
            {
                "file": upload,
                "include_articles": "on",
                "include_orders": "on",
                "include_settings": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(models.Article.objects.filter(sku__iexact="ST-001").count(), 1)
        article = models.Article.objects.get(sku="ST-001")
        self.assertEqual(article.stock, 20)

        item = models.OrderItem.objects.get(order_id=100)
        self.assertEqual(item.article_id, article.id)

    def test_backup_import_reuses_existing_blank_prefix_category(self):
        models.Category.objects.create(name="Sonstiges", prefix="")
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            articles_output = io.StringIO()
            writer = csv.writer(articles_output)
            writer.writerow(
                [
                    "name",
                    "sku",
                    "category",
                    "stock",
                    "minimum_stock",
                    "location_primary",
                    "location_secondary",
                    "price",
                ]
            )
            writer.writerow(["Patch", "ZZ-001", "Neue Kategorie", "5", "1", "", "", "1.00"])
            archive.writestr("articles.csv", articles_output.getvalue())
        zip_buffer.seek(0)

        upload = SimpleUploadedFile("backup.zip", zip_buffer.getvalue(), content_type="application/zip")
        response = self.client.post(
            reverse("settings_backup"),
            {
                "file": upload,
                "include_articles": "on",
                "include_orders": "",
                "include_settings": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        article = models.Article.objects.get(sku="ZZ-001")
        self.assertEqual(article.category.name, "Sonstiges")
        self.assertEqual(models.Category.objects.filter(name="Neue Kategorie").count(), 0)
