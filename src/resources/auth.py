"""Emision de JWT (Flask-JWT-Extended).

El enunciado permite un token estatico, y ese es el mecanismo principal del
API. Este endpoint es un complemento: intercambia el token estatico por un JWT
con vencimiento, para quienes quieran probar la variante con JWT.

Nota de seguridad: el endpoint esta protegido con ``token_required``, es decir
solo quien ya posee un Bearer Token valido puede emitir un JWT. No es un
endpoint publico.
"""

from datetime import datetime, timezone

from flask import current_app, request
from flask_jwt_extended import create_access_token
from flask_restful import Resource

from src.security import token_required


class TokenResource(Resource):
    """``/auth/token`` - entrega un JWT de acceso."""

    method_decorators = [token_required]

    def post(self):
        payload = request.get_json(silent=True) or {}
        app_uuid = str(payload.get("app_uuid") or "internal-client")

        access_token = create_access_token(
            identity=app_uuid,
            additional_claims={
                "scope": "blacklist:read blacklist:write",
                "issued_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        expires = current_app.config.get("JWT_ACCESS_TOKEN_EXPIRES")
        return {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in_seconds": int(expires.total_seconds()) if expires else None,
        }, 200
