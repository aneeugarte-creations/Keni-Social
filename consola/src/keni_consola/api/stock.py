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

  CREDENCIALES DE AGENCIAS (almacen de secretos, bloque `[agencias.<agencia>]`). AFP y
  Reuters tienen campos PROPIOS; el formulario se dirige por el catálogo `_CAMPOS_AGENCIA`.
    GET    /api/stock/agencias               -> estado por agencia + sus campos (sin secretos)
    PUT    /api/stock/agencias/{agencia}     -> guarda las credenciales de la agencia
    DELETE /api/stock/agencias/{agencia}     -> borra todas sus credenciales
    POST   /api/stock/agencias/{agencia}/probar -> valida en vivo (AFP token; Reuters presencia)

Las claves se gestionan en Sistema → Proveedores (globales); los toggles, en la subpágina
de la etapa Stock (Contexto), por marca.

SOLO ADMIN: las claves de stock son SECRETOS compartidos del despliegue. TODOS los
endpoints (lectura Y mutación) exigen rol admin; un editor recibe 403. Mismo gate
estricto que `conexiones` (`keni_consola.permisos.es_admin`). Errores en español, sin
tracebacks, sin filtrar secretos.
"""

from __future__ import annotations

from keni_shared import marcas
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import agencias, ajustes, config, permisos, secretos, stock_fotos
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


# --------------------------------------------------------------------------- #
# Credenciales de AGENCIAS de noticias/foto (Sistema → Proveedores)           #
# --------------------------------------------------------------------------- #
# Cada agencia tiene campos PROPIOS (AFP OAuth2: client_id/client_secret/base_url; Reuters
# Bearer: api_key/base_url), así que el formulario se dirige por este catálogo de metadatos
# (fuente única). Los campos `secreto` NUNCA devuelven su valor (solo presencia + pista);
# `base_url` NO es secreto, así que se devuelve su valor efectivo (secreto/env/defecto).

_CAMPOS_AGENCIA: dict[str, dict] = {
    "afp": {
        "nombre": "AFP",
        "campos": [
            {"clave": "client_id", "etiqueta": "Client ID", "secreto": True, "opcional": False},
            {"clave": "client_secret", "etiqueta": "Client Secret", "secreto": True, "opcional": False},
            {"clave": "base_url", "etiqueta": "Base URL", "secreto": False, "opcional": True,
             "defecto": config.AFP_BASE_URL_DEF},
        ],
    },
    "reuters": {
        "nombre": "Reuters",
        "campos": [
            {"clave": "api_key", "etiqueta": "API key (Bearer)", "secreto": True, "opcional": False},
            {"clave": "base_url", "etiqueta": "Base URL", "secreto": False, "opcional": True,
             "defecto": config.REUTERS_BASE_URL_DEF},
        ],
    },
}

# Estado de configuración de cada agencia (deriva de los accesores de config).
_CONFIGURADO_AGENCIA = {
    "afp": config.afp_configurado,
    "reuters": config.reuters_configurado,
}

# Valor EFECTIVO de cada campo NO secreto (secreto UI > env > defecto), por accesor de config.
_VALOR_NO_SECRETO = {
    ("afp", "base_url"): config.afp_base_url,
    ("reuters", "base_url"): config.reuters_base_url,
}


def _campo_estado(agencia: str, campo: dict) -> dict:
    """Estado de UN campo del catálogo: presencia+pista si es secreto, valor si no lo es."""
    clave = campo["clave"]
    base = {
        "clave": clave,
        "etiqueta": campo["etiqueta"],
        "secreto": campo["secreto"],
        "opcional": campo["opcional"],
    }
    if campo["secreto"]:
        pista = secretos.estado_credencial_agencia(agencia, clave)
        base["configurado"] = pista["configurado"]
        base["pista"] = pista["pista"]
    else:
        accesor = _VALOR_NO_SECRETO.get((agencia, clave))
        base["valor"] = accesor() if accesor else (campo.get("defecto") or "")
    return base


def _estado_agencia(agencia: str) -> dict:
    """`{agencia, nombre, configurado, disponible, motivo, campos:[...]}` de una agencia."""
    meta = _CAMPOS_AGENCIA[agencia]
    configurado = _CONFIGURADO_AGENCIA[agencia]()
    return {
        "agencia": agencia,
        "nombre": meta["nombre"],
        "configurado": configurado,
        "disponible": configurado,
        "motivo": "" if configurado else "Faltan credenciales por configurar.",
        "campos": [_campo_estado(agencia, c) for c in meta["campos"]],
    }


async def agencias_estado(request: Request) -> Response:
    """GET /api/stock/agencias: estado de las credenciales de las agencias. SOLO ADMIN.

    Nunca devuelve el valor de un campo secreto (solo presencia + pista `····last4`).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse(
        {"agencias": [_estado_agencia(a) for a in _CAMPOS_AGENCIA]}
    )


async def agencia_guardar(request: Request) -> Response:
    """PUT /api/stock/agencias/{agencia}: guarda credenciales (JSON `{valores:{campo:valor}}`).

    Valida agencia y campos contra el catálogo. Guarda cada campo NO vacío; un campo que
    llegue vacío NO se toca (no se borra al guardar). Devuelve el estado nuevo. SOLO ADMIN.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    agencia = (request.path_params["agencia"] or "").strip().lower()
    meta = _CAMPOS_AGENCIA.get(agencia)
    if meta is None:
        return JSONResponse({"error": "Agencia desconocida."}, status_code=400)
    datos = await leer_json(request)
    valores = datos.get("valores")
    if not isinstance(valores, dict):
        return JSONResponse(
            {"error": "Se esperaba el objeto de valores a guardar."}, status_code=400
        )
    claves_validas = {c["clave"] for c in meta["campos"]}
    if any(str(k).strip().lower() not in claves_validas for k in valores):
        return JSONResponse(
            {"error": "Campo no válido para esta agencia."}, status_code=400
        )
    try:
        for clave in claves_validas:
            valor = valores.get(clave)
            if isinstance(valor, str) and valor.strip():
                secretos.guardar_credencial_agencia(agencia, clave, valor)
    except OSError:
        return JSONResponse(
            {"error": "No se pudieron guardar las credenciales."}, status_code=500
        )
    return JSONResponse(_estado_agencia(agencia))


async def agencia_borrar(request: Request) -> Response:
    """DELETE /api/stock/agencias/{agencia}: borra TODAS las credenciales de la agencia. SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    agencia = (request.path_params["agencia"] or "").strip().lower()
    if agencia not in _CAMPOS_AGENCIA:
        return JSONResponse({"error": "Agencia desconocida."}, status_code=400)
    try:
        secretos.borrar_agencia(agencia)
    except OSError:
        return JSONResponse(
            {"error": "No se pudieron borrar las credenciales."}, status_code=500
        )
    return JSONResponse(_estado_agencia(agencia))


def _probar_agencia(agencia: str) -> tuple[bool, str]:
    """Valida en vivo las credenciales de una agencia, sin exponer secretos.

    AFP: pide un token OAuth2 real (`agencias.obtener_token_afp`, transporte inyectable —
    OFFLINE en tests). Reuters: su API de foto es de contrato y no tiene endpoint público de
    validación, así que se confirma sólo la presencia de credenciales.
    """
    if agencia == "afp":
        if not config.afp_configurado():
            return False, "No hay credenciales de AFP configuradas."
        try:
            agencias.obtener_token_afp()
        except agencias.rss.RSSError as e:
            return False, str(e)
        return True, "Conexión con AFP correcta (token OAuth2 obtenido)."
    if agencia == "reuters":
        if not config.reuters_configurado():
            return False, "No hay credenciales de Reuters configuradas."
        return True, "Credenciales presentes; la validación en vivo requiere la API de Reuters."
    return False, "Agencia desconocida."


async def agencia_probar(request: Request) -> Response:
    """POST /api/stock/agencias/{agencia}/probar: valida las credenciales guardadas. SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    agencia = (request.path_params["agencia"] or "").strip().lower()
    if agencia not in _CAMPOS_AGENCIA:
        return JSONResponse({"error": "Agencia desconocida."}, status_code=400)
    ok, mensaje = await run_in_threadpool(_probar_agencia, agencia)
    return JSONResponse({"ok": ok, "mensaje": mensaje})


RUTAS = [
    Route("/api/stock/proveedores", proveedores_estado, methods=["GET"]),
    Route("/api/stock/clave", clave_guardar, methods=["PUT"]),
    Route("/api/stock/clave/{proveedor}", clave_borrar, methods=["DELETE"]),
    Route("/api/stock/probar", clave_probar, methods=["POST"]),
    Route("/api/stock/fuentes", fuentes_estado, methods=["GET"]),
    Route("/api/stock/fuentes/{marca}", fuentes_guardar, methods=["PUT"]),
    Route("/api/stock/agencias", agencias_estado, methods=["GET"]),
    Route("/api/stock/agencias/{agencia}", agencia_guardar, methods=["PUT"]),
    Route("/api/stock/agencias/{agencia}", agencia_borrar, methods=["DELETE"]),
    Route("/api/stock/agencias/{agencia}/probar", agencia_probar, methods=["POST"]),
]
