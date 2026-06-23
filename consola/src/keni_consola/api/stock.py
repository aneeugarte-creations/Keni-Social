"""API Stock: claves GLOBALES de los bancos de fotos + fuentes habilitadas por marca.

Dos áreas, una misma regla de oro de `conexiones`: los SECRETOS no salen nunca al
navegador; solo se reporta presencia/estado y, como mucho, una PISTA (`····last4`).

  CLAVES GLOBALES (almacen de secretos, bloque `[stock]`). Pexels/Pixabay son agencias
  GENÉRICAS: una clave por agencia sirve a TODAS las marcas (no es propiedad de ninguna).
    GET    /api/stock/proveedores        -> estado de las claves (sin la clave)
    PUT    /api/stock/clave              -> guarda la clave de un proveedor
    DELETE /api/stock/clave/{proveedor}  -> borra esa clave
    POST   /api/stock/probar            -> valida la clave con una búsqueda barata

  FUENTES HABILITADAS POR MARCA (store de ajustes, `KENI_STOCK_FUENTES::<marca>`): qué
  bancos usa CADA marca (decisión editorial por marca).
    GET    /api/stock/fuentes?marca=     -> qué fuentes usa esa marca (toggles)
    PUT    /api/stock/fuentes/{marca}    -> guarda qué proveedores se usan

Las claves se gestionan en Sistema → Proveedores (globales); los toggles, en la subpágina
de la etapa Stock (Contexto), por marca.

SOLO ADMIN: las claves de stock son SECRETOS compartidos del despliegue. TODOS los
endpoints (lectura Y mutación) exigen rol admin; un editor recibe 403. Mismo gate
estricto que `conexiones` (`keni_consola.permisos.es_admin`). Errores en español, sin
tracebacks, sin filtrar secretos.
"""

from __future__ import annotations

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import ajustes, config, marcas, permisos, secretos, stock_fotos
from .._http_json import leer_json

# Mensaje de rechazo cuando un no-admin toca las fuentes de stock (secretos compartidos).
_MSG_SOLO_ADMIN = (
    "Solo un administrador puede ver o cambiar las fuentes de stock (claves y toggles)."
)

# Agencias genéricas que llevan API key (las únicas que se guardan/prueban). Fuente única.
_CON_CLAVE = secretos._PROVEEDORES_STOCK

# Query de prueba neutra para validar una clave sin depender de un término concreto.
_QUERY_PRUEBA = "ciudad"


# --------------------------------------------------------------------------- #
# Claves GLOBALES (Sistema → Proveedores)                                     #
# --------------------------------------------------------------------------- #


def _proveedor_global(proveedor: str) -> dict:
    """Estado GLOBAL de un proveedor (clave + disponibilidad), sin exponer la clave."""
    estado = stock_fotos.estado_fuente(proveedor)
    salida = {
        "proveedor": estado["proveedor"],
        "nombre": estado["nombre"],
        "requiere_clave": estado["requiere_clave"],
        "disponible": estado["disponible"],
    }
    if estado["requiere_clave"]:
        pista = secretos.estado_clave_stock(proveedor)
        salida["configurado"] = pista["configurado"]
        salida["pista"] = pista["pista"]
    return salida


async def proveedores_estado(request: Request) -> Response:
    """GET /api/stock/proveedores: estado GLOBAL de las agencias (claves). SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse(
        {"proveedores": [_proveedor_global(p) for p in stock_fotos.ids_proveedores()]}
    )


async def clave_guardar(request: Request) -> Response:
    """PUT /api/stock/clave: guarda la API key GLOBAL (JSON `{proveedor, api_key}`).

    Valida que `proveedor` es uno con clave (pexels/pixabay). No devuelve la clave. SOLO ADMIN.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    datos = await leer_json(request)
    proveedor = (datos.get("proveedor") or "").strip().lower()
    if proveedor not in _CON_CLAVE:
        return JSONResponse(
            {"error": "Proveedor de stock no admite clave."}, status_code=400
        )
    api_key = datos.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        return JSONResponse({"error": "Falta la API key."}, status_code=400)
    try:
        secretos.guardar_clave_stock(proveedor, api_key)
    except OSError:
        return JSONResponse({"error": "No se pudo guardar la API key."}, status_code=500)
    return JSONResponse({"configurado": True, "mensaje": "Clave de stock guardada."})


async def clave_borrar(request: Request) -> Response:
    """DELETE /api/stock/clave/{proveedor}: borra la clave GLOBAL de un proveedor. SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    proveedor = (request.path_params["proveedor"] or "").strip().lower()
    if proveedor not in _CON_CLAVE:
        return JSONResponse(
            {"error": "Proveedor de stock no admite clave."}, status_code=400
        )
    try:
        secretos.borrar_clave_stock(proveedor)
    except OSError:
        return JSONResponse({"error": "No se pudo borrar la API key."}, status_code=500)
    return JSONResponse({"configurado": False, "mensaje": "Clave de stock borrada."})


def _probar(proveedor: str) -> tuple[bool, str]:
    """Valida la clave GLOBAL de un proveedor con una búsqueda barata. NO expone la clave.

    Reutiliza `stock_fotos.buscar` (descarga via el `_DESCARGADOR` inyectable de `api.rss`,
    parcheable en tests). Una respuesta sin error = la clave funciona, aunque traiga 0 fotos.
    """
    if proveedor in _CON_CLAVE and secretos.obtener_clave_stock(proveedor) is None:
        return False, "No hay clave configurada."
    try:
        stock_fotos.buscar(_QUERY_PRUEBA, proveedor, limite=1)
    except stock_fotos.rss.RSSError:
        return False, "El proveedor rechazó la búsqueda o no respondió."
    return True, "La conexión funciona."


async def clave_probar(request: Request) -> Response:
    """POST /api/stock/probar: valida la clave GLOBAL guardada (JSON `{proveedor}`). SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    datos = await leer_json(request)
    proveedor = (datos.get("proveedor") or "").strip().lower()
    if proveedor not in stock_fotos.ids_proveedores():
        return JSONResponse({"error": "Proveedor de stock desconocido."}, status_code=400)
    ok, mensaje = await run_in_threadpool(_probar, proveedor)
    return JSONResponse({"ok": ok, "mensaje": mensaje})


# --------------------------------------------------------------------------- #
# Fuentes habilitadas POR MARCA (Contexto → etapa Stock)                      #
# --------------------------------------------------------------------------- #


def _fuente_marca(marca: str, proveedor: str) -> dict:
    """Estado de un proveedor PARA UNA MARCA: disponibilidad GLOBAL + toggle de la marca."""
    estado = stock_fotos.estado_fuente(proveedor, marca)
    return {
        "proveedor": estado["proveedor"],
        "nombre": estado["nombre"],
        "requiere_clave": estado["requiere_clave"],
        "disponible": estado["disponible"],
        "activa": estado["activa"],
        "motivo": estado["motivo"],
    }


def _estado_marca(marca: str, etiqueta: str) -> dict:
    """`{marca, etiqueta, fuentes:[...]}` con TODAS las fuentes del catálogo para una marca."""
    return {
        "marca": marca,
        "etiqueta": etiqueta,
        "fuentes": [_fuente_marca(marca, p) for p in stock_fotos.ids_proveedores()],
    }


async def fuentes_estado(request: Request) -> Response:
    """GET /api/stock/fuentes?marca=ID: qué fuentes usa una marca (toggles). SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = (request.query_params.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    return JSONResponse(_estado_marca(marca, marcas.etiqueta_de(marca)))


async def fuentes_guardar(request: Request) -> Response:
    """PUT /api/stock/fuentes/{marca}: fija qué proveedores usa la marca (JSON `{activas:[ids]}`).

    Persiste un CSV en `KENI_STOCK_FUENTES::{marca}`. Lista vacía o todas = sin filtro (todas
    las disponibles). Valida los ids contra el catálogo de proveedores. SOLO ADMIN.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not marcas.es_marca(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    datos = await leer_json(request)
    activas = datos.get("activas")
    if not isinstance(activas, list):
        return JSONResponse(
            {"error": "Se esperaba la lista de fuentes activas."}, status_code=400
        )
    validos = stock_fotos.ids_proveedores()
    ids = [p for p in validos if p in {str(a).strip().lower() for a in activas}]
    clave = config.clave_por_marca(config.ENV_STOCK_FUENTES, marca)
    try:
        if ids and len(ids) < len(validos):
            ajustes.guardar(clave, ",".join(ids))
        else:
            # Todas (o ninguna explícita) = sin filtro: limpia el override de la marca.
            ajustes.borrar(clave)
    except OSError:
        return JSONResponse(
            {"error": "No se pudieron guardar las fuentes."}, status_code=500
        )
    return JSONResponse(_estado_marca(marca, marcas.etiqueta_de(marca)))


RUTAS = [
    Route("/api/stock/proveedores", proveedores_estado, methods=["GET"]),
    Route("/api/stock/clave", clave_guardar, methods=["PUT"]),
    Route("/api/stock/clave/{proveedor}", clave_borrar, methods=["DELETE"]),
    Route("/api/stock/probar", clave_probar, methods=["POST"]),
    Route("/api/stock/fuentes", fuentes_estado, methods=["GET"]),
    Route("/api/stock/fuentes/{marca}", fuentes_guardar, methods=["PUT"]),
]
