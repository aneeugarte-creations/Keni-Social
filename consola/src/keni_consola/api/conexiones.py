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
plataforma.

REUTILIZA los helpers de metricas (`leer_config_existente` + `fusionar_config` +
`escribir_config_atomico`) para escribir el config.toml de forma atomica y segura;
NO duplica esa logica. Errores en espanol, sin tracebacks, sin filtrar secretos.

SOLO ADMIN
=================
La clave del proveedor de imagen y los tokens de Metricool son SECRETOS GLOBALES y
COMPARTIDOS (un unico fichero por despliegue). Antes cualquier usuario autenticado
podia leerlos/mutarlos; eso es una fuga de datos en un servicio multiusuario. Ahora
TODOS los endpoints de conexiones (lectura Y mutacion) exigen rol ADMIN: un editor
recibe 403. SOLO una SESION admin real puede gestionarlos; el TOKEN de mantenimiento
NO es admin y tambien recibe 403 aqui (no es un backdoor a los secretos). El gate
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
    presencia y la pista `····last4`. SOLO ADMIN: un editor recibe 403.
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

    Valida que `api_key` no este vacia. Responde estado (sin la clave). SOLO ADMIN.
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
    `SeguridadConsola`; ademas, SOLO ADMIN: un editor recibe 403.
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
    """DELETE: borra la clave guardada del proveedor de imagen. SOLO ADMIN."""
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
    SOLO ADMIN: un editor recibe 403 (no puede sondear la clave global).
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
    estan, una pista del user_id (no secreto) y el blog_id. SOLO ADMIN.
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
    campos vienen no vacios. SOLO ADMIN.
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
    """DELETE: quita la marca de `[metricool.marcas.<marca>]`. SOLO ADMIN."""
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
    """POST: prueba EN VIVO la credencial GUARDADA de una marca. SOLO ADMIN.

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
    """POST: descubre las marcas (blogId) de un token de Metricool. SOLO ADMIN.

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


# --------------------------------------------------------------------------- #
# Postproxy (canal de pieza alternativo a Metricool)                    #
# --------------------------------------------------------------------------- #
#
# Modelo de secreto distinto al de Metricool: Postproxy usa UNA api_key GLOBAL
# (header Bearer), tratada como un SECRETO GLOBAL — igual de delicado que el
# user_token de Metricool: NUNCA se devuelve, solo una pista `····last4`. Lo que
# varia por marca es el `profile_group_id` (a que grupo de perfiles publica). Mismo
# patron que Metricool: helpers `_config_existente` (compartido), escritura atomica
# `_escribir_postproxy_global` / `_escribir_marca_postproxy`, guard SOLO ADMIN, y un
# punto INYECTABLE por operacion de red (`_PROBADOR_PP_*`) que los tests parchean.

from keni_metricas.fuentes import postproxy as _pp_cliente  # noqa: E402


def _postproxy_global(cfg: dict) -> dict:
    """Tabla `[postproxy]` del config ({} si no existe)."""
    pp = cfg.get("postproxy")
    return pp if isinstance(pp, dict) else {}


def _postproxy_api_key(cfg: dict) -> str:
    """api_key global GUARDADA en el config ('' si no hay). Solo uso interno."""
    return _credencial(_postproxy_global(cfg), "api_key")


def _marca_postproxy(cfg: dict, marca: str) -> dict:
    """Tabla `[postproxy.marcas.<marca>]` del config ({} si no existe)."""
    pp = _postproxy_global(cfg)
    marcas = pp.get("marcas")
    marcas = marcas if isinstance(marcas, dict) else {}
    tabla = marcas.get(marca)
    return tabla if isinstance(tabla, dict) else {}


def _pista_secreto(valor: str) -> str | None:
    """Pista NO sensible de un secreto: `····last4` (None si no hay valor)."""
    if not valor:
        return None
    return "····" + valor[-4:] if len(valor) >= 4 else "····"


def _canal_marca_postproxy(tabla: dict) -> str:
    """Canal de publicación GUARDADO para una marca (validado): default `metricool`.

    Fuente única de la validación: `keni_metricas.config.normalizar_canal` (un valor
    desconocido o ausente cae a `metricool`, el default sin cambio de comportamiento).
    """
    from keni_metricas.config import normalizar_canal

    return normalizar_canal(tabla.get("canal"))


def estado_postproxy() -> dict:
    """Estado de Postproxy: api_key configurada (solo pista) + grupo y canal por marca.

    `{configurado, pista, marcas: [{marca, etiqueta, profile_group_id, canal}]}`. NUNCA
    expone la api_key (solo `····last4`). Una entrada por marca del catalogo de metricas.
    `canal` ∈ {metricool, postproxy} (default `metricool`): el canal de publicación de
    esa marca, ortogonal a tener grupo o no.
    """
    cfg = _config_existente()
    api_key = _postproxy_api_key(cfg)
    marcas = []
    for mid, etiqueta in _marcas_metricool():
        tabla = _marca_postproxy(cfg, mid)
        grupo = _credencial(tabla, "profile_group_id") or None
        marcas.append({
            "marca": mid,
            "etiqueta": etiqueta,
            "profile_group_id": grupo,
            "canal": _canal_marca_postproxy(tabla),
        })
    return {
        "configurado": bool(api_key),
        "pista": _pista_secreto(api_key),
        "marcas": marcas,
    }


async def postproxy_estado(request: Request) -> Response:
    """GET: estado de Postproxy (api_key como pista) + grupo por marca. SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    return JSONResponse(estado_postproxy())


def _escribir_postproxy_global(api_key: str) -> None:
    """Persiste `[postproxy] api_key` en el config.toml (atomico 0600).

    REUTILIZA los helpers del asistente: lee el existente, fusiona SOLO la api_key (sin
    clobberar `[postproxy.marcas]` ni otras secciones) y escribe de forma atomica.
    """
    ruta = ruta_config()
    existente = asistente.leer_config_existente(ruta)
    fusionado = asistente.fusionar_config(existente, {"postproxy": {"api_key": api_key}})
    asistente.escribir_config_atomico(ruta, fusionado)


def _escribir_marca_postproxy(marca: str, valores: dict[str, str]) -> None:
    """Persiste `[postproxy.marcas.<marca>]` en el config.toml (atomico 0600).

    Espejo de `_escribir_marca_metricool`: fusiona SOLO esta marca (sin tocar la api_key
    global, otras marcas ni otras secciones).
    """
    ruta = ruta_config()
    existente = asistente.leer_config_existente(ruta)
    nuevo = {"postproxy": {"marcas": {marca: valores}}}
    fusionado = asistente.fusionar_config(existente, nuevo)
    asistente.escribir_config_atomico(ruta, fusionado)


async def postproxy_guardar(request: Request) -> Response:
    """PUT: guarda la api_key GLOBAL de Postproxy (JSON `{api_key}`). SOLO ADMIN.

    No la devuelve. Valida que no este vacia.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    datos = await leer_json(request)
    api_key = datos.get("api_key")
    if not isinstance(api_key, str) or not api_key.strip():
        return JSONResponse({"error": "Falta la API key de Postproxy."}, status_code=400)
    try:
        _escribir_postproxy_global(api_key.strip())
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar la API key de Postproxy."}, status_code=500
        )
    return JSONResponse({"configurado": True, "mensaje": "API key de Postproxy guardada."})


async def postproxy_borrar(request: Request) -> Response:
    """DELETE: borra la api_key GLOBAL de Postproxy. SOLO ADMIN.

    Solo borra la api_key (preserva los `profile_group_id` por marca).
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    ruta = ruta_config()
    try:
        cfg = asistente.leer_config_existente(ruta)
        pp = cfg.get("postproxy") if isinstance(cfg.get("postproxy"), dict) else None
        if isinstance(pp, dict) and "api_key" in pp:
            del pp["api_key"]
            asistente.escribir_config_atomico(ruta, cfg)
    except OSError:
        return JSONResponse(
            {"error": "No se pudo borrar la API key de Postproxy."}, status_code=500
        )
    return JSONResponse({"mensaje": "API key de Postproxy eliminada."})


# Puntos INYECTABLES: lo unico que toca la red. Los tests los parchean.
_PROBADOR_PP = _pp_cliente.probar
_PP_CREAR_GRUPO = _pp_cliente.crear_grupo
_PP_INICIAR_CONEXION = _pp_cliente.initialize_connection
_PP_DESCONECTAR = _pp_cliente.desconectar_perfil


async def postproxy_probar(request: Request) -> Response:
    """POST: prueba EN VIVO la api_key GUARDADA (GET /profile_groups). SOLO ADMIN.

    Usa la api_key ya guardada (nunca llega por el body ni sale por la respuesta). Si no
    hay api_key, responde `{ok:false}` con mensaje claro.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    api_key = _postproxy_api_key(_config_existente())
    if not api_key:
        return JSONResponse({"ok": False, "mensaje": "No hay API key de Postproxy configurada."})
    ok, mensaje = _PROBADOR_PP(api_key)
    return JSONResponse({"ok": ok, "mensaje": mensaje})


async def postproxy_grupo(request: Request) -> Response:
    """PUT: fija el grupo de perfiles de una marca. SOLO ADMIN.

    Body `{profile_group_id?}`. Si viene, se guarda tal cual. Si NO viene, se CREA un
    grupo en Postproxy (con la etiqueta de la marca) y se guarda su id. Devuelve
    `{profile_group_id, mensaje}`. La api_key nunca sale.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    datos = await leer_json(request)
    grupo = datos.get("profile_group_id")
    if isinstance(grupo, str) and grupo.strip():
        grupo = grupo.strip()
        mensaje = "Grupo de perfiles guardado."
    else:
        # No viene: hay que CREARLO en Postproxy. Requiere api_key.
        api_key = _postproxy_api_key(_config_existente())
        if not api_key:
            return JSONResponse(
                {"error": "Configura primero la API key de Postproxy."}, status_code=400
            )
        etiqueta = dict(_marcas_metricool()).get(marca, marca)
        ok, msg, datos_grupo = _PP_CREAR_GRUPO(api_key, etiqueta)
        if not ok or not datos_grupo:
            return JSONResponse({"error": msg}, status_code=502)
        grupo = str(datos_grupo["id"])
        mensaje = "Grupo de perfiles creado."
    try:
        _escribir_marca_postproxy(marca, {"profile_group_id": grupo})
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar el grupo de perfiles."}, status_code=500
        )
    return JSONResponse({"profile_group_id": grupo, "mensaje": mensaje})


async def postproxy_conectar(request: Request) -> Response:
    """POST: inicia la conexion OAuth de una red para una marca. SOLO ADMIN.

    Body `{platform, redirect_url}`. Valida la plataforma y que haya api_key. Si la marca
    no tiene grupo aun, lo CREA primero. Llama a initialize_connection y devuelve `{url}`.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    datos = await leer_json(request)
    platform = datos.get("platform")
    redirect_url = datos.get("redirect_url")
    if platform not in _pp_cliente.PLATAFORMAS:
        validas = ", ".join(_pp_cliente.PLATAFORMAS)
        return JSONResponse(
            {"error": f"Plataforma no válida. Válidas: {validas}."}, status_code=400
        )
    if not isinstance(redirect_url, str) or not redirect_url.strip():
        return JSONResponse({"error": "Falta la URL de redirección."}, status_code=400)
    api_key = _postproxy_api_key(_config_existente())
    if not api_key:
        return JSONResponse(
            {"error": "Configura primero la API key de Postproxy."}, status_code=400
        )
    grupo = _credencial(_marca_postproxy(_config_existente(), marca), "profile_group_id")
    if not grupo:
        # No hay grupo aun: crearlo primero (con la etiqueta de la marca) y persistirlo.
        etiqueta = dict(_marcas_metricool()).get(marca, marca)
        ok, msg, datos_grupo = _PP_CREAR_GRUPO(api_key, etiqueta)
        if not ok or not datos_grupo:
            return JSONResponse({"error": msg}, status_code=502)
        grupo = str(datos_grupo["id"])
        try:
            _escribir_marca_postproxy(marca, {"profile_group_id": grupo})
        except OSError:
            return JSONResponse(
                {"error": "No se pudo guardar el grupo de perfiles."}, status_code=500
            )
    ok, msg, url = _PP_INICIAR_CONEXION(api_key, grupo, platform, redirect_url.strip())
    if not ok or not url:
        return JSONResponse({"error": msg}, status_code=502)
    return JSONResponse({"url": url})


async def postproxy_desconectar_perfil(request: Request) -> Response:
    """DELETE: desconecta un perfil de Postproxy por su id. SOLO ADMIN."""
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    perfil_id = request.path_params["perfil_id"]
    api_key = _postproxy_api_key(_config_existente())
    if not api_key:
        return JSONResponse(
            {"error": "Configura primero la API key de Postproxy."}, status_code=400
        )
    ok, msg = _PP_DESCONECTAR(api_key, perfil_id)
    if not ok:
        return JSONResponse({"error": msg}, status_code=502)
    return JSONResponse({"mensaje": msg})


async def postproxy_canal(request: Request) -> Response:
    """PUT: fija el CANAL de publicación de una marca. SOLO ADMIN.

    Body `{canal}` con `canal` ∈ {metricool, postproxy}. Persiste en
    `[postproxy.marcas.<id>].canal` (sin tocar el grupo). El selector decide a qué
    adaptador entrega el programador esa marca; default histórico es `metricool`.
    Responde `{canal, mensaje}`. NO toca la red.
    """
    if not permisos.es_admin(request):
        return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)
    marca = request.path_params["marca"]
    if not _es_marca_metricool(marca):
        return JSONResponse({"error": "Marca desconocida."}, status_code=400)
    from keni_metricas.config import CANALES_PUBLICACION

    datos = await leer_json(request)
    canal = datos.get("canal")
    if not isinstance(canal, str) or canal.strip().lower() not in CANALES_PUBLICACION:
        validos = ", ".join(sorted(CANALES_PUBLICACION))
        return JSONResponse(
            {"error": f"Canal no válido. Válidos: {validos}."}, status_code=400
        )
    canal = canal.strip().lower()
    try:
        _escribir_marca_postproxy(marca, {"canal": canal})
    except OSError:
        return JSONResponse(
            {"error": "No se pudo guardar el canal de publicación."}, status_code=500
        )
    return JSONResponse({"canal": canal, "mensaje": "Canal de publicación guardado."})


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
    # Postproxy (canal alternativo): api_key global + grupo/conexion por marca.
    Route("/api/conexiones/postproxy", postproxy_estado, methods=["GET"]),
    Route("/api/conexiones/postproxy", postproxy_guardar, methods=["PUT"]),
    Route("/api/conexiones/postproxy", postproxy_borrar, methods=["DELETE"]),
    Route("/api/conexiones/postproxy/probar", postproxy_probar, methods=["POST"]),
    Route("/api/conexiones/postproxy/perfil/{perfil_id}", postproxy_desconectar_perfil, methods=["DELETE"]),
    Route("/api/conexiones/postproxy/{marca}/grupo", postproxy_grupo, methods=["PUT"]),
    Route("/api/conexiones/postproxy/{marca}/canal", postproxy_canal, methods=["PUT"]),
    Route("/api/conexiones/postproxy/{marca}/conectar", postproxy_conectar, methods=["POST"]),
]
