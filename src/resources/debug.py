"""Endpoints de inyeccion de fallas para el monitoreo (Entrega 4).

Permiten provocar a voluntad lo que se analiza en New Relic: errores 500,
respuestas lentas del servicio y consultas lentas a la base de datos.

Estan apagados por defecto: solo responden si ``ENABLE_FAULT_INJECTION=true``
(si no, 404) y siempre exigen el Bearer Token.
"""

import time

from flask import abort, current_app, request
from flask_restful import Resource
from sqlalchemy import text

from src.extensions import db
from src.security import token_required

MAX_DELAY_MS = 10_000


def _require_enabled() -> None:
    if not current_app.config.get("ENABLE_FAULT_INJECTION"):
        abort(404)


def _delay_ms() -> int:
    try:
        value = int(request.args.get("ms", 1000))
    except ValueError:
        abort(400, description="El parametro ms debe ser un entero.")
    return max(0, min(value, MAX_DELAY_MS))


class DebugErrorResource(Resource):
    """``GET /debug/error`` - lanza una excepcion no controlada (responde 500)."""

    method_decorators = [token_required]

    def get(self):
        _require_enabled()
        raise RuntimeError("Error simulado para el monitoreo de errores en New Relic")


class DebugSlowResource(Resource):
    """``GET /debug/slow?ms=1500`` - respuesta lenta del servicio."""

    method_decorators = [token_required]

    def get(self):
        _require_enabled()
        delay = _delay_ms()
        time.sleep(delay / 1000)
        return {"simulated_delay_ms": delay}, 200


class DebugSlowDbResource(Resource):
    """``GET /debug/slow-db?ms=1500`` - consulta lenta en PostgreSQL (pg_sleep)."""

    method_decorators = [token_required]

    def get(self):
        _require_enabled()
        delay = _delay_ms()
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("SELECT pg_sleep(:s)"), {"s": delay / 1000})
        else:
            # SQLite (pruebas y desarrollo) no tiene pg_sleep.
            db.session.execute(text("SELECT 1"))
            time.sleep(delay / 1000)
        return {"simulated_db_delay_ms": delay, "database": db.engine.dialect.name}, 200
