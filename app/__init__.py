import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

# Datenbank und LoginManager global definieren
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'change-me'  # für Sessions/Login
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventory.db'

    # Benutzerverwaltung aktivieren: über Umgebungsvariable oder dauerhaft
    app.config['ENABLE_USER_MANAGEMENT'] = True
    # Falls du das immer aktiv haben willst, ersetze die Zeile durch:
    # app.config['ENABLE_USER_MANAGEMENT'] = True

    # Initialisiere Erweiterungen
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    # Kontextvariable für Template (z. B. enable_user_management im Menü)
    @app.context_processor
    def inject_config():
        return dict(enable_user_management=app.config.get['ENABLE_USER_MANAGEMENT'])

    # Registriere Blueprint & lade Modelle
    with app.app_context():
        from . import routes, models
        app.register_blueprint(routes.bp)
        db.create_all()

        # Admin-Nutzer automatisch anlegen, falls keine Benutzer existieren
        if app.config['ENABLE_USER_MANAGEMENT'] and models.User.query.count() == 0:
            admin = models.User(username='admin', is_admin=True)
            admin.set_password('admin')  # Passwort: admin
            db.session.add(admin)
            db.session.commit()

    return app
