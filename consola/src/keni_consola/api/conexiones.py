"""API Conexiones: clave del proveedor de imagen IA + tokens de redes sociales.

Dos areas, una misma regla de oro: los SECRETOS no salen nunca al navegador. Solo
se reporta presencia/estado y, como mucho, una PISTA (`····last4`).

  IMAGEN IA (almacen de secretos de la consola, `keni_consola.secretos`):
    GET    /api/conexiones/imagen          -> estado (sin la clave) + modelos disponibles
    PUT    /api/conexiones/imagen          -> guarda la clave (no la devuelve)
    PUT    /api/conexiones/imagen/modelo   -> fija el modelo de imagen (lista curada)
    POST   /api/conexiones/imagen/probar   -> valida la clave con una llamada BARATA
    DELETE /api/conexiones/imagen          -> borra la clave

  REDES SOCIALES (config.toml de metricas, via `keni_metricas.asistente`):
    GET    /api/conexiones/redes               -> estado por plataforma (conectado bool)
    PUT    /api/conexiones/redes/{plataforma}  -> pega el token (no lo devuelve)
    DELETE /api/conexiones/redes/{plataforma}  -> quita el token (placeholder)

REUTILIZA los helpers de metricas (`leer_config_existente` + `fusionar_config` +
`escribir_config_atomico`) para escribir el config.toml de forma atomica y segura;
NO duplica esa logica. Errores en espanol, sin tracebacks, sin filtrar secretos.
"""

from __future__ import annotations

from keni_metricas import asistente
from keni_metricas.config import ruta_config
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import media, secretos
from .._http_json import leer_json

# Nombres legibles por plataforma de redes (las plataformas se DERIVAN de
# `asistente.CAMPO_TOKEN`, no se hardcodean aparte).
_NOMBRE_RED: dict[str, str] = {
    "meta": "Meta (Facebook/Instagram)",
    "youtube": "YouTube",
    "x": "X",
    "tiktok": "TikTok",
}


def _plataformas() -> tuple[str, ...]:
    """Plataformas de redes reconocidas, derivadas de `asistente.CAMPO_TOKEN`."""
    return tuple(asistente.CAMPO_TOKEN.keys())


def _nombre_red(plataforma: str) -> str:
    """Nombre legible de una plataforma (cae al propio id si no hay etiqueta)."""
    return _NOMBRE_RED.get(plataforma, plataforma)


# --------------------------------------------------------------------------- #
# Imagen IA (almacen de secretos de la consola)                               #
# --------------------------------------------------------------------------- #


async def imagen_estado(request: Request) -> Response:
    """GET: estado del proveedor de imagen (proveedor, modelo, modelos, configurado, pista).

    `modelo` es el modelo de imagen EN USO (`media._modelo()`, con su precedencia) y
    `modelos` la lista curada para poblar el dropdown. NUNCA devuelve la clave: solo
    presencia y la pista `····last4`.
    """
    estado = secretos.estado_imagen()
    return JSONResponse(
        {
            "proveedor": estado["proveedor"],
            "modelo": media._modelo(),
            "modelos": media.modelos_disponibles(),
            "configurado": estado["configurado"],
            "pista": estado["pista"],
        }
    )


async def imagen_guardar(request: Request) -> Response:
    """PUT: guarda la clave del proveedor de imagen (JSON `{proveedor?, api_key}`).

    Valida que `api_key` no este vacia. Responde estado (sin la clave).
    """
    datos = await leer_json(request)
    api_key = datos.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        return JSONResponse(
            {"error": "Falta la clave del proveedor de imagen."}, status_code=400
        )
    proveedor = datos.get("proveedor")
    proveedor = proveedor if isinstance(proveedor, str) else ""
    try:
        secretos.guardar_clave_imagen(proveedor, api_key)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar la clave del proveedor de imagen."},
            status_code=500,
        )
    return JSONResponse({"configurado": True, "mensaje": "Clave de imagen guardada."})


async def imagen_modelo_guardar(request: Request) -> Response:
    """PUT: fija el modelo de imagen elegido por la UI (JSON `{modelo}`).

    VALIDA que el id este en la lista curada (`media.MODELOS_IMAGEN`); si no, 400 en
    espanol. Persiste SOLO el campo modelo (preserva clave/proveedor). Mismo patron de
    auth que el resto de conexiones: la barrera de sesion + CSRF la aplica el middleware
    `SeguridadConsola`; este handler no anade un gate de rol propio.
    """
    datos = await leer_json(request)
    modelo = datos.get("modelo")
    if not isinstance(modelo, str) or not modelo.strip():
        return JSONResponse({"error": "Falta el modelo de imagen."}, status_code=400)
    modelo = modelo.strip()
    if not media.modelo_valido(modelo):
        return JSONResponse(
            {"error": "Modelo de imagen no reconocido."}, status_code=400
        )
    try:
        secretos.guardar_modelo_imagen(modelo)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar el modelo de imagen."}, status_code=500
        )
    return JSONResponse({"modelo": modelo})


async def imagen_borrar(request: Request) -> Response:
    """DELETE: borra la clave guardada del proveedor de imagen."""
    try:
        secretos.borrar_clave_imagen()
    except OSError:
        return JSONResponse(
            {"error": "No se pudo borrar la clave del proveedor de imagen."},
            status_code=500,
        )
    return JSONResponse({"mensaje": "Clave de imagen eliminada."})


def _probar_openrouter(clave: str) -> tuple[bool, str]:
    """Valida una clave de OpenRouter con una llamada BARATA: `GET /api/v1/auth/key`.

    NO genera ninguna imagen (sin coste): solo consulta los datos de la propia clave
    (requiere Bearer). Punto INYECTABLE/mockeable: los tests parchean `_PROBADOR` para
    NUNCA tocar la red. La clave nunca aparece en los mensajes de salida.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia transitiva
        return False, "Falta la librería para probar la conexión en este equipo."
    try:
        respuesta = httpx.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {clave}"},
            timeout=30,
            follow_redirects=False,
        )
    except Exception:  # noqa: BLE001 -- cualquier fallo de red: mensaje en espanol
        return False, "No se pudo contactar al proveedor de imagen."
    if respuesta.status_code == 200:
        return True, "La clave de OpenRouter funciona."
    if respuesta.status_code in (401, 403):
        return False, "La clave fue rechazada por OpenRouter."
    return False, "OpenRouter devolvió un error al validar la clave."


# Punto INYECTABLE: lo unico que toca la red al "probar". Los tests lo parchean.
_PROBADOR = _probar_openrouter


async def imagen_probar(request: Request) -> Response:
    """POST: valida la clave GUARDADA con una llamada barata (sin generar imagen).

    Si no hay clave configurada responde `{ok:false, ...}`. La clave nunca sale.
    """
    clave = secretos.obtener_clave_imagen()
    if clave is None:
        return JSONResponse({"ok": False, "mensaje": "No hay clave configurada."})
    ok, mensaje = _PROBADOR(clave)
    return JSONResponse({"ok": ok, "mensaje": mensaje})


# --------------------------------------------------------------------------- #
# Redes sociales (config.toml de metricas)                                    #
# --------------------------------------------------------------------------- #


def _config_existente() -> dict:
    """Lee el config.toml de metricas existente ({} si no existe). Solo lectura."""
    return asistente.leer_config_existente(ruta_config())


def _token_bloque(cfg: dict, plataforma: str) -> str | None:
    """Token actual del bloque de una plataforma (o None si falta)."""
    creds = cfg.get("credenciales")
    creds = creds if isinstance(creds, dict) else {}
    bloque = creds.get(plataforma)
    bloque = bloque if isinstance(bloque, dict) else {}
    campo = asistente.CAMPO_TOKEN.get(plataforma)
    valor = bloque.get(campo) if campo else None
    return valor if isinstance(valor, str) else None


def _conectado(token: str | None) -> bool:
    """True si el token existe y no es el placeholder (= la red esta conectada)."""
    return bool(token) and token != asistente.PLACEHOLDER_TOKEN


async def redes_estado(request: Request) -> Response:
    """GET: estado de conexion por plataforma de redes (sin exponer ningun token)."""
    cfg = _config_existente()
    redes = [
        {
            "plataforma": p,
            "nombre": _nombre_red(p),
            "conectado": _conectado(_token_bloque(cfg, p)),
        }
        for p in _plataformas()
    ]
    return JSONResponse({"redes": redes})


def _escribir_token(plataforma: str, token: str) -> None:
    """Escribe el token de una plataforma en el config.toml de metricas (atomico).

    REUTILIZA los helpers de metricas: lee el existente, fusiona SOLO el campo del
    token de ese bloque (sin clobberar app_id/secret ni otros bloques) y escribe de
    forma atomica con permisos `0600`.
    """
    ruta = ruta_config()
    existente = asistente.leer_config_existente(ruta)
    campo = asistente.CAMPO_TOKEN[plataforma]
    nuevo = {"credenciales": {plataforma: {campo: token}}}
    fusionado = asistente.fusionar_config(existente, nuevo)
    asistente.escribir_config_atomico(ruta, fusionado)


async def redes_guardar(request: Request) -> Response:
    """PUT: pega el token de una plataforma (JSON `{token}`). No lo devuelve."""
    plataforma = request.path_params["plataforma"]
    if plataforma not in asistente.CAMPO_TOKEN:
        return JSONResponse({"error": "Plataforma desconocida."}, status_code=400)
    datos = await leer_json(request)
    token = datos.get("token")
    if not isinstance(token, str) or not token.strip():
        return JSONResponse({"error": "Falta el token de la red."}, status_code=400)
    try:
        _escribir_token(plataforma, token.strip())
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar el token de la red."}, status_code=500
        )
    return JSONResponse(
        {"conectado": True, "mensaje": f"{_nombre_red(plataforma)} conectada."}
    )


async def redes_borrar(request: Request) -> Response:
    """DELETE: quita el token de una plataforma (lo deja en el placeholder)."""
    plataforma = request.path_params["plataforma"]
    if plataforma not in asistente.CAMPO_TOKEN:
        return JSONResponse({"error": "Plataforma desconocida."}, status_code=400)
    try:
        _escribir_token(plataforma, asistente.PLACEHOLDER_TOKEN)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo quitar el token de la red."}, status_code=500
        )
    return JSONResponse({"mensaje": f"{_nombre_red(plataforma)} desconectada."})


RUTAS = [
    Route("/api/conexiones/imagen", imagen_estado, methods=["GET"]),
    Route("/api/conexiones/imagen", imagen_guardar, methods=["PUT"]),
    Route("/api/conexiones/imagen", imagen_borrar, methods=["DELETE"]),
    Route("/api/conexiones/imagen/modelo", imagen_modelo_guardar, methods=["PUT"]),
    Route("/api/conexiones/imagen/probar", imagen_probar, methods=["POST"]),
    Route("/api/conexiones/redes", redes_estado, methods=["GET"]),
    Route("/api/conexiones/redes/{plataforma}", redes_guardar, methods=["PUT"]),
    Route("/api/conexiones/redes/{plataforma}", redes_borrar, methods=["DELETE"]),
]
