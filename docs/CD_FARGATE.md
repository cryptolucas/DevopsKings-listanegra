# Entrega 3 – Entrega continua (CD) en AWS Fargate

Cada commit en `main` ejecuta las pruebas, construye la imagen Docker, la publica en Amazon ECR y la
despliega automáticamente en AWS Fargate con AWS CodeDeploy (blue/green). Todo en **us-east-1**.

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

## Archivos en el repositorio

| Archivo | Para qué |
|---|---|
| `Dockerfile` | Imagen del microservicio: Python 3.11 slim + gunicorn en el puerto 8000, usuario sin privilegios |
| `.dockerignore` | Deja fuera de la imagen las pruebas, docs, `.git`, etc. |
| `buildspec-cd.yml` | CodeBuild del pipeline de CD: pruebas → imagen → push a ECR → archivos para CodeDeploy |
| `deploy/taskdef.json` | Definición de tarea de Fargate (0.5 vCPU, 1 GB). `<IMAGE1_NAME>` lo llena CodePipeline; `<ACCOUNT_ID>` y `<REGION>` los llena el buildspec |
| `deploy/appspec.yaml` | Instrucciones de CodeDeploy: qué contenedor y puerto conectar al balanceador |
| `scripts/crear_servicio_ecs.sh` | Crea el servicio de ECS con el controlador `CODE_DEPLOY` (paso A9). Se corre una sola vez en CloudShell |
| `postman/DevopsKings-ListaNegra-Fargate.postman_environment.json` | Environment de Postman apuntando al balanceador |
| `buildspec.yml` | **Sin cambios**: sigue siendo el pipeline de CI de la Entrega 2 |

Los secretos (contraseña de la base, token) **no están en el repositorio**: la tarea los lee de
AWS Systems Manager Parameter Store al arrancar.

## Antes de empezar

- **Cuenta y región:** la misma cuenta de la Entrega 2 (allí está la conexión `github-devopskings`),
  región **us-east-1 (N. Virginia)**. Revise la región en la esquina superior derecha en cada servicio.
- **Base de datos:** la RDS PostgreSQL de la Entrega 1 debe existir en esta cuenta, en la VPC por
  defecto. Si no existe, créela con la *Fase 1* de [`DESPLIEGUE_AWS.md`](DESPLIEGUE_AWS.md) (solo la
  parte de RDS) y anote endpoint, usuario y contraseña.
- **AWS Academy (Learner Lab):** si usan una cuenta de Academy no pueden crear roles. Use `LabRole` en
  cada lugar donde esta guía crea un rol, y en `deploy/taskdef.json` cambie `ecsTaskExecutionRole` por
  `LabRole`.
- **Rama:** el enunciado habla de `master`; en este repositorio la rama principal es `main`.
- **GitHub:** el paso A7 clona el repositorio en CloudShell, así que lo que haya en `main` en ese
  momento es lo que se usa.

> **No cree el servicio de ECS desde la consola.** El asistente *Create service* de ECS ahora ofrece
> el blue/green **nativo de ECS**. Ese servicio no se puede conectar a CodeDeploy, y el enunciado exige
> CodeDeploy. El servicio se crea con el script del paso A9, que usa el controlador `CODE_DEPLOY`.
> Todo lo demás se hace en la consola.

---

## Parte A – Configuración manual de Fargate (20%)

### A1. Repositorio de imágenes (ECR)
ECR → **Create repository**:
- Visibility: **Private**, nombre `listanegra`.
- Image tag mutability: **Mutable** (cada build vuelve a publicar la etiqueta `latest`).
- **Create**.

### A2. Parámetros (secretos)
Systems Manager → **Parameter Store → Create parameter**, uno por fila (tier *Standard*):

| Nombre | Tipo | Valor |
|---|---|---|
| `/listanegra/DB_HOST` | String | endpoint de la RDS (sin `:5432`) |
| `/listanegra/DB_NAME` | String | `blacklistdb` |
| `/listanegra/DB_USER` | String | usuario de la RDS |
| `/listanegra/DB_PASSWORD` | **SecureString** | contraseña de la RDS |
| `/listanegra/STATIC_TOKEN` | **SecureString** | `devopskings-2026-token-listanegra` (el que usa Postman) |
| `/listanegra/JWT_SECRET_KEY` | **SecureString** | una cadena larga aleatoria |

En los SecureString deje la llave KMS por defecto (`alias/aws/ssm`).

### A3. Roles de IAM
1. **`ecsTaskExecutionRole`**: lo usa ECS para descargar la imagen, leer los parámetros y escribir logs.
   - Si ya existe en IAM → Roles, ábralo. Si no: IAM → Roles → **Create role** → *AWS service* →
     **Elastic Container Service** → caso de uso **Elastic Container Service Task** → política
     `AmazonECSTaskExecutionRolePolicy` → nombre `ecsTaskExecutionRole` → Create.
   - En el rol: **Add permissions → Create inline policy → JSON**, pegue esto y nómbrela `listanegra-ssm`:
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
2. **`ecsCodeDeployRole`**: lo usa CodeDeploy para crear tareas y mover el tráfico del balanceador.
   IAM → Roles → **Create role** → *AWS service* → **CodeDeploy** → caso de uso **CodeDeploy - ECS**
   (trae la política `AWSCodeDeployRoleForECS`) → nombre `ecsCodeDeployRole` → Create.

### A4. Logs
CloudWatch → Log groups → **Create log group** → nombre `/ecs/listanegra` (retención: 1 semana).
La tarea no puede crearlo sola: si no existe, no arranca.

### A5. Security groups
EC2 → **Security Groups → Create security group**, ambos en la VPC por defecto:
- `sg-listanegra-alb`: inbound **HTTP 80** desde `Anywhere-IPv4` (`0.0.0.0/0`).
- `sg-listanegra-tasks`: inbound **Custom TCP 8000**, source *Custom* → `sg-listanegra-alb`.

Y en el security group de la **RDS** (`sg-listanegra-rds` en la Entrega 1) → **Edit inbound rules** →
agregue **PostgreSQL 5432** con source `sg-listanegra-tasks`.

### A6. Target groups y balanceador
EC2 → **Target Groups → Create target group** (dos veces, uno por color):
- Target type **IP addresses**, nombre `tg-listanegra-blue` (y luego `tg-listanegra-green`).
- Protocol **HTTP**, port **8000**, VPC por defecto, protocol version HTTP1.
- Health check path **`/health`**. En *Advanced health check settings*: healthy threshold **2**,
  unhealthy threshold **2**, timeout **5**, interval **10**, success codes `200`. Así un despliegue
  tarda unos 3 minutos en vez de 10.
- **Next** → no registre targets (borre cualquier IP sugerida) → **Create target group**.
- Luego, en cada target group → pestaña **Attributes → Edit** → *Deregistration delay* **30** segundos.

EC2 → **Load Balancers → Create load balancer → Application Load Balancer**:
- Nombre `alb-listanegra`, *Internet-facing*, IPv4.
- VPC por defecto, zonas **us-east-1a** y **us-east-1b** (la subred por defecto de cada una).
  El script del paso A9 pone las tareas en estas mismas subredes.
- Security groups: quite `default` y deje solo `sg-listanegra-alb`.
- Listener **HTTP:80** → *Forward to* `tg-listanegra-blue`.
- **Create**. Anote el **DNS name** (`alb-listanegra-xxxx.us-east-1.elb.amazonaws.com`).

### A7. Primera imagen (despliegue manual)
Abra **CloudShell** (ícono `>_` en la barra superior de la consola, con la región en us-east-1) y ejecute:
```bash
git clone https://github.com/cryptolucas/DevopsKings-listanegra.git   # si ya existe: cd ... && git pull
cd DevopsKings-listanegra
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGISTRY=$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY
docker build -t $REGISTRY/listanegra:manual .
docker push $REGISTRY/listanegra:manual
```
En ECR → `listanegra` debe aparecer la etiqueta `manual`.

### A8. Cluster
ECS → **Clusters → Create cluster** → nombre `listanegra-cluster` → Infrastructure: solo
**AWS Fargate (serverless)** → **Create** (tarda un minuto).

### A9. Definición de tarea y servicio (script)
En la misma sesión de CloudShell, desde la carpeta del repositorio:
```bash
bash scripts/crear_servicio_ecs.sh
```
El script:
1. Verifica que existan la imagen, el cluster, el balanceador, el target group azul y el security group.
2. Registra `deploy/taskdef.json` (revisión `listanegra:1`) con la imagen `:manual`.
3. Crea el servicio `listanegra-svc`: Fargate, 1 tarea, controlador **CODE_DEPLOY**, subredes del
   balanceador, IP pública (para descargar la imagen sin NAT) y `tg-listanegra-blue`.
4. Espera a que la tarea quede *healthy* en el target group y llama `/health`.

Si falla, el mensaje dice qué paso falta. Si la tarea no queda sana, vea la tabla de
[problemas frecuentes](#problemas-frecuentes).

### A10. Aplicación y deployment group de CodeDeploy
CodeDeploy → **Applications → Create application** → nombre `listanegra-codedeploy`, compute platform
**Amazon ECS** → Create. Dentro de la aplicación → **Create deployment group**:

| Campo | Valor |
|---|---|
| Deployment group name | `listanegra-dg` |
| Service role | `ecsCodeDeployRole` |
| ECS cluster name / service name | `listanegra-cluster` / `listanegra-svc` |
| Load balancer | `alb-listanegra` |
| Production listener port | `HTTP: 80` |
| Test listener port | (vacío) |
| Target group 1 / 2 | `tg-listanegra-blue` / `tg-listanegra-green` |
| Traffic rerouting | **Reroute traffic immediately** |
| Deployment configuration | `CodeDeployDefault.ECSAllAtOnce` |
| Original revision termination | 0 días, 0 horas, **5 minutos** |
| Advanced → Rollbacks | ✅ **Roll back when a deployment fails** |

> CodePipeline espera a que se apaguen las tareas viejas para marcar el despliegue como terminado.
> Si deja la terminación en 1 hora, cada ejecución del pipeline tarda una hora.

### A11. Validar
- Navegador: `http://<DNS del ALB>/health` → `status: ok`, `database: up`, `version: 1.0.5`.
- Postman: importe `postman/DevopsKings-ListaNegra-Fargate.postman_environment.json`, cambie
  `base_url` por `http://<DNS del ALB>` (sin `/` al final) y corra la colección con el Runner.

📸 Capturas: ECR con la imagen `manual`, Parameter Store, cluster, task definition `listanegra:1`,
servicio con la tarea en RUNNING, target group con el target *healthy*, deployment group de
CodeDeploy, `/health` en el navegador y el Runner de Postman.

---

## Parte B – Pipeline de CI/CD (60%)

CodePipeline → **Create pipeline → Build custom pipeline**:

1. **Pipeline settings:** nombre `listanegra-cd`, execution mode *Queued*, service role *New service role*.
2. **Source:** **GitHub (via GitHub App)** → conexión `github-devopskings` → repo
   `cryptolucas/DevopsKings-listanegra` → branch `main` → output artifact format *CodePipeline default*.
   Trigger: **Specify filter → Push → Branch → `main`**.
3. **Build:** *Other build providers* → **AWS CodeBuild** → **Create project** (se abre otra ventana):
   - Project name `listanegra-build-cd`.
   - Environment: *On-demand*, *Managed image*, compute **EC2** (Lambda no puede construir imágenes
     Docker), Amazon Linux, Standard, imagen **`aws/codebuild/amazonlinux-x86_64-standard:5.0`**.
   - Service role: *New service role* (anote el nombre, `codebuild-listanegra-build-cd-service-role`).
   - *Additional configuration*: ✅ **Privileged** (*Enable this flag if you want to build Docker
     images…*). Cómputo: 3 GB / 2 vCPU.
   - Buildspec: **Use a buildspec file** → nombre **`buildspec-cd.yml`**.
   - Logs: CloudWatch activado → **Continue to CodePipeline**.

   **Antes de seguir con el asistente**, en otra pestaña: IAM → Roles →
   `codebuild-listanegra-build-cd-service-role` → **Add permissions → Attach policies** →
   `AmazonEC2ContainerRegistryPowerUser`. Sin esta política el build falla al hacer login en ECR.
4. **Test:** *Skip test stage*.
5. **Deploy:** provider **Amazon ECS (Blue/Green)**, región us-east-1:
   - AWS CodeDeploy application name: `listanegra-codedeploy`; deployment group: `listanegra-dg`.
   - Amazon ECS task definition: `BuildArtifact` → `taskdef.json`.
   - AWS CodeDeploy AppSpec file: `BuildArtifact` → `appspec.yaml`.
   - *Dynamically update task definition image*: input artifact `BuildArtifact`, placeholder
     **`IMAGE1_NAME`**.
6. **Create pipeline.** Arranca solo con el último commit de `main`: Source, Build y Deploy deben
   terminar en verde (unos 8 minutos, incluidos los 5 de espera para apagar las tareas viejas). Es el
   primer despliegue automático: en ECS aparece la revisión `listanegra:2` y en ECR una imagen con la
   etiqueta del commit.

> El pipeline `listanegra-ci` de la Entrega 2 también corre con cada push. Para no duplicar builds ni
> confundir las capturas: CodePipeline → `listanegra-ci` → entre Source y Build, **Disable transition**
> (se puede volver a habilitar).

📸 Capturas: configuración del proyecto de CodeBuild (imagen, *Privileged*, buildspec), las tres etapas
del pipeline, la configuración de la acción de Deploy y el trigger de `main`.

---

## Parte C – Las tres ejecuciones del documento (20%)

Puede dejar corriendo el monitor de la Entrega 1 contra el ALB para ver el cambio de versión:
`.\scripts\monitor_deploy.ps1 -Url http://<DNS del ALB> -Target <versión>`.

### C1. CI fallido (4%)
```powershell
# src/resources/blacklist.py: en el return final de post(), cambie 201 por 200
git commit -am "ci: prueba de CI fallido (POST responde 200)"
git push
```
Falla en **Build**: 3 pruebas fallan, no se publica imagen y **Deploy no se ejecuta**.
Después: `git revert HEAD --no-edit` y `git push`.

📸 Pipeline con Build en rojo y Deploy sin ejecutar, Build logs con los FAILED, Reports 20/23, ECR sin
imagen nueva.

### C2. CI exitoso + CD exitoso (8%)
```powershell
# src/version.py: suba la versión, por ejemplo "2.0.0"
git commit -am "v2.0.0: despliegue continuo en Fargate"
git push
```
Build y Deploy en verde. `/health` responde la versión nueva.

📸 Pipeline completo en verde, CodeDeploy con los pasos del blue/green (reroute de tráfico),
ECR con la imagen etiquetada con el commit, ECS con la nueva revisión de la taskdef, `/health` con la
versión nueva.

### C3. CI exitoso + CD fallido (8%)
Error de configuración que las pruebas unitarias no pueden detectar: el AppSpec apunta a un puerto
que el contenedor no expone.
```powershell
# deploy/appspec.yaml: cambie ContainerPort: 8000 por ContainerPort: 9000
git commit -am "cd: prueba de despliegue fallido (puerto del AppSpec incorrecto)"
git push
```
Build pasa (23 pruebas OK, imagen publicada), pero **Deploy falla** en el primer paso de CodeDeploy
(*Deploying replacement task set*): ECS rechaza el task set porque el contenedor `listanegra` no tiene
el puerto 9000. La versión anterior sigue atendiendo. Después: `git revert HEAD --no-edit` y `git push`.

> Variante con el mismo efecto: en `deploy/appspec.yaml` cambie `ContainerName` por un nombre que no
> exista en la definición de tarea (por ejemplo `listanegra-v2`).

📸 Pipeline con Build en verde y Deploy en rojo, CodeDeploy con el error, ECR con la imagen nueva
publicada (CI sí pasó), `/health` mostrando que la versión anterior siguió en línea.

---

## Problemas frecuentes

| Dónde se ve | Síntoma | Solución |
|---|---|---|
| CodeBuild, fase PRE_BUILD | `AccessDenied ... ecr:GetAuthorizationToken` | Falta `AmazonEC2ContainerRegistryPowerUser` en el rol de CodeBuild (parte B, paso 3) |
| CodeBuild, fase BUILD | `Cannot connect to the Docker daemon` | El proyecto no tiene **Privileged** activado: CodeBuild → proyecto → Edit → Environment |
| ECS → tarea detenida | `ResourceInitializationError: unable to pull secrets` | Falta la política `listanegra-ssm` en `ecsTaskExecutionRole` o un parámetro tiene otro nombre (A2, A3) |
| ECS → tarea detenida | `... log group does not exist` | Cree `/ecs/listanegra` (A4) |
| ECS → tarea detenida | `CannotPullContainerError` | La imagen no existe en ECR o la tarea no tiene IP pública |
| Target group: *unhealthy*, `/health` = 503 | `database: down` | Falta la regla 5432 desde `sg-listanegra-tasks` en el SG de la RDS, o los parámetros `DB_*` están mal |
| Target group: *unhealthy*, *Request timed out* | El ALB no llega al contenedor | `sg-listanegra-tasks` debe permitir 8000 desde `sg-listanegra-alb` |
| CodeDeploy, al crear el deployment group | El servicio no aparece o da error de controlador | El servicio se creó desde la consola (blue/green nativo). Bórrelo y corra el script de A9 |
| CodePipeline, Deploy | `not authorized to perform: iam:PassRole` | Agregue al rol del pipeline una política inline con `iam:PassRole` sobre `ecsTaskExecutionRole` |
| CodePipeline, Deploy | Queda *In progress* casi una hora | *Original revision termination* quedó en 1 hora: edite el deployment group (A10) |

## Costos

El balanceador y las tareas de Fargate cobran por hora mientras existan (en total del orden de
1 a 2 USD al día con 1 tarea, contando las IP públicas). Hagan las ejecuciones y el video en los
mismos días y luego: servicio de ECS a 0 tareas o borrado, balanceador y target groups borrados,
imágenes de ECR borradas. Si el ambiente de Elastic Beanstalk de la Entrega 1 sigue encendido y ya no
lo necesitan, termínelo (la RDS es independiente y no se borra).

## Estructura sugerida de "Proyecto 1 entrega 3 – Documento.pdf"

1. Portada con los integrantes, link del repositorio y URL del ALB.
2. Arquitectura (los dos diagramas de arriba) y archivos de configuración del repositorio.
3. Configuración de Fargate (parte A, con sus capturas).
4. Configuración del pipeline (parte B, con sus capturas).
5. C1 – CI fallido: capturas y hallazgos.
6. C2 – CI y CD exitosos: capturas y hallazgos.
7. C3 – CI exitoso y CD fallido: capturas y hallazgos.
8. Conclusiones.

Video (máximo 10 minutos): consola de AWS con cada recurso de la parte A, el pipeline y su
configuración, un push en vivo que pase por las tres etapas, la colección de Postman contra el ALB,
y las tres ejecuciones de la parte C.
