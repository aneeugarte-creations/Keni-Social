"""App Starlette de la Consola Keni: API JSON pura + servir el SPA React.

Arquitectura de MODULOS DE API auto-descubiertos: cada area funcional vive en su
propio modulo dentro de `consola/api/` y exporta una variable `RUTAS` (ver el
contrato en `consola/api/__init__.py`). Esta app NO conoce los modulos concretos:
los descubre y monta sus rutas `/api/...`. Anadir un area = soltar UN archivo en
`api/`, sin tocar este `app.py`.

El resto (todo lo que NO empieza por `/api`) sirve el SPA React desde `webapp/`
(`/assets/*` desde `webapp/assets/`, favicons/recursos sueltos, y el resto cae a
`webapp/index.html`, fallback SPA). `webapp/` es la salida de `vite build` (outDir),
GITIGNORED: NO se versiona. En producción el SPA lo sirve nginx (`deploy/front`), no
este back (Traefik enruta solo `/api`+`/mcp` aquí); este servido es para
`python -m keni_consola` en local. Si `webapp/index.html` no existe (no se compiló
en local), devuelve un placeholder amable en espanol (200).

Bind SOLO a 127.0.0.1 (ver `__main__.py`).

SEGURIDAD (resumen): sin shell=True; SQL parametrizado; los errores salen como JSON
en espanol (sin tracebacks crudos).
"""

from __future__ import annotations

import contextlib
import logging
import mimetypes
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute

from . import api, config, db, seguridad
from ._repos_comun import PiezaPublicadaInmutable
from .dominio.runner import ColaLlenaError
from .observabilidad import NOMBRE_LOGGER, RegistroPeticiones, manejar_excepcion

_logger = logging.getLogger(NOMBRE_LOGGER)

# Centinela para distinguir "no se paso `token`" (=> resolver de env / generar en local)
# de "se paso `token=None`" (=> EXPRESAMENTE sin token interino, solo sesion + CSRF). El
# token interino es OPCIONAL: el despliegue no depende de el.
_TOKEN_NO_ESPECIFICADO = object()

# Carpeta donde el build del frontend deja el SPA (no existe aun en este worktree).
_DIR_WEBAPP = Path(__file__).parent / "webapp"
_INDICE_SPA = _DIR_WEBAPP / "index.html"
_DIR_ASSETS = _DIR_WEBAPP / "assets"

# Archivos sueltos de la RAIZ de webapp/ que el SPA puede pedir (favicon, manifest,
# robots...). SOLO estos nombres conocidos se sirven desde la raiz: cualquier otra
# cosa cae al index del SPA, de modo que un archivo ajeno colocado en webapp/ nunca
# se sirve por error (defensa en profundidad, ademas del anti-traversal).
_ARCHIVOS_RAIZ = frozenset(
    {
        "favicon.ico",
        "favicon.svg",
        "favicon.png",
        "apple-touch-icon.png",
        "manifest.webmanifest",
        "site.webmanifest",
        "robots.txt",
    }
)

# Placeholder amable cuando aun no hay build del frontend (caso normal aqui).
_PLACEHOLDER = (
    "<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
    "<title>KENI</title></head><body>"
    "<main style='font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem'>"
    "<h1>KENI</h1>"
    "<p>La interfaz aún no está construida; ejecuta el build del frontend.</p>"
    "</main></body></html>"
)


def _resolver_dentro(base: Path, sub: str) -> Path | None:
    """Resuelve `sub` DENTRO de `base`; None si escaparia (defensa anti-traversal)."""
    try:
        destino = (base / sub).resolve()
    except (OSError, ValueError):
        return None
    base_res = base.resolve()
    if destino == base_res or not destino.is_relative_to(base_res):
        return None
    return destino


async def _servir_asset(request: Request) -> Response:
    """Sirve un archivo estatico del SPA desde `webapp/assets/` (404 si no esta)."""
    sub = request.path_params["ruta"]
    destino = _resolver_dentro(_DIR_ASSETS, sub)
    if destino is None or not destino.is_file():
        return PlainTextResponse("No encontrado", status_code=404)
    return FileResponse(destino)


def _token_app(request: Request) -> str | None:
    """Token de sesion guardado en el estado de la app (None si no hay)."""
    return getattr(request.app.state, "token_consola", None)


def _respuesta_index_spa(request: Request, html: str) -> HTMLResponse:
    """Devuelve el index del SPA inyectando el token y fijando la cookie.

    El token se inyecta en el HTML (`window.__KENI_TOKEN__`, lo lee `api.ts` para la
    cabecera) y se fija como cookie `keni_consola_token`, de modo que las descargas
    por `window.open` y las `<img src>` —que no pueden mandar cabeceras— sigan
    autenticando. La cookie es SameSite=Strict: el navegador no la envia desde otro
    sitio, lo que (junto al chequeo de Origin en mutaciones) cierra el vector CSRF.
    """
    token = _token_app(request)
    if token:
        html = seguridad.inyectar_token_en_html(html, token)
    resp = HTMLResponse(html)
    if token:
        resp.set_cookie(
            seguridad.COOKIE_TOKEN,
            token,
            httponly=False,  # el SPA puede leerla; la defensa CSRF no depende del secreto
            samesite="strict",
            secure=seguridad.cookie_secure(),  # Secure tras un proxy TLS; ver seguridad.py
            path="/",
        )
    return resp


async def _servir_spa(request: Request) -> Response:
    """Fallback SPA: sirve `webapp/index.html` o un placeholder amable (200).

    Si la ruta pedida corresponde a un archivo suelto de `webapp/` (favicon, etc.)
    lo sirve; en cualquier otro caso devuelve el index del SPA (enrutado en cliente).
    """
    sub = (request.path_params.get("resto") or "").strip("/")
    # Solo servimos archivos sueltos de webapp/ cuyo nombre este en la allowlist
    # (favicon, manifest...). Cualquier otra ruta cae al index del SPA (enrutado en
    # cliente); asi un archivo plantado en webapp/ (p.ej. secreto.txt) jamas se sirve.
    if sub in _ARCHIVOS_RAIZ:
        candidato = _resolver_dentro(_DIR_WEBAPP, sub)
        if candidato is not None and candidato.is_file():
            tipo, _ = mimetypes.guess_type(str(candidato))
            return FileResponse(candidato, media_type=tipo or "application/octet-stream")

    if _INDICE_SPA.is_file():
        html = _INDICE_SPA.read_text(encoding="utf-8")
        return _respuesta_index_spa(request, html)
    return _respuesta_index_spa(request, _PLACEHOLDER)


async def _api_no_encontrado(request: Request) -> Response:
    """Sub-ruta /api inexistente: 404 JSON en espanol (NO debe caer al SPA)."""
    return JSONResponse({"error": "Recurso no encontrado."}, status_code=404)


async def _healthz(request: Request) -> Response:
    """Liveness: 200 JSON simple, SIN auth y SIN tocar la BD.

    Va FUERA de `/api` a proposito: asi el middleware `SeguridadConsola` la deja pasar
    sin credencial (un proxy/orquestador necesita pingarla sin token). Es liveness PURA:
    no consulta la BD ni nada externo, para no dar falsos negativos (un fallo de BD no
    debe tumbar el proceso). Una eventual readiness iria en otra ruta, aparte y opcional.
    """
    return JSONResponse({"estado": "ok"})


async def _manejar_cola_llena(request: Request, exc: ColaLlenaError) -> Response:
    """Backpressure de admision -> 429 JSON claro.

    Manejador CENTRAL por TIPO: cualquier endpoint que deje propagar `ColaLlenaError`
    (en vez de tragarla) responde un 429 consistente con un mensaje en espanol y la
    cabecera `Retry-After`. La cola NO tiene tope (R-NO-LIMIT): esto YA NO se dispara por
    tamano de cola, solo por el tope VOLUNTARIO de presupuesto/pausa (subclases de
    `ColaLlenaError`). El mensaje real (`str(exc)`) precisa el porque."""
    return JSONResponse(
        {"error": str(exc) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
        status_code=429,
        headers={"Retry-After": "5"},
    )


async def _manejar_pieza_inmutable(request: Request, exc: PiezaPublicadaInmutable) -> Response:
    """Edición de una pieza ya `publicado` -> 409 JSON claro.

    Manejador CENTRAL por TIPO: cualquier mutador que deje propagar `PiezaPublicadaInmutable`
    (la lanza la fachada `repos.actualizar_pieza`/`actualizar_pieza_fila`)
    responde 409 con el detalle de qué campo se intentó cambiar."""
    return JSONResponse(
        {"error": str(exc) or "Una pieza ya publicada es inmutable."},
        status_code=409,
    )


def crear_app(
    lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None,
    token=_TOKEN_NO_ESPECIFICADO, bootstrap=True,
) -> Starlette:
    """Construye la app Starlette descubriendo las rutas de la API + el SPA.

    `token`: token INTERINO opcional para la API. Es un gate EXTRA, no la
    barrera principal (esa es la sesion). Tres formas:
      - NO pasarlo (def): se resuelve de `KENI_CONSOLA_TOKEN`; si no esta, en local se
        GENERA uno (su VALOR NO se loguea; la cookie la fija el index del SPA). El
        arranque hosted fija la env (o la deja vacia para correr SIN token interino).
      - `token="..."`: usa ese token fijo (los tests pasan uno conocido).
      - `token=None`: EXPRESAMENTE sin token interino. La unica credencial es la sesion;
        sin sesion -> 401 igual. Sirve para probar/usar el modo "solo sesion + CSRF".
    `bootstrap`: si True (def), crea el admin inicial si la BD no tiene
    usuarios (idempotente). Los tests lo desactivan por defecto (la mayoria usan
    el token y no quieren pagar el coste del hash); los de auth lo activan o crean el
    usuario a mano. `lanzar_run` se ACEPTA por retrocompatibilidad con los tests, pero se IGNORA.
    `lanzar_generacion`: funcion opcional `(gen_id, *, prompt, cwd, procesar, dir_temporal)`
    para lanzar trabajos de IA (copy/RSS/hashtags) en background. `lanzar_imagen`: funcion
    opcional `(gen_id, *, generar)` para trabajos de imagen. Por defecto todas son las
    reales (Popen/hilo/stream-json); los tests pasan mocks que NO tocan `claude` ni la red.
    """
    if lanzar_generacion is not None or lanzar_imagen is not None:
        from . import generaciones as gen_modulo

        if lanzar_generacion is not None:
            def _encolar_inyectado(gen_id, *, prompt, cwd, procesar, dir_temporal=None, spec=None):  # noqa: ANN001
                return lanzar_generacion(
                    gen_id, prompt=prompt, cwd=cwd, procesar=procesar, dir_temporal=dir_temporal
                )

            gen_modulo.encolar_job_claude = _encolar_inyectado
        if lanzar_imagen is not None:
            gen_modulo.lanzar_job_imagen = lanzar_imagen

    # Idempotente y best-effort: corre en back Y daemons (mismo volumen), antes de leer config.
    try:
        from . import ajustes

        movidas = ajustes.migrar_claves_legado()
        if movidas:
            _logger.info("Ajustes: %d clave(s) legada(s) migradas al nombre nuevo.", movidas)
        purgadas = ajustes.purgar_claves_obsoletas()
        if purgadas:
            _logger.info("Ajustes: %d clave(s) obsoleta(s) purgadas del store.", purgadas)
    except OSError:
        _logger.warning("No se pudieron migrar/purgar las claves de ajustes.", exc_info=True)

    # Crea el esquema y, en hosted (Postgres), REHUSA arrancar
    # si el Postgres esta vacio pero hay un SQLite local CON datos (evita orfanar datos
    # vivos). El error SE PROPAGA a proposito (no lo tragamos): detiene el arranque.
    db.arrancar_persistencia()

    # Bootstrap del admin inicial: si la BD no tiene usuarios, crea uno desde
    # las env vars (o con pass aleatoria logueada). Idempotente; best-effort para no
    # impedir el arranque si la BD no esta disponible (la auth por token sigue valiendo).
    if bootstrap:
        from . import auth

        try:
            auth.bootstrap_admin()
        except Exception:  # noqa: BLE001 -- el arranque no debe romper por el bootstrap
            _logger.warning("No se pudo ejecutar el bootstrap del admin inicial.", exc_info=True)
        try:
            from . import bootstrap_categorias

            bootstrap_categorias.inicializar_categorias()
            # Retira las etiquetas viejas que no son líneas del plan (desactiva; reversible).
            bootstrap_categorias.retirar_categorias_obsoletas()
        except Exception:  # noqa: BLE001 -- idem: no impide el arranque
            _logger.warning("No se pudieron inicializar las líneas/orígenes.", exc_info=True)
        try:
            # Motor de ingesta (Ola A): si el catálogo de feeds está vacío, activa los presets
            # como `fuentes_rss` para que el motor tenga de dónde leer. Idempotente por URL.
            from . import bootstrap_categorias

            bootstrap_categorias.inicializar_fuentes_ingesta()
        except Exception:  # noqa: BLE001 -- idem: no impide el arranque
            _logger.warning("No se pudieron inicializar las fuentes del motor de ingesta.", exc_info=True)
        try:
            # Asocia cada feed a su LÍNEA (backfill `categoria`->`linea_id` por marca). Corre tras
            # sembrar líneas y fuentes; idempotente (solo toca feeds sin línea).
            from . import bootstrap_categorias

            bootstrap_categorias.vincular_fuentes_a_lineas()
        except Exception:  # noqa: BLE001 -- idem: no impide el arranque
            _logger.warning("No se pudieron vincular las fuentes a sus líneas.", exc_info=True)
        try:
            # Re-clava el plan diario y las franjas del slug de categoría al id de LÍNEA.
            # Idempotente; corre tras sembrar/vincular líneas.
            from . import bootstrap_categorias

            bootstrap_categorias.migrar_plan_y_franjas_a_lineas()
        except Exception:  # noqa: BLE001 -- idem: no impide el arranque
            _logger.warning("No se pudo migrar el plan/franjas a líneas.", exc_info=True)
        # Lleva tareas, piezas de la rota y
        # piezas al modelo `contenido` para que el tablero las muestre.
        # Idempotente (marca el origen / preserva ids) y best-effort: no impide el arranque.
        try:
            from . import migrar_publicacion

            migrar_publicacion.migrar()
        except Exception:  # noqa: BLE001 -- el arranque no debe romper por la migración
            _logger.warning("No se pudo migrar al tablero de contenido.", exc_info=True)

        # Reconstruye el histórico por pieza desde las caches del listado ya guardadas, para
        # que la curva del detalle arranque con el pasado capturado. Idempotente y best-effort.
        try:
            from . import metricas_pieza

            metricas_pieza.backfill_historico_desde_cache()
        except Exception:  # noqa: BLE001 -- el arranque no debe romper por el backfill
            _logger.warning("No se pudo reconstruir el histórico por pieza.", exc_info=True)

    rutas: list[Route | WebSocketRoute] = list(api.descubrir(refresco=True))

    # Cualquier OTRA sub-ruta /api (no descubierta) -> 404 JSON. Va despues de las
    # rutas reales y ANTES del fallback del SPA, para que un /api/... inexistente no
    # devuelva el index.html del SPA (que confundiria al cliente).
    rutas.append(Route("/api/{resto:path}", _api_no_encontrado))

    # Healthcheck de liveness: ruta de nivel superior (NO bajo /api, asi el
    # middleware la deja pasar sin token) y ANTES del catch-all del SPA, para que no
    # caiga al index.html. 200 JSON barato, sin tocar la BD.
    rutas.append(Route("/healthz", _healthz))

    # MCP operativo: si hay `KENI_MCP_BEARER` configurado, monta el servidor MCP en `/mcp`
    # (transporte streamable-HTTP) para que un cliente MCP (Claude Code) opere la API sin
    # conocerla. Se monta ANTES del catch-all del SPA para que /mcp no caiga al index. El
    # endpoint exige el bearer (middleware abajo) y por dentro opera con sesion del dueño.
    # APAGADO por defecto (sin bearer no se monta): el despliegue actual no cambia. Ver
    # `mcp_operativo.py`.
    bearer_mcp = config.mcp_bearer()
    servidor_mcp = None
    if bearer_mcp:
        from . import mcp_operativo

        servidor_mcp = mcp_operativo.crear_servidor(config.mcp_usuario())
        rutas.append(Mount("/mcp", app=servidor_mcp.app_asgi()))

    # Estaticos del SPA y fallback. Van DESPUES de las rutas /api para no taparlas.
    rutas.append(Route("/assets/{ruta:path}", _servir_asset))
    rutas.append(Route("/", _servir_spa))
    rutas.append(Route("/{resto:path}", _servir_spa))

    # Seguridad: resolvemos el token de mantenimiento opcional. Si NO se
    # inyecto (centinela), lo toma de KENI_CONSOLA_TOKEN; en local, si no esta, GENERA uno
    # (su valor NO se loguea; la cookie la fija el index del SPA). Si se inyecta
    # `token=None` EXPRESAMENTE, no hay token: la app queda protegida solo por sesion + CSRF
    # (el despliegue no depende del token). El token NO es admin.
    if token is _TOKEN_NO_ESPECIFICADO:
        token, generado = seguridad.resolver_token()
        if generado:
            # NUNCA logueamos el VALOR del token (vector de fuga: logs/capturas). El
            # acceso normal es el login multiusuario; el token es una credencial de
            # mantenimiento opcional que se entrega fuera de banda, no por el log.
            _logger.warning(
                "No hay KENI_CONSOLA_TOKEN: se genero un token de mantenimiento interino "
                "para esta ejecucion (NO se registra su valor). Entra por el login "
                "multiusuario; fija KENI_CONSOLA_TOKEN para un token estable de mantenimiento."
            )

    # Observabilidad: UNA linea de log por peticion (sin body/query/
    # cabeceras: ver `RegistroPeticiones`) + un manejador central que convierte
    # cualquier `Exception` no controlada en un 500 JSON consistente, logueando el
    # traceback en el servidor. Es ADITIVO: los endpoints que ya devuelven su propio
    # `{"error": ...}` siguen igual; esto solo atrapa lo que hoy caeria a un 500 crudo.
    #
    # Seguridad: `SeguridadConsola` envuelve TODO (va el primero, mas externo)
    # para exigir el token en `/api` y verificar CSRF en mutaciones ANTES de tocar las
    # rutas. El SPA y los estaticos pasan sin token (hay que poder cargar la pagina).
    middleware = [
        Middleware(seguridad.SeguridadConsola, token=token),
        Middleware(RegistroPeticiones),
    ]
    # Con el MCP montado: el guard del bearer va el MAS externo (rechaza /mcp no
    # autorizado antes que nada) y el lifespan del padre arranca el session manager del
    # MCP + abre el cliente in-proceso (Starlette no corre el lifespan de un sub-app
    # montado, hay que engancharlo aqui). Ver `mcp_operativo.ServidorMcp.lifespan`.
    mcp_lifespan = servidor_mcp.lifespan if servidor_mcp is not None else None
    if servidor_mcp is not None:
        middleware.insert(0, Middleware(mcp_operativo.GuardBearerMcp, bearer=bearer_mcp))

    # Bus del túnel keni-fotos (registro de dispositivos COMPARTIDO entre workers vía Postgres
    # LISTEN/NOTIFY): cada worker del back arranca su bus al iniciarse y lo para al cerrar. Se
    # compone con el lifespan del MCP si lo hay (Starlette admite un único lifespan).
    @contextlib.asynccontextmanager
    async def _lifespan(app_: Starlette):  # noqa: ANN202 -- contrato de Starlette
        from . import fotos_tunel

        fotos_tunel.iniciar_bus()
        try:
            if mcp_lifespan is not None:
                async with mcp_lifespan(app_):
                    yield
            else:
                yield
        finally:
            await fotos_tunel.detener_bus()

    app = Starlette(
        routes=rutas,
        middleware=middleware,
        lifespan=_lifespan,
        # ColaLlenaError ANTES que Exception: Starlette elige el handler por tipo mas
        # especifico, pero lo dejamos explicito (cola al tope -> 429, no 500).
        exception_handlers={
            ColaLlenaError: _manejar_cola_llena,
            PiezaPublicadaInmutable: _manejar_pieza_inmutable,
            Exception: manejar_excepcion,
        },
    )
    # El token vive en el estado de la app para que `_servir_spa` lo inyecte/siembre.
    app.state.token_consola = token
    return app
