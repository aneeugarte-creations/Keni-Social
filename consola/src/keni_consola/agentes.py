"""Dominio AGENTES de la Consola Keni: el conjunto ABIERTO de agentes.

La Ola 2a unifico el contenido por MARCA en `<KENI_CONSOLA_RAIZ>/<marca>/`
(publicaciones, plantillas, RSS, hashtags, franjas, historial). Este modulo da el
salto conceptual: la carpeta de cada agente es su espacio de trabajo, con:

  - `CLAUDE.md`              contexto principal del agente (su "memoria").
  - `contexto/<nombre>.md`   sub-contextos opcionales (apuntes adicionales).
  - `runs/<id>.yaml`         ejecuciones de un prompt en esa carpeta.

DOS clases de agente conviven bajo la MISMA raiz:

  - MARCA-AGENTE: las 5 marcas del catalogo unico (`marcas.opciones()`) vienen DE
    SERIE. Su `id` = id de marca; `es_marca=True`; carpeta `<raiz>/<marca-id>/`;
    nombre del catalogo. Producen copy/publicaciones/metricas. NO se borran ni se
    renombran. Se reconocen por `marcas.es_marca(carpeta.name)`.

  - AGENTE GENERICO: se puede CREAR/CONECTAR/RENOMBRAR/BORRAR. Vive en
    `<raiz>/<slug>/` con un MANIFIESTO `.keni/agente.yaml` `{nombre, tipo, creado}`.
    `es_marca=False`; `id` = slug de la CARPETA (estable). Renombrar cambia solo el
    `nombre` (display) del manifiesto, NO el slug/carpeta (para no romper
    referencias). `n_publicaciones=0` (no es una marca).

DESCUBRIMIENTO: la lista de agentes = las 5 marcas ∪ las subcarpetas de `<raiz>`
que tengan `.keni/agente.yaml` y cuyo nombre de carpeta NO sea un id de marca.
Marcas primero (orden del catalogo), luego genericos (recientes primero por
`creado`, luego slug). El `id` de un agente (marca o generico) SIEMPRE resuelve.

LAYOUT (raiz = `KENI_CONSOLA_RAIZ`, def `~/keni-proyectos`; misma que `ficheros.py`):

    <raiz>/<marca|slug>/
        CLAUDE.md
        .keni/agente.yaml          # SOLO genericos: {nombre, tipo, creado}
        contexto/<nombre>.md
        runs/<id>.yaml

SEGURIDAD: todo cae DENTRO de `raiz_permitida()`. El id de una marca se valida
contra el catalogo; el slug de un generico se DERIVA del nombre reutilizando la
validacion anti-escape/caracteres de `api.carpetas` (sin `/`, `\\`, `..`, control,
comodines, ni rutas absolutas) y la ruta resuelta debe quedar estrictamente dentro
de la raiz (`is_relative_to`). Conectar acepta SOLO el nombre de una subcarpeta
existente (anti-traversal). Borrar es SOLO para genericos y SOLO dentro de la raiz
(`rmtree` defensivo). La escritura de CLAUDE.md, sub-contextos, runs y manifiesto es
DEFENSIVA (destino dentro de la carpeta del agente) y ATOMICA (tmp + os.replace)
como en `ficheros.py`/`secretos.py`. Sin shell. Errores en espanol.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from . import ficheros, marcas
from .io_atomico import escribir_atomico

# --------------------------------------------------------------------------- #
# Plantilla de CLAUDE.md por marca (reutiliza las plantillas de api.carpetas)  #
# --------------------------------------------------------------------------- #

# Mapa marca_id -> id de plantilla de `api.carpetas`. Una marca sin entrada cae a
# la plantilla "general". Asi el CLAUDE.md inicial encaja con el tipo de la marca.
_PLANTILLA_POR_MARCA: dict[str, str] = {
    "unotv": "noticias",
    "claro-sports": "deportes",
    "piso-15": "podcast",
    "fundacion": "social",
}
_PLANTILLA_DEF = "general"

# Plantilla por defecto para un agente generico recien creado.
_PLANTILLA_GENERICA_DEF = "general"

# Sub-carpetas dentro de la carpeta del agente.
_DIR_CONTEXTO = "contexto"
_DIR_RUNS = "runs"

# Manifiesto de un agente GENERICO (lo que lo distingue de una carpeta cualquiera).
_DIR_KENI = ".keni"
_ARCHIVO_MANIFIESTO = "agente.yaml"

# Nombre de sub-contexto: base sin separadores/control, terminada en `.md`.
_RE_NOMBRE_CONTEXTO = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 ._-]*[A-Za-z0-9])?$")

# Modos validos de un run.
MODOS_RUN: tuple[str, ...] = ("headless", "interactivo")


class AgenteInvalido(ValueError):
    """El id no resuelve a un agente conocido (marca o generico). Mensaje en espanol."""


class NombreAgenteInvalido(ValueError):
    """El nombre de un agente generico esta vacio o produce un slug no permitido."""


class AgenteExistente(ValueError):
    """El slug derivado choca con una marca o con un agente generico ya registrado."""


class OperacionNoPermitida(ValueError):
    """Operacion no valida sobre el agente (p.ej. renombrar/borrar una marca)."""


class NombreContextoInvalido(ValueError):
    """El nombre de sub-contexto no es valido o escaparia de `contexto/`."""


# --------------------------------------------------------------------------- #
# Localizacion de la carpeta del agente (on-demand, validada contra el catalogo)#
# --------------------------------------------------------------------------- #


def _render_claude_md(marca_id: str) -> str:
    """Renderiza el CLAUDE.md inicial del agente desde su plantilla por tipo.

    Import LOCAL de `api.carpetas` para no crear un ciclo (carpetas no importa este
    modulo, pero el dominio no debe depender del paquete `api` a nivel de modulo).
    """
    from .api import carpetas

    plantilla_id = _PLANTILLA_POR_MARCA.get(marca_id, _PLANTILLA_DEF)
    return carpetas.render_claude_md(plantilla_id, marcas.etiqueta_de(marca_id))


def _raiz() -> Path:
    """Raiz resuelta donde viven TODOS los agentes (misma que `ficheros.raiz_datos`)."""
    return ficheros.raiz_datos().resolve()


def _ruta_dentro_raiz(slug: str) -> Path:
    """Resuelve `<raiz>/<slug>/` garantizando que cae ESTRICTAMENTE dentro de la raiz.

    Lanza `AgenteInvalido` si el slug intentara escapar (un `..`, separador, etc.) o
    si coincidiera con la propia raiz. Esta es la unica forma de construir la carpeta
    de un agente: ni marcas ni genericos esquivan esta comprobacion.
    """
    raiz = _raiz()
    carpeta = (raiz / slug).resolve()
    if carpeta == raiz or not carpeta.is_relative_to(raiz):
        raise AgenteInvalido("Agente no permitido o fuera de la carpeta base.")
    return carpeta


def es_agente(agente_id: object) -> bool:
    """True si `agente_id` resuelve a un agente conocido: una marca O un generico registrado."""
    if not isinstance(agente_id, str) or not agente_id:
        return False
    if marcas.es_marca(agente_id):
        return True
    return agente_id in _slugs_genericos()


def es_generico(agente_id: object) -> bool:
    """True si `agente_id` es un agente GENERICO registrado (tiene manifiesto, no es marca)."""
    if not isinstance(agente_id, str) or not agente_id or marcas.es_marca(agente_id):
        return False
    return agente_id in _slugs_genericos()


def carpeta_agente(agente_id: str, *, crear: bool = True) -> Path:
    """Carpeta `<raiz>/<id>/` de un agente (marca o generico), validada y dentro de la raiz.

    Acepta TANTO un id de marca del catalogo COMO el slug de un agente generico ya
    registrado (con manifiesto `.keni/agente.yaml`). Lanza `AgenteInvalido` si el id
    no resuelve a ninguno de los dos. La carpeta siempre se comprueba dentro de la
    raiz (defensa en profundidad).

    Si `crear` (defecto), crea la carpeta y un `CLAUDE.md` ON-DEMAND si faltan: las
    marcas usan su plantilla por tipo; los genericos NO se siembran aqui (su CLAUDE.md
    y manifiesto los crea `crear_agente`/`conectar_agente`).
    """
    if not isinstance(agente_id, str):
        raise AgenteInvalido("Agente no permitido o inexistente.")
    es_una_marca = marcas.es_marca(agente_id)
    if not es_una_marca and agente_id not in _slugs_genericos():
        raise AgenteInvalido("Agente no permitido o inexistente.")

    carpeta = _ruta_dentro_raiz(agente_id)
    if crear:
        carpeta.mkdir(parents=True, exist_ok=True)
        if es_una_marca:
            claude = carpeta / "CLAUDE.md"
            if not claude.exists():
                claude.write_text(_render_claude_md(agente_id), encoding="utf-8")
    return carpeta


# --------------------------------------------------------------------------- #
# Agentes GENERICOS: slug, manifiesto, descubrimiento y CRUD                   #
# --------------------------------------------------------------------------- #


def _slug_de_nombre(nombre: str) -> str:
    """Deriva un slug de carpeta seguro (slug-guion) desde un nombre humano.

    Normaliza acentos (NFKD -> ASCII), pasa a minusculas, y colapsa cualquier cosa
    que no sea `[a-z0-9]` en guiones (sin guiones al inicio/fin). El slug resultante
    se VALIDA aparte con `carpetas.resolver_destino` (anti-escape/caracteres); aqui
    solo lo construimos. Lanza `NombreAgenteInvalido` si el nombre esta vacio o no
    deja ningun caracter aprovechable.
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreAgenteInvalido("El nombre del agente no puede estar vacío.")
    ascii_txt = unicodedata.normalize("NFKD", crudo).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_txt.lower()).strip("-")
    if not slug:
        raise NombreAgenteInvalido(
            "El nombre del agente no produce un identificador válido (usa letras o dígitos)."
        )
    return slug


def _slug_seguro(nombre: str) -> str:
    """Slug derivado del nombre, ya VALIDADO contra el anti-escape de `api.carpetas`.

    Reutiliza `carpetas.resolver_destino` (la misma validacion que crea carpetas de
    proyecto): el slug debe quedar estrictamente dentro de la raiz, sin `..`, sin
    separadores ni caracteres peligrosos. Traduce el fallo a `NombreAgenteInvalido`.
    """
    from .api import carpetas

    slug = _slug_de_nombre(nombre)
    try:
        carpetas.resolver_destino(slug)
    except carpetas.NombreInvalido as e:  # nombre que escaparia / caracter prohibido
        raise NombreAgenteInvalido(str(e)) from e
    return slug


def _ruta_manifiesto(slug: str) -> Path:
    """Ruta `<raiz>/<slug>/.keni/agente.yaml` (sin crear nada)."""
    return _ruta_dentro_raiz(slug) / _DIR_KENI / _ARCHIVO_MANIFIESTO


def _leer_manifiesto(slug: str) -> dict[str, Any] | None:
    """Lee el manifiesto de un generico, o None si no existe / no valida."""
    try:
        ruta = _ruta_manifiesto(slug)
    except AgenteInvalido:
        return None
    if not ruta.is_file():
        return None
    return _leer_yaml(ruta)


def _escribir_manifiesto(slug: str, nombre: str, tipo: str, creado: str) -> None:
    """Escribe `.keni/agente.yaml` de forma ATOMICA `{nombre, tipo, creado}`."""
    ruta = _ruta_manifiesto(slug)
    _escribir_yaml_atomico(ruta, {"nombre": nombre, "tipo": tipo, "creado": creado})


def _slugs_genericos() -> set[str]:
    """Slugs de las subcarpetas de la raiz que son agentes GENERICOS registrados.

    Un generico = subcarpeta con manifiesto `.keni/agente.yaml` cuyo nombre NO es un
    id de marca (las marcas nunca son genericas, aunque tuvieran ese fichero).
    """
    raiz = _raiz()
    if not raiz.is_dir():
        return set()
    slugs: set[str] = set()
    for hijo in raiz.iterdir():
        if not hijo.is_dir() or marcas.es_marca(hijo.name):
            continue
        if (hijo / _DIR_KENI / _ARCHIVO_MANIFIESTO).is_file():
            slugs.add(hijo.name)
    return slugs


def _agentes_genericos() -> list[dict[str, str]]:
    """Genericos registrados como `[{slug, nombre, tipo, creado}]`, recientes primero.

    Orden: por `creado` desc (recientes primero), luego por slug para ser estable.
    Un manifiesto sin `nombre` cae al propio slug como display.
    """
    salida: list[dict[str, str]] = []
    for slug in _slugs_genericos():
        datos = _leer_manifiesto(slug) or {}
        nombre = datos.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            nombre = slug
        tipo = datos.get("tipo")
        if not isinstance(tipo, str) or not tipo:
            tipo = _PLANTILLA_GENERICA_DEF
        creado = datos.get("creado")
        if not isinstance(creado, str):
            creado = ""
        salida.append({"slug": slug, "nombre": nombre.strip(), "tipo": tipo, "creado": creado})
    salida.sort(key=lambda a: (a["creado"], a["slug"]), reverse=True)
    return salida


def crear_agente(nombre: str, tipo: str = _PLANTILLA_GENERICA_DEF) -> dict[str, Any]:
    """Crea un agente GENERICO nuevo: carpeta + manifiesto + CLAUDE.md desde plantilla.

    Deriva un slug seguro del `nombre` (validado contra el anti-escape de `api.carpetas`),
    crea `<raiz>/<slug>/`, escribe `.keni/agente.yaml` `{nombre, tipo, creado}` y un
    `CLAUDE.md` renderizado con la plantilla `tipo` (def "general"; un tipo desconocido
    cae a "general"). Lanza `NombreAgenteInvalido` si el nombre no produce slug, y
    `AgenteExistente` si el slug choca con una marca o con un generico/carpeta ya
    presente. Devuelve el resumen del agente recien creado.
    """
    slug = _slug_seguro(nombre)
    if marcas.es_marca(slug):
        raise AgenteExistente("Ese nombre coincide con una marca de serie; usa otro.")

    carpeta = _ruta_dentro_raiz(slug)
    if carpeta.exists():
        raise AgenteExistente("Ya existe un agente o carpeta con ese nombre.")

    tipo_final = _tipo_plantilla(tipo)
    nombre_display = nombre.strip()
    carpeta.mkdir(parents=True, exist_ok=False)
    _escribir_texto_atomico(
        carpeta / "CLAUDE.md", _render_claude_md_generico(tipo_final, nombre_display)
    )
    _escribir_manifiesto(slug, nombre_display, tipo_final, ahora_iso())
    return resumen_agente(slug)


def conectar_agente(carpeta_nombre: str) -> dict[str, Any]:
    """Registra una subcarpeta EXISTENTE de la raiz como agente GENERICO.

    `carpeta_nombre` debe ser SOLO el nombre de una subcarpeta directa de la raiz
    (anti-traversal: se rechaza cualquier `/`, `\\`, `..` o ruta). Escribe el
    manifiesto `.keni/agente.yaml` (nombre = el del slug, tipo "general") y un
    `CLAUDE.md` minimo si falta. Lanza `NombreAgenteInvalido` si el nombre escaparia,
    y `AgenteExistente` si no existe bajo la raiz, ya es una marca o ya es un generico.
    Devuelve el resumen del agente conectado.
    """
    crudo = (carpeta_nombre or "").strip()
    if not crudo:
        raise NombreAgenteInvalido("Indica el nombre de la carpeta a conectar.")
    # Solo el NOMBRE de una subcarpeta directa: ni separadores, ni `..`, ni ruta.
    if Path(crudo).name != crudo or crudo in (".", ".."):
        raise NombreAgenteInvalido("Usa solo el nombre de una subcarpeta de la carpeta base.")
    if marcas.es_marca(crudo):
        raise AgenteExistente("Esa carpeta es una marca de serie; ya es un agente.")

    carpeta = _ruta_dentro_raiz(crudo)
    if not carpeta.is_dir():
        raise AgenteExistente("No existe esa carpeta dentro de la carpeta base.")
    if (carpeta / _DIR_KENI / _ARCHIVO_MANIFIESTO).is_file():
        raise AgenteExistente("Esa carpeta ya está conectada como agente.")

    _escribir_manifiesto(crudo, crudo, _PLANTILLA_GENERICA_DEF, ahora_iso())
    claude = carpeta / "CLAUDE.md"
    if not claude.exists():
        _escribir_texto_atomico(
            claude, _render_claude_md_generico(_PLANTILLA_GENERICA_DEF, crudo)
        )
    return resumen_agente(crudo)


def renombrar_agente(agente_id: str, nombre: str) -> dict[str, Any]:
    """Renombra el DISPLAY de un agente GENERICO (actualiza `nombre` del manifiesto).

    NO cambia el slug/carpeta (para no romper referencias): solo el `nombre` legible.
    Lanza `OperacionNoPermitida` si `agente_id` es una marca, `AgenteInvalido` si no
    es un generico registrado, y `NombreAgenteInvalido` si el nombre queda vacio.
    Devuelve el resumen actualizado.
    """
    if marcas.es_marca(agente_id):
        raise OperacionNoPermitida("Las marcas de serie no se pueden renombrar.")
    if agente_id not in _slugs_genericos():
        raise AgenteInvalido("Agente no encontrado.")
    nuevo = (nombre or "").strip()
    if not nuevo:
        raise NombreAgenteInvalido("El nombre del agente no puede estar vacío.")
    actual = _leer_manifiesto(agente_id) or {}
    tipo = actual.get("tipo")
    if not isinstance(tipo, str) or not tipo:
        tipo = _PLANTILLA_GENERICA_DEF
    creado = actual.get("creado")
    if not isinstance(creado, str) or not creado:
        creado = ahora_iso()
    _escribir_manifiesto(agente_id, nuevo, tipo, creado)
    return resumen_agente(agente_id)


def borrar_agente(agente_id: str) -> None:
    """Borra la carpeta de un agente GENERICO (rmtree DENTRO de la raiz, defensivo).

    Lanza `OperacionNoPermitida` si es una marca, y `AgenteInvalido` si no es un
    generico registrado. La carpeta se vuelve a comprobar dentro de la raiz antes de
    borrar (defensa en profundidad: nunca un rmtree fuera de la base).
    """
    if marcas.es_marca(agente_id):
        raise OperacionNoPermitida("Las marcas de serie no se pueden borrar.")
    if agente_id not in _slugs_genericos():
        raise AgenteInvalido("Agente no encontrado.")
    carpeta = _ruta_dentro_raiz(agente_id)
    raiz = _raiz()
    # Defensa en profundidad: solo borramos una subcarpeta REAL dentro de la raiz.
    if carpeta == raiz or not carpeta.is_relative_to(raiz) or not carpeta.is_dir():
        raise AgenteInvalido("Agente no encontrado.")
    shutil.rmtree(carpeta)


def _tipo_plantilla(tipo: object) -> str:
    """Normaliza el `tipo` a un id de plantilla valido de `api.carpetas` (def 'general')."""
    from .api import carpetas

    if isinstance(tipo, str) and tipo in carpetas.PLANTILLAS:
        return tipo
    return _PLANTILLA_GENERICA_DEF


def _render_claude_md_generico(tipo: str, nombre: str) -> str:
    """Renderiza el CLAUDE.md inicial de un generico desde la plantilla `tipo`."""
    from .api import carpetas

    return carpetas.render_claude_md(tipo, nombre)


# --------------------------------------------------------------------------- #
# CLAUDE.md (contexto principal): lectura / escritura defensiva                #
# --------------------------------------------------------------------------- #


def leer_claude_md(marca_id: str) -> str:
    """Contenido del `CLAUDE.md` del agente (creandolo on-demand si falta)."""
    archivo = carpeta_agente(marca_id) / "CLAUDE.md"
    if archivo.is_file():
        return archivo.read_text(encoding="utf-8")
    return ""


def guardar_claude_md(marca_id: str, contenido: str) -> Path:
    """Escribe `<marca>/CLAUDE.md` de forma DEFENSIVA (dentro de la carpeta del agente)."""
    carpeta = carpeta_agente(marca_id)
    destino = (carpeta / "CLAUDE.md").resolve()
    if destino.parent != carpeta:
        raise ValueError("Ruta de destino fuera de la carpeta del agente.")
    _escribir_texto_atomico(destino, contenido)
    return destino


# --------------------------------------------------------------------------- #
# Sub-contextos: `*.md` dentro de `contexto/` (defensivo, anti-traversal)      #
# --------------------------------------------------------------------------- #


def _dir_contexto(marca_id: str) -> Path:
    """Sub-carpeta `contexto/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _sanear_nombre_contexto(nombre: str) -> str:
    """Valida/normaliza el nombre de un sub-contexto y devuelve su nombre de fichero.

    Solo `*.md`: si no trae extension se le anade `.md`; si trae `.md` se respeta.
    El nombre BASE (sin extension) se valida contra `_RE_NOMBRE_CONTEXTO` (letras,
    digitos, espacio, `.`, `_`, `-`, sin empezar/acabar en separador) para impedir
    traversal (`/`, `\\`, `..`), rutas absolutas y caracteres de control. Lanza
    `NombreContextoInvalido` (en espanol) ante cualquier nombre no permitido.
    """
    crudo = (nombre or "").strip()
    if not crudo:
        raise NombreContextoInvalido("El nombre del contexto no puede estar vacío.")
    if crudo.lower().endswith(".md"):
        base = crudo[:-3]
    else:
        base = crudo
    base = base.strip()
    # Rechaza separadores de ruta, `..`, control y nombres que escaparian.
    if not base or base in (".", "..") or not _RE_NOMBRE_CONTEXTO.match(base):
        raise NombreContextoInvalido(
            "El nombre del contexto solo puede tener letras, dígitos, espacios, '.', '_' o '-'."
        )
    return f"{base}.md"


def _resolver_contexto(marca_id: str, nombre: str) -> Path:
    """Ruta de un sub-contexto DENTRO de `contexto/` (defensa anti-traversal)."""
    carpeta = _dir_contexto(marca_id)
    destino = (carpeta / _sanear_nombre_contexto(nombre)).resolve()
    base = carpeta.resolve()
    if destino.parent != base or not destino.is_relative_to(base):
        raise NombreContextoInvalido("El nombre del contexto saldría de la carpeta de contexto.")
    return destino


def listar_contextos(marca_id: str) -> list[dict[str, str]]:
    """Sub-contextos del agente: `[{nombre, contenido}]`, ordenados por nombre."""
    carpeta = carpeta_agente(marca_id) / _DIR_CONTEXTO
    if not carpeta.is_dir():
        return []
    salida: list[dict[str, str]] = []
    for ruta in sorted(carpeta.glob("*.md")):
        if not ruta.is_file():
            continue
        try:
            contenido = ruta.read_text(encoding="utf-8")
        except OSError:
            continue
        salida.append({"nombre": ruta.name, "contenido": contenido})
    return salida


def guardar_contexto(marca_id: str, nombre: str, contenido: str) -> Path:
    """Escribe un sub-contexto `*.md` (saneado) DENTRO de `contexto/` (atomico)."""
    destino = _resolver_contexto(marca_id, nombre)
    _escribir_texto_atomico(destino, contenido)
    return destino


def borrar_contexto(marca_id: str, nombre: str) -> bool:
    """Borra un sub-contexto; True si existia, False si no. Saneado y defensivo."""
    destino = _resolver_contexto(marca_id, nombre)
    if not destino.is_file():
        return False
    destino.unlink(missing_ok=True)
    return True


# --------------------------------------------------------------------------- #
# Runs (ejecuciones de un prompt): `runs/<id>.yaml`                            #
# --------------------------------------------------------------------------- #


def _dir_runs(marca_id: str) -> Path:
    """Sub-carpeta `runs/` del agente (creada si falta)."""
    carpeta = carpeta_agente(marca_id) / _DIR_RUNS
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def nuevo_run_id() -> str:
    """Nuevo id de run (12 hex, mismo formato que `ficheros._nuevo_id`)."""
    return uuid.uuid4().hex[:12]


def ahora_iso() -> str:
    """Fecha-hora ISO a segundos (orden determinista de los runs)."""
    return datetime.now().isoformat(timespec="seconds")


def _metricas_run(datos: dict[str, Any]) -> dict[str, Any] | None:
    """Normaliza el campo `metricas` de un run: dict no vacio o None."""
    metricas = datos.get("metricas")
    if not isinstance(metricas, dict) or not metricas:
        return None
    return metricas


def _parsear_run(datos: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Reconstruye el dict publico de un run (id implicito = nombre de fichero)."""
    return {
        "id": run_id,
        "prompt": datos.get("prompt", "") or "",
        "modo": datos.get("modo", "") or "",
        "estado": datos.get("estado", "") or "",
        "salida": datos.get("salida", "") or "",
        "motivo": datos.get("motivo", "") or "",
        "fecha_inicio": datos.get("fecha_inicio", "") or "",
        "fecha_fin": datos.get("fecha_fin", "") or "",
        "metricas": _metricas_run(datos),
    }


def guardar_run(marca_id: str, run: dict[str, Any]) -> dict[str, Any]:
    """Escribe `runs/<id>.yaml` (atomico) y devuelve el run con su `id`.

    Si el run no trae `id`, se genera uno. El cuerpo YAML no repite el `id` (es
    implicito por el nombre de fichero). `metricas` (tokens/turnos/coste/duracion/
    modelo) se incluye solo si viene presente (None => ausente en el YAML). `motivo`
    (p.ej. "timeout") se incluye solo si trae valor.
    """
    run_id = run.get("id") or nuevo_run_id()
    cuerpo: dict[str, Any] = {
        "prompt": run.get("prompt", "") or "",
        "modo": run.get("modo", "") or "",
        "estado": run.get("estado", "") or "",
        "salida": run.get("salida", "") or "",
        "fecha_inicio": run.get("fecha_inicio", "") or "",
        "fecha_fin": run.get("fecha_fin", "") or "",
    }
    motivo = run.get("motivo", "") or ""
    if motivo:
        cuerpo["motivo"] = motivo
    metricas = _metricas_run(run)
    if metricas is not None:
        cuerpo["metricas"] = metricas
    ruta = _dir_runs(marca_id) / f"{run_id}.yaml"
    _escribir_yaml_atomico(ruta, cuerpo)
    return {"id": run_id, "motivo": motivo, **cuerpo, "metricas": metricas}


def actualizar_run(marca_id: str, run_id: str, cambios: dict[str, Any]) -> dict[str, Any]:
    """Mezcla `cambios` sobre el run `runs/<id>.yaml` existente y lo reescribe ATOMICO.

    Lee el YAML actual (si falta, parte de un cuerpo vacio), aplica los `cambios` por
    clave (sobre `prompt/modo/estado/salida/motivo/fecha_inicio/fecha_fin/metricas`) y
    reescribe via `guardar_run` (que ya escribe de forma atomica). Es la primitiva del
    SONDEO en vivo: el hilo lector la usa para avanzar `estado`/`metricas` parciales y,
    al final, fijar el estado terminal. `metricas` se reemplaza por completo cuando
    viene en `cambios` (parciales o finales); las claves ausentes se conservan.
    """
    ruta = _dir_runs(marca_id) / f"{run_id}.yaml"
    actual = _leer_yaml(ruta) or {}
    fusion: dict[str, Any] = {"id": run_id, **actual, **cambios}
    return guardar_run(marca_id, fusion)


def listar_runs(marca_id: str) -> list[dict[str, Any]]:
    """Runs del agente, recientes primero (por `fecha_inicio` desc, luego id)."""
    carpeta = carpeta_agente(marca_id) / _DIR_RUNS
    if not carpeta.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for ruta in carpeta.glob("*.yaml"):
        if ruta.name.startswith(".tmp-"):
            continue
        datos = _leer_yaml(ruta)
        if datos is None:
            continue
        runs.append(_parsear_run(datos, ruta.stem))
    runs.sort(key=lambda r: (r["fecha_inicio"], r["id"]), reverse=True)
    return runs


def obtener_run(marca_id: str, run_id: str) -> dict[str, Any] | None:
    """Un run del agente por id (None si no existe o su YAML no valida).

    El `run_id` se sanea (solo el `stem`) para impedir traversal por la ruta.
    """
    if not isinstance(run_id, str) or not run_id:
        return None
    # Solo el nombre base: descarta cualquier separador/`..` del id.
    seguro = Path(run_id).name
    if seguro != run_id or seguro in (".", ".."):
        return None
    ruta = (carpeta_agente(marca_id) / _DIR_RUNS / f"{seguro}.yaml").resolve()
    base = (carpeta_agente(marca_id) / _DIR_RUNS).resolve()
    if ruta.parent != base or not ruta.is_file():
        return None
    datos = _leer_yaml(ruta)
    if datos is None:
        return None
    return _parsear_run(datos, seguro)


# --------------------------------------------------------------------------- #
# Resumen de un agente (para el listado / detalle)                            #
# --------------------------------------------------------------------------- #


def _contar(carpeta: Path, patron: str) -> int:
    """Cuenta ficheros que casan un glob dentro de `carpeta` (0 si no existe)."""
    if not carpeta.is_dir():
        return 0
    return sum(1 for _ in carpeta.glob(patron))


def resumen_agente(agente_id: str) -> dict[str, Any]:
    """Resumen ligero de un agente (marca o generico). NO crea la carpeta si no existe.

    Cuenta publicaciones (siempre 0 en genericos: no son marcas) y runs leyendo el
    disco; reporta si el `CLAUDE.md` existe y si `es_marca`. No siembra nada
    (`crear=False`) para que el LISTADO no materialice carpetas.
    """
    carpeta = carpeta_agente(agente_id, crear=False)
    una_marca = marcas.es_marca(agente_id)
    if una_marca:
        nombre = marcas.etiqueta_de(agente_id)
        n_pub = _contar(carpeta / "publicaciones", "*.yaml")
    else:
        manifiesto = _leer_manifiesto(agente_id) or {}
        crudo = manifiesto.get("nombre")
        nombre = crudo.strip() if isinstance(crudo, str) and crudo.strip() else agente_id
        n_pub = 0  # un generico no es una marca: no produce publicaciones
    n_runs = _contar(carpeta / _DIR_RUNS, "*.yaml")
    return {
        "id": agente_id,
        "nombre": nombre,
        "ruta": str(carpeta),
        "es_marca": una_marca,
        "tiene_claude_md": (carpeta / "CLAUDE.md").is_file(),
        "n_publicaciones": n_pub,
        "n_runs": n_runs,
    }


def listar_agentes() -> list[dict[str, Any]]:
    """Todos los agentes: las 5 marcas (orden del catalogo) ∪ los genericos registrados.

    Marcas primero (orden de presentacion del catalogo), luego genericos (recientes
    primero). Cada entrada lleva `es_marca` para que la UI distinga sin adivinar.
    """
    agentes_lista = [resumen_agente(mid) for mid, _etiqueta in marcas.opciones()]
    agentes_lista.extend(resumen_agente(g["slug"]) for g in _agentes_genericos())
    return agentes_lista


# --------------------------------------------------------------------------- #
# Monitorizacion: runs de TODOS los agentes + agregados                       #
# --------------------------------------------------------------------------- #


def _agentes_para_runs() -> list[tuple[str, str]]:
    """Pares `(agente_id, nombre)` de TODOS los agentes (marcas + genericos) para monitor."""
    pares: list[tuple[str, str]] = list(marcas.opciones())
    pares.extend((g["slug"], g["nombre"]) for g in _agentes_genericos())
    return pares


def listar_runs_globales() -> list[dict[str, Any]]:
    """Runs de TODOS los agentes (marcas + genericos), recientes primero.

    Cada run incluye su agente (`agente`/`agente_nombre`) ademas de sus campos. No
    materializa carpetas que no existan. Orden: por `fecha_inicio` desc, luego id.
    """
    todos: list[dict[str, Any]] = []
    for agente_id, nombre in _agentes_para_runs():
        carpeta = carpeta_agente(agente_id, crear=False) / _DIR_RUNS
        if not carpeta.is_dir():
            continue
        for run in listar_runs(agente_id):
            todos.append({**run, "agente": agente_id, "agente_nombre": nombre})
    todos.sort(key=lambda r: (r["fecha_inicio"], r["id"]), reverse=True)
    return todos


def _sumar_metrica(metricas: dict[str, Any] | None, clave: str) -> float:
    """Devuelve `metricas[clave]` como numero (0 si ausente/no numerico/None)."""
    if not isinstance(metricas, dict):
        return 0.0
    valor = metricas.get(clave)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return 0.0
    return float(valor)


def agregados_runs() -> dict[str, Any]:
    """Totales de coste/tokens/runs: global, por agente y por dia.

    - `total`: `{coste_usd, tokens, runs}` sumando TODOS los runs.
    - `por_agente`: una entrada por agente con runs (`{agente, agente_nombre, coste_usd,
      tokens, runs}`), de mayor a menor coste.
    - `por_dia`: una entrada por fecha (YYYY-MM-DD del `fecha_inicio`), recientes primero.
    Tokens = tokens_in + tokens_out de cada run con metricas.
    """
    runs = listar_runs_globales()
    total_coste = 0.0
    total_tokens = 0.0
    por_agente: dict[str, dict[str, Any]] = {}
    por_dia: dict[str, dict[str, Any]] = {}
    for run in runs:
        metricas = run.get("metricas")
        coste = _sumar_metrica(metricas, "total_cost_usd")
        tokens = _sumar_metrica(metricas, "tokens_in") + _sumar_metrica(metricas, "tokens_out")
        total_coste += coste
        total_tokens += tokens

        ag = run["agente"]
        entrada = por_agente.setdefault(
            ag,
            {"agente": ag, "agente_nombre": run["agente_nombre"], "coste_usd": 0.0,
             "tokens": 0, "runs": 0},
        )
        entrada["coste_usd"] += coste
        entrada["tokens"] += int(tokens)
        entrada["runs"] += 1

        dia = (run["fecha_inicio"] or "")[:10]
        dentrada = por_dia.setdefault(
            dia, {"dia": dia, "coste_usd": 0.0, "tokens": 0, "runs": 0}
        )
        dentrada["coste_usd"] += coste
        dentrada["tokens"] += int(tokens)
        dentrada["runs"] += 1

    agentes_lista = sorted(por_agente.values(), key=lambda e: e["coste_usd"], reverse=True)
    dias_lista = sorted(por_dia.values(), key=lambda e: e["dia"], reverse=True)
    return {
        "total": {
            "coste_usd": round(total_coste, 6),
            "tokens": int(total_tokens),
            "runs": len(runs),
        },
        "por_agente": [{**e, "coste_usd": round(e["coste_usd"], 6)} for e in agentes_lista],
        "por_dia": [{**e, "coste_usd": round(e["coste_usd"], 6)} for e in dias_lista],
    }


# --------------------------------------------------------------------------- #
# Escritura atomica (delega en `io_atomico.escribir_atomico`, util comun)      #
# --------------------------------------------------------------------------- #


def _escribir_texto_atomico(ruta: Path, contenido: str) -> None:
    """Escribe texto en `ruta` de forma ATOMICA (tmp en el mismo dir + os.replace)."""
    escribir_atomico(ruta, contenido)


def _escribir_yaml_atomico(ruta: Path, datos: dict[str, Any]) -> None:
    """Escribe un dict como YAML legible de forma ATOMICA (tmp + os.replace)."""
    texto = yaml.safe_dump(
        datos, default_flow_style=False, allow_unicode=True, sort_keys=False, width=4096
    )
    _escribir_texto_atomico(ruta, texto)


def _leer_yaml(ruta: Path) -> dict[str, Any] | None:
    """Lee un YAML como dict, o None si no existe / esta corrupto / no es un mapa."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        datos = yaml.safe_load(texto)
    except yaml.YAMLError:
        return None
    if not isinstance(datos, dict):
        return None
    return datos
