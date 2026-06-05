# Auditoría nocturna — production readiness

Trabajo autónomo (~8h) mientras el equipo duerme. Objetivo: dejar keni-social
production-grade. Prioridad: **seguridad y fiabilidad**, luego rendimiento/escala.

Mandato (decisiones del owner antes de dormir):
- Push directo a `main` de todo (CI valida).
- MFA: implementar **detrás de un flag** (opt-in/desactivado por defecto).
- App + servidor son míos esta noche; nadie más toca. App aún sin uso real →
  downtime/pérdida de datos NO es preocupación. SSH/restart/load-test permitidos.
- ~8h. Production-grade = prioridad.

## Bitácora
- Worktree: `audit-prod-ready` en `/Users/mm/projects/keni-social-audit`.

## Hallazgos — Ola 1 (7 auditorías read-only)

Veredicto general: base madura y consciente de seguridad. Lo de abajo es
endurecimiento + unos pocos huecos realmente explotables.

### Seguridad
- **[HIGH] env completo al subproceso `claude -p`** — `generaciones.py:504-526` (`_entorno_skill` hace `dict(os.environ)`) pasa `CLAUDE_CODE_OAUTH_TOKEN`, `S3_SECRET_KEY`, `DATABASE_URL`/`POSTGRES_PASSWORD` al modelo, que corre con `--dangerously-skip-permissions` y solo veta `Bash` (`config.py:768`). `Read`+`WebFetch` siguen activos → cadena de exfiltración bajo prompt-injection. Fix: scrub de secretos del env + desactivar WebFetch/WebSearch/Read en flujos de copy. NO-BRAINER (scrub).
- **[HIGH] breakout del delimitador `</contenido_usuario>`** — `dominio/generar.py:45-55` inserta el cuerpo crudo; un RSS/nota malicioso cierra el tag e inyecta instrucciones top-level. Fix: tag con nonce aleatorio + neutralizar el cierre. NO-BRAINER.
- **[HIGH] IDOR cross-marca sistémico** — brand-scope solo cableado en 3 de ~55 módulos. Editor de UnoTV puede editar/aprobar/PUBLICAR(Metricool)/borrar piezas de Claro Sports y leer sus métricas. Reconocido-diferido en ADR 0003. Fix: hacer brand-scope el DEFAULT (intersección server-side) + check de propiedad por `{id}`. Grande, dedicado.
- **[MED] sin allowlist de tools por flujo** (copy no necesita tools). `runner.py:95-125`.
- **[MED] input autogen sin truncar a MAX_TEXTO** — `autogen_copy.py:168` / `dominio/generar.py`. NO-BRAINER (cap en el sink).
- **[LOW] 500 filtra `type(exc).__name__`** — `observabilidad.py:224`. NO-BRAINER.
- **[LOW] timing: rama de cuenta bloqueada salta scrypt** — `auth/usuarios.py:438`. NO-BRAINER.

### MFA — implementar detrás de flag `KENI_CONSOLA_MFA` (TOTP). Plan: `auth/mfa.py` nuevo + 3 columnas en `usuarios` + gate de elevación en `api/auth.py` (pre-auth cookie 5min → `/api/auth/mfa/verify`). Con flag off, comportamiento idéntico a hoy.

### Fiabilidad (frontend)
- **[HIGH] sin manejo de 401 a media sesión** — `hooks/use-sesion.tsx` solo corre en mount; sesión expirada deja la página rota en vez de volver a login. Fix: `QueryCache`/`MutationCache` onError global. NO-BRAINER.
- **[MED] sin timeouts en fetch** — `lib/api.ts:421`; back/worker colgado = spinner infinito. NO-BRAINER.
- **[LOW] FeedIdeacion sin botón reintentar** — `FeedIdeacion.tsx:352`. NO-BRAINER.
- **[LOW] `mensajeError` duplicado en ~30 ficheros** — centralizar en `lib/api.ts`. NO-BRAINER.

### Concurrencia
- **[HIGH] aprobación TOCTOU** (doble-aprobar / aprobar-tras-rechazar / lost update) — `aprobacion.py:97-129` + `db.py:7814` UPDATE ciego. Fix: CAS `WHERE decision='pendiente'`. NO-BRAINER (el CAS de nivel).
- **[HIGH] cap de `claude -p` por-proceso, no global** — `--scale worker=N` multiplica sin techo de flota. Documentar/mover al layer de cola.
- **[HIGH] slots de parrilla sin UNIQUE → doble-booking** — `publicaciones.py:396-457`. Fix: UNIQUE `(marca,red,fecha_programada)` + retry / advisory lock.
- **[MED] re-reclaim de job huérfano duplica output** (drafts/veredictos no idempotentes). `db.py:9396`.
- **[MED] daemons sin single-flight cross-proceso** — `daemons.py` + endpoint on-demand comparte fn → sweeps duplican. Fix: `pg_try_advisory_lock`.
- **[MED] versionado `MAX(version)+1` con índice no-UNIQUE → versiones duplicadas** — `db.py:5409,7646`. NO-BRAINER (UNIQUE + retry).
- **[MED] sin idempotencia al lanzar generación** (doble-click → 2 runs). `dominio/generar.py:161`.
- **[LOW] rota swap sin guard de doble-apply** — `db.py:9166`. NO-BRAINER.
- **[LOW] enviar_a_revision/programar TOCTOU** — `aprobacion.py`.

### Rendimiento / escala
- **[CRIT] sin pool de conexiones Postgres** — `motor_db.py:178`/`db.py:245`; connect+auth por operación, techo `max_connections=100`. Alta prioridad, no no-brainer.
- **[CRIT] sin límites de RAM/CPU en contenedores** — un `claude -p` o Garage pesado puede OOM-matar Postgres. NO-BRAINER (solo compose).
- **[HIGH] N+1 Metricool + cache reads en piezas-rendimiento** — `metricas_pieza.py:163` + cliente httpx nuevo por pieza.
- **[HIGH] queries de tablero sin LIMIT** — `db.py:4114`/`4650`; crecen para siempre.
- **[HIGH] actividad globea y parsea TODOS los YAML** — `generaciones.py:323`; sin retención.
- **[MED] `/api/skills/historial` ignora su paginación** — `api/historial.py:50`. NO-BRAINER.
- **[MED] series de métricas sin LIMIT** — `db.py:2741`.
- **[MED] sin healthchecks en front/worker/files/mcp** — `deploy/docker-compose.yml`. NO-BRAINER (compose).

## Preguntas para el owner (mañana)
(pendiente — se rellena con dudas que surjan)

## Cambios pusheados a main
(se registra al promover cada lote)
