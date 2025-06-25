from datetime import datetime
from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    sku = db.Column(db.String(64), unique=True, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    stock = db.Column(db.Integer, default=0)
    minimum_stock = db.Column(db.Integer, default=0)
    location_primary = db.Column(db.String(80))
    location_secondary = db.Column(db.String(80))
    image = db.Column(db.String(200))

    movements = db.relationship('Movement', backref='article', lazy=True, cascade='all, delete-orphan')


class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(200))
    type = db.Column(db.String(20), default='Wareneingang', nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_address = db.Column(db.String(200))
    status = db.Column(db.String(20), default='offen')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')
    movements = db.relationship('Movement', backref='order', lazy=True)

    @property
    def total_price(self):
        return sum(item.quantity * item.unit_price for item in self.items)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Float, nullable=False)

    article = db.relationship('Article')

