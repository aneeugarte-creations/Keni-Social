"""App Starlette de la Consola Keni: API JSON pura + servir el SPA React.

Arquitectura de MODULOS DE API auto-descubiertos: cada area funcional vive en su
propio modulo dentro de `consola/api/` y exporta una variable `RUTAS` (ver el
contrato en `consola/api/__init__.py`). Esta app NO conoce los modulos concretos:
los descubre y monta sus rutas `/api/...`. Anadir un area = soltar UN archivo en
`api/`, sin tocar este `app.py`.

El resto (todo lo que NO empieza por `/api`) sirve el SPA React que construye otra
persona: `/assets/*` desde `webapp/assets/`, los favicons/recursos sueltos de
`webapp/`, y cualquier otra ruta devuelve `webapp/index.html` (fallback SPA). Si
`webapp/index.html` no existe todavia (caso normal en este worktree), devuelve un
placeholder amable en espanol (200).

Bind SOLO a 127.0.0.1 (ver `__main__.py`).

SEGURIDAD (resumen): el guardado de CLAUDE.md y el "abrir en Claude Code" SOLO
operan sobre carpetas presentes en consola.toml (allowlist por id estable); sin
shell=True; SQL parametrizado; los errores salen como JSON en espanol (sin
tracebacks crudos).
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from . import api, proyectos, seguridad
from .dominio.runner import ColaLlenaError
from .observabilidad import NOMBRE_LOGGER, RegistroPeticiones, manejar_excepcion

_logger = logging.getLogger(NOMBRE_LOGGER)

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
    "<title>Consola Keni</title></head><body>"
    "<main style='font-family:system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem'>"
    "<h1>Consola Keni</h1>"
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
    """Devuelve el index del SPA inyectando el token y sembrando la cookie (#134).

    El token se inyecta en el HTML (`window.__KENI_TOKEN__`, lo lee `api.ts` para la
    cabecera) y se siembra como cookie `keni_consola_token`, de modo que las descargas
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
            secure=seguridad.cookie_secure(),  # Secure tras un proxy TLS (#130); ver seguridad.py
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
    """Liveness (#130): 200 JSON simple, SIN auth y SIN tocar la BD.

    Va FUERA de `/api` a proposito: asi el middleware `SeguridadConsola` la deja pasar
    sin credencial (un proxy/orquestador necesita pingarla sin token). Es liveness PURA:
    no consulta la BD ni nada externo, para no dar falsos negativos (un fallo de BD no
    debe tumbar el proceso). Una eventual readiness iria en otra ruta, aparte y opcional.
    """
    return JSONResponse({"estado": "ok"})


async def _manejar_cola_llena(request: Request, exc: ColaLlenaError) -> Response:
    """Cola de generaciones al tope -> 429 JSON claro (#137).

    Manejador CENTRAL por TIPO: cualquier endpoint que deje propagar `ColaLlenaError`
    (en vez de tragarla) responde un 429 consistente con un mensaje en espanol y la
    cabecera `Retry-After`. Asi un pico de peticiones se rechaza con backpressure en
    vez de apilar hilos. Es deuda PERMANENTE: la generacion sigue siendo subprocess
    `claude -p` (ADR 0001), por lo que el tope de cola no desaparece."""
    return JSONResponse(
        {"error": str(exc) or "Hay demasiadas generaciones en curso; inténtalo en unos segundos."},
        status_code=429,
        headers={"Retry-After": "5"},
    )


def crear_app(
    abrir=None, lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None,
    token=None, bootstrap=True,
) -> Starlette:
    """Construye la app Starlette descubriendo las rutas de la API + el SPA.

    `token`: token de sesion para la API (#134). Si es None, se resuelve de
    `KENI_CONSOLA_TOKEN` o se genera uno aleatorio (que se loguea). Los tests pasan
    uno conocido. `bootstrap`: si True (def), crea el admin inicial si la BD no tiene
    usuarios (#130, idempotente). Los tests lo desactivan por defecto (la mayoria usan
    el token y no quieren pagar el coste del hash); los de auth lo activan o crean el
    usuario a mano. `abrir`: funcion opcional `(Path) -> str` para lanzar Claude Code (interactivo);
    por defecto la real. `lanzar_run`: funcion opcional
    `(marca_id, run_id, prompt, *, cwd) -> None` para lanzar runs headless en background.
    `lanzar_generacion`: funcion opcional `(gen_id, *, prompt, cwd, procesar, dir_temporal)`
    para lanzar trabajos de IA (copy/RSS/hashtags) en background. `lanzar_imagen`: funcion
    opcional `(gen_id, *, generar)` para trabajos de imagen. Por defecto todas son las
    reales (Popen/hilo/stream-json); los tests pasan mocks que NO tocan `claude` ni la red.
    """
    if abrir is not None or lanzar_run is not None:
        from .api import agentes as api_agentes

    if abrir is not None:
        from .api import proyectos as api_proyectos
        from .api import tareas as api_tareas

        api_proyectos.abrir_en_claude_code = abrir
        # Tareas usa su propio wrapper (con detalle como prompt). Lo envolvemos para
        # que tambien dependa del `abrir` inyectado, ignorando el detalle (mock simple).
        api_tareas.abrir_tarea_en_claude_code = lambda ruta, detalle="": abrir(ruta)
        # Agentes (runs interactivos) abre con `prompt=`; lo envolvemos para que use el
        # `abrir` inyectado ignorando el prompt (el mock simple solo recibe la ruta).
        api_agentes.abrir_en_claude_code = lambda ruta, prompt=None: abrir(ruta)

    if lanzar_run is not None:
        # Runs headless en background: inyectamos una fake que NO usa Popen ni red.
        api_agentes.lanzar_run_background = lanzar_run

    if lanzar_generacion is not None or lanzar_imagen is not None:
        from . import generaciones as gen_modulo

        if lanzar_generacion is not None:
            gen_modulo.lanzar_job_claude = lanzar_generacion
        if lanzar_imagen is not None:
            gen_modulo.lanzar_job_imagen = lanzar_imagen

    # Aseguramos que existe el consola.toml (best-effort; no rompe si falla).
    try:
        proyectos.crear_config_si_falta()
    except OSError:
        pass

    # Bootstrap del admin inicial (#130): si la BD no tiene usuarios, crea uno desde
    # las env vars (o con pass aleatoria logueada). Idempotente; best-effort para no
    # impedir el arranque si la BD no esta disponible (la auth por token sigue valiendo).
    if bootstrap:
        from . import auth

        try:
            auth.bootstrap_admin()
        except Exception:  # noqa: BLE001 -- el arranque no debe romper por el bootstrap
            _logger.warning("No se pudo ejecutar el bootstrap del admin inicial.", exc_info=True)

    rutas: list[Route] = list(api.descubrir(refresco=True))

    # Cualquier OTRA sub-ruta /api (no descubierta) -> 404 JSON. Va despues de las
    # rutas reales y ANTES del fallback del SPA, para que un /api/... inexistente no
    # devuelva el index.html del SPA (que confundiria al cliente).
    rutas.append(Route("/api/{resto:path}", _api_no_encontrado))

    # Healthcheck de liveness (#130): ruta de nivel superior (NO bajo /api, asi el
    # middleware la deja pasar sin token) y ANTES del catch-all del SPA, para que no
    # caiga al index.html. 200 JSON barato, sin tocar la BD.
    rutas.append(Route("/healthz", _healthz))

    # Estaticos del SPA y fallback. Van DESPUES de las rutas /api para no taparlas.
    rutas.append(Route("/assets/{ruta:path}", _servir_asset))
    rutas.append(Route("/", _servir_spa))
    rutas.append(Route("/{resto:path}", _servir_spa))

    # Seguridad (issue #134): resolvemos el token de sesion. Si no se inyecto uno (tests
    # pasan uno conocido), lo toma de KENI_CONSOLA_TOKEN o genera uno aleatorio. Cuando
    # se GENERA, hay que mostrarlo en el log para que el operador local pueda usarlo.
    if token is None:
        token, generado = seguridad.resolver_token()
        if generado:
            _logger.warning(
                "No hay KENI_CONSOLA_TOKEN: token de sesion generado para esta "
                "ejecucion: %s  (abre la Consola con ?token=%s o exporta "
                "KENI_CONSOLA_TOKEN para fijarlo).",
                token,
                token,
            )

    # Observabilidad (issue #123): UNA linea de log por peticion (sin body/query/
    # cabeceras: ver `RegistroPeticiones`) + un manejador central que convierte
    # cualquier `Exception` no controlada en un 500 JSON consistente, logueando el
    # traceback en el servidor. Es ADITIVO: los endpoints que ya devuelven su propio
    # `{"error": ...}` siguen igual; esto solo atrapa lo que hoy caeria a un 500 crudo.
    #
    # Seguridad (#134): `SeguridadConsola` envuelve TODO (va el primero, mas externo)
    # para exigir el token en `/api` y verificar CSRF en mutaciones ANTES de tocar las
    # rutas. El SPA y los estaticos pasan sin token (hay que poder cargar la pagina).
    app = Starlette(
        routes=rutas,
        middleware=[
            Middleware(seguridad.SeguridadConsola, token=token),
            Middleware(RegistroPeticiones),
        ],
        # ColaLlenaError ANTES que Exception: Starlette elige el handler por tipo mas
        # especifico, pero lo dejamos explicito (#137: cola al tope -> 429, no 500).
        exception_handlers={
            ColaLlenaError: _manejar_cola_llena,
            Exception: manejar_excepcion,
        },
    )
    # El token vive en el estado de la app para que `_servir_spa` lo inyecte/siembre.
    app.state.token_consola = token
    return app
