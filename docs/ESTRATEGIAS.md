# Estrategias de despliegue – resultados

Registro de las 4 estrategias ejecutadas sobre `listanegra-env` (ASG mínimo 3 / máximo 6, `t3.micro`)
el 16 de octubre de 2026. Procedimiento:
[DESPLIEGUE_AWS.md – Fase 5](DESPLIEGUE_AWS.md#fase-5--las-4-estrategias-de-despliegue-20-de-la-nota).
La salida completa del monitor de cada despliegue está en `evidencias/<versión>-<fecha>.log`.

Los tiempos del monitor son aproximados. El tiempo oficial (literal c) sale de la pestaña **Events**
(`Environment update is starting.` → `Environment update completed successfully.`); donde dice
`PENDIENTE` hay que copiarlo de esa pestaña.

| # | Estrategia | Versión | Version label | Log del monitor |
|---|---|---|---|---|
| 1 | All at once | 1.0.1 | `v1.0.1-all-at-once` | `evidencias/1.0.1-20261016-214626.log` |
| 2 | Rolling (batch 1) | 1.0.2 | `v1.0.2-rolling` | `evidencias/1.0.2-20261016-215632.log` |
| 3 | Rolling with additional batch (batch 1) | 1.0.3 | `v1.0.3-rolling-additional` | `evidencias/1.0.3-20261016-221121.log` |
| 4 | Immutable | 1.0.4 | `v1.0.4-immutable` | `evidencias/1.0.4-*.log` |

---

## 1. All at once

**Configuración:** Deployment policy = `All at once`.

- **a. Cantidad de instancias:** 3, las mismas del ambiente, actualizadas al mismo tiempo.
- **b. Validación de que el despliegue estaba en ejecución:** el monitor consultó `/health` cada
  segundo: 143 solicitudes, **6 fallidas (HTTP 502)** seguidas entre 21:48:14 y 21:48:20. Durante esos
  ~6 s ninguna instancia atendía: es la caída esperada de esta estrategia. Desde 21:48:21 las tres
  instancias responden `1.0.1`.
- **c. Tiempo total:** PENDIENTE (Events). Monitor: el cambio de versión ocurrió a los 113 s de iniciado
  el monitoreo.
- **d. ¿Instancias iniciales o nuevas?:** iniciales. Los mismos hosts (`ip-172-31-2-67`,
  `ip-172-31-43-122`, `ip-172-31-25-220`) siguen atendiendo después. Confirmar con las capturas de
  EC2 → Instances (mismos IDs antes y después).
  > El resumen del log dice "instancias NUEVAS", pero es un error del monitor: la versión anterior no
  > reportaba el campo `host` y no había con qué comparar. Ya está corregido en el script.
- **e. Capturas:** política seleccionada, Events, Health durante el despliegue, EC2 antes y después,
  resumen del monitor.
- **f. Hallazgos:** es la estrategia más rápida y no lanza instancias extra, pero tiene **downtime**: el
  balanceador devolvió 502 durante ~6 s porque las tres instancias reiniciaban la aplicación al mismo
  tiempo. El rollback es otro despliegue completo, con otra caída.

---

## 2. Rolling

**Configuración:** Deployment policy = `Rolling`, Batch size = `Fixed` `1`.

> ⚠️ **Esta medición hay que repetirla.** El log muestra el comportamiento de *All at once*, no de
> Rolling: las 3 instancias respondieron `1.0.1` hasta 21:57:34, luego hubo **6 fallos 502 seguidos**
> (21:57:35–21:57:40) y las 3 pasaron a `1.0.2` en menos de 3 s. Con Rolling de lote 1 se deberían ver
> versiones mezcladas por varios minutos y ningún fallo. Lo más probable es que el cambio de política no
> se aplicó (o el batch size quedó en 100%). Revisar en Events si aparece "Deploying new version to
> instance(s)" para las 3 a la vez.

Valores esperados al repetirla (con la versión 1.0.5):

- **a. Cantidad de instancias:** 3; en cada momento solo 2 atienden.
- **b. Validación:** el monitor muestra respuestas de la versión anterior y la nueva intercaladas;
  Health con versiones distintas por instancia; Events con un mensaje por lote.
- **c. Tiempo total:** PENDIENTE.
- **d. ¿Instancias iniciales o nuevas?:** iniciales.
- **e. Capturas:** política + batch size, Events por lote, Health con dos versiones, EC2 antes y después,
  monitor.
- **f. Hallazgos:** PENDIENTE.

---

## 3. Rolling with additional batch

**Configuración:** Deployment policy = `Rolling with additional batch`, Batch size = `Fixed` `1`.

- **a. Cantidad de instancias:** 3 iniciales + 1 adicional = **4 durante el despliegue**; al final
  vuelven a ser 3.
- **b. Validación de que el despliegue estaba en ejecución:** 573 solicitudes, **0 fallidas**. Línea de
  tiempo del monitor:

  | Hora | Evento observado |
  |---|---|
  | 22:11:21 | Inicio: 3 instancias con `1.0.2` |
  | 22:13:17 | Aparece la instancia **nueva** `ip-172-31-28-132` con `1.0.3` (4 instancias atendiendo) |
  | 22:15:21 → 22:16:02 | `ip-172-31-43-122` sale del balanceador ~41 s y vuelve con `1.0.3` |
  | 22:18:00 → 22:18:40 | `ip-172-31-2-67` sale ~40 s y vuelve con `1.0.3` |
  | 22:20:54 | Fin del monitoreo; `ip-172-31-25-220` seguía con `1.0.2` |
  | 22:38 | Verificado: atienden `ip-172-31-2-67`, `ip-172-31-43-122` y `ip-172-31-28-132` con `1.0.3`; `ip-172-31-25-220` fue terminada |

- **c. Tiempo total:** PENDIENTE (Events). El monitor se detuvo antes del final, por eso el log no tiene
  resumen.
- **d. ¿Instancias iniciales o nuevas?:** mezcla. Se lanzó una instancia nueva (`ip-172-31-28-132`)
  que quedó en el ambiente; dos iniciales se actualizaron en sitio y una inicial
  (`ip-172-31-25-220`) se terminó al final.
- **e. Capturas:** política + batch size, Events (lote adicional, inicio y fin), Health con 4 instancias,
  EC2 antes y después, monitor.
- **f. Hallazgos:** sin pérdida de disponibilidad y sin reducir capacidad: mientras una instancia se
  actualiza, la adicional cubre su lugar. Tarda bastante más que All at once (~10 min) y cuesta una
  instancia extra mientras dura. Durante varios minutos conviven dos versiones respondiendo a la vez,
  algo a tener en cuenta si una versión cambia el contrato del API.

---

## 4. Immutable

**Configuración:** Deployment policy = `Immutable`.

- **a. Cantidad de instancias:** PENDIENTE (esperado: 3 iniciales + 3 nuevas en un ASG temporal).
- **b. Validación:** PENDIENTE. A las 22:39 ya atendía una instancia nueva (`ip-172-31-39-209`) con
  `1.0.4` junto a las 3 con `1.0.3`.
- **c. Tiempo total:** PENDIENTE (Events).
- **d. ¿Instancias iniciales o nuevas?:** PENDIENTE (esperado: todas nuevas).
- **e. Capturas:** política, Events (ASG temporal, inicio y fin), EC2 → Auto Scaling Groups con el
  grupo temporal, EC2 antes y después, monitor.
- **f. Hallazgos:** PENDIENTE.

---

## Tabla comparativa

| Estrategia | Instancias durante el despliegue | Nuevas / existentes | Tiempo total (Events) | Fallos observados (monitor) | Costo relativo | Facilidad de rollback |
|---|---|---|---|---|---|---|
| All at once | 3 | Existentes | PENDIENTE | 6 × 502 (~6 s de caída) | Sin costo extra | Baja: redesplegar la versión anterior, con otra caída |
| Rolling | 3 (2 atendiendo) | Existentes | PENDIENTE | Repetir medición | Sin costo extra | Media: otro rolling con la versión anterior |
| Rolling with additional batch | 4 | Mezcla (1 nueva, 1 terminada) | PENDIENTE | 0 | +1 instancia mientras dura | Media: otro rolling con la versión anterior |
| Immutable | PENDIENTE | PENDIENTE | PENDIENTE | PENDIENTE | El doble de instancias mientras dura | Alta: si falla, se descarta el ASG temporal sin tocar las instancias iniciales |

## Conclusiones

PENDIENTE: qué estrategia recomienda el grupo para producción y por qué (disponibilidad vs. tiempo vs. costo).
