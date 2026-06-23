"""Configuracion CENTRAL de la Consola Keni: fuente UNICA de las env vars `KENI_*`.

Declara cada nombre de variable UNA vez (constantes `ENV_*`) y expone un
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
                                  (la cola NO tiene tope: el exceso ESPERA un slot)

  Cola + worker de generacion (ADR 0002; `cola`, `worker`):
    - KENI_WORKER_EXTERNO         hay un servicio `worker` aparte    def OFF (worker in-proceso)
    - KENI_WORKER_SONDEO_SEGUNDOS intervalo de sondeo de la cola (s) def 0.5  (min 0.05)

  Generacion `claude -p` (`generaciones`, `dominio.stream`):
    - KENI_CLAUDE_TIMEOUT         wall-timeout de un job (s)         def 600
    - KENI_CLAUDE_MAX_USD         tope de coste (--max-budget-usd)   def sin tope
    - KENI_CLAUDE_MAX_TURNS       tope de turnos (--max-turns)       def sin tope
    - KENI_CLAUDE_SKIP_PERMISSIONS  saltar permisos (--dangerously-skip-permissions)  def ON

  Texto de prompts + linea editorial (`texto`, `dominio.prompts_lanzar`):
    - KENI_PROMPTS_DIR         almacen de documentos markdown     def <dir_config>/texto

  Programadores en segundo plano (`programador`):
    - KENI_METRICAS_REFRESCO_HORAS       refresco cache metricas (h) def 4   (min 1)
    - KENI_METRICAS_PIEZAS_REFRESCO_HORAS refresco cache POR PIEZA (h) def 4 (min 1)
    - KENI_ALERTAS_RENDIMIENTO_HORAS     barrido alertas rendim. (h) def 6   (min 1)
    - KENI_ALERTAS_RENDIMIENTO           apaga el barrido de alertas def ON
    - KENI_ALERTAS_UMBRAL_ENGAGEMENT     umbral bajo rendim. (%)     def 1.0

  Imagen / secretos (`secretos`, `media`): la precedencia fichero>env vive en
  `secretos.py`; aqui se declaran solo los nombres (no hay accesor central porque el
  fichero de secretos participa en la decision):
    - KENI_IMAGEN_API_KEY, KENI_IMAGEN_PROVEEDOR  (+ OPENROUTER_API_KEY/OPENAI_API_KEY)

  Persistencia (ADR 0004): la operacional (tareas/comercial/rota/usuarios/sesiones/
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
    BREAKING_EXTRA_DIA_DEF,
    CLUSTER_BREAKING_PESO_DEF,
    CLUSTER_BREAKING_VENTANA_H_DEF,
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
    ENV_AUTOGEN_ARTE_MAX,
    ENV_CLASIFICAR_MARCA_IA,
    ENV_CLAUDE_DISALLOWED_TOOLS,
    ENV_CLAUDE_EXCLUDE_DYNAMIC_SECTIONS,
    ENV_CLAUDE_FALLBACK_MODEL,
    ENV_CLAUDE_IDLE_TIMEOUT,
    ENV_CLAUDE_MAX_TURNS,
    ENV_CLAUDE_MAX_USD,
    ENV_CLAUDE_SESSION_PERSISTENCE,
    ENV_CLAUDE_SKIP_PERMISSIONS,
    ENV_CLAUDE_TIMEOUT,
    ENV_CLUSTER_BREAKING_FUENTES,
    ENV_BREAKING_EXTRA_DIA,
    ENV_CLUSTER_BREAKING_PESO,
    ENV_CLUSTER_BREAKING_VENTANA_H,
    ENV_CLUSTER_VENTANA_H,
    ENV_CONSOLA_URL_PUBLICA,
    ENV_COOKIE_SECURE,
    ENV_CRITICA_IA,
    ENV_DATA_DIR,
    ENV_DATABASE_URL,
    ENV_DB_POOL,
    ENV_DB_POOL_MAX,
    ENV_DB_POOL_MIN,
    ENV_ESFUERZO,
    ENV_FEED_SLA_MIN,
    ENV_FFMPEG_BIN,
    ENV_FUENTES_BAJA_CONFIANZA,
    ENV_FUSION_SEMANTICA_MAX,
    ENV_FUSION_VENTANA_H,
    ENV_GENERACION_PAUSADA,
    ENV_GENERACIONES,
    ENV_GENERACIONES_TTL_HORAS,
    ENV_HOST,
    ENV_HTTPS,
    ENV_IMAGEN_API_KEY,
    ENV_IMAGEN_PROVEEDOR,
    ENV_INDICE,
    ENV_INGESTA_BATCH,
    ENV_INGESTA_INTERVALO_BREAKING,
    ENV_INGESTA_INTERVALO_DEFECTO,
    ENV_INGESTA_INTERVALO_DEPORTES,
    ENV_INGESTA_INTERVALO_GAMING,
    ENV_INGESTA_INTERVALO_INTERNACIONAL,
    ENV_INGESTA_INTERVALO_MX,
    ENV_INGESTA_MAX_ERRORES,
    ENV_INGESTA_MAX_ITEMS,
    ENV_INGESTA_WORKERS,
    ENV_FUSION_MODELO,
    ENV_INSUMOS_MODELO,
    ENV_LOG_LEVEL,
    ENV_CONTROL_BEARER,
    ENV_CONTROL_PORT,
    ENV_CONTROL_URL,
    ENV_DEV_PORT,
    ENV_DEV_REPO,
    ENV_DEV_URL,
    ENV_MAQUINA,
    ENV_MAX_JOBS,
    ENV_MAX_RALPH,
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
    ENV_MFA_ADMIN,
    ENV_MFA_KEY,
    ENV_MIN_APROBACIONES,
    ENV_NOTICIAS_GC,
    ENV_NOTICIAS_GC_INACTIVIDAD_HORAS,
    ENV_NOTICIAS_GC_INTERVALO_HORAS,
    ENV_NOTICIAS_GC_SCORE_UMBRAL,
    ENV_ORIGENES,
    ENV_PASSWORD_MIN,
    ENV_PATRONES_AUTO,
    ENV_PERFIL_EDITORIAL_TTL_HORAS,
    ENV_PG_DB,
    ENV_PG_HOST,
    ENV_PG_PASSWORD,
    ENV_PG_PORT,
    ENV_PG_USER,
    ENV_PIPELINE_ILUSTRAR,
    ENV_PIPELINE_STOCK,
    ENV_STOCK_FUENTES,
    ENV_PIPELINE_SUGERIR_HASHTAGS,
    ENV_PIPELINE_DECISOR,
    ENV_PIPELINE_REVISAR,
    ENV_PIPELINE_REDACTAR,
    ENV_PIPELINE_EN_PROCESO_MAX,
    ENV_PIPELINE_FUSIONAR,
    ENV_PIPELINE_MAX,
    ENV_PIPELINE_RECOLECTAR,
    ENV_PIPELINE_VERIFICAR,
    ENV_PORT,
    ENV_PREFERENCIAS,
    ENV_JOBS_MAX_INTENTOS,
    ENV_PROMPT_AVISO_CHARS,
    ENV_PROMPT_MAX_CHARS,
    ENV_PRESUPUESTO_MARGEN_MANUAL,
    ENV_PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA,
    ENV_PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA,
    ENV_PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA,
    ENV_PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA,
    ENV_PRESUPUESTO_USD_DIA,
    ENV_PUBLICAR_REAL,
    ENV_VERIFICACION_EN_CURSO_TTL_MIN,
    ENV_VERIFICACION_FUENTE_ESFUERZO,
    ENV_VERIFICACION_FUENTE_MODELO,
    ENV_VERIFICACION_FUENTE_TIMEOUT,
    ENV_RAIZ,
    ENV_RALPH_PORT,
    ENV_RALPH_URL,
    ENV_PRIORIZAR_PERFIL_IA,
    ENV_LIMPIADOR_INTERVALO_MIN,
    ENV_RENDIMIENTO_MIN_PIEZAS,
    ENV_RENDIMIENTO_RANKING,
    ENV_RENDIMIENTO_TOP_N,
    ENV_REUTERS_API_KEY,
    ENV_REUTERS_BASE_URL,
    ENV_RP_ID,
    ENV_RP_NOMBRE,
    ENV_RP_ORIGIN,
    ENV_S3_ACCESS_KEY,
    ENV_S3_BUCKET,
    ENV_S3_ENDPOINT,
    ENV_S3_REGION,
    ENV_S3_SECRET_KEY,
    ENV_SCORE_BONUS_BREAKING,
    ENV_SCORE_PESO_CORROBORACION,
    ENV_SCORE_PESO_VELOCIDAD,
    ENV_SCORE_PESO_FRESCURA,
    ENV_SCORE_PESO_MARCA,
    ENV_SCORE_PESO_RENDIMIENTO,
    ENV_SCORE_PESO_VIRALIDAD,
    ENV_SECRETOS,
    ENV_SESION_HORAS,
    ENV_SESION_MAX_HORAS,
    ENV_PROMPTS_DIR,
    ENV_PROMPTS_DIR_LEGACY,
    ENV_SUGERENCIAS,
    ENV_TOKEN,
    ENV_TRAD_LOTE,
    ENV_TRAD_MIN_SCORE,
    ENV_TRADUCCION_MAX,
    ENV_TRENDS,
    ENV_TRENDS_GEOS,
    ENV_TRENDS_INTERVALO_MIN,
    ENV_VIDEO_MAX_MB,
    ENV_VIDEO_RENDER_TIMEOUT,
    ENV_WORKER_EXTERNO,
    ENV_WORKER_SONDEO_SEGUNDOS,
    FEED_SLA_MIN_DEF,
    FFMPEG_BIN_DEF,
    FUENTES_BAJA_CONFIANZA_DEF,
    FUSION_SEMANTICA_MAX_DEF,
    GENERACIONES_TTL_HORAS_DEF,
    HOST_DEF,
    INGESTA_BACKOFF_TOPE_SEG,
    INGESTA_BATCH_DEF,
    INGESTA_INTERVALO_BREAKING_DEF,
    INGESTA_INTERVALO_DEFECTO_DEF,
    INGESTA_INTERVALO_DEPORTES_DEF,
    INGESTA_INTERVALO_EVERGREEN_DEF,
    INGESTA_INTERVALO_GAMING_DEF,
    INGESTA_INTERVALO_INTERNACIONAL_DEF,
    INGESTA_INTERVALO_MX_DEF,
    INGESTA_MAX_ERRORES_DEF,
    INGESTA_MAX_ITEMS_DEF,
    INGESTA_WORKERS_DEF,
    LOG_LEVEL_DEF,
    JOBS_MAX_INTENTOS_DEF,
    PROMPT_AVISO_CHARS_DEF,
    PROMPT_MAX_CHARS_DEF,
    MAX_JOBS_DEF,
    PRESUPUESTO_MARGEN_MANUAL_DEF,
    PRESUPUESTO_TOKENS_INVESTIGACION_IN_DIA_DEF,
    PRESUPUESTO_TOKENS_INVESTIGACION_OUT_DIA_DEF,
    PRESUPUESTO_TOKENS_PRODUCCION_IN_DIA_DEF,
    PRESUPUESTO_TOKENS_PRODUCCION_OUT_DIA_DEF,
    PRESUPUESTO_USD_DIA_DEF,
    MEDIA_GC_ANTIGUEDAD_HORAS_DEF,
    MEDIA_GC_INTERVALO_HORAS_DEF,
    METRICAS_HISTORICO_RETENCION_DIAS_DEF,
    METRICAS_PIEZAS_REFRESCO_HORAS_DEF,
    METRICAS_REFRESCO_HORAS_DEF,
    MIN_APROBACIONES_DEF,
    NOTICIAS_GC_INACTIVIDAD_HORAS_DEF,
    NOTICIAS_GC_INTERVALO_HORAS_DEF,
    NOTICIAS_GC_SCORE_UMBRAL_DEF,
    PERFIL_EDITORIAL_TTL_HORAS_DEF,
    PIPELINE_EN_PROCESO_MAX_DEF,
    PIPELINE_MAX_DEF,
    PORT_DEF,
    LIMPIADOR_INTERVALO_MIN_DEF,
    RENDIMIENTO_MIN_PIEZAS_DEF,
    RENDIMIENTO_TOP_N_DEF,
    S3_BUCKET_DEF,
    S3_REGION_DEF,
    SCORE_BONUS_BREAKING_DEF,
    SCORE_PESO_CORROBORACION_DEF,
    SCORE_PESO_VELOCIDAD_DEF,
    SCORE_PESO_FRESCURA_DEF,
    SCORE_PESO_MARCA_DEF,
    SCORE_PESO_RENDIMIENTO_DEF,
    SCORE_PESO_VIRALIDAD_DEF,
    SESION_HORAS_DEF,
    SESION_MAX_HORAS_DEF,
    TRAD_LOTE_DEF,
    TRAD_MIN_SCORE_DEF,
    TRENDS_GEOS_DEF,
    TRENDS_INTERVALO_MIN_DEF,
    VIDEO_MAX_MB_DEF,
    VIDEO_RENDER_TIMEOUT_DEF,
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
    control_bearer,
    control_puerto,
    control_url,
    cookie_secure,
    dev_puerto,
    dev_repo,
    dev_url,
    flag_https,
    mcp_bearer,
    mcp_usuario,
    ralph_max,
    ralph_puerto,
    ralph_url,
    mfa_habilitado,
    mfa_key,
    mfa_key_presente,
    mfa_obligatorio_admin,
    origenes_permitidos,
    password_min,
    PASSWORD_MIN_DEF,
    rp_id,
    rp_nombre,
    rp_origenes,
    sesion_horas,
    sesion_max_horas,
    token,
)
from .config_contenido import (  # noqa: F401
    decisor_modelo,
    fusion_modelo,
    hashtags_modelo,
    insumos_modelo,
)
from .config_generacion import (  # noqa: F401
    CLAUDE_DISALLOWED_TOOLS_DEF,
    claude_disallowed_tools,
    claude_exclude_dynamic_sections,
    claude_fallback_model,
    claude_idle_timeout,
    claude_max_turns,
    claude_max_usd,
    claude_session_persistence,
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
    generacion_pausada,
    generacion_pausada_marca,
    jobs_max_intentos,
    prompt_aviso_chars,
    prompt_max_chars,
    max_jobs,
    presupuesto_margen_manual_pct,
    presupuesto_tokens_investigacion_in_dia,
    presupuesto_tokens_investigacion_in_dia_marca,
    presupuesto_tokens_investigacion_out_dia,
    presupuesto_tokens_investigacion_out_dia_marca,
    presupuesto_tokens_produccion_in_dia,
    presupuesto_tokens_produccion_in_dia_marca,
    presupuesto_tokens_produccion_out_dia,
    presupuesto_tokens_produccion_out_dia_marca,
    presupuesto_usd_dia,
    presupuesto_usd_dia_marca,
    worker_externo,
    worker_sondeo_segundos,
)
from .config_noticias import (  # noqa: F401
    AFP_BASE_URL_DEF,
    ENV_INGESTA_FILTRO,
    CUPO_DIA_DEF,
    ENV_CUPO_DIA,
    ENV_INVESTIGACION,
    ENV_PRODUCCION,
    ENV_PLAN_DIA,
    ENV_PLAN_REDES,
    ENV_PROMOVER_MADURACION_MIN,
    ETAPAS_INVESTIGACION,
    ETAPAS_PRODUCCION,
    PROMOVER_MADURACION_MIN_DEF,
    ENV_PROMOVER_MIN_MARCA,
    ENV_PROMOVER_MIN_SCORE,
    REUTERS_BASE_URL_DEF,
    afp_base_url,
    afp_client_id,
    afp_client_secret,
    afp_configurado,
    alguna_etapa_investigacion_activa,
    alguna_etapa_pipeline_activa,
    alguna_etapa_produccion_activa,
    auto_programar_activo,
    ilustrar_activo,
    sugerir_hashtags_activo,
    critica_ia_activa,
    clasificar_marca_ia,
    marca_noticias,
    marcas_activas,
    cluster_breaking_fuentes,
    breaking_extra_dia,
    cluster_breaking_peso,
    cluster_breaking_ventana_h,
    cluster_ventana_h,
    cupo_dia,
    etapa_activa,
    etapa_global_activa,
    feed_sla_min,
    fuentes_baja_confianza,
    fusionar_semantica_activo,
    fusion_semantica_max,
    fusion_ventana_h,
    recolectar_activo,
    ingesta_batch,
    ingesta_filtro_activo,
    ingesta_intervalo_categoria,
    intervalo_de_cadencia,
    ingesta_max_errores,
    ingesta_max_items,
    ingesta_workers,
    ENV_NOTICIAS_RETENCION_H,
    ENV_NOTICIAS_TTL_H,
    NOTICIAS_RETENCION_H_DEF,
    NOTICIAS_TTL_H_DEF,
    noticias_gc_activo,
    noticias_gc_inactividad_horas,
    noticias_gc_intervalo_horas,
    noticias_gc_score_umbral,
    noticias_retencion_horas,
    noticias_ttl_horas,
    priorizar_perfil_activo,
    perfil_editorial_ttl_horas,
    pipeline_activo,
    revisar_activo,
    pipeline_en_proceso_max,
    pipeline_fetch_fuente,
    pipeline_tema_ttl_horas,
    parsear_plan,
    parsear_redes,
    pipeline_max,
    plan_dia,
    plan_redes,
    promover_diversidad_umbral,
    promover_maduracion_min,
    promover_min_marca,
    promover_min_score,
    verificar_activo,
    verificacion_en_curso_ttl_seg,
    verificacion_fuente_esfuerzo,
    verificacion_fuente_modelo,
    verificacion_fuente_timeout,
    rendimiento_min_piezas,
    rendimiento_ranking_activo,
    rendimiento_top_n,
    reuters_api_key,
    reuters_base_url,
    reuters_configurado,
    pexels_api_key,
    pixabay_api_key,
    fuentes_stock_activas,
    stock_busca_activo,
    stock_max_por_barrido,
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
    limpiador_intervalo_seg,
)
from .config_programadores import (  # noqa: F401
    alertas_rendimiento_activas,
    alertas_rendimiento_horas,
    alertas_umbral_engagement,
    algoritmos_auto_activo,
    algoritmos_intervalo_horas,
    auto_preaprobacion,
    canal_publicacion_para,
    metricas_historico_retencion_dias,
    metricas_piezas_refresco_horas,
    metricas_refresco_horas,
    min_aprobaciones,
    patrones_auto_activo,
    publicar_real,
    publicar_real_para,
    trends_activo,
    trends_geos,
    trends_intervalo_min,
)
from .config_prompts import (  # noqa: F401
    prompts_dir,
)
from .config_video import (  # noqa: F401
    ffmpeg_bin,
    video_render_timeout,
)
