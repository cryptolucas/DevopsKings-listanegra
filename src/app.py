"""Factory de la aplicacion Flask del microservicio de lista negra."""

from __future__ import annotations

import logging
import os

from flask import Flask, jsonify
from flask_restful import Api
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from src.config import get_config
from src.extensions import db, jwt, ma


def _configure_logging(app: Flask) -> None:
    """Envia los logs de la app a stdout/stderr (los recoge Elastic Beanstalk)."""
    level = logging.DEBUG if app.config.get("DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    app.logger.setLevel(level)


def _register_extensions(app: Flask) -> None:
    db.init_app(app)
    ma.init_app(app)
    jwt.init_app(app)


def _register_resources(app: Flask) -> None:
    """Registra los endpoints del API REST."""
    # Import tardio: evita import circular con src.extensions.
    from src.resources import (
        BlacklistEmailResource,
        BlacklistResource,
        HealthResource,
        RootResource,
        TokenResource,
    )

    api = Api(app, catch_all_404s=False)

    # --- Endpoints exigidos por el enunciado --------------------------------
    api.add_resource(BlacklistResource, "/blacklists", endpoint="blacklists")
    api.add_resource(
        BlacklistEmailResource,
        "/blacklists/<string:email>",
        endpoint="blacklists_email",
    )

    # --- Endpoints de soporte ------------------------------------------------
    api.add_resource(HealthResource, "/health", endpoint="health")
    api.add_resource(RootResource, "/", endpoint="root")
    api.add_resource(TokenResource, "/auth/token", endpoint="auth_token")

    app.extensions["restful_api"] = api


def _register_error_handlers(app: Flask) -> None:
    """Garantiza que todas las respuestas de error sean application/json."""

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        response = jsonify(
            {
                "message": error.description,
                "error": error.name,
                "status_code": error.code,
            }
        )
        response.status_code = error.code or 500
        return response

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception):  # pragma: no cover
        app.logger.exception("Error no controlado: %s", error)
        response = jsonify(
            {
                "message": "Error interno del servidor.",
                "error": "internal_server_error",
                "status_code": 500,
            }
        )
        response.status_code = 500
        return response


def _register_jwt_handlers(app: Flask) -> None:
    """Respuestas JSON uniformes para los errores de JWT."""

    @jwt.unauthorized_loader
    def missing_token(reason: str):
        return (
            jsonify({"message": "Token de autorizacion ausente o invalido.", "error": "unauthorized"}),
            401,
        )

    @jwt.invalid_token_loader
    def invalid_token(reason: str):
        return (
            jsonify({"message": "Token de autorizacion invalido.", "error": "invalid_token"}),
            401,
        )

    @jwt.expired_token_loader
    def expired_token(jwt_header, jwt_payload):
        return (
            jsonify({"message": "El token de autorizacion expiro.", "error": "token_expired"}),
            401,
        )


def _create_tables(app: Flask) -> None:
    """Crea el esquema si no existe (no hay migraciones en esta entrega)."""
    if not app.config.get("AUTO_CREATE_TABLES"):
        return
    # Import necesario para que SQLAlchemy conozca los modelos.
    from src import models  # noqa: F401

    try:
        with app.app_context():
            db.create_all()
            app.logger.info("Esquema de base de datos verificado/creado.")
    except Exception as error:  # noqa: BLE001
        # No tumbamos el arranque: /health reportara la base como "down" y el
        # despliegue en Elastic Beanstalk no entra en bucle de reinicios.
        app.logger.error("No fue posible crear/verificar las tablas: %s", error)


def create_app(config_name: str | None = None) -> Flask:
    """Construye y configura la aplicacion Flask."""
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    # Detras del Elastic Load Balancer de Elastic Beanstalk.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    _configure_logging(app)
    _register_extensions(app)
    _register_jwt_handlers(app)
    _register_resources(app)
    _register_error_handlers(app)
    _create_tables(app)

    app.logger.info(
        "Aplicacion inicializada (env=%s, db=%s)",
        config_name or os.environ.get("APP_ENV", "production"),
        app.config["SQLALCHEMY_DATABASE_URI"].split("@")[-1],
    )
    return app
