"""S3 / Garage del panel de ADMIN: estado + uso del bucket, navegador y borrado de objetos.

Endpoints (bajo `/api/sistema`, CONTRATO con el frontend):

  - GET  /api/sistema/s3            -> estado y uso del object storage.
  - POST /api/sistema/s3/probar     -> test de conexion (head_bucket). SOLO lectura.
  - GET  /api/sistema/s3/objetos    -> navega el bucket por prefijo (carpetas/objetos).
  - GET  /api/sistema/s3/objeto     -> STREAMING de los bytes del objeto (proxy por el back).
  - POST /api/sistema/s3/borrar     -> borra UN objeto por key exacta (DESTRUCTIVO).
  - POST /api/sistema/s3/borrar-lote-> borra VARIOS objetos (DESTRUCTIVO en masa).

Implementacion DEFENSIVA: cualquier fallo de boto3/red se captura y se degrada a un campo
de error legible; la pagina nunca se cae por una sonda.
"""

from __future__ import annotations

import os

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ... import config, media
from ._comun import _es_admin, _logger, _rechazo_no_admin

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


def sonda_s3_salud() -> dict:
    """SONDA de salud del object storage (head_bucket, SOLO lectura, sin medir uso).

    Devuelve `{configurado, salud, error}`: sin S3 cableado `{False, None, None}`; con S3,
    `salud` es "ok"/"err" y `error` un mensaje legible solo en fallo. La comparten el test
    de conexion (`POST /api/sistema/s3/probar`) y el doctor (`/api/estado`, chequeo
    `infra:s3`): una sola sonda, dos consumidores. Defensiva: nunca propaga.
    """
    if not config.s3_configurado():
        return {"configurado": False, "salud": None, "error": None}
    try:
        cliente = _cliente_s3()
        cliente.head_bucket(Bucket=config.s3_bucket())
    except Exception as e:  # noqa: BLE001 -- fallo de conexion: salud err, sin traceback
        _logger.warning("Prueba de conexion S3/Garage fallida: %s", e)
        return {
            "configurado": True,
            "salud": "err",
            "error": "No se pudo conectar con el almacenamiento.",
        }
    return {"configurado": True, "salud": "ok", "error": None}


async def probar_s3(request: Request) -> Response:
    """POST /api/sistema/s3/probar: test de conexion (head_bucket). SOLO lectura (admin).

    409 si S3 no esta configurado (no hay nada que probar). Devuelve `salud` ok/err
    (la misma `sonda_s3_salud` que usa el doctor).
    """
    if not _es_admin(request):
        return _rechazo_no_admin()
    if not config.s3_configurado():
        return JSONResponse(
            {"error": "El almacenamiento S3 no está configurado en este servidor."},
            status_code=409,
        )
    sonda = sonda_s3_salud()
    return JSONResponse({"salud": sonda["salud"], "error": sonda["error"]})


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
