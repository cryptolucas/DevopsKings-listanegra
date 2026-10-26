# Entrega 2 – Integración continua con AWS CodeBuild y CodePipeline

Cada commit en `main` dispara un pipeline que instala dependencias, ejecuta las pruebas unitarias y,
si pasan, genera el artefacto desplegable (zip para Elastic Beanstalk) en S3. **No hay despliegue
automático (CD)**: el enunciado lo excluye en esta entrega.

```
GitHub (push a main) ──► CodePipeline ──► CodeBuild (buildspec.yml)
                          Source stage     ├─ install: Python 3.11 + requirements-dev.txt
                                           ├─ build:   pytest (SQLite en memoria)
                                           └─ artifact: zip del microservicio → S3
```

> El enunciado habla de commits en `master`. En este repositorio la rama principal se llama `main`;
> cumple el mismo papel.

## Lo que ya está en el repositorio (25% + 30%)

| Archivo | Qué hace |
|---|---|
| `buildspec.yml` | Instrucciones para CodeBuild: instala, prueba, publica el reporte de pruebas y empaqueta el artefacto |
| `tests/conftest.py` | Crea una app nueva con SQLite en memoria para cada prueba (no depende de PostgreSQL) |
| `tests/test_blacklists.py` | POST `/blacklists` (201, 409, 400 ×6, 401 ×3) y GET `/blacklists/<email>` (200 sí/no, mayúsculas, 401) |
| `tests/test_auth_y_soporte.py` | POST `/auth/token`, GET `/` y GET `/health` con la base caída (503) |
| `tests/test_health.py` | GET `/health` reporta versión y host |
| `requirements-dev.txt` | Dependencias de la app + `pytest`; lo instala CodeBuild, no Beanstalk |

Correrlas en local:

```powershell
pip install -r requirements-dev.txt
python -m pytest -v
```

## Paso 1 – Conexión con GitHub (la hace el dueño del repo)

El repositorio es de `cryptolucas`, así que **Lucas** debe autorizar la conexión:

1. Consola de AWS en **us-east-2 (Ohio)** → **Developer Tools → Settings → Connections →
   Create connection**.
2. Provider **GitHub** → nombre `github-devopskings` → **Connect to GitHub** → **Install a new app** →
   instalar la app *AWS Connector for GitHub* en la cuenta `cryptolucas`, solo para el repo
   `DevopsKings-listanegra` → **Connect**.
3. La conexión debe quedar en estado **Available**.

📸 Captura de la conexión en estado Available.

## Paso 2 – Crear el pipeline y el proyecto de CodeBuild (15% + 10%)

**CodePipeline → Pipelines → Create pipeline → Build custom pipeline**:

1. **Pipeline settings**
   - Name: `listanegra-ci`
   - Execution mode: *Queued* (o *Superseded*)
   - Service role: *New service role*
2. **Source stage**
   - Provider: **GitHub (via GitHub App)**
   - Connection: `github-devopskings`
   - Repository: `cryptolucas/DevopsKings-listanegra`
   - Default branch: `main`
   - Output artifact format: *CodePipeline default*
   - Trigger: **Specify filter → Push → Branch → `main`**. Esto cumple "cada commit en master
     ejecuta el build".
3. **Build stage**
   - Provider: **Other build providers → AWS CodeBuild**
   - **Create project** (se abre otra ventana):
     - Project name: `listanegra-build`
     - Environment: *Managed image* → **Amazon Linux** → *Standard* →
       **`aws/codebuild/amazonlinux-x86_64-standard:5.0`**
     - Compute: el más pequeño (3 GB, 2 vCPUs)
     - Service role: *New service role*
     - Buildspec: **Use a buildspec file** (deje el nombre vacío; usa `buildspec.yml`)
     - Logs: CloudWatch activado
     - **Continue to CodePipeline**
   - Build type: *Single build*
4. **Test stage:** *Skip*.
5. **Deploy stage:** **Skip deploy stage**. No se configura CD en esta entrega.
6. **Create pipeline**. Arranca solo con el último commit de `main`.

El artefacto queda en el bucket que crea CodePipeline (`codepipeline-us-east-2-...`), carpeta
`listanegra-ci/BuildArtif/`. Ese zip es el mismo bundle que se sube a Beanstalk.

> Si el build falla en la fase **INSTALL** con un error de `runtime-versions`, la imagen no tiene
> Python 3.11. Revise la imagen elegida (debe ser `amazonlinux-x86_64-standard:5.0`).

## Paso 3 – Ejecución exitosa (documento, 10%)

1. Haga un commit pequeño en `main` (por ejemplo, la versión en `src/version.py`) y `git push`.
2. Las dos etapas quedan en verde (*Source* y *Build*).

📸 Capturas:
- [ ] CodePipeline: la ejecución con Source y Build en verde, y el commit que la disparó.
- [ ] CodeBuild → la ejecución → **Phase details**, con todas las fases en *Succeeded*.
- [ ] CodeBuild → **Build logs**, con `23 passed` y el mensaje de empaquetado.
- [ ] CodeBuild → **Reports** (o *Report groups*), con 23/23 pruebas superadas.
- [ ] S3 → el zip del artefacto en el bucket de CodePipeline.

## Paso 4 – Ejecución fallida (documento, 10%)

Se introduce a propósito un error que las pruebas deben detectar, por ejemplo que POST
`/blacklists` responda 200 en vez de 201:

```powershell
# En src/resources/blacklist.py, en el return final de post(), cambie 201 por 200
git commit -am "ci: prueba de pipeline fallido (POST responde 200)"
git push
```

El pipeline falla en *Build*: 3 pruebas fallan y CodeBuild marca **FAILED**.

📸 Capturas:
- [ ] CodePipeline con *Build* en rojo.
- [ ] CodeBuild → **Phase details**, con BUILD en *Failed*.
- [ ] **Build logs** con los `FAILED tests/test_blacklists.py::...` y el `assert 200 == 201`.
- [ ] **Reports**, con 20 superadas y 3 fallidas.

Después se revierte para dejar `main` sano (genera otra ejecución exitosa):

```powershell
git revert HEAD --no-edit
git push
```

Hallazgo a documentar: el error se detectó en ~2 minutos, antes de generar un artefacto apto para
desplegar, y la ejecución identifica el commit exacto que lo introdujo.

## Costos

CodeBuild y CodePipeline tienen capa gratuita mensual de minutos. Un build de este proyecto tarda
pocos minutos, así que unas decenas de ejecuciones cuestan centavos o nada. El bucket de artefactos
también es mínimo. Para no dejar cobros activos al terminar el curso, borre el pipeline, el proyecto
de CodeBuild y el bucket.

## Estructura sugerida de "Proyecto 1 entrega 2 – Documento.pdf"

1. Portada con los integrantes.
2. Arquitectura del pipeline (el diagrama de arriba) y link del repositorio.
3. Pruebas unitarias: lista de escenarios por endpoint y captura de `pytest -v` en local.
4. Configuración: conexión GitHub, proyecto CodeBuild (imagen, buildspec), pipeline (trigger en `main`).
5. Ejecución exitosa: capturas y hallazgos (Paso 3).
6. Ejecución fallida: capturas y hallazgos (Paso 4).
7. Conclusiones.
