"""Identidad de AGENTE y agentes GENERICOS: slug, manifiesto, descubrimiento y CRUD.

Cubre la resolucion de un agente (marca o generico) a su carpeta, el ciclo de vida de
los agentes GENERICOS (`.keni/agente.yaml`) y la enumeracion de TODOS los agentes:

  - Resolucion/validacion: `es_agente`, `es_generico`, `carpeta_agente`.
  - Slug/manifiesto: `_slug_de_nombre`, `_slug_seguro`, `_ruta_manifiesto`,
    `_leer_manifiesto`, `_escribir_manifiesto`.
  - Descubrimiento: `_slugs_genericos`, `_agentes_genericos`.
  - CRUD: `crear_agente`, `conectar_agente`, `renombrar_agente`, `borrar_agente`.
  - Resumen/listado: `_contar`, `resumen_agente`, `listar_agentes`.
  - Enumeracion para monitor: `_agentes_para_runs`, `_mapa_nombres_agentes`.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any

from keni_shared import marcas

from ._comun import (
    _ARCHIVO_MANIFIESTO,
    _DIR_KENI,
    _DIR_RUNS,
    _PLANTILLA_GENERICA_DEF,
    AgenteExistente,
    AgenteInvalido,
    NombreAgenteInvalido,
    OperacionNoPermitida,
    _escribir_texto_atomico,
    _escribir_yaml_atomico,
    _leer_yaml,
    _raiz,
    _render_claude_md,
    _render_claude_md_generico,
    _ruta_dentro_raiz,
    _tipo_plantilla,
    ahora_iso,
)
from ._rutas import resolver_slug_agente

__all__ = [
    "es_agente",
    "es_generico",
    "carpeta_agente",
    "_slug_de_nombre",
    "_slug_seguro",
    "_ruta_manifiesto",
    "_leer_manifiesto",
    "_escribir_manifiesto",
    "_slugs_genericos",
    "_agentes_genericos",
    "crear_agente",
    "conectar_agente",
    "renombrar_agente",
    "borrar_agente",
    "_contar",
    "resumen_agente",
    "listar_agentes",
    "_agentes_para_runs",
    "_mapa_nombres_agentes",
]


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
    marcas usan su plantilla por tipo; los genericos NO se inicializan aqui (su CLAUDE.md
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
                _escribir_texto_atomico(claude, _render_claude_md(agente_id))
    return carpeta


# --------------------------------------------------------------------------- #
# Agentes GENERICOS: slug, manifiesto, descubrimiento y CRUD                   #
# --------------------------------------------------------------------------- #


def _slug_de_nombre(nombre: str) -> str:
    """Deriva un slug de carpeta seguro (slug-guion) desde un nombre humano.

    Normaliza acentos (NFKD -> ASCII), pasa a minusculas, y colapsa cualquier cosa
    que no sea `[a-z0-9]` en guiones (sin guiones al inicio/fin). El slug resultante
    se VALIDA aparte con `resolver_slug_agente` (anti-escape/caracteres); aqui solo lo
    construimos. Lanza `NombreAgenteInvalido` si el nombre esta vacio o no deja ningun
    caracter aprovechable.
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
    """Slug derivado del nombre, ya VALIDADO contra el anti-escape de agentes.

    `resolver_slug_agente` exige que el slug quede estrictamente dentro de la raiz, sin
    `..`, sin separadores ni caracteres peligrosos. Lanza `NombreAgenteInvalido` si el
    nombre escaparia o trae un caracter prohibido.
    """
    slug = _slug_de_nombre(nombre)
    resolver_slug_agente(slug, _raiz())
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
    return _leer_yaml(ruta, tipo="agente")


def _escribir_manifiesto(slug: str, nombre: str, tipo: str, creado: str) -> None:
    """Escribe `.keni/agente.yaml` de forma ATOMICA `{nombre, tipo, creado}`."""
    ruta = _ruta_manifiesto(slug)
    _escribir_yaml_atomico(
        ruta, {"nombre": nombre, "tipo": tipo, "creado": creado}, tipo="agente"
    )


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
    # Los runs del agente borrado salen del disco: reindexamos para que el indice (y
    # por tanto los agregados del monitor) no conserve filas sueltas de coste/tokens.
    # Import LOCAL: `_runs` depende de este modulo, evitamos el ciclo a nivel de import.
    from . import _runs

    _runs.reindexar_runs()


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

    Cuenta piezas (siempre 0 en genericos: no son marcas) y runs leyendo el
    disco; reporta si el `CLAUDE.md` existe y si `es_marca`. No inicializa nada
    (`crear=False`) para que el LISTADO no materialice carpetas.
    """
    carpeta = carpeta_agente(agente_id, crear=False)
    una_marca = marcas.es_marca(agente_id)
    if una_marca:
        nombre = marcas.etiqueta_de(agente_id)
        n_pub = _contar(carpeta / "piezas", "*.yaml")
    else:
        manifiesto = _leer_manifiesto(agente_id) or {}
        crudo = manifiesto.get("nombre")
        nombre = crudo.strip() if isinstance(crudo, str) and crudo.strip() else agente_id
        n_pub = 0  # un generico no es una marca: no produce piezas
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
# Enumeracion de TODOS los agentes (marcas + genericos) para el monitor        #
# --------------------------------------------------------------------------- #


def _agentes_para_runs() -> list[tuple[str, str]]:
    """Pares `(agente_id, nombre)` de TODOS los agentes (marcas + genericos) para monitor."""
    pares: list[tuple[str, str]] = list(marcas.opciones())
    pares.extend((g["slug"], g["nombre"]) for g in _agentes_genericos())
    return pares


def _mapa_nombres_agentes() -> dict[str, str]:
    """Mapa `agente_id -> nombre legible` (marcas + genericos) para enriquecer runs."""
    return {agente_id: nombre for agente_id, nombre in _agentes_para_runs()}
