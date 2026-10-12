# Estrategias de despliegue – resultados

Registro de las 4 estrategias ejecutadas sobre `listanegra-env` (ASG mínimo 3 / máximo 6, `t3.micro`).
Procedimiento: [DESPLIEGUE_AWS.md – Fase 5](DESPLIEGUE_AWS.md#fase-5--las-4-estrategias-de-despliegue-20-de-la-nota).
Los valores `PENDIENTE` se llenan con los resultados reales; la salida completa del monitor de cada
despliegue queda en `evidencias/<versión>-<fecha>.log`.

Orden de ejecución y versión desplegada en cada una:

| # | Estrategia | Versión (`src/version.py`) | Version label en Beanstalk |
|---|---|---|---|
| 1 | All at once | 1.0.1 | `v1.0.1-all-at-once` |
| 2 | Rolling (batch 1) | 1.0.2 | `v1.0.2-rolling` |
| 3 | Rolling with additional batch (batch 1) | 1.0.3 | `v1.0.3-rolling-additional` |
| 4 | Immutable | 1.0.4 | `v1.0.4-immutable` |

---

## 1. All at once

**Configuración:** Deployment policy = `All at once`.

- **a. Cantidad de instancias:** PENDIENTE (esperado: las 3 existentes, actualizadas a la vez)
- **b. Validación de que el despliegue estaba en ejecución:** PENDIENTE
  (monitor de `/health` cada 1 s → N solicitudes, M fallidas entre t=… y t=…; pestaña Health con
  instancias en `Pending`/`Info`; evento `Deploying new version to instance(s).`)
- **c. Tiempo total:** PENDIENTE min PENDIENTE s
  (Events: `Environment update is starting.` hh:mm:ss → `Environment update completed successfully.` hh:mm:ss)
- **d. ¿Instancias iniciales o nuevas?:** PENDIENTE (esperado: iniciales; mismos IDs en EC2 y mismos
  `host` en el monitor antes y después)
- **e. Capturas:** PENDIENTE
  - [ ] Configuration → Deployments con la política seleccionada
  - [ ] Events con el evento de inicio y el de fin
  - [ ] Health por instancia durante el despliegue
  - [ ] EC2 → Instances (IDs y *launch time*) antes y después
  - [ ] Salida del monitor (resumen)
- **f. Hallazgos:** PENDIENTE

---

## 2. Rolling

**Configuración:** Deployment policy = `Rolling`, Batch size = `Fixed` `1`.

- **a. Cantidad de instancias:** PENDIENTE (esperado: 3; durante cada lote sirven 2)
- **b. Validación de que el despliegue estaba en ejecución:** PENDIENTE
  (el monitor muestra respuestas de la versión anterior y la nueva intercaladas; Health con versiones
  distintas por instancia)
- **c. Tiempo total:** PENDIENTE min PENDIENTE s
- **d. ¿Instancias iniciales o nuevas?:** PENDIENTE (esperado: iniciales)
- **e. Capturas:** PENDIENTE
  - [ ] Configuration → Deployments (política + batch size)
  - [ ] Events con un evento por lote, el de inicio y el de fin
  - [ ] Health con dos versiones distintas al mismo tiempo
  - [ ] EC2 → Instances antes y después
  - [ ] Salida del monitor (resumen)
- **f. Hallazgos:** PENDIENTE

---

## 3. Rolling with additional batch

**Configuración:** Deployment policy = `Rolling with additional batch`, Batch size = `Fixed` `1`.

- **a. Cantidad de instancias:** PENDIENTE (esperado: 3 + 1 adicional = 4 durante el despliegue)
- **b. Validación de que el despliegue estaba en ejecución:** PENDIENTE
- **c. Tiempo total:** PENDIENTE min PENDIENTE s
- **d. ¿Instancias iniciales o nuevas?:** PENDIENTE (mezcla: comparar IDs en EC2 antes y después para
  ver cuál instancia se lanzó y cuál se terminó al final)
- **e. Capturas:** PENDIENTE
  - [ ] Configuration → Deployments (política + batch size)
  - [ ] Events con `Launched additional batch` / terminación del lote extra, inicio y fin
  - [ ] Health mostrando 4 instancias
  - [ ] EC2 → Instances antes y después
  - [ ] Salida del monitor (resumen)
- **f. Hallazgos:** PENDIENTE

---

## 4. Immutable

**Configuración:** Deployment policy = `Immutable`.

- **a. Cantidad de instancias:** PENDIENTE (esperado: 3 iniciales + 3 nuevas en un ASG temporal = hasta 6)
- **b. Validación de que el despliegue estaba en ejecución:** PENDIENTE
  (EC2 → Auto Scaling Groups muestra el ASG temporal; el monitor ve `host` nuevos)
- **c. Tiempo total:** PENDIENTE min PENDIENTE s
- **d. ¿Instancias iniciales o nuevas?:** PENDIENTE (esperado: todas nuevas; las iniciales se terminan)
- **e. Capturas:** PENDIENTE
  - [ ] Configuration → Deployments con la política
  - [ ] Events (creación del ASG temporal, inicio y fin)
  - [ ] EC2 → Auto Scaling Groups con el ASG temporal
  - [ ] EC2 → Instances antes y después (IDs distintos)
  - [ ] Salida del monitor (resumen)
- **f. Hallazgos:** PENDIENTE

---

## Tabla comparativa

| Estrategia | Instancias durante el despliegue | Nuevas / existentes | Tiempo total | Fallos observados (monitor) | Costo relativo | Facilidad de rollback |
|---|---|---|---|---|---|---|
| All at once | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | Sin costo extra | Baja: redesplegar la versión anterior, con otra caída |
| Rolling | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | Sin costo extra | Media: otro rolling con la versión anterior |
| Rolling with additional batch | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | +1 lote mientras dura | Media: otro rolling con la versión anterior |
| Immutable | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | El doble de instancias mientras dura | Alta: si falla, se descarta el ASG temporal sin tocar las instancias iniciales |

## Conclusiones

PENDIENTE: qué estrategia recomienda el grupo para producción y por qué (disponibilidad vs. tiempo vs. costo).
