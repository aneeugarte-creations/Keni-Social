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

Implementacion DEFENSIVA: cualquier fallo de psutil/boto3/red se captura y se degrada a un
campo de error legible; la pagina nunca se cae por una sonda.
"""

from __future__ import annotations

import logging
import os
import shutil

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import config, permisos, rutas
from ..observabilidad import NOMBRE_LOGGER

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


RUTAS = [
    Route("/api/sistema/recursos", recursos, methods=["GET"]),
    Route("/api/sistema/s3", s3, methods=["GET"]),
    # IMPORTANTE: la ruta mas especifica (/s3/objetos) va ANTES que /s3/probar y /s3
    # para que Starlette la case correctamente.
    Route("/api/sistema/s3/objetos", s3_objetos, methods=["GET"]),
    Route("/api/sistema/s3/probar", probar_s3, methods=["POST"]),
]
