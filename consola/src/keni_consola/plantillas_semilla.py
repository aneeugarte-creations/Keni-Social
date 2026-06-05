"""Semilla idempotente de PLANTILLAS DE DISEÑO modernas por marca.

Objetivo: que las marcas que hoy NO tienen plantillas en producción (claro-sports,
fundacion) arranquen con un set de plantillas listas, de estilo deportivo/informativo
moderno (sistema del manual de Claro Sports USA): foto a sangre + degradado de
legibilidad + pleca bicolor + logo wordmark (placeholder) + titular Anton apretado +
secundario Lato + chip de etiqueta + crédito de foto.

UnoTV NO se siembra a propósito: ya tiene sus plantillas en producción y duplicarlas
crearía ruido.

Cada documento se CONSTRUYE a partir de los tokens de marca (`marcas.json`), pasa por
`estudio_imagen.validar_documento` y se crea con `repos.crear_plantilla_diseno`. La
miniatura se deja vacía ("") a propósito: se regenera al abrir/guardar la plantilla en
el estudio. El logo es un wordmark placeholder (como `desde_spec`): el PNG real lo sube
el equipo y sustituye el wordmark.

Idempotente: por cada (marca, nombre), si ya existe una plantilla con esa marca+nombre
NO se toca (nunca pisa lo que el equipo edite). Pensada para correr en el bootstrap del
arranque, best-effort (no rompe el arranque si la BD no está disponible).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import repos
from .dominio import estudio_imagen

_log = logging.getLogger(__name__)

# Formato base de todas las plantillas (FEED 4:5, espejo de marcas.json -> formatos.feed).
_W, _H = 1080, 1350
_SAFE_TOP, _SAFE_BOTTOM = 60, 96

# Fuentes (catálogo del editor `editor/documento.ts::CATALOGO_FUENTES`). "Antonio" NO
# existe en el catálogo -> usamos Anton (display condensada) y Lato (texto).
_TITULAR = "Anton"
_SECUNDARIO = "Lato"


# --------------------------------------------------------------------------- #
# Tokens de marca (leídos de marcas.json para no desincronizar)                #
# --------------------------------------------------------------------------- #


def _cargar_marcas() -> dict[str, Any]:
    ruta = Path(__file__).resolve().parent / "motores" / "estudio_imagen" / "marcas.json"
    with ruta.open(encoding="utf-8") as fh:
        return json.load(fh).get("marcas", {})


def _tokens(marca: str) -> dict[str, str]:
    """Tokens de diseño de una marca: acento (rojo/ámbar), tinta, blanco, wordmark, etiqueta."""
    m = _cargar_marcas().get(marca, {})
    return {
        "acento": m.get("rojo", "#CF2E2E"),  # 'rojo' es la clave del acento en marcas.json
        "tinta": m.get("tinta", "#0A0A0A"),
        "blanco": m.get("blanco", "#FFFFFF"),
        "wordmark": m.get("wordmark", m.get("nombre", marca)),
        "etiqueta": m.get("etiqueta_default", "ÚLTIMA HORA"),
    }


# --------------------------------------------------------------------------- #
# Constructores de capas (bloques reutilizables del sistema de diseño)          #
# --------------------------------------------------------------------------- #


def _capa_foto() -> dict[str, Any]:
    """Foto a sangre: el HUECO de foto obligatorio (es_foto), bloqueada, fondo (z0)."""
    return {
        "id": "foto",
        "tipo": "imagen",
        "x": 0, "y": 0, "w": _W, "h": _H,
        "objeto": "",
        "ajuste": "cover",
        "foco": [0.5, 0.45],
        "es_foto": True,
        "bloqueada": True,
        "z": 0,
    }


def _capa_degradado(tinta: str, *, alto_frac: float = 0.5, alpha: int = 220) -> dict[str, Any]:
    """Degradado negro inferior para legibilidad del texto sobre la foto (z10)."""
    return {
        "id": "degradado",
        "tipo": "overlay",
        "x": 0, "y": 0, "w": _W, "h": _H,
        "color": tinta,
        "alto_frac": alto_frac,
        "alpha": alpha,
        "z": 10,
    }


def _capa_pleca(acento: str) -> dict[str, Any]:
    """Pleca de acento: barra vertical fina en el borde superior derecho (z30)."""
    return {
        "id": "pleca",
        "tipo": "marco",
        "forma": "rect",
        "relleno": acento,
        "x": 1052, "y": 0, "w": 28, "h": 150,
        "z": 30,
    }


def _capa_logo(wordmark: str, acento: str, blanco: str) -> dict[str, Any]:
    """Logo placeholder (wordmark) arriba-izquierda; el PNG real lo sube el equipo (z30)."""
    return {
        "id": "logo",
        "tipo": "logo",
        "tipo_logo": "wordmark",
        "media_id": "",
        "wordmark": {
            "texto": wordmark,
            "color": blanco,
            "fondo": acento,
            "familia": _TITULAR,
            "peso": 700,
        },
        "x": 56, "y": 56, "w": 300, "h": 90,
        "z": 30,
    }


def _capa_titular(
    *, alineacion: str = "izquierda", tamano: int = 150, max_lineas: int = 3,
    blanco: str = "#FFFFFF", y: int = 760, h: int = 360,
) -> dict[str, Any]:
    """Titular (binding copy_in): Anton, mayúsculas, tracking apretado, abajo en la caja (z20)."""
    return {
        "id": "titular",
        "tipo": "texto",
        "x": 64, "y": y, "w": 952, "h": h,
        "texto": "",
        "binding": "copy_in",
        "familia": _TITULAR,
        "tamano": tamano,
        "peso": 700,
        "color": blanco,
        "alineacion": alineacion,
        "mayusculas": True,
        "interletra": -4,
        "valign": "abajo",
        "auto_ajuste": {"max_lineas": max_lineas, "tam_min": 70},
        "sombra": {"dx": 0, "dy": 2, "color": "#000000", "desenfoque": 8, "opacidad": 0.6},
        "z": 20,
    }


def _capa_secundario(
    *, alineacion: str = "izquierda", blanco: str = "#FFFFFF", y: int = 1140,
) -> dict[str, Any]:
    """Texto secundario (descripción) fijo y editable: Lato, debajo del titular (z20)."""
    return {
        "id": "secundario",
        "tipo": "texto",
        "x": 64, "y": y, "w": 952, "h": 120,
        "texto": "Texto secundario de la nota.",
        "binding": None,
        "familia": _SECUNDARIO,
        "tamano": 46,
        "peso": 400,
        "color": blanco,
        "alineacion": alineacion,
        "valign": "arriba",
        "auto_ajuste": {"max_lineas": 3, "tam_min": 28},
        "z": 20,
    }


def _capa_chip(
    acento: str, blanco: str, *, alineacion: str = "izquierda", x: int = 64,
    y: int = 700, w: int = 400, h: int = 64, radio: int = 0,
) -> dict[str, Any]:
    """Etiqueta/pleca de texto (binding etiqueta_default) como chip de acento (z20)."""
    return {
        "id": "etiqueta",
        "tipo": "texto",
        "x": x, "y": y, "w": w, "h": h,
        "texto": "",
        "binding": "etiqueta_default",
        "familia": _TITULAR,
        "tamano": 38,
        "peso": 700,
        "color": blanco,
        "alineacion": alineacion,
        "mayusculas": True,
        "interletra": 1,
        "valign": "centro",
        "auto_ajuste": {"max_lineas": 1, "tam_min": 24},
        "chip": {"color": acento, "pad_x": 24, "pad_y": 10, "radio": radio},
        "z": 20,
    }


def _capa_credito(blanco: str, *, alineacion: str = "centro") -> dict[str, Any]:
    """Crédito de foto fijo y editable, abajo del todo, semitransparente (z20)."""
    return {
        "id": "credito",
        "tipo": "texto",
        "x": 64, "y": 1300, "w": 952, "h": 36,
        "texto": "FOTO: AFP",
        "binding": None,
        "familia": _SECUNDARIO,
        "tamano": 22,
        "peso": 400,
        "color": blanco,
        "alineacion": alineacion,
        "valign": "centro",
        "opacidad": 0.7,
        "auto_ajuste": {"max_lineas": 1, "tam_min": 16},
        "z": 20,
    }


def _capa_acento_esquina(
    acento: str, *, id_: str, x: int, y: int, w: int = 80, h: int = 12,
) -> dict[str, Any]:
    """Pequeño acento de color tipo 'esquina' (marco rect fino) para el estilo Breaking (z25)."""
    return {
        "id": id_,
        "tipo": "marco",
        "forma": "rect",
        "relleno": acento,
        "x": x, "y": y, "w": w, "h": h,
        "z": 25,
    }


def _envoltura(marca: str, tokens: dict[str, str], capas: list[dict[str, Any]]) -> dict[str, Any]:
    """Documento completo (formato FEED + fondo tinta + capas)."""
    return {
        "version": 1,
        "marca": marca,
        "fuentes": {"sans": _SECUNDARIO, "condensada": _TITULAR},
        "formato": {
            "w": _W, "h": _H,
            "safe_top": _SAFE_TOP, "safe_bottom": _SAFE_BOTTOM,
        },
        "fondo": {"tipo": "color", "color": tokens["tinta"]},
        "capas": capas,
    }


# --------------------------------------------------------------------------- #
# Documentos por plantilla                                                      #
# --------------------------------------------------------------------------- #


def _doc_galeria_informativa(
    marca: str, tokens: dict[str, str], *, alineacion: str, con_chip: bool = False,
) -> dict[str, Any]:
    """Caso mainstream: foto a sangre + degradado + pleca + logo + titular + secundario + crédito.

    `con_chip`: añade el chip de etiqueta_default (acento) sobre el titular (p.ej. "COMUNIDAD").
    """
    a, t, b, wm = tokens["acento"], tokens["tinta"], tokens["blanco"], tokens["wordmark"]
    # El chip va alineado igual que el titular (izquierda o centrado). Para centro, lo
    # extendemos a todo el ancho de la caja para que el texto quede centrado dentro.
    chip_x = 64 if alineacion != "centro" else 64
    chip_w = 400 if alineacion != "centro" else 952
    capas = [
        _capa_foto(),
        _capa_degradado(t),
        _capa_pleca(a),
        _capa_logo(wm, a, b),
    ]
    if con_chip:
        capas.append(_capa_chip(a, b, alineacion=alineacion, x=chip_x, y=692, w=chip_w, h=60))
    capas += [
        _capa_titular(alineacion=alineacion, blanco=b),
        _capa_secundario(alineacion=alineacion, blanco=b),
        _capa_credito(b),
    ]
    return _envoltura(marca, tokens, capas)


def _doc_breaking(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Breaking: chip de etiqueta arriba + titular MUY grande + 2 acentos de esquina."""
    a, t, b, wm = tokens["acento"], tokens["tinta"], tokens["blanco"], tokens["wordmark"]
    capas = [
        _capa_foto(),
        _capa_degradado(t, alto_frac=0.55, alpha=230),
        _capa_pleca(a),
        _capa_logo(wm, a, b),
        _capa_chip(a, b, alineacion="izquierda", x=64, y=686, w=460, h=64),
        _capa_titular(alineacion="izquierda", tamano=230, max_lineas=2, blanco=b, y=770, h=380),
        _capa_acento_esquina(a, id_="acento_sup", x=64, y=666, w=120, h=10),
        _capa_acento_esquina(a, id_="acento_inf", x=896, y=1166, w=120, h=10),
        _capa_credito(b),
    ]
    return _envoltura(marca, tokens, capas)


def _doc_foto_limpia(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Foto limpia: foto + logo + pleca + chip pequeño de etiqueta; SIN titular grande."""
    a, t, b, wm = tokens["acento"], tokens["tinta"], tokens["blanco"], tokens["wordmark"]
    capas = [
        _capa_foto(),
        _capa_degradado(t, alto_frac=0.32, alpha=180),
        _capa_pleca(a),
        _capa_logo(wm, a, b),
        _capa_chip(a, b, alineacion="izquierda", x=64, y=1180, w=380, h=60),
        _capa_credito(b),
    ]
    return _envoltura(marca, tokens, capas)


# --------------------------------------------------------------------------- #
# Catálogo de la semilla                                                         #
# --------------------------------------------------------------------------- #

# (marca -> [(nombre, categoria, constructor)]). UnoTV NO se incluye a propósito (ya en producción).
_CATALOGO: dict[str, list[tuple[str, str, Any]]] = {
    "claro-sports": [
        ("Galería informativa", "post",
         lambda m, t: _doc_galeria_informativa(m, t, alineacion="izquierda")),
        ("Galería informativa · centro", "post",
         lambda m, t: _doc_galeria_informativa(m, t, alineacion="centro")),
        ("Breaking", "post", _doc_breaking),
        ("Foto limpia", "post", _doc_foto_limpia),
    ],
    "fundacion": [
        ("Comunidad", "post",
         lambda m, t: _doc_galeria_informativa(m, t, alineacion="centro", con_chip=True)),
        ("Historia", "post",
         lambda m, t: _doc_galeria_informativa(m, t, alineacion="izquierda")),
        ("Foto limpia", "post", _doc_foto_limpia),
    ],
}


def documentos_semilla() -> list[tuple[str, str, str, dict[str, Any]]]:
    """Catálogo de la semilla como (marca, nombre, categoria, documento_dict).

    Construye cada documento a partir de los tokens de marca. Testeable SIN BD: cada
    documento puede pasarse por `estudio_imagen.validar_documento`.
    """
    out: list[tuple[str, str, str, dict[str, Any]]] = []
    for marca, plantillas in _CATALOGO.items():
        tokens = _tokens(marca)
        for nombre, categoria, constructor in plantillas:
            out.append((marca, nombre, categoria, constructor(marca, tokens)))
    return out


def sembrar_plantillas() -> int:
    """Siembra las plantillas de diseño de la semilla. Devuelve cuántas creó.

    Idempotente: por cada (marca, nombre), si ya existe una plantilla con esa marca+nombre
    NO se crea (nunca pisa lo que el equipo edite). Valida el documento antes de persistir.
    Tolerante a fallos por plantilla (no aborta el resto). Pensada para el bootstrap.
    """
    creadas = 0
    for marca, nombre, categoria, documento in documentos_semilla():
        try:
            existentes = repos.listar_plantillas_diseno(marca=marca)
            if any((p.get("nombre") or "") == nombre for p in existentes):
                continue
            # Valida (y normaliza) el documento antes de persistir: no guardamos JSON inválido.
            normalizado = estudio_imagen.validar_documento(documento)
            repos.crear_plantilla_diseno(
                marca=marca,
                nombre=nombre,
                categoria=categoria,
                documento=json.dumps(normalizado, ensure_ascii=False),
                miniatura="",  # se regenera al abrir/guardar en el estudio
                lineas="[]",
                activo=True,
                autor=None,
            )
            creadas += 1
        except Exception:  # noqa: BLE001 -- una plantilla no debe romper el resto
            _log.warning("semilla plantillas: no se pudo crear %s/%s", marca, nombre, exc_info=True)
    if creadas:
        _log.info("semilla plantillas: %d plantillas de diseño creadas", creadas)
    return creadas
