# Microservicio de Lista Negra Global de Emails

Entrega 1 – Despliegue manual de un microservicio sobre un servicio PaaS (AWS Elastic Beanstalk).
Universidad de los Andes – Equipo **DevopsKings**.

Microservicio REST que permite a cientos de sistemas internos **agregar** emails a la lista negra
global de la compañía y **consultar** si un email está en ella.

---

## Stack tecnológico

| Componente | Versión | Uso |
|---|---|---|
| Python | 3.11 (mín. 3.8) | Lenguaje |
| Flask | 2.2.5 | Micro framework web |
| Flask-SQLAlchemy | 3.0.5 | ORM / acceso a datos |
| Flask-RESTful | 0.3.10 | Recursos REST orientados a objetos |
| Flask-Marshmallow | 0.15.0 | Serialización y validación |
| Flask-JWT-Extended | 4.5.3 | Soporte JWT / Bearer Token |
| Werkzeug | 2.2.3 | Capa WSGI |
| PostgreSQL | 15/16 (AWS RDS) | Motor de base de datos |
| Gunicorn | 21.2.0 | Servidor WSGI en producción |

> **Nota sobre la versión de Flask.** El enunciado menciona Flask 1.1.x. Esa versión depende de
> Jinja2 2.x / MarkupSafe 1.x, que ya no compilan en las plataformas Python actuales de Elastic
> Beanstalk (Amazon Linux 2023, Python 3.11+). Se usa Flask 2.2.5, que mantiene la misma API usada
> en el proyecto y es compatible con el resto del stack exigido.

---

## Endpoints

### `POST /blacklists`

Agrega un email a la lista negra global.

- **Autorización:** `Authorization: Bearer <token>` (obligatorio)
- **Content-Type:** `application/json`

| Parámetro | Tipo | Obligatorio | Reglas |
|---|---|---|---|
| `email` | String | Sí | Formato de email válido, máx. 254 caracteres |
| `app_uuid` | String | Sí | UUID válido |
| `blocked_reason` | String | No | Máx. 255 caracteres |

El microservicio registra internamente, sin que el cliente los envíe:

- `ip_address`: IP de origen de la solicitud (primer valor de `X-Forwarded-For` cuando está detrás
  del Elastic Load Balancer, o `remote_addr`).
- `created_at`: fecha/hora UTC de la solicitud.

Respuesta `201 Created`:

```json
{
  "message": "El email spammer@example.com fue agregado a la lista negra global.",
  "created": true,
  "blacklist": {
    "created_at": "2026-10-09T23:34:02.702338",
    "id": 1,
    "email": "spammer@example.com",
    "app_uuid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "blocked_reason": "Envio masivo de spam",
    "ip_address": "201.45.80.12"
  }
}
```

Otros códigos: `400` datos inválidos, `401` token ausente/inválido, `409` el email ya estaba en la
lista, `500` error de persistencia.

### `GET /blacklists/<string:email>`

Indica si un email está en la lista negra global y por qué.

- **Autorización:** `Authorization: Bearer <token>` (obligatorio)
- **Parámetros del endpoint:** ninguno (el email viaja en la ruta)

Respuesta `200 OK`:

```json
{
  "email": "spammer@example.com",
  "blacklisted": true,
  "blocked_reason": "Envio masivo de spam"
}
```

Si el email no está en la lista: `"blacklisted": false` y `"blocked_reason": null`.

### Endpoints de soporte

| Método | Ruta | Autorización | Descripción |
|---|---|---|---|
| `GET` | `/` | No | Información del servicio y listado de endpoints |
| `GET` | `/health` | No | Health check del ELB; valida la app y la conexión a la BD |
| `POST` | `/auth/token` | Sí | Intercambia el token estático por un JWT con vencimiento |

`/health` no exige token porque el balanceador de Elastic Beanstalk no envía el header
`Authorization`. Devuelve `200` si la base responde a `SELECT 1`, o `503` si no.

---

## Autorización

El enunciado permite un token estático predefinido. La API acepta como `Bearer`:

1. El valor de la variable de entorno `STATIC_TOKEN` (es el que se usa en Postman).
2. Un JWT válido firmado con `JWT_SECRET_KEY`, emitido por `POST /auth/token`.

Cualquier otro valor produce `401`. La comparación del token estático usa `hmac.compare_digest`
(tiempo constante). **Cambie `STATIC_TOKEN` y `JWT_SECRET_KEY` antes de desplegar**; los valores por
defecto son solo para desarrollo local.

---

## Estructura del proyecto

```
.
├── application.py                 # Punto de entrada WSGI que busca Elastic Beanstalk
├── Procfile                       # Comando gunicorn que ejecuta la plataforma
├── requirements.txt               # Dependencias con versiones fijas
├── .ebextensions/
│   ├── 01_app.config              # WSGIPath, variables, health check, enhanced health
│   └── 02_autoscaling.config      # ASG min 3 / max 6, tipo de instancia, triggers
├── .env.example                   # Plantilla de variables de entorno
├── docs/
│   └── DESPLIEGUE_AWS.md          # Guía paso a paso de RDS + Elastic Beanstalk
├── postman/
│   ├── *_collection.json          # Colección de 14 escenarios de prueba
│   └── *_environment.json         # Variables de entorno de Postman
└── src/
    ├── app.py                     # Factory create_app() y manejadores de error
    ├── config.py                  # Configuración desde variables de entorno
    ├── extensions.py              # Instancias de db, ma, jwt
    ├── security.py                # Decorador token_required (estático + JWT)
    ├── utils.py                   # Resolución de la IP real del cliente
    ├── models/blacklist.py        # Modelo Blacklist
    ├── schemas/blacklist.py       # Esquemas Marshmallow (validación/serialización)
    └── resources/
        ├── blacklist.py           # POST /blacklists y GET /blacklists/<email>
        ├── health.py              # GET / y GET /health
        └── auth.py                # POST /auth/token
```

---

## Modelo de datos

Tabla `blacklist`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | Integer | PK, autoincremental |
| `email` | String(254) | No nulo, índice, único |
| `app_uuid` | String(36) | No nulo, índice |
| `blocked_reason` | String(255) | Nullable |
| `ip_address` | String(45) | Registrada por el servicio (soporta IPv6) |
| `created_at` | DateTime | UTC, registrada por el servicio |

El esquema se crea automáticamente al arrancar (`db.create_all()`), controlado por
`AUTO_CREATE_TABLES`. Si la base no está disponible el arranque no falla: `/health` reporta
`database: down` para que Elastic Beanstalk no entre en un bucle de reinicios.

---

## Variables de entorno

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `APP_ENV` | No | `production` | `development` \| `production` \| `testing` |
| `DATABASE_URL` | No | – | Cadena completa; tiene prioridad sobre las piezas |
| `DB_ENGINE` | No | `postgresql` | Motor |
| `DB_HOST` | Sí (prod) | – | Endpoint de RDS |
| `DB_PORT` | No | `5432` | Puerto |
| `DB_NAME` | Sí (prod) | – | Nombre de la base |
| `DB_USER` | Sí (prod) | – | Usuario maestro |
| `DB_PASSWORD` | Sí (prod) | – | Contraseña |
| `STATIC_TOKEN` | Sí (prod) | valor de desarrollo | Bearer Token estático |
| `JWT_SECRET_KEY` | Sí (prod) | `SECRET_KEY` | Llave de firma de JWT |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | No | `60` | Vigencia del JWT |
| `AUTO_CREATE_TABLES` | No | `true` | Crear tablas al arrancar |

También se reconocen `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME` y `RDS_PASSWORD`,
las variables que Elastic Beanstalk inyecta cuando se adjunta una base de datos al ambiente.

Sin `DB_HOST`/`DATABASE_URL` la aplicación cae a SQLite local, útil para desarrollo.

---

## Ejecución local

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env     # ajuste los valores
python application.py           # http://127.0.0.1:5000
```

Prueba rápida:

```powershell
$h = @{ Authorization = "Bearer devopskings-2026-token-listanegra" }
$body = '{"email":"spammer@example.com","app_uuid":"3fa85f64-5717-4562-b3fc-2c963f66afa6","blocked_reason":"spam"}'
Invoke-RestMethod -Uri http://127.0.0.1:5000/blacklists -Method POST -Headers $h -ContentType application/json -Body $body
Invoke-RestMethod -Uri http://127.0.0.1:5000/blacklists/spammer@example.com -Headers $h
```

En producción el servidor es gunicorn (`Procfile`), no el servidor de desarrollo de Flask.

---

## Despliegue

El paso a paso completo (RDS, Elastic Beanstalk, security groups, health checks y las 4 estrategias
de despliegue) está en [`docs/DESPLIEGUE_AWS.md`](docs/DESPLIEGUE_AWS.md).

---

## Postman

1. Importe `postman/DevopsKings-ListaNegra.postman_collection.json`.
2. Importe `postman/DevopsKings-ListaNegra.postman_environment.json` y ajuste `base_url` con la URL
   del ambiente de Elastic Beanstalk y `bearer_token` con el valor de `STATIC_TOKEN`.
3. Ejecute la colección completa con el Collection Runner; los 14 escenarios incluyen tests
   automáticos.
4. Publique la documentación desde Postman (**Collection → View documentation → Publish**) y anexe
   la URL al documento de la entrega.
