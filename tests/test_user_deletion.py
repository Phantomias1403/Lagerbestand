import pytest
from flask import Flask

from app import db
from app.models import User, ActivityLog, Message


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'test-key'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    db.init_app(app)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.drop_all()


def test_delete_admin_with_logs_and_messages(app):
    with app.app_context():
        user = User(username='admin', is_admin=True, is_staff=True)
        user.set_password('pw')
        db.session.add(user)
        db.session.commit()
        db.session.add(ActivityLog(user_id=user.id, action='login'))
        db.session.add(Message(sender_id=user.id, receiver_id=user.id, content='hi'))
        db.session.commit()
        db.session.delete(user)
        db.session.commit()
        assert User.query.count() == 0
        assert ActivityLog.query.count() == 0
        assert Message.query.count() == 0
