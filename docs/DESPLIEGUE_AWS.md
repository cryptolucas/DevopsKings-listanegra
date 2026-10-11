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

## Fase 1 – Crear la base de datos en RDS

El enunciado solo pide persistir en un servicio de bases de datos relacionales y *recomienda* RDS.
La base se crea como **instancia independiente** en la consola de RDS.

> La documentación de AWS describe también una base *acoplada* al ambiente, que Elastic Beanstalk
> crea y conecta sola inyectando `RDS_HOSTNAME`, `RDS_PORT`, `RDS_DB_NAME`, `RDS_USERNAME` y
> `RDS_PASSWORD`. **Esa sección ya no aparece en el asistente de creación de la consola** (ni en las
> cuentas de AWS Academy), así que el camino real es el de esta fase. El código soporta ambos:
> `src/config.py` lee las `DB_*` y, si no están, las `RDS_*`.

Una base independiente además es preferible: sobrevive a la terminación del ambiente, permite
conectar varios ambientes a la misma base y hacer blue/green
([Using Elastic Beanstalk with Amazon RDS](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/AWSHowTo.RDS.html)).

> **Si el ambiente de Elastic Beanstalk ya existe**, el orden cambia un poco y se evita una vuelta
> atrás: vaya al **[Anexo A](#anexo-a--conectar-rds-a-un-ambiente-que-ya-existe)**.

### 1.1 Security group para la base de datos

1. Consola → **EC2** → *Network & Security* → **Security Groups** → **Create security group**.
2. **Name:** `sg-listanegra-rds`
   **Description:** `Acceso PostgreSQL para el microservicio de lista negra`
   **VPC:** la default (la misma que usará Elastic Beanstalk)
3. **Inbound rules:** déjelo vacío. La regla se agrega en la Fase 4, cuando ya exista el ambiente y
   se conozca su security group.
4. **Create security group** y anote el ID (`sg-xxxxxxxx`).

### 1.2 Crear la instancia PostgreSQL

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
   - **VPC:** la default, la misma donde irán las instancias de Elastic Beanstalk
   - **Public access:** `No`
   - **VPC security group:** `Choose existing` → `sg-listanegra-rds`, y **quite** el grupo `default`
7. **Database authentication:** `Password authentication`.
8. **Monitoring:** desactive *Performance Insights* (ahorra costo).
9. **Additional configuration** ← **paso crítico:**
   - **Initial database name:** `blacklistdb`
     Si deja este campo vacío, RDS crea el servidor pero **ninguna base de datos**, y la aplicación
     fallará con `database "blacklistdb" does not exist`.
   - **Backup retention:** 1 día (o 0 para la práctica).
10. **Create database**. Tarda 5–10 minutos en pasar a `Available`.

### 1.3 Anotar el endpoint

Con el estado en `Available`, abra `listanegra-db` → pestaña **Connectivity & security** y copie:

- **Endpoint:** `listanegra-db.xxxxxxxx.us-east-1.rds.amazonaws.com`
- **Port:** `5432`

📸 *Capturas para el punto 1.a del documento ("Configuración de RDS"): la pantalla de creación con el
engine y la clase de instancia, la sección Connectivity con el security group, el campo
**Initial database name** = `blacklistdb`, y la vista final de la base en `Available` con su
endpoint.*

> Con **Public access = No** no podrá conectarse con pgAdmin/DBeaver desde su equipo. Es lo correcto:
> la base solo es alcanzable desde la VPC. Para el video, demuestre la persistencia a través del API
> (`POST` y luego varios `GET`) o con `psql` desde una instancia EC2 vía **Session Manager**.

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

### 3.3 Networking, database and tags

- **VPC:** la misma VPC de la base de datos (la default).
- **Instance subnets:** marque **al menos dos** subredes en zonas de disponibilidad distintas
  (requisito del balanceador y base para alta disponibilidad).
- **Public IP address:** activado (`Activated`) para las instancias.
- **Database:** no hay nada que configurar. El asistente ya no ofrece crear una base acoplada; la
  base se creó aparte en la Fase 1 y se conecta por variables de entorno en la Fase 3.5.

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
- **Environment properties:** aquí van las credenciales. Agregue las ocho:

  | Name | Value |
  |---|---|
  | `DB_ENGINE` | `postgresql` |
  | `DB_HOST` | el endpoint de RDS de la Fase 1.3, **sin** `:5432` |
  | `DB_PORT` | `5432` |
  | `DB_NAME` | `blacklistdb` |
  | `DB_USER` | `postgres` |
  | `DB_PASSWORD` | la contraseña maestra de RDS |
  | `STATIC_TOKEN` | el token que usará en Postman |
  | `JWT_SECRET_KEY` | una cadena aleatoria larga |

  Genere los valores aleatorios con un generador criptográfico (no con `Get-Random`, que no lo es):

  ```powershell
  $bytes = New-Object byte[] 48
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
  [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_').TrimEnd('=')
  ```

  El resultado solo usa `A-Z a-z 0-9 - _`, caracteres válidos para un valor de environment property
  y que no necesitan escape.

  `APP_ENV=production` y `AUTO_CREATE_TABLES=true` ya vienen en `.ebextensions/01_app.config`.
  Las credenciales **no** se versionan en GitHub: viven solo aquí.

> Si omite las variables `DB_*`, la aplicación **no falla**: `src/config.py` cae a SQLite local y
> `/health` reporta `database: up`. Parece que todo funciona, pero cada instancia tendría su propia
> base y se borraría en cada despliegue. Vea la Fase 4.2 para detectarlo.

### 3.6 Crear el ambiente

**Submit**. La creación tarda entre 5 y 15 minutos (crea el ALB, el ASG, las 3 instancias y despliega
el código).

El ambiente quedará en **Degraded** o **Severe**: la aplicación arrancó pero el security group de
RDS todavía bloquea el puerto 5432, así que `/health` responde 503 con `database: down`. Es esperado
y se corrige en la Fase 4.

📸 *Captura: dashboard del ambiente con la URL y la versión `v1-inicial`.*

---

## Fase 4 – Conectar el ambiente con RDS y verificar

### 4.1 Abrir el puerto 5432 desde las instancias

1. **Averigüe el security group de las instancias EC2:** Elastic Beanstalk → `listanegra-env` →
   **Configuration** → *Instance traffic and scaling* → **Edit** → sección **Instances** →
   **EC2 security groups**. Es algo como `awseb-e-xxxxxxx-stack-AWSEBSecurityGroup-xxxxxxxx`.
   Cópielo y salga con **Cancel** sin guardar nada.

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

3. **Actions → Restart app server(s)** para que gunicorn reabra la conexión y cree la tabla.

📸 *Captura: la regla de entrada 5432 en `sg-listanegra-rds` apuntando al security group del
ambiente.*

### 4.2 Health check

```powershell
$url = "http://listanegra-env.eba-xxxxxxx.us-east-1.elasticbeanstalk.com"
Invoke-RestMethod -Uri "$url/health"
# Esperado: @{status=ok; database=up}
```

El Health del ambiente debe pasar a **Ok (verde)**. Si responde `database: down`, vaya a
[Problemas frecuentes](#problemas-frecuentes).

> ⚠️ `database: up` **no** garantiza que esté usando RDS. Si faltan las variables `DB_*`, la
> aplicación cae a SQLite local y el health check también pasa. La prueba definitiva es la
> consistencia entre instancias: inserte un email y repita el `GET` unas seis veces. Con RDS, las
> seis respuestas son `blacklisted: true`. Con SQLite verá `true` y `false` alternados, porque el
> balanceador reparte entre instancias que tienen cada una su propio archivo.
>
> ```powershell
> 1..6 | ForEach-Object { (Invoke-RestMethod -Uri "$url/blacklists/spammer@example.com" -Headers $h).blacklisted }
> ```

### 4.3 Prueba funcional de los endpoints

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

### 4.4 Postman

Importe la colección y el environment de `postman/`, ajuste `base_url` y `bearer_token`, y ejecute
los 14 escenarios con el **Collection Runner**.

📸 *Captura: Collection Runner con los 14 escenarios en verde.*

Publique la documentación desde Postman (**Collection → View documentation → Publish**) y anexe la
URL al documento de la entrega.

### 4.5 Ver los datos en la base (opcional, para el video)

Con `Public access = No` la base no se alcanza con pgAdmin desde su equipo. Para demostrar la
persistencia:

- La forma simple: `POST` y luego `GET` del mismo email, y después **Restart app server(s)** y
  repetir el `GET`. Si sigue respondiendo `blacklisted: true`, el dato está en RDS y no en el
  sistema de archivos de la instancia.
- La forma directa: conéctese a una instancia EC2 por **Session Manager** y ejecute
  `psql -h $DB_HOST -U postgres -d blacklistdb -c "SELECT * FROM blacklist;"`.

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

## Anexo A – Conectar RDS a un ambiente que ya existe

Si el ambiente de Elastic Beanstalk se creó antes que la base de datos, este orden evita una vuelta
atrás: se averigua primero el security group del ambiente, de modo que el de la base se crea ya con
la regla de entrada puesta.

1. **Security group del ambiente.** Elastic Beanstalk → su ambiente → **Configuration** →
   *Instance traffic and scaling* → **Edit** → sección **Instances** → **EC2 security groups**.
   Copie el nombre (`awseb-e-...-AWSEBSecurityGroup-...`) y salga con **Cancel** sin guardar.

2. **Security group de la base.** EC2 → **Security Groups** → **Create security group**:
   nombre `sg-listanegra-rds`, la VPC del ambiente, y **ya con** la inbound rule
   `PostgreSQL` / TCP 5432 / Source = `Custom` → el security group del paso 1.

3. **Instancia RDS.** Igual que la [Fase 1.2](#12-crear-la-instancia-postgresql), seleccionando
   `sg-listanegra-rds` en *Connectivity*. No olvide **Initial database name = `blacklistdb`**.

4. **Endpoint.** Cópielo como en la [Fase 1.3](#13-anotar-el-endpoint).

5. **Variables de entorno.** Elastic Beanstalk → su ambiente → **Configuration** →
   *Updates, monitoring, and logging* → **Edit** → **Environment properties** → agregue las seis
   variables `DB_*` de la [Fase 3.5](#35-updates-monitoring-and-logging) → **Apply**.

   Guardar environment properties dispara una actualización del ambiente de 1 a 3 minutos que
   reinicia los servidores de aplicación. Al arrancar, `src/config.py` detecta `DB_HOST` (que tiene
   precedencia sobre el fallback a SQLite), se conecta a RDS y `db.create_all()` crea la tabla
   `blacklist`. **No hace falta** un *Restart app server(s)* aparte ni volver a subir el ZIP.

6. **Verifique** con la [Fase 4.2](#42-health-check), incluyendo la prueba de consistencia de los
   seis `GET` seguidos.

---

## Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `502 Bad Gateway` | gunicorn no arrancó | `Logs` → *Request logs* → *Last 100 lines*; revise `/var/log/web.stdout.log` |
| `/health` responde `database: down` | Security group de RDS sin la regla 5432, o RDS todavía no está `Available` | Fase 4.1 |
| `/health` responde `database: up` pero los `GET` alternan `true`/`false` | Faltan las variables `DB_*`: la app está sobre SQLite local, una base por instancia | Agregue las `DB_*` en *Environment properties* (Fase 3.5) |
| `could not translate host name` | `DB_HOST` mal escrito | Use el endpoint sin `:5432` |
| `database "blacklistdb" does not exist` | No se definió *Initial database name* al crear RDS | Cree la base con `psql`, o recree la instancia RDS |
| `password authentication failed` | `DB_PASSWORD` incorrecto | Reinicie la contraseña maestra en RDS (**Modify**) y actualice la variable |
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

Para no consumir créditos, en este orden:

1. Elastic Beanstalk → **Actions** → **Terminate environment**. Como la base es independiente,
   **sobrevive**: puede recrear el ambiente después sin perder los datos.
2. RDS → `listanegra-db` → **Actions** → **Delete** (desmarque *Create final snapshot* si no lo
   necesita).
3. EC2 → **Security Groups** → borre `sg-listanegra-rds`.

Si todavía le faltan estrategias de despliegue por documentar, termine solo el ambiente y deje la
base: al recrear el ambiente basta volver a poner las variables `DB_*` y la regla 5432.
