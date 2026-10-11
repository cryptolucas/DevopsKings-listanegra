"""Configuracion de la aplicacion.

La configuracion se resuelve 100% desde variables de entorno, de modo que el
mismo artefacto se pueda desplegar en local, en RDS/Elastic Beanstalk o en
cualquier otro ambiente sin cambiar codigo.
"""

from __future__ import annotations

import os
from datetime import timedelta
from urllib.parse import quote_plus


def _build_database_uri() -> str:
    """Construye la URI de SQLAlchemy a partir del entorno.

    Orden de precedencia:
      1. ``DATABASE_URL`` completa (la que suele inyectar RDS/Heroku/EB).
      2. Piezas sueltas ``DB_USER``, ``DB_PASSWORD``, ``DB_HOST``, ``DB_PORT``,
         ``DB_NAME`` (lo mas comodo de configurar en Elastic Beanstalk).
      3. SQLite local, para poder levantar el microservicio sin PostgreSQL.
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # SQLAlchemy 2.x ya no reconoce el esquema historico "postgres://".
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return database_url

    # Elastic Beanstalk, cuando se adjunta una base de datos al ambiente,
    # publica RDS_HOSTNAME / RDS_PORT / RDS_DB_NAME / RDS_USERNAME / RDS_PASSWORD.
    host = os.environ.get("DB_HOST") or os.environ.get("RDS_HOSTNAME")
    name = os.environ.get("DB_NAME") or os.environ.get("RDS_DB_NAME")
    user = os.environ.get("DB_USER") or os.environ.get("RDS_USERNAME")
    password = os.environ.get("DB_PASSWORD") or os.environ.get("RDS_PASSWORD")
    port = os.environ.get("DB_PORT") or os.environ.get("RDS_PORT") or "5432"

    if host and name and user:
        engine = os.environ.get("DB_ENGINE", "postgresql")
        driver = "postgresql+psycopg2" if engine.startswith("postgres") else engine
        # Escapado obligatorio: una contraseña con %, :, #, ? o / rompe el
        # parseo de la URI y SQLAlchemy enviaria credenciales distintas a las
        # configuradas (el sintoma es un "password authentication failed"
        # aunque la contraseña sea correcta).
        safe_user = quote_plus(user)
        safe_password = quote_plus(password) if password else ""
        return f"{driver}://{safe_user}:{safe_password}@{host}:{port}/{name}"

    sqlite_path = os.path.join(os.path.abspath(os.path.dirname(os.path.dirname(__file__))), "blacklist.db")
    return f"sqlite:///{sqlite_path}"


def _build_engine_options(uri: str) -> dict:
    """Opciones del engine de SQLAlchemy segun el motor en uso."""
    options: dict = {
        # Evita errores "server closed the connection unexpectedly" cuando
        # gunicorn mantiene procesos vivos mas tiempo que RDS.
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    if uri.startswith("postgresql"):
        # Sin este timeout, una conexion bloqueada (p. ej. security group sin
        # la regla 5432) deja la peticion colgada hasta el timeout de TCP: el
        # health check del ELB aborta antes y en los logs aparece un 499 sin
        # explicacion. Con el timeout, /health responde 503 rapido y el error
        # real queda registrado.
        options["connect_args"] = {
            "connect_timeout": int(os.environ.get("DB_CONNECT_TIMEOUT", "5")),
        }

    return options


class Config:
    """Configuracion base compartida por todos los ambientes."""

    # --- Flask ---------------------------------------------------------------
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    PROPAGATE_EXCEPTIONS = True
    JSON_SORT_KEYS = False
    # Flask-RESTful: no queremos que atrape y oculte nuestros handlers.
    ERROR_404_HELP = False

    # --- SQLAlchemy ----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = _build_engine_options(SQLALCHEMY_DATABASE_URI)

    # --- Seguridad -----------------------------------------------------------
    # Token estatico/predefinido aceptado como Bearer Token (lo permite el
    # enunciado de la entrega para simplificar las pruebas en Postman).
    STATIC_TOKEN = os.environ.get("STATIC_TOKEN", "devopskings-2026-token-listanegra")

    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", SECRET_KEY)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "60"))
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # --- Aplicacion ----------------------------------------------------------
    # Crea las tablas al arrancar. Practico para la Entrega 1 (no hay
    # migraciones); se puede apagar con AUTO_CREATE_TABLES=false.
    AUTO_CREATE_TABLES = os.environ.get("AUTO_CREATE_TABLES", "true").lower() == "true"


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URI", "sqlite:///:memory:")


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name: str | None = None):
    """Devuelve la clase de configuracion segun ``APP_ENV``.

    Se usa ``APP_ENV`` y no ``FLASK_ENV`` porque Flask 2.2+ marca ``FLASK_ENV``
    como obsoleto y emite una advertencia al arrancar. Se mantiene como
    respaldo por compatibilidad.
    """
    env = (name or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "production").lower()
    return _CONFIGS.get(env, ProductionConfig)
