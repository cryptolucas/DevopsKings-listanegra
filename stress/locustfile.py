"""Prueba de estres del microservicio con Locust (Entrega 4).

Simula clientes que consultan y agregan emails a la lista negra, con una
mezcla parecida al uso real (muchas mas consultas que altas). Con
``LN_FAULTS=1`` agrega una pequena porcion de trafico a /debug/* para que New
Relic muestre errores, respuestas lentas y consultas lentas a la base
(requiere ``ENABLE_FAULT_INJECTION=true`` en el servidor).

Uso (desde la raiz del repo):

    pip install -r stress/requirements.txt
    locust -f stress/locustfile.py --host http://<DNS-del-ALB> --headless \
        --users 50 --spawn-rate 5 --run-time 5m --csv evidencias/stress-base

Variables de entorno:
    LN_TOKEN   Bearer token (por defecto el token estatico del proyecto)
    LN_FAULTS  1 para incluir el trafico de /debug/*
"""

import os
import random
import uuid

from locust import HttpUser, between, events, task

TOKEN = os.environ.get("LN_TOKEN", "devopskings-2026-token-listanegra")
FAULTS = os.environ.get("LN_FAULTS", "0") == "1"
APP_UUID = "3fa85f64-5717-4562-b3fc-2c963f66afa6"

# Emails que se agregaron durante la prueba: las consultas usan estos para que
# la mayoria responda blacklisted=true y toque filas reales de la base.
added_emails: list[str] = []


class ClienteListaNegra(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.client.headers.update({"Authorization": f"Bearer {TOKEN}"})

    @task(6)
    def consultar_email_bloqueado(self):
        email = random.choice(added_emails) if added_emails else "spammer@example.com"
        self.client.get(f"/blacklists/{email}", name="GET /blacklists/[bloqueado]")

    @task(3)
    def consultar_email_limpio(self):
        self.client.get(f"/blacklists/limpio.{uuid.uuid4().hex[:10]}@example.com",
                        name="GET /blacklists/[limpio]")

    @task(2)
    def agregar_email(self):
        email = f"stress.{uuid.uuid4().hex[:12]}@example.com"
        with self.client.post(
            "/blacklists",
            json={"email": email, "app_uuid": APP_UUID, "blocked_reason": "Prueba de estres"},
            name="POST /blacklists",
            catch_response=True,
        ) as response:
            if response.status_code == 201:
                added_emails.append(email)
                response.success()
            else:
                response.failure(f"Esperaba 201 y llego {response.status_code}")

    @task(1)
    def agregar_invalido(self):
        # Error del cliente esperado (400): no es una falla de la prueba.
        with self.client.post("/blacklists", json={"email": "no-es-email", "app_uuid": APP_UUID},
                              name="POST /blacklists [invalido]", catch_response=True) as response:
            if response.status_code == 400:
                response.success()


class FallasSimuladas(HttpUser):
    """Trafico minoritario a /debug/* para errores y lentitud en New Relic."""

    weight = 1 if FAULTS else 0
    wait_time = between(2, 5)

    def on_start(self):
        self.client.headers.update({"Authorization": f"Bearer {TOKEN}"})

    @task(2)
    def respuesta_lenta(self):
        self.client.get(f"/debug/slow?ms={random.choice([600, 1500, 3000])}", name="GET /debug/slow")

    @task(2)
    def consulta_lenta_db(self):
        self.client.get(f"/debug/slow-db?ms={random.choice([500, 1500, 2500])}", name="GET /debug/slow-db")

    @task(1)
    def error_500(self):
        with self.client.get("/debug/error", name="GET /debug/error", catch_response=True) as response:
            if response.status_code == 500:
                response.success()  # El 500 es el resultado buscado.


@events.init.add_listener
def _resumen_inicio(environment, **kwargs):
    print(f"[stress] host={environment.host} fallas_simuladas={'si' if FAULTS else 'no'}")
