"""Etapa Revisar (calidad del copy) del pipeline: criba ADVISORY antes del avance a revisión.

La criba de la FUENTE (Verificar, pre-redactar, `_qa`) valida la NOTA de origen ANTES de redactar; esta
etapa valida el COPY YA REDACTADO, justo antes de que un borrador completo avance solo a la cola
de revisión (etapa AVANCE, `_avance`). Es la "IA hacia adentro": filtra calidad para que el
humano solo DECIDA, no corrija. Dos chequeos, ambos BARATOS y deterministas (sin `claude -p`):

  - VOZ: contrasta el copy contra los PATRONES medidos de la marca (`patrones_marca`, el MISMO
    lint que `dominio.copy.verificar_voz` corre al generar). Reusa la herramienta existente; aquí
    cubre TODO borrador que llega al avance —también los editados a mano o devueltos—, no solo el
    recién generado. Se lintea con `copy_unico=False`: el borrador ya es el copy FINAL (con los
    hashtags de línea inyectados), no el copy unificado sin hashtags del contrato de generación.
  - COHERENCIA (barata): solapamiento léxico de TÉRMINOS DE CONTENIDO entre el copy y la NOTA de
    origen del tema. Solo AVISA cuando el copy no comparte NINGÚN término de contenido con su nota
    (posible alucinación o pieza pegada al tema equivocado), y solo si ambos textos son lo bastante
    largos para que el contraste signifique algo. CONSERVADOR a propósito: ante la duda, no avisa.

ADVISORY y SAFE-by-default (mismo patrón que `dominio.copy.verificar_voz`): NUNCA bloquea el
avance ni descarta la pieza. Si encuentra avisos, DEGRADA el veredicto del borrador
(`listo`→`revisar`, sólo un pase limpio) y deja una nota en el tema padre; el humano decide en la
revisión con los avisos delante. Gateada por `KENI_PIPELINE_REVISAR` (def OFF): sin el toggle el
avance no cambia ni un byte.

PURO/testeable: `avisos_voz`, `avisos_coherencia` y `avisos_calidad` no tocan BD ni red (el
perfil de patrones se lee de disco, determinista). El único con efectos (degradar + anotar) es
`verificar_calidad_pieza`, que NUNCA lanza.
"""

from __future__ import annotations

from typing import Any

from .. import patrones_marca, repos
from ..dominio import dedup
from ._comun import _log

__all__ = [
    "VEREDICTO_LISTO",
    "VEREDICTO_REVISAR",
    "avisos_voz",
    "avisos_coherencia",
    "avisos_calidad",
    "verificar_calidad_pieza",
]

# Veredictos del copy relevantes para la degradación advisory: un pase LIMPIO ("listo") baja a
# "revisar" si la criba encuentra algo; cualquier otro veredicto ya pide ojos humanos y se respeta.
VEREDICTO_LISTO = "listo"
VEREDICTO_REVISAR = "revisar"

# --- Coherencia copy↔nota (heurística léxica conservadora) ------------------------------- #
# Términos de CONTENIDO = tokens normalizados (sin acentos, alfanuméricos) de longitud >= 4: deja
# fuera la mayoría de artículos/preposiciones ("de","la","el","con") y siglas/números sueltos, así
# el solapamiento refleja entidades y palabras con carga, no relleno gramatical.
_LARGO_TOKEN_CONTENIDO = 4
# Mínimos para que el contraste signifique algo: por debajo, un copy/nota corto comparte poco por
# puro azar y avisar sería ruido. Sólo notas y copys SUSTANCIALES entran al chequeo.
_MIN_TOKENS_COPY = 12
_MIN_TOKENS_NOTA = 20


def _tokens_contenido(texto: str) -> set[str]:
    """Conjunto de TÉRMINOS DE CONTENIDO de un texto (tokens normalizados de >= 4 caracteres)."""
    return {t for t in dedup.clave(texto).split() if len(t) >= _LARGO_TOKEN_CONTENIDO}


def avisos_coherencia(copy_texto: str, nota_origen: str) -> list[str]:
    """Aviso (lista de 0/1) si el copy NO comparte ningún término de contenido con su nota. PURO.

    Conservador: sólo se pronuncia cuando AMBOS textos son sustanciales (≥ mínimos de tokens de
    contenido) y la intersección de términos es VACÍA —señal fuerte de que el copy habla de otra
    cosa que su nota de origen (alucinación o pieza pegada al tema equivocado)—. En cualquier otro
    caso (solapamiento aunque sea de un término, o textos cortos) devuelve [] (no avisa)."""
    if not (copy_texto or "").strip() or not (nota_origen or "").strip():
        return []
    toks_copy = _tokens_contenido(copy_texto)
    toks_nota = _tokens_contenido(nota_origen)
    if len(toks_copy) < _MIN_TOKENS_COPY or len(toks_nota) < _MIN_TOKENS_NOTA:
        return []
    if toks_copy & toks_nota:
        return []
    return [
        "el copy no comparte NINGÚN término con la nota de origen — revisa que hable del mismo "
        "tema (posible información inventada o pieza cruzada con otra noticia)"
    ]


def avisos_voz(marca: str, red: str, copy_texto: str) -> list[str]:
    """Avisos de VOZ del copy contra los patrones medidos de la marca (`patrones_marca`). PURO.

    `copy_unico=False`: el borrador es el copy FINAL (lleva ya los hashtags de línea), no el copy
    unificado sin hashtags del contrato de generación; con `True` se marcaría como aviso cualquier
    hashtag legítimo. Best-effort: un fallo del lint devuelve [] (nunca rompe el avance)."""
    if not marca or not red or not (copy_texto or "").strip():
        return []
    try:
        return patrones_marca.verificar_pieza(marca, red, copy_texto, copy_unico=False)
    except Exception:  # noqa: BLE001 -- el lint es un extra; jamás rompe el avance
        _log.warning("calidad: verificación de voz falló (%s/%s)", marca, red, exc_info=True)
        return []


def avisos_calidad(marca: str, red: str, copy_texto: str, *, nota_origen: str = "") -> list[str]:
    """Todos los avisos de calidad del copy: VOZ + COHERENCIA (si hay nota). PURO."""
    return avisos_voz(marca, red, copy_texto) + avisos_coherencia(copy_texto, nota_origen)


# --- Aplicación ADVISORY sobre el borrador (efectos; nunca lanza) ------------------------- #


def _nota_origen(contenido_id: str) -> str:
    """Nota de origen del tema padre (`contenido.descripcion`) para el chequeo de coherencia.

    Best-effort: "" si no hay tema legible o no trae descripción. Sin nota, la coherencia se
    omite (el chequeo de voz sí corre)."""
    if not contenido_id:
        return ""
    try:
        tema = repos.obtener_contenido(contenido_id)
    except Exception:  # noqa: BLE001 -- sin tema legible, sólo se omite la coherencia
        return ""
    return str((tema or {}).get("descripcion") or "").strip()


def _degradar_veredicto(pub_id: str, veredicto_actual: object) -> None:
    """Baja un veredicto LIMPIO (`listo`) a `revisar`; deja en paz cualquier otro. Best-effort.

    Sólo se toca un pase limpio: un borrador que ya viene `revisar`/`no_publicar`/`no_verificado`
    ya pide ojos humanos, no hay que degradarlo. Un fallo de escritura no rompe el avance (la nota
    en el tema ya deja constancia)."""
    if str(veredicto_actual or "").strip().lower() != VEREDICTO_LISTO:
        return
    try:
        repos.actualizar_publicacion(pub_id, {"veredicto": VEREDICTO_REVISAR})
    except Exception:  # noqa: BLE001 -- la degradación es advisory; la nota ya avisa
        _log.warning("calidad: no se pudo degradar el veredicto de la pieza %s", pub_id, exc_info=True)


def _anotar(avisos: list[str], *, contenido_id: str, marca: str) -> None:
    """Deja rastro de los avisos de calidad: WARN + nota en el tema padre (si lo hay).

    Mismo patrón best-effort que `dominio.copy._avisar_voz`: la nota acompaña a la revisión
    humana, nunca rompe el avance."""
    detalle = "; ".join(avisos)
    _log.warning("calidad: copy fuera de calidad tema=%s marca=%s: %s", contenido_id or "-", marca, detalle)
    if not contenido_id:
        return
    nota = f"⚠ Revisión del copy (voz/coherencia, IA hacia adentro): {detalle}."
    try:
        tema = repos.obtener_contenido(contenido_id)
        if tema is None:
            return
        previas = str(tema.get("notas") or "").strip()
        repos.actualizar_contenido(contenido_id, {"notas": f"{previas}\n{nota}" if previas else nota})
    except Exception:  # noqa: BLE001 -- la nota es un extra; nunca rompe el avance
        _log.warning("calidad: no se pudo anotar el tema %s", contenido_id, exc_info=True)


def verificar_calidad_pieza(pub: dict[str, Any]) -> list[str]:
    """Criba ADVISORY de la CALIDAD del copy de UN borrador antes de su avance a revisión.

    Devuelve los avisos encontrados (vacío = copy dentro de calidad). Con avisos: DEGRADA el
    veredicto del borrador (sólo un `listo` limpio → `revisar`) y deja una nota en el tema padre,
    pero NO bloquea el avance (lo decide el llamante; el humano resuelve en la revisión). NUNCA
    lanza: cualquier fallo se loguea y se trata como "sin avisos" (el avance sigue su curso)."""
    marca = str(pub.get("marca") or "").strip()
    red = str(pub.get("red") or "").strip()
    texto = str(pub.get("contenido") or "")
    pub_id = str(pub.get("id") or "")
    contenido_id = str(pub.get("contenido_id") or "")
    if not marca or not red or not texto.strip() or not pub_id:
        return []
    try:
        avisos = avisos_calidad(marca, red, texto, nota_origen=_nota_origen(contenido_id))
    except Exception:  # noqa: BLE001 -- la criba de calidad jamás rompe el avance
        _log.warning("calidad: criba del copy falló para la pieza %s", pub_id, exc_info=True)
        return []
    if not avisos:
        return []
    _degradar_veredicto(pub_id, pub.get("veredicto"))
    _anotar(avisos, contenido_id=contenido_id, marca=marca)
    return avisos
