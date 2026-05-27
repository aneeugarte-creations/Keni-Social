"""Almacen de OBJETOS de media: disco (local) o S3/Garage (hosted), un solo codigo.

`media.py` valida/genera la imagen y SIEMPRE inventa el NOMBRE del objeto (uuid+ext); este
modulo solo decide DONDE vive ese objeto, segun la config S3 (ver `config.s3_configurado`):

  - SIN S3 cableado  -> disco local bajo `dir_media()` (perfil privado/local de ADR
    0001/0002). Comportamiento HISTORICO intacto: nada sale de la maquina.
  - CON S3 cableado  -> bucket S3/Garage (`S3_ENDPOINT`/`S3_BUCKET`/credenciales). El stack
    `deploy/` lo cablea; el cutover de objetos lo hace `migracion.py` (one-shot).

SEGURIDAD: el nombre del objeto lo genera SIEMPRE el llamante (`media.py`: uuid + ext
saneada), NUNCA el cliente. En disco, `resolver_media` valida ANTI-TRAVERSAL que el nombre
caiga dentro del dir. En S3 el nombre es la KEY del objeto: rechazamos cualquier nombre con
`/`, `..` o separadores (defensa en profundidad, aunque siempre sea un uuid+ext nuestro).

El cliente S3 (boto3) se importa de forma DIFERIDA: en local no es necesario (extra `s3`).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config, rutas

# Un nombre de objeto VALIDO es exactamente `<hex/uuid>.<ext>`: minusculas/digitos y un
# unico punto de extension. Lo generamos nosotros asi; esta regex es defensa en profundidad
# para que un nombre con `/`, `..` o separadores NUNCA llegue a una key de S3.
_RE_NOMBRE_OBJETO = re.compile(r"^[A-Za-z0-9._-]+$")


def s3_activo() -> bool:
    """True si la media va a S3/Garage (endpoint + credenciales presentes)."""
    return config.s3_configurado()


# --------------------------------------------------------------------------- #
# Disco (local; comportamiento historico intacto)                              #
# --------------------------------------------------------------------------- #


def dir_media() -> Path:
    """Directorio de media en disco (perfil local).

    `KENI_CONSOLA_MEDIA` lo sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.dir_config()`).
    """
    if (p := config.override_ruta(config.ENV_MEDIA)) is not None:
        return p
    return rutas.dir_config() / "media"


def asegurar_dir() -> Path:
    """Crea (si falta) y devuelve el directorio de media en disco."""
    d = dir_media()
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolver_media(nombre: str) -> Path | None:
    """Resuelve `nombre` DENTRO del dir de media (disco); None si escaparia (anti-traversal).

    Solo aplica al backend de DISCO. Mismo patron defensivo de siempre: cualquier nombre
    que se salga del directorio (`..`, ruta absoluta, symlink fuera) se rechaza con None.
    """
    base = asegurar_dir()
    try:
        destino = (base / nombre).resolve()
    except (OSError, ValueError):
        return None
    base_res = base.resolve()
    if destino == base_res or not destino.is_relative_to(base_res):
        return None
    return destino


# --------------------------------------------------------------------------- #
# S3 / Garage (hosted). Cliente boto3 diferido + cacheado por proceso.          #
# --------------------------------------------------------------------------- #


def _nombre_objeto_seguro(nombre: str) -> str:
    """Valida que `nombre` sea un nombre de objeto plano (sin separadores); lo devuelve.

    Lanza ValueError si trae `/`, `..` o caracteres fuera del set seguro. Siempre lo
    generamos nosotros (uuid+ext), asi que esto es defensa en profundidad para S3.
    """
    if not nombre or "/" in nombre or "\\" in nombre or ".." in nombre:
        raise ValueError(f"nombre de objeto invalido: {nombre!r}")
    if not _RE_NOMBRE_OBJETO.match(nombre):
        raise ValueError(f"nombre de objeto invalido: {nombre!r}")
    return nombre


# Cliente S3 cacheado por proceso: boto3 es caro de crear y la config no cambia en runtime.
_cliente_s3 = None


def _s3():  # noqa: ANN202 -- tipo de boto3 client (no anotamos para no importar al cargar)
    """Cliente S3 (boto3) configurado contra `S3_ENDPOINT` y credenciales. Cacheado.

    Importacion DIFERIDA: boto3 solo es necesario en hosted (extra `s3`). Si falta, error
    claro pidiendo el extra.
    """
    global _cliente_s3
    if _cliente_s3 is not None:
        return _cliente_s3
    try:
        import boto3
        from botocore.config import Config as BotoConfig
    except ImportError as e:  # pragma: no cover -- solo si falta el extra en hosted
        raise RuntimeError(
            "S3 esta cableado pero falta el cliente. Instala el extra `s3` (boto3) en la "
            "imagen del back."
        ) from e
    _cliente_s3 = boto3.client(
        "s3",
        endpoint_url=config.s3_endpoint(),
        region_name=config.s3_region(),
        aws_access_key_id=config.s3_access_key(),
        aws_secret_access_key=config.s3_secret_key(),
        # Path-style (Garage no soporta virtual-host style por subdominio de bucket).
        config=BotoConfig(s3={"addressing_style": "path"}),
    )
    return _cliente_s3


def _resetear_cliente_s3() -> None:
    """Olvida el cliente S3 cacheado (tests: cambian credenciales entre casos)."""
    global _cliente_s3
    _cliente_s3 = None


# --------------------------------------------------------------------------- #
# API neutra del almacen (la usa media.py): guardar / leer bytes por nombre     #
# --------------------------------------------------------------------------- #


def guardar_objeto(nombre: str, datos: bytes, *, content_type: str) -> None:
    """Guarda `datos` con clave/nombre `nombre` en el backend activo (disco o S3).

    El llamante (`media.py`) ya valido el contenido y genero el nombre (uuid+ext). En S3
    sube con `Content-Type` para que el GET lo sirva correcto; en disco solo escribe.
    """
    if s3_activo():
        cliente = _s3()
        cliente.put_object(
            Bucket=config.s3_bucket(),
            Key=_nombre_objeto_seguro(nombre),
            Body=datos,
            ContentType=content_type,
        )
        return
    destino_dir = asegurar_dir()
    (destino_dir / nombre).write_bytes(datos)


def leer_objeto(nombre: str) -> bytes | None:
    """Devuelve los bytes del objeto `nombre`, o None si no existe / nombre invalido.

    En disco aplica el anti-traversal de `resolver_media`. En S3 lee la key (None si el
    objeto no existe). Lo usa `api/media.py:servir` para devolver la imagen.
    """
    if s3_activo():
        try:
            nombre_seguro = _nombre_objeto_seguro(nombre)
        except ValueError:
            return None
        cliente = _s3()
        try:
            resp = cliente.get_object(Bucket=config.s3_bucket(), Key=nombre_seguro)
        except Exception:  # noqa: BLE001 -- NoSuchKey u otro fallo de lectura -> 404 limpio
            return None
        return resp["Body"].read()
    destino = resolver_media(nombre)
    if destino is None or not destino.is_file():
        return None
    try:
        return destino.read_bytes()
    except OSError:
        return None


def borrar_objeto(nombre: str) -> None:
    """Borra el objeto `nombre` del backend activo (idempotente; usado al limpiar restos)."""
    if s3_activo():
        try:
            nombre_seguro = _nombre_objeto_seguro(nombre)
        except ValueError:
            return
        try:
            _s3().delete_object(Bucket=config.s3_bucket(), Key=nombre_seguro)
        except Exception:  # noqa: BLE001 -- borrado best-effort
            return
        return
    destino = resolver_media(nombre)
    if destino is not None:
        destino.unlink(missing_ok=True)
