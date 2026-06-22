"""Almacen de OBJETOS de media: disco (local) o S3/Garage (hosted), un solo codigo.

`media.py` valida/genera la imagen y SIEMPRE inventa el NOMBRE del objeto (uuid+ext); este
modulo solo decide DONDE vive ese objeto, segun la config S3 (ver `config.s3_configurado`):

  - SIN S3 cableado  -> disco local bajo `dir_media()` (perfil privado/local de ADR
    0001/0002). Comportamiento HISTORICO intacto: nada sale de la maquina.
  - CON S3 cableado  -> bucket S3/Garage (`S3_ENDPOINT`/`S3_BUCKET`/credenciales). El stack
    `deploy/` lo cablea; el cutover de objetos lo hace `migracion.py` (one-shot).

CARPETAS POR TIPO: el almacen se DIVIDE en subcarpetas por categoria de dato (`fotos/`,
`logos/`, `plantillas/`, `render/`, ...). La key de un objeto es `<categoria>/<nombre-plano>`
(o el nombre plano, compat historico). El prefijo lo elige SIEMPRE el server (`componer_clave`
desde `media.py` o la promocion de reusables), NUNCA el cliente. Asi se puede limpiar a mano
unas carpetas (fotos efimeras) sin tocar otras (logos/plantillas reusables).

SEGURIDAD: el nombre plano del objeto lo genera SIEMPRE el llamante (`media.py`: uuid/sha256 +
ext normalizada), NUNCA el cliente. En disco, `resolver_media` valida ANTI-TRAVERSAL que la key
caiga dentro del dir. En S3 la key se valida con `_clave_segura`: la categoria (si la hay) debe
ser una de CATEGORIAS y el resto un nombre plano; cualquier `..`/separador raro se rechaza.

El cliente S3 (boto3) se importa de forma DIFERIDA: en local no es necesario (extra `s3`).
"""

from __future__ import annotations

import re
import shutil
import threading
from pathlib import Path

from . import config, rutas

# Un nombre de objeto plano VALIDO es exactamente `<hex/uuid>.<ext>`: minusculas/digitos y un
# unico punto de extension. Lo generamos nosotros asi; esta regex es defensa en profundidad
# para que un nombre con `/`, `..` o separadores NUNCA se cuele crudo en una key de S3.
_RE_NOMBRE_OBJETO = re.compile(r"^[A-Za-z0-9._-]+$")

# CATEGORIAS = subcarpetas (prefijos de key) en las que se DIVIDE el almacen por TIPO de dato.
# Cerrado a proposito: el prefijo lo elige SIEMPRE el server (`media.py` / promocion), NUNCA el
# cliente. Permite limpiar manualmente unas carpetas sin tocar otras (logos/plantillas reusables
# frente a fotos efimeras). Una key con categoria es exactamente `<categoria>/<nombre-plano>` (un
# solo nivel). Sin categoria, la key es el nombre plano (compat con el almacen historico).
CATEGORIAS: frozenset[str] = frozenset(
    {
        "fotos",        # fotos crudas subidas / extraidas (efimeras; borrables manualmente)
        "videos",       # videos crudos subidos para piezas de formato video (efimeros)
        "audios",       # audios/videos del gestor de transcripciones; el GC los CONSERVA mientras
                        # exista su fila en audio_transcripciones (reanudar/re-transcribir/snippets)
        "documentos",   # documentos de importacion de parrilla (PDF/word/...; efimeros)
        "generadas",    # variantes de imagen generadas por IA (efimeras)
        "render",       # composites horneados / cache de render (reciclable, regenerable)
        "deriv",        # derivadas redimensionadas (WebP por ancho) de un original (cache regenerable)
        "previews",     # cache del preview de plantillas (1 png por documento+muestra; regenerable)
        "plantillas",   # assets del editor de plantillas + miniaturas (reusable)
        "logos",        # activos de marca: logos, tipografias, plecas (reusable)
        "artes",        # artes catalogadas (galeria) para reutilizar (reusable)
        "texto",        # soporte para servir objetos ya promovidos a `texto/`.
    }
)


def componer_clave(categoria: str | None, nombre: str) -> str:
    """Compone la KEY del almacen a partir de la `categoria` (subcarpeta) y el `nombre` plano.

    `nombre` es el nombre de objeto plano que genera `media.py` (uuid/sha256 + ext normalizada). Con
    `categoria` (∈ CATEGORIAS) la key es `<categoria>/<nombre>`; sin ella, el nombre plano (compat
    con el almacen historico sin carpetas). Valida ambos trozos; lanza ValueError si algo no cuadra.
    """
    base = _nombre_plano_seguro(nombre)
    if categoria is None:
        return base
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria de objeto invalida: {categoria!r}")
    return f"{categoria}/{base}"


def categoria_de(clave: str) -> str | None:
    """Categoria (subcarpeta) de una key, o None si es una key plana / prefijo desconocido."""
    cat, sep, _ = clave.partition("/")
    return cat if sep and cat in CATEGORIAS else None


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


def _nombre_plano_seguro(nombre: str) -> str:
    """Valida que `nombre` sea un nombre de objeto PLANO (sin separadores); lo devuelve.

    Lanza ValueError si trae `/`, `..` o caracteres fuera del set seguro. Siempre lo
    generamos nosotros (uuid/sha256 + ext), asi que esto es defensa en profundidad.
    """
    if not nombre or "/" in nombre or "\\" in nombre or ".." in nombre:
        raise ValueError(f"nombre de objeto invalido: {nombre!r}")
    if not _RE_NOMBRE_OBJETO.match(nombre):
        raise ValueError(f"nombre de objeto invalido: {nombre!r}")
    return nombre


def _clave_segura(clave: str) -> str:
    """Valida una KEY de almacen: nombre plano O `<categoria>/<nombre-plano>` (un solo nivel).

    Es la frontera defensiva para S3: la categoria, si la hay, debe ser una de CATEGORIAS, y el
    resto un nombre plano seguro. Un `..`, doble `/`, prefijo desconocido o caracter raro -> error.
    Las keys SIEMPRE las componemos nosotros (`componer_clave`), asi que esto es defensa en
    profundidad para que nada con separadores arbitrarios llegue al bucket.
    """
    cat, sep, resto = clave.partition("/")
    if not sep:
        return _nombre_plano_seguro(clave)
    if cat not in CATEGORIAS:
        raise ValueError(f"categoria de objeto invalida: {cat!r}")
    return f"{cat}/{_nombre_plano_seguro(resto)}"


# Cliente S3 cacheado por proceso: boto3 es caro de crear y la config no cambia en runtime.
# `_CLIENTE_LOCK` serializa la creacion perezosa (double-checked): sin el, dos hilos podrian
# crear dos clientes boto3 a la vez al primer uso.
_cliente_s3 = None
_CLIENTE_LOCK = threading.Lock()


def _s3():  # noqa: ANN202 -- tipo de boto3 client (no anotamos para no importar al cargar)
    """Cliente S3 (boto3) configurado contra `S3_ENDPOINT` y credenciales. Cacheado.

    Importacion DIFERIDA: boto3 solo es necesario en hosted (extra `s3`). Si falta, error
    claro pidiendo el extra.
    """
    global _cliente_s3
    if _cliente_s3 is not None:
        return _cliente_s3
    with _CLIENTE_LOCK:
        # Re-verifica dentro del lock: otro hilo pudo crearlo mientras esperabamos.
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
    with _CLIENTE_LOCK:
        _cliente_s3 = None


# --------------------------------------------------------------------------- #
# API neutra del almacen (la usa media.py): guardar / leer bytes por nombre     #
# --------------------------------------------------------------------------- #


def guardar_objeto(nombre: str, datos: bytes, *, content_type: str) -> None:
    """Guarda `datos` con clave/nombre `nombre` en el backend activo (disco o S3).

    El llamante (`media.py`) ya valido el contenido y compuso la key (`componer_clave`: nombre
    plano o `<categoria>/<nombre>`). En S3 sube con `Content-Type` para que el GET lo sirva
    correcto; en disco escribe, creando la subcarpeta de la categoria si hace falta.
    """
    clave = _clave_segura(nombre)
    if s3_activo():
        cliente = _s3()
        cliente.put_object(
            Bucket=config.s3_bucket(),
            Key=clave,
            Body=datos,
            ContentType=content_type,
        )
        return
    destino = resolver_media(clave)
    if destino is None:
        raise ValueError(f"clave de objeto invalida: {nombre!r}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)


def leer_objeto(nombre: str) -> bytes | None:
    """Devuelve los bytes del objeto `nombre`, o None si no existe / nombre invalido.

    En disco aplica el anti-traversal de `resolver_media`. En S3 lee la key (None si el
    objeto no existe). Lo usa `api/media.py:servir` para devolver la imagen.
    """
    if s3_activo():
        try:
            nombre_seguro = _clave_segura(nombre)
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


def objeto_existe(nombre: str) -> bool:
    """True si el objeto `nombre` ya existe en el backend activo (sin leer sus bytes).

    Lo usa el guardado CONTENT-ADDRESSED (`media.importar_imagen`): si la key derivada del
    hash del contenido ya está, no hace falta re-subir bytes idénticos. En S3 es un
    `head_object` (barato); en disco, un `is_file`. Nombre inválido -> False.
    """
    if s3_activo():
        try:
            nombre_seguro = _clave_segura(nombre)
        except ValueError:
            return False
        try:
            _s3().head_object(Bucket=config.s3_bucket(), Key=nombre_seguro)
        except Exception:  # noqa: BLE001 -- NoSuchKey u otro -> tratamos como ausente
            return False
        return True
    destino = resolver_media(nombre)
    return destino is not None and destino.is_file()


def listar_objetos() -> list[tuple[str, float]]:
    """Lista los objetos del backend activo como `(nombre, mtime_epoch)` (neutral disco/S3).

    `mtime_epoch` es la antiguedad del objeto en segundos epoch (UTC): en disco el mtime del
    fichero; en S3/Garage el `LastModified` de la key. Lo usa el GC de sueltos para borrar
    SOLO los objetos viejos (no las variantes recien generadas que el usuario aun revisa).

    - DISCO: recorre `dir_media()` RECURSIVAMENTE y devuelve cada fichero con su mtime. La key
      es la ruta RELATIVA a la raiz en estilo posix (`fotos/<uuid>.jpg`), espejo de la key de
      S3: asi el GC y el resto del codigo ven el MISMO identificador en ambos backends. Si el
      directorio no existe aun, devuelve lista vacia.
    - S3/Garage: pagina `list_objects_v2` sobre el bucket y devuelve `Key` + `LastModified`
      (convertido a epoch). La key incluye su subcarpeta de categoria (`fotos/<uuid>.jpg`).

    Best-effort por backend: un fallo de listado se propaga (lo gestiona el llamante), pero
    nunca devuelve nombres parciales mezclados con errores silenciosos.
    """
    if s3_activo():
        cliente = _s3()
        bucket = config.s3_bucket()
        objetos: list[tuple[str, float]] = []
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {"Bucket": bucket}
            if token:
                kwargs["ContinuationToken"] = token
            resp = cliente.list_objects_v2(**kwargs)
            for item in resp.get("Contents", []) or []:
                clave = item.get("Key")
                if not clave:
                    continue
                modificado = item.get("LastModified")
                mtime = modificado.timestamp() if modificado is not None else 0.0
                objetos.append((clave, mtime))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
            if not token:
                break
        return objetos
    base = dir_media()
    if not base.is_dir():
        return []
    salida: list[tuple[str, float]] = []
    for entrada in base.rglob("*"):
        if not entrada.is_file():
            continue
        try:
            clave = entrada.relative_to(base).as_posix()
            salida.append((clave, entrada.stat().st_mtime))
        except OSError:
            continue
    return salida


def promover_objeto(clave: str, categoria: str) -> str:
    """Promueve (COPIA) el objeto `clave` a la subcarpeta `categoria` y devuelve su nueva key.

    Para llevar un objeto a su carpeta por tipo cuando su rol se decide DESPUES de subirlo (un
    upload generico que se cataloga como logo de marca, arte de texto o miniatura de
    plantilla: no se re-sube, solo se referencia). Conserva el nombre plano (uuid/sha256+ext) y
    solo cambia el prefijo. Idempotente: si `clave` ya esta en `categoria`, no hace nada.

    COPIA, no mueve: NO borra el origen. Razon -> el mismo objeto puede seguir referenciado por
    una pieza desde `fotos/`; borrar el origen romperia esa pieza. Con limpieza manual, la copia
    vive en su carpeta protegida (logos/texto/plantillas) y el origen efimero en `fotos/` se
    elimina cuando el equipo vacia esa carpeta a mano. Devuelve la `clave` original sin tocar si
    el objeto no existe (no perdemos la referencia existente).
    """
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria de objeto invalida: {categoria!r}")
    if categoria_de(clave) == categoria:
        return clave
    base = clave.rpartition("/")[2] if "/" in clave else clave
    destino = componer_clave(categoria, base)
    if destino == clave:
        return clave
    if objeto_existe(destino):
        return destino
    datos = leer_objeto(clave)
    if datos is None:
        return clave
    import mimetypes

    ct = mimetypes.guess_type(base)[0] or "application/octet-stream"
    guardar_objeto(destino, datos, content_type=ct)
    return destino


def borrar_objeto(nombre: str) -> None:
    """Borra el objeto `nombre` del backend activo (idempotente; usado al limpiar restos)."""
    if s3_activo():
        try:
            nombre_seguro = _clave_segura(nombre)
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


def borrar_prefijo(prefijo: str) -> int:
    """Borra TODOS los objetos cuya clave empieza por `prefijo`. Idempotente, best-effort.

    A diferencia de `borrar_objeto`, opera sobre claves CRUDAS multinivel: la usa la limpieza de
    los bundles de preview del carril dev (`previews/sug-<id>/...`), cuyas rutas anidadas quedan
    fuera del esquema `<categoria>/<nombre>` del resto de la media. Devuelve cuantos borro.
    """
    if not prefijo:
        return 0
    if s3_activo():
        cliente = _s3()
        bucket = config.s3_bucket()
        borrados = 0
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {"Bucket": bucket, "Prefix": prefijo}
            if token:
                kwargs["ContinuationToken"] = token
            try:
                resp = cliente.list_objects_v2(**kwargs)
            except Exception:  # noqa: BLE001 -- listado best-effort
                return borrados
            lote = [{"Key": it["Key"]} for it in (resp.get("Contents") or []) if it.get("Key")]
            if lote:
                try:
                    cliente.delete_objects(Bucket=bucket, Delete={"Objects": lote, "Quiet": True})
                    borrados += len(lote)
                except Exception:  # noqa: BLE001 -- caida a borrado uno-a-uno
                    for obj in lote:
                        try:
                            cliente.delete_object(Bucket=bucket, Key=obj["Key"])
                            borrados += 1
                        except Exception:  # noqa: BLE001 -- best-effort por clave
                            pass
            if not resp.get("IsTruncated"):
                return borrados
            token = resp.get("NextContinuationToken")
            if not token:
                return borrados
    # Disco: borra el subarbol bajo el prefijo, anclado DENTRO del dir de media (anti-traversal).
    base = asegurar_dir().resolve()
    objetivo = (base / prefijo).resolve()
    if objetivo == base or not objetivo.is_relative_to(base) or not objetivo.exists():
        return 0
    contados = sum(1 for p in objetivo.rglob("*") if p.is_file())
    shutil.rmtree(objetivo, ignore_errors=True)
    return contados
