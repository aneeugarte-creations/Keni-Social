# Operación: resiliencia, observabilidad y backups

Qué vigila al sistema, qué lo recupera solo y dónde lo ve el humano. Escrito tras el
overhaul de operación (2026-06). Complementa `despliegue-hosted.md` (cómo se despliega)
y `deploy/host/README.md` (instalación de los artefactos de host).

## El principio

El humano ve y controla todo lo que la máquina hace sola, sin entrar por ssh. La señal
operativa vive en el **panel Sistema** (avatar → Sistema, solo admin); el host se
defiende solo (autoheal, systemd, alertas) y deja rastro consultable.

## Capas de resiliencia (de dentro afuera)

| Capa | Mecanismo | Cubre |
|---|---|---|
| Proceso | `restart: unless-stopped` en todos los servicios | proceso que MUERE |
| Salud | healthchecks + sidecar `autoheal` (label `autoheal=true`) | proceso vivo pero COLGADO |
| Cola | claim `FOR UPDATE SKIP LOCKED` + re-reclamo de sueltos + re-encolado en el apagado del pool (`stop_grace_period: 30s` del worker) | jobs sin perder ni duplicar tras reinicio/deploy/OOM |
| Daemons | bucles gateados que capturan excepciones + reaper de generaciones atascada | barridos que fallan sin matar el hilo; sueltos "Generando…" |
| Deploy | verificación de salud post-`up` (back, front, daemons, worker) con **rollback automático** a `:previa` | una imagen rota no se queda en prod |
| Host | timers systemd: backup (03:30) + janitor (00:10) + alertas (cada 10 min) | disco, backups, certificado, contenedores no sanos |

### Healthcheck del servicio `daemons`

El proceso `python -m keni_consola.daemons` toca un **fichero de latido**
(`/tmp/keni-daemons.latido`, env `KENI_DAEMONS_LATIDO_FICHERO`) cada 30 s desde su bucle
principal. El healthcheck del contenedor comprueba el mtime (>120 s = colgado) y autoheal
lo reinicia. Sin dependencia de la BD: un Postgres caído no marca unhealthy a los daemons.

## Latidos de daemons (tabla `daemon_latidos`)

Cada daemon de fondo deja un latido persistido vía la fachada best-effort
`latidos.py` (un latido JAMÁS rompe un barrido; sin BD es no-op):

- los 10 daemons gateados quedan instrumentados automáticamente en
  `daemon_util.bucle_gateado` (nombre derivado del módulo del sweep);
- los 4 bucles fijos (comercial, metricas, metricas_piezas, programador) registran
  explícitamente.

`GET /api/sistema/daemons` (admin) juzga cada daemon con el umbral derivado de su
`tick_seg` persistido: **ok / error / inactivo / atrasado**. "Atrasado" = hilo muerto,
proceso daemons caído o BD inaccesible para él.

## Panel Sistema (avatar → Sistema)

- **Banner de alertas**: sintetiza disco ≥85 %, daemons atrasados/en error, backup
  atrasado o fallido, cola llena, presupuesto de tokens agotado / kill switch, S3 en
  error. Sin problemas, no aparece.
- **Recursos**: CPU / RAM / discos.
- **Cola y gasto de IA**: lectura del contrato `/api/actividad/cola` (en curso,
  esperando, slots, workers; tokens gastados hoy, % del presupuesto, nivel de corte).
  Las ACCIONES (purgar, re-encolar, toggles de daemons, kill switch) viven en el
  Monitor de Actividad IA, su sitio natural.
- **Daemons de fondo**: la tabla de latidos de arriba.
- **Backups locales**: último run (`estado.json`), verificación, edad del último dump
  (>26 h = atrasado), tamaños.
- **Rendimiento de la API**: agregador en memoria alimentado por `RegistroPeticiones`
  (TTFB por ruta normalizada, ventana de 256 muestras; p50/p95/max y 5xx). Se reinicia
  con cada deploy del back.
- **S3/Garage**: salud del bucket + explorador.

## Backups (verificados)

`deploy/backup/keni-backup.sh` (timer diario 03:30 UTC):

1. `pg_dump -Fc` del Postgres (operacional + editorial estructurado).
2. **Verificación**: `pg_restore --list` del dump recién escrito (detecta truncados).
3. tar.gz de los 3 volúmenes de estado + `gzip -t` de cada uno.
4. `estado.json` atómico con el resultado (lo muestra el panel; el back monta
   `/var/backups/keni-social` en `/backups` SOLO LECTURA).
5. Retención 14 días. Fallo en cualquier paso → unidad failed → `OnFailure=` dispara
   keni-alertas (journal `err` + webhook opcional).

Restore COMPLETO probado el 2026-06-10 en un Postgres efímero (58 tablas, filas reales).
Receta en `deploy/host/README.md` §1; repetir tras cambios grandes de esquema.

**Límite honesto**: backup local en el mismo disco. Para offsite: `BACKUP_RCLONE_REMOTE`
en `/etc/keni-backup.conf`.

## Higiene de disco

`deploy/janitor/keni-janitor.sh` (timer diario):
- conserva las 5 imágenes más recientes por repo `keni-social/*`;
- **capa el build cache a 15 GB** (`BUILD_CACHE_KEEP`) aunque el disco vaya sobrado
  (2026-06: había 41 GB acumulados con el disco al 9 %);
- prune agresivo solo si el disco supera el 50 %;
- purga de respaldo de registros de generación >30 días (la vía principal es el reaper).

Logs de contenedores capados por daemon.json (`max-size: 50m`, `max-file: 5`).

## Alertas de host (sin servicios externos)

`keni-alertas.timer` (cada 10 min, instalado 2026-06-10): contenedores no sanos
(incluido `db`, excluido de autoheal a propósito; `daemons` cuenta como "con
healthcheck" desde el fichero de latido), disco >85 %, backup >26 h, certificado TLS
<15 días. Siempre al journal (`journalctl -p err -t keni-alertas`); webhook opcional en
`/etc/keni-alertas.conf`.

## Rendimiento

- gzip ON en el nginx del front (2026-06: el bundle `index-*.js` viajaba en crudo,
  704 KB → ~212 KB).
- Latencias de la API visibles en el panel (sección Rendimiento).
- Pendiente conocido (no urgente): pool de conexiones Postgres (hoy cada operación
  abre/cierra la suya; `max_connections=200` lo absorbe).
