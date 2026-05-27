# ADR 0001 — Runtime: de app local single-user a servicio compartido multiusuario

- **Estado:** Aceptado
- **Fecha:** 2026-05-27
- **Decisores:** equipo keni-social (auditoría de arquitectura, épica #140)
- **Issues:** #130 (esta decisión) · #137 #134 #133 #9 #5
- **Componente:** `consola/` (runtime y modelo de despliegue)

> **Sobre los ADR en este repo.** Este es el primer Architecture Decision Record del
> proyecto: no había convención previa ni carpeta `docs/adr/`. Adoptamos numeración
> incremental de cuatro dígitos (`0001-…`, `0002-…`) y este formato como plantilla para
> los siguientes. Un ADR registra una decisión de arquitectura con su contexto y sus
> consecuencias; no se reescribe cuando cambia la realidad: si una decisión se revierte,
> se escribe un ADR nuevo que la supersede.

---

## Contexto

### Objetivo del producto

keni-social aspira a ser una **herramienta de producción de uso diario por un equipo de
redes** (no por un operador técnico), **reutilizable entre clientes**. La promesa de
diseño es "botones en vez de comandos": que un community manager no-técnico convierta una
nota, un clip o una tendencia en copy publicable —con voz de marca, tropicalización MX,
formato por plataforma y auto-verificación— y lea métricas multi-plataforma y multi-marca,
sin tener que pelearse con una CLI ni montar un entorno de desarrollo. La filosofía es
**capacidad, no dependencia**.

### Tres hechos del piloto AMX que rompen el runtime actual

La auditoría de arquitectura (#140) contrastó el diseño con las conversaciones de entrega
del piloto AMX (Bernardo Vázquez, Elías, Diana Ramos). Tres hechos duros del campo son
incompatibles con la arquitectura de ejecución de hoy:

1. **Máquinas corporativas bloqueadas + IT cuello de botella.** Bernardo: *"con todos los
   equipos van a tener ese problema… con IT también tenemos que hablar."* No se puede
   instalar Claude Code, clonar el repo y correr `npm run build` en cada máquina del
   equipo. El modelo actual exige exactamente eso.

2. **Multiusuario / móvil / 24-7.** Hay cuentas compartidas ("una licencia para tres":
   Tescu/Luis/Roger rotan un PC por horario). Elías quiere acceder *"desde el móvil"*;
   Bernardo quiere automatizar el flujo de presidencia el fin de semana, también desde el
   móvil. Una app que solo escucha en `127.0.0.1` del portátil de una persona no da móvil,
   ni 24-7, ni estado compartido entre miembros del equipo.

3. **Presupuesto de tokens por usuario (adoption killer explícito).** Bernardo: *"como se
   le acabe el saldo, no la van a usar. La de 20 dólares no va a dar para un día entero."*
   Hoy no existe ningún control de coste por usuario: el coste recae sobre la suscripción
   de Claude Code de la máquina de cada quien, sin tope, sin cuota y sin visibilidad
   central.

---

## Estado actual (lo que hay hoy)

La Consola es una app **Starlette single-process, single-user**, que corre en el portátil
de cada persona y genera copy lanzando `claude -p` como **subproceso local** por cada job.
Es la arquitectura correcta para *un operador técnico* (el facilitador del piloto), pero no
para el objetivo declarado. Evidencia en el repo:

- **Bind local, un proceso por persona.** `consola/src/keni_consola/__main__.py:27` fija
  `HOST = "127.0.0.1"` y `__main__.py:49` lo declara explícitamente
  ("solo escucha en 127.0.0.1 (no expuesta a la red)"). Es una decisión de seguridad
  *deliberada* para el modelo local — y precisamente por eso no sirve para acceso de
  equipo ni móvil.
- **Exige Claude Code instalado y autenticado en cada máquina.**
  `consola/src/keni_consola/generaciones.py:451` hace `shutil.which("claude")`: si no está
  en el PATH, el job falla.
- **Un subproceso `claude -p` por job.** `generaciones.py:464` (`subprocess.Popen(...)`) y
  el runner unificado `consola/src/keni_consola/dominio/runner.py:49`
  (`"claude", "-p", prompt, …`). El coste vive en la cuenta de Claude Code de la máquina,
  fuera de nuestro control.
- **Persistencia local sin multiusuario ni estado compartido.**
  `consola/src/keni_consola/db.py:30` asume "poca concurrencia" y guarda en
  `~/.config/keni-social/consola.db` (local de cada persona). No hay separación de usuarios:
  los borradores de A no existen para B.
- **Cola sin tope ni presupuesto de coste por usuario.**
  `dominio/runner.py:145,151` — el `BoundedSemaphore` limita *procesos concurrentes*
  (`KENI_MAX_JOBS`, def. 4), pero la espera bloqueante `sem.acquire()` no acota la cola y no
  hay ningún concepto de coste/cuota por usuario.
- **Sin auth.** `app.py` sirve las rutas sin capa de autenticación; el bind a `127.0.0.1`
  *no es control de acceso* (ver #134). En modo hosted la auth se delega a un reverse proxy
  externo (`docs/despliegue-hosted.md:51-54`), que hoy no existe.
- **Distribución acoplada al repo de dev.** `dominio/skills.py:329` resuelve el `cwd` de las
  skills a `~/projects/keni-social`; sin ese checkout, las skills no se descubren (#133).

---

## Decisión

Reemplazar el runtime, conservando la IP de dominio. El nuevo runtime es un **servicio
compartido multiusuario** con estas propiedades de primera clase:

1. **Servicio compartido (un backend, multiusuario, accesible por navegador/móvil)** en
   lugar de una app local por persona. Un solo despliegue al que el equipo entra desde el
   navegador del PC corporativo o del móvil, sin instalar nada. Mata de raíz el cuello de
   botella de IT (hecho 1) y habilita móvil/24-7 (hecho 2).

2. **Autenticación multiusuario** como requisito, no como capa opcional delegada a un proxy.
   Identidad por usuario, sesión, y protección CSRF/`Origin` en las mutaciones. Esto absorbe
   y resuelve #134, que el servicio compartido necesita de todas formas.

3. **Generación vía la API de Claude (SDK)**, no `subprocess` de la CLI local de cada quien.
   El servidor llama a la API de Claude con una clave central; elimina la dependencia de
   tener Claude Code instalado/autenticado en cada máquina, y habilita control de coste, cola
   y observabilidad centrales. (El repo ya conoce `ANTHROPIC_API_KEY`, hoy solo en
   `autodesarrollo.py:142`.)

4. **Presupuesto/cuota de tokens por usuario** como requisito de primera clase: cada usuario
   tiene una cuota; al agotarse, se le corta (con aviso), sin afectar al resto. Resuelve el
   adoption killer (hecho 3) y da visibilidad de coste central.

5. **Estado compartido** entre miembros del equipo: borradores, cola de aprobación, historial
   y publicaciones son visibles según permisos, no aislados por máquina. Esto habilita #9
   (scheduling + cola de aprobación de equipo + dashboard).

La IP de dominio —**skills de copy, contexto editorial versionado, la abstracción
`FuenteMetricas` y `keni-shared`**— se conserva intacta: el cambio es de runtime y modelo de
despliegue, no del núcleo que produce y mide.

---

## Alternativas consideradas

### A. Status quo (app local single-user + `claude -p` por subproceso). Descartada.

Es la arquitectura actual. Funciona para un operador técnico, pero choca de frente con los
tres hechos del piloto: exige instalar Claude Code y clonar el repo en máquinas bloqueadas
(hecho 1), no da multiusuario/móvil/24-7 (hecho 2) y no tiene control de coste por usuario
(hecho 3). No sirve al objetivo declarado del producto.

### B. `claude -p` centralizado en un servidor (la CLI, pero alojada). Descartada.

Mover el binario local a un servidor compartido y seguir lanzando `claude -p` como
subproceso, ahora central. Resolvería el acceso (un solo despliegue) pero arrastra los
defectos del modelo de subprocesos a un entorno de carga real:

- Mantiene la **fragilidad del runner** (#137): cola sin backpressure, procesos
  potencialmente huérfanos, `kill` que no mata el árbol de procesos hijos
  (`generaciones.py:502`, `dominio/runner.py`). Multiplicado por N usuarios concurrentes, es
  un servidor lleno de zombies.
- El **coste por usuario sigue siendo opaco**: `claude -p` factura contra la suscripción de
  Claude Code de la cuenta del servidor, no expone tokens por petición de forma fiable, y no
  hay forma limpia de imponer cuota por usuario.
- Depende del ciclo de vida y la autenticación interactiva de una CLI pensada para un humano,
  no para servir tráfico de muchos. La API/SDK es la interfaz pensada para esto: streaming
  nativo, contabilidad de tokens por respuesta y sin gestión de árboles de subprocesos.

Por eso se descarta a favor de la API de Claude (SDK).

---

## Consecuencias

### IP que se conserva (no se toca)

- **Skills de copy** (`skills-copy/`) y el **contexto editorial versionado** (marcas/voces):
  la lógica que produce el copy y los datos editoriales son independientes del runtime. La
  generación deja de invocarse por `subprocess claude -p` y pasa a invocarse por la API/SDK,
  pero **las skills y su contexto son la misma IP**.
- **Abstracción `FuenteMetricas`** y su jerarquía (`FuenteMuestra` / `FuenteCompuesta` +
  adaptadores por plataforma): el MCP de métricas y su diseño "añadir plataforma = un
  adaptador" no cambian.
- **`keni-shared`**: el módulo común (marcas, cuentas, esquema YAML, normalización) sigue
  siendo la base compartida.

### Qué se reemplaza

- El **bind local `127.0.0.1` + un proceso por persona** → backend compartido con auth,
  accesible por red/móvil.
- El **subproceso `claude -p` por job** (`generaciones.py:464`, `runner.py:49`) → llamadas a
  la **API de Claude (SDK)** con clave central.
- La **persistencia local single-user** (`db.py`) → estado compartido multiusuario con
  separación por usuario y modelo de permisos.
- La **dependencia de Claude Code instalado** (`shutil.which("claude")`,
  `generaciones.py:451`) y del **repo de dev en disco** para resolver skills
  (`skills.py:329`) → desaparecen: el servicio lleva su propio contexto.

### #137 (endurecer el runner) es una medida INTERINA y se descarta al migrar

#137 endurece el runner de subprocesos: cola con tope/backpressure, lanzar en su propio
grupo de procesos y matar el árbol completo en timeout/cancel, y no tragar excepciones. Todo
eso es **deuda del modelo de subprocesos**. Bajo la decisión de este ADR, la generación pasa
a la API/SDK y **el runner de subprocesos deja de existir** — con él se van la cola sin tope,
los procesos huérfanos y el problema del `kill` del árbol. Por tanto:

- #137 se trata como **medida interina**: solo merece esfuerzo mientras el runtime de
  subprocesos siga en producción (Fase 0). Hacer lo mínimo para que el piloto no se caiga.
- #137 se **descarta/cierra al completar la migración** de generación a la API (Fase 2): el
  componente que arregla ya no estará.

### Impacto en issues relacionadas

- **#133 (distribución rota).** El servicio compartido es la solución de fondo: con la
  Consola alojada, no hay que distribuir nada a las máquinas del equipo (ni plugin, ni repo,
  ni Claude Code) — entran por navegador. El fallback de `cwd_skills()` a la caché del plugin
  queda como parche solo para los usuarios técnicos que sigan en local.
- **#134 (auth/CSRF).** Se absorbe: el servicio multiusuario necesita auth de primera clase
  de todas formas. La auth deja de delegarse a un proxy inexistente y vive en el servicio.
- **#9 (Fase 3: scheduling + cola de aprobación de equipo + dashboard).** Queda **habilitada**:
  scheduling y aprobación de equipo requieren estado compartido y multiusuario, que es
  exactamente lo que provee este runtime. #9 es consumidor de esta decisión.
- **#5 (Meta App Review + cuentas reales).** Independiente y en paralelo (gating externo de
  plataforma); este ADR no lo desbloquea ni lo bloquea. Pero el servicio alojado encaja con
  los System User tokens de Meta del despliegue hosted, y el dashboard de #9 consumirá esas
  métricas reales cuando #5 las desbloquee.

---

## Plan de migración por fases

La migración es incremental: el piloto AMX no puede pararse. El núcleo de dominio (skills,
contexto editorial, MCP) viaja sin cambios; lo que se mueve por fases es el runtime.

### Fase 0 — Estabilizar el modelo actual (interino)

Mantener el piloto en pie mientras se construye el servicio. Endurecer lo mínimo de #137 (no
sobre-invertir: es código que se va a borrar). **Criterios de aceptación:**

- Un wall-timeout o una cancelación **no deja procesos huérfanos** (subprocesos en su propio
  grupo de procesos; el `kill` mata el árbol).
- La cola **rechaza con backpressure** por encima de un tope configurable, en vez de acumular
  hilos sin límite.

### Fase 1 — Backend compartido con auth (sin tocar la generación)

Desplegar la Consola como servicio compartido con autenticación multiusuario, accesible por
navegador y móvil. La generación **sigue** por `claude -p` por debajo (aún no migrada).
**Criterios de aceptación:**

- Dos usuarios distintos entran desde **navegadores/dispositivos distintos** (incluido móvil)
  con **sesiones autenticadas** separadas; un usuario sin sesión válida recibe 401.
- Las mutaciones rechazan peticiones cross-site (CSRF/`Origin` verificado). Cierra #134.
- El estado (borradores, historial) es **compartido y atribuido por usuario**: A ve lo suyo
  como suyo y, según permisos, lo del equipo. Ningún miembro necesita el repo de dev en disco
  ni Claude Code instalado para *entrar* (avance sobre #133).

### Fase 2 — Generación vía API de Claude (SDK) + cuota por usuario

Sustituir el subproceso `claude -p` por llamadas a la API de Claude con clave central, e
introducir presupuesto/cuota de tokens por usuario. **Criterios de aceptación:**

- Generar copy **no requiere `claude` en el PATH** de la máquina (la del usuario ni la del
  servidor en modo CLI): `shutil.which("claude")` deja de estar en el camino crítico.
- Cada generación **registra los tokens consumidos** atribuidos a un usuario; existe un
  **presupuesto por usuario** y, al agotarse, se le bloquea con un aviso claro **sin afectar a
  los demás** (resuelve el adoption killer del hecho 3).
- El **runner de subprocesos queda retirado** del camino de generación; **#137 se cierra** por
  obsolescencia (su componente ya no existe).

### Fase 3 — Funciones de equipo sobre estado compartido

Sobre el runtime ya migrado, construir scheduling, cola de aprobación de equipo y dashboard
(#9). **Criterios de aceptación:**

- Una pieza pasa por **estados de aprobación** entre miembros (autor → revisor → publicable)
  con el estado visible para todo el equipo.
- Se puede **programar** una publicación y el sistema la ejecuta en su franja, 24-7, sin la
  máquina de nadie encendida.
- Multi-cliente: un segundo cliente (más allá de AMX) se da de alta **sin hardcodear marcas**
  (coordina con #135), validando la promesa "reutilizable entre clientes".

---

## Enlaces

- #130 — Runtime no apto para equipo (esta decisión)
- #137 — Robustez del runner (medida interina; se descarta al migrar)
- #134 — Consola sin auth ni CSRF (se absorbe en el servicio compartido)
- #133 — Distribución rota (la solución de fondo es el servicio compartido)
- #9 — Fase 3: scheduling + cola de aprobación de equipo + dashboard (habilitada por esta decisión)
- #5 — Meta App Review + cuentas reales de AMX (paralelo; gating externo)
- Épica #140 — Auditoría de arquitectura: ¿sirve la arquitectura al objetivo del producto?
