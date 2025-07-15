import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-me'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'

    # Benutzerverwaltung aktivieren über Umgebungsvariable ENABLE_USER_MANAGEMENT (default = aktiviert)
    app.config['ENABLE_USER_MANAGEMENT'] = os.environ.get('ENABLE_USER_MANAGEMENT', '1') == '1'

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    # Template-Variablen bereitstellen
    @app.context_processor
    def inject_config():
        from .utils import user_management_enabled
        return dict(enable_user_management=user_management_enabled())

    with app.app_context():
        from . import routes, models
        app.register_blueprint(routes.bp)
        db.create_all()

        # Nur Admin-Nutzer anlegen, wenn Benutzerverwaltung aktiv ist
        if app.config['ENABLE_USER_MANAGEMENT'] and models.User.query.count() == 0:
            admin = models.User(username='admin', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()

       # Initial categories from prefix settings
        if models.Category.query.count() == 0:
            from .utils import get_category_prefixes
            for name in sorted(set(get_category_prefixes().values())):
                db.session.add(models.Category(name=name))
            db.session.commit()


    return app
