import pytest
from flask import Flask

from app import db, login_manager
from app.models import (
    Category,
    EndingCategory,
    EndingComponent,
    Article,
    ArticleMixComponent,
)
from app.utils import (
    _get_prefix_definitions,
    category_from_sku,
    price_from_suffix,
    csv_multiplier_from_suffix,
    get_default_minimum_stock,
    generate_reset_token,
    verify_reset_token,
    get_mix_components,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True

    db.init_app(app)
    login_manager.init_app(app)

    with app.app_context():
        db.create_all()
        for prefix, (name, price, min_stock) in _get_prefix_definitions().items():
            db.session.add(
                Category(
                    name=name,
                    prefix=prefix,
                    default_price=price,
                    default_min_stock=min_stock,
                )
            )
        db.session.commit()
    yield app

    with app.app_context():
        db.drop_all()


def test_category_from_sku(app):
    with app.app_context():
        assert category_from_sku('ST-123') == 'Sticker'
        assert category_from_sku('SC-456') == 'Schal'
        assert category_from_sku('XX-000') is None


def test_price_and_multiplier_from_suffix(app):
    with app.app_context():
        assert price_from_suffix('ST-1-XX') is None
        assert csv_multiplier_from_suffix('ST-1-XX') is None

        end = EndingCategory(category='Sticker', suffix='XX', price=20.0, csv_multiplier=2)
        db.session.add(end)
        db.session.commit()

        assert price_from_suffix('ST-1-XX', 'Sticker') == 10.0
        assert csv_multiplier_from_suffix('ST-1-XX', 'Sticker') == 2

        article = Article(name='Mix', sku='ST-1-XX', category='Sticker', stock=0, price=0.0)
        db.session.add(article)
        db.session.commit()

        assert get_mix_components('ST-1-XX', 'Sticker') == []

        comp = ArticleMixComponent(article_id=article.id, component_sku='ST-BASE', component_quantity=3)
        db.session.add(comp)
        db.session.commit()

        assert csv_multiplier_from_suffix('ST-1-XX', 'Sticker') == 1
        assert price_from_suffix('ST-1-XX', 'Sticker') == 20.0
        assert get_mix_components('ST-1-XX', 'Sticker') == [('ST-BASE', 3)]

        legacy_comp = EndingComponent(ending_id=end.id, component_sku='ST-LEGACY', component_quantity=2)
        db.session.add(legacy_comp)
        other = Article(name='Alt', sku='ST-2-XX', category='Sticker', stock=0, price=0.0)
        db.session.add(other)
        db.session.commit()

        assert get_mix_components('ST-2-XX', 'Sticker') == [('ST-LEGACY', 2)]


def test_get_default_minimum_stock(app):
    with app.app_context():
        assert get_default_minimum_stock('Schal') == 20
        assert get_default_minimum_stock('Unbekannt') == 0


def test_generate_and_verify_reset_token(app):
    with app.app_context():
        token = generate_reset_token(42)
        assert verify_reset_token(token) == 42
        assert verify_reset_token('invalid') is None
