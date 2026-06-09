"""Configuracion CENTRAL de la Consola Keni: fuente UNICA de las env vars `KENI_*`.

Antes cada modulo leia sus `os.environ.get("KENI_...")` por su cuenta (~30 lecturas
dispersas), repitiendo el nombre de la var, su default y el parseo. Este modulo las
CENTRALIZA: declara cada nombre de variable UNA vez (constantes `ENV_*`) y expone un
accesor por variable que encapsula su default, su tipo y su precedencia. Los modulos
llaman al accesor en vez de tocar `os.environ` directamente.

POR QUE ACCESORES (y no constantes leidas al importar): la configuracion se lee SIEMPRE
en tiempo de LLAMADA, nunca al importar el modulo. Los tests aislan cada recurso con
`monkeypatch.setenv(...)` ANTES de invocar el codigo; si el valor se capturara al
importar, ese aislamiento no funcionaria. Por eso cada accesor hace su `os.environ.get`
al ser llamado.

QUE NO HACE (a proposito, para no cambiar comportamiento):
  - NO renombra ninguna `KENI_*` ni cambia defaults/precedencia: es centralizacion, no
    rename. Un deploy que ya fija las vars actuales sigue funcionando igual.
  - NO resuelve las RUTAS de estado: la PRECEDENCIA de rutas (var especifica del recurso
    > `KENI_DATA_DIR` > `${XDG_CONFIG_HOME:-~/.config}`) vive en `rutas.py`, que es el
    sitio historico de esa logica. Aqui solo se centraliza el NOMBRE de cada var de ruta
    (constante `ENV_*`) y el accesor del OVERRIDE especifico (`override_ruta`), que cada
    modulo de ruta usa como su override de maxima prioridad. `rutas.data_dir()` sigue
    siendo quien compone el fallback.

CATALOGO de variables (todas opcionales salvo que se diga). Agrupadas por area:

  Arranque / red (`__main__`):
    - KENI_CONSOLA_HOST            host de bind                       def 127.0.0.1
    - KENI_CONSOLA_PORT            puerto                             def 8765

  Auth / sesion / CSRF (`seguridad`, `auth`):
    - KENI_CONSOLA_TOKEN          token interino OPCIONAL (gate extra) def (modo local genera uno)
    - KENI_CONSOLA_ORIGENES       hosts externos permitidos (CSRF tras proxy) def (solo el Host)
    - KENI_CONSOLA_COOKIE_SECURE  cookies Secure (flag)              def derivado de HTTPS
    - KENI_CONSOLA_HTTPS          vamos tras TLS (flag)              def off
    - KENI_CONSOLA_SESION_HORAS   duracion de sesion (horas)         def 12
    - KENI_CONSOLA_SESION_MAX_HORAS  tope ABSOLUTO de vida de sesion (horas) def 720 (30 d)
    - KENI_CONSOLA_ADMIN_USER     usuario del admin de bootstrap     def "admin"
    - KENI_CONSOLA_ADMIN_PASS     contrasena del admin de bootstrap  def (genera una)

  Observabilidad (`observabilidad`):
    - KENI_CONSOLA_LOG_LEVEL      nivel de log                       def INFO

  Concurrencia de jobs (`dominio.runner`):
    - KENI_MAX_JOBS               jobs `claude` simultaneos          def 4   (min 1)
    - KENI_MAX_COLA               jobs esperando un slot             def 16  (min 0)

  Cola + worker de generacion (#130 Fase 2 / ADR 0002 Fase B; `cola`, `worker`):
    - KENI_WORKER_EXTERNO         hay un servicio `worker` aparte    def OFF (worker in-proceso)
    - KENI_WORKER_SONDEO_SEGUNDOS intervalo de sondeo de la cola (s) def 0.5  (min 0.05)

  Generacion `claude -p` (`generaciones`, `dominio.stream`):
    - KENI_CLAUDE_TIMEOUT         wall-timeout de un job (s)         def 600
    - KENI_CLAUDE_MAX_USD         tope de coste (--max-budget-usd)   def sin tope
    - KENI_CLAUDE_MAX_TURNS       tope de turnos (--max-turns)       def sin tope
    - KENI_CLAUDE_SKIP_PERMISSIONS  saltar permisos (--dangerously-skip-permissions)  def ON

  Texto de prompts + linea editorial (`texto`, `dominio.texto_lanzar`):
    - KENI_TEXTO_DIR         almacen de documentos markdown     def <dir_config>/texto

  Programadores en segundo plano (`comercial`, `programador`):
    - KENI_COMERCIAL_INTERVALO_SEGUNDOS  intervalo captura (s)       prioridad sobre horas
    - KENI_COMERCIAL_INTERVALO_HORAS     intervalo captura (h)       def INTERVALO_HORAS_DEF
    - KENI_PROGRAMADOR_INTERVALO_SEGUNDOS  intervalo barrido (s)     def INTERVALO_SEGUNDOS_DEF
    - KENI_METRICAS_REFRESCO_HORAS       refresco cache metricas (h) def 4   (min 1)
    - KENI_METRICAS_PIEZAS_REFRESCO_HORAS refresco cache POR PIEZA (h) def 4 (min 1)
    - KENI_ALERTAS_RENDIMIENTO_HORAS     barrido alertas rendim. (h) def 6   (min 1)
    - KENI_ALERTAS_RENDIMIENTO           apaga el barrido de alertas def ON
    - KENI_ALERTAS_UMBRAL_ENGAGEMENT     umbral bajo rendim. (%)     def 1.0

  Imagen / secretos (`secretos`, `media`): la precedencia fichero>env vive en
  `secretos.py`; aqui se declaran solo los nombres (no hay accesor central porque el
  fichero de secretos participa en la decision):
    - KENI_IMAGEN_API_KEY, KENI_IMAGEN_PROVEEDOR  (+ OPENROUTER_API_KEY/OPENAI_API_KEY)

  Persistencia (#130 / ADR 0004): la operacional (tareas/comercial/rota/usuarios/sesiones/
  jobs) va SIEMPRE a Postgres -> `DATABASE_URL` es OBLIGATORIA (local o hosted). La media va
  a object storage S3/Garage si se cablean las `S3_*`; si no, sigue en disco. Los NOMBRES
  son los que ya estan en `deploy/docker-compose.yml`/`.env.example` (no se renombran):
    - DATABASE_URL                URL Postgres del back            OBLIGATORIA (ADR 0004)
    - S3_ENDPOINT                 endpoint S3/Garage               (cablea S3 si presente)
    - S3_REGION                   region S3                        def garage
    - S3_BUCKET                   bucket de media                  def keni-media
    - S3_ACCESS_KEY / S3_SECRET_KEY  credenciales S3               (vacias = disco)

  Rutas de estado (override especifico de cada recurso; la composicion del fallback
  vive en `rutas.py`). Nombre centralizado aqui, valor leido via `override_ruta`:
    - KENI_DATA_DIR               raiz unica de estado (contenedor)  -> lo usa `rutas`
    - KENI_CONSOLA_RAIZ           contenido editorial por marca
    - KENI_CONSOLA_INDICE         indice.sqlite (regenerable)
    - KENI_CONSOLA_MEDIA          dir de media (imagenes)
    - KENI_CONSOLA_SECRETOS       secretos.toml
    - KENI_CONSOLA_PREFERENCIAS   preferencias.toml
    - KENI_CONSOLA_SUGERENCIAS    sugerencias.json
    - KENI_CONSOLA_TERMOMETRO     termometro.json
    - KENI_CONSOLA_CONFIG         consola.toml (allowlist de proyectos)
    - KENI_CONSOLA_GENERACIONES   dir de registros de generacion
"""
# config.py es un BARREL: la implementación vive en `_config_comun` + `config_<dominio>`.
# `config.<algo>` y `from .config import X` siguen funcionando sin cambios.

from ._config_comun import (  # noqa: F401
    _FALSOS,
    _VERDADEROS,
    ADMIN_USER_DEF,
    ALERTAS_INTERVALO_HORAS_DEF,
    ALERTAS_UMBRAL_ENGAGEMENT_DEF,
    ALGORITMOS_INTERVALO_HORAS_DEF,
    AUTOGEN_ARTE_MAX_DEF,
    CLAUDE_TIMEOUT_DEF,
    CLUSTER_BREAKING_FUENTES_DEF,
    CLUSTER_BREAKING_VENTANA_H_DEF,
    CLUSTER_UMBRAL_DEF,
    CLUSTER_VENTANA_H_DEF,
    DB_POOL_MAX_DEF,
    DB_POOL_MIN_DEF,
    ENV_ADMIN_PASS,
    ENV_ADMIN_USER,
    ENV_AFP_BASE_URL,
    ENV_AFP_CLIENT_ID,
    ENV_AFP_CLIENT_SECRET,
    ENV_AJUSTES,
    ENV_ALERTAS_ACTIVAS,
    ENV_ALERTAS_INTERVALO_HORAS,
    ENV_ALERTAS_UMBRAL_ENGAGEMENT,
    ENV_ALGORITMOS_AUTO,
    ENV_ALGORITMOS_INTERVALO_HORAS,
    ENV_AUTO_PREAPROBACION,
    ENV_AUTO_PROGRAMAR,
    ENV_AUTOGEN_ARTE,
    ENV_AUTOGEN_ARTE_MAX,
    ENV_TEXTO_DIR,
    ENV_CLAUDE_DISALLOWED_TOOLS,
    ENV_CLAUDE_MAX_TURNS,
    ENV_CLAUDE_MAX_USD,
    ENV_CLAUDE_SKIP_PERMISSIONS,
    ENV_CLAUDE_TIMEOUT,
    ENV_CLUSTER_BREAKING_FUENTES,
    ENV_CLUSTER_BREAKING_VENTANA_H,
    ENV_CLUSTER_UMBRAL,
    ENV_CLUSTER_VENTANA_H,
    ENV_COMERCIAL_INTERVALO_HORAS,
    ENV_COMERCIAL_INTERVALO_SEGUNDOS,
    ENV_CONFIG,
    ENV_CONSOLA_URL_PUBLICA,
    ENV_COOKIE_SECURE,
    ENV_DATA_DIR,
    ENV_DATABASE_URL,
    ENV_DB_POOL,
    ENV_DB_POOL_MAX,
    ENV_DB_POOL_MIN,
    ENV_EVENTOS_INTERVALO_SEGUNDOS,
    ENV_EVENTOS_VENCIMIENTOS,
    ENV_FEED_SLA_MIN,
    ENV_FFMPEG_BIN,
    ENV_FUENTES_BAJA_CONFIANZA,
    ENV_GENERACIONES,
    ENV_GENERACIONES_TTL_HORAS,
    ENV_HOST,
    ENV_HTTPS,
    ENV_IMAGEN_API_KEY,
    ENV_IMAGEN_PROVEEDOR,
    ENV_INDICE,
    ENV_INGESTA,
    ENV_INGESTA_BATCH,
    ENV_INGESTA_INTERVALO_BREAKING,
    ENV_INGESTA_INTERVALO_CIENCIA_TECH,
    ENV_INGESTA_INTERVALO_DEFECTO,
    ENV_INGESTA_INTERVALO_DEPORTES,
    ENV_INGESTA_INTERVALO_GAMING,
    ENV_INGESTA_INTERVALO_INTERNACIONAL,
    ENV_INGESTA_INTERVALO_MX,
    ENV_INGESTA_INTERVALO_TENDENCIAS,
    ENV_INGESTA_MAX_ERRORES,
    ENV_INGESTA_MAX_ITEMS,
    ENV_INGESTA_WORKERS,
    ENV_INSUMOS_MODELO,
    ENV_INVESTIGADOR,
    ENV_INVESTIGADOR_INTERVALO_HORAS,
    ENV_LOG_LEVEL,
    ENV_MAQUINA,
    ENV_MAX_COLA,
    ENV_MAX_JOBS,
    ENV_MCP_BEARER,
    ENV_MCP_USUARIO,
    ENV_MEDIA,
    ENV_MEDIA_GC,
    ENV_MEDIA_GC_ANTIGUEDAD_HORAS,
    ENV_MEDIA_GC_INTERVALO_HORAS,
    ENV_METRICAS_HISTORICO_RETENCION_DIAS,
    ENV_METRICAS_PIEZAS_REFRESCO_HORAS,
    ENV_METRICAS_REFRESCO_HORAS,
    ENV_MFA,
    ENV_MFA_KEY,
    ENV_MIN_APROBACIONES,
    ENV_ORIGENES,
    ENV_PG_DB,
    ENV_PG_HOST,
    ENV_PG_PASSWORD,
    ENV_PG_PORT,
    ENV_PG_USER,
    ENV_PIPELINE,
    ENV_PIPELINE_INTERVALO_HORAS,
    ENV_PIPELINE_MAX,
    ENV_PORT,
    ENV_PREFERENCIAS,
    ENV_PRIORIZA_METRICAS,
    ENV_PRIORIZA_METRICAS_RANGO,
    ENV_PROGRAMADOR_INTERVALO_SEGUNDOS,
    ENV_PUBLICAR_REAL,
    ENV_QA,
    ENV_RAIZ,
    ENV_REAPER_INTERVALO_MIN,
    ENV_REUTERS_API_KEY,
    ENV_REUTERS_BASE_URL,
    ENV_RP_ID,
    ENV_RP_NOMBRE,
    ENV_RP_ORIGIN,
    ENV_S3_ACCESS_KEY,
    ENV_S3_BUCKET,
    ENV_S3_ENDPOINT,
    ENV_S3_REGION,
    ENV_NOTICIAS_GC,
    ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
    ENV_NOTICIAS_GC_INTERVALO_HORAS,
    ENV_NOTICIAS_GC_SCORE_UMBRAL,
    ENV_FUSION_SEMANTICA,
    ENV_FUSION_SEMANTICA_MAX,
    ENV_PERFIL_EDITORIAL,
    ENV_PERFIL_EDITORIAL_TTL_HORAS,
    ENV_RENDIMIENTO_MIN_PIEZAS,
    ENV_RENDIMIENTO_RANKING,
    ENV_RENDIMIENTO_TOP_N,
    ENV_SCORE_PESO_RENDIMIENTO,
    ENV_S3_SECRET_KEY,
    ENV_SCORE_BONUS_BREAKING,
    ENV_SCORE_PESO_CORROBORACION,
    ENV_SCORE_PESO_FRESCURA,
    ENV_SCORE_PESO_MARCA,
    ENV_SCORE_PESO_VIRALIDAD,
    ENV_SECRETOS,
    ENV_SESION_HORAS,
    ENV_SESION_MAX_HORAS,
    ENV_SUGERENCIAS,
    ENV_SUGERENCIAS_EDITORIALES,
    ENV_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS,
    ENV_SUGERENCIAS_EDITORIALES_MAX,
    ENV_TERMOMETRO,
    ENV_TOKEN,
    ENV_TRAD_LOTE,
    ENV_TRAD_MIN_SCORE,
    ENV_TRADUCCION_MAX,
    ENV_TRENDS,
    ENV_TRENDS_GEOS,
    ENV_TRENDS_INTERVALO_MIN,
    ENV_VIDEO_MAX_MB,
    ENV_VIDEO_RENDER_TIMEOUT,
    ENV_WHISPER_MODELO,
    ENV_WORKER_EXTERNO,
    ENV_WORKER_SONDEO_SEGUNDOS,
    EVENTOS_INTERVALO_SEGUNDOS_DEF,
    FEED_SLA_MIN_DEF,
    FFMPEG_BIN_DEF,
    FUENTES_BAJA_CONFIANZA_DEF,
    GENERACIONES_TTL_HORAS_DEF,
    HOST_DEF,
    INGESTA_BACKOFF_TOPE_SEG,
    INGESTA_BATCH_DEF,
    INGESTA_INTERVALO_BREAKING_DEF,
    INGESTA_INTERVALO_CIENCIA_TECH_DEF,
    INGESTA_INTERVALO_DEFECTO_DEF,
    INGESTA_INTERVALO_DEPORTES_DEF,
    INGESTA_INTERVALO_GAMING_DEF,
    INGESTA_INTERVALO_INTERNACIONAL_DEF,
    INGESTA_INTERVALO_MX_DEF,
    INGESTA_INTERVALO_TENDENCIAS_DEF,
    INGESTA_MAX_ERRORES_DEF,
    INGESTA_MAX_ITEMS_DEF,
    INGESTA_WORKERS_DEF,
    INVESTIGADOR_INTERVALO_HORAS_DEF,
    LOG_LEVEL_DEF,
    MAX_COLA_DEF,
    MAX_JOBS_DEF,
    MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
    MEDIA_GC_INTERVALO_HORAS_DEF,
    METRICAS_HISTORICO_RETENCION_DIAS_DEF,
    METRICAS_PIEZAS_REFRESCO_HORAS_DEF,
    METRICAS_REFRESCO_HORAS_DEF,
    MIN_APROBACIONES_DEF,
    PIPELINE_INTERVALO_HORAS_DEF,
    PIPELINE_MAX_DEF,
    PORT_DEF,
    FUSION_SEMANTICA_MAX_DEF,
    NOTICIAS_GC_INACTIVIDAD_HORAS_DEF,
    NOTICIAS_GC_INTERVALO_HORAS_DEF,
    NOTICIAS_GC_SCORE_UMBRAL_DEF,
    PERFIL_EDITORIAL_TTL_HORAS_DEF,
    REAPER_INTERVALO_MIN_DEF,
    RENDIMIENTO_MIN_PIEZAS_DEF,
    RENDIMIENTO_TOP_N_DEF,
    SCORE_PESO_RENDIMIENTO_DEF,
    S3_BUCKET_DEF,
    S3_REGION_DEF,
    SCORE_BONUS_BREAKING_DEF,
    SCORE_PESO_CORROBORACION_DEF,
    SCORE_PESO_FRESCURA_DEF,
    SCORE_PESO_MARCA_DEF,
    SCORE_PESO_VIRALIDAD_DEF,
    SESION_HORAS_DEF,
    SESION_MAX_HORAS_DEF,
    SUGERENCIAS_EDITORIALES_INTERVALO_HORAS_DEF,
    SUGERENCIAS_EDITORIALES_MAX_DEF,
    TRAD_LOTE_DEF,
    TRAD_MIN_SCORE_DEF,
    TRENDS_GEOS_DEF,
    TRENDS_INTERVALO_MIN_DEF,
    VIDEO_MAX_MB_DEF,
    VIDEO_RENDER_TIMEOUT_DEF,
    WHISPER_MODELO_DEF,
    WORKER_SONDEO_SEGUNDOS_DEF,
    Callable,
    Path,
    _crudo,
    _entero,
    _leer_secreto_fichero,
    annotations,
    gate_maquina,
    maquina_activa,
    os,
    quote,
)
from .config_arranque import (  # noqa: F401
    host,
    port,
)
from .config_auth import (  # noqa: F401
    admin_pass,
    admin_user,
    cookie_secure,
    flag_https,
    mcp_bearer,
    mcp_usuario,
    mfa_habilitado,
    mfa_key,
    origenes_permitidos,
    rp_id,
    rp_nombre,
    rp_origenes,
    sesion_horas,
    sesion_max_horas,
    token,
)
from .config_texto import (  # noqa: F401
    texto_dir,
)
from .config_contenido import (  # noqa: F401
    insumos_modelo,
)
from .config_generacion import (  # noqa: F401
    CLAUDE_DISALLOWED_TOOLS_DEF,
    claude_disallowed_tools,
    claude_max_turns,
    claude_max_usd,
    claude_skip_permisos,
    claude_timeout,
)
from .config_hosted import (  # noqa: F401
    database_url,
    db_pool_activado,
    db_pool_max,
    db_pool_min,
    override_ruta,
    s3_access_key,
    s3_bucket,
    s3_configurado,
    s3_endpoint,
    s3_region,
    s3_secret_key,
    video_max_mb,
)
from .config_jobs import (  # noqa: F401
    max_cola,
    max_jobs,
    worker_externo,
    worker_sondeo_segundos,
)
from .config_noticias import (  # noqa: F401
    AFP_BASE_URL_DEF,
    REUTERS_BASE_URL_DEF,
    afp_base_url,
    afp_client_id,
    afp_client_secret,
    afp_configurado,
    alguna_etapa_pipeline_activa,
    auto_programar_activo,
    autogen_arte_activo,
    cluster_breaking_fuentes,
    cluster_breaking_ventana_h,
    cluster_umbral,
    cluster_ventana_h,
    feed_sla_min,
    fuentes_baja_confianza,
    ingesta_activa,
    ingesta_batch,
    ingesta_intervalo_categoria,
    ingesta_max_errores,
    ingesta_max_items,
    ingesta_workers,
    pipeline_activo,
    pipeline_intervalo_horas,
    pipeline_max,
    qa_activo,
    fusion_semantica_activa,
    fusion_semantica_max,
    noticias_gc_activo,
    noticias_gc_inactividad_horas,
    noticias_gc_intervalo_horas,
    noticias_gc_score_umbral,
    perfil_editorial_activo,
    perfil_editorial_ttl_horas,
    rendimiento_min_piezas,
    rendimiento_ranking_activo,
    rendimiento_top_n,
    reuters_api_key,
    reuters_base_url,
    reuters_configurado,
    score_pesos,
    trad_lote,
    trad_min_score,
    traduccion_max,
)
from .config_observabilidad import (  # noqa: F401
    log_level,
)
from .config_produccion import (  # noqa: F401
    SEP_MARCA,
    autogen_arte_max,
    clave_por_marca,
    consola_url_publica,
    generaciones_ttl_seg,
    marca_apagada,
    media_gc_activo,
    media_gc_antiguedad_horas,
    media_gc_intervalo_horas,
    reaper_intervalo_seg,
)
from .config_programadores import (  # noqa: F401
    alertas_rendimiento_activas,
    alertas_rendimiento_horas,
    alertas_umbral_engagement,
    algoritmos_auto_activo,
    algoritmos_intervalo_horas,
    auto_preaprobacion,
    comercial_intervalo_horas,
    comercial_intervalo_segundos,
    eventos_intervalo_segundos,
    eventos_vencimientos_activos,
    investigador_activo,
    investigador_intervalo_horas,
    metricas_historico_retencion_dias,
    metricas_piezas_refresco_horas,
    metricas_refresco_horas,
    min_aprobaciones,
    prioriza_metricas_activo,
    prioriza_metricas_rango,
    programador_intervalo_segundos,
    publicar_real,
    publicar_real_para,
    sugerencias_editoriales_activo,
    sugerencias_editoriales_intervalo_horas,
    sugerencias_editoriales_max,
    trends_activo,
    trends_geos,
    trends_intervalo_min,
)
from .config_video import (  # noqa: F401
    ffmpeg_bin,
    video_render_timeout,
    whisper_modelo,
)
