"""Autorizacion del API (Bearer Token).

El enunciado permite usar un token estatico/predefinido para toda la
aplicacion. Aun asi se deja habilitado Flask-JWT-Extended, de modo que el API
acepta dos formas de ``Authorization: Bearer <token>``:

1. El token estatico definido en ``STATIC_TOKEN`` (lo que se usa en Postman).
2. Un JWT valido firmado con ``JWT_SECRET_KEY`` (emitido por POST /auth/token).

Cualquier otro valor produce 401.
"""

from __future__ import annotations

import hmac
from functools import wraps

from flask import current_app, request
from flask_jwt_extended import verify_jwt_in_request

UNAUTHORIZED_BODY = {
    "message": "Token de autorizacion ausente o invalido.",
    "error": "unauthorized",
}


def _extract_bearer_token() -> str | None:
    """Obtiene el token del header ``Authorization: Bearer <token>``."""
    header = request.headers.get("Authorization", "")
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip()


def _is_static_token(token: str) -> bool:
    """Compara el token con el estatico usando comparacion de tiempo constante."""
    expected = current_app.config.get("STATIC_TOKEN") or ""
    if not expected:
        return False
    return hmac.compare_digest(token, expected)


def _is_valid_jwt() -> bool:
    """Valida el JWT presente en la solicitud usando Flask-JWT-Extended."""
    try:
        verify_jwt_in_request()
        return True
    except Exception:  # noqa: BLE001 - cualquier fallo de JWT es un 401
        return False


def token_required(func):
    """Protege un endpoint exigiendo un Bearer Token valido."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        token = _extract_bearer_token()
        if not token:
            return UNAUTHORIZED_BODY, 401
        if _is_static_token(token) or _is_valid_jwt():
            return func(*args, **kwargs)
        return UNAUTHORIZED_BODY, 401

    return wrapper
