"""Pruebas de la inyeccion de fallas y de la integracion con New Relic."""

import pytest

import src.monitoring as monitoring

DEBUG_PATHS = ["/debug/error", "/debug/slow?ms=0", "/debug/slow-db?ms=0"]


@pytest.fixture
def fault_injection(app):
    app.config["ENABLE_FAULT_INJECTION"] = True


@pytest.mark.parametrize("path", DEBUG_PATHS)
def test_debug_apagado_por_defecto_responde_404(client, auth_headers, path):
    assert client.get(path, headers=auth_headers).status_code == 404


@pytest.mark.parametrize("path", DEBUG_PATHS)
def test_debug_exige_token(client, fault_injection, path):
    assert client.get(path).status_code == 401


def test_debug_error_responde_500_y_lo_reporta(client, auth_headers, fault_injection, monkeypatch):
    reportados = []
    monkeypatch.setattr(monitoring, "notice_error", reportados.append)
    monkeypatch.setattr("src.app.notice_error", reportados.append)

    response = client.get("/debug/error", headers=auth_headers)

    assert response.status_code == 500
    assert response.get_json()["error"] == "internal_server_error"
    assert len(reportados) == 1
    assert isinstance(reportados[0], RuntimeError)


def test_debug_slow_espera_el_tiempo_pedido(client, auth_headers, fault_injection):
    response = client.get("/debug/slow?ms=50", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json() == {"simulated_delay_ms": 50}


def test_debug_slow_limita_el_maximo(client, auth_headers, fault_injection, monkeypatch):
    monkeypatch.setattr("src.resources.debug.time.sleep", lambda s: None)

    response = client.get("/debug/slow?ms=999999", headers=auth_headers)

    assert response.get_json()["simulated_delay_ms"] == 10_000


def test_debug_slow_rechaza_ms_no_numerico(client, auth_headers, fault_injection):
    assert client.get("/debug/slow?ms=abc", headers=auth_headers).status_code == 400


def test_debug_slow_db_consulta_la_base(client, auth_headers, fault_injection):
    response = client.get("/debug/slow-db?ms=10", headers=auth_headers)

    assert response.status_code == 200
    assert response.get_json()["database"] == "sqlite"


def test_monitoring_no_falla_sin_agente(monkeypatch):
    monkeypatch.setattr(monitoring, "_agent", None)

    monitoring.notice_error(RuntimeError("x"))
    monitoring.ignore_transaction()
