# ADR 0001 — Runtime: servicio compartido multiusuario con `claude -p`

keni-social es una herramienta de producción de uso diario para un equipo de redes
no-técnico, reutilizable entre clientes: convertir una nota, un clip o una tendencia en copy
publicable —con voz de marca, tropicalización MX, formato por plataforma y auto-verificación—
y leer métricas multi-marca y multi-plataforma, sin CLI ni entorno de desarrollo. La filosofía
es capacidad, no dependencia.

## Principios de runtime

1. **Servicio compartido multiusuario.** Un solo backend al que el equipo entra por navegador
   (PC corporativo o móvil), sin instalar nada y sin pasar por IT. No es una app local por
   persona: nada de bind a `127.0.0.1` como modelo de acceso, ni Claude Code en la máquina del
   usuario, ni estado atado a un portátil.

2. **Auth multiusuario de primera clase.** Identidad por usuario, sesión, y protección
   CSRF/`Origin` en las mutaciones. El control de acceso es explícito, no un efecto del bind de
   red.

3. **Estado compartido y atribuido por usuario** (borradores, cola de aprobación, historial,
   publicaciones) según permisos. Habilita el flujo de equipo: estados de aprobación entre
   miembros, programación de publicaciones 24-7 sin la máquina de nadie encendida, y alta de
   nuevos clientes sin hardcodear marcas.

4. **Generación con `claude -p` mientras sea la opción más barata.** El copy se produce ejecutando
   `claude -p` (stream-json, token a token), aprovechando el harness de Claude Code (tool use,
   contexto editorial inyectado en el prompt). Los prompts son autocontenidos —la línea
   editorial y la entrada viajan dentro del prompt— y corren con un cwd neutro. El back **encola**
   los jobs y un **worker** aparte los **ejecuta**; el back no lanza `claude -p` en su propio
   proceso (ver [ADR 0002](0002-descomposicion-monolito-modular-catalogo-apps.md)). Esto es una
   decisión económica vigente —no un invariante de arquitectura—: la suscripción de Claude Code
   sale más barata que el coste por token de la API/SDK, y el motor de generación queda contenido
   detrás del worker, de modo que el resto del sistema no depende de cuál sea.

5. **Coste por suscripción global, no por saldo individual.** La generación corre contra una
   suscripción de Claude Code única (OAuth de la máquina), de modo que no hay saldo por persona
   que se agote. Tokens/coste/duración por job y usuario son observabilidad, nunca un gate de
   adopción.

## Invariantes que el resto del sistema asume

- **La disciplina de subproceso es permanente mientras la generación corra por subproceso.**
  Mientras el copy se produzca lanzando un proceso externo (hoy `claude -p`), ese runner se
  endurece sin excepción: lanzar en su propio grupo de procesos y **matar el árbol completo**
  (no dejar procesos sueltos) en timeout o cancelación, y no tragar excepciones. La concurrencia
  tiene un tope de huecos en ejecución; los jobs que no caben esperan en cola. El detalle de
  límites y backpressure es del código, no de este ADR. Lo invariante es esta disciplina, no el
  motor concreto: si el motor cambiase, la disciplina de subproceso aplica igual a lo que haya.

- **La IP de dominio es ortogonal al runtime.** La lógica que produce copy y los datos
  editoriales, la abstracción `FuenteMetricas` y su MCP, y la base común `keni-shared` (marcas,
  cuentas, esquema, normalización) no dependen del modelo de despliegue. Mover el runtime no
  toca el núcleo que produce y mide.

## Estado
Decisión de fase — producto en validación (piloto AMX). Revisable; no es ley permanente.

## Revisar cuando
- La suscripción de Claude deje de ser más barata que el coste por token de la API (entonces, y solo entonces, reconsiderar el motor de generación).
- Se necesiten capacidades que el CLI no ofrezca y la API/SDK sí (p. ej. salidas estructuradas o Batch) y su valor supere el coste de suscripción.
