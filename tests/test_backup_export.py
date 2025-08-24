import io
import csv
import zipfile
import pytest
from flask import Flask

from app import db, login_manager
from app.models import User, Order
from app.routes import bp

@pytest.fixture
def app(monkeypatch):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    app.config['ENABLE_USER_MANAGEMENT'] = False

    db.init_app(app)
    login_manager.init_app(app)
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
        user = User(username='alice')
        user.set_password('pw')
        db.session.add(user)
        db.session.commit()
        order = Order(customer_name='Bob', user_id=user.id)
        db.session.add(order)
        db.session.commit()

    # Disable login requirement
    monkeypatch.setattr('app.routes.user_management_enabled', lambda: False)

    yield app

    with app.app_context():
        db.drop_all()


def test_export_includes_user_id(app):
    client = app.test_client()
    resp = client.post('/settings/backup/export', data={'orders': '1'})
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    data = zf.read('orders.csv').decode('utf-8')
    reader = csv.DictReader(io.StringIO(data))
    row = next(reader)
    assert row['user_id'] == '1'
