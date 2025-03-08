from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
import json
import os

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'main.login'


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    # Load routine data
    with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'routine_data.json'), 'r') as f:
        app.config['ROUTINE_DATA'] = json.load(f)

    from app.routes import main
    app.register_blueprint(main)

    return app
