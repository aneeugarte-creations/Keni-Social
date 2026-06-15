"""API Conexiones: clave del proveedor de imagen IA + credenciales de Metricool.

Dos areas, una misma regla de oro: los SECRETOS no salen nunca al navegador. Solo
se reporta presencia/estado y, como mucho, una PISTA (`····last4`).

  IMAGEN IA (almacen de secretos de la consola, `keni_consola.secretos`):
    GET    /api/conexiones/imagen          -> estado (sin la clave) + modelos disponibles
    PUT    /api/conexiones/imagen          -> guarda la clave (no la devuelve)
    PUT    /api/conexiones/imagen/modelo   -> fija el modelo de imagen (lista curada)
    POST   /api/conexiones/imagen/probar   -> valida la clave con una llamada BARATA
    DELETE /api/conexiones/imagen          -> borra la clave

  METRICOOL POR MARCA (config.toml de metricas, [metricool.marcas.<id>]):
    GET    /api/conexiones/metricool              -> estado por marca (sin token)
    PUT    /api/conexiones/metricool/{marca}      -> guarda user_token/user_id/blog_id
    DELETE /api/conexiones/metricool/{marca}      -> quita esa marca
    POST   /api/conexiones/metricool/{marca}/probar -> prueba EN VIVO (sin exponer token)
    POST   /api/conexiones/metricool/perfiles     -> descubre las marcas (blogId) de un token

Las metricas se consumen VIA Metricool (ADR 0005 §B): NO hay ingesta propia por
plataforma. La antigua seccion "Redes sociales" (un token global por plataforma que
alimentaba la fuente `real`/`FuenteCompuesta`) se RETIRO de Conexiones; el plumbing
de esa fuente sigue en `keni_metricas`, pero ya no se gestiona desde aqui.

REUTILIZA los helpers de metricas (`leer_config_existente` + `fusionar_config` +
`escribir_config_atomico`) para escribir el config.toml de forma atomica y segura;
NO duplica esa logica. Errores en espanol, sin tracebacks, sin filtrar secretos.

SOLO ADMIN (#153)
=================
La clave del proveedor de imagen y los tokens de Metricool son SECRETOS GLOBALES y
COMPARTIDOS (un unico fichero por despliegue). Antes cualquier usuario autenticado
podia leerlos/mutarlos; eso es una fuga de datos en un servicio multiusuario. Ahora
TODOS los endpoints de conexiones (lectura Y mutacion) exigen rol ADMIN: un editor
recibe 403. SOLO una SESION admin real puede gestionarlos; el TOKEN de mantenimiento
NO es admin (#150) y tambien recibe 403 aqui (no es un backdoor a los secretos). El gate
se aplica por handler leyendo el rol que el middleware dejo en `request.state`
(`keni_consola.permisos.es_admin`, fuente unica y ESTRICTA), igual que `/api/usuarios`.
El AISLAMIENTO por tenant (un almacen por cliente) queda diferido:
ver `docs/adr/0003-aislamiento-secretos-por-tenant.md`.
"""

from __future__ import annotations

from keni_metricas import asistente
from keni_metricas.config import ruta_config
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import media, permisos, secretos
from .._http_json import leer_json

# Mensaje de rechazo cuando un no-admin toca las conexiones (secretos globales).
_MSG_SOLO_ADMIN = (
    "Solo un administrador puede ver o cambiar las conexiones (claves y tokens)."
)


# --------------------------------------------------------------------------- #
# Imagen IA (almacen de secretos de la consola)                               #
# --------------------------------------------------------------------------- #


async def imagen_estado(request: Request) -> Response:
    """GET: estado del proveedor de imagen (proveedor, modelo, modelos, configurado, pista).

    `modelo` es el modelo de imagen EN USO (`media._modelo()`, con su precedencia) y
    `modelos` la lista curada para poblar el dropdown. NUNCA devuelve la clave: solo
    presencia y la pista `····last4`. SOLO ADMIN (#153): un editor recibe 403.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
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

    Valida que `api_key` no este vacia. Responde estado (sin la clave). SOLO ADMIN (#153).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
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
    `SeguridadConsola`; ademas, SOLO ADMIN (#153): un editor recibe 403.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
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
    """DELETE: borra la clave guardada del proveedor de imagen. SOLO ADMIN (#153)."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
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
    SOLO ADMIN (#153): un editor recibe 403 (no puede sondear la clave global).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    clave = secretos.obtener_clave_imagen()
    if clave is None:
        return JSONResponse({"ok": False, "mensaje": "No hay clave configurada."})
    ok, mensaje = _PROBADOR(clave)
    return JSONResponse({"ok": ok, "mensaje": mensaje})


# --------------------------------------------------------------------------- #
# Metricool (credenciales POR MARCA en el config.toml de metricas)            #
# --------------------------------------------------------------------------- #


def _config_existente() -> dict:
    """Lee el config.toml de metricas existente ({} si no existe). Solo lectura."""
    return asistente.leer_config_existente(ruta_config())
#
# A diferencia de las redes (un token global por plataforma), Metricool guarda
# credenciales POR MARCA: en el cliente cada marca es una cuenta Metricool distinta, con
# su PROPIO user_token (X-Mc-Auth) + user_id + blog_id. Se persisten en
# `[metricool.marcas.<id>]` del config.toml de metricas, vía los MISMOS helpers
# del asistente (atomico 0600). `user_token` esta en `asistente.CLAVES_SECRETAS`:
# nunca se devuelve por la API ni se loguea; del estado solo sale presencia +
# una PISTA no sensible del user_id (no secreto) y el blog_id.


def _marcas_metricool() -> list[tuple[str, str]]:
    """Marcas (id_metricas, etiqueta) que pueden tener credenciales de Metricool.

    Fuente UNICA: `keni_shared.marcas.opciones_metricas()` (la clave es el
    `id_metricas`, que es justo la clave de `[metricool.marcas.<id>]`).
    """
    from keni_shared import marcas as marcas_catalogo

    return marcas_catalogo.opciones_metricas()


def _es_marca_metricool(marca: str) -> bool:
    """True si `marca` es un id_metricas real del catalogo de marcas."""
    return any(marca == mid for mid, _ in _marcas_metricool())


def _marca_metricool(cfg: dict, marca: str) -> dict:
    """Tabla `[metricool.marcas.<marca>]` del config ({} si no existe)."""
    mc = cfg.get("metricool")
    mc = mc if isinstance(mc, dict) else {}
    marcas = mc.get("marcas")
    marcas = marcas if isinstance(marcas, dict) else {}
    tabla = marcas.get(marca)
    return tabla if isinstance(tabla, dict) else {}


def _credencial(tabla: dict, clave: str) -> str:
    """Valor str de una clave de la tabla de marca (cae a '' si falta o no es str)."""
    valor = tabla.get(clave)
    return valor if isinstance(valor, str) else ("" if valor is None else str(valor))


def _metricool_conectada(tabla: dict) -> bool:
    """True si la marca tiene los tres campos (token + user_id + blog_id) no vacios.

    El token no debe ser el placeholder (= sin token real). El default global
    `[metricool] user_token/user_id` NO se considera aqui: el estado refleja lo que
    esta GUARDADO para ESA marca (la consola gestiona credenciales por marca).
    """
    token = _credencial(tabla, "user_token")
    return bool(
        token
        and token != asistente.PLACEHOLDER_TOKEN
        and _credencial(tabla, "user_id")
        and _credencial(tabla, "blog_id")
    )


def _pista_user_id(user_id: str) -> str:
    """Pista NO sensible del user_id (no es secreto): se devuelve tal cual si existe."""
    return user_id


def estado_marcas_metricool() -> list[dict]:
    """Estado de conexion de Metricool POR MARCA, sin exponer NUNCA el user_token.

    Una entrada por marca del catalogo (`keni_shared.marcas.opciones_metricas()`):
    `{marca, etiqueta, conectado}` y, si esta conectada, la pista del user_id (no
    secreto) y el blog_id. FUENTE UNICA del juicio "conectada": la comparten el
    endpoint `GET /api/conexiones/metricool` y el doctor (`/api/estado`, chequeo
    `metricas:metricool`). Propaga errores de lectura del config (el handler los
    convierte en HTTP; el doctor los degrada a chequeo en error).
    """
    cfg = _config_existente()
    marcas = []
    for mid, etiqueta in _marcas_metricool():
        tabla = _marca_metricool(cfg, mid)
        conectado = _metricool_conectada(tabla)
        entrada: dict = {"marca": mid, "etiqueta": etiqueta, "conectado": conectado}
        if conectado:
            entrada["user_id_pista"] = _pista_user_id(_credencial(tabla, "user_id"))
            entrada["blog_id"] = _credencial(tabla, "blog_id")
        marcas.append(entrada)
    return marcas


async def metricool_estado(request: Request) -> Response:
    """GET: estado por marca de Metricool (sin exponer NUNCA el user_token).

    Lista TODAS las marcas del catalogo con su estado conectado/desconectado y, si
    estan, una pista del user_id (no secreto) y el blog_id. SOLO ADMIN (#153).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse({"marcas": estado_marcas_metricool()})


def _escribir_marca_metricool(marca: str, valores: dict[str, str]) -> None:
    """Persiste `[metricool.marcas.<marca>]` en el config.toml (atomico 0600).

    REUTILIZA los helpers del asistente: lee el existente, fusiona SOLO esta marca
    (sin clobberar otras marcas ni otras secciones) y escribe de forma atomica.
    """
    ruta = ruta_config()
    existente = asistente.leer_config_existente(ruta)
    nuevo = {"metricool": {"marcas": {marca: valores}}}
    fusionado = asistente.fusionar_config(existente, nuevo)
    asistente.escribir_config_atomico(ruta, fusionado)


async def metricool_guardar(request: Request) -> Response:
    """PUT: guarda las credenciales de UNA marca (JSON `{user_token, user_id, blog_id}`).

    No devuelve el token. Valida que `{marca}` es una marca real y que los tres
    campos vienen no vacios. SOLO ADMIN (#153).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    datos = await leer_json(request)
    campos = {}
    for clave, etiqueta in (
        ("user_token", "el token de Metricool"),
        ("user_id", "el user_id"),
        ("blog_id", "el blog_id"),
    ):
        valor = datos.get(clave)
        if not isinstance(valor, str) or not valor.strip():
            return JSONResponse({"error": f"Falta {etiqueta}."}, status_code=400)
        campos[clave] = valor.strip()
    try:
        _escribir_marca_metricool(marca, campos)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar la credencial de Metricool."}, status_code=500
        )
    return JSONResponse({"conectado": True, "mensaje": "Credencial de Metricool guardada."})


async def metricool_borrar(request: Request) -> Response:
    """DELETE: quita la marca de `[metricool.marcas.<marca>]`. SOLO ADMIN (#153)."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    ruta = ruta_config()
    try:
        cfg = asistente.leer_config_existente(ruta)
        marcas = cfg.get("metricool", {}).get("marcas") if isinstance(cfg.get("metricool"), dict) else None
        if isinstance(marcas, dict) and marca in marcas:
            del marcas[marca]
            asistente.escribir_config_atomico(ruta, cfg)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo quitar la credencial de Metricool."}, status_code=500
        )
    return JSONResponse({"mensaje": "Credencial de Metricool eliminada."})


def _probar_metricool(user_token: str, user_id: str, blog_id: str) -> tuple[bool, str]:
    """Prueba EN VIVO una credencial de Metricool con un GET de lectura barato.

    Llama a `/admin/simpleProfiles` (lista de marcas del usuario): autentica con
    `X-Mc-Auth` + `userId` + `blogId` y, si responde 200, la credencial es valida.
    NO expone el token en ningun mensaje. Punto INYECTABLE/mockeable (`_PROBADOR_MC`).
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia transitiva
        return False, "Falta la librería para probar la conexión en este equipo."
    try:
        respuesta = httpx.get(
            "https://app.metricool.com/api/admin/simpleProfiles",
            headers={"X-Mc-Auth": user_token},
            params={"userId": user_id, "blogId": blog_id},
            timeout=30,
            follow_redirects=False,
        )
    except Exception:  # noqa: BLE001 -- cualquier fallo de red: mensaje en espanol
        return False, "No se pudo contactar con Metricool."
    if respuesta.status_code == 200:
        return True, "La credencial de Metricool funciona."
    if respuesta.status_code in (401, 403):
        return False, "Metricool rechazó la credencial (token o IDs incorrectos)."
    return False, "Metricool devolvió un error al validar la credencial."


# Punto INYECTABLE: lo unico que toca la red al "probar". Los tests lo parchean.
_PROBADOR_MC = _probar_metricool


async def metricool_probar(request: Request) -> Response:
    """POST: prueba EN VIVO la credencial GUARDADA de una marca. SOLO ADMIN (#153).

    Usa el token YA guardado de la marca (nunca llega por el body, nunca sale por la
    respuesta). Si falta alguna credencial, responde `{ok:false}` con mensaje claro.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    tabla = _marca_metricool(_config_existente(), marca)
    token = _credencial(tabla, "user_token")
    user_id = _credencial(tabla, "user_id")
    blog_id = _credencial(tabla, "blog_id")
    if not (token and token != asistente.PLACEHOLDER_TOKEN and user_id and blog_id):
        return JSONResponse(
            {"ok": False, "mensaje": "Esta marca no tiene credenciales completas guardadas."}
        )
    ok, detalle = _PROBADOR_MC(token, user_id, blog_id)
    return JSONResponse({"ok": ok, "detalle": detalle})


def _listar_perfiles(user_token: str, user_id: str) -> tuple[bool, str, list[dict]]:
    """Descubre las marcas (blogId) de un user_token via `GET /admin/simpleProfiles`.

    Autentica con `X-Mc-Auth: <user_token>` + query `userId=<user_id>` (igual que
    `FuenteMetricool`). NO persiste nada y NO devuelve el token. El parseo es DEFENSIVO
    (varios alias por id/label) porque la forma exacta de cada perfil no esta fijada en
    el swagger. Punto INYECTABLE/mockeable (`_PROBADOR_PERFILES`): los tests lo parchean
    para NUNCA tocar la red. Devuelve `(ok, mensaje, marcas)` donde cada marca es
    `{"blog_id": str, "label": str}`.
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover -- httpx es dependencia transitiva
        return False, "Falta la librería para consultar Metricool en este equipo.", []
    try:
        respuesta = httpx.get(
            "https://app.metricool.com/api/admin/simpleProfiles",
            headers={"X-Mc-Auth": user_token},
            params={"userId": user_id},
            timeout=30,
            follow_redirects=False,
        )
    except Exception:  # noqa: BLE001 -- cualquier fallo de red: mensaje en espanol
        return False, "No se pudo contactar con Metricool.", []
    if respuesta.status_code in (401, 403):
        return False, "Metricool rechazó el token o el userId.", []
    if respuesta.status_code != 200:
        return False, "Metricool devolvió un error al listar las marcas.", []
    try:
        cuerpo = respuesta.json()
    except ValueError:
        return False, "Metricool devolvió una respuesta no válida.", []
    marcas = _parsear_perfiles(cuerpo)
    if not marcas:
        return False, "Metricool no devolvió ninguna marca para este token.", []
    return True, "Marcas encontradas.", marcas


def _parsear_perfiles(cuerpo: object) -> list[dict]:
    """Parsea DEFENSIVAMENTE la respuesta de `simpleProfiles` a `[{blog_id, label}]`.

    Acepta tanto una lista de perfiles como un dict con la lista bajo claves comunes
    (`profiles`/`data`/`blogs`/`results`). De cada perfil toma el id por varios alias
    (`blogId`/`id`/`blog_id`) y la etiqueta (`label`/`name`/`title`/`brand`). Descarta
    los que no tengan id; cae a su propio id como label si falta.
    """
    perfiles = cuerpo
    if isinstance(cuerpo, dict):
        for clave in ("profiles", "data", "blogs", "results", "simpleProfiles"):
            valor = cuerpo.get(clave)
            if isinstance(valor, list):
                perfiles = valor
                break
    if not isinstance(perfiles, list):
        return []
    marcas: list[dict] = []
    for perfil in perfiles:
        if not isinstance(perfil, dict):
            continue
        bid = None
        for clave in ("blogId", "blog_id", "id"):
            valor = perfil.get(clave)
            if valor not in (None, ""):
                bid = str(valor)
                break
        if bid is None:
            continue
        label = None
        for clave in ("label", "name", "title", "brand", "blogName"):
            valor = perfil.get(clave)
            if isinstance(valor, str) and valor.strip():
                label = valor.strip()
                break
        marcas.append({"blog_id": bid, "label": label or bid})
    return marcas


# Punto INYECTABLE: lo unico que toca la red al descubrir marcas. Los tests lo parchean.
_PROBADOR_PERFILES = _listar_perfiles


async def metricool_perfiles(request: Request) -> Response:
    """POST: descubre las marcas (blogId) de un token de Metricool. SOLO ADMIN (#153).

    Body `{user_token, user_id}`. Llama a `GET /admin/simpleProfiles` y devuelve
    `{"marcas": [{"blog_id", "label"}, ...]}`. NO persiste NADA (el config.toml no se
    toca) y NO devuelve el token en ningun caso. Si la auth falla o no hay marcas,
    responde con un error claro en espanol.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    datos = await leer_json(request)
    user_token = datos.get("user_token")
    user_id = datos.get("user_id")
    if not isinstance(user_token, str) or not user_token.strip():
        return JSONResponse({"error": "Falta el token de Metricool."}, status_code=400)
    if not isinstance(user_id, str) or not user_id.strip():
        return JSONResponse({"error": "Falta el user_id."}, status_code=400)
    ok, mensaje, marcas = _PROBADOR_PERFILES(user_token.strip(), user_id.strip())
    if not ok:
        return JSONResponse({"error": mensaje}, status_code=502)
    # Solo blog_id + label salen al cliente; el token NUNCA se eco ni se persiste.
    return JSONResponse({"marcas": marcas})


RUTAS = [
    Route("/api/conexiones/imagen", imagen_estado, methods=["GET"]),
    Route("/api/conexiones/imagen", imagen_guardar, methods=["PUT"]),
    Route("/api/conexiones/imagen", imagen_borrar, methods=["DELETE"]),
    Route("/api/conexiones/imagen/modelo", imagen_modelo_guardar, methods=["PUT"]),
    Route("/api/conexiones/imagen/probar", imagen_probar, methods=["POST"]),
    Route("/api/conexiones/metricool", metricool_estado, methods=["GET"]),
    Route("/api/conexiones/metricool/perfiles", metricool_perfiles, methods=["POST"]),
    Route("/api/conexiones/metricool/{marca}", metricool_guardar, methods=["PUT"]),
    Route("/api/conexiones/metricool/{marca}", metricool_borrar, methods=["DELETE"]),
    Route("/api/conexiones/metricool/{marca}/probar", metricool_probar, methods=["POST"]),
]
