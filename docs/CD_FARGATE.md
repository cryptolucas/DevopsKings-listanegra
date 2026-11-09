# Entrega 3 – Tutorial: entrega continua (CD) en AWS Fargate

Al terminar este tutorial, cada commit en `main` ejecuta las pruebas, construye la imagen Docker, la
publica en Amazon ECR y la despliega automáticamente en AWS Fargate con AWS CodeDeploy (blue/green).

```
git push a main
   │
   ▼
CodePipeline ── Source ── Build (CodeBuild, buildspec-cd.yml) ─────────── Deploy (CodeDeploy)
                GitHub     1. pytest (23 pruebas)                          Amazon ECS (Blue/Green)
                           2. docker build → push a ECR                    1. registra la nueva taskdef
                           3. imageDetail.json + taskdef.json +            2. levanta tareas "green"
                              appspec.yaml                                  3. pasa el tráfico del ALB
                                                                            4. apaga las "blue"
```

```
Internet → Application Load Balancer (puerto 80)
              ├─ target group BLUE  ─► tareas Fargate con la versión actual
              └─ target group GREEN ─► tareas Fargate con la versión nueva (durante el despliegue)
                                         │
                                         ▼
                                    RDS PostgreSQL (puerto 5432)
```

**Cómo usar este tutorial:** haga los pasos en orden; cada uno depende de los anteriores. Al final de
cada paso hay un ✅ para verificar que quedó bien y un 📸 con las capturas para el documento. Tómelas
en el momento: rehacer una captura después suele obligar a repetir el paso.

| Parte | Qué se hace | Tiempo aprox. | Nota |
|---|---|---|---|
| 0 | Preparación | 15 min | – |
| A | Infraestructura de Fargate y despliegue manual | 1,5 a 2 h | 20% |
| B | Pipeline de CI/CD | 45 min | 60% |
| C | Las tres ejecuciones del documento | 1 h | 20% |
| D | Documento y video | – | obligatorio |

---

## Archivos del repositorio que usa este tutorial

| Archivo | Para qué |
|---|---|
| `Dockerfile` | Imagen del microservicio: Python 3.11 slim + gunicorn en el puerto 8000, usuario sin privilegios |
| `.dockerignore` | Deja fuera de la imagen las pruebas, docs, `.git`, etc. |
| `buildspec-cd.yml` | CodeBuild: pruebas → imagen → push a ECR → archivos para CodeDeploy |
| `deploy/taskdef.json` | Definición de tarea de Fargate (0.5 vCPU, 1 GB). `<IMAGE1_NAME>` lo llena CodePipeline; `<ACCOUNT_ID>` y `<REGION>` los llena el buildspec |
| `deploy/appspec.yaml` | Instrucciones de CodeDeploy: qué contenedor y puerto conectar al balanceador |
| `scripts/crear_servicio_ecs.sh` | Crea el servicio de ECS con el controlador `CODE_DEPLOY` (paso A10) |
| `postman/DevopsKings-ListaNegra-Fargate.postman_environment.json` | Environment de Postman apuntando al balanceador |
| `buildspec.yml` | Sin cambios: el pipeline de CI de la Entrega 2 |

Los secretos (contraseña de la base, token) **no están en el repositorio**: la tarea los lee de
AWS Systems Manager Parameter Store al arrancar.

---

## Parte 0 – Preparación

> **AWS Academy (Learner Lab):** si usan una cuenta de Academy no pueden crear roles. En cada paso que
> crea un rol, use `LabRole`; y antes del paso 0.1 cambie `ecsTaskExecutionRole` por `LabRole` en
> `deploy/taskdef.json`.

### 0.1 Subir el repositorio a GitHub
CloudShell clona el repositorio desde GitHub (pasos A8 y A10), así que el script y los archivos de
despliegue deben estar en `main`. En su computador, desde la carpeta del proyecto:
```powershell
git pull
git status
```
Si `git status` muestra archivos modificados o nuevos de esta entrega (`buildspec-cd.yml`,
`docs/CD_FARGATE.md`, `scripts/crear_servicio_ecs.sh`, el environment de Postman), súbalos:
```powershell
git add buildspec-cd.yml docs/CD_FARGATE.md scripts/crear_servicio_ecs.sh postman/DevopsKings-ListaNegra-Fargate.postman_environment.json
git commit -m "cd: script del servicio con CodeDeploy, tutorial y environment de Postman"
git push
```
Este push dispara el pipeline `listanegra-ci` de la Entrega 2 (solo corre las pruebas); es normal.

✅ En `https://github.com/cryptolucas/DevopsKings-listanegra` existe `scripts/crear_servicio_ecs.sh`.

### 0.2 Entrar a la consola de AWS
1. Inicie sesión con la cuenta donde está el pipeline de la Entrega 2.
2. En la esquina superior derecha elija la región **US East (N. Virginia) us-east-1**. Revísela cada vez
   que abra un servicio nuevo: si un recurso "no aparece", casi siempre es por la región.
3. Confirme que es la cuenta correcta: **CodePipeline** debe mostrar `listanegra-ci`, y en
   **Developer Tools → Settings → Connections** la conexión `github-devopskings` debe estar
   **Available**.

### 0.3 Datos de la base de datos
1. Abra **RDS → Databases** y seleccione la base de la Entrega 1 (`listanegra-db`).
2. Pestaña **Connectivity & security**: anote el **Endpoint** y el **VPC security group**
   (`sg-listanegra-rds`). Confirme que la VPC es la *default*.
3. Pestaña **Configuration**: anote el **Master username** y el **DB name** (`blacklistdb`).
4. La contraseña maestra no se puede consultar: pídala a quien creó la base.

Si la base no existe en esta cuenta, créela con la *Fase 1* de [`DESPLIEGUE_AWS.md`](DESPLIEGUE_AWS.md)
(solo la parte de RDS) y vuelva aquí.

### 0.4 Hoja de datos
Copie esta tabla en un bloc de notas y llénela a medida que avanza:

| Dato | Valor |
|---|---|
| Account ID (12 dígitos, menú de su usuario arriba a la derecha) | |
| Endpoint de la RDS | |
| Usuario / contraseña de la RDS | |
| Security group de la RDS | |
| DNS del balanceador (paso A7) | |

Los nombres de los recursos ya están fijados en este tutorial (`listanegra`, `alb-listanegra`,
`tg-listanegra-blue`, …). Úselos tal cual: el script y los archivos del repositorio los buscan por nombre.

> **Importante:** no cree el servicio de ECS desde la consola. El asistente *Create service* de ECS
> ahora ofrece el blue/green **nativo de ECS**, que no se puede conectar a CodeDeploy, y el enunciado
> exige CodeDeploy. El servicio se crea con el script del paso A10. Todo lo demás se hace en la consola.

---

## Parte A – Infraestructura de Fargate y despliegue manual (20%)

### A1. Repositorio de imágenes (ECR)
1. Busque **Elastic Container Registry** en la barra de búsqueda de la consola.
2. **Private registry → Repositories → Create repository**.
3. **Repository name:** `listanegra`.
4. **Image tag mutability:** **Mutable**. Cada build vuelve a publicar la etiqueta `latest`; con
   *Immutable* el segundo build fallaría.
5. Deje el cifrado por defecto (AES-256) → **Create**.

✅ El repositorio `listanegra` aparece en la lista, vacío.

### A2. Parámetros en Parameter Store
1. Abra **Systems Manager** → menú izquierdo → **Parameter Store** → **Create parameter**.
2. Cree estos seis parámetros, uno a la vez (**Tier: Standard**, **Data type: text**):

   | Name | Type | Value |
   |---|---|---|
   | `/listanegra/DB_HOST` | String | endpoint de la RDS, **sin** `:5432` |
   | `/listanegra/DB_NAME` | String | `blacklistdb` |
   | `/listanegra/DB_USER` | String | usuario maestro de la RDS |
   | `/listanegra/DB_PASSWORD` | **SecureString** | contraseña maestra de la RDS |
   | `/listanegra/STATIC_TOKEN` | **SecureString** | `devopskings-2026-token-listanegra` |
   | `/listanegra/JWT_SECRET_KEY` | **SecureString** | una cadena larga aleatoria (30 o más caracteres) |

3. En los SecureString deje **KMS key source: My current account** y **KMS Key ID: alias/aws/ssm**.
4. **Create parameter** en cada uno.

Los nombres deben quedar exactos (mayúsculas incluidas): `deploy/taskdef.json` los busca así.
`STATIC_TOKEN` debe ser el mismo de Postman; si lo cambia, cámbielo también en el environment.

✅ Parameter Store lista seis parámetros que empiezan por `/listanegra/`.

📸 La lista de parámetros (los SecureString salen ocultos).

### A3. Roles de IAM

**Rol 1: `ecsTaskExecutionRole`.** ECS lo usa para descargar la imagen, leer los parámetros y escribir
logs.
1. **IAM → Roles** → busque `ecsTaskExecutionRole`. Si existe, ábralo y salte al punto 7.
2. **Create role** → **Trusted entity type: AWS service**.
3. **Service or use case:** *Elastic Container Service* → opción **Elastic Container Service Task** → **Next**.
4. Busque y marque `AmazonECSTaskExecutionRolePolicy` → **Next**.
5. **Role name:** `ecsTaskExecutionRole` → **Create role**.
6. Abra el rol recién creado.
7. Pestaña **Permissions → Add permissions → Create inline policy** → pestaña **JSON** → borre el
   contenido y pegue:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["ssm:GetParameters"],
       "Resource": "arn:aws:ssm:us-east-1:*:parameter/listanegra/*"
     }]
   }
   ```
8. **Next** → **Policy name:** `listanegra-ssm` → **Create policy**.

✅ El rol tiene dos políticas: `AmazonECSTaskExecutionRolePolicy` y `listanegra-ssm`.

**Rol 2: `ecsCodeDeployRole`.** CodeDeploy lo usa para crear tareas y mover el tráfico del balanceador.
1. **IAM → Roles → Create role** → **AWS service**.
2. **Service or use case:** *CodeDeploy* → opción **CodeDeploy - ECS** → **Next**.
3. La política `AWSCodeDeployRoleForECS` ya viene marcada → **Next**.
4. **Role name:** `ecsCodeDeployRole` → **Create role**.

✅ Ambos roles aparecen en la lista de IAM.

📸 Los permisos de cada rol.

### A4. Grupo de logs
1. **CloudWatch → Logs → Log groups → Create log group**.
2. **Log group name:** `/ecs/listanegra` (con la barra inicial).
3. **Retention setting:** 1 week → **Create**.

La tarea no puede crear el grupo por su cuenta: si no existe, la tarea no arranca.

### A5. Security groups
Abra **EC2 → Network & Security → Security Groups**.

**SG del balanceador:**
1. **Create security group** → **Name:** `sg-listanegra-alb` → **Description:** `ALB listanegra` →
   **VPC:** la *default*.
2. **Inbound rules → Add rule** → **Type:** HTTP → **Source:** Anywhere-IPv4.
3. Deje las reglas de salida como están → **Create security group**.

**SG de las tareas:**
1. **Create security group** → **Name:** `sg-listanegra-tasks` → **Description:** `Tareas Fargate
   listanegra` → **VPC:** la *default*.
2. **Add rule** → **Type:** Custom TCP → **Port range:** `8000` → **Source:** Custom → escriba `sg-` y
   elija `sg-listanegra-alb`.
3. **Create security group**.

**Permitir que las tareas lleguen a la base:**
1. Seleccione el SG de la RDS (`sg-listanegra-rds`) → pestaña **Inbound rules → Edit inbound rules**.
2. **Add rule** → **Type:** PostgreSQL → **Source:** Custom → `sg-listanegra-tasks`.
3. **Save rules**. No borre las reglas que ya tenía.

✅ `sg-listanegra-tasks` permite el puerto 8000 solo desde `sg-listanegra-alb`, y el SG de la RDS
permite el 5432 desde `sg-listanegra-tasks`.

📸 Las reglas de entrada de los tres security groups.

### A6. Target groups (azul y verde)
Repita estos pasos dos veces: la primera con el nombre `tg-listanegra-blue` y la segunda con
`tg-listanegra-green`.

1. **EC2 → Load Balancing → Target Groups → Create target group**.
2. **Choose a target type:** **IP addresses**. Fargate registra la IP de cada tarea, no una instancia.
3. **Target group name:** `tg-listanegra-blue` (o `-green`).
4. **Protocol : Port:** HTTP : `8000` · **IP address type:** IPv4 · **VPC:** la *default* ·
   **Protocol version:** HTTP1.
5. **Health checks:** protocolo HTTP, **Health check path:** `/health`.
6. Despliegue **Advanced health check settings**: **Healthy threshold** 2, **Unhealthy threshold** 2,
   **Timeout** 5, **Interval** 10, **Success codes** 200. Con los valores por defecto un despliegue
   tarda unos 10 minutos; con estos, unos 3.
7. **Next**. En *Register targets* no agregue nada: si hay una IP sugerida, bórrela.
8. **Create target group**.
9. Abra el target group → pestaña **Attributes → Edit** → **Deregistration delay:** `30` segundos →
   **Save changes**. Por defecto son 300 s, y CodeDeploy esperaría 5 minutos extra en cada despliegue.

✅ Hay dos target groups con 0 targets y la columna *Load balancer* vacía (se llena en el paso A7).

### A7. Balanceador (ALB)
1. **EC2 → Load Balancers → Create load balancer** → **Application Load Balancer → Create**.
2. **Load balancer name:** `alb-listanegra` · **Scheme:** Internet-facing · **IP address type:** IPv4.
3. **Network mapping → VPC:** la *default*. **Availability Zones:** marque **us-east-1a** y
   **us-east-1b** (se elige sola la subred por defecto de cada zona). El script del paso A10 pone las
   tareas en estas mismas subredes.
4. **Security groups:** quite `default` y deje solo `sg-listanegra-alb`.
5. **Listeners and routing:** HTTP : 80 → **Default action:** *Forward to target groups* →
   `tg-listanegra-blue`.
6. **Create load balancer**. Pasa de *Provisioning* a **Active** en 2 o 3 minutos.
7. Copie el **DNS name** (`alb-listanegra-XXXX.us-east-1.elb.amazonaws.com`) en su hoja de datos.

✅ Al abrir `http://<DNS del ALB>/health` en el navegador sale **503 Service Temporarily Unavailable**.
Es lo esperado: el balanceador funciona pero todavía no tiene tareas.

📸 El ALB en estado Active con su listener HTTP:80 → `tg-listanegra-blue`.

### A8. Primera imagen, desde CloudShell
1. En la barra superior de la consola haga clic en el ícono **CloudShell** (`>_`). Se abre una terminal
   abajo. La primera vez tarda alrededor de un minuto. Confirme que la región es us-east-1.
2. Copie y pegue, una línea a la vez:
   ```bash
   git clone https://github.com/cryptolucas/DevopsKings-listanegra.git
   cd DevopsKings-listanegra
   ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
   REGISTRY=$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
   aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
   docker build -t $REGISTRY/listanegra:manual .
   docker push $REGISTRY/listanegra:manual
   ```
   - Si `git clone` dice que la carpeta ya existe: `cd DevopsKings-listanegra && git pull`.
   - `docker login` debe responder **Login Succeeded**.
   - `docker build` tarda de 1 a 2 minutos y `docker push` alrededor de 1.

✅ **ECR → listanegra** muestra una imagen con la etiqueta `manual` (unos 90 MB comprimida).

📸 La imagen `manual` en ECR.

### A9. Cluster de ECS
1. **Elastic Container Service → Clusters → Create cluster**.
2. **Cluster name:** `listanegra-cluster`.
3. **Infrastructure:** **Fargate only**. En versiones anteriores de la consola, marque solo
   *AWS Fargate (serverless)*.
4. Deje *Container Insights* apagado (cobra aparte) → **Create**.

✅ Tras un minuto el cluster aparece **Active**, con 0 servicios y 0 tareas.

### A10. Definición de tarea y servicio (script)
En la misma terminal de CloudShell, dentro de `DevopsKings-listanegra`:
```bash
bash scripts/crear_servicio_ecs.sh
```
El script:
1. Verifica que existan la imagen, el cluster, el balanceador, el target group azul y el security
   group. Si falta algo, dice qué paso de este tutorial falta y se detiene sin crear nada.
2. Registra `deploy/taskdef.json` como la revisión `listanegra:1`, con la imagen `:manual`.
3. Crea el servicio `listanegra-svc`: Fargate, 1 tarea, controlador **CODE_DEPLOY**, en las subredes
   del balanceador, con IP pública (para descargar la imagen sin NAT) y conectado a
   `tg-listanegra-blue`.
4. Cada 10 segundos imprime cuántas tareas están RUNNING y cuántos targets están *healthy*, y al final
   llama a `/health`.

La salida termina así (de 1 a 3 minutos):
```
    10:42:31  tareas RUNNING: 1/1   targets healthy: 1

GET http://alb-listanegra-XXXX.us-east-1.elb.amazonaws.com/health
{"status": "ok", "database": "up", "version": "1.0.5", "host": "ip-172-31-..."}
```
Si la tarea no queda sana, vea [Problemas frecuentes](#problemas-frecuentes).

✅ En **ECS → listanegra-cluster → Services → listanegra-svc** el servicio tiene 1/1 tareas, y en su
configuración el tipo de despliegue es **CodeDeploy** (blue/green). En el target group azul hay un
target *healthy*.

📸 La definición de tarea `listanegra:1` (contenedor, puerto 8000, *secrets*), el servicio con la
tarea RUNNING, la pestaña **Logs** de la tarea (arranque de gunicorn) y el target *healthy* en
`tg-listanegra-blue`.

### A11. Aplicación y deployment group de CodeDeploy
1. **CodeDeploy → Applications → Create application**.
2. **Application name:** `listanegra-codedeploy` · **Compute platform:** **Amazon ECS** →
   **Create application**.
3. Dentro de la aplicación: pestaña **Deployment groups → Create deployment group**.
4. Llene el formulario:

   | Campo | Valor |
   |---|---|
   | Deployment group name | `listanegra-dg` |
   | Service role | el ARN de `ecsCodeDeployRole` |
   | Choose an ECS cluster name | `listanegra-cluster` |
   | Choose an ECS service name | `listanegra-svc` |
   | Load balancer | `alb-listanegra` |
   | Production listener port | `HTTP: 80` |
   | Test listener port | (vacío) |
   | Target group 1 name | `tg-listanegra-blue` |
   | Target group 2 name | `tg-listanegra-green` |
   | Traffic rerouting | **Reroute traffic immediately** |
   | Deployment configuration | `CodeDeployDefault.ECSAllAtOnce` |
   | Original revision termination | 0 días, 0 horas, **5 minutos** |
   | Advanced → Rollbacks | ✅ **Roll back when a deployment fails** |

5. **Create deployment group**.

> **No deje la terminación en 1 hora.** CodePipeline espera a que se apaguen las tareas viejas para
> marcar el despliegue como terminado, así que cada ejecución del pipeline tardaría una hora. Con 5
> minutos, las dos versiones conviven 5 minutos, que alcanza para tomar las capturas del blue/green.

Si `listanegra-svc` no aparece en la lista o da error de controlador, el servicio se creó desde la
consola: bórrelo y repita el paso A10.

📸 La configuración del deployment group.

### A12. Validar el despliegue manual
1. **Navegador:** `http://<DNS del ALB>/health` → `"status": "ok"`, `"database": "up"`,
   `"version": "1.0.5"`.
2. **Postman:**
   1. **Import** → elija `postman/DevopsKings-ListaNegra-Fargate.postman_environment.json`
      (y la colección `postman/DevopsKings-ListaNegra.postman_collection.json` si no la tiene).
   2. En **Environments** abra **ListaNegra - AWS Fargate (ALB)** y cambie `base_url` por
      `http://<DNS del ALB>`, **sin** `/` al final → **Save**. Luego selecciónelo como environment
      activo (selector arriba a la derecha).
   3. En la colección → **Run collection** → **Run**.

✅ Todas las pruebas del Runner pasan: POST 201, el duplicado 409, la validación 400, sin token 401, GET
200 con `blacklisted` verdadero y falso.

📸 `/health` en el navegador con la URL del ALB visible y el resumen del Runner de Postman.

**Con esto queda cubierto el 20% de Fargate:** configuración manual, despliegue manual y validación.

---

## Parte B – Pipeline de CI/CD (60%)

### B1. Crear el pipeline
1. **CodePipeline → Pipelines → Create pipeline**.
2. **Choose creation option:** **Build custom pipeline** → **Next**.
3. **Pipeline settings:**
   - **Pipeline name:** `listanegra-cd`.
   - **Execution mode:** Queued.
   - **Service role:** New service role (deje el nombre que propone) → **Next**.

### B2. Source
1. **Source provider:** **GitHub (via GitHub App)**.
2. **Connection:** `github-devopskings`.
3. **Repository name:** `cryptolucas/DevopsKings-listanegra` · **Default branch:** `main`.
4. **Output artifact format:** CodePipeline default.
5. **Trigger:** *Specify filter* → **Event type:** Push → **Filter type:** Branch → **Branches /
   Include:** `main`. Esto cumple "cada commit en master ejecuta el build".
6. **Next**.

### B3. Build (y creación del proyecto de CodeBuild)
1. **Build provider:** *Other build providers* → **AWS CodeBuild**.
2. Junto a *Project name*, clic en **Create project**. Se abre una ventana nueva:
   - **Project name:** `listanegra-build-cd`.
   - **Environment:**
     - Provisioning model: **On-demand** · Environment image: **Managed image**.
     - **Compute: EC2** (no Lambda: Lambda no puede construir imágenes Docker).
     - Si aparece *Running mode*, deje **Container**.
     - Operating system: **Amazon Linux** · Runtime(s): **Standard** ·
       Image: **`aws/codebuild/amazonlinux-x86_64-standard:5.0`** · Image version: la más reciente.
     - Service role: **New service role**. Anote el nombre que propone:
       `codebuild-listanegra-build-cd-service-role`.
     - Despliegue **Additional configuration**: ✅ **Privileged** (*Enable this flag if you want to
       build Docker images…*). Sin esto, `docker build` falla. Compute: 3 GB de memoria, 2 vCPU.
   - **Buildspec:** **Use a buildspec file** → **Buildspec name:** `buildspec-cd.yml`. Si lo deja
     vacío, usa el `buildspec.yml` de la Entrega 2, que no construye imágenes.
   - **Logs:** CloudWatch logs activado.
   - **Continue to CodePipeline**. La ventana se cierra.
3. De vuelta en el asistente: **Build type:** Single build · **Input artifacts:** SourceArtifact.
   El artefacto de salida se llama `BuildArtifact`.
4. **No dé Next todavía.** Haga el paso B4 en otra pestaña.

### B4. Permiso de ECR para CodeBuild
El pipeline arranca apenas se crea, así que este permiso debe estar antes:
1. En **otra pestaña**: **IAM → Roles** → `codebuild-listanegra-build-cd-service-role`.
2. **Add permissions → Attach policies** → busque y marque `AmazonEC2ContainerRegistryPowerUser` →
   **Add permissions**.
3. Vuelva a la pestaña del pipeline → **Next**.

### B5. Test
**Skip test stage** → confirme **Skip**. Las pruebas ya corren dentro del Build.

### B6. Deploy
1. **Deploy provider:** **Amazon ECS (Blue/Green)** · **Region:** US East (N. Virginia).
2. **Input artifacts:** `BuildArtifact`.
3. **AWS CodeDeploy application name:** `listanegra-codedeploy` · **AWS CodeDeploy deployment group:**
   `listanegra-dg`.
4. **Amazon ECS task definition:** `BuildArtifact` · ruta `taskdef.json`.
5. **AWS CodeDeploy AppSpec file:** `BuildArtifact` · ruta `appspec.yaml`.
6. **Dynamically update task definition image:** **Input artifact with image details:**
   `BuildArtifact` · **Placeholder text in the task definition:** `IMAGE1_NAME` (sin `<` `>`).
7. **Next** → revise el resumen → **Create pipeline**.

📸 Antes de crear, tome captura del resumen (*Review*): muestra las tres etapas y su configuración.

### B7. Seguir la primera ejecución
El pipeline arranca solo con el último commit de `main` (unos 8 minutos en total).

1. **Source** → Succeeded en segundos.
2. **Build** (3–4 min) → clic en **View details → View in CodeBuild** → pestaña **Build logs**:
   - INSTALL: instala las dependencias.
   - PRE_BUILD: `Login Succeeded` en ECR.
   - BUILD: `23 passed` y luego `docker build`.
   - POST_BUILD: `docker push` y el contenido de `imageDetail.json`.
3. **Deploy** → clic en **Details** → abre el despliegue en CodeDeploy. Ahí se ve el blue/green:
   - Step 1: *Deploying replacement task set* (tarea nueva en `tg-listanegra-green`).
   - Step 2: *Test traffic route setup*.
   - Step 3: *Rerouting production traffic to replacement task set* (barra Original 0% / Replacement 100%).
   - Step 4: *Wait 5 minutes* (las dos versiones conviven).
   - Step 5: *Terminate original task set*.
4. Al final, las tres etapas quedan en verde.

✅ Comprobaciones:
- **ECR:** hay una imagen nueva etiquetada con los primeros 7 caracteres del commit (y `latest`).
- **ECS → Task definitions → listanegra:** existe la revisión `listanegra:2`, creada por el pipeline.
- **EC2 → Load Balancers → alb-listanegra → Listeners:** el listener 80 ahora envía a
  `tg-listanegra-green`. En el siguiente despliegue volverá a `blue`; así funciona el blue/green.
- `/health` sigue respondiendo `1.0.5`, porque el código no cambió.

📸 El pipeline completo en verde, las fases de CodeBuild en *Succeeded*, la pantalla de CodeDeploy con
los 5 pasos y el reporte de pruebas (CodeBuild → **Report groups** → 23/23).

### B8. Apagar el pipeline de la Entrega 2
`listanegra-ci` también corre con cada push y duplica builds y capturas.
1. **CodePipeline → listanegra-ci**.
2. En la flecha entre **Source** y **Build**, clic en **Disable transition** → razón:
   `Entrega 3 usa listanegra-cd` → **Disable**.

Se puede volver a habilitar con **Enable transition**.

📸 La configuración del pipeline: **Edit** en `listanegra-cd` muestra las tres etapas, y en la etapa
Source se ve el trigger de `main`.

**Con esto queda cubierto el 60% del pipeline:** archivos de configuración en el repositorio, build
automático con imagen en cada commit, y despliegue automático en Fargate después del CI exitoso.

---

## Parte C – Las tres ejecuciones del documento (20%)

Para cada ejecución: haga el cambio, haga push, observe, tome las capturas y anote los hallazgos.
En una terminal aparte puede dejar el monitor de la Entrega 1 contra el ALB; muestra cada segundo qué
versión y qué tarea responde:
```powershell
.\scripts\monitor_deploy.ps1 -Url http://<DNS del ALB> -Target <versión esperada>
```

### C1. CI fallido (4%)
**Cambio:** un error que las pruebas unitarias detectan.
1. En `src/resources/blacklist.py`, línea 87 (el `return` final de `post()`), cambie `}, 201` por `}, 200`.
2. Haga commit y push:
   ```powershell
   git commit -am "ci: prueba de CI fallido (POST responde 200)"
   git push
   ```
3. Observe en CodePipeline: **Build** queda en rojo y **Deploy** no se ejecuta.

**Qué revisar:**
- CodeBuild → **Phase details:** BUILD *Failed*, POST_BUILD *Failed*.
- **Build logs:** `3 failed, 20 passed`, las líneas `FAILED tests/test_blacklists.py::...` con
  `assert 200 == 201`, y el mensaje `Pruebas o construccion fallidas: no se publica imagen ni se despliega.`
- **Report groups:** 20 superadas y 3 fallidas.
- **ECR:** no hay imagen con la etiqueta de este commit.
- `/health` sigue en `1.0.5`: producción no se tocó.

**Hallazgos para el documento:** el error se detectó en unos 3 minutos, antes de construir la
imagen; el pipeline se detuvo y no publicó ni desplegó nada; la ejecución identifica el commit exacto
y las pruebas que fallaron.

📸 El pipeline con Build en rojo y Deploy sin ejecutar, Phase details, los FAILED en el log, el
reporte 20/23 y ECR sin imagen nueva.

### C2. CI exitoso + CD exitoso (8%)
**Cambio:** se corrige el error de C1 y se publica una versión nueva, en un solo push.
1. Revierta el commit de C1 y suba la versión:
   ```powershell
   git revert HEAD --no-edit
   ```
2. En `src/version.py` cambie `APP_VERSION = "1.0.5"` por `APP_VERSION = "2.0.0"`.
3. Haga commit y push:
   ```powershell
   git commit -am "v2.0.0: despliegue continuo en Fargate"
   git push
   ```
4. Arranque el monitor: `.\scripts\monitor_deploy.ps1 -Url http://<DNS del ALB> -Target 2.0.0`.
5. Siga el pipeline como en B7.

**Qué revisar:**
- Las tres etapas en verde y **23 passed** en el Build.
- **ECR:** imagen nueva con la etiqueta del commit.
- **ECS:** nueva revisión de la taskdef. En el servicio, durante el despliegue, se ven dos *task
  sets* (el original y el de reemplazo).
- **CodeDeploy:** los 5 pasos, con el tráfico pasando de Original a Replacement.
- **Monitor:** las respuestas cambian de `1.0.5` a `2.0.0` (y cambia el `host`, porque responde otra
  tarea) sin errores 5xx.
- `/health` responde `"version": "2.0.0"`.

**Hallazgos para el documento:** tiempo total del commit a producción; cero caídas durante el cambio
(monitor); la versión anterior siguió disponible 5 minutos para un rollback; el despliegue no tuvo
ningún paso manual.

📸 El pipeline en verde con el commit `v2.0.0`, CodeDeploy con el tráfico en 100% Replacement, ECR con
la imagen nueva, la revisión nueva de la taskdef, `/health` con `2.0.0` y el resumen del monitor.

### C3. CI exitoso + CD fallido (8%)
**Cambio:** un error de configuración del despliegue que las pruebas unitarias no pueden detectar.
1. En `deploy/appspec.yaml` cambie `ContainerPort: 8000` por `ContainerPort: 9000`.
2. En `src/version.py` ponga `APP_VERSION = "2.0.1"`. Así, si se ve `2.0.0` después, queda probado que
   la versión rota nunca llegó a producción.
3. Haga commit y push:
   ```powershell
   git commit -am "cd: prueba de despliegue fallido (puerto del AppSpec incorrecto)"
   git push
   ```

**Qué revisar:**
- **Build** en verde: 23 pruebas superadas e imagen publicada en ECR (el CI sí pasó).
- **Deploy** en rojo. En CodeDeploy, el paso 1 (*Deploying replacement task set*) falla: ECS rechaza
  la tarea nueva porque el contenedor `listanegra` no expone el puerto 9000. Copie el mensaje de error
  exacto en el documento.
- Si aparece un despliegue de *rollback*, es el rollback automático del paso A11.
- El listener del ALB sigue apuntando al mismo target group y `/health` sigue respondiendo `2.0.0`.

**Hallazgos para el documento:** el CI no puede detectar errores de configuración del despliegue; el
blue/green protegió producción porque el tráfico nunca se movió a la versión rota; el pipeline
señala la etapa y el error exactos.

> Si el despliegue no falla en el paso 1 sino que se queda esperando, deténgalo en CodeDeploy
> (**Stop deployment** con rollback) y use la variante: en `deploy/appspec.yaml` deje el puerto en
> `8000` y cambie `ContainerName` por `listanegra-v2`, un nombre que no existe en la definición de tarea.

📸 El pipeline con Build en verde y Deploy en rojo, CodeDeploy con el paso fallido y el mensaje de
error, ECR con la imagen `2.0.1` publicada y `/health` mostrando `2.0.0`.

**Dejar `main` sano:** devuelva el puerto a `8000` en `deploy/appspec.yaml` y haga push:
```powershell
git commit -am "cd: corrige el puerto del AppSpec"
git push
```
El pipeline despliega `2.0.1` y prueba que, corregida la configuración, todo vuelve a funcionar.

---

## Parte D – Documento y video

### Documento: "Proyecto 1 entrega 3 – Documento.pdf"
1. Portada: integrantes, link del repositorio y URL del ALB.
2. Arquitectura: los dos diagramas del inicio y los archivos de configuración del repositorio.
3. Configuración de Fargate: capturas de la Parte A.
4. Configuración del pipeline: capturas de la Parte B.
5. C1 – CI fallido: capturas y hallazgos.
6. C2 – CI y CD exitosos: capturas y hallazgos.
7. C3 – CI exitoso y CD fallido: capturas y hallazgos.
8. Conclusiones.

### Video (máximo 10 minutos; lo que pase del minuto 10 no se califica)
El enunciado pide mostrar evidencias, no leer el PDF. Un guion que cabe en 10 minutos:

| Minuto | Qué mostrar |
|---|---|
| 0:00–0:30 | Integrantes y diagrama de la arquitectura |
| 0:30–2:00 | Repositorio en GitHub: `Dockerfile`, `buildspec-cd.yml` (pruebas → imagen → ECR), `taskdef.json`, `appspec.yaml` |
| 2:00–4:00 | Consola de AWS: ECR, Parameter Store, cluster, servicio (controlador CodeDeploy), task definition, ALB y target groups, deployment group |
| 4:00–5:00 | Postman contra el ALB: correr la colección y explicar los escenarios de prueba |
| 5:00–7:30 | Configuración del pipeline y un push en vivo: Source → Build (pruebas, imagen) → Deploy (blue/green en CodeDeploy) |
| 7:30–9:30 | Historial del pipeline: C1 (log de pruebas fallidas), C3 (error de CodeDeploy) |
| 9:30–10:00 | Conclusiones |

Como el pipeline tarda unos 8 minutos, haga el push al empezar la grabación (o corte el video) para
mostrar el despliegue sin tiempos muertos.

---

## Problemas frecuentes

| Dónde se ve | Síntoma | Solución |
|---|---|---|
| Script A10 | `ERROR: no existe ...` | Haga el paso que indica el mensaje y vuelva a correr el script |
| CodeBuild, fase PRE_BUILD | `AccessDenied ... ecr:GetAuthorizationToken` | Falta `AmazonEC2ContainerRegistryPowerUser` en el rol de CodeBuild (B4). Después: **Release change** en el pipeline |
| CodeBuild, fase BUILD | `Cannot connect to the Docker daemon` | Falta **Privileged**: CodeBuild → `listanegra-build-cd` → Edit → Environment |
| CodeBuild, fase BUILD | Corre las pruebas pero no hace `docker build` | El proyecto usa `buildspec.yml`: ponga `buildspec-cd.yml` en Edit → Buildspec |
| ECS → tarea detenida (*Stopped reason*) | `ResourceInitializationError: unable to pull secrets` | Falta `listanegra-ssm` en `ecsTaskExecutionRole` o un parámetro tiene otro nombre (A2, A3) |
| ECS → tarea detenida | `... log group does not exist` | Cree `/ecs/listanegra` (A4) |
| ECS → tarea detenida | `CannotPullContainerError` | La imagen no existe en ECR o la tarea no tiene IP pública |
| Target *unhealthy*, `/health` = 503 | `database: down` | Falta la regla 5432 desde `sg-listanegra-tasks` en el SG de la RDS, o los `DB_*` están mal. Vea el log de la tarea en CloudWatch |
| Target *unhealthy*, *Request timed out* | El ALB no llega al contenedor | `sg-listanegra-tasks` debe permitir 8000 desde `sg-listanegra-alb` |
| CodeDeploy, al crear el deployment group | El servicio no aparece o da error de controlador | El servicio se creó desde la consola: bórrelo (*Force delete*) y corra el script de A10 |
| CodePipeline, Deploy | `not authorized to perform: iam:PassRole` | Rol del pipeline → política inline con `iam:PassRole` sobre `arn:aws:iam::*:role/ecsTaskExecutionRole` |
| CodePipeline, Deploy | Queda *In progress* casi una hora | *Original revision termination* quedó en 1 hora: edite el deployment group (A11) |

Para ver el motivo de una tarea detenida: **ECS → listanegra-cluster → Tasks** → filtro
**Stopped** → abra la tarea → campo **Stopped reason**. Los logs de la aplicación están en
**CloudWatch → Log groups → /ecs/listanegra**.

---

## Costos y limpieza

El balanceador, las tareas de Fargate y sus IP públicas cobran por hora mientras existan, del orden de
1 a 2 USD al día con 1 tarea. CodeBuild, CodePipeline y ECR cuestan centavos con este uso.

- El enunciado pide la **aplicación en ejecución accesible vía Postman**: no borre nada hasta que el
  tutor califique.
- Si el ambiente de Elastic Beanstalk de la Entrega 1 sigue encendido y ya no lo necesitan,
  termínelo. La RDS es independiente y no se borra.
- Al terminar el curso, en este orden: pipeline `listanegra-cd`, aplicación de CodeDeploy, servicio
  de ECS (*Force delete*), cluster, balanceador, los dos target groups, imágenes y repositorio de ECR,
  log group y parámetros.
