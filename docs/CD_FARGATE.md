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
| `buildspec.yml` | **Sin cambios**: sigue siendo el pipeline de CI de la Entrega 2 |

Los secretos (contraseña de la base, token) **no están en el repositorio**: la tarea los lee de
AWS Systems Manager Parameter Store al arrancar.

> **CodeCommit:** el enunciado pide el código en AWS CodeCommit, pero AWS cerró CodeCommit a
> clientes nuevos en julio de 2024 y la cuenta del grupo no puede crear repositorios. Se mantiene
> GitHub como fuente (conectado por CodeConnections, igual que en la Entrega 2). Conviene
> confirmarlo con el tutor y dejarlo explicado en el documento.

---

## Parte A – Configuración manual de Fargate (20%)

### A1. Repositorio de imágenes (ECR)
ECR → **Create repository** → Private → nombre `listanegra` → Create.

### A2. Parámetros (secretos)
Systems Manager → **Parameter Store → Create parameter**, uno por fila:

| Nombre | Tipo | Valor |
|---|---|---|
| `/listanegra/DB_HOST` | String | endpoint de la RDS (sin `:5432`) |
| `/listanegra/DB_NAME` | String | `blacklistdb` |
| `/listanegra/DB_USER` | String | usuario de la RDS |
| `/listanegra/DB_PASSWORD` | **SecureString** | contraseña de la RDS |
| `/listanegra/STATIC_TOKEN` | **SecureString** | el token que usa Postman |
| `/listanegra/JWT_SECRET_KEY` | **SecureString** | una cadena larga aleatoria |

### A3. Roles de IAM
1. **`ecsTaskExecutionRole`** (si no existe: IAM → Roles → Create role → *Elastic Container
   Service Task* → política `AmazonECSTaskExecutionRolePolicy`). Agréguele una política en línea
   para leer los parámetros:
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
2. **`ecsCodeDeployRole`**: IAM → Create role → *CodeDeploy* → caso de uso **CodeDeploy - ECS** →
   política `AWSCodeDeployRoleForECS`.

### A4. Logs
CloudWatch → Log groups → **Create log group** → `/ecs/listanegra`.

### A5. Red (security groups)
EC2 → Security Groups:
- `sg-listanegra-alb`: entrada **HTTP 80** desde `0.0.0.0/0` (y **8080** si va a usar listener de prueba).
- `sg-listanegra-tasks`: entrada **TCP 8000** solo desde `sg-listanegra-alb`.
- En el security group de la **RDS**: agregue entrada **PostgreSQL 5432** desde `sg-listanegra-tasks`.

### A6. Balanceador y target groups
EC2 → **Target Groups → Create** (dos veces):
- Tipo **IP addresses**, protocolo HTTP, puerto **8000**, VPC por defecto.
- Health check path **`/health`**.
- Nombres: `tg-listanegra-blue` y `tg-listanegra-green` (no registre targets).

EC2 → **Load Balancers → Create → Application Load Balancer**:
- `alb-listanegra`, internet-facing, al menos 2 subredes públicas, security group `sg-listanegra-alb`.
- Listener **HTTP:80 → `tg-listanegra-blue`**.

### A7. Primera imagen (despliegue manual)
Desde su computador, con Docker y la AWS CLI configurada (`aws configure --profile devopskings`):
```powershell
$acct = aws sts get-caller-identity --query Account --output text --profile devopskings
$reg  = "$acct.dkr.ecr.us-east-1.amazonaws.com"
aws ecr get-login-password --region us-east-1 --profile devopskings | docker login --username AWS --password-stdin $reg
docker build -t "$reg/listanegra:manual" .
docker push "$reg/listanegra:manual"
```

### A8. Cluster, definición de tarea y servicio
1. ECS → **Clusters → Create** → `listanegra-cluster` → infraestructura **AWS Fargate**.
2. ECS → **Task definitions → Create new with JSON** → pegue `deploy/taskdef.json` reemplazando
   `<ACCOUNT_ID>`, `<REGION>` (`us-east-1`) e `<IMAGE1_NAME>` (la imagen `:manual` del paso A7).
3. Cluster → **Services → Create**:
   - Launch type **FARGATE**, task definition `listanegra`, service name `listanegra-svc`,
     desired tasks **1** (o 2 si quieren mostrar varias tareas).
   - **Deployment options → Deployment type: Blue/green deployment (powered by AWS CodeDeploy)**,
     deployment configuration `CodeDeployDefault.ECSAllAtOnce`, service role `ecsCodeDeployRole`.
   - Networking: VPC por defecto, subredes públicas, security group `sg-listanegra-tasks`,
     **Public IP: ON** (para que la tarea pueda descargar la imagen de ECR sin NAT).
   - Load balancing: `alb-listanegra`, contenedor `listanegra 8000`, listener 80,
     target group 1 `tg-listanegra-blue`, target group 2 `tg-listanegra-green`.
   - Esto crea en CodeDeploy una aplicación y un deployment group (anote sus nombres).
4. CodeDeploy → Applications → el deployment group → **Edit**: active **Roll back when a deployment
   fails** y ponga *Original revision termination* en 0–5 minutos para que los despliegues no tarden.

### A9. Validar
`http://<DNS del ALB>/health` debe responder `status: ok` y `database: up`. Cambie `base_url` del
environment de Postman al DNS del ALB y corra la colección.

📸 Capturas: ECR con la imagen, cluster, servicio con la tarea en RUNNING, target group con el target
*healthy*, `/health` en el navegador y el Runner de Postman.

---

## Parte B – Pipeline de CI/CD (60%)

### B1. Proyecto de CodeBuild para CD
CodeBuild → **Create build project** → `listanegra-build-cd`:
- Source: (se configura desde el pipeline).
- Environment: On-demand, **EC2**, Amazon Linux, `aws/codebuild/amazonlinux-x86_64-standard:5.0`.
- **Privileged: activado** (necesario para `docker build`).
- Buildspec: **Use a buildspec file** → nombre **`buildspec-cd.yml`**.
- Al rol de servicio que crea la consola agréguele la política **`AmazonEC2ContainerRegistryPowerUser`**.

### B2. Pipeline
CodePipeline → **Create pipeline** → `listanegra-cd`:
1. **Source:** GitHub (via GitHub App), conexión existente, repo `cryptolucas/DevopsKings-listanegra`,
   rama `main`, trigger en push a `main`.
2. **Build:** AWS CodeBuild → `listanegra-build-cd`. Output artifact: `BuildArtifact`.
3. **Deploy:** provider **Amazon ECS (Blue/Green)**:
   - CodeDeploy application y deployment group: los creados en A8.
   - Amazon ECS task definition: `BuildArtifact` → `taskdef.json`.
   - AWS CodeDeploy AppSpec file: `BuildArtifact` → `appspec.yaml`.
   - Dynamically update task definition image: input artifact `BuildArtifact`,
     placeholder **`IMAGE1_NAME`**.

> El pipeline de la Entrega 2 también se dispara con cada push a `main`. Pueden dejarlo (solo corre
> pruebas) o desactivar su trigger para no confundir las capturas.

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

📸 Pipeline con Build en rojo y Deploy sin ejecutar, Build logs con los FAILED, Reports 20/23.

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
Build pasa (23 pruebas OK, imagen publicada), pero **Deploy falla** en CodeDeploy y la versión
anterior sigue atendiendo. Después: `git revert HEAD --no-edit` y `git push`.

> Si ese error no falla rápido, la alternativa es romper el arranque del contenedor: en
> `deploy/taskdef.json` cambie la ruta del `healthCheck` a `/no-existe`. Las tareas nuevas nunca
> quedan sanas y CodeDeploy hace rollback (tarda más).

📸 Pipeline con Build en verde y Deploy en rojo, CodeDeploy con el error y el rollback, `/health`
mostrando que la versión anterior siguió en línea.

---

## Costos

El balanceador y las tareas de Fargate cobran por hora mientras existan (en total del orden de
1 a 2 USD al día con 1 tarea, contando las IP públicas). Hagan las ejecuciones y el video en los mismos días y luego:
servicio de ECS a 0 tareas o borrado, balanceador y target groups borrados, imágenes de ECR
borradas.
