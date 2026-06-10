"""API Sistema: monitorizacion del servidor + estado de S3/Garage. SOLO rol admin.

Superficie de ADMIN de la Consola: da un vistazo operativo a la maquina que sirve la
consola (CPU/RAM/disco) y al object storage (S3/Garage) donde vive la media en hosted.
Es informacion SENSIBLE (capacidad, endpoints, uso) -> exige una SESION admin real, igual
que `/api/usuarios` y `/api/conexiones` (helper unico `permisos.es_admin`, #150/#153). El
token de mantenimiento NO es admin: recibe 403.

Endpoints (bajo `/api/sistema`, CONTRATO con el frontend):

  - GET /api/sistema/recursos -> {cpu:{porcentaje,cores}, ram:{usado,total,porcentaje},
      discos:[{etiqueta, ruta, usado, total, porcentaje}], psutil: bool}. Bytes en crudo;
      el front formatea GB/%. Degradado: si `psutil` no esta, devuelve CPU/RAM nulos pero
      SI el disco (via `shutil.disk_usage`, stdlib) -> nunca 500 por falta de un opcional.
  - GET /api/sistema/s3 -> {configurado, endpoint, bucket, region, salud, objetos, bytes,
      error?}. Con S3 cableado consulta el bucket (head_bucket + conteo/suma de objetos);
      sin cablear devuelve `configurado:false` (degradado, NO 500). `salud` es "ok"/"err".
  - POST /api/sistema/s3/probar -> {salud, error?}. Test de conexion (head_bucket). SOLO
      lectura: NADA destructivo. 409 si S3 no esta configurado (no hay nada que probar).
  - GET /api/sistema/s3/objetos?prefijo=<p> -> {carpetas, objetos, prefijo, migas}.
      Navega el bucket por prefijo usando Delimiter="/": devuelve subcarpetas (CommonPrefixes)
      y objetos del nivel actual ({key, nombre, tamano, modificado}). Tope anti-escaneo de
      1000 objetos por pagina, maximo _MAX_PAGINAS_NAV paginas. Sin S3: degradado, no 500.
      SOLO lectura: NADA destructivo.
  - GET /api/sistema/s3/objeto?key=<k>[&descargar=1] -> STREAMING de los bytes del objeto.
      El endpoint S3 de Garage es INTERNO (`http://files:3900`): el navegador no lo alcanza,
      asi que NO se usan URLs prefirmadas; se proxean los bytes por el back con el Content-Type
      real del objeto. Por defecto `inline` (previsualizacion: sirve para `<img src=...>` con la
      cookie de sesion); `?descargar=1` fuerza `attachment`. Valida la key (sin `..`). Cap de
      tamano (_MAX_BYTES_OBJETO). 404 si no existe, 409 si S3 no configurado. SOLO lectura.
  - POST /api/sistema/s3/borrar {key} -> {borrado, key}. Operacion DESTRUCTIVA: borra UN
      objeto por su key exacta (la que lista el explorador). Valida la key (anti-traversal,
      sin `..`) y rechaza keys de "carpeta" (terminadas en "/"). Confirma existencia con
      head_object para dar un 404 honesto antes de borrar (delete_object de S3 es idempotente
      y no distingue). 400 key invalida, 404 inexistente, 409 sin configurar, 502 fallo.
  - POST /api/sistema/s3/borrar-lote {keys:[...]} -> {borrados:[...], fallidos:[{key,error}]}.
      Operacion DESTRUCTIVA en MASA (seleccion multiple del explorador). Valida y deduplica las
      keys, descarta invalidas/"carpetas", y usa delete_objects (batch nativo, hasta 1000 por
      llamada). NO hace head_object por key (prioriza rapidez): no distingue ausentes. 400 sin
      keys validas, 409 sin configurar, 502 fallo. El RESTO del panel sigue siendo solo lectura.

Implementacion DEFENSIVA: cualquier fallo de psutil/boto3/red se captura y se degrada a un
campo de error legible; la pagina nunca se cae por una sonda.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import UTC, datetime

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

from .. import config, db, media, permisos, rutas
from ..observabilidad import NOMBRE_LOGGER
from ..tiempo import ahora_iso

_logger = logging.getLogger(NOMBRE_LOGGER)

_MSG_SOLO_ADMIN = "Solo un administrador puede ver el estado del sistema."

# Tope de objetos a recorrer al medir el uso del bucket: protege de un bucket gigantesco
# (cada pagina son hasta 1000 keys). 100k objetos son 100 llamadas; suficiente para la
# media de la consola sin convertir el panel en un escaneo eterno. Si se supera, marcamos
# `truncado` para que el front avise de que el conteo es un minimo.
_MAX_OBJETOS = 100_000

# Tope de paginas al navegar un prefijo (explorador de carpetas): 5 paginas = 5000 objetos
# por nivel. Mas que suficiente para la media de la consola; evita escaneos infinitos.
_MAX_PAGINAS_NAV = 5

# Tope de tamano al servir/descargar un objeto por el back (proxy de bytes): 100 MiB. La
# media de la consola son imagenes/clips ligeros; mas que de sobra. Protege la RAM del back
# de descargar un objeto gigante de golpe. Si se supera, 413 (objeto demasiado grande).
_MAX_BYTES_OBJETO = 100 * 1024 * 1024

# Tamano de chunk al streamear los bytes del objeto al cliente (256 KiB).
_CHUNK_STREAM = 256 * 1024

# Tope de keys por borrado en masa. delete_objects de S3 admite 1000 por llamada; lo dejamos
# en 1000 para resolver el lote en UNA sola peticion al almacenamiento.
_MAX_BORRADO_LOTE = 1000


def _es_admin(request: Request) -> bool:
    """True SOLO si la peticion la hace una SESION admin real (token NO cuenta, #150)."""
    return permisos.es_admin(request)


def _rechazo_no_admin() -> Response:
    return permisos.rechazo_solo_admin(_MSG_SOLO_ADMIN)


# --------------------------------------------------------------------------- #
# Recursos de la maquina (CPU / RAM / disco)                                   #
# --------------------------------------------------------------------------- #


def _uso_disco(ruta: str, etiqueta: str) -> dict | None:
    """Uso de disco del volumen que contiene `ruta` (None si no se puede medir).

    `shutil.disk_usage` es stdlib (no depende de psutil): siempre disponible. Si la ruta
    no existe (p.ej. no hay volumen `/data` en local), devuelve None para omitir el disco.
    """
    try:
        uso = shutil.disk_usage(ruta)
    except OSError:
        return None
    porcentaje = (uso.used / uso.total * 100) if uso.total else 0.0
    return {
        "etiqueta": etiqueta,
        "ruta": ruta,
        "usado": int(uso.used),
        "total": int(uso.total),
        "porcentaje": round(porcentaje, 1),
    }


def _discos() -> list[dict]:
    """Discos relevantes: el volumen de estado (`/data` hosted) y el root.

    El de estado se mide sobre `rutas.data_dir()` (con `KENI_DATA_DIR` apunta al volumen
    `/data`; en local cae a `~/.config`). Evitamos duplicar si root y estado son el mismo
    volumen (misma ruta resuelta).
    """
    discos: list[dict] = []
    rutas_vistas: set[str] = set()
    raiz_estado = str(rutas.data_dir())
    if (d := _uso_disco(raiz_estado, "Estado")) is not None:
        discos.append(d)
        rutas_vistas.add(d["ruta"])
    # El root solo se anade si NO es ya el mismo punto de montaje que el estado. Comparamos
    # por (total, usado) ademas de por ruta: dos rutas distintas del mismo volumen dan el
    # mismo uso, y no queremos pintar el mismo disco dos veces.
    root = _uso_disco("/", "Sistema")
    if root is not None and not any(
        d["total"] == root["total"] and d["usado"] == root["usado"] for d in discos
    ):
        discos.append(root)
    return discos


async def recursos(request: Request) -> Response:
    """GET /api/sistema/recursos: CPU/RAM/disco de la maquina (admin).

    Degradado: psutil es opcional; si falta, CPU/RAM van a None pero el disco SIEMPRE sale
    (stdlib). Nunca un 500 por un opcional ausente.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    cpu: dict = {"porcentaje": None, "cores": None}
    ram: dict = {"usado": None, "total": None, "porcentaje": None}
    psutil_ok = False
    try:
        import psutil

        psutil_ok = True
        # interval=None: lectura NO bloqueante (delta desde la llamada previa del proceso).
        # En el primer muestreo puede dar 0.0; el auto-refresco del front lo corrige enseguida.
        cpu = {
            "porcentaje": round(float(psutil.cpu_percent(interval=None)), 1),
            "cores": psutil.cpu_count(logical=True),
        }
        vm = psutil.virtual_memory()
        ram = {
            "usado": int(vm.used),
            "total": int(vm.total),
            "porcentaje": round(float(vm.percent), 1),
        }
    except Exception:  # noqa: BLE001 -- psutil ausente o sonda fallida: degradar, no 500
        _logger.warning("psutil no disponible o fallo al leer CPU/RAM; se degrada.")

    return JSONResponse(
        {
            "cpu": cpu,
            "ram": ram,
            "discos": _discos(),
            "psutil": psutil_ok,
        }
    )


# --------------------------------------------------------------------------- #
# S3 / Garage (estado + uso del bucket)                                        #
# --------------------------------------------------------------------------- #


def _s3_no_configurado() -> dict:
    """Payload degradado cuando NO hay object storage cableado (media en disco local)."""
    return {
        "configurado": False,
        "endpoint": None,
        "bucket": None,
        "region": None,
        "salud": None,
        "objetos": None,
        "bytes": None,
        "truncado": False,
        "error": None,
    }


def _cliente_s3():  # noqa: ANN202 -- tipo boto3 (sin anotar para no importar al cargar)
    """Cliente S3 (boto3) configurado contra `S3_*`. Import DIFERIDO (extra `s3`)."""
    import boto3
    from botocore.config import Config as BotoConfig

    return boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint(),
        region_name=config.s3_region(),
        aws_access_key_id=config.s3_access_key(),
        aws_secret_access_key=config.s3_secret_key(),
        # Path-style: Garage no sirve virtual-host style por subdominio de bucket.
        config=BotoConfig(s3={"addressing_style": "path"}),
    )


def _medir_bucket(cliente, bucket: str) -> tuple[int, int, bool]:
    """Recorre el bucket y devuelve `(num_objetos, bytes_totales, truncado)`.

    Pagina `list_objects_v2` sumando `Size`. Corta en `_MAX_OBJETOS` para no escanear sin
    fin (marca `truncado=True`): el conteo pasa a ser un MINIMO, no el total exacto.
    """
    objetos = 0
    total_bytes = 0
    truncado = False
    token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket}
        if token:
            kwargs["ContinuationToken"] = token
        resp = cliente.list_objects_v2(**kwargs)
        for item in resp.get("Contents", []) or []:
            objetos += 1
            total_bytes += int(item.get("Size", 0) or 0)
        if objetos >= _MAX_OBJETOS:
            truncado = True
            break
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return objetos, total_bytes, truncado


async def s3(request: Request) -> Response:
    """GET /api/sistema/s3: estado y uso del object storage (admin).

    Sin S3 cableado: degradado (`configurado:false`), no 500. Con S3: head_bucket para la
    salud y conteo/suma de objetos para el uso. Cualquier fallo de red/credencial se reporta
    en `error` con `salud:"err"` (la pagina sigue viva).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    if not config.s3_configurado():
        return JSONResponse(_s3_no_configurado())

    bucket = config.s3_bucket()
    payload: dict = {
        "configurado": True,
        "endpoint": config.s3_endpoint(),
        "bucket": bucket,
        "region": config.s3_region(),
        "salud": "err",
        "objetos": None,
        "bytes": None,
        "truncado": False,
        "error": None,
    }
    try:
        cliente = _cliente_s3()
        cliente.head_bucket(Bucket=bucket)
        payload["salud"] = "ok"
        objetos, total_bytes, truncado = _medir_bucket(cliente, bucket)
        payload["objetos"] = objetos
        payload["bytes"] = total_bytes
        payload["truncado"] = truncado
    except Exception as e:  # noqa: BLE001 -- boto3/red: degradar a salud err + mensaje
        _logger.warning("No se pudo consultar S3/Garage: %s", e)
        payload["error"] = "No se pudo consultar el almacenamiento. Revisa el endpoint y las credenciales."
    return JSONResponse(payload)


async def probar_s3(request: Request) -> Response:
    """POST /api/sistema/s3/probar: test de conexion (head_bucket). SOLO lectura (admin).

    409 si S3 no esta configurado (no hay nada que probar). Devuelve `salud` ok/err.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    if not config.s3_configurado():
        return JSONResponse(
            {"error": "El almacenamiento S3 no está configurado en este servidor."},
            status_code=409,
        )
    try:
        cliente = _cliente_s3()
        cliente.head_bucket(Bucket=config.s3_bucket())
    except Exception as e:  # noqa: BLE001 -- fallo de conexion: salud err, sin traceback
        _logger.warning("Prueba de conexion S3/Garage fallida: %s", e)
        return JSONResponse(
            {"salud": "err", "error": "No se pudo conectar con el almacenamiento."}
        )
    return JSONResponse({"salud": "ok", "error": None})


# --------------------------------------------------------------------------- #
# S3 / Garage (navegador de carpetas/objetos)                                  #
# --------------------------------------------------------------------------- #


def _migas(prefijo: str) -> list[dict]:
    """Genera las migas de pan para el breadcrumb dado un prefijo como 'a/b/c/'.

    Devuelve [{nombre, prefijo}] incluyendo la raiz (prefijo vacio). Cada elemento lleva
    el prefijo acumulado hasta ese nivel para poder navegar directo a cualquier ancestro.
    """
    migas: list[dict] = [{"nombre": "Raiz", "prefijo": ""}]
    if not prefijo:
        return migas
    # El prefijo termina en "/": dividimos y acumulamos.
    partes = prefijo.rstrip("/").split("/")
    acumulado = ""
    for parte in partes:
        acumulado = f"{acumulado}{parte}/"
        migas.append({"nombre": parte, "prefijo": acumulado})
    return migas


async def s3_objetos(request: Request) -> Response:
    """GET /api/sistema/s3/objetos?prefijo=<p>: navega el bucket por prefijo. Admin.

    Usa `list_objects_v2` con `Delimiter="/"` para distinguir "carpetas" (CommonPrefixes)
    de objetos del nivel actual. Devuelve:
      - carpetas: lista de prefijos de subcarpetas bajo el prefijo actual.
      - objetos:  lista {key, nombre (basename), tamano, modificado} del nivel.
      - prefijo:  el prefijo activo (normalizado).
      - migas:    breadcrumb [{nombre, prefijo}] desde la raiz hasta el nivel actual.

    Tope anti-escaneo: _MAX_PAGINAS_NAV paginas (hasta 5000 objetos por nivel). Si S3 no
    esta configurado devuelve payload degradado (no 500). SOLO lectura: nada destructivo.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    if not config.s3_configurado():
        return JSONResponse(
            {
                "configurado": False,
                "carpetas": [],
                "objetos": [],
                "prefijo": "",
                "migas": [{"nombre": "Raiz", "prefijo": ""}],
                "error": "S3 no está configurado en este servidor.",
            }
        )

    # Normalizar prefijo: sin barra al inicio, con barra al final (salvo raiz).
    prefijo_raw = request.query_params.get("prefijo", "")
    prefijo = prefijo_raw.lstrip("/")
    if prefijo and not prefijo.endswith("/"):
        prefijo = f"{prefijo}/"

    bucket = config.s3_bucket()
    carpetas: list[str] = []
    objetos_lista: list[dict] = []
    error: str | None = None

    try:
        cliente = _cliente_s3()
        token: str | None = None
        paginas = 0
        while paginas < _MAX_PAGINAS_NAV:
            paginas += 1
            kwargs: dict = {
                "Bucket": bucket,
                "Delimiter": "/",
                "Prefix": prefijo,
            }
            if token:
                kwargs["ContinuationToken"] = token
            resp = cliente.list_objects_v2(**kwargs)

            # Subcarpetas (CommonPrefixes): S3 agrupa las keys con "/" como separador.
            for cp in resp.get("CommonPrefixes", []) or []:
                p = cp.get("Prefix", "")
                if p:
                    carpetas.append(p)

            # Objetos del nivel actual (excluimos el "directorio virtual" propio).
            for item in resp.get("Contents", []) or []:
                key = item.get("Key", "")
                if key == prefijo:
                    # Es el "folder marker" (clave identica al prefijo): omitir.
                    continue
                nombre = os.path.basename(key.rstrip("/")) or key
                tamano = int(item.get("Size", 0) or 0)
                modificado_raw = item.get("LastModified")
                modificado = (
                    modificado_raw.isoformat() if modificado_raw is not None else None
                )
                objetos_lista.append(
                    {
                        "key": key,
                        "nombre": nombre,
                        "tamano": tamano,
                        "modificado": modificado,
                    }
                )

            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
            if not token:
                break
    except Exception as e:  # noqa: BLE001 -- boto3/red: degradar, no 500
        _logger.warning("Error al navegar S3/Garage (prefijo=%r): %s", prefijo, e)
        error = "No se pudo listar el almacenamiento. Revisa el endpoint y las credenciales."

    return JSONResponse(
        {
            "configurado": True,
            "carpetas": carpetas,
            "objetos": objetos_lista,
            "prefijo": prefijo,
            "migas": _migas(prefijo),
            "error": error,
        }
    )


def _key_valida(key: str) -> bool:
    """True si `key` es una key de objeto SEGURA para servir (anti-traversal).

    Rechaza keys vacias, absolutas (empiezan por "/") o con un segmento "..": aunque S3 no
    es un FS, blindamos contra cualquier intento de escapar del bucket o de jugar con rutas.
    """
    if not key or key.startswith("/"):
        return False
    return ".." not in key.split("/")


def _es_objeto_inexistente(e: Exception) -> bool:
    """True si la excepcion de boto3 indica que el objeto NO existe (404 / NoSuchKey).

    boto3 levanta `ClientError` con `e.response = {"Error": {"Code": ...}, "ResponseMetadata":
    {"HTTPStatusCode": ...}}`. Miramos ambos por robustez (Garage y AWS pueden diferir en el
    Code). Si no hay `response`, es un fallo de red/credencial -> NO es un 404.
    """
    resp = getattr(e, "response", None)
    if not isinstance(resp, dict):
        return False
    codigo = str(resp.get("Error", {}).get("Code", "")).lower()
    estado = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return codigo in ("nosuchkey", "404", "notfound") or estado == 404


async def s3_objeto(request: Request) -> Response:
    """GET /api/sistema/s3/objeto?key=<k>[&descargar=1]: streamea un objeto del bucket. Admin.

    El endpoint de Garage es INTERNO: el navegador no lo alcanza, asi que NO firmamos URLs;
    proxeamos los bytes por el back. `get_object` da el cuerpo (stream) y el `ContentType`
    real, que reflejamos al cliente. `inline` por defecto (sirve para `<img src=...>` con la
    cookie de sesion); `?descargar=1` -> `attachment`. SOLO lectura: nada destructivo.

    Codigos: 400 key invalida, 409 S3 no configurado, 404 objeto inexistente, 413 demasiado
    grande, 502 fallo de almacenamiento. Anti-traversal en la key (sin `..`).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    if not config.s3_configurado():
        return JSONResponse(
            {"error": "El almacenamiento S3 no está configurado en este servidor."},
            status_code=409,
        )

    key = request.query_params.get("key", "")
    if not _key_valida(key):
        return JSONResponse({"error": "Clave de objeto no válida."}, status_code=400)

    descargar = request.query_params.get("descargar") in ("1", "true", "si", "sí")

    try:
        cliente = _cliente_s3()
        obj = cliente.get_object(Bucket=config.s3_bucket(), Key=key)
    except Exception as e:  # noqa: BLE001 -- boto3 lanza ClientError(NoSuchKey/404) o red
        # Distinguimos "no existe" (404) del resto (problema de almacenamiento, 502). boto3
        # cuelga el detalle en `e.response` (dict) cuando es un ClientError; si no, es red.
        if _es_objeto_inexistente(e):
            return JSONResponse({"error": "Ese objeto no existe."}, status_code=404)
        _logger.warning("No se pudo leer el objeto S3 %r: %s", key, e)
        return JSONResponse(
            {"error": "No se pudo leer el objeto del almacenamiento."}, status_code=502
        )

    # Cap de tamano: protege la RAM del back. `ContentLength` viene en la respuesta de S3.
    tamano = int(obj.get("ContentLength", 0) or 0)
    if tamano > _MAX_BYTES_OBJETO:
        return JSONResponse(
            {"error": "El objeto es demasiado grande para previsualizarlo aquí."},
            status_code=413,
        )

    # Content-Type real del objeto; si S3 no lo trae, lo inferimos de la extension de la key.
    tipo = obj.get("ContentType") or media.mime_de(key)

    nombre_archivo = os.path.basename(key.rstrip("/")) or "objeto"
    disposicion = "attachment" if descargar else "inline"
    headers = {
        "Content-Disposition": f'{disposicion}; filename="{nombre_archivo}"',
        # Cache breve en el navegador: thumbnails repetidos no re-piden al back cada scroll.
        "Cache-Control": "private, max-age=300",
    }
    if tamano:
        headers["Content-Length"] = str(tamano)

    cuerpo = obj["Body"]  # StreamingBody de botocore (file-like, .read(n))

    def _iter():
        try:
            while True:
                trozo = cuerpo.read(_CHUNK_STREAM)
                if not trozo:
                    break
                yield trozo
        finally:
            try:
                cuerpo.close()
            except Exception:  # noqa: BLE001 -- cierre best-effort
                pass

    return StreamingResponse(_iter(), media_type=tipo, headers=headers)


async def s3_borrar(request: Request) -> Response:
    """POST /api/sistema/s3/borrar {key}: borra UN objeto del bucket. Admin.

    Unica operacion DESTRUCTIVA del panel (el resto es solo lectura). Borra por key EXACTA
    el objeto que lista el explorador. Valida la key (anti-traversal, sin `..`) y rechaza
    keys de "carpeta" (terminadas en "/"): aqui solo se borran objetos, no prefijos. Confirma
    existencia con head_object para dar un 404 honesto (delete_object de S3 es idempotente y
    no distingue si existia). Codigos: 400 key invalida, 404 inexistente, 409 S3 no
    configurado, 502 fallo de almacenamiento.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    if not config.s3_configurado():
        return JSONResponse(
            {"error": "El almacenamiento S3 no está configurado en este servidor."},
            status_code=409,
        )

    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- cuerpo ausente o no-JSON: key vacia -> 400
        cuerpo = {}
    key = str(cuerpo.get("key", "")).strip() if isinstance(cuerpo, dict) else ""

    if not _key_valida(key) or key.endswith("/"):
        return JSONResponse({"error": "Clave de objeto no válida."}, status_code=400)

    bucket = config.s3_bucket()
    try:
        cliente = _cliente_s3()
        # Confirmar que existe ANTES de borrar: delete_object es idempotente (no falla si la
        # key no estaba), pero queremos un 404 honesto y no decir "borrado" de algo ausente.
        try:
            cliente.head_object(Bucket=bucket, Key=key)
        except Exception as e:  # noqa: BLE001 -- 404 -> inexistente; otro -> error real (raise)
            if _es_objeto_inexistente(e):
                return JSONResponse({"error": "Ese objeto no existe."}, status_code=404)
            raise
        cliente.delete_object(Bucket=bucket, Key=key)
    except Exception as e:  # noqa: BLE001 -- boto3/red: 502, sin tumbar la pagina
        _logger.warning("No se pudo borrar el objeto S3 %r: %s", key, e)
        return JSONResponse(
            {"error": "No se pudo borrar el objeto del almacenamiento."}, status_code=502
        )

    _logger.info("Objeto S3 borrado por un administrador: %r", key)
    return JSONResponse({"borrado": True, "key": key})


async def s3_borrar_lote(request: Request) -> Response:
    """POST /api/sistema/s3/borrar-lote {keys:[...]}: borra VARIOS objetos del bucket. Admin.

    Borrado en MASA del explorador (seleccion multiple / seleccionar todo). Valida cada key
    (anti-traversal, sin `..`, sin "carpetas" terminadas en "/") y descarta las invalidas. Usa
    `delete_objects` (batch nativo de S3, hasta 1000 keys por llamada): idempotente, no falla
    por keys ausentes. NO hace head_object por cada una (seria O(n) llamadas): el borrado en
    masa prioriza rapidez sobre el 404 honesto del borrado individual.

    Devuelve {borrados:[keys], fallidos:[{key, error}]}. Codigos: 400 sin keys validas, 409 S3
    no configurado, 502 fallo de almacenamiento. Tope de `_MAX_BORRADO_LOTE` keys por peticion.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()

    if not config.s3_configurado():
        return JSONResponse(
            {"error": "El almacenamiento S3 no está configurado en este servidor."},
            status_code=409,
        )

    try:
        cuerpo = await request.json()
    except Exception:  # noqa: BLE001 -- cuerpo ausente o no-JSON: sin keys -> 400
        cuerpo = {}
    keys_raw = cuerpo.get("keys") if isinstance(cuerpo, dict) else None
    if not isinstance(keys_raw, list):
        return JSONResponse({"error": "Se esperaba una lista de keys."}, status_code=400)

    # Normaliza + deduplica + filtra invalidas/carpetas, conservando el orden de llegada.
    vistas: set[str] = set()
    keys: list[str] = []
    for k in keys_raw:
        ck = str(k).strip()
        if ck in vistas or not _key_valida(ck) or ck.endswith("/"):
            continue
        vistas.add(ck)
        keys.append(ck)

    if not keys:
        return JSONResponse({"error": "Ninguna key válida para borrar."}, status_code=400)
    if len(keys) > _MAX_BORRADO_LOTE:
        return JSONResponse(
            {"error": f"Demasiados objetos: máximo {_MAX_BORRADO_LOTE} por borrado en masa."},
            status_code=400,
        )

    bucket = config.s3_bucket()
    borrados: list[str] = []
    fallidos: list[dict] = []
    try:
        cliente = _cliente_s3()
        # delete_objects acepta hasta 1000 keys; _MAX_BORRADO_LOTE garantiza una sola llamada.
        resp = cliente.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in keys], "Quiet": False},
        )
    except Exception as e:  # noqa: BLE001 -- boto3/red: 502, sin tumbar la pagina
        _logger.warning("No se pudo borrar en lote de S3 (%d keys): %s", len(keys), e)
        return JSONResponse(
            {"error": "No se pudo borrar los objetos del almacenamiento."}, status_code=502
        )

    # S3 devuelve Deleted (ok) y Errors (por key). Pedimos Quiet:False; lo que no salga en
    # Errors lo damos por borrado (delete_objects es idempotente con keys ausentes).
    con_error = {str(err.get("Key", "")) for err in (resp.get("Errors") or [])}
    for err in resp.get("Errors") or []:
        fallidos.append(
            {"key": str(err.get("Key", "")), "error": str(err.get("Message", "error"))}
        )
    borrados = [k for k in keys if k not in con_error]

    _logger.info(
        "Borrado en masa S3 por un administrador: %d borrados, %d fallidos.",
        len(borrados),
        len(fallidos),
    )
    return JSONResponse({"borrados": borrados, "fallidos": fallidos})


# --------------------------------------------------------------------------- #
# Daemons de fondo (latidos persistidos por `latidos.py`)                       #
# --------------------------------------------------------------------------- #

# Umbral de ATRASO de un daemon: su bucle late cada `tick_seg` (gateados: <=60s; bucles
# fijos: su intervalo). Si `visto` es mas viejo que 2 ticks + margen, el hilo esta muerto
# o el proceso daemons caido => "atrasado". El suelo evita falsos positivos con ticks
# muy cortos (jitter de BD/arranque).
_MARGEN_ATRASO_SEG = 90.0
_UMBRAL_ATRASO_MIN_SEG = 120.0


def _edad_segundos(iso: str, ahora: datetime) -> float | None:
    """Edad en segundos de un timestamp canon (naive-UTC) frente a `ahora`; None si vacio."""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return max(0.0, (ahora - dt).total_seconds())


async def daemons_latidos(request: Request) -> Response:
    """Estado de los daemons de fondo a partir de sus latidos persistidos (solo admin).

    Devuelve `{daemons: [...], error}` donde cada entrada agrega al registro crudo de
    `daemon_latidos` la `edad_seg` del ultimo latido, el `umbral_atraso_seg` aplicado y
    un `estado` listo para pintar: "ok" (late y su ultimo barrido fue bien), "error"
    (late pero su ultimo barrido fallo), "inactivo" (late con el gate OFF) o "atrasado"
    (no late: hilo muerto, proceso daemons caido o BD inaccesible para el). Defensivo:
    un fallo de BD degrada a lista vacia con `error` legible, nunca 500.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    try:
        filas = db.listar_latidos()
    except Exception as e:  # noqa: BLE001 -- sonda defensiva: el panel nunca se cae
        _logger.warning("No se pudieron leer los latidos de daemons: %s", e)
        return JSONResponse(
            {"daemons": [], "error": "No se pudieron leer los latidos de los daemons."}
        )
    ahora = datetime.fromisoformat(ahora_iso())
    salida = []
    for f in filas:
        edad = _edad_segundos(f["visto"], ahora)
        umbral = max(2.0 * f["tick_seg"], _UMBRAL_ATRASO_MIN_SEG) + _MARGEN_ATRASO_SEG
        if edad is None or edad > umbral:
            estado = "atrasado"
        elif not f["activo"]:
            estado = "inactivo"
        elif f["ultimo_error"] and f["ultimo_error"] >= (f["ultimo_ok"] or ""):
            # Canon ISO naive-UTC: comparar como texto respeta el orden temporal.
            estado = "error"
        else:
            estado = "ok"
        salida.append(
            {**f, "edad_seg": edad, "umbral_atraso_seg": umbral, "estado": estado}
        )
    return JSONResponse({"daemons": salida, "error": None})


# --------------------------------------------------------------------------- #
# Backups locales (estado.json del keni-backup del host, montado :ro)          #
# --------------------------------------------------------------------------- #

# Umbral de atraso del backup: timer diario + margen (mismo criterio que keni-alertas).
_BACKUP_ATRASO_SEG = 26 * 3600.0

# Env con el directorio de backups montado SOLO LECTURA en el contenedor (compose:
# /var/backups/keni-social -> /backups). Vacio/ausente => seccion degradada, nunca 500.
_ENV_BACKUPS_DIR = "KENI_BACKUPS_DIR"


async def backups(request: Request) -> Response:
    """Estado de los backups locales del host (solo admin; observabilidad pura).

    Lee el `estado.json` que escribe `deploy/backup/keni-backup.sh` en cada run (ok/fallo,
    verificacion, bytes, duracion) y sondea el dump mas reciente de `postgres/` para
    calcular la edad real (robusto aunque estado.json falte o sea de un run fallido).
    `atrasado` = ningun dump en las ultimas 26h (timer diario + margen, igual que
    keni-alertas). Degradado sin el mount/env (`configurado: false`), nunca 500.
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    raiz = os.environ.get(_ENV_BACKUPS_DIR, "")
    base = {
        "configurado": False,
        "estado": None,
        "dumps": 0,
        "ultimo_dump": None,
        "atrasado": False,
        "error": None,
    }
    if not raiz or not os.path.isdir(raiz):
        return JSONResponse(base)
    base["configurado"] = True

    import json as _json

    try:
        with open(os.path.join(raiz, "estado.json"), encoding="utf-8") as f:
            base["estado"] = _json.load(f)
    except FileNotFoundError:
        pass  # primer run aun sin estado.json: los dumps de abajo siguen contando
    except Exception as e:  # noqa: BLE001 -- JSON roto/permisos: degradar legible
        base["error"] = f"estado.json ilegible: {e}"

    try:
        dir_pg = os.path.join(raiz, "postgres")
        dumps = [
            e
            for e in os.scandir(dir_pg)
            if e.is_file() and e.name.startswith("keni-") and e.name.endswith(".dump")
        ]
        base["dumps"] = len(dumps)
        if dumps:
            ultimo = max(dumps, key=lambda e: e.stat().st_mtime)
            st = ultimo.stat()
            edad = max(0.0, datetime.now(UTC).timestamp() - st.st_mtime)
            base["ultimo_dump"] = {
                "fichero": ultimo.name,
                "bytes": st.st_size,
                "modificado": datetime.fromtimestamp(st.st_mtime, UTC)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds"),
                "edad_seg": edad,
            }
            base["atrasado"] = edad > _BACKUP_ATRASO_SEG
        else:
            base["atrasado"] = True
    except FileNotFoundError:
        base["atrasado"] = True
    except Exception as e:  # noqa: BLE001 -- sonda defensiva: el panel nunca se cae
        base["error"] = base["error"] or f"no se pudo listar postgres/: {e}"
    return JSONResponse(base)


RUTAS = [
    Route("/api/sistema/recursos", recursos, methods=["GET"]),
    Route("/api/sistema/daemons", daemons_latidos, methods=["GET"]),
    Route("/api/sistema/backups", backups, methods=["GET"]),
    Route("/api/sistema/s3", s3, methods=["GET"]),
    # IMPORTANTE: las rutas mas especificas (/s3/objetos, /s3/objeto, /s3/borrar) van ANTES
    # que /s3/probar y /s3 para que Starlette las case correctamente.
    Route("/api/sistema/s3/objetos", s3_objetos, methods=["GET"]),
    Route("/api/sistema/s3/objeto", s3_objeto, methods=["GET"]),
    Route("/api/sistema/s3/borrar-lote", s3_borrar_lote, methods=["POST"]),
    Route("/api/sistema/s3/borrar", s3_borrar, methods=["POST"]),
    Route("/api/sistema/s3/probar", probar_s3, methods=["POST"]),
]
