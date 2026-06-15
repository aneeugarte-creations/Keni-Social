"""Fixtures compartidas de los tests de la Consola Keni (API JSON). Todo OFFLINE.

Aisla en `tmp_path` (env vars) toda la persistencia y configuracion para que
ningun test toque el disco real del usuario:
  - `KENI_CONSOLA_CONFIG`  -> consola.toml (allowlist de proyectos)
  - `KENI_CONSOLA_RAIZ`    -> raiz de datos del backend de ficheros (YAML por marca)
  - `KENI_CONSOLA_INDICE`  -> indice SQLite regenerable del backend de ficheros
  - `KENI_CONSOLA_MEDIA`   -> dir de media (imagenes) aislado en tmp
  - `KENI_CONSOLA_SECRETOS`-> almacen de secretos (clave de imagen) aislado en tmp
  - `KENI_CONSOLA_PREFERENCIAS`-> preferencias (esfuerzo de generacion) aisladas en tmp
  - `KENI_CONSOLA_SUGERENCIAS`-> buzon de sugerencias (JSON local) aislado en tmp
  - `KENI_METRICAS_CONFIG` -> archivo inexistente + `KENI_METRICAS_FUENTE=muestra` => fuente de muestra
  - `KENI_TEXTO_DIR`  -> almacen de la Texto (prompts) FALSO en tmp (no toca el real)

PERSISTENCIA OPERACIONAL (ADR 0004): la Consola persiste en Postgres. La fixture `entorno`
fija `DATABASE_URL` apuntando al Postgres de pruebas (env `KENI_TEST_DATABASE_URL`) y
TRUNCA las tablas operacionales antes/despues del test (aislamiento entre tests). Si no
hay Postgres de pruebas, el test se SALTA con un mensaje claro (consistente con la fixture
`pg`): un dev sin Postgres recibe una senal clara; en CI hay un service `postgres` que los
ejecuta de verdad.

Tambien BORRA `OPENAI_API_KEY` para que, por defecto, la generacion de imagen este
"no configurada" (camino 400). Los tests que prueban un proveedor lo parchean.

Nada de red, nada de tokens reales, nunca se llama a `claude` (el runner se mockea).
"""

from __future__ import annotations

import os

import pytest
from starlette.testclient import TestClient

# Pool de conexiones Postgres ON en la suite. REUSA conexiones (cada operación NO abre/cierra
# su propia conexión TCP), así NO hay ~16k conexiones efímeras que agoten los puertos del CI
# (`Cannot assign requested address`). Y además es MÁS RÁPIDO que sin pool (medido -n6 vs
# Postgres real: 124 s con pool vs 211 s sin pool) — siempre que NO se pague el backoff de
# reconexión: ver `_postgres.limpiar_postgres`, que cierra el pool del proceso ANTES del
# `pg_terminate_backend`/TRUNCATE (si no, el pool descubre sus conexiones muertas server-side y
# psycopg_pool las reconstruye con ~1 s de backoff cada una -> esa era la causa del 3x, no un
# "admision de lock"). DEBE ir antes de importar `db`/`app` (abren el pool de forma perezosa).
# `setdefault` respeta overrides (`KENI_DB_POOL=0` para el camino directo, p.ej. depurar).
os.environ.setdefault("KENI_DB_POOL", "1")

from keni_consola import app as app_modulo  # noqa: E402 -- tras fijar KENI_DB_POOL
from keni_consola import db as db_modulo  # noqa: E402 -- tras fijar KENI_DB_POOL

# Plugin con la fixture/ayuda del backend POSTGRES (skip si no hay Postgres). Registrarlo
# aqui hace que la fixture `pg` se AUTODESCUBRA por nombre en los tests (sin importarla, lo
# que evita falsos F811 de "redefinicion"). Ver `_postgres.py`.
pytest_plugins = ["tests._postgres"]


@pytest.fixture(autouse=True)
def _versionado_git_desactivado(monkeypatch):
    """Desactiva por defecto el versionado git de la Texto en la suite.

    El versionado (commit por guardado) es BEST-EFFORT en produccion, pero en la suite cada
    `crear`/`guardar` lanzaria subprocesos git: lento y ruidoso. Lo apagamos por defecto; los
    tests que lo EJERCITAN lo reactivan con `monkeypatch.setenv('KENI_TEXTO_GIT', '1')`.
    """
    monkeypatch.setenv("KENI_TEXTO_GIT", "0")


@pytest.fixture(autouse=True)
def _esquema_fresco_por_test():
    """Limpia el memo de esquema de `db` al inicio de CADA test (#perf de la suite).

    `db._conectar` asegura el esquema (CREATE/ALTER idempotentes) UNA vez por proceso y URL para
    no pagar ~89 sentencias DDL en cada conexion (sin pool, eso domina la suite). Limpiar el memo
    por test hace que la PRIMERA conexion de cada test re-asegure el esquema: cuesta 1 ejecucion
    DDL por test (no por conexion) y preserva la auto-curacion que ejercitan los tests de "BD
    vieja"/esquema on-demand (que recrean el esquema con conexion cruda y esperan que la primera
    operacion `db.*` lo migre).
    """
    db_modulo._esquemas_asegurados.clear()
    yield


@pytest.fixture(autouse=True)
def _aislar_plantillas_marca(monkeypatch, tmp_path):
    """Aisla el store de plantillas de marca para que NINGÚN test escriba en la config
    REAL del desarrollador (`~/.config/keni-social/plantillas_marca`).

    El store cae a `rutas.dir_config()` salvo override `KENI_PLANTILLAS_MARCA_DIR`, que el
    resto de fixtures no fijaban. Resultado: tests como `test_marca_tiene_plantilla`
    guardaban un spec en la config real y contaminaban corridas locales posteriores
    (el spec persistía y el assert "marca SIN plantilla" fallaba). Autouse → cubre todos
    los tests, usen o no el fixture `entorno`.
    """
    monkeypatch.setenv("KENI_PLANTILLAS_MARCA_DIR", str(tmp_path / "plantillas_marca"))


@pytest.fixture(autouse=True)
def _aislar_patrones(monkeypatch, tmp_path):
    """Aisla el dir de perfiles de patrones (`patrones_marca.dir_perfiles_data`).

    Sin esto, un test que aplica un perfil (re-derivación, verificador de voz)
    escribiría en la config REAL (`~/.config/keni-social/patrones`) y el verificador
    leería perfiles del runtime del desarrollador en vez de la semilla del paquete.
    """
    monkeypatch.setenv("KENI_PATRONES_DIR", str(tmp_path / "patrones"))


@pytest.fixture(autouse=True)
def _aislar_logging_keni():
    """Aisla el estado del logger del paquete entre tests (contaminacion cruzada de logging).

    `observabilidad.configurar_logging()` anade un handler y pone `propagate=False` en el
    logger `keni_consola` (correcto en PRODUCCION: evita el doble log via root). Pero en la
    SUITE ese estado se filtraba al siguiente test y rompia los tests basados en `caplog`:
      - con `propagate=False`, los records ya no suben al root donde escucha `caplog`
        (los tests de observabilidad/generaciones veian 0 lineas -> AssertionError), y
      - el handler quedaba apuntando a un stream de captura de pytest ya cerrado
        ("ValueError: I/O operation on closed file").
    Era order-dependent: bastaba que un test previo configurara el logging. Aqui
    snapshotteamos handlers/propagate/nivel del logger ANTES de cada test y los restauramos
    despues, de modo que ningun test herede ni filtre el estado de logging de otro. Es un
    arreglo SOLO de test: no cambia el comportamiento en produccion.
    """
    import logging

    from keni_consola.observabilidad import NOMBRE_LOGGER

    logger = logging.getLogger(NOMBRE_LOGGER)
    handlers = logger.handlers[:]
    propagate = logger.propagate
    nivel = logger.level
    try:
        yield
    finally:
        logger.handlers[:] = handlers
        logger.propagate = propagate
        logger.setLevel(nivel)


@pytest.fixture(autouse=True)
def _limpiar_limite_login_por_ip():
    """Vacia el limite de login POR IP entre tests (estado en memoria por proceso).

    El TestClient de Starlette presenta SIEMPRE la misma IP ("testclient"): sin esta
    limpieza, los intentos FALLIDOS de login de tests anteriores se acumularian en la
    ventana deslizante de `api.auth` y un test tardio del mismo proceso recibiria 429 en
    vez de su 401 esperado (fallo order-dependent). Es un arreglo SOLO de test.
    """
    from keni_consola.api import auth as api_auth

    api_auth.reiniciar_limite_login_por_ip()
    yield
    api_auth.reiniciar_limite_login_por_ip()


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config + DB aisladas; metricas offline; Texto de prompts aislada en tmp.

    La operacional vive en Postgres (ADR 0004): fija `DATABASE_URL` al Postgres de pruebas
    (`KENI_TEST_DATABASE_URL`) y trunca las tablas operacionales antes/despues del test
    (aislamiento entre tests). Si no hay Postgres de pruebas, SE SALTA (con mensaje claro).
    El contenido editorial sigue en disco y se aisla en `tmp_path` con `KENI_CONSOLA_*`.
    """
    # Postgres operacional (obligatorio tras ADR 0004): apuntar al de pruebas o saltar.
    from ._postgres import limpiar_postgres, requiere_postgres

    url_pg = requiere_postgres()
    limpiar_postgres(url_pg)
    monkeypatch.setenv("DATABASE_URL", url_pg)
    # Anular componentes derivables para que `database_url()` use la URL EXPLICITA del test.
    for var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
                "POSTGRES_HOST", "POSTGRES_PORT"):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_CONSOLA_PREFERENCIAS", str(tmp_path / "preferencias.toml"))
    monkeypatch.setenv("KENI_CONSOLA_SUGERENCIAS", str(tmp_path / "sugerencias.json"))
    # Store de AJUSTES editables aislado en tmp. Sin esto caia a la ruta COMPARTIDA
    # `${XDG_CONFIG_HOME:-~/.config}/keni-social/ajustes.toml`: con xdist, un test que
    # ESCRIBE un ajuste (knobs de economia, kill switch, media_gc...) contaminaba a los
    # tests de OTRO worker en pleno vuelo (el store tiene precedencia sobre env), p.ej.
    # una pausa de generacion escrita en gw2 hacia fallar el corte por presupuesto en
    # gw5 con la excepcion equivocada. Flaky real desde que los knobs son editables.
    monkeypatch.setenv("KENI_CONSOLA_AJUSTES", str(tmp_path / "ajustes.toml"))
    # Token de sesion (#134): lo borramos del entorno para que `crear_app` use el que
    # le pasamos (TOKEN_PRUEBA) y no uno del shell del usuario. Determinismo en tests.
    monkeypatch.delenv("KENI_CONSOLA_TOKEN", raising=False)
    # MCP operativo APAGADO por defecto en los tests (determinismo): sin bearer, `crear_app`
    # no monta `/mcp` ni añade su lifespan. Los tests del MCP lo activan a propósito.
    monkeypatch.delenv("KENI_MCP_BEARER", raising=False)
    monkeypatch.delenv("KENI_MCP_USUARIO", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    # La fuente única por defecto es ahora `metricool` (sin credenciales = estado vacío,
    # no demo). Los tests del backend usan la fuente de MUESTRA determinista, así que la
    # fijamos explícita (antes se confiaba en que el default fuera `muestra`).
    monkeypatch.setenv("KENI_METRICAS_FUENTE", "muestra")
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Claves/proveedor de imagen por entorno: fuera, para que "sin clave" y el proveedor
    # por defecto sean deterministas (secretos lee OPENROUTER_API_KEY/KENI_IMAGEN_API_KEY).
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("KENI_IMAGEN_API_KEY", raising=False)
    monkeypatch.delenv("KENI_IMAGEN_PROVEEDOR", raising=False)
    monkeypatch.delenv("OPENROUTER_IMAGE_MODEL", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    # Economia de tokens (presupuesto_ia): deterministas — sin presupuesto, sin pausa, y la
    # cache del gasto del dia invalidada (es estado de MODULO; lo leido por un test previo
    # no debe contaminar al siguiente).
    monkeypatch.delenv("KENI_PRESUPUESTO_TOKENS_DIA", raising=False)
    monkeypatch.delenv("KENI_PRESUPUESTO_MARGEN_MANUAL", raising=False)
    monkeypatch.delenv("KENI_GENERACION_PAUSADA", raising=False)
    from keni_consola import presupuesto_ia as _presupuesto_ia

    _presupuesto_ia.invalidar_cache()
    # Almacen de generaciones (trabajos de IA en background) aislado en tmp.
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    # Almacen de la Texto (prompts + linea editorial) aislado en tmp: ningun test
    # debe leer/escribir el store real (~/.config/keni-social/texto).
    monkeypatch.setenv("KENI_TEXTO_DIR", str(tmp_path / "texto"))
    try:
        yield tmp_path
    finally:
        # Aislamiento entre tests: trunca las tablas operacionales del Postgres de pruebas.
        limpiar_postgres(url_pg)


def _lanzador_run_noop(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
    """Fake del lanzador de runs en background: NO usa Popen ni red, deja el run tal cual.

    Por defecto el run queda en `estado="ejecutando"` (como recien lanzado). Los tests
    que quieran simular avance/terminacion parchean `api.agentes.lanzar_run_background`
    por una fake propia que escribe estados/medidas en el YAML.
    """
    return None


def _lanzador_generacion_noop(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
    """Fake del lanzador de generaciones de claude: NO usa Popen ni red.

    Deja la generacion en `estado="ejecutando"`. Los tests que necesiten el resultado
    pasan `lanzar_generacion=lanzador_generacion_completa(salida, metricas)` a `_cliente`.
    """
    import shutil as _sh

    if dir_temporal is not None:
        _sh.rmtree(dir_temporal, ignore_errors=True)
    return None


def _lanzador_imagen_noop(gen_id, *, generar):  # noqa: ANN001
    """Fake del lanzador de imagen: NO toca la red. Deja la generacion en `ejecutando`."""
    return None


def lanzador_generacion_completa(salida: str, metricas=None):  # noqa: ANN001
    """Fake del lanzador de claude que COMPLETA la generacion SINCRONAMENTE.

    Llama al `procesar` REAL con una `salida` canned (asi se cubre el post-procesado:
    piezas/publicaciones/historial/hashtags) y fija el registro en `completado`. Sin
    Popen ni red.
    """
    import shutil as _sh

    from keni_consola import generaciones
    from keni_consola.dominio import stream

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        # Igual que el lanzador real: el temporal se borra DESPUES de `procesar` (el
        # post-procesado puede leer archivos del dir temporal antes de limpiarlo).
        try:
            resultado = procesar(salida, metricas)
        finally:
            if dir_temporal is not None:
                _sh.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "salida": salida,
                "metricas": stream.metricas_a_dict(metricas),
                "resultado": resultado,
                "fecha_fin": generaciones.ahora_iso(),
            },
        )

    return lanzar


def lanzador_imagen_completa(resultado: dict):
    """Fake del lanzador de imagen que COMPLETA la generacion con `resultado` (sin red)."""
    from keni_consola import generaciones

    def lanzar(gen_id, *, generar):  # noqa: ANN001
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "resultado": resultado,
                "fecha_fin": generaciones.ahora_iso(),
            },
        )

    return lanzar


def lanzador_imagen_ejecuta():
    """Fake del lanzador de imagen que EJECUTA `generar` SINCRONAMENTE (sin hilo).

    Corre el `generar` real del endpoint (con su proveedor MOCK) y fija el estado segun
    el resultado. Asi se cubre el pipeline real (generar -> guardar -> servir) sin red.
    """
    from keni_consola import generaciones

    def lanzar(gen_id, *, generar):  # noqa: ANN001
        try:
            resultado = generar()
        except Exception as e:  # noqa: BLE001 -- reflejamos el error como la generacion real
            generaciones.actualizar(
                gen_id,
                {"estado": generaciones.ESTADO_ERROR, "error": str(e) or "error",
                 "fecha_fin": generaciones.ahora_iso()},
            )
            return
        generaciones.actualizar(
            gen_id,
            {"estado": generaciones.ESTADO_COMPLETADO, "resultado": resultado,
             "fecha_fin": generaciones.ahora_iso()},
        )

    return lanzar


# Token de sesion FIJO para los tests (#134). `_cliente` lo inyecta a `crear_app` y
# lo manda por defecto en CADA peticion del TestClient, asi los ~600 tests existentes
# de la API pasan la barrera de auth sin cambios. Los tests de seguridad construyen un
# cliente SIN este header (`_cliente_sin_token`) para probar el rechazo (401/403).
TOKEN_PRUEBA = "token-de-prueba-1234567890"


def _cliente(
    abrir=None, lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None,
    token=TOKEN_PRUEBA, autenticar=True, bootstrap=False,
) -> TestClient:
    """TestClient de la app. Ningun lanzador toca nada real (mocks).

    `abrir` (interactivo), `lanzar_run` (runs headless), `lanzar_generacion` (trabajos de
    copy/RSS/hashtags) y `lanzar_imagen` (imagen) se inyectan por defecto a fakes
    inofensivas para que NUNCA se llame a `claude`, a un proveedor de imagen, ni se abra
    Terminal. Los tests que necesiten un resultado pasan una fake "completa".

    `token` fija el token de sesion de la app (#134). Si `autenticar` (def), el cliente
    manda `Authorization: Bearer <token>` por defecto en cada peticion para que los tests
    de API existentes pasen la auth sin cambios. Pasa `autenticar=False` para probar el
    rechazo sin token.

    `bootstrap` (def False): los tests que NO prueban la auth multiusuario (#130) no
    crean el admin inicial, asi evitan el coste del hash scrypt y siguen pasando por la
    via del TOKEN. Los tests de auth/usuarios lo activan (o crean usuarios a mano).
    """
    if abrir is None:
        def abrir(_ruta):  # noqa: ANN001
            return "ok-mock"
    if lanzar_run is None:
        lanzar_run = _lanzador_run_noop
    if lanzar_generacion is None:
        lanzar_generacion = _lanzador_generacion_noop
    if lanzar_imagen is None:
        lanzar_imagen = _lanzador_imagen_noop

    cabeceras = {"Authorization": f"Bearer {token}"} if autenticar else None
    return TestClient(
        app_modulo.crear_app(
            abrir=abrir,
            lanzar_run=lanzar_run,
            lanzar_generacion=lanzar_generacion,
            lanzar_imagen=lanzar_imagen,
            token=token,
            bootstrap=bootstrap,
        ),
        headers=cabeceras,
    )


@pytest.fixture
def cliente(entorno):
    """TestClient listo con el entorno aislado (mock de `abrir` inofensivo)."""
    return _cliente()


# --------------------------------------------------------------------------- #
# Marcado por app para el TEST-SCOPING del CI (pipelines `.woodpecker/tests-app-*`)
# --------------------------------------------------------------------------- #
#
# Los pipelines scoped corren un SUBCONJUNTO por app SIN enumerar ficheros (antes
# listaban rutas a mano en el .woodpecker y se rompian con un "file not found" en cuanto
# se borraba o renombraba un test). Ahora cada test se asigna aqui a su app por el STEM
# de su fichero, y el pipeline corre `pytest consola/tests -m "contrato or app_X"`.
#
# ROBUSTO: un test BORRADO simplemente no se recolecta (no rompe nada). Un test NUEVO de
# una app: anade su stem abajo para que entre en el scope; si se olvida, NO rompe el CI y
# de todas formas lo cubre la suite COMPLETA (`tests-python`, que corre el directorio
# entero en push a `main` y en cambios de keni-shared/gateway). `contrato` = fronteras +
# catalogo, el contrato compartido que TODOS los pipelines scoped ejecutan.
_APP_POR_STEM: dict[str, str] = {
    # Contrato compartido (corre en los tres pipelines scoped).
    "test_fronteras": "contrato",
    "test_catalogo": "contrato",
    # App B · Metricas (api/metricas, comercial).
    "test_api_metricas": "app_metricas",
    "test_api_comercial": "app_metricas",
    "test_comercial": "app_metricas",
    # App C · Operacion (publicaciones, aprobacion, franjas, rota...).
    "test_api_publicaciones": "app_operacion",
    "test_api_publicaciones_contenido": "app_operacion",
    "test_api_aprobacion": "app_operacion",
    "test_colaboracion_dominio": "app_operacion",
    "test_api_franjas": "app_operacion",
    "test_api_rota": "app_operacion",
    "test_api_rota_ampliada": "app_operacion",
    "test_api_rota_franjas": "app_operacion",
    "test_api_rota_piezas": "app_operacion",
    "test_api_rota_programas": "app_operacion",
    "test_api_rota_swaps": "app_operacion",
    "test_rota": "app_operacion",
    "test_api_reciclar": "app_operacion",
    "test_db_piezas": "app_operacion",
    "test_mcp_operativo": "app_operacion",
    # App A · Produccion (actividad, generaciones, skills, rss, radar...).
    "test_actividad": "app_produccion",
    "test_api_cola_monitor": "app_produccion",
    "test_pipeline_contenido": "app_produccion",
    "test_pipeline_verificar_fuente": "app_produccion",
    "test_api_pipelines": "app_produccion",
    "test_generaciones": "app_produccion",
    "test_api_hashtags": "app_produccion",
    "test_db_editorial": "app_produccion",
    "test_api_verificaciones": "app_produccion",
    "test_api_patrones": "app_produccion",
    "test_api_rss": "app_produccion",
    "test_api_algoritmos": "app_produccion",
    "test_algoritmos": "app_produccion",
    "test_metricas_runs": "app_produccion",
    "test_patrones_marca": "app_produccion",
    "test_verdicto_voz": "app_produccion",
    "test_patrones_refresco": "app_produccion",
    "test_plantillas_marca": "app_produccion",
    "test_api_plantillas_marca": "app_produccion",
    "test_investigacion": "app_produccion",
}


def pytest_collection_modifyitems(items):  # noqa: D401 -- hook de pytest
    """Marca cada test con su app (`_APP_POR_STEM`) para el test-scoping del CI.

    Permite a los pipelines scoped seleccionar por marcador (`-m app_X`) en vez de
    enumerar ficheros. Tests sin entrada quedan sin marca de app (solo corren en la suite
    completa). No falla nunca por un stem que ya no exista.
    """
    for item in items:
        marca = _APP_POR_STEM.get(getattr(getattr(item, "path", None), "stem", ""))
        if marca:
            item.add_marker(getattr(pytest.mark, marca))
