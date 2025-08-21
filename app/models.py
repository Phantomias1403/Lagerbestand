from datetime import datetime
from . import db, login_manager
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_staff = db.Column(db.Boolean, default=False)
    name = db.Column(db.String(120))
    gender = db.Column(db.String(20))
    bio = db.Column(db.String(500))
    profile_image = db.Column(db.String(200))

    logs = db.relationship('ActivityLog', backref='user', lazy=True)

    def has_staff_rights(self):
        return self.is_admin or self.is_staff

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
    category = db.Column(db.String(100), default='Sticker')
    stock = db.Column(db.Integer, default=0)
    minimum_stock = db.Column(db.Integer, default=0)
    location_primary = db.Column(db.String(80))
    location_secondary = db.Column(db.String(80))
    image = db.Column(db.String(200))
    price = db.Column(db.Float, default=10.49)

    movements = db.relationship('Movement', backref='article', lazy=True, cascade='all, delete-orphan')


class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('article.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    note = db.Column(db.String(200))
    type = db.Column(db.String(20), default='Wareneingang', nullable=False)
    invoice_number = db.Column(db.String(100))
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

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)


class Category(db.Model):
    """Simple category table used for article grouping."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    prefix = db.Column(db.String(20), unique=True)
    default_price = db.Column(db.Float, default=0.0)
    default_min_stock = db.Column(db.Integer, default=0)


class EndingCategory(db.Model):
    """Suffix-based category used for price/multiplier overrides."""
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False, default='')
    suffix = db.Column(db.String(20), unique=True, nullable=False)
    price = db.Column(db.Float, default=0.0)
    csv_multiplier = db.Column(db.Integer, default=1)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.String(500), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])

    
class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
