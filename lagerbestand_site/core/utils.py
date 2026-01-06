from __future__ import annotations

from typing import Iterable

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import F
from django.urls import reverse
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.template.loader import render_to_string

from . import models


IMPORT_HEADER_ALIASES = {
    'artikelnummer': 'sku',
    'artnr': 'sku',
    'artikel_nr': 'sku',
    'bestand': 'stock',
    'bestandsmenge': 'stock',
    'menge': 'stock',
    'mindestbestand': 'minimum_stock',
    'mindesbestand': 'minimum_stock',
    'min_stock': 'minimum_stock',
    'kategorie': 'category',
    'bezeichnung': 'name',
    'hauptlager': 'location_primary',
    'lagerplatz': 'location_primary',
    'lager': 'location_primary',
    'nebenlager': 'location_secondary',
    'zusatzlager': 'location_secondary',
    'preis': 'price',
    'vk': 'price',
    'verkaufspreis': 'price',
}


def normalise_import_header(header: str | None) -> str:
    if not header:
        return ''
    cleaned = header.strip().lower()
    for ch in (' ', '-', '.', '\t'):
        cleaned = cleaned.replace(ch, '_')
    cleaned = cleaned.replace('__', '_').strip('_')
    return IMPORT_HEADER_ALIASES.get(cleaned, cleaned)


def normalise_import_row(row: dict[str, str]) -> dict[str, str]:
    normalised: dict[str, str] = {}
    for key, value in row.items():
        normalised_key = normalise_import_header(key)
        if not normalised_key:
            continue
        if isinstance(value, str):
            normalised[normalised_key] = value.strip()
        else:
            normalised[normalised_key] = value
    return normalised


class TokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.password}{timestamp}"


password_reset_token_generator = TokenGenerator()


def user_management_enabled() -> bool:
    return getattr(settings, 'ENABLE_USER_MANAGEMENT', False)


DEFAULT_MIN_STOCK = {
    'sticker': 1000,
    'schal': 20,
    'shirt': 10,
}


def _get_prefix_definitions() -> dict[str, tuple[models.Category, float, int]]:
    mapping: dict[str, tuple[models.Category, float, int]] = {}
    for category in models.Category.objects.all():
        prefix = (category.prefix or '').strip()
        if not prefix:
            continue
        mapping[prefix] = (
            category,
            float(category.default_price or 0),
            int(category.default_min_stock or DEFAULT_MIN_STOCK.get(category.name.lower(), 0)),
        )
    return mapping


def get_category_prefixes() -> dict[str, models.Category]:
    return {prefix: cat for prefix, (cat, _, _) in _get_prefix_definitions().items()}


def get_categories() -> list[models.Category]:
    return list(models.Category.objects.order_by('name'))


def category_from_sku(sku: str) -> models.Category | None:
    sku = sku or ''
    for prefix, category in get_category_prefixes().items():
        if sku.startswith(prefix):
            return category
    return None


def price_from_sku(sku: str) -> float | None:
    for prefix, (category, price, _) in _get_prefix_definitions().items():
        if sku.startswith(prefix):
            return price
    return None


def get_default_price(category: models.Category) -> float:
    return float(category.default_price or 0)


def get_default_minimum_stock(category: models.Category) -> int:
    return int(category.default_min_stock or DEFAULT_MIN_STOCK.get(category.name.lower(), 0))


def price_from_suffix(sku: str, category: models.Category | None = None) -> float | None:
    category = category or category_from_sku(sku)
    if not category:
        return None

    try:
        article = models.Article.objects.get(sku=sku)
    except models.Article.DoesNotExist:
        article = None

    for ending in models.EndingCategory.objects.select_related('category').prefetch_related('components').all():
        if sku.endswith(ending.suffix) and ending.category == category:
            price = float(ending.price or 0)
            multiplier = ending.csv_multiplier or 1
            has_mix_components = False
            if article and article.category == ending.category:
                has_mix_components = article.mix_components.exists()
            if not has_mix_components and ending.components.exists():
                has_mix_components = True
            if has_mix_components:
                multiplier = 1
            if multiplier and multiplier > 1:
                price /= multiplier
            return price
    return None


def csv_multiplier_from_suffix(sku: str, category: models.Category | None = None) -> int | None:
    category = category or category_from_sku(sku)
    if not category:
        return None

    try:
        article = models.Article.objects.get(sku=sku)
    except models.Article.DoesNotExist:
        article = None

    for ending in models.EndingCategory.objects.select_related('category').prefetch_related('components').all():
        if sku.endswith(ending.suffix) and ending.category == category:
            has_mix_components = False
            if article and article.category == ending.category:
                has_mix_components = article.mix_components.exists()
            if not has_mix_components and ending.components.exists():
                has_mix_components = True
            if has_mix_components:
                return 1
            return ending.csv_multiplier or 1
    return None


def get_mix_components(sku: str, category: models.Category | None = None) -> list[tuple[str, int]]:
    category = category or category_from_sku(sku)
    components: list[tuple[str, int]] = []

    if category:
        try:
            article = models.Article.objects.get(sku=sku, category=category)
        except models.Article.DoesNotExist:
            article = None
        if article:
            for comp in article.mix_components.order_by('id').all():
                sku_value = (comp.component_sku or '').strip()
                if not sku_value:
                    continue
                quantity = comp.component_quantity or 1
                components.append((sku_value, max(1, quantity)))
            if components:
                return components

    for ending in models.EndingCategory.objects.select_related('category').prefetch_related('components').all():
        if sku.endswith(ending.suffix) and (not category or ending.category == category):
            for comp in ending.components.all():
                sku_value = (comp.component_sku or '').strip()
                if not sku_value:
                    continue
                quantity = comp.component_quantity or 1
                components.append((sku_value, max(1, quantity)))
            break
    return components


def send_email(to: str, subject: str, template: str, context: dict) -> None:
    body = render_to_string(template, context)
    email = EmailMessage(subject, body, settings.DEFAULT_FROM_EMAIL, [to])
    email.content_subtype = 'html'
    email.send(fail_silently=False)


def allocate_stock_for_order(order: models.Order) -> None:
    """Synchronise article stock with items belonging to *order*."""
    relevant_status = {'offen', 'bezahlt'}
    if order.status not in relevant_status:
        return
    for item in order.items.select_related('article'):
        models.Article.objects.filter(pk=item.article_id).update(stock=F('stock') - item.quantity)
        models.Movement.objects.create(
            article=item.article,
            quantity=-item.quantity,
            movement_type='Warenausgang',
            note=f'Automatische Reservierung für Bestellung #{order.pk}',
            order=order,
        )


def apply_category_defaults(category: models.Category) -> int:
    prefix = (category.prefix or '').strip()
    if not prefix:
        return 0

    minimum_stock = get_default_minimum_stock(category)
    price_value = category.default_price if category.default_price is not None else 0

    updated = 0
    prefix_lower = prefix.lower()
    for article in models.Article.objects.all().only(
        'id', 'sku', 'category', 'minimum_stock', 'price'
    ).iterator():
        sku_value = (article.sku or '').strip()
        if not sku_value.lower().startswith(prefix_lower):
            continue
        fields_to_update: list[str] = []
        if article.category_id != category.id:
            article.category = category
            fields_to_update.append('category')
        if article.minimum_stock != minimum_stock:
            article.minimum_stock = minimum_stock
            fields_to_update.append('minimum_stock')
        if article.price != price_value:
            article.price = price_value
            fields_to_update.append('price')
        if fields_to_update:
            article.save(update_fields=fields_to_update)
            updated += 1
    return updated



def import_articles(rows: Iterable[dict[str, str]]) -> tuple[int, int]:
    categories = list(models.Category.objects.all())
    category_cache: dict[str, models.Category] = {c.name: c for c in categories}
    prefix_cache: dict[str, models.Category] = {
        c.prefix: c for c in categories if c.prefix
    }
    created = 0
    updated = 0

    for raw_row in rows:
        row = normalise_import_row(raw_row)
        sku = (row.get('sku') or '').strip()
        if not sku:
            continue
        name = (row.get('name') or '').strip()
        category_name = (row.get('category') or '').strip()

        category = None
        if category_name:
            category = category_cache.get(category_name)
            if not category:
                category, _ = models.Category.objects.get_or_create(name=category_name)
                category_cache[category_name] = category
                if category.prefix:
                    prefix_cache[category.prefix] = category

        if category is None:
            for prefix, cached_category in prefix_cache.items():
                if sku.startswith(prefix):
                    category = cached_category
                    break

        if category is None:
            default_name = 'Sticker'
            category = category_cache.get(default_name)
            if not category:
                category, _ = models.Category.objects.get_or_create(name=default_name)
                category_cache[default_name] = category
                if category.prefix:
                    prefix_cache[category.prefix] = category

        article, was_created = models.Article.objects.get_or_create(
            sku=sku,
            defaults={'name': name or sku, 'category': category},
        )
        if was_created:
            created += 1
        else:
            updated += 1

        article.name = name or article.name
        article.category = category
        try:
            article.stock = int(row.get('stock') or 0)
        except (TypeError, ValueError):
            article.stock = 0
        try:
            article.minimum_stock = int(row.get('minimum_stock') or get_default_minimum_stock(category))
        except (TypeError, ValueError):
            article.minimum_stock = get_default_minimum_stock(category)
        article.location_primary = (row.get('location_primary') or '').strip()
        article.location_secondary = (row.get('location_secondary') or '').strip()
        price_raw = (row.get('price') or '')
        if isinstance(price_raw, str):
            price_clean = price_raw.replace('€', '').replace('EUR', '').strip()
            price_clean = price_clean.replace(',', '.').replace(' ', '')
        else:
            price_clean = ''
        if price_clean:
            try:
                article.price = float(price_clean)
            except ValueError:
                pass
        else:
            price = price_from_suffix(sku, category)
            if price is None:
                price = price_from_sku(sku)
            if price is None:
                price = get_default_price(category)
            article.price = price or 0
        article.save()

    return created, updated


def generate_password_reset_link(request, user: models.User) -> str:
    token = password_reset_token_generator.make_token(user)
    uid = user.pk
    return request.build_absolute_uri(
        reverse('password_reset_confirm_custom', args=[uid, token])
    )
