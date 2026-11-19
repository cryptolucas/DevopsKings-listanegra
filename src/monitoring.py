"""Integracion opcional con el agente de New Relic.

El agente se activa desde fuera del codigo: el contenedor arranca gunicorn con
``newrelic-admin run-program`` y la configuracion llega por variables de
entorno (``NEW_RELIC_LICENSE_KEY``, ``NEW_RELIC_APP_NAME``...). Este modulo solo
agrega lo que el agente no hace solo, y no falla si el paquete no esta
instalado (por ejemplo en Windows, donde el agente no existe).
"""

from __future__ import annotations

try:
    import newrelic.agent as _agent
except ImportError:  # pragma: no cover - depende de la plataforma
    _agent = None


def notice_error(error: BaseException) -> None:
    """Reporta a New Relic un error que la app atrapo y convirtio en un 500."""
    if _agent is not None:
        _agent.notice_error(error=(type(error), error, error.__traceback__))


def ignore_transaction() -> None:
    """Excluye la solicitud actual de las metricas (health checks del balanceador)."""
    if _agent is not None:
        _agent.ignore_transaction(flag=True)
