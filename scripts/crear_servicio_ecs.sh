#!/usr/bin/env bash
###############################################################################
# Crea el servicio de ECS (Fargate) del microservicio con el controlador de
# despliegue CODE_DEPLOY, que es el que exige la accion "Amazon ECS
# (Blue/Green)" de CodePipeline.
#
# Por que un script y no la consola: el asistente "Create service" de la
# consola de ECS ahora ofrece el blue/green NATIVO de ECS (controlador ECS).
# Un servicio creado asi no se puede asociar a un deployment group de
# AWS CodeDeploy. El controlador CODE_DEPLOY solo se elige por API/CLI.
#
# Se ejecuta en AWS CloudShell (region us-east-1), desde la raiz del repo:
#   git clone https://github.com/cryptolucas/DevopsKings-listanegra.git
#   cd DevopsKings-listanegra
#   bash scripts/crear_servicio_ecs.sh
#
# Requisitos (docs/CD_FARGATE.md, pasos A1 a A9): imagen :manual en ECR,
# parametros en Parameter Store, ecsTaskExecutionRole, log group, security
# groups, target group azul, ALB con listener 80 y el cluster.
#
# Pasos:
#   1. Verifica que existan los recursos anteriores.
#   2. Registra deploy/taskdef.json con la imagen :manual.
#   3. Crea el servicio (deploymentController = CODE_DEPLOY).
#   4. Espera a que la tarea quede sana en el target group y prueba /health.
#
# Los nombres se pueden cambiar con variables de entorno, por ejemplo:
#   DESIRED_COUNT=2 bash scripts/crear_servicio_ecs.sh
###############################################################################
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CLUSTER="${CLUSTER:-listanegra-cluster}"
SERVICE="${SERVICE:-listanegra-svc}"
ECR_REPOSITORY="${ECR_REPOSITORY:-listanegra}"
IMAGE_TAG="${IMAGE_TAG:-manual}"
ALB_NAME="${ALB_NAME:-alb-listanegra}"
TG_BLUE="${TG_BLUE:-tg-listanegra-blue}"
SG_TASKS="${SG_TASKS:-sg-listanegra-tasks}"
DESIRED_COUNT="${DESIRED_COUNT:-1}"
# Deben coincidir con deploy/taskdef.json y deploy/appspec.yaml.
CONTAINER_NAME="listanegra"
CONTAINER_PORT=8000

export AWS_DEFAULT_REGION="$REGION"
export AWS_PAGER=""

fallar() { echo; echo "ERROR: $*" >&2; exit 1; }
paso() { echo; echo "==> $*"; }

[ -f deploy/taskdef.json ] || fallar "ejecute el script desde la raiz del repositorio."

# --- 1. Recursos previos ------------------------------------------------------
paso "Verificando los recursos en $REGION"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"
echo "    cuenta: $ACCOUNT_ID"

aws ecr describe-images --repository-name "$ECR_REPOSITORY" --image-ids imageTag="$IMAGE_TAG" >/dev/null 2>&1 \
  || fallar "no existe la imagen $IMAGE_URI. Haga el paso A8 (primera imagen)."
echo "    imagen: $IMAGE_URI"

CLUSTER_STATUS=$(aws ecs describe-clusters --clusters "$CLUSTER" --query 'clusters[0].status' --output text)
[ "$CLUSTER_STATUS" = "ACTIVE" ] || fallar "no existe el cluster $CLUSTER. Haga el paso A9."
echo "    cluster: $CLUSTER"

ALB_ARN=$(aws elbv2 describe-load-balancers --names "$ALB_NAME" \
  --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null) \
  || fallar "no existe el balanceador $ALB_NAME. Haga el paso A7."
ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" --query 'LoadBalancers[0].DNSName' --output text)
VPC_ID=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" --query 'LoadBalancers[0].VpcId' --output text)
# Las tareas van en las mismas subredes (publicas) que el balanceador.
SUBNETS=$(aws elbv2 describe-load-balancers --load-balancer-arns "$ALB_ARN" \
  --query 'LoadBalancers[0].AvailabilityZones[].SubnetId' --output text)
echo "    balanceador: $ALB_DNS (VPC $VPC_ID, subredes: $SUBNETS)"

TG_ARN=$(aws elbv2 describe-target-groups --names "$TG_BLUE" \
  --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null) \
  || fallar "no existe el target group $TG_BLUE. Haga el paso A6."
TG_LBS=$(aws elbv2 describe-target-groups --target-group-arns "$TG_ARN" \
  --query 'TargetGroups[0].LoadBalancerArns' --output text)
if [ -z "$TG_LBS" ] || [ "$TG_LBS" = "None" ]; then
  fallar "$TG_BLUE no esta conectado al balanceador. El listener HTTP:80 de $ALB_NAME debe enviar a $TG_BLUE (paso A7)."
fi
echo "    target group azul: $TG_BLUE"

SG_ID=$(aws ec2 describe-security-groups \
  --filters Name=group-name,Values="$SG_TASKS" Name=vpc-id,Values="$VPC_ID" \
  --query 'SecurityGroups[0].GroupId' --output text)
[ -n "$SG_ID" ] && [ "$SG_ID" != "None" ] \
  || fallar "no existe el security group $SG_TASKS en la VPC $VPC_ID. Haga el paso A5."
echo "    security group de las tareas: $SG_TASKS ($SG_ID)"

EXISTING=$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
  --query 'services[?status==`ACTIVE`].deploymentController.type' --output text)
if [ -n "$EXISTING" ]; then
  if [ "$EXISTING" = "CODE_DEPLOY" ]; then
    echo
    echo "El servicio $SERVICE ya existe con el controlador CODE_DEPLOY. No hay nada que hacer."
    echo "URL: http://$ALB_DNS/health"
    exit 0
  fi
  fallar "el servicio $SERVICE ya existe con el controlador $EXISTING (probablemente se creo desde la consola). CodeDeploy no puede usarlo: borrelo en ECS > $CLUSTER > Services > $SERVICE > Delete service (marque Force delete), espere a que desaparezca y vuelva a ejecutar este script."
fi

# --- 2. Definicion de tarea ---------------------------------------------------
paso "Registrando la definicion de tarea con la imagen $IMAGE_TAG"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

sed -e "s|<ACCOUNT_ID>|$ACCOUNT_ID|g" \
    -e "s|<REGION>|$REGION|g" \
    -e "s|<IMAGE1_NAME>|$IMAGE_URI|g" \
    deploy/taskdef.json > "$TMP/taskdef.json"

TASKDEF_ARN=$(aws ecs register-task-definition --cli-input-json "file://$TMP/taskdef.json" \
  --query 'taskDefinition.taskDefinitionArn' --output text)
echo "    $TASKDEF_ARN"

# --- 3. Servicio --------------------------------------------------------------
paso "Creando el servicio $SERVICE con el controlador CODE_DEPLOY"

SUBNETS_JSON=$(printf '"%s",' $SUBNETS)
SUBNETS_JSON="[${SUBNETS_JSON%,}]"

cat > "$TMP/service.json" <<EOF
{
  "cluster": "$CLUSTER",
  "serviceName": "$SERVICE",
  "taskDefinition": "$TASKDEF_ARN",
  "desiredCount": $DESIRED_COUNT,
  "launchType": "FARGATE",
  "platformVersion": "LATEST",
  "schedulingStrategy": "REPLICA",
  "deploymentController": { "type": "CODE_DEPLOY" },
  "healthCheckGracePeriodSeconds": 60,
  "loadBalancers": [
    {
      "targetGroupArn": "$TG_ARN",
      "containerName": "$CONTAINER_NAME",
      "containerPort": $CONTAINER_PORT
    }
  ],
  "networkConfiguration": {
    "awsvpcConfiguration": {
      "subnets": $SUBNETS_JSON,
      "securityGroups": ["$SG_ID"],
      "assignPublicIp": "ENABLED"
    }
  }
}
EOF

aws ecs create-service --cli-input-json "file://$TMP/service.json" \
  --query 'service.{servicio:serviceName,controlador:deploymentController.type,estado:status}' --output table

# --- 4. Verificacion ----------------------------------------------------------
paso "Esperando a que la tarea quede sana en $TG_BLUE (maximo 10 minutos)"

HEALTHY=0
for _ in $(seq 1 60); do
  RUNNING=$(aws ecs describe-services --cluster "$CLUSTER" --services "$SERVICE" \
    --query 'services[0].runningCount' --output text)
  HEALTHY=$(aws elbv2 describe-target-health --target-group-arn "$TG_ARN" \
    --query 'length(TargetHealthDescriptions[?TargetHealth.State==`healthy`])' --output text)
  echo "    $(date +%H:%M:%S)  tareas RUNNING: $RUNNING/$DESIRED_COUNT   targets healthy: $HEALTHY"
  [ "$HEALTHY" -ge "$DESIRED_COUNT" ] && break
  sleep 10
done

if [ "$HEALTHY" -lt "$DESIRED_COUNT" ]; then
  fallar "la tarea no quedo sana. Revise ECS > $CLUSTER > $SERVICE > Tasks (pestana Stopped, campo 'Stopped reason'), el log group /ecs/listanegra en CloudWatch y la tabla de problemas de docs/CD_FARGATE.md."
fi

echo
echo "GET http://$ALB_DNS/health"
curl -s "http://$ALB_DNS/health" || true
echo
echo
echo "Servicio listo. Siguiente paso: crear la aplicacion y el deployment group de CodeDeploy (paso A11)."
