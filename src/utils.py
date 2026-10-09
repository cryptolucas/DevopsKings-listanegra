"""Utilidades compartidas."""

from __future__ import annotations

from flask import request

MAX_IP_LENGTH = 45


def get_client_ip() -> str | None:
    """Resuelve la IP real del cliente que hace la solicitud.

    En Elastic Beanstalk la aplicacion corre detras de un Elastic Load
    Balancer, por lo que ``request.remote_addr`` es la IP del balanceador. La
    IP original viaja en el primer valor de ``X-Forwarded-For``.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        candidate = forwarded_for.split(",")[0].strip()
        if candidate:
            return candidate[:MAX_IP_LENGTH]

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()[:MAX_IP_LENGTH]

    if request.remote_addr:
        return request.remote_addr[:MAX_IP_LENGTH]

    return None
