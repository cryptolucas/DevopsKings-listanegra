"""Pruebas del health check que usan los scripts de monitoreo de despliegues."""

import socket

from src.app import create_app
from src.version import APP_VERSION


def test_health_reporta_version_y_host():
    app = create_app("testing")
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["version"] == APP_VERSION
    assert body["host"] == socket.gethostname()
