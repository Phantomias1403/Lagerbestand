import pytest
from flask import Flask

from app import db, login_manager
from app.models import Category, Article, EndingCategory
from app.routes import bp, apply_category_defaults, apply_ending_price


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(bp)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


def test_apply_category_defaults_updates_category(app):
    with app.app_context():
        cat = Category(name='Sticker', prefix='ST-', default_price=5.0, default_min_stock=2)
        db.session.add(cat)
        art1 = Article(name='A', sku='ST-001', category='Old', price=1.0, minimum_stock=0)
        art2 = Article(name='B', sku='XX-001', category='Old', price=1.0, minimum_stock=0)
        db.session.add_all([art1, art2])
        db.session.commit()
        with app.test_request_context('/'):
            apply_category_defaults.__wrapped__.__wrapped__(cat.id)
        a1 = Article.query.filter_by(sku='ST-001').first()
        a2 = Article.query.filter_by(sku='XX-001').first()
        assert a1.category == 'Sticker'
        assert a1.price == 5.0
        assert a1.minimum_stock == 2
        assert a2.category == 'Old'


def test_apply_ending_price_updates_category(app):
    with app.app_context():
        end = EndingCategory(category='Sticker', suffix='XX', price=3.0, csv_multiplier=1)
        db.session.add(end)
        art1 = Article(name='A', sku='AA-XX', category='Old', price=1.0)
        art2 = Article(name='B', sku='BB-YY', category='Old', price=1.0)
        db.session.add_all([art1, art2])
        db.session.commit()
        with app.test_request_context('/'):
            apply_ending_price.__wrapped__.__wrapped__(end.id)
        a1 = Article.query.filter_by(sku='AA-XX').first()
        a2 = Article.query.filter_by(sku='BB-YY').first()
        assert a1.category == 'Sticker'
        assert a1.price == 3.0
        assert a2.category == 'Old'
        assert a2.price == 1.0
