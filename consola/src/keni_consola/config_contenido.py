"""Config — accesores del dominio contenido. Parte de config.py (ver barrel)."""
from __future__ import annotations

from ._config_comun import (
    _FALSOS,
    ENV_COPY_MODELO,
    ENV_DECISOR_MODELO,
    ENV_FUSION_INCREMENTAL,
    ENV_FUSION_MODELO,
    ENV_HASHTAGS_MODELO,
    ENV_INSUMOS_MODELO,
    ENV_SUBTEMA_INCREMENTAL,
    ENV_SUBTEMA_MODELO,
    _crudo,
    os,
)

# --------------------------------------------------------------------------- #
# Accesor: insumos del día                                                     #
# --------------------------------------------------------------------------- #


def insumos_modelo() -> str:
    """Modelo de claude para parsear insumos del día (`KENI_INSUMOS_MODELO`, def "haiku").

    Si la var esta explicitamente vacia (""), devuelve "" -> el llamante NO pasa `--model`
    y claude usa su propio default. Si no esta fijada, devuelve "haiku". Si esta fijada a
    un valor no vacio, devuelve ese valor como nombre de modelo.
    """
    # _crudo() hace strip: si la var es "" o solo espacios, devuelve "".
    # Si la var no esta en el entorno, os.environ.get devuelve None -> _crudo da "".
    # Por eso chequeamos la var cruda del entorno para distinguir "no fijada" de "vacia".
    raw = os.environ.get(ENV_INSUMOS_MODELO)
    if raw is None:
        return "haiku"  # no fijada: default haiku
    return raw.strip()  # fijada: respeta el valor (puede ser "" para desactivar --model)


def fusion_modelo() -> str:
    """Modelo de claude para la FUSIÓN semántica de historias (`KENI_FUSION_MODELO`, def "sonnet").

    La fusión decide qué historias se CORROBORAN entre sí: un grupo equivocado infla
    `n_fuentes`/score y puede auto-producir una pieza con fuentes que no hablan de lo mismo.
    Ese juicio fino ("mismo acontecimiento" vs "mismo tema") se le escapaba a haiku — agrupó
    el show de Shakira con una alerta de la embajada por compartir «Mundial»—, así que la
    fusión usa sonnet por defecto (pocas llamadas por barrido: el coste es menor). Mismas
    semánticas que `insumos_modelo`: "" explícito = sin `--model`.
    """
    raw = os.environ.get(ENV_FUSION_MODELO)
    if raw is None:
        return "sonnet"
    return raw.strip()


def subtema_modelo() -> str:
    """Modelo de claude para Subtema (facetear un macro-evento) (`KENI_SUBTEMA_MODELO`, def "haiku").

    Repartir los ids de una familia por faceta («Partidos», «Espectáculo»…) es una tarea acotada de
    clasificación, no el juicio fino de la fusión PRINCIPAL (que sigue en `fusion_modelo`, sonnet):
    por eso Subtema va con haiku por defecto. Mismas semánticas que `insumos_modelo`: "" explícito =
    sin `--model`.
    """
    raw = os.environ.get(ENV_SUBTEMA_MODELO)
    if raw is None:
        return "haiku"
    return raw.strip()


def fusion_incremental_activo() -> bool:
    """True si Fusionar es DELTA-AWARE: solo dispara con clusters aún no vistos (`KENI_FUSION_INCREMENTAL`).

    Con ON (def) una pasada de fusión solo se encola cuando hay clusters que la fusión no vio aún
    (`fusion_vista` vacía) y el prompt manda las historias NUEVAS completas + lo YA VISTO como
    contexto compacto (familias con etiqueta/representantes/conteo) — evita re-pagar la ventana
    entera cuando casi nada cambió. Con OFF vuelve al camino previo (re-envía el lote completo en
    cada pasada). Idiom default-ON (vacío → True).
    """
    crudo = _crudo(ENV_FUSION_INCREMENTAL).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


def subtema_incremental_activo() -> bool:
    """True si Subtema clasifica SOLO lo nuevo de una familia ya faceteada (`KENI_SUBTEMA_INCREMENTAL`).

    Con ON (def) una familia que ya tiene subtemas asignados y recibe historias nuevas manda a Haiku
    solo esas, con las etiquetas existentes como contexto a reutilizar — evita re-pagar (y
    re-arriesgar) las etiquetas ya estables cada vez que llega una historia más. Con OFF vuelve al
    camino previo (re-envía la familia entera). Idiom default-ON (vacío → True).
    """
    crudo = _crudo(ENV_SUBTEMA_INCREMENTAL).lower()
    if not crudo:
        return True
    return crudo not in _FALSOS


def hashtags_modelo() -> str:
    """Modelo de claude para Sugerir hashtags (`KENI_HASHTAGS_MODELO`, def "haiku").

    Elegir hashtags de la lista fija de candidatos de la marca es una tarea acotada (salida JSON
    cerrada sobre un conjunto dado), no necesita el modelo grande: por eso va con haiku por defecto.
    Mismas semánticas que `insumos_modelo`: "" explícito = sin `--model`.
    """
    raw = os.environ.get(ENV_HASHTAGS_MODELO)
    if raw is None:
        return "haiku"
    return raw.strip()


def copy_modelo() -> str:
    """Modelo de claude para Redactar (copy de producción) (`KENI_COPY_MODELO`, def "sonnet").

    El copy es el mayor consumidor unitario de la máquina: sale con el modelo grande y un copy
    de ~2.000 caracteres. Medido sobre generaciones reales (A/B con input idéntico), sonnet da
    copy de calidad equivalente o mejor que opus a ~mitad de coste de salida, así que el copy
    usa sonnet por defecto en vez del modelo por defecto de la cuenta (opus). Mismas semánticas
    que `insumos_modelo`: "" explícito = sin `--model` (vuelve al default de la cuenta).
    """
    raw = os.environ.get(ENV_COPY_MODELO)
    if raw is None:
        return "sonnet"
    return raw.strip()


def decisor_modelo() -> str:
    """Modelo de claude para el Decisor de formato foto/carrusel (`KENI_DECISOR_MODELO`, def "haiku").

    Decidir el camino sobre señales ligeras (titulares, nº de notas/fuentes) es la tarea más
    acotada del pipeline: salida binaria, contexto mínimo. Por eso va con haiku por defecto.
    Mismas semánticas que `insumos_modelo`: "" explícito = sin `--model`.
    """
    raw = os.environ.get(ENV_DECISOR_MODELO)
    if raw is None:
        return "haiku"
    return raw.strip()
