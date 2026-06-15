# ADR 0001 — Runtime y generación: servicio compartido multiusuario con `claude -p` en sandbox por usuario

- **Estado:** Aceptado
- **Fecha:** 2026-05-27
- **Decisores:** equipo keni-social (auditoría de arquitectura, épica #140)
- **Issues:** #130 (esta decisión) · #137 · #134 · #133 · #9
- **Componente:** `consola/` (runtime, generación y modelo de despliegue)

> **Sobre los ADR en este repo.** Numeración incremental de cuatro dígitos (`0001-…`, `0002-…`). Un
> ADR registra una decisión de arquitectura con su contexto, su decisión y sus consecuencias.
> **Política de consolidación:** el ADR contiene **solo decisiones aceptadas** — sin sección de
> alternativas rechazadas. Cuando una decisión se revierte, **se reescribe el ADR afectado** para
> reflejar lo vigente y **se elimina el razonamiento ya descartado**; un límite relevante ("se usa X,
> no Y") se enuncia de forma **positiva dentro de la decisión**, no como una alternativa en conflicto.
> El objetivo es que quien lea el ADR (persona o agente) no resucite preguntas ya resueltas. La traza
> histórica fina vive en git, no en el cuerpo del ADR.

> **[Nota de estado]** La **decisión de runtime sigue vigente** (servicio compartido multiusuario +
> generación con `claude -p` en sandbox por usuario, no la API/SDK de Claude). Lo que cambió desde
> entonces: el **sistema de skills** (`SKILL.md`, `dominio/skills.py`, resolución de skills) se
> **retiró** y se reemplazó por la **Texto de prompts** (`texto.py`) + lanzador neutro
> (`dominio/generar.py`) y el **Estudio** de imagen. Donde abajo se lea "plugin/skills" / "`SKILL.md`"
> como mecanismo de generación, léase hoy "prompts autocontenidos de la Texto, lanzados con
> `claude -p`". El razonamiento del runtime no cambia.

---

## Contexto

### Objetivo del producto

keni-social aspira a ser una **herramienta de producción de uso diario por un equipo de redes** (no
por un operador técnico), **reutilizable entre clientes**. La promesa de diseño es "botones en vez de
comandos": que un community manager no-técnico convierta una nota, un clip o una tendencia en copy
publicable —con voz de marca, tropicalización MX, formato por plataforma y auto-verificación— y lea
métricas multi-plataforma y multi-marca, sin pelearse con una CLI ni montar un entorno de desarrollo.
La filosofía es **capacidad, no dependencia**.

### Tres hechos del piloto AMX que condicionan el runtime

La auditoría de arquitectura (#140) contrastó el diseño con las conversaciones de entrega del piloto
(Bernardo Vázquez, Elías, Diana Ramos). Tres hechos duros del campo condicionan la decisión:

1. **Máquinas corporativas bloqueadas + IT cuello de botella.** Bernardo: *"con todos los equipos van
   a tener ese problema… con IT también tenemos que hablar."* No se puede instalar Claude Code, clonar
   el repo y correr `npm run build` en cada máquina del equipo.

2. **Multiusuario / móvil / 24-7.** Hay cuentas compartidas ("una licencia para tres": Tescu/Luis/Roger
   rotan un PC por horario). Elías quiere acceder *"desde el móvil"*; Bernardo quiere automatizar el
   flujo de presidencia el fin de semana, también desde el móvil. Una app que solo escucha en
   `127.0.0.1` del portátil de una persona no da móvil, ni 24-7, ni estado compartido.

3. **Coste de tokens (adoption killer si recae en saldos individuales).** Bernardo: *"como se le acabe
   el saldo, no la van a usar. La de 20 dólares no va a dar para un día entero."* El coste **no puede**
   recaer en saldos por persona que se agotan.

### Estado de partida (lo que había)

La Consola nació como app **Starlette single-process, single-user**, corriendo en el portátil de cada
persona y generando copy con `claude -p` como **subproceso local**. Es la arquitectura correcta para
*un operador técnico* (el facilitador del piloto), pero no para el objetivo declarado: bind a
`127.0.0.1` (`__main__.py`), exige `claude` en el PATH de cada máquina (`generaciones.py`,
`shutil.which("claude")`), persistencia local sin multiusuario (`db.py`, `~/.config/keni-social/`),
y resolución de skills atada al repo de dev en disco (`dominio/skills.py`, #133).

---

## Decisión

Runtime = **servicio compartido multiusuario**, conservando la IP de dominio, con la generación por
**`claude -p` en sandbox por usuario**. Propiedades de primera clase:

1. **Servicio compartido** (un backend, accesible por navegador/móvil), no una app local por persona.
   Un solo despliegue al que el equipo entra desde el navegador del PC corporativo o del móvil, sin
   instalar nada. Mata el cuello de IT (hecho 1) y habilita móvil/24-7 (hecho 2).

2. **Auth multiusuario** de primera clase: identidad por usuario, sesión y protección CSRF/`Origin` en
   las mutaciones (el bind a `127.0.0.1` no era control de acceso). Absorbe #134.

3. **Generación con `claude -p` en un sandbox por usuario** en `code.kenitech.io`, contra una
   **suscripción de Claude Code global**. El gateway **despacha** el job al sandbox del usuario y
   **consume el stream-json** (token a token) para la UI; **no** ejecuta `claude -p` en su propio
   proceso. Se conserva el modelo de plugin/skills (flujo `SKILL.md`, contexto editorial, whisper
   local, tool use del harness) **sin reimplementarlo**: la generación es **`claude -p`**, no la API de
Claude (SDK). El sandbox por usuario aísla procesos, datos
   y credenciales por persona, y se alinea con los hallazgos de seguridad ya cerrados (#127–#129).

4. **Coste por suscripción global**, no por saldo individual: no hay saldo por usuario que se agote
   (resuelve el hecho 3). La visibilidad de tokens/coste/duración por usuario y job es
   **observabilidad** (página "Actividad IA"), no un gate de adopción.

5. **Estado compartido** entre miembros (borradores, cola de aprobación, historial, publicaciones)
   según permisos, no aislado por máquina. Habilita #9.

La **IP de dominio** —skills de copy, contexto editorial versionado, la abstracción `FuenteMetricas` y
`keni-shared`— se conserva intacta: el cambio es de **runtime y modelo de despliegue**, no del núcleo
que produce y mide.

---

## Consecuencias

### IP que se conserva (no se toca)

- **Skills de copy** y **contexto editorial versionado**: la lógica que produce el copy y los datos
  editoriales son independientes del runtime. La generación se sigue invocando por `claude -p` (ahora
  dentro del sandbox), **misma IP**.
- **Abstracción `FuenteMetricas`** y su jerarquía + el **MCP de métricas**: sin cambios.
- **`keni-shared`**: base común (marcas, cuentas, esquema YAML, normalización).

### Robustez del runner (#137) es deuda **permanente**

Como la generación sigue siendo subprocesos `claude -p` (en el sandbox), el runner de subprocesos
**no desaparece**: hay que endurecerlo bien y de forma permanente — cola con tope/backpressure, lanzar
en su propio grupo de procesos y **matar el árbol completo** en timeout/cancelación (sin sueltos), y
no tragar excepciones. **#137 es permanente, no interina.**

### Distribución (#133): resuelta

El sandbox lleva las skills y Claude Code; el usuario entra **por navegador** sin clonar el repo ni
instalar el plugin. El fallback de `cwd_skills()` queda como parche solo para usuarios técnicos locales.

### Privacidad: en hosted, "local" pasa a "en tu sandbox"

La transcripción whisper corre en la máquina (modo local) o en el **sandbox del usuario en Keni infra**
(modo alojado). El audio sale del portátil a su sandbox propio, **no a un tercero**. Detalle y
distinción de modos en [`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md).

### Dependencia de Claude Code: reubicada, no eliminada

Vive en el **sandbox** (preinstalado y autenticado contra la suscripción global), no en la máquina del
usuario.

### Impacto en issues

- **#134 (auth/CSRF):** se absorbe — el servicio multiusuario la necesita de todas formas.
- **#9 (Fase 3: scheduling + cola de aprobación + dashboard):** **habilitada** — requiere el estado
  compartido y multiusuario que provee este runtime; #9 es su consumidor.
- **#5 (publicación/métricas reales + cuentas reales):** en paralelo; ni se desbloquea ni se
  bloquea aquí. La publicación y las métricas reales llegan **vía Metricool** (una integración para
  FB/IG/X/TikTok/YouTube), así que la última milla es trabajo de código interno, no un trámite
  externo. El servicio alojado encaja igualmente con esa ruta.

---

## Plan de migración por fases

Incremental: el piloto AMX no puede pararse. El núcleo de dominio (skills, contexto editorial, MCP)
viaja sin cambios; lo que se mueve por fases es el runtime.

### Fase 1 — Backend compartido con auth

Desplegar la Consola como servicio compartido con auth multiusuario, accesible por navegador y móvil.
La generación **sigue** por `claude -p` por debajo (aún en local, no en sandbox). **Criterios:**

- Dos usuarios entran desde **dispositivos distintos** (incluido móvil) con **sesiones autenticadas**
  separadas; sin sesión válida → 401.
- Las mutaciones rechazan peticiones cross-site (CSRF/`Origin`). Cierra #134.
- El estado (borradores, historial) es **compartido y atribuido por usuario**; nadie necesita el repo
  de dev ni Claude Code para *entrar* (avance sobre #133).

### Fase 2 — Generación en sandbox por usuario (`code.kenitech.io`)

- Provisionar **sandbox por usuario** con Claude Code preinstalado y autenticado contra la
  **suscripción global**; el sandbox lleva las skills.
- El **gateway despacha** la generación al sandbox y **transmite el stream-json** a la UI.
- **Endurecer el runner (#137) como permanente:** cola con tope, grupo de procesos propio, kill del
  árbol, sin sueltos.
- **Criterios:**
  - Generar copy **no requiere `claude` en la máquina del usuario** (corre en su sandbox); entra por
    navegador/móvil con sesión autenticada.
  - Un timeout o cancelación **no deja procesos sueltos** en el sandbox.
  - La cola **rechaza con backpressure** por encima de un tope configurable.
  - "Actividad IA" muestra **tokens/coste/duración por job y usuario** (observabilidad, no bloqueo).

### Fase 3 — Funciones de equipo sobre estado compartido (#9)

- Una pieza pasa por **estados de aprobación** entre miembros (autor → revisor → publicable), visibles
  para todo el equipo.
- Se puede **programar** una publicación y el sistema la ejecuta en su franja, 24-7, sin la máquina de
  nadie encendida.
- **Multi-cliente:** un segundo cliente se da de alta **sin hardcodear marcas** (coordina con #135).

---

## Enlaces

- #130 — Runtime no apto para equipo (esta decisión)
- #137 — Robustez del runner (**deuda permanente**; el runner de subprocesos se conserva)
- #134 — Consola sin auth ni CSRF (se absorbe)
- #133 — Distribución rota (resuelta por el servicio + sandbox)
- #9 — Fase 3: scheduling + cola de aprobación + dashboard (habilitada)
- Publicación/métricas reales + cuentas reales (paralelo; vía Metricool, trabajo interno)
- [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md) — Descomposición (complementa esta decisión)
- Épica #140 — Auditoría de arquitectura
- [`../flujo-de-datos-privacidad.md`](../flujo-de-datos-privacidad.md) — modos local vs alojado
