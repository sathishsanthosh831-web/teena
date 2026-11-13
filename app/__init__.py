import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app(config=None):
    app = Flask(__name__)
    url = os.environ.get("DATABASE_URL", "sqlite:///placement.db")
    if url.startswith("postgres://"):  # Render/Heroku style URL
        url = url.replace("postgres://", "postgresql://", 1)
    app.config.update(
        SQLALCHEMY_DATABASE_URI=url,
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,  # 2 MB resume limit
    )
    if config:
        app.config.update(config)

    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all()
    return app
