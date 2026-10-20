"""Pruebas de POST /blacklists y GET /blacklists/<email>."""

import pytest

from tests.conftest import APP_UUID


# --- POST /blacklists --------------------------------------------------------


def test_post_agrega_email_y_registra_ip_y_fecha(add_email):
    response = add_email(email="Spammer@Example.com ")

    assert response.status_code == 201
    body = response.get_json()
    assert body["created"] is True
    record = body["blacklist"]
    assert record["email"] == "spammer@example.com"
    assert record["app_uuid"] == APP_UUID
    assert record["blocked_reason"] == "Envio masivo de correo"
    assert record["ip_address"]
    assert record["created_at"]


def test_post_sin_blocked_reason_es_valido(add_email):
    response = add_email(blocked_reason=None)

    assert response.status_code == 201
    assert response.get_json()["blacklist"]["blocked_reason"] is None


def test_post_toma_la_ip_de_x_forwarded_for(client, auth_headers):
    headers = {**auth_headers, "X-Forwarded-For": "203.0.113.7, 10.0.0.1"}
    payload = {"email": "ip@example.com", "app_uuid": APP_UUID}

    response = client.post("/blacklists", json=payload, headers=headers)

    assert response.status_code == 201
    assert response.get_json()["blacklist"]["ip_address"] == "203.0.113.7"


def test_post_email_duplicado_responde_409(add_email):
    add_email()

    response = add_email(blocked_reason="Segundo intento")

    assert response.status_code == 409
    assert response.get_json()["created"] is False


@pytest.mark.parametrize(
    "payload, campo",
    [
        ({"app_uuid": APP_UUID}, "email"),
        ({"email": "esto-no-es-un-email", "app_uuid": APP_UUID}, "email"),
        ({"email": "a@example.com"}, "app_uuid"),
        ({"email": "a@example.com", "app_uuid": "no-es-un-uuid"}, "app_uuid"),
        ({"email": "a@example.com", "app_uuid": APP_UUID, "blocked_reason": "A" * 256}, "blocked_reason"),
    ],
    ids=["sin-email", "email-invalido", "sin-app-uuid", "app-uuid-invalido", "motivo-mayor-a-255"],
)
def test_post_datos_invalidos_responde_400(client, auth_headers, payload, campo):
    response = client.post("/blacklists", json=payload, headers=auth_headers)

    assert response.status_code == 400
    body = response.get_json()
    assert body["created"] is False
    assert campo in body["errors"]


def test_post_cuerpo_que_no_es_json_responde_400(client, auth_headers):
    response = client.post(
        "/blacklists", data="no es json", headers={**auth_headers, "Content-Type": "text/plain"}
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer token-que-no-sirve"}, {"Authorization": "Basic abc"}],
    ids=["sin-token", "token-invalido", "esquema-no-bearer"],
)
def test_post_sin_token_valido_responde_401(client, headers):
    payload = {"email": "a@example.com", "app_uuid": APP_UUID}

    response = client.post("/blacklists", json=payload, headers=headers)

    assert response.status_code == 401


# --- GET /blacklists/<email> -------------------------------------------------


def test_get_email_en_lista_negra(client, auth_headers, add_email):
    add_email()

    response = client.get("/blacklists/spammer@example.com", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {
        "email": "spammer@example.com",
        "blacklisted": True,
        "blocked_reason": "Envio masivo de correo",
    }


def test_get_email_que_no_esta_en_lista_negra(client, auth_headers):
    response = client.get("/blacklists/cliente.ok@example.com", headers=auth_headers)

    assert response.status_code == 200
    body = response.get_json()
    assert body["blacklisted"] is False
    assert body["blocked_reason"] is None


def test_get_no_distingue_mayusculas(client, auth_headers, add_email):
    add_email()

    response = client.get("/blacklists/SPAMMER@Example.com", headers=auth_headers)

    assert response.get_json()["blacklisted"] is True


def test_get_sin_token_responde_401(client):
    response = client.get("/blacklists/spammer@example.com")

    assert response.status_code == 401
