"""Endpoints de salud.

``/health`` es el path que se configura como *Health check path* del Elastic
Load Balancer en Elastic Beanstalk. No requiere autorizacion porque el
balanceador no envia el header ``Authorization``.
"""

import socket

from flask import current_app
from flask_restful import Resource
from sqlalchemy import text

from src.extensions import db
from src.version import APP_VERSION

# En EC2 el hostname es ip-172-31-x-x: identifica que instancia respondio, lo
# que permite ver durante un despliegue si atienden las iniciales o las nuevas.
HOSTNAME = socket.gethostname()


class RootResource(Resource):
    """``/`` - informacion basica del microservicio."""

    def get(self):
        return {
            "service": "blacklist-microservice",
            "version": APP_VERSION,
            "host": HOSTNAME,
            "status": "ok",
            "endpoints": {
                "add_to_blacklist": "POST /blacklists",
                "check_blacklist": "GET /blacklists/<email>",
                "health": "GET /health",
                "issue_token": "POST /auth/token",
            },
        }, 200


class HealthResource(Resource):
    """``/health`` - health check para el load balancer de Elastic Beanstalk."""

    def get(self):
        database = "up"
        status_code = 200
        try:
            db.session.execute(text("SELECT 1"))
        except Exception as error:  # noqa: BLE001 - el health check nunca debe explotar
            database = "down"
            status_code = 503
            # Se registra para poder diagnosticar desde los logs de Elastic
            # Beanstalk; la respuesta HTTP no expone el detalle del error.
            current_app.logger.error("Health check: la base de datos no responde: %s", error)
            db.session.rollback()

        return {
            "status": "ok" if status_code == 200 else "degraded",
            "database": database,
            "version": APP_VERSION,
            "host": HOSTNAME,
        }, status_code
