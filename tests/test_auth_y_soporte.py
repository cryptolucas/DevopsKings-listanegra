"""Pruebas de POST /auth/token, GET / y el caso 503 de GET /health."""

from sqlalchemy.exc import OperationalError

from src.extensions import db
from src.version import APP_VERSION
from tests.conftest import APP_UUID


# --- POST /auth/token --------------------------------------------------------


def test_token_emite_jwt(client, auth_headers):
    response = client.post("/auth/token", json={"app_uuid": APP_UUID}, headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["token_type"] == "Bearer"
    assert body["access_token"].count(".") == 2
    assert body["expires_in_seconds"] > 0


def test_jwt_emitido_sirve_para_consultar(client, auth_headers):
    jwt = client.post("/auth/token", json={}, headers=auth_headers).get_json()["access_token"]

    response = client.get(
        "/blacklists/spammer@example.com", headers={"Authorization": f"Bearer {jwt}"}
    )

    assert response.status_code == 200


def test_token_sin_autorizacion_responde_401(client):
    response = client.post("/auth/token", json={"app_uuid": APP_UUID})

    assert response.status_code == 401


# --- GET / -------------------------------------------------------------------


def test_root_describe_el_servicio(client):
    response = client.get("/")

    assert response.status_code == 200
    body = response.get_json()
    assert body["service"] == "blacklist-microservice"
    assert body["version"] == APP_VERSION
    assert body["endpoints"]["add_to_blacklist"] == "POST /blacklists"


# --- GET /health cuando la base no responde ------------------------------------


def test_health_responde_503_si_la_base_no_responde(client, monkeypatch):
    def base_caida(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("conexion rechazada"))

    monkeypatch.setattr(db.session, "execute", base_caida)

    response = client.get("/health")

    assert response.status_code == 503
    assert response.get_json()["database"] == "down"
