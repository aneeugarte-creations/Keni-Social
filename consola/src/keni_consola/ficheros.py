"""Backend de FICHEROS YAML de la Consola Keni: el contenido vive en disco.

FUENTE DE VERDAD = los ficheros YAML, organizados POR MARCA (agente = marca =
carpeta). Este modulo expone las MISMAS funciones publicas que `db.py` para las
entidades de CONTENIDO, de modo que la fachada `repos.py` pueda delegar aqui sin
que ningun `api/*.py` cambie. `tareas` NO vive aqui (sigue en SQLite via `db.py`).

LAYOUT (raiz = `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`):

    <raiz>/<marca>/
        marca.yaml                  # id, etiqueta, id_metricas
        CLAUDE.md                   # minimo, si falta
        publicaciones/<id>.yaml
        plantillas/<id>.yaml
        fuentes-rss/<id>.yaml
        hashtags/<id>.yaml
        franjas.yaml                # UN fichero, lista de franjas de la marca
        historial/<YYYY>/<MM>/<id>.yaml
        .keni/rss-vistos.yaml       # {fuente_id: [clave, ...]}

ESQUEMA YAML por entidad: legible; el `id` es IMPLICITO (= nombre de fichero) y la
`marca` la da la CARPETA (no se repiten como campos dentro del YAML). Cuerpos
largos (`contenido`, `resultado`) salen en bloque `|`. Listas YAML nativas (no
JSON embebido). Booleans nativos. SIEMPRE `yaml.safe_load` al leer.

ESCRITURA ATOMICA: temporal en el mismo dir + `os.replace` (patron de
`secretos.py`). VALIDACION al leer: una entrada con YAML invalido, o con `estado` /
`red` fuera de la allowlist, se OMITE con log (degradado), nunca rompe el listado.

INDICE: `indice.py` (SQLite regenerable) mapea id -> (marca, tipo, ruta) + campos
filtrables. Se actualiza al escribir; si un YAML cambio por fuera (mtime) se
re-indexa; si el indice se borra, se reconstruye leyendo los ficheros.

ORDEN ESTABLE: las fechas de creacion llevan HORA (ISO datetime) para un orden
determinista (antes el orden se apoyaba en el `rowid` de SQLite).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from keni_shared.esquema_yaml import migrar, sellar

from . import config, indice, marcas, redes, rutas
from .estados import ESTADOS_PUBLICACION, ESTADOS_TAREA  # re-export para la fachada
from .io_atomico import escribir_atomico

_log = logging.getLogger("keni_consola.ficheros")

__all__ = ["ESTADOS_TAREA", "ESTADOS_PUBLICACION"]

# Sub-carpetas por entidad dentro de la carpeta de cada marca.
_SUBDIR = {
    "publicacion": "publicaciones",
    "plantilla": "plantillas",
    "fuente_rss": "fuentes-rss",
    "grupo_hashtags": "hashtags",
}

# Marca por defecto para entidades creadas SIN marca (la carpeta necesita un slug).
_MARCA_SIN = "_sin-marca"

# Tipo de INDICE -> tipo de ESQUEMA (`keni_shared.esquema_yaml.VERSIONES`). Solo
# difieren en `historial` (indice) vs `historial_skill` (esquema); el resto coincide.
_TIPO_ESQUEMA = {
    "publicacion": "publicacion",
    "plantilla": "plantilla",
    "fuente_rss": "fuente_rss",
    "grupo_hashtags": "grupo_hashtags",
    "historial": "historial_skill",
}


# --------------------------------------------------------------------------- #
# Raiz / carpeta de marca                                                      #
# --------------------------------------------------------------------------- #


def raiz_datos() -> Path:
    """Raiz de datos de ficheros (CONTENIDO editorial por marca).

    `KENI_CONSOLA_RAIZ` la sobreescribe (override de maxima prioridad; tests). Si no,
    cuelga de la raiz de estado unica (`rutas.raiz_proyectos()`): local `~/keni-proyectos`
    EXACTAMENTE como antes, o `<KENI_DATA_DIR>/keni-proyectos` en contenedor.
    """
    if (p := config.override_ruta(config.ENV_RAIZ)) is not None:
        return p
    return rutas.raiz_proyectos()


def _slug_marca(marca: str) -> str:
    """Slug de carpeta para una marca (cae a `_MARCA_SIN` si viene vacia)."""
    return marca or _MARCA_SIN


def carpeta_marca(marca: str) -> Path:
    """Carpeta `<raiz>/<marca>/`, creando `marca.yaml` y `CLAUDE.md` minimos si faltan."""
    carpeta = raiz_datos() / _slug_marca(marca)
    carpeta.mkdir(parents=True, exist_ok=True)
    _sembrar_marca(carpeta, marca)
    return carpeta


def _sembrar_marca(carpeta: Path, marca: str) -> None:
    """Crea `marca.yaml` (id/etiqueta/id_metricas) y un `CLAUDE.md` minimo si no existen."""
    meta = carpeta / "marca.yaml"
    if not meta.exists() and marca:
        datos = {
            "id": marca,
            "etiqueta": marcas.etiqueta_de(marca),
            "id_metricas": marcas.id_metricas_de(marca),
        }
        _escribir_yaml(meta, datos, tipo="marca")
    claude = carpeta / "CLAUDE.md"
    if not claude.exists() and marca:
        claude.write_text(
            f"# {marcas.etiqueta_de(marca)}\n\n"
            "Carpeta de contenido de esta marca (agente = marca = carpeta).\n"
            "El contenido (publicaciones, plantillas, RSS, hashtags, franjas, "
            "historial) vive aqui como ficheros YAML, fuente de verdad.\n",
            encoding="utf-8",
        )


def _subcarpeta(marca: str, tipo: str) -> Path:
    """Sub-carpeta de un `tipo` dentro de la marca (creada si falta)."""
    carpeta = carpeta_marca(marca) / _SUBDIR[tipo]
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _marcas_en_disco() -> list[str]:
    """Slugs de marca presentes en disco (carpetas con `marca.yaml` o sub-carpetas)."""
    raiz = raiz_datos()
    if not raiz.is_dir():
        return []
    slugs: list[str] = []
    for hijo in sorted(raiz.iterdir()):
        if hijo.is_dir() and not hijo.name.startswith("."):
            slugs.append(hijo.name)
    return slugs


def _marca_de_slug(slug: str) -> str:
    """Traduce el slug de carpeta a la `marca` interna (`_MARCA_SIN` => '')."""
    return "" if slug == _MARCA_SIN else slug


# --------------------------------------------------------------------------- #
# YAML: lectura / escritura atomica                                            #
# --------------------------------------------------------------------------- #


class _DumperBloque(yaml.SafeDumper):
    """SafeDumper que vuelca los strings multilinea como bloque literal `|`.

    PyYAML por defecto representa los textos con saltos de linea en estilo plegado
    o entre comillas (feo de editar a mano). Forzamos el bloque `|` cuando el texto
    tiene saltos de linea, para que un humano (o Claude Code) edite el cuerpo
    (p. ej. `contenido`, `resultado`) comodamente. Si una linea tiene espacios al
    final, PyYAML cae solo a un estilo seguro (no se puede romper el round-trip).
    """


def _str_bloque(dumper: yaml.Dumper, data: str) -> Any:
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_DumperBloque.add_representer(str, _str_bloque)


def _escribir_yaml(ruta: Path, datos: dict[str, Any], *, tipo: str) -> None:
    """Escribe un dict como YAML legible de forma ATOMICA (tmp + os.replace).

    `default_flow_style=False` (mapas/listas en bloque), `allow_unicode=True`
    (acentos sin escapar), `sort_keys=False` (respeta el orden dado), y bloque `|`
    para textos multilinea (via `_DumperBloque`). `sellar(tipo, ...)` estampa la
    `version` de esquema antes de volcar (#125).
    """
    texto = yaml.dump(
        sellar(tipo, datos),
        Dumper=_DumperBloque,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=4096,
    )
    escribir_atomico(ruta, texto, sufijo=".yaml")


def _leer_yaml(ruta: Path, *, tipo: str) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa.

    Degrada con log (nunca lanza): un fichero ilegible se trata como ausente. Al
    leer aplica `migrar(tipo, ...)` (upgrade perezoso de esquema, #125): un YAML
    legado sin `version` se trata como version 0 y se sube a la actual en memoria.
    """
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        _log.warning("YAML invalido, se omite: %s", ruta)
        return None
    if not isinstance(datos, dict):
        _log.warning("YAML no es un mapa, se omite: %s", ruta)
        return None
    return migrar(tipo, datos)


def _ahora_iso() -> str:
    """Fecha-hora ISO a segundos (orden determinista en la creacion)."""
    return datetime.now().isoformat(timespec="seconds")


def _nuevo_id() -> str:
    """Nuevo id corto (mismo formato que `db.py`: 12 hex)."""
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------- #
# Localizacion de una entidad por id (indice -> ruta; con re-indexado por mtime) #
# --------------------------------------------------------------------------- #


def _buscar_ruta(tipo: str, entidad_id: str) -> Path | None:
    """Ruta del fichero de una entidad por id: via indice, con fallback a escaneo.

    Si el indice apunta a una ruta que existe, se usa. Si no (indice borrado o
    desfasado), se reconstruye el indice de ese tipo y se reintenta.
    """
    entrada = indice.obtener(tipo, entidad_id)
    if entrada is not None:
        ruta = Path(entrada["ruta"])
        if ruta.exists():
            return ruta
    # Indice ausente o desfasado: reconstruir ese tipo y reintentar.
    _reindexar_tipo(tipo)
    entrada = indice.obtener(tipo, entidad_id)
    if entrada is not None:
        ruta = Path(entrada["ruta"])
        if ruta.exists():
            return ruta
    return None


def _indexar(tipo: str, marca: str, ruta: Path, datos: dict[str, Any]) -> None:
    """Da de alta/actualiza la entrada de indice de una entidad recien escrita."""
    indice.upsert(_a_entrada_indice(tipo, marca, ruta, datos))


def _a_entrada_indice(tipo: str, marca: str, ruta: Path, datos: dict[str, Any]) -> dict[str, Any]:
    """Construye la fila de indice (campos filtrables) de una entidad ya cargada."""
    try:
        mtime = ruta.stat().st_mtime
    except OSError:
        mtime = 0.0
    return {
        "id": ruta.stem,
        "tipo": tipo,
        "marca": marca,
        "ruta": str(ruta),
        "mtime": mtime,
        "red": datos.get("red", "") or "",
        "estado": datos.get("estado", "") or "",
        "evergreen": bool(datos.get("evergreen")),
        "fecha": datos.get("fecha", "") or "",
        "fecha_creacion": datos.get("fecha_creacion", "") or "",
    }


# --------------------------------------------------------------------------- #
# Reconstruccion del indice (regenerable desde los YAML)                       #
# --------------------------------------------------------------------------- #


def _rutas_de_tipo(tipo: str) -> list[tuple[str, Path]]:
    """Lista `(marca, ruta_yaml)` de TODAS las entidades de un tipo en todas las marcas."""
    pares: list[tuple[str, Path]] = []
    for slug in _marcas_en_disco():
        marca = _marca_de_slug(slug)
        if tipo == "historial":
            base = raiz_datos() / slug / "historial"
            if base.is_dir():
                pares.extend((marca, p) for p in base.rglob("*.yaml"))
        else:
            base = raiz_datos() / slug / _SUBDIR[tipo]
            if base.is_dir():
                pares.extend((marca, p) for p in sorted(base.glob("*.yaml")))
    return pares


def _reindexar_tipo(tipo: str) -> None:
    """Reconstruye en el indice TODAS las entradas de un `tipo` leyendo el disco."""
    entradas: list[dict[str, Any]] = []
    for marca, ruta in _rutas_de_tipo(tipo):
        datos = _leer_yaml(ruta, tipo=_TIPO_ESQUEMA[tipo])
        if datos is None:
            continue
        entradas.append(_a_entrada_indice(tipo, marca, ruta, datos))
    indice.reemplazar_tipo(tipo, entradas)


def reconstruir_indice() -> None:
    """Reconstruye el indice COMPLETO desde los ficheros (todas las entidades indexadas).

    Los tipos de CONTENIDO editorial (publicacion/plantilla/fuente_rss/grupo_hashtags/
    historial) los reconstruye este modulo; el tipo `run` lo posee `agentes.py` (los
    runs viven en `runs/<id>.yaml` por agente, no en sub-carpetas de contenido), asi
    que se delega ahi para no acoplar `ficheros` al layout de runs.
    """
    for tipo in indice.TIPOS:
        if tipo == "run":
            continue
        _reindexar_tipo(tipo)
    from . import agentes  # import local: evita ciclo a nivel de modulo
    agentes.reindexar_runs()


def _listar_validado(
    tipo: str,
    *,
    filtros: dict[str, Any] | None,
    parsear,  # noqa: ANN001 -- callable(datos, marca, id) -> dict | None
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    """Lista entidades indexadas de un tipo, cargando+validando SOLO la pagina pedida.

    Si el indice esta vacio para ese tipo pero hay ficheros en disco, primero lo
    reconstruye (cubre el caso de indice borrado). Las entradas cuyo YAML ya no
    existe o no valida se OMITEN (degradado), sin romper el listado.

    `limite`/`desplazamiento` se EMPUJAN al indice (`LIMIT/OFFSET`): asi solo se leen
    los cuerpos YAML de la PAGINA, no de todas las coincidencias. `limite=None`
    devuelve el conjunto completo (retrocompat). Para que la reconstruccion perezosa
    no se salte por un OFFSET mas alla del final, el chequeo de "indice vacio" mira el
    conteo SIN paginar.
    """
    if indice.contar(tipo, filtros) == 0 and _rutas_de_tipo(tipo):
        _reindexar_tipo(tipo)
    entradas = indice.listar(tipo, filtros=filtros, limite=limite, desplazamiento=desplazamiento)
    salida: list[dict[str, Any]] = []
    for entrada in entradas:
        ruta = Path(entrada["ruta"])
        datos = _leer_yaml(ruta, tipo=_TIPO_ESQUEMA[tipo])
        if datos is None:
            continue
        item = parsear(datos, entrada["marca"], entrada["id"])
        if item is not None:
            salida.append(item)
    return salida


# --------------------------------------------------------------------------- #
# Publicaciones                                                                #
# --------------------------------------------------------------------------- #

# Campos que la edicion parcial puede tocar (igual que `db.py`). Incluye los del flujo
# de aprobacion de equipo (#9, Fase 3: revisor/marcas de tiempo) y la preparacion del
# programador (`preparado_en`), todos ADITIVOS y retrocompatibles.
_CAMPOS_EDITABLES_PUBLICACION = (
    "titulo",
    "contenido",
    "estado",
    "fecha_programada",
    "imagen",
    "evergreen",
    # Flujo de aprobacion de equipo (#9).
    "enviado_a_revision_en",
    "revisor_id",
    "revisor_nombre",
    "revisado_en",
    # Preparacion por el programador (#9): marca dry-run "lista para publicar".
    "preparado_en",
    # Publicacion real via Metricool: id del post en el scheduler de Metricool.
    "id_post_metricool",
)


def _publicacion_yaml(pub: dict[str, Any]) -> dict[str, Any]:
    """Cuerpo YAML de una publicacion (sin `id` ni `marca`: implicitos por fichero/carpeta).

    `autor_id`/`autor_nombre` (atribucion por usuario, #130 Fase 1) se persisten como
    campos mas; vacios en creaciones anonimas o legadas (retrocompat: un YAML sin estas
    claves se lee como "sin autor", ver `_parsear_publicacion`).
    """
    return {
        "titulo": pub["titulo"],
        "red": pub["red"],
        "estado": pub["estado"],
        "veredicto": pub["veredicto"],
        "evergreen": bool(pub["evergreen"]),
        "autor_id": pub.get("autor_id", "") or "",
        "autor_nombre": pub.get("autor_nombre", "") or "",
        # Flujo de aprobacion de equipo (#9, Fase 3). Aditivos: una pieza legada no los
        # trae y se leen como "" (ver `_parsear_publicacion`); nunca rompen el round-trip.
        "enviado_a_revision_en": pub.get("enviado_a_revision_en", "") or "",
        "revisor_id": pub.get("revisor_id", "") or "",
        "revisor_nombre": pub.get("revisor_nombre", "") or "",
        "revisado_en": pub.get("revisado_en", "") or "",
        # Marca dry-run del programador (#9): instante en que se preparo "lista para
        # publicar" (NO publica de verdad; gating en #5/#8). "" hasta que vence.
        "preparado_en": pub.get("preparado_en", "") or "",
        # Id del post en Metricool una vez programado de verdad (KENI_PUBLICAR_REAL).
        # "" en dry-run y en piezas legadas; nunca rompe el round-trip.
        "id_post_metricool": pub.get("id_post_metricool", "") or "",
        "fecha_creacion": pub["fecha_creacion"],
        "fecha_actualizacion": pub["fecha_actualizacion"],
        "fecha_programada": pub["fecha_programada"],
        "origen": pub["origen"],
        "imagen": pub["imagen"],
        "contenido": pub["contenido"],
    }


def _parsear_publicacion(datos: dict[str, Any], marca: str, pub_id: str) -> dict[str, Any] | None:
    """Reconstruye el dict publico de una publicacion; None si `red`/`estado` invalidos."""
    red = datos.get("red", "")
    estado = datos.get("estado", "borrador")
    if not isinstance(red, str) or not redes.es_red(red):
        _log.warning("publicacion %s: red invalida %r, se omite", pub_id, red)
        return None
    if estado not in ESTADOS_PUBLICACION:
        _log.warning("publicacion %s: estado invalido %r, se omite", pub_id, estado)
        return None
    return {
        "id": pub_id,
        "titulo": datos.get("titulo", "") or "",
        "marca": marca,
        "red": red,
        "contenido": datos.get("contenido", "") or "",
        "estado": estado,
        "veredicto": datos.get("veredicto", "") or "",
        # Atribucion por usuario (#130 Fase 1). Ausente en publicaciones legadas/anonimas
        # => "" (la UI lo muestra como "desconocido"); nunca rompe la lectura.
        "autor_id": datos.get("autor_id", "") or "",
        "autor_nombre": datos.get("autor_nombre", "") or "",
        # Flujo de aprobacion de equipo (#9, Fase 3). Ausentes en piezas legadas => ""
        # (la pieza simplemente no ha pasado por revision aun); nunca rompe la lectura.
        "enviado_a_revision_en": datos.get("enviado_a_revision_en", "") or "",
        "revisor_id": datos.get("revisor_id", "") or "",
        "revisor_nombre": datos.get("revisor_nombre", "") or "",
        "revisado_en": datos.get("revisado_en", "") or "",
        # Marca dry-run del programador (#9): "" hasta que el programador la prepara.
        "preparado_en": datos.get("preparado_en", "") or "",
        # Id del post en Metricool (solo cuando KENI_PUBLICAR_REAL esta activo).
        "id_post_metricool": datos.get("id_post_metricool", "") or "",
        "fecha_creacion": datos.get("fecha_creacion", "") or "",
        "fecha_actualizacion": datos.get("fecha_actualizacion", "") or "",
        "fecha_programada": datos.get("fecha_programada", "") or "",
        "origen": datos.get("origen", "") or "",
        "imagen": datos.get("imagen", "") or "",
        "evergreen": bool(datos.get("evergreen")),
    }


def _construir_publicacion(datos: dict[str, Any]) -> dict[str, Any]:
    """Normaliza un dict de entrada en una publicacion completa (id + fechas con hora)."""
    ahora = _ahora_iso()
    return {
        "id": _nuevo_id(),
        "titulo": datos.get("titulo") or "",
        "marca": datos.get("marca") or "",
        "red": datos.get("red") or "",
        "contenido": datos.get("contenido") or "",
        "estado": datos.get("estado") or "borrador",
        "veredicto": datos.get("veredicto") or "",
        "autor_id": datos.get("autor_id") or "",
        "autor_nombre": datos.get("autor_nombre") or "",
        # Flujo de aprobacion de equipo (#9): una pieza nueva nace sin revision.
        "enviado_a_revision_en": datos.get("enviado_a_revision_en") or "",
        "revisor_id": datos.get("revisor_id") or "",
        "revisor_nombre": datos.get("revisor_nombre") or "",
        "revisado_en": datos.get("revisado_en") or "",
        "preparado_en": datos.get("preparado_en") or "",
        "id_post_metricool": datos.get("id_post_metricool") or "",
        "fecha_creacion": ahora,
        "fecha_actualizacion": ahora,
        "fecha_programada": datos.get("fecha_programada") or "",
        "origen": datos.get("origen") or "",
        "imagen": datos.get("imagen") or "",
        "evergreen": bool(datos.get("evergreen")),
    }


def _guardar_publicacion(pub: dict[str, Any]) -> None:
    """Escribe el YAML de una publicacion y actualiza el indice."""
    ruta = _subcarpeta(pub["marca"], "publicacion") / f"{pub['id']}.yaml"
    cuerpo = _publicacion_yaml(pub)
    _escribir_yaml(ruta, cuerpo, tipo="publicacion")
    _indexar("publicacion", pub["marca"], ruta, cuerpo)


def crear_publicacion(
    marca: str,
    red: str,
    *,
    titulo: str = "",
    contenido: str = "",
    estado: str = "borrador",
    veredicto: str = "",
    fecha_programada: str = "",
    origen: str = "",
    imagen: str = "",
    evergreen: bool = False,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Crea una publicacion (un YAML en `<marca>/publicaciones/`) y la devuelve.

    `autor` (atribucion por usuario, #130 Fase 1) es `{"id", "usuario"}` o `None`
    (creacion anonima / por token de mantenimiento). Se persiste en el YAML.
    """
    autor = autor or {}
    pub = _construir_publicacion(
        {
            "titulo": titulo,
            "marca": marca,
            "red": red,
            "contenido": contenido,
            "estado": estado,
            "veredicto": veredicto,
            "fecha_programada": fecha_programada,
            "origen": origen,
            "imagen": imagen,
            "evergreen": evergreen,
            "autor_id": autor.get("id", ""),
            "autor_nombre": autor.get("usuario", ""),
        }
    )
    _guardar_publicacion(pub)
    return pub


def crear_publicaciones(lista: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Crea varias publicaciones (una por dict de entrada) y las devuelve."""
    creadas: list[dict[str, Any]] = []
    for d in lista:
        pub = _construir_publicacion(d)
        _guardar_publicacion(pub)
        creadas.append(pub)
    return creadas


def listar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
    *,
    limite: int | None = None,
    desplazamiento: int | None = None,
) -> list[dict[str, Any]]:
    """Publicaciones (mas recientes primero), con filtros y paginacion opcionales.

    `limite=None` (def) devuelve todas (retrocompat); con `limite`/`desplazamiento`
    solo se lee el cuerpo YAML de la pagina pedida.
    """
    return _listar_validado(
        "publicacion",
        filtros={"marca": marca, "red": red, "estado": estado, "evergreen": evergreen},
        parsear=_parsear_publicacion,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_publicaciones(
    marca: str | None = None,
    red: str | None = None,
    estado: str | None = None,
    evergreen: bool | None = None,
) -> int:
    """Total de publicaciones que casan los filtros (para el `total` de paginacion)."""
    filtros = {"marca": marca, "red": red, "estado": estado, "evergreen": evergreen}
    if indice.contar("publicacion", filtros) == 0 and _rutas_de_tipo("publicacion"):
        _reindexar_tipo("publicacion")
    return indice.contar("publicacion", filtros)


def obtener_publicacion(publicacion_id: str) -> dict[str, Any] | None:
    """Una publicacion por id (None si no existe o su YAML no valida)."""
    ruta = _buscar_ruta("publicacion", publicacion_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="publicacion")
    if datos is None:
        return None
    marca = _marca_de_slug(ruta.parent.parent.name)
    return _parsear_publicacion(datos, marca, publicacion_id)


def actualizar_publicacion(
    publicacion_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una publicacion (titulo/contenido/estado/fecha_programada/imagen/evergreen)."""
    actual = obtener_publicacion(publicacion_id)
    if actual is None:
        return None
    for clave in _CAMPOS_EDITABLES_PUBLICACION:
        if clave in campos:
            actual[clave] = bool(campos[clave]) if clave == "evergreen" else campos[clave]
    actual["fecha_actualizacion"] = _ahora_iso()
    _guardar_publicacion(actual)
    return actual


def borrar_publicacion(publicacion_id: str) -> bool:
    """Borra una publicacion (su YAML + entrada de indice); True si existia."""
    ruta = _buscar_ruta("publicacion", publicacion_id)
    if ruta is None:
        return False
    ruta.unlink(missing_ok=True)
    indice.borrar("publicacion", publicacion_id)
    return True


# --------------------------------------------------------------------------- #
# Grupos de hashtags                                                           #
# --------------------------------------------------------------------------- #


def _parsear_grupo(datos: dict[str, Any], marca: str, grupo_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de un grupo de hashtags (lista de strings)."""
    tags = datos.get("hashtags")
    if not isinstance(tags, list):
        tags = []
    return {
        "id": grupo_id,
        "nombre": datos.get("nombre", "") or "",
        "marca": marca,
        "hashtags": [t for t in tags if isinstance(t, str)],
    }


def _guardar_grupo(grupo: dict[str, Any]) -> None:
    """Escribe el YAML de un grupo de hashtags y lo indexa."""
    ruta = _subcarpeta(grupo["marca"], "grupo_hashtags") / f"{grupo['id']}.yaml"
    cuerpo = {
        "nombre": grupo["nombre"],
        "fecha_creacion": grupo.get("fecha_creacion", ""),
        "hashtags": list(grupo["hashtags"]),
    }
    _escribir_yaml(ruta, cuerpo, tipo="grupo_hashtags")
    _indexar("grupo_hashtags", grupo["marca"], ruta, cuerpo)


def listar_grupos_hashtags(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Grupos de hashtags (mas recientes primero), con paginacion opcional."""
    return _listar_validado(
        "grupo_hashtags",
        filtros=None,
        parsear=_parsear_grupo,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_grupos_hashtags() -> int:
    """Total de grupos de hashtags (para el `total` de paginacion)."""
    if indice.contar("grupo_hashtags", None) == 0 and _rutas_de_tipo("grupo_hashtags"):
        _reindexar_tipo("grupo_hashtags")
    return indice.contar("grupo_hashtags", None)


def obtener_grupo_hashtags(grupo_id: str) -> dict[str, Any] | None:
    """Un grupo de hashtags por id (None si no existe)."""
    ruta = _buscar_ruta("grupo_hashtags", grupo_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="grupo_hashtags")
    if datos is None:
        return None
    return _parsear_grupo(datos, _marca_de_slug(ruta.parent.parent.name), grupo_id)


def crear_grupo_hashtags(
    nombre: str, marca: str = "", hashtags: list[str] | None = None
) -> dict[str, Any]:
    """Crea un grupo de hashtags y lo devuelve."""
    tags = [t for t in (hashtags or []) if isinstance(t, str)]
    grupo = {
        "id": _nuevo_id(),
        "nombre": nombre,
        "marca": marca,
        "hashtags": tags,
        "fecha_creacion": _ahora_iso(),
    }
    _guardar_grupo(grupo)
    # El dict publico no incluye fecha_creacion (paridad con db.py).
    return {"id": grupo["id"], "nombre": nombre, "marca": marca, "hashtags": tags}


def actualizar_grupo_hashtags(
    grupo_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente un grupo (nombre/marca/hashtags); None si no existe.

    Cambiar de `marca` mueve el fichero a la carpeta de la nueva marca.
    """
    ruta = _buscar_ruta("grupo_hashtags", grupo_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="grupo_hashtags")
    if datos is None:
        return None
    marca_actual = _marca_de_slug(ruta.parent.parent.name)
    actual = _parsear_grupo(datos, marca_actual, grupo_id)
    actual["fecha_creacion"] = datos.get("fecha_creacion", "")

    nueva_marca = marca_actual
    if "nombre" in campos:
        actual["nombre"] = campos["nombre"]
    if "hashtags" in campos:
        actual["hashtags"] = [t for t in (campos["hashtags"] or []) if isinstance(t, str)]
    if "marca" in campos:
        nueva_marca = campos["marca"]

    if nueva_marca != marca_actual:
        ruta.unlink(missing_ok=True)
        indice.borrar("grupo_hashtags", grupo_id)
        actual["marca"] = nueva_marca
    _guardar_grupo({**actual, "marca": nueva_marca})
    return {
        "id": grupo_id,
        "nombre": actual["nombre"],
        "marca": nueva_marca,
        "hashtags": actual["hashtags"],
    }


def borrar_grupo_hashtags(grupo_id: str) -> bool:
    """Borra un grupo de hashtags; True si existia, False si no."""
    ruta = _buscar_ruta("grupo_hashtags", grupo_id)
    if ruta is None:
        return False
    ruta.unlink(missing_ok=True)
    indice.borrar("grupo_hashtags", grupo_id)
    return True


# --------------------------------------------------------------------------- #
# Franjas (UN fichero lista por marca: <marca>/franjas.yaml)                   #
# --------------------------------------------------------------------------- #


def _ruta_franjas(marca: str) -> Path:
    """Ruta del fichero lista de franjas de una marca."""
    return carpeta_marca(marca) / "franjas.yaml"


def _leer_franjas_marca(slug: str) -> list[dict[str, Any]]:
    """Lee las franjas de una marca (lista), validando red y dia; degrada con log."""
    marca = _marca_de_slug(slug)
    ruta = raiz_datos() / slug / "franjas.yaml"
    if not ruta.exists():
        return []
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        _log.warning("franjas.yaml invalido, se omite: %s", ruta)
        return []
    if isinstance(datos, dict):
        datos = migrar("franjas", datos)  # upgrade perezoso de esquema (#125)
    crudas = datos.get("franjas") if isinstance(datos, dict) else datos
    if not isinstance(crudas, list):
        return []
    franjas: list[dict[str, Any]] = []
    for cruda in crudas:
        if not isinstance(cruda, dict):
            continue
        red = cruda.get("red", "") or ""
        if red and not redes.es_red(red):
            _log.warning("franja con red invalida %r en %s, se omite", red, ruta)
            continue
        dia = cruda.get("dia_semana", 0)
        if not isinstance(dia, int) or not (0 <= dia <= 6):
            continue
        fid = cruda.get("id")
        if not (isinstance(fid, str) and fid):
            continue
        franjas.append(
            {
                "id": fid,
                "marca": marca,
                "red": red,
                "dia_semana": dia,
                "hora": cruda.get("hora", "") or "",
            }
        )
    return franjas


def listar_franjas() -> list[dict[str, Any]]:
    """Todas las franjas (de todas las marcas), ordenadas por dia/hora/id (determinista)."""
    franjas: list[dict[str, Any]] = []
    for slug in _marcas_en_disco():
        franjas.extend(_leer_franjas_marca(slug))
    franjas.sort(key=lambda f: (f["dia_semana"], f["hora"], f["id"]))
    return franjas


def crear_franja(
    dia_semana: int, hora: str, marca: str = "", red: str = ""
) -> dict[str, Any]:
    """Crea una franja (la anade al `franjas.yaml` de su marca) y la devuelve."""
    franja = {
        "id": _nuevo_id(),
        "marca": marca,
        "red": red,
        "dia_semana": dia_semana,
        "hora": hora,
    }
    slug = _slug_marca(marca)
    existentes = _leer_franjas_marca(slug)
    existentes.append(franja)
    _escribir_franjas_marca(marca, existentes)
    return franja


def _escribir_franjas_marca(marca: str, franjas: list[dict[str, Any]]) -> None:
    """Reescribe el `franjas.yaml` de una marca con la lista dada (sin el campo marca)."""
    cuerpo = {
        "franjas": [
            {"id": f["id"], "red": f["red"], "dia_semana": f["dia_semana"], "hora": f["hora"]}
            for f in franjas
        ]
    }
    _escribir_yaml(_ruta_franjas(marca), cuerpo, tipo="franjas")


def borrar_franja(franja_id: str) -> bool:
    """Borra una franja (la quita del `franjas.yaml` de su marca); True si existia."""
    for slug in _marcas_en_disco():
        marca = _marca_de_slug(slug)
        franjas = _leer_franjas_marca(slug)
        restantes = [f for f in franjas if f["id"] != franja_id]
        if len(restantes) != len(franjas):
            _escribir_franjas_marca(marca, restantes)
            return True
    return False


# --------------------------------------------------------------------------- #
# Plantillas                                                                   #
# --------------------------------------------------------------------------- #


def _parsear_plantilla(datos: dict[str, Any], marca: str, plantilla_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de una plantilla."""
    return {
        "id": plantilla_id,
        "nombre": datos.get("nombre", "") or "",
        "marca": marca,
        "red": datos.get("red", "") or "",
        "contenido": datos.get("contenido", "") or "",
        "fecha": datos.get("fecha", "") or "",
    }


def _guardar_plantilla(plantilla: dict[str, Any]) -> None:
    """Escribe el YAML de una plantilla y la indexa."""
    ruta = _subcarpeta(plantilla["marca"], "plantilla") / f"{plantilla['id']}.yaml"
    cuerpo = {
        "nombre": plantilla["nombre"],
        "red": plantilla["red"],
        "fecha": plantilla["fecha"],
        "fecha_creacion": plantilla.get("fecha_creacion", plantilla["fecha"]),
        "contenido": plantilla["contenido"],
    }
    _escribir_yaml(ruta, cuerpo, tipo="plantilla")
    _indexar("plantilla", plantilla["marca"], ruta, cuerpo)


def listar_plantillas(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Plantillas (mas recientes primero), con paginacion opcional."""
    return _listar_validado(
        "plantilla",
        filtros=None,
        parsear=_parsear_plantilla,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_plantillas() -> int:
    """Total de plantillas (para el `total` de paginacion)."""
    if indice.contar("plantilla", None) == 0 and _rutas_de_tipo("plantilla"):
        _reindexar_tipo("plantilla")
    return indice.contar("plantilla", None)


def obtener_plantilla(plantilla_id: str) -> dict[str, Any] | None:
    """Una plantilla por id (None si no existe)."""
    ruta = _buscar_ruta("plantilla", plantilla_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="plantilla")
    if datos is None:
        return None
    return _parsear_plantilla(datos, _marca_de_slug(ruta.parent.parent.name), plantilla_id)


def crear_plantilla(
    nombre: str, marca: str = "", red: str = "", contenido: str = ""
) -> dict[str, Any]:
    """Crea una plantilla y la devuelve."""
    ahora = _ahora_iso()
    plantilla = {
        "id": _nuevo_id(),
        "nombre": nombre,
        "marca": marca,
        "red": red,
        "contenido": contenido,
        "fecha": date.today().isoformat(),
        "fecha_creacion": ahora,
    }
    _guardar_plantilla(plantilla)
    return {
        "id": plantilla["id"],
        "nombre": nombre,
        "marca": marca,
        "red": red,
        "contenido": contenido,
        "fecha": plantilla["fecha"],
    }


def actualizar_plantilla(
    plantilla_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una plantilla (nombre/marca/red/contenido); None si no existe."""
    ruta = _buscar_ruta("plantilla", plantilla_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="plantilla")
    if datos is None:
        return None
    marca_actual = _marca_de_slug(ruta.parent.parent.name)
    actual = _parsear_plantilla(datos, marca_actual, plantilla_id)
    actual["fecha_creacion"] = datos.get("fecha_creacion", actual["fecha"])

    editables = ("nombre", "marca", "red", "contenido")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return _parsear_plantilla(datos, marca_actual, plantilla_id)
    nueva_marca = cambios.get("marca", marca_actual)
    for k, v in cambios.items():
        actual[k] = v
    actual["marca"] = nueva_marca
    if nueva_marca != marca_actual:
        ruta.unlink(missing_ok=True)
        indice.borrar("plantilla", plantilla_id)
    _guardar_plantilla(actual)
    return {
        "id": plantilla_id,
        "nombre": actual["nombre"],
        "marca": nueva_marca,
        "red": actual["red"],
        "contenido": actual["contenido"],
        "fecha": actual["fecha"],
    }


def borrar_plantilla(plantilla_id: str) -> bool:
    """Borra una plantilla; True si existia, False si no."""
    ruta = _buscar_ruta("plantilla", plantilla_id)
    if ruta is None:
        return False
    ruta.unlink(missing_ok=True)
    indice.borrar("plantilla", plantilla_id)
    return True


# --------------------------------------------------------------------------- #
# Fuentes RSS (+ salud) + items vistos                                         #
# --------------------------------------------------------------------------- #


def _parsear_fuente(datos: dict[str, Any], marca: str, fuente_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de una fuente RSS (`activo` como bool)."""
    return {
        "id": fuente_id,
        "nombre": datos.get("nombre", "") or "",
        "url": datos.get("url", "") or "",
        "marca": marca,
        "fecha": datos.get("fecha", "") or "",
        "activo": bool(datos.get("activo", True)),
        "incluir": datos.get("incluir", "") or "",
        "excluir": datos.get("excluir", "") or "",
        "redes_def": datos.get("redes_def", "") or "",
        "ultima_actualizacion": datos.get("ultima_actualizacion", "") or "",
        "ultimo_error": datos.get("ultimo_error", "") or "",
        "ultimo_conteo": int(datos.get("ultimo_conteo", 0) or 0),
    }


def _guardar_fuente(fuente: dict[str, Any]) -> None:
    """Escribe el YAML de una fuente RSS y la indexa."""
    ruta = _subcarpeta(fuente["marca"], "fuente_rss") / f"{fuente['id']}.yaml"
    cuerpo = {
        "nombre": fuente["nombre"],
        "url": fuente["url"],
        "fecha": fuente["fecha"],
        "fecha_creacion": fuente.get("fecha_creacion", fuente["fecha"]),
        "activo": bool(fuente["activo"]),
        "incluir": fuente["incluir"],
        "excluir": fuente["excluir"],
        "redes_def": fuente["redes_def"],
        "ultima_actualizacion": fuente["ultima_actualizacion"],
        "ultimo_error": fuente["ultimo_error"],
        "ultimo_conteo": int(fuente["ultimo_conteo"]),
    }
    _escribir_yaml(ruta, cuerpo, tipo="fuente_rss")
    _indexar("fuente_rss", fuente["marca"], ruta, cuerpo)


def listar_fuentes_rss(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Fuentes RSS (mas recientes primero), con paginacion opcional."""
    return _listar_validado(
        "fuente_rss",
        filtros=None,
        parsear=_parsear_fuente,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_fuentes_rss() -> int:
    """Total de fuentes RSS (para el `total` de paginacion)."""
    if indice.contar("fuente_rss", None) == 0 and _rutas_de_tipo("fuente_rss"):
        _reindexar_tipo("fuente_rss")
    return indice.contar("fuente_rss", None)


def obtener_fuente_rss(fuente_id: str) -> dict[str, Any] | None:
    """Una fuente RSS por id (None si no existe)."""
    ruta = _buscar_ruta("fuente_rss", fuente_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="fuente_rss")
    if datos is None:
        return None
    return _parsear_fuente(datos, _marca_de_slug(ruta.parent.parent.name), fuente_id)


def crear_fuente_rss(
    nombre: str,
    url: str,
    marca: str = "",
    *,
    incluir: str = "",
    excluir: str = "",
    redes_def: str = "",
) -> dict[str, Any]:
    """Crea una fuente RSS (activa, salud vacia) y la devuelve."""
    fuente = {
        "id": _nuevo_id(),
        "nombre": nombre,
        "url": url,
        "marca": marca,
        "fecha": date.today().isoformat(),
        "fecha_creacion": _ahora_iso(),
        "activo": True,
        "incluir": incluir,
        "excluir": excluir,
        "redes_def": redes_def,
        "ultima_actualizacion": "",
        "ultimo_error": "",
        "ultimo_conteo": 0,
    }
    _guardar_fuente(fuente)
    salida = dict(fuente)
    salida.pop("fecha_creacion", None)
    return salida


def actualizar_fuente_rss(
    fuente_id: str, campos: dict[str, Any]
) -> dict[str, Any] | None:
    """Edita parcialmente una fuente (nombre/url/marca/activo/incluir/excluir/redes_def)."""
    ruta = _buscar_ruta("fuente_rss", fuente_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="fuente_rss")
    if datos is None:
        return None
    marca_actual = _marca_de_slug(ruta.parent.parent.name)
    actual = _parsear_fuente(datos, marca_actual, fuente_id)
    actual["fecha_creacion"] = datos.get("fecha_creacion", actual["fecha"])

    editables = ("nombre", "url", "marca", "activo", "incluir", "excluir", "redes_def")
    cambios = {k: v for k, v in campos.items() if k in editables}
    if not cambios:
        return _parsear_fuente(datos, marca_actual, fuente_id)
    nueva_marca = cambios.get("marca", marca_actual)
    if "activo" in cambios:
        cambios["activo"] = bool(cambios["activo"])
    for k, v in cambios.items():
        actual[k] = v
    actual["marca"] = nueva_marca
    if nueva_marca != marca_actual:
        ruta.unlink(missing_ok=True)
        indice.borrar("fuente_rss", fuente_id)
    _guardar_fuente(actual)
    salida = {k: v for k, v in actual.items() if k != "fecha_creacion"}
    salida["marca"] = nueva_marca
    return salida


def registrar_salud_fuente_rss(fuente_id: str, *, conteo: int, error: str = "") -> None:
    """Anota la salud de una fuente (fecha de hoy + conteo + error). Best-effort."""
    ruta = _buscar_ruta("fuente_rss", fuente_id)
    if ruta is None:
        return
    datos = _leer_yaml(ruta, tipo="fuente_rss")
    if datos is None:
        return
    marca = _marca_de_slug(ruta.parent.parent.name)
    actual = _parsear_fuente(datos, marca, fuente_id)
    actual["fecha_creacion"] = datos.get("fecha_creacion", actual["fecha"])
    actual["ultima_actualizacion"] = date.today().isoformat()
    actual["ultimo_conteo"] = int(conteo)
    actual["ultimo_error"] = error
    _guardar_fuente(actual)


def borrar_fuente_rss(fuente_id: str) -> bool:
    """Borra una fuente RSS y sus items vistos; True si existia, False si no."""
    ruta = _buscar_ruta("fuente_rss", fuente_id)
    if ruta is None:
        return False
    marca = _marca_de_slug(ruta.parent.parent.name)
    ruta.unlink(missing_ok=True)
    indice.borrar("fuente_rss", fuente_id)
    # Limpia los items vistos de esa fuente en su marca.
    vistos = _leer_vistos(marca)
    if fuente_id in vistos:
        vistos.pop(fuente_id, None)
        _escribir_vistos(marca, vistos)
    return True


# --------------------------------------------------------------------------- #
# Items RSS vistos (.keni/rss-vistos.yaml por marca)                           #
# --------------------------------------------------------------------------- #


def _ruta_vistos(marca: str) -> Path:
    """Ruta del fichero de items vistos de una marca."""
    return carpeta_marca(marca) / ".keni" / "rss-vistos.yaml"


def _leer_vistos(marca: str) -> dict[str, list[str]]:
    """Lee el mapa `{fuente_id: [clave, ...]}` de items vistos de una marca."""
    ruta = raiz_datos() / _slug_marca(marca) / ".keni" / "rss-vistos.yaml"
    if not ruta.exists():
        return {}
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    if not isinstance(datos, dict):
        return {}
    datos = migrar("rss_vistos", datos)  # upgrade perezoso de esquema (#125)
    salida: dict[str, list[str]] = {}
    for fid, claves in datos.items():
        if fid == "version":  # clave de control, no es un fuente_id
            continue
        if isinstance(fid, str) and isinstance(claves, list):
            salida[fid] = [c for c in claves if isinstance(c, str)]
    return salida


def _escribir_vistos(marca: str, vistos: dict[str, list[str]]) -> None:
    """Reescribe el fichero de items vistos de una marca (atomico)."""
    _escribir_yaml(
        _ruta_vistos(marca),
        {fid: sorted(set(cl)) for fid, cl in vistos.items()},
        tipo="rss_vistos",
    )


def _marca_de_fuente(fuente_id: str) -> str | None:
    """Marca a la que pertenece una fuente RSS por su id (None si no se localiza)."""
    ruta = _buscar_ruta("fuente_rss", fuente_id)
    if ruta is None:
        return None
    return _marca_de_slug(ruta.parent.parent.name)


def marcar_item(fuente_id: str, clave: str, usado: bool) -> None:
    """Marca/desmarca un item de una fuente como usado (idempotente).

    Los items vistos viven en el `.keni/rss-vistos.yaml` de la MARCA de la fuente.
    Si la fuente ya no existe se cae al fichero de `_MARCA_SIN` (best-effort) para
    no perder la marca, igual que el backend SQLite no exige fuente existente.
    """
    marca = _marca_de_fuente(fuente_id)
    if marca is None:
        marca = ""  # _MARCA_SIN: fuente desconocida (paridad: no requiere existir)
    vistos = _leer_vistos(marca)
    claves = set(vistos.get(fuente_id, []))
    if usado:
        claves.add(clave)
    else:
        claves.discard(clave)
    if claves:
        vistos[fuente_id] = sorted(claves)
    else:
        vistos.pop(fuente_id, None)
    _escribir_vistos(marca, vistos)


def claves_vistas(fuente_id: str) -> set[str]:
    """Conjunto de claves ya marcadas como usadas para una fuente (vacio si ninguna)."""
    marca = _marca_de_fuente(fuente_id)
    if marca is None:
        marca = ""
    return set(_leer_vistos(marca).get(fuente_id, []))


# --------------------------------------------------------------------------- #
# Historial de skills (historial/<YYYY>/<MM>/<id>.yaml)                        #
# --------------------------------------------------------------------------- #


def _parsear_historial(datos: dict[str, Any], marca: str, hid: str) -> dict[str, Any]:
    """Reconstruye el dict publico de una entrada de historial (`piezas` lista, `metricas` dict|None)."""
    piezas = datos.get("piezas")
    if not isinstance(piezas, list):
        piezas = []
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        metricas = None
    return {
        "id": hid,
        "skill": datos.get("skill", "") or "",
        "marca": marca,
        "fecha": datos.get("fecha", "") or "",
        "resultado": datos.get("resultado", "") or "",
        "piezas": [p for p in piezas if isinstance(p, dict)],
        "titulo": datos.get("titulo", "") or "",
        # Atribucion por usuario (#130 Fase 1). Ausente en historial legado => "".
        "autor_id": datos.get("autor_id", "") or "",
        "autor_nombre": datos.get("autor_nombre", "") or "",
        "metricas": metricas,
    }


def registrar_historial_skill(
    skill: str,
    marca: str,
    resultado: str,
    *,
    piezas: list[dict[str, Any]] | None = None,
    titulo: str = "",
    metricas: dict[str, Any] | None = None,
    autor: dict[str, str] | None = None,
) -> str:
    """Guarda una ejecucion de skill (un YAML en `<marca>/historial/<YYYY>/<MM>/`) y devuelve su id.

    `metricas` (tokens/turnos/coste/duracion/modelo del run) se guarda como un mapa en
    el YAML, o se omite si es None. `autor` (atribucion por usuario, #130 Fase 1) es
    `{"id", "usuario"}` o `None`; se persiste (vacio si anonimo / por token).
    """
    autor = autor or {}
    hid = _nuevo_id()
    ahora = datetime.now()
    cuerpo: dict[str, Any] = {
        "skill": skill,
        "fecha": date.today().isoformat(),
        "fecha_creacion": ahora.isoformat(timespec="seconds"),
        "titulo": titulo,
        "autor_id": autor.get("id", "") or "",
        "autor_nombre": autor.get("usuario", "") or "",
        "piezas": [dict(p) for p in (piezas or [])],
        "resultado": resultado,
    }
    if metricas:
        cuerpo["metricas"] = dict(metricas)
    carpeta = carpeta_marca(marca) / "historial" / f"{ahora.year:04d}" / f"{ahora.month:02d}"
    ruta = carpeta / f"{hid}.yaml"
    _escribir_yaml(ruta, cuerpo, tipo="historial_skill")
    _indexar("historial", marca, ruta, cuerpo)
    return hid


def listar_historial_skills(
    *, limite: int | None = None, desplazamiento: int | None = None
) -> list[dict[str, Any]]:
    """Historial (recientes primero por fecha_creacion), con paginacion opcional."""
    return _listar_validado(
        "historial",
        filtros=None,
        parsear=_parsear_historial,
        limite=limite,
        desplazamiento=desplazamiento,
    )


def contar_historial_skills() -> int:
    """Total de entradas de historial (para el `total` de paginacion)."""
    if indice.contar("historial", None) == 0 and _rutas_de_tipo("historial"):
        _reindexar_tipo("historial")
    return indice.contar("historial", None)


def obtener_historial_skill(historial_id: str) -> dict[str, Any] | None:
    """Una entrada del historial por id (None si no existe)."""
    ruta = _buscar_ruta("historial", historial_id)
    if ruta is None:
        return None
    datos = _leer_yaml(ruta, tipo="historial_skill")
    if datos is None:
        return None
    # historial/<YYYY>/<MM>/<id>.yaml -> la marca es 3 niveles arriba del fichero.
    marca = _marca_de_slug(ruta.parent.parent.parent.parent.name)
    return _parsear_historial(datos, marca, historial_id)
