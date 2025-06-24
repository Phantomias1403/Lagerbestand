import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Database instance
# Creates and configures the Flask application

db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-me'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'
    # Benutzerverwaltung standardmäßig deaktivieren.
    # Aktivieren über Umgebungsvariable ENABLE_USER_MANAGEMENT=1
    app.config['ENABLE_USER_MANAGEMENT'] = os.environ.get('ENABLE_USER_MANAGEMENT') == '1'

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    @app.context_processor
    def inject_config():
        return dict(enable_user_management=app.config.get('ENABLE_USER_MANAGEMENT', False))


    with app.app_context():
        from . import routes, models
        app.register_blueprint(routes.bp)
        db.create_all()
        # Nur einen Admin-Benutzer anlegen, wenn die Benutzerverwaltung
        # aktiviert ist. Dadurch kann das System ohne Login betrieben werden.
        if app.config['ENABLE_USER_MANAGEMENT'] and models.User.query.count() == 0:
            admin = models.User(username='admin', is_admin=True)
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()

    return app