# Guía de despliegue manual en AWS

Microservicio de lista negra global – Entrega 1 (PaaS: AWS Elastic Beanstalk + AWS RDS PostgreSQL).

Esta guía cubre, en orden, todo lo que hay que hacer **manualmente** en la consola de AWS. Cada
sección indica qué captura de pantalla tomar para el documento `Proyecto 1 entrega 1 – Documento.pdf`.

```
Internet → Application Load Balancer → Auto Scaling Group (3–6 × EC2 t3.micro)
                                            │  gunicorn + Flask (/var/app/current)
                                            ▼
                                       RDS PostgreSQL (puerto 5432)
```

---

## Fase 0 – Subir el código a GitHub

1. Cree el repositorio en GitHub (p. ej. `DevopsKings-listanegra`).
2. Desde la raíz del proyecto:

   ```powershell
   git add .
   git commit -m "Entrega 1: microservicio de lista negra global con Flask"
   git branch -M main
   git remote add origin https://github.com/<ORG>/<REPO>.git
   git push -u origin main
   ```

3. Verifique que **no** se subieron `.venv/`, `.env`, ni `*.db` (están en `.gitignore`).

📸 *Captura: repositorio en GitHub con los archivos y el historial de commits.*

> La entrega exige despliegue **manual**: no configure GitHub Actions ni ningún pipeline.

---

## Fase 1 – Decidir cómo se crea la base de datos

El enunciado solo pide persistir en un servicio de bases de datos relacionales y *recomienda* RDS.
No exige que la base sea independiente, así que hay dos caminos válidos:

| | **Opción A – Base acoplada al ambiente** *(recomendada para esta entrega)* | **Opción B – RDS independiente** |
|---|---|---|
| Cómo se crea | En la misma pantalla de creación del ambiente de Elastic Beanstalk | Como instancia aparte en la consola de RDS |
| Credenciales en la app | Elastic Beanstalk inyecta `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME`, `RDS_PASSWORD`. **El código ya las lee**: no hay que configurar nada | Hay que definir a mano `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` |
| Security group | Elastic Beanstalk lo configura solo | Hay que crear la regla de entrada 5432 manualmente |
| Nombre de la base | Siempre `ebdb` (no se puede elegir) | El que usted defina |
| Ciclo de vida | Atada al ambiente: al terminarlo se aplica la *deletion policy* | Independiente del ambiente |
| Varios ambientes / blue-green | No | Sí |

Las 4 estrategias de despliegue funcionan igual en ambos casos: la base está asociada al
**ambiente**, no a las instancias, así que sobrevive intacta incluso en *immutable* y
*traffic-splitting*.

**Recomendación para esta entrega: Opción A.** Es un ambiente único, de vida corta, y se ahorra toda
la configuración de red. AWS misma sugiere empezar acoplado y desacoplar solo cuando se necesita
conectar varios ambientes a la misma base o hacer blue/green
([Adding a database to your Elastic Beanstalk environment](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.managing.db.html)).

> ⚠️ Lo único que hay que cuidar en la Opción A: ponga **Database deletion policy = `Retain`**. Con
> `Delete` (el valor por defecto), terminar el ambiente borra la base y pierde los datos.

Si prefiere la Opción B, siga el **[Anexo A](#anexo-a--opción-b-rds-independiente)** y luego vuelva
a la Fase 2.

---

## Fase 2 – Empaquetar el código

El ZIP debe contener los archivos **en su raíz**, no dentro de una carpeta.

```powershell
cd "d:\SEMESTRE 10\DEVOPS\DevopsKings-listanegra"

# Opción recomendada: empaqueta exactamente lo que está versionado en git
git archive --format=zip --output ..\listanegra-v1.zip HEAD
```

Si prefiere no usar git:

```powershell
$excluir = @('.venv', '.git', '__pycache__', '.vscode', 'docs', 'postman')
$temp = Join-Path $env:TEMP 'eb-bundle'
Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $temp | Out-Null
Get-ChildItem -Force | Where-Object { $excluir -notcontains $_.Name } |
  Copy-Item -Destination $temp -Recurse -Force
Compress-Archive -Path "$temp\*" -DestinationPath "$env:TEMP\listanegra-v1.zip" -Force
```

Verifique el contenido: al abrir el ZIP debe ver `application.py`, `Procfile`, `requirements.txt`,
`.ebextensions/` y `src/` en el primer nivel.

> `.ebextensions` empieza con punto. `Compress-Archive` la incluye solo si usa `Get-ChildItem -Force`
> como arriba. Si la carpeta no viaja en el ZIP, el health check y el Auto Scaling quedarán sin
> configurar.

---

## Fase 3 – Crear la aplicación y el ambiente en Elastic Beanstalk

### 3.1 Datos iniciales

1. Consola → **Elastic Beanstalk** → **Create application**.
2. **Environment tier:** `Web server environment`.
3. **Application name:** `listanegra-devopskings`.
4. **Environment name:** `listanegra-env` (acepte el dominio sugerido y verifique disponibilidad).
5. **Platform:**
   - **Platform:** `Python`
   - **Platform branch:** `Python 3.11 running on 64bit Amazon Linux 2023`
     (3.12 o 3.13 también funcionan; evite ramas marcadas como *retired*)
   - **Platform version:** la recomendada
6. **Application code:** `Upload your code` → *Local file* → el ZIP de la Fase 2.
   **Version label:** `v1-inicial`.
7. **Presets:** `Custom configuration` (necesario para pedir varias instancias).
8. **Next**.

### 3.2 Service access (paso donde más falla AWS Academy)

| Campo | AWS Academy / Learner Lab | Cuenta propia |
|---|---|---|
| **Service role** | `Use an existing service role` → **LabRole** | `Create and use new service role` |
| **EC2 key pair** | opcional (solo si quiere SSH) | opcional |
| **EC2 instance profile** | **LabInstanceProfile** (si no existe, `LabRole`) | `aws-elasticbeanstalk-ec2-role` |

En AWS Academy **no** tiene permisos para crear roles IAM. Si ve un error tipo
`not authorized to perform: iam:CreateRole`, significa que eligió "create new role": vuelva y
seleccione los roles existentes del laboratorio.

### 3.3 Networking, database and tags ← aquí se crea la base de datos

**Networking**

- **VPC:** la VPC por defecto.
- **Instance subnets:** marque **al menos dos** subredes en zonas de disponibilidad distintas
  (requisito del balanceador y base para alta disponibilidad).
- **Public IP address:** activado (`Activated`) para las instancias.

**Database** (Opción A). Active la sección y configure:

| Campo | Valor |
|---|---|
| **Snapshot** | `None` |
| **Engine** | `postgres` |
| **Engine version** | 15.x o 16.x |
| **Instance class** | `db.t3.micro` |
| **Storage** | 20 GB |
| **Username** | `postgres` |
| **Password** | 8–16 caracteres ASCII imprimibles, **sin** `/`, `\` ni `@` |
| **Availability** | `Low (one AZ)` |
| **Database deletion policy** | **`Retain`** ← no lo deje en `Delete` |

Guarde la contraseña: no se puede volver a consultar en la consola.

La base se llamará `ebdb` (Elastic Beanstalk no permite elegir el nombre) y la aplicación la
recibirá por la variable `RDS_DB_NAME`. **No agregue las variables `DB_HOST`, `DB_NAME`, `DB_USER` ni
`DB_PASSWORD`**: si lo hace, sobrescriben a las `RDS_*` y la app apuntaría a otro lugar.

> Si el laboratorio de AWS Academy rechaza la creación de la base desde Elastic Beanstalk por
> permisos (`rds:CreateDBInstance`), use el **[Anexo A](#anexo-a--opción-b-rds-independiente)**.

📸 *Capturas para el punto 1.a del documento ("Configuración de RDS"): este panel **Database** con el
engine, la clase de instancia y la deletion policy; y, al terminar la creación, la instancia en la
consola de **RDS → Databases** en estado `Available` con su endpoint.*

### 3.4 Instance traffic and scaling

Aquí se configura lo que exige el punto 2 del documento (más de una instancia):

- **Root volume:** valores por defecto.
- **Instance types:** `t3.micro` (puede añadir `t3.small` como alternativa).
- **Capacity → Environment type:** `Load balanced`
- **Instances:** **Min = 3**, **Max = 6**
- **Fleet composition:** `On-Demand instances`
- **Scaling triggers:** `CPUUtilization`, Average, Percent, Upper 70, Lower 30, periodo 5 min.
- **Load balancer type:** `Application Load Balancer` → `Dedicated`
- **Listeners:** HTTP puerto 80 por defecto.
- **Processes → default:**
  - **Health check path:** `/health`
  - **Port:** 80, **Protocol:** HTTP
  - **Healthy threshold:** 3, **Unhealthy threshold:** 5
  - **Interval:** 15 s, **Timeout:** 5 s
  - **HTTP code (Matcher):** 200

Estos valores ya vienen en `.ebextensions/01_app.config` y `02_autoscaling.config`, pero conviene
revisarlos en la consola para tomar las capturas.

📸 *Capturas para los puntos 1.b y 1.c del documento: la pantalla de Capacity con min 3 / max 6, y la
pantalla Processes con el health check path `/health`.*

### 3.5 Updates, monitoring and logging

- **Health reporting → System:** `Enhanced`
- **Managed platform updates:** desactívelo durante la práctica, para que no interfiera con las
  mediciones de tiempo de los despliegues.
- **Deployment policy:** `All at once` (es la primera de las 4 estrategias que se van a medir).
- **Log streaming to CloudWatch Logs:** actívelo si quiere ver los logs de gunicorn en CloudWatch
  (útil para depurar); fíjelo con retención de 1 día.
- **Environment properties:** agregue solo estas dos. Las de base de datos las pone Elastic
  Beanstalk automáticamente.

  | Name | Value |
  |---|---|
  | `STATIC_TOKEN` | el token que usará en Postman |
  | `JWT_SECRET_KEY` | una cadena aleatoria larga |

  Genere valores aleatorios así:

  ```powershell
  [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }))
  ```

  `APP_ENV=production` y `AUTO_CREATE_TABLES=true` ya vienen en `.ebextensions/01_app.config`.
  `STATIC_TOKEN` y `JWT_SECRET_KEY` **no** se versionan en GitHub: viven solo aquí.

### 3.6 Crear el ambiente

**Submit**. La creación tarda entre 15 y 25 minutos (crea la base RDS, el ALB, el ASG, las 3
instancias y despliega el código). Al terminar, el Health del ambiente debe quedar en **Ok (verde)**.

Como Elastic Beanstalk crea la base antes de arrancar las instancias, la aplicación conecta en el
primer arranque y crea la tabla `blacklist` automáticamente (`db.create_all()`).

📸 *Captura: dashboard del ambiente en verde con la URL y la versión `v1-inicial`.*

---

## Fase 4 – Verificar que todo funciona

### 4.1 Health check

```powershell
$url = "http://listanegra-env.eba-xxxxxxx.us-east-1.elasticbeanstalk.com"
Invoke-RestMethod -Uri "$url/health"
# Esperado: @{status=ok; database=up}
```

Si responde `database: down`, la app está arriba pero no alcanza la base: vaya a
[Problemas frecuentes](#problemas-frecuentes).

### 4.2 Prueba funcional de los endpoints

```powershell
$url   = "http://listanegra-env.eba-xxxxxxx.us-east-1.elasticbeanstalk.com"
$token = "<el valor de STATIC_TOKEN>"
$h     = @{ Authorization = "Bearer $token" }

# 1. Agregar un email a la lista negra
$body = @{
  email          = "spammer@example.com"
  app_uuid       = [guid]::NewGuid().ToString()
  blocked_reason = "Envio masivo de correo no solicitado"
} | ConvertTo-Json
Invoke-RestMethod -Uri "$url/blacklists" -Method POST -Headers $h -ContentType application/json -Body $body

# 2. Consultar un email que SI esta en la lista
Invoke-RestMethod -Uri "$url/blacklists/spammer@example.com" -Headers $h

# 3. Consultar un email que NO esta en la lista
Invoke-RestMethod -Uri "$url/blacklists/cliente.ok@example.com" -Headers $h

# 4. Sin token: debe responder 401
try { Invoke-RestMethod -Uri "$url/blacklists/spammer@example.com" }
catch { "HTTP $($_.Exception.Response.StatusCode.value__)" }
```

En la respuesta del paso 1 confirme que `ip_address` contiene **su IP pública** (no la del
balanceador): es la evidencia de que el microservicio registra la IP de origen correctamente.

### 4.3 Postman

Importe la colección y el environment de `postman/`, ajuste `base_url` y `bearer_token`, y ejecute
los 14 escenarios con el **Collection Runner**.

📸 *Captura: Collection Runner con los 14 escenarios en verde.*

Publique la documentación desde Postman (**Collection → View documentation → Publish**) y anexe la
URL al documento de la entrega.

### 4.4 Ver los datos en la base (opcional, para el video)

Con la Opción A la base no es pública, así que no se alcanza con pgAdmin desde su equipo. Para
demostrar la persistencia:

- La forma simple: `POST` y luego `GET` del mismo email, y después **Restart app server(s)** y
  repetir el `GET`. Si sigue respondiendo `blacklisted: true`, el dato está en RDS y no en memoria.
- La forma directa: conéctese a una instancia EC2 por **Session Manager** y ejecute
  `psql -h $RDS_HOSTNAME -U postgres -d ebdb -c "SELECT * FROM blacklist;"`.

---

## Fase 5 – Las 4 estrategias de despliegue (20% de la nota)

### Cómo cambiar de estrategia

Elastic Beanstalk → `listanegra-env` → **Configuration** → *Updates, monitoring, and logging* →
**Edit** → sección **Deployments** → **Deployment policy** → **Apply**.

### Cómo generar una versión nueva para desplegar

Cada medición necesita un artefacto distinto. Introduzca un cambio trivial y visible, por ejemplo
suba la versión en `src/resources/health.py` (`"version"`), o defina la variable de entorno
`APP_VERSION`. Luego:

```powershell
git commit -am "v2: prueba de estrategia rolling"
git archive --format=zip --output ..\listanegra-v2.zip HEAD
```

Y en la consola: **Upload and deploy** → seleccione el ZIP → **Version label** descriptivo
(`v2-rolling`) → **Deploy**.

### Cómo medir el tiempo exacto

El tiempo oficial sale del log de eventos del ambiente: **Events** (o pestaña *Events* del ambiente).
Busque la pareja de eventos:

- `Environment update is starting.` ← inicio
- `Environment update completed successfully.` ← fin

La diferencia entre ambas marcas de tiempo es el tiempo total del despliegue. Tome la captura con
ambos eventos visibles.

### Cómo validar que el despliegue estaba en ejecución (sin downtime)

Deje este monitor corriendo en una terminal **durante todo el despliegue**. Registra la
disponibilidad segundo a segundo y produce el resumen que pide el literal *b*:

```powershell
$url = "http://listanegra-env.eba-xxxxxxx.us-east-1.elasticbeanstalk.com/health"
$ok = 0; $fail = 0; $inicio = Get-Date
while ($true) {
  $t = (Get-Date).ToString("HH:mm:ss")
  try {
    $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    $ok++
    Write-Host "$t  HTTP $($r.StatusCode)  OK=$ok  FAIL=$fail" -ForegroundColor Green
  } catch {
    $fail++
    $code = $_.Exception.Response.StatusCode.value__
    Write-Host "$t  FALLO ($code)  OK=$ok  FAIL=$fail" -ForegroundColor Red
  }
  Start-Sleep -Seconds 1
}
# Ctrl+C para detener. Transcurrido: (Get-Date) - $inicio
```

Evidencias complementarias de que el despliegue estaba activo:

- **Health** del ambiente → pestaña **Health**: muestra instancia por instancia su estado
  (`Ok`, `Pending`, `Degraded`) y la **versión desplegada en cada una**. Durante un rolling verá
  instancias con `v1` y otras con `v2` simultáneamente.
- **EC2 → Instances**: los IDs de instancia y su hora de lanzamiento. Si cambian, el despliegue creó
  instancias nuevas (literal *d*).
- **EC2 → Target Groups → Targets**: estado `healthy` / `draining` / `unused` de cada instancia.

### Qué esperar de cada estrategia

Ejecute estas cuatro (o reemplace alguna por *traffic splitting*) y documente los 6 literales de
cada una:

| # | Estrategia | Dónde se despliega | Capacidad durante el despliegue | Tiempo típico (3 instancias) |
|---|---|---|---|---|
| 1 | **All at once** | Instancias existentes | Cae a 0 → **hay downtime** | ~1–3 min |
| 2 | **Rolling** (batch 1) | Instancias existentes | Reducida (2 de 3 sirviendo) | ~4–8 min |
| 3 | **Rolling with additional batch** | Existentes + 1 lote nuevo | Siempre 100% | ~7–12 min |
| 4 | **Immutable** | ASG temporal con instancias nuevas | Siempre 100% | ~10–18 min |
| 5 | **Traffic splitting** (opcional) | Instancias nuevas, tráfico en canario | 100% + % configurable al canario | ~12–20 min |

Configuración adicional por estrategia, en la misma pantalla **Deployments**:

- *Rolling*: **Batch size** → `Fixed = 1` (o `Percentage = 33%`).
- *Rolling with additional batch*: **Batch size** → `Fixed = 1`.
- *Traffic splitting*: **Traffic split** = 10%, **Traffic splitting evaluation time** = 5 min.

Plantilla para documentar cada estrategia:

```
Estrategia: Rolling with additional batch
a. Instancias utilizadas: 3 iniciales + 1 lote adicional = 4 durante el despliegue
b. Validación: monitor de /health cada 1 s → 0 fallos sobre N solicitudes;
   pestaña Health mostrando instancias con versión v2 y v3 en simultáneo;
   target group con las instancias en estado healthy/draining
c. Tiempo total: 00:08:42 (evento "update is starting" 14:03:11 → "completed" 14:11:53)
d. ¿Instancias nuevas? Sí, se lanzó una instancia adicional (i-0ab...) que permaneció al final
   reemplazando a una de las originales
e. Capturas: dashboard, Events con ambas marcas de tiempo, Health por instancia, EC2 Instances
f. Hallazgos: sin pérdida de disponibilidad; mayor costo temporal por la instancia extra;
   el rollback es rápido porque el lote adicional se descarta si falla el health check
```

---

## Fase 6 – Checklist de la entrega

**Aplicación y repositorio**

- [ ] `POST /blacklists` responde 201 y persiste `email`, `app_uuid`, `blocked_reason`, `ip_address`, `created_at`
- [ ] `GET /blacklists/<email>` responde `blacklisted` + `blocked_reason`
- [ ] Ambos endpoints devuelven 401 sin Bearer Token
- [ ] Datos persistidos en RDS PostgreSQL (no SQLite)
- [ ] Repositorio en GitHub, sin credenciales ni `.env`, sin pipelines de CI/CD

**Postman**

- [ ] Workspace de equipo creado
- [ ] Colección con los escenarios de éxito y error de cada endpoint
- [ ] Documentación publicada; URL pública anexada al documento

**Documento `Proyecto 1 entrega 1 – Documento.pdf`**

- [ ] (10%) Capturas del paso a paso: RDS, proyecto en Beanstalk, health checks
- [ ] (20%) 4 estrategias de despliegue, cada una con los literales a–f

**Video (máx. 10 minutos)**

- [ ] Endpoints funcionando contra la URL de Elastic Beanstalk
- [ ] Consola de AWS: RDS, ambiente de EB, estrategias de despliegue
- [ ] Repositorio en GitHub y colección de Postman
- [ ] Participan los integrantes del grupo

---

## Anexo A – Opción B: RDS independiente

Use este anexo solo si necesita la base fuera del ambiente: para conectar varios ambientes a la
misma base, hacer blue/green, elegir el nombre de la base, o porque el laboratorio de AWS Academy no
permite crear la base desde Elastic Beanstalk.

Ejecute el anexo **antes** de la Fase 3, porque necesitará el endpoint de la base.

### A.1 Security group para la base de datos

1. Consola → **EC2** → *Network & Security* → **Security Groups** → **Create security group**.
2. **Name:** `sg-listanegra-rds`, **VPC:** la default (la misma que usará Elastic Beanstalk).
3. **Inbound rules:** déjelo vacío; la regla se agrega en A.4, cuando exista el ambiente.
4. **Create security group** y anote el ID (`sg-xxxxxxxx`).

### A.2 Crear la instancia PostgreSQL

1. Consola → **RDS** → **Databases** → **Create database**.
2. `Standard create` → **Engine** `PostgreSQL` 15.x o 16.x → **Templates** `Free tier`
   (o `Dev/Test` si la cuenta no ofrece free tier).
3. **Settings:**
   - **DB instance identifier:** `listanegra-db`
   - **Master username:** `postgres`
   - **Credentials management:** `Self managed`
   - **Master password:** una contraseña fuerte. **Guárdela**, no se puede volver a ver.
4. **Instance configuration:** `db.t3.micro` (o `db.t4g.micro`).
5. **Storage:** 20 GB gp3. **Desactive** *Enable storage autoscaling*.
6. **Connectivity:**
   - **Compute resource:** `Don't connect to an EC2 compute resource`
   - **VPC:** la default
   - **Public access:** `No`
   - **VPC security group:** `Choose existing` → `sg-listanegra-rds`, y **quite** el grupo `default`
7. **Database authentication:** `Password authentication`.
8. **Monitoring:** desactive *Performance Insights*.
9. **Additional configuration** ← **paso crítico:**
   - **Initial database name:** `blacklistdb`
     Si deja este campo vacío, RDS crea el servidor pero **ninguna base de datos**, y la aplicación
     fallará con `database "blacklistdb" does not exist`.
   - **Backup retention:** 1 día (o 0 para la práctica).
10. **Create database**. Tarda 5–10 minutos en pasar a `Available`.
11. Abra `listanegra-db` → **Connectivity & security** y copie el **Endpoint** y el **Port**.

### A.3 Variables de entorno en Elastic Beanstalk

En la Fase 3.3 deje la sección **Database vacía**, y en la Fase 3.5 agregue, además de
`STATIC_TOKEN` y `JWT_SECRET_KEY`:

| Name | Value |
|---|---|
| `DB_ENGINE` | `postgresql` |
| `DB_HOST` | el endpoint de RDS (sin `:5432`) |
| `DB_PORT` | `5432` |
| `DB_NAME` | `blacklistdb` |
| `DB_USER` | `postgres` |
| `DB_PASSWORD` | la contraseña maestra de RDS |

### A.4 Abrir el puerto 5432 desde las instancias

Al terminar la Fase 3, el ambiente aparecerá **Degraded** o **Severe**: la aplicación arrancó pero el
security group de RDS todavía bloquea el tráfico, así que `/health` responde 503 con
`database: down`. Es esperado y se corrige así:

1. **Averigüe el security group de las instancias EC2:** Elastic Beanstalk → `listanegra-env` →
   **Configuration** → *Instance traffic and scaling* → **Edit** → sección **Instances** →
   **EC2 security groups**. Es algo como `awseb-e-xxxxxxx-stack-AWSEBSecurityGroup-xxxxxxxx`.

2. **Autorice el acceso:** EC2 → **Security Groups** → `sg-listanegra-rds` → **Inbound rules** →
   **Edit inbound rules** → **Add rule**:

   | Campo | Valor |
   |---|---|
   | Type | `PostgreSQL` |
   | Protocol / Port | TCP / 5432 |
   | Source | `Custom` → el security group de las instancias de EB |
   | Description | `Acceso desde instancias de Elastic Beanstalk` |

   **Save rules**.

   > Use el **security group** como origen, no un rango de IPs. Las instancias cambian de IP en cada
   > despliegue inmutable o evento de autoscaling; la regla por security group sigue funcionando.

3. **Actions → Restart app server(s)** para que gunicorn reabra la conexión y cree las tablas.

4. Verifique con `GET /health` que responda `database: up`, y continúe en la Fase 4.

📸 *Captura: la regla de entrada 5432 en `sg-listanegra-rds`.*

---

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `502 Bad Gateway` | gunicorn no arrancó | `Logs` → *Request logs* → *Last 100 lines*; revise `/var/log/web.stdout.log` |
| `/health` responde `database: down` (Opción A) | La base aún se está creando, o se definieron variables `DB_*` que sobrescriben las `RDS_*` | Espere a que RDS esté `Available`; borre las `DB_HOST`/`DB_NAME`/`DB_USER`/`DB_PASSWORD` de *Environment properties* |
| `/health` responde `database: down` (Opción B) | Security group de RDS sin la regla 5432 | Anexo A.4 |
| `could not translate host name` | `DB_HOST` mal escrito | Use el endpoint sin `:5432` |
| `database "blacklistdb" does not exist` | En la Opción B no se definió *Initial database name* | Cree la base con `psql`, o recree la instancia RDS |
| `password authentication failed` | Contraseña incorrecta | Opción A: *Configuration → Database → Edit → Password*. Opción B: reinicie la contraseña maestra en RDS y actualice `DB_PASSWORD` |
| La contraseña de la base es rechazada al crear el ambiente | Las bases acopladas exigen 8–16 caracteres ASCII imprimibles sin `/`, `\` ni `@` | Use una contraseña que cumpla esa regla |
| `not authorized to perform: iam:CreateRole` | Se eligió crear roles nuevos en AWS Academy | Use `LabRole` y `LabInstanceProfile` |
| `Requires a minimum of 2 subnets` | Se seleccionó una sola subred | Marque subredes en dos AZ distintas |
| El ZIP se despliega pero `.ebextensions` no aplica | La carpeta oculta no entró al ZIP | Use `git archive` o `Get-ChildItem -Force` |
| `ip_address` guarda la IP del balanceador | Falta `X-Forwarded-For` | Ya está resuelto en `src/utils.py`; verifique que el ALB esté al frente |

### Ver logs de la aplicación

Elastic Beanstalk → `listanegra-env` → **Logs** → **Request logs** → *Last 100 lines* o
*Full logs*. Los archivos útiles son:

- `/var/log/web.stdout.log` – salida de gunicorn y de la aplicación Flask
- `/var/log/eb-engine.log` – proceso de despliegue de la plataforma (errores de `pip install`)
- `/var/log/nginx/error.log` – errores del proxy

### Limpieza al terminar

Para no consumir créditos: Elastic Beanstalk → **Actions** → **Terminate environment**.

- Con la Opción A y deletion policy `Retain`, la base **sobrevive**: bórrela aparte en
  RDS → **Actions** → **Delete**.
- Con la Opción A y deletion policy `Delete`, la base se borra junto con el ambiente.
- Con la Opción B, borre la instancia RDS y el security group `sg-listanegra-rds` manualmente.
