# Entrega 4 – Monitoreo continuo con New Relic

El microservicio que ya se despliega solo en AWS Fargate (Entrega 3) ahora reporta a New Relic cómo
se comporta en producción: tiempos de respuesta, tiempos de la base de datos, Apdex, errores y
alertas. Para tener datos que analizar se le aplica carga con pruebas de estrés (Locust).

```
Locust (usuarios simulados) ──► ALB ──► tareas Fargate (gunicorn + agente New Relic) ──► RDS
                                                 │
                                                 └── métricas, trazas, errores y logs ──► New Relic APM
                                                                                          ├─ dashboards
                                                                                          └─ alertas ──► email
```

## Qué cambió en el repositorio

| Archivo | Cambio |
|---|---|
| `requirements.txt` | `newrelic==14.3.0` (solo Linux/macOS; en Windows se omite y la app funciona igual) |
| `Dockerfile` | gunicorn arranca con `newrelic-admin run-program`, que carga el agente antes que la app |
| `deploy/taskdef.json` | Variables `NEW_RELIC_*` y la licencia como secreto desde Parameter Store |
| `src/monitoring.py` | Reporta a New Relic los errores que la app atrapa y excluye `/health` de las métricas |
| `src/resources/debug.py` | `/debug/error`, `/debug/slow` y `/debug/slow-db` para provocar errores y lentitud (apagados por defecto) |
| `stress/locustfile.py` | Prueba de estrés con la mezcla de tráfico real y, opcionalmente, fallas simuladas |
| `tests/test_monitoreo.py` | 12 pruebas de lo anterior (en total 35) |

**El agente se configura solo con variables de entorno**; no hay `newrelic.ini`. Sin
`NEW_RELIC_LICENSE_KEY` la app corre normal y simplemente no envía datos.

### Los endpoints de inyección de fallas

Solo responden si `ENABLE_FAULT_INJECTION=true` (en `taskdef.json` está activado; en local hay que
pasarlo) y siempre exigen el token:

| Endpoint | Qué provoca | Para qué sección del documento |
|---|---|---|
| `GET /debug/error` | Excepción no controlada → 500 | Registro y monitoreo de errores; alerta por tasa de errores |
| `GET /debug/slow?ms=1500` | Respuesta lenta del servicio | Tiempo de respuesta; Apdex |
| `GET /debug/slow-db?ms=1500` | Consulta lenta en PostgreSQL (`pg_sleep`) | Tiempo de respuesta de la base de datos |

`ms` va de 0 a 10000.

---

## Paso 1 – Crear la cuenta (5%)

1. https://newrelic.com/signup → cuenta gratuita, región de datos **US**.
2. Invite a los demás: **Administration → User management → Add user** (en el plan gratuito solo
   1 usuario es *Full platform*; los demás quedan *Basic*, que alcanza para ver los datos).
3. Copie la llave de ingesta: menú de usuario → **API Keys** → la de tipo **INGEST - LICENSE** →
   *Copy key*. **No la suba al repositorio.**

📸 Captura de la cuenta creada y de la página de API keys (tapando la llave).

## Paso 2 – Ambiente de desarrollo (30%)

En su computador, con Docker:

```powershell
docker build -t listanegra .
docker run --rm -p 8000:8000 `
  -e NEW_RELIC_LICENSE_KEY=<su-llave> `
  -e NEW_RELIC_APP_NAME=listanegra-dev `
  -e NEW_RELIC_LOG=stdout `
  -e ENABLE_FAULT_INJECTION=true `
  listanegra
```

En otra terminal, genere tráfico durante un par de minutos:

```powershell
pip install -r stress/requirements.txt
$env:LN_FAULTS = "1"
locust -f stress/locustfile.py --host http://localhost:8000 --headless --users 20 --spawn-rate 5 --run-time 3m
```

En 1–2 minutos aparece la aplicación **listanegra-dev** en **APM & Services**.

📸 Capturas: los logs del contenedor con la línea del agente (`New Relic Python Agent ... connected`),
la app `listanegra-dev` en APM con transacciones, y la lista de transacciones
(`/blacklists`, `/blacklists/<email>`...).

> En local la base es SQLite, así que la sección de bases de datos muestra SQLite y no PostgreSQL.
> El análisis de la base se hace en la nube.

## Paso 3 – Despliegue en Fargate con el pipeline (15%)

El orden importa: **primero el secreto, después el merge**. Si la tarea pide un parámetro que no
existe, no arranca y CodeDeploy hace rollback.

1. **Systems Manager → Parameter Store → Create parameter**:
   `/listanegra/NEW_RELIC_LICENSE_KEY`, tipo **SecureString**, valor: la llave del paso 1.
   (El rol `ecsTaskExecutionRole` ya puede leer `/listanegra/*` desde la Entrega 3.)
2. Haga merge de la rama `entrega4-newrelic` a `main` (pull request en GitHub) o, desde la consola:
   ```powershell
   git switch main
   git merge entrega4-newrelic
   git push
   ```
3. El pipeline `listanegra-cd` corre solo: pruebas (35) → imagen → despliegue blue/green.
4. En New Relic aparece **listanegra-fargate**. Con 1 tarea se ve 1 instancia; con más tareas, una
   por tarea.

📸 Capturas: el pipeline en verde con este commit, el parámetro en Parameter Store (sin mostrar el
valor), `listanegra-fargate` en APM recibiendo datos.

## Paso 4 – Pruebas de estrés en la nube

Ejecútelas desde su computador o desde **AWS CloudShell** (que ya tiene Python):

```bash
git clone https://github.com/cryptolucas/DevopsKings-listanegra.git && cd DevopsKings-listanegra
pip install -r stress/requirements.txt
ALB=http://<DNS-del-ALB>
```

| Escenario | Comando | Qué muestra |
|---|---|---|
| 1. Línea base | `locust -f stress/locustfile.py --host $ALB --headless -u 30 -r 5 -t 5m --csv evidencias/stress-base` | Comportamiento normal: tiempos bajos, Apdex alto, 0 errores |
| 2. Pico de carga | `locust -f stress/locustfile.py --host $ALB --headless -u 150 -r 10 -t 5m --csv evidencias/stress-pico` | Cómo crecen los tiempos y la CPU con más usuarios |
| 3. Fallas | `LN_FAULTS=1 locust -f stress/locustfile.py --host $ALB --headless -u 50 -r 5 -t 10m --csv evidencias/stress-fallas` | Errores 500, servicio y base lentos, caída del Apdex y disparo de alertas |

Anote la hora de inicio y fin de cada escenario: en New Relic se elige ese rango de tiempo para las
capturas. Guarde los `.csv` como evidencia.

> Hallazgo ya observado en local: con 2 workers × 4 hilos, gunicorn atiende 8 solicitudes a la vez.
> Cuando los endpoints lentos ocupan esos hilos, las solicitudes normales hacen fila: su mediana
> fue 13 ms, pero el máximo llegó a 10 s. En New Relic se ve como un salto en el tiempo de
> respuesta de transacciones que no son lentas por sí mismas.

---

## Paso 5 – Qué analizar en New Relic (documento, 50%)

Todo en **APM & Services → listanegra-fargate**. Las consultas NRQL se pegan en **Query your data**
y sirven para gráficas precisas en el documento.

### 5.1 Desempeño de la aplicación (20%)

**a. Tiempo de respuesta de los servicios**
- **Summary**: *Web transactions time* (con el desglose Python / Postgres), *Throughput* (rpm) y
  *Error rate*.
- **Transactions**: ordene por *Most time consuming* y *Slowest average response time*; abra una
  transacción para ver su traza (*transaction trace*) segmento por segmento.
```sql
SELECT average(duration), percentile(duration, 95, 99) FROM Transaction
WHERE appName = 'listanegra-fargate' FACET name SINCE 30 minutes ago TIMESERIES
```

**b. Tiempo de respuesta de la base de datos**
- **Databases**: operaciones de Postgres (`select`, `insert` sobre `blacklist`), tiempo por
  operación y *throughput*. En el escenario 3 aparece `pg_sleep` como la consulta más lenta.
```sql
SELECT average(databaseDuration), percentile(databaseDuration, 95), average(databaseCallCount)
FROM Transaction WHERE appName = 'listanegra-fargate' FACET name SINCE 30 minutes ago
```
Compare: qué parte del tiempo total de cada endpoint es base de datos y qué parte es Python.

### 5.2 Apdex (10%)

Apdex resume la satisfacción en un número de 0 a 1 con un umbral **T** (por defecto 0.5 s):
- **Satisfecho**: respuesta ≤ T.
- **Tolerando**: entre T y 4T.
- **Frustrado**: > 4T o error.
- **Apdex = (satisfechos + tolerando / 2) / total.**

Dónde: **Summary** (gráfica de Apdex) y **Settings → Application → Apdex T**. Muestre cómo baja el
Apdex en el escenario 3 frente al 1, y cómo cambia si ajusta T (por ejemplo 0.3 s vs 1 s).
```sql
SELECT apdex(duration, t: 0.5) FROM Transaction WHERE appName = 'listanegra-fargate'
FACET name SINCE 30 minutes ago
```

### 5.3 Registro y monitoreo de errores (10%)

- **Errors (Errors Inbox)**: el `RuntimeError` de `/debug/error` con su *stack trace*, cuántas
  veces ocurrió, en qué transacción y con qué atributos de la solicitud.
- **Summary → Error rate** durante el escenario 3.
- **Logs**: con `NEW_RELIC_APPLICATION_LOGGING_FORWARDING_ENABLED=true` los logs de la app llegan a
  New Relic y se ven junto al error (*logs in context*).
```sql
SELECT count(*) FROM TransactionError WHERE appName = 'listanegra-fargate'
FACET error.class, transactionName SINCE 30 minutes ago
```
Los 400, 401 y 409 **no** son errores para New Relic: son respuestas correctas del API a solicitudes
inválidas. Solo los 500 cuentan. Es un buen punto para explicar en el documento.

### 5.4 Configuración de alertas (10%)

1. **Alerts → Destinations → Email**: los correos del grupo.
2. **Alerts → Alert policies → New alert policy** → `listanegra-produccion`.
3. Dentro de la política, **New alert condition** (tipo NRQL), una por fila:

| Condición | NRQL | Umbral crítico |
|---|---|---|
| Tasa de errores alta | `SELECT percentage(count(*), WHERE error IS true) FROM Transaction WHERE appName = 'listanegra-fargate'` | > 5 % durante 2 minutos |
| Servicio lento | `SELECT percentile(duration, 95) FROM Transaction WHERE appName = 'listanegra-fargate'` | > 1 s durante 2 minutos |
| Apdex bajo | `SELECT apdex(duration, t: 0.5) FROM Transaction WHERE appName = 'listanegra-fargate'` | < 0.85 durante 2 minutos |

4. **Workflows → Add workflow** → filtro por la política `listanegra-produccion` → destino: el email.
5. Corra el escenario 3: en unos minutos se abren **issues** y llega el correo. Al detener la prueba,
   las alertas se cierran solas.

📸 Capturas: la política con sus condiciones, el umbral de una condición, el issue abierto, el correo
recibido y el issue cerrado.

---

## Documento "Proyecto 1 entrega 4 – Documento.pdf"

1. Portada e integrantes.
2. Arquitectura del monitoreo (diagrama de arriba) y cómo se integró el agente (Dockerfile,
   taskdef, Parameter Store).
3. Escenarios de estrés: herramienta, mezcla de tráfico, usuarios, duración y horarios.
4. Desempeño: tiempos de servicios y de base de datos, por escenario (5.1).
5. Apdex (5.2).
6. Errores (5.3).
7. Alertas (5.4).
8. Hallazgos y conclusiones: qué ofrece New Relic, qué se descubrió y qué se mejoraría.

## Video (máximo 10 minutos)

Repositorio en GitHub (los cambios del agente), pipeline en verde desplegando a Fargate, New Relic
recibiendo datos de desarrollo y de la nube, una prueba de estrés corriendo, cada análisis (5.1 a
5.4) y una alerta disparándose. Que hablen varios integrantes.

## Limpieza

Al terminar el video: servicio de ECS a 0 tareas o borrado, balanceador y target groups borrados.
En New Relic la cuenta gratuita no cobra mientras no se pase de 100 GB de datos al mes.
