# Imagen del microservicio de lista negra para AWS Fargate.
# Se usa el espejo de Docker Hub en ECR Public para evitar el limite de
# descargas anonimas de Docker Hub dentro de CodeBuild.
FROM public.ecr.aws/docker/library/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENV=production

WORKDIR /app

# Las dependencias van en su propia capa: si solo cambia el codigo, Docker
# reutiliza esta capa y la imagen se construye mas rapido.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY application.py .
COPY src ./src

# El proceso no corre como root.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000

# Mismo servidor que en Elastic Beanstalk (Procfile), con menos workers porque
# cada tarea de Fargate tiene 0.5 vCPU.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "application:application"]
