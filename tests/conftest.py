"""Fixtures compartidas por las pruebas unitarias.

Cada prueba recibe una aplicacion nueva con configuracion ``testing``: SQLite
en memoria, de modo que el pipeline de CI no depende de un motor de base de
datos externo y las pruebas no comparten datos entre si.
"""

import pytest

from src.app import create_app
from src.extensions import db

APP_UUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


@pytest.fixture
def app():
    application = create_app("testing")
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers(app):
    return {"Authorization": f"Bearer {app.config['STATIC_TOKEN']}"}


@pytest.fixture
def add_email(client, auth_headers):
    """Agrega un email a la lista negra y devuelve la respuesta."""

    def _add(email="spammer@example.com", blocked_reason="Envio masivo de correo", **extra):
        payload = {"email": email, "app_uuid": APP_UUID, **extra}
        if blocked_reason is not None:
            payload["blocked_reason"] = blocked_reason
        return client.post("/blacklists", json=payload, headers=auth_headers)

    return _add
