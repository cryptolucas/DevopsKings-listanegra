"""Instancias unicas de las extensiones de Flask.

Se declaran aqui (sin app) para inicializarlas luego con el patron
``init_app`` dentro de la factory ``create_app``.
"""

from flask_jwt_extended import JWTManager
from flask_marshmallow import Marshmallow
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
ma = Marshmallow()
jwt = JWTManager()
