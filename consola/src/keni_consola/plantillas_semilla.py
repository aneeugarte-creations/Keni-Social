"""Semilla idempotente de PLANTILLAS DE DISEÑO modernas por marca.

Objetivo: que las marcas que hoy NO tienen plantillas en producción (claro-sports,
fundacion) arranquen con un set de plantillas listas. Las de claro-sports calcan la
ESTRUCTURA real de los posts de feed de Claro Sports (1080×1350), con contenido de
PLACEHOLDER GENÉRICO (no se replica ningún titular, cita, nombre ni foto real; solo la
composición/jerarquía: foto a sangre + degradado de legibilidad + logo wordmark +
crédito de foto + el bloque propio de cada tipo).

UnoTV NO se siembra a propósito: ya tiene sus plantillas en producción y duplicarlas
crearía ruido.

Cada documento se CONSTRUYE a partir de los tokens de marca (`marcas.json`), pasa por
`estudio_imagen.validar_documento` y se persiste con `repos`. La miniatura se deja
vacía ("") a propósito: se regenera al abrir/guardar la plantilla en el estudio. El logo
es un wordmark placeholder: el PNG real lo sube el equipo y sustituye el wordmark. En
"Cita textual", el retrato circular queda vacío (`objeto:""`): la foto del citado la
aporta el equipo en el estudio.

Idempotente CON REFRESCO. La semilla marca lo que crea con autor {"id":"semilla"}. En
cada arranque, por cada (marca, nombre) del catálogo:
  - si existe una plantilla con ese nombre y autor de la semilla ("" o "semilla")
    -> la REFRESCA (reescribe su documento) para que el catálogo mande;
  - si existe con autor del equipo -> NO se toca;
  - si no existe -> se crea.
Además DEPRECA: cualquier plantilla de la semilla (autor "" o "semilla") de una marca
del catálogo cuyo nombre ya no esté en el catálogo se BORRA (limpia plantillas viejas mal
hechas). Nunca se borra lo que hizo el equipo. Best-effort por plantilla; no rompe el
arranque si la BD no está disponible.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from . import repos
from .dominio import estudio_imagen

_log = logging.getLogger(__name__)

# Autor con el que la semilla firma sus plantillas (para reconocerlas y poder refrescarlas
# o deprecarlas sin tocar las del equipo). Las antiguas se crearon con autor vacío ("").
_AUTOR_SEMILLA = {"id": "semilla", "usuario": "Semilla Keni"}
_AUTORES_SEMILLA = {"", "semilla"}  # autor_id que cuenta como "de la semilla"

# Formato base de todas las plantillas (FEED 4:5, espejo de marcas.json -> formatos.feed).
_W, _H = 1080, 1350
_SAFE_TOP, _SAFE_BOTTOM = 60, 96

# Fuentes (catálogo del editor `editor/documento.ts::CATALOGO_FUENTES`). "Antonio"/"Anton"
# es la display condensada; Lato el texto de apoyo.
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


def _capa_degradado(tinta: str, *, alto_frac: float = 0.55, alpha: int = 235) -> dict[str, Any]:
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


def _capa_logo(wordmark: str, acento: str, blanco: str) -> dict[str, Any]:
    """Logo placeholder (wordmark) arriba-izquierda; el PNG real lo sube el equipo (z40)."""
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
        "x": 48, "y": 48, "w": 220, "h": 84,
        "z": 40,
    }


def _capa_credito(blanco: str) -> dict[str, Any]:
    """Crédito de foto fijo y editable, abajo del todo, semitransparente (z30)."""
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
        "alineacion": "izquierda",
        "valign": "centro",
        "opacidad": 0.7,
        "auto_ajuste": {"max_lineas": 1, "tam_min": 16},
        "z": 30,
    }


def _capa_titular(
    *, alineacion: str = "izquierda", tamano: int = 150, max_lineas: int = 3,
    tam_min: int = 80, blanco: str = "#FFFFFF", x: int = 64, y: int = 780,
    w: int = 920, h: int = 440,
) -> dict[str, Any]:
    """Titular (binding copy_in): Anton, mayúsculas, tracking apretado, abajo en la caja (z20)."""
    return {
        "id": "titular",
        "tipo": "texto",
        "x": x, "y": y, "w": w, "h": h,
        "texto": "",
        "binding": "copy_in",
        "familia": _TITULAR,
        "tamano": tamano,
        "peso": 700,
        "color": blanco,
        "alineacion": alineacion,
        "mayusculas": True,
        "interletra": -3,
        "valign": "abajo",
        "auto_ajuste": {"max_lineas": max_lineas, "tam_min": tam_min},
        "sombra": {"dx": 0, "dy": 2, "color": "#000000", "desenfoque": 10, "opacidad": 0.55},
        "z": 20,
    }


def _capa_secundario(
    *, texto: str = "Texto secundario de la nota.", familia: str = _SECUNDARIO,
    blanco: str = "#FFFFFF", x: int = 64, y: int = 1140, w: int = 920, h: int = 120,
    tamano: int = 46, max_lineas: int = 3, mayusculas: bool = False,
) -> dict[str, Any]:
    """Texto secundario (descripción) fijo y editable, debajo del titular (z20)."""
    return {
        "id": "secundario",
        "tipo": "texto",
        "x": x, "y": y, "w": w, "h": h,
        "texto": texto,
        "binding": None,
        "familia": familia,
        "tamano": tamano,
        "peso": 400 if familia == _SECUNDARIO else 700,
        "color": blanco,
        "alineacion": "izquierda",
        "mayusculas": mayusculas,
        "valign": "arriba",
        "auto_ajuste": {"max_lineas": max_lineas, "tam_min": 28},
        "z": 20,
    }


def _capa_chip(
    acento: str, blanco: str, *, x: int = 64, y: int = 700, w: int = 400, h: int = 64,
    tamano: int = 44, radio: int = 0, pad_x: int = 24, pad_y: int = 10,
    texto: str = "", binding: str | None = "etiqueta_default",
) -> dict[str, Any]:
    """Píldora de texto (chip de acento). Por defecto binding etiqueta_default; texto fijo si se pasa (z21)."""
    return {
        "id": "etiqueta",
        "tipo": "texto",
        "x": x, "y": y, "w": w, "h": h,
        "texto": texto,
        "binding": binding,
        "familia": _TITULAR,
        "tamano": tamano,
        "peso": 700,
        "color": blanco,
        "alineacion": "izquierda",
        "mayusculas": True,
        "interletra": 1,
        "valign": "centro",
        "auto_ajuste": {"max_lineas": 1, "tam_min": 24},
        "chip": {"color": acento, "pad_x": pad_x, "pad_y": pad_y, "radio": radio},
        "z": 21,
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


def _capa_acento_esquina(
    acento: str, *, id_: str, x: int, y: int, w: int = 80, h: int = 12,
) -> dict[str, Any]:
    """Pequeño acento de color (marco rect fino) tipo 'esquina' (z25)."""
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


def _base_claro(tokens: dict[str, str]) -> list[dict[str, Any]]:
    """Marco de marca común a los 3 tipos de Claro Sports: foto + degradado + logo + crédito."""
    a, t, b, wm = tokens["acento"], tokens["tinta"], tokens["blanco"], tokens["wordmark"]
    return [
        _capa_foto(),
        _capa_degradado(t, alto_frac=0.55, alpha=235),
        _capa_logo(wm, a, b),
        _capa_credito(b),
    ]


# --------------------------------------------------------------------------- #
# Documentos por plantilla — CLARO SPORTS (estructura real, placeholder genérico)
# --------------------------------------------------------------------------- #


def _doc_cs_titular(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Titular: solo el titular grande sobre la foto. (foto+degradado+logo+crédito + titular)."""
    b = tokens["blanco"]
    capas = _base_claro(tokens)
    capas.append(
        _capa_titular(
            alineacion="izquierda", tamano=150, max_lineas=3, tam_min=80, blanco=b,
            x=64, y=780, w=920, h=440,
        )
    )
    return _envoltura(marca, tokens, capas)


def _doc_cs_breaking(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Breaking: píldora roja "BREAKING" + titular + línea secundaria, todo izquierda y abajo."""
    a, b = tokens["acento"], tokens["blanco"]
    capas = _base_claro(tokens)
    capas += [
        # Píldora roja redondeada FIJA "BREAKING" sobre el titular.
        _capa_chip(
            a, b, x=64, y=700, w=420, h=70, tamano=44, radio=40, pad_x=30, pad_y=14,
            texto="BREAKING", binding=None,
        ),
        # Titular (copy de la pieza), 2 líneas.
        _capa_titular(
            alineacion="izquierda", tamano=130, max_lineas=2, tam_min=80, blanco=b,
            x=64, y=790, w=920, h=300,
        ),
        # Línea secundaria fija editable, en mayúsculas y condensada.
        _capa_secundario(
            texto="Texto secundario de la nota", familia=_TITULAR, blanco=b,
            x=64, y=1130, w=920, h=120, tamano=40, max_lineas=2, mayusculas=True,
        ),
    ]
    return _envoltura(marca, tokens, capas)


def _doc_cs_cita(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Cita textual: retrato circular (la foto la pone el equipo) + aro de acento + cita + atribución."""
    a, b = tokens["acento"], tokens["blanco"]
    capas = _base_claro(tokens)
    capas += [
        # Retrato circular del citado (SEGUNDA capa imagen, NO es el hueco de foto). Vacío: lo
        # rellena el diseñador con el retrato de la persona citada.
        {
            "id": "retrato",
            "tipo": "imagen",
            "x": 720, "y": 330, "w": 300, "h": 300,
            "objeto": "",
            "ajuste": "cover",
            "foco": [0.5, 0.4],
            "forma": "elipse",
            "es_foto": False,
            "z": 25,
        },
        # Aro de acento alrededor del retrato (marco elipse sin relleno, solo borde).
        {
            "id": "aro",
            "tipo": "marco",
            "forma": "elipse",
            "relleno": None,
            "borde": {"color": a, "grosor": 10},
            "x": 712, "y": 322, "w": 316, "h": 316,
            "z": 24,
        },
        # Cita (copy de la pieza). NOTA: el esquema es de un color por capa; no se pueden
        # resaltar palabras sueltas en rojo dentro del mismo texto -> toda la cita en blanco.
        _capa_titular(
            alineacion="izquierda", tamano=72, max_lineas=4, tam_min=40, blanco=b,
            x=64, y=880, w=960, h=300,
        ),
        # Atribución: nombre de la persona, en acento.
        {
            "id": "atribucion",
            "tipo": "texto",
            "x": 64, "y": 1210, "w": 920, "h": 60,
            "texto": "Nombre Apellido",
            "binding": None,
            "familia": _TITULAR,
            "tamano": 44,
            "peso": 700,
            "color": a,
            "alineacion": "izquierda",
            "mayusculas": True,
            "valign": "centro",
            "auto_ajuste": {"max_lineas": 1, "tam_min": 28},
            "z": 20,
        },
        # Cargo / fuente: línea de apoyo en blanco semitransparente.
        {
            "id": "cargo",
            "tipo": "texto",
            "x": 64, "y": 1270, "w": 920, "h": 40,
            "texto": "Cargo · Vía: @fuente",
            "binding": None,
            "familia": _SECUNDARIO,
            "tamano": 24,
            "peso": 400,
            "color": b,
            "alineacion": "izquierda",
            "mayusculas": False,
            "valign": "centro",
            "opacidad": 0.85,
            "auto_ajuste": {"max_lineas": 1, "tam_min": 18},
            "z": 20,
        },
    ]
    return _envoltura(marca, tokens, capas)


def _doc_cs_foto_limpia(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Foto limpia: foto + logo + degradado + crédito; sin titular (la foto manda)."""
    return _envoltura(marca, tokens, _base_claro(tokens))


# --------------------------------------------------------------------------- #
# Documentos por plantilla — FUNDACIÓN (se mantienen; acento ámbar)             #
# --------------------------------------------------------------------------- #


def _doc_fundacion(
    marca: str, tokens: dict[str, str], *, alineacion: str, con_chip: bool = False,
) -> dict[str, Any]:
    """Caso mainstream de Fundación: foto + degradado + pleca + logo + titular + secundario + crédito.

    `con_chip`: añade el chip de etiqueta_default (acento ámbar) sobre el titular.
    """
    a, b = tokens["acento"], tokens["blanco"]
    chip_x = 64
    chip_w = 400 if alineacion != "centro" else 952
    capas: list[dict[str, Any]] = [
        _capa_foto(),
        _capa_degradado(tokens["tinta"], alto_frac=0.5, alpha=220),
        _capa_pleca(a),
        _capa_logo(tokens["wordmark"], a, b),
    ]
    if con_chip:
        capas.append(_capa_chip(a, b, x=chip_x, y=692, w=chip_w, h=60, tamano=38))
    capas += [
        _capa_titular(alineacion=alineacion, blanco=b, y=760, h=360),
        _capa_secundario(blanco=b),
        _capa_credito(b),
    ]
    return _envoltura(marca, tokens, capas)


def _doc_fundacion_foto_limpia(marca: str, tokens: dict[str, str]) -> dict[str, Any]:
    """Foto limpia de Fundación: foto + logo + pleca + chip pequeño; SIN titular grande."""
    a, b = tokens["acento"], tokens["blanco"]
    capas = [
        _capa_foto(),
        _capa_degradado(tokens["tinta"], alto_frac=0.32, alpha=180),
        _capa_pleca(a),
        _capa_logo(tokens["wordmark"], a, b),
        _capa_chip(a, b, x=64, y=1180, w=380, h=60, tamano=38),
        _capa_credito(b),
    ]
    return _envoltura(marca, tokens, capas)


# --------------------------------------------------------------------------- #
# Catálogo de la semilla                                                         #
# --------------------------------------------------------------------------- #

# (marca -> [(nombre, categoria, constructor)]). UnoTV NO se incluye a propósito (ya en producción).
_CATALOGO: dict[str, list[tuple[str, str, Any]]] = {
    "claro-sports": [
        ("Titular", "post", _doc_cs_titular),
        ("Breaking", "post", _doc_cs_breaking),
        ("Cita textual", "post", _doc_cs_cita),
        ("Foto limpia", "post", _doc_cs_foto_limpia),
    ],
    "fundacion": [
        ("Comunidad", "post",
         lambda m, t: _doc_fundacion(m, t, alineacion="centro", con_chip=True)),
        ("Historia", "post",
         lambda m, t: _doc_fundacion(m, t, alineacion="izquierda")),
        ("Foto limpia", "post", _doc_fundacion_foto_limpia),
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


# --------------------------------------------------------------------------- #
# Siembra idempotente con REFRESCO y DEPRECACIÓN                                 #
# --------------------------------------------------------------------------- #


def _es_de_la_semilla(plantilla: dict[str, Any]) -> bool:
    """True si la plantilla la creó la semilla (autor_id vacío o "semilla")."""
    return (plantilla.get("autor_id") or "") in _AUTORES_SEMILLA


def sembrar_plantillas() -> int:
    """Siembra/refresca las plantillas de diseño de la semilla. Devuelve cuántas creó.

    Por cada (marca, nombre) del catálogo:
      - si ya existe y es de la semilla -> REFRESCA su documento (el catálogo manda);
      - si existe con autor del equipo -> la respeta (no la toca);
      - si no existe -> la crea con autor "semilla".
    DEPRECA además: cualquier plantilla de la semilla de una marca del catálogo cuyo
    nombre ya no esté en el catálogo se BORRA. Valida SIEMPRE el documento antes de
    persistir. Tolerante a fallos por plantilla. Pensada para el bootstrap.
    """
    creadas = refrescadas = borradas = omitidas = 0

    # Catálogo por marca para conocer los nombres vigentes (deprecación) y construir docs.
    por_marca: dict[str, dict[str, tuple[str, dict[str, Any]]]] = {}
    for marca, nombre, categoria, documento in documentos_semilla():
        por_marca.setdefault(marca, {})[nombre] = (categoria, documento)

    for marca, plantillas in por_marca.items():
        try:
            existentes = repos.listar_plantillas_diseno(marca=marca)
        except Exception:  # noqa: BLE001 -- sin BD: no sembramos esta marca, pero no rompemos
            _log.warning("semilla plantillas: no se pudo listar %s", marca, exc_info=True)
            continue
        por_nombre: dict[str, dict[str, Any]] = {}
        for p in existentes:
            por_nombre.setdefault(p.get("nombre") or "", p)

        # 1) Crear o refrescar cada plantilla del catálogo.
        for nombre, (categoria, documento) in plantillas.items():
            try:
                normalizado = estudio_imagen.validar_documento(documento)
                doc_json = json.dumps(normalizado, ensure_ascii=False)
                actual = por_nombre.get(nombre)
                if actual is None:
                    repos.crear_plantilla_diseno(
                        marca=marca,
                        nombre=nombre,
                        categoria=categoria,
                        documento=doc_json,
                        miniatura="",  # se regenera al abrir/guardar en el estudio
                        lineas="[]",
                        activo=True,
                        autor=dict(_AUTOR_SEMILLA),
                    )
                    creadas += 1
                elif _es_de_la_semilla(actual):
                    repos.actualizar_plantilla_diseno(actual["id"], {"documento": doc_json})
                    refrescadas += 1
                else:
                    omitidas += 1  # la editó el equipo: intocable
            except Exception:  # noqa: BLE001 -- una plantilla no debe romper el resto
                _log.warning(
                    "semilla plantillas: no se pudo crear/refrescar %s/%s",
                    marca, nombre, exc_info=True,
                )

        # 2) Deprecar plantillas de la semilla cuyo nombre ya no está en el catálogo.
        vigentes = set(plantillas)
        for p in existentes:
            nombre = p.get("nombre") or ""
            if nombre in vigentes or not _es_de_la_semilla(p):
                continue
            try:
                repos.borrar_plantilla_diseno(p["id"])
                borradas += 1
            except Exception:  # noqa: BLE001
                _log.warning(
                    "semilla plantillas: no se pudo borrar la obsoleta %s/%s",
                    marca, nombre, exc_info=True,
                )

    if creadas or refrescadas or borradas:
        _log.info(
            "semilla plantillas: %d creadas, %d refrescadas, %d borradas, %d omitidas (equipo)",
            creadas, refrescadas, borradas, omitidas,
        )
    return creadas
