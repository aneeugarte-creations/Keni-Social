"""Observabilidad de la TUBERIA automatica: en que ETAPA esta cada tema (Fase 2 / Flujo C).

PROBLEMA QUE RESUELVE
=====================
Los daemons (`radar_auto` -> `autogen_copy` -> `autogen_arte` -> revision) llevan cada tema
de "entrada" a "borrador completo en cola de revision", pero hoy NO hay forma de ver EN QUE
PUNTO esta cada pieza a lo largo de la cadena. Este modulo deriva, de las senales que YA
existen (estado de `contenido_plataforma`, presencia de copy/imagen, etiquetas de dedup
`autogen`/`autogen-arte`, origen auto-generable), la ETAPA de cada tema y CUENTA piezas por
etapa para un panel de un vistazo.

DISENO
======
PURO y testeable: `etapa_de_tema` y `contar_por_etapa` reciben dicts ya leidos (items del
tablero + sus filas por plataforma + sus etiquetas resueltas a NOMBRES); no tocan la BD ni
el disco. El que las usa lee `repos.*` y se las pasa. Determinista.

NO reescribe estados ni inventa un enum nuevo en `estados.py` (frontera con la coordinacion):
las etapas son una LECTURA derivada, no un campo persistido. El ciclo de vida real de una
fila sigue siendo `estados.ESTADOS_CONTENIDO_PLATAFORMA`.
"""

from __future__ import annotations

from typing import Any

from .estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN

# Etiquetas de dedup que ponen los daemons al ENCOLAR copy / arte (fuente unica: el valor
# que usan `autogen_copy.ETIQUETA_AUTOGEN` y `autogen_arte.ETIQUETA_AUTOGEN_ARTE`). Se
# replican aqui como literales para no acoplar este modulo neutro a los daemons (que
# importan config/media/etc.); si cambian alla, este modulo no compila menos, solo deja de
# distinguir "en cola" de "generando" (degrada con elegancia, no rompe).
ETIQUETA_AUTOGEN = "autogen"
ETIQUETA_AUTOGEN_ARTE = "autogen-arte"

# Estado terminal del contenido padre: ya no esta "en la tuberia".
_ESTADO_CERRADO = "hecha"

# --------------------------------------------------------------------------- #
# Etapas de la tuberia (orden = avance). Son una LECTURA derivada, no un enum   #
# persistido: NO viven en `estados.py` (no son estados del dominio).            #
# --------------------------------------------------------------------------- #
ETAPA_PRIORIZADA = "priorizada"          # tema auto-generable en cola, sin copy aun
ETAPA_GENERANDO_COPY = "generando_copy"  # copy ya encolado (etiqueta autogen), sin copy listo
ETAPA_GENERANDO_ARTE = "generando_arte"  # tiene copy pero le falta imagen (arte en curso/pendiente)
ETAPA_FALTA_COPY_IN = "falta_copy_in"    # copy + foto pero sin el texto en la imagen (placa)
ETAPA_FALTA_HASHTAGS = "falta_hashtags"  # en revision pero sin hashtags (clave para campanas/lineas)
ETAPA_LISTA_REVISAR = "lista_para_revisar"  # copy + imagen listos / ya en revision o mas alla
ETAPA_FUERA = "fuera_de_tuberia"         # no entra a la auto-generacion (manual tecleado, tarea)

# Orden canonico para presentar los contadores (entrada -> salida -> fuera).
ETAPAS: tuple[str, ...] = (
    ETAPA_PRIORIZADA,
    ETAPA_GENERANDO_COPY,
    ETAPA_GENERANDO_ARTE,
    ETAPA_LISTA_REVISAR,
    ETAPA_FUERA,
)

# Estados de fila por plataforma que YA estan en revision o mas alla: la pieza salio de la
# fase de produccion automatica y vive en el gate humano (cola de revision/aprobacion).
_ESTADOS_EN_REVISION_O_MAS = frozenset(
    {"en_revision", "aprobado", "programado", "publicado"}
)

_ORIGENES_AUTOGEN = frozenset(ORIGENES_AUTOGEN)


def _norm(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _tiene_copy(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma tiene copy redactado (mismo criterio que autogen_arte)."""
    return bool((plataforma.get("copy") or "").strip())


def _tiene_imagen(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma tiene imagen adjunta (media compuesto)."""
    return bool((plataforma.get("imagen") or "").strip())


def _en_revision_o_mas(plataforma: dict[str, Any]) -> bool:
    """True si la fila por plataforma ya esta en revision/aprobado/programado/publicado."""
    return _norm(plataforma.get("estado")) in _ESTADOS_EN_REVISION_O_MAS


def etapa_de_tema(
    item: dict[str, Any],
    plataformas: list[dict[str, Any]],
    *,
    etiquetas: list[str] | None = None,
) -> str:
    """Etapa de la tuberia de UN tema (PURA). `etiquetas` = NOMBRES ya resueltos.

    Reglas, de la SALIDA hacia la ENTRADA (gana la mas avanzada que aplique):
      - clase != 'contenido' (una tarea) o estado padre 'hecha' (cerrado) -> FUERA.
      - origen NO auto-generable (alta tecleada legada `origen=""`, etc.) -> FUERA: la
        auto-generacion no lo toca (lo lleva el equipo a mano).
      - alguna plataforma en revision/aprobado/... O (con copy Y con imagen) -> LISTA_PARA_REVISAR.
      - alguna plataforma con copy pero SIN imagen -> GENERANDO_ARTE.
      - sin copy aun, pero ya etiquetado `autogen` (copy encolado) -> GENERANDO_COPY.
      - sin copy y sin encolar todavia -> PRIORIZADA (en cola de trabajo de la IA).

    Determinista; depende solo de sus argumentos.
    """
    etiquetas = etiquetas or []
    if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
        return ETAPA_FUERA
    if _norm(item.get("estado")) == _ESTADO_CERRADO:
        return ETAPA_FUERA
    if (item.get("origen") or "") not in _ORIGENES_AUTOGEN:
        return ETAPA_FUERA

    # Salida: alguna pieza ya esta en revision o ya tiene copy + imagen (lista para aprobar).
    if any(_en_revision_o_mas(p) for p in plataformas):
        return ETAPA_LISTA_REVISAR
    if any(_tiene_copy(p) and _tiene_imagen(p) for p in plataformas):
        return ETAPA_LISTA_REVISAR

    # Tiene copy en alguna red pero le falta imagen: el arte esta en curso/pendiente.
    if any(_tiene_copy(p) for p in plataformas):
        return ETAPA_GENERANDO_ARTE

    # Sin copy todavia: distinguimos "ya encolado" (etiqueta autogen) de "en cola".
    nombres = {_norm(e) for e in etiquetas}
    if ETIQUETA_AUTOGEN in nombres:
        return ETAPA_GENERANDO_COPY
    return ETAPA_PRIORIZADA


# --------------------------------------------------------------------------- #
# Etapa POR PIEZA (no por tema): la etapa IA de UNA fila por plataforma         #
# (`contenido_plataforma` / publicacion), para el Feed de ideacion (Flujo D).   #
# Es un enum mas RICO que el de tema: el tema solo llega a "lista_para_revisar", #
# pero una pieza concreta avanza por el gate humano (aprobada / programada /    #
# publicada). Misma derivacion que documenta el front (`feed/etapa.ts`); este    #
# modulo es la FUENTE UNICA en backend para no duplicar la heuristica en la UI.  #
# --------------------------------------------------------------------------- #
# Etapas terminales por-pieza, ademas de las tres de produccion de arriba
# (GENERANDO_COPY / GENERANDO_ARTE / LISTA_REVISAR, que se reusan tal cual).
ETAPA_APROBADA = "aprobada"
ETAPA_PROGRAMADA = "programada"
ETAPA_PUBLICADA = "publicada"

# Orden canonico de las etapas IA de una PIEZA (entrada -> salida). Es el contrato
# que consume el feed (`EtapaIa` en `feed/etapa.ts`): mismos literales, mismo orden.
ETAPAS_PIEZA: tuple[str, ...] = (
    ETAPA_GENERANDO_COPY,
    ETAPA_GENERANDO_ARTE,
    ETAPA_FALTA_COPY_IN,
    ETAPA_FALTA_HASHTAGS,
    ETAPA_LISTA_REVISAR,
    ETAPA_APROBADA,
    ETAPA_PROGRAMADA,
    ETAPA_PUBLICADA,
)


def etapa_de_pieza(pieza: dict[str, Any]) -> str:
    """Etapa IA de UNA pieza serializada (publicacion), PURA. Devuelve un literal de `ETAPAS_PIEZA`.

    `pieza` es la forma publica de una publicacion (`publicacion_a_dict`): usa su `estado`
    editorial (`borrador`/`en_revision`/`aprobado`/`programado`/`publicado`) y la checklist
    `falta_copy`/`falta_imagen`/`falta_copy_in`/`falta_hashtags`. ESPEJO de la derivacion del
    front (`etapaDePublicacion` en `feed/etapa.ts`).

    «Revisión» NO es una etapa que se enseñe como tal: es interna y significa "hay que hacer
    algo". Por eso, MIENTRAS la pieza no esté aprobada/programada/publicada, la etapa enseña la
    PRIMERA ACCIÓN PENDIENTE (no un "para revisar" que oculte lo que falta), tanto en borrador
    como en revisión:

      - estado `publicado` / `programado` / `aprobado` -> etapa terminal (ya pasó el gate)
      - falta copy                      -> generando_copy   ("Falta copy")
      - falta el ASSET del formato (foto: `falta_imagen`; vídeo: `falta_video`) -> generando_arte
      - EN REVISIÓN y falta la placa     -> falta_copy_in    ("Falta copy-in")
      - EN REVISIÓN y sin hashtags       -> falta_hashtags   ("Faltan hashtags")
      - nada pendiente                   -> lista_para_revisar (te toca el like/dislike)

    DOS NIVELES de "lo que falta":
      - PRODUCCIÓN (copy + foto): la genera el pipeline y GATEA el avance a revisión. Se exige
        siempre; sin ella la pieza no entra a la cola.
      - REVISIÓN (placa `copy_in` + hashtags): acciones del equipo dentro de la cola. NO bloquean
        el avance —solo se piden YA en revisión—; los hashtags son clave para monitorizar
        campañas y líneas de contenido.

    Backend y front comparten esta misma logica a proposito: el front PREFIERE este
    `etapa_ia` cuando viene y cae a su propia derivacion solo si no llega (degradacion).
    Determinista; depende solo de su argumento.
    """
    estado = _norm(pieza.get("estado"))
    if estado == "publicado":
        return ETAPA_PUBLICADA
    if estado == "programado":
        return ETAPA_PROGRAMADA
    if estado == "aprobado":
        return ETAPA_APROBADA
    if pieza.get("falta_copy", True):
        return ETAPA_GENERANDO_COPY
    # El ASSET que falta depende del formato (espejo del front): una pieza de VÍDEO necesita el
    # vídeo (`falta_video`), no una foto (`falta_imagen` es opcional en vídeo: portada/thumbnail).
    if _norm(pieza.get("formato")) == "video":
        if pieza.get("falta_video", True):
            return ETAPA_GENERANDO_ARTE
    elif pieza.get("falta_imagen", True):
        return ETAPA_GENERANDO_ARTE
    # Acciones de la FASE DE REVISIÓN (placa + hashtags): se piden YA en revisión y no bloquean el
    # avance (en borrador la pieza con copy+foto ya está "lista" y la mueve sola el pipeline).
    if estado == "en_revision":
        if pieza.get("falta_copy_in", False):
            return ETAPA_FALTA_COPY_IN
        if pieza.get("falta_hashtags", False):
            return ETAPA_FALTA_HASHTAGS
    return ETAPA_LISTA_REVISAR


def contar_por_etapa(
    items: list[dict[str, Any]],
    *,
    plataformas_por_item: dict[str, list[dict[str, Any]]] | None = None,
    etiquetas_por_item: dict[str, list[str]] | None = None,
    incluir_fuera: bool = False,
) -> dict[str, int]:
    """Cuenta temas por ETAPA de la tuberia (PURA). Devuelve un dict etapa -> n.

    `plataformas_por_item`: id de contenido -> sus filas `contenido_plataforma`.
    `etiquetas_por_item`:    id de contenido -> NOMBRES de etiqueta resueltos.
    Ambos se inyectan (los lee la capa API), de modo que esta funcion no toca la BD.

    Por defecto NO cuenta los temas FUERA de la tuberia (manual/tarea/cerrado): el panel
    quiere ver el flujo automatico. `incluir_fuera=True` los suma (etapa `fuera_de_tuberia`).
    El dict de salida SIEMPRE trae las etapas relevantes en 0 (forma estable para la UI).
    """
    plataformas_por_item = plataformas_por_item or {}
    etiquetas_por_item = etiquetas_por_item or {}

    etapas_salida = ETAPAS if incluir_fuera else ETAPAS[:-1]
    conteo: dict[str, int] = {e: 0 for e in etapas_salida}
    for item in items:
        cid = item.get("id") or ""
        etapa = etapa_de_tema(
            item,
            plataformas_por_item.get(cid, []),
            etiquetas=etiquetas_por_item.get(cid, []),
        )
        if etapa == ETAPA_FUERA and not incluir_fuera:
            continue
        conteo[etapa] = conteo.get(etapa, 0) + 1
    return conteo
