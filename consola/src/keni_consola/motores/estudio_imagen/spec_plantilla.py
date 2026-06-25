"""Esquema del SPEC de plantilla de marca: capas por formato, fuente de verdad del render.

Una "plantilla" pasa de ser campos planos (color, logo + 1 de 4 esquinas, pleca...) a un SPEC
de CAPAS por formato (9:16 / 4:5 / 1:1 / 16:9) que el equipo diseña visualmente y que TANTO el editor
(navegador, react-konva) COMO el servidor (Node + node-canvas) renderizan idéntico. Este módulo
es el contrato canónico: define el esquema, lo valida y deriva un spec por defecto desde los
campos planos actuales (continuidad visual sin migración explícita).

Coordenadas: píxeles sobre el lienzo de cada formato (1080×1920 / 1080×1350 / 1080×1080 / 1600×900).

Capas por formato:
  - `fondo`: relleno base detrás de la foto (`color` | `degradado` | `imagen`).
  - `foto_slot`: hueco donde entra la foto subida (x,y,w,h + ajuste cover/contain + foco).
  - `overlay_inferior`: degradado oscuro de legibilidad (opcional) sobre la foto.
  - `logo`: imagen (media_id) o wordmark de texto; x,y,w,h libres.
  - `textos[]`: 1–3 bloques (titular/pleca/kicker) con binding a datos (copy_in / etiqueta_default).

NO depende de Pillow ni de red: solo dicts. El renderer (Node) y el editor (TS) consumen el
mismo JSON. Los mensajes de error salen en español (la API los devuelve como 400).
"""

from __future__ import annotations

import math
from typing import Any

# Versión del esquema (para migraciones futuras vía `migrar`).
VERSION = 1

# Geometría base de cada formato (espejo de `marcas.json:formatos`). El spec la incrusta por
# formato para que editor y servidor compartan exactamente el lienzo y las zonas seguras.
FORMATOS: dict[str, dict[str, int]] = {
    "vertical": {"w": 1080, "h": 1920, "safe_top": 220, "safe_bottom": 420},
    "feed": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
    "cuadrado": {"w": 1080, "h": 1080, "safe_top": 60, "safe_bottom": 96},
    # 16:9 (lienzo de X y de web/YouTube). Medidas 1600×900 espejo de `formatos_red`
    # (la matriz red→lienzo declara el 16:9 a 1600×900). Es ancho y bajo, así que las
    # zonas seguras arriba/abajo son pequeñas (como feed); el ancho da sitio al titular.
    "horizontal": {"w": 1600, "h": 900, "safe_top": 56, "safe_bottom": 72},
}

# Familias lógicas de fuente -> el renderer y el editor las resuelven a su archivo embebido.
# Familias lógicas antiguas (compat) + catálogo de fuentes embebidas reales (las que ofrece el
# editor). `familia` de una capa puede ser una lógica o un nombre del catálogo; el renderer las
# resuelve (fuentes.mjs::familiaReal). Validación tolerante: cualquier str no vacío vale.
FAMILIAS = ("sans", "condensada")
CATALOGO_FUENTES = (
    "Barlow", "Barlow Condensed", "Anton", "Oswald", "Montserrat", "Archivo Black", "Lora",
    "Exo 2", "Lato", "Poppins", "Roboto Condensed", "Mulish", "Nunito Sans", "Jost",
)

_AJUSTES = ("cover", "contain")
_ALINEACIONES = ("izquierda", "centro", "derecha", "justificado")
_TIPOS_FONDO = ("color", "degradado", "imagen")
_TIPOS_LOGO = ("imagen", "wordmark")
_BINDINGS = ("copy_in", "etiqueta_default", None)
# Ids de bloque de texto admitidos (1–3 bloques por formato).
_IDS_TEXTO = ("titular", "pleca", "kicker")

# Constantes geométricas que hoy viven en `componer.py` (para reproducir el layout actual).
_MARGEN = 56
_LOGO_ALTO = 96
_DEGRADADO_ALTO_FRAC = 0.58
_DEGRADADO_ALPHA = 238
_TITULAR_MAX_ALTO_FRAC = 0.42
_PLECA_TAM = 36
_CHIP_PAD_X = 24
_CHIP_PAD_Y = 14


class SpecError(ValueError):
    """Error de validación del spec de plantilla, con mensaje en español para la UI."""


# --------------------------------------------------------------------------- #
# Validación                                                                   #
# --------------------------------------------------------------------------- #


def _es_hex(v: Any) -> bool:
    # Acepta #RRGGBB (opaco) y #RRGGBBAA (con canal alfa, para transparencias y degradados a
    # transparente). El canvas (navegador y @napi-rs/canvas) entiende ambos como fillStyle.
    return isinstance(v, str) and len(v) in (7, 9) and v[0] == "#" and all(
        c in "0123456789abcdefABCDEF" for c in v[1:]
    )


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _exige(cond: bool, msg: str) -> None:
    if not cond:
        raise SpecError(msg)


def _entero(valor: Any, campo: str, minimo: int | None = None, maximo: int | None = None, defecto: int = 0) -> int:
    """Convierte un valor a entero o lanza `SpecError` (español) si no es un número válido.

    Blinda la entrada del editor: un valor no numérico devuelve 400 (SpecError), no un 500 por
    `ValueError` crudo. Valida rango [minimo, maximo] si se especifican.
    """
    if valor is None or valor == "":
        return defecto
    # Solo el CAST va en el try: `SpecError` hereda de `ValueError`, así que las comprobaciones de
    # rango van fuera para no recazarlas como "número válido" y perder su mensaje de límite.
    try:
        num = int(valor)
    except (ValueError, TypeError, OverflowError):
        raise SpecError(f"'{campo}' debe ser un número entero válido.")
    if minimo is not None and num < minimo:
        raise SpecError(f"'{campo}' no puede ser menor a {minimo}.")
    if maximo is not None and num > maximo:
        raise SpecError(f"'{campo}' no puede ser mayor a {maximo}.")
    return num


def _flotante(valor: Any, campo: str, minimo: float | None = None, maximo: float | None = None, defecto: float = 0.0) -> float:
    """Convierte un valor a flotante o lanza `SpecError` (español) si no es un número válido."""
    if valor is None or valor == "":
        return defecto
    try:
        num = float(valor)
    except (ValueError, TypeError, OverflowError):
        raise SpecError(f"'{campo}' debe ser un número válido.")
    if not math.isfinite(num):
        raise SpecError(f"'{campo}' debe ser un número válido.")
    if minimo is not None and num < minimo:
        raise SpecError(f"'{campo}' no puede ser menor a {minimo}.")
    if maximo is not None and num > maximo:
        raise SpecError(f"'{campo}' no puede ser mayor a {maximo}.")
    return num


def _validar_fondo(fondo: Any) -> dict[str, Any]:
    _exige(isinstance(fondo, dict), "El fondo debe ser un objeto.")
    tipo = fondo.get("tipo")
    _exige(tipo in _TIPOS_FONDO, "El tipo de fondo debe ser color, degradado o imagen.")
    limpio: dict[str, Any] = {"tipo": tipo}
    if tipo == "color":
        _exige(_es_hex(fondo.get("color")), "El color de fondo debe ser hex #RRGGBB.")
        limpio["color"] = fondo["color"]
    elif tipo == "degradado":
        g = fondo.get("degradado") or {}
        _exige(_es_hex(g.get("desde")) and _es_hex(g.get("hasta")),
               "El degradado de fondo necesita colores 'desde' y 'hasta' hex.")
        deg = {
            "desde": g["desde"], "hasta": g["hasta"],
            "angulo": _flotante(g.get("angulo", 180), "fondo.degradado.angulo", defecto=180.0),
        }
        # `tipo` (lineal/radial) y `stops` (multi-parada) son aditivos y retrocompatibles: solo se
        # persisten si se apartan del default lineal 2-stop, para no ensuciar specs viejos.
        if g.get("tipo") == "radial":
            deg["tipo"] = "radial"
        raw_stops = g.get("stops")
        if isinstance(raw_stops, list):
            stops = []
            for s in raw_stops:
                if isinstance(s, dict) and _es_hex(s.get("color")):
                    pos = s.get("pos", 0)
                    stops.append({
                        "pos": min(1.0, max(0.0, float(pos) if _num(pos) else 0.0)),
                        "color": s["color"],
                    })
            if len(stops) >= 2:
                deg["stops"] = sorted(stops, key=lambda s: s["pos"])
        limpio["degradado"] = deg
    else:  # imagen
        img = fondo.get("imagen") or {}
        limpio["imagen"] = {
            "media_id": str(img.get("media_id", "")),
            "ajuste": img.get("ajuste") if img.get("ajuste") in _AJUSTES else "cover",
        }
    return limpio


def _validar_caja(c: Any, ctx: str) -> dict[str, float]:
    _exige(isinstance(c, dict), f"{ctx} debe ser un objeto con x,y,w,h.")
    for k in ("x", "y", "w", "h"):
        _exige(_num(c.get(k)), f"{ctx}: '{k}' debe ser numérico.")
    return {k: float(c[k]) for k in ("x", "y", "w", "h")}


def _validar_foto_slot(s: Any) -> dict[str, Any]:
    caja = _validar_caja(s, "El hueco de foto")
    foco = s.get("foco") or [0.5, 0.45]
    _exige(isinstance(foco, (list, tuple)) and len(foco) == 2 and all(_num(f) for f in foco),
           "El foco del hueco de foto debe ser [x,y] entre 0 y 1.")
    return {
        **caja,
        "ajuste": s.get("ajuste") if s.get("ajuste") in _AJUSTES else "cover",
        "foco": [float(foco[0]), float(foco[1])],
        "z": _entero(s.get("z", 0), "foto_slot.z", defecto=0),
    }


def _validar_logo(lg: Any) -> dict[str, Any]:
    _exige(isinstance(lg, dict), "El logo debe ser un objeto.")
    tipo = lg.get("tipo")
    _exige(tipo in _TIPOS_LOGO, "El tipo de logo debe ser imagen o wordmark.")
    caja = _validar_caja(lg, "El logo")
    wm = lg.get("wordmark") or {}
    return {
        "tipo": tipo,
        "media_id": str(lg.get("media_id", "")),
        "wordmark": {
            "texto": str(wm.get("texto", "")),
            "color": wm["color"] if _es_hex(wm.get("color")) else "#FFFFFF",
            "fondo": wm["fondo"] if _es_hex(wm.get("fondo")) else "#E30613",
            "familia": wm["familia"] if isinstance(wm.get("familia"), str) and wm.get("familia") else "sans",
            "peso": _entero(wm.get("peso", 700), "logo.wordmark.peso", defecto=700),
        },
        **caja,
        "z": _entero(lg.get("z", 30), "logo.z", defecto=30),
    }


def _validar_texto(t: Any) -> dict[str, Any]:
    _exige(isinstance(t, dict), "Cada bloque de texto debe ser un objeto.")
    tid = t.get("id")
    _exige(tid in _IDS_TEXTO, "El id de texto debe ser titular, pleca o kicker.")
    _exige(t.get("binding") in _BINDINGS, "El binding debe ser copy_in, etiqueta_default o nulo.")
    caja = _validar_caja({**t, "h": t.get("h", 0)}, "El bloque de texto")
    chip = t.get("chip")
    chip_limpio = None
    if isinstance(chip, dict):
        _exige(_es_hex(chip.get("color")), "El color del chip debe ser hex #RRGGBB.")
        chip_limpio = {
            "color": chip["color"],
            "pad_x": _entero(chip.get("pad_x", _CHIP_PAD_X), "chip.pad_x", defecto=_CHIP_PAD_X),
            "pad_y": _entero(chip.get("pad_y", _CHIP_PAD_Y), "chip.pad_y", defecto=_CHIP_PAD_Y),
            "radio": _entero(chip.get("radio", 0), "chip.radio", defecto=0),
        }
    sombra = t.get("sombra")
    sombra_limpia = None
    if isinstance(sombra, dict):
        sombra_limpia = {
            "dx": _entero(sombra.get("dx", 2), "sombra.dx", defecto=2),
            "dy": _entero(sombra.get("dy", 2), "sombra.dy", defecto=2),
            "color": sombra["color"] if _es_hex(sombra.get("color")) else "#000000",
        }
    aj = t.get("auto_ajuste") or {}
    _exige(_es_hex(t.get("color")), "El color del texto debe ser hex #RRGGBB.")
    familia = t["familia"] if isinstance(t.get("familia"), str) and t.get("familia") else "sans"
    return {
        "id": tid,
        "binding": t.get("binding"),
        "texto": str(t.get("texto", "")),
        "x": caja["x"], "y": caja["y"], "w": caja["w"],
        "familia": familia,
        "tamano": _entero(t.get("tamano", 64), "tamano", defecto=64),
        "peso": _entero(t.get("peso", 700), "peso", defecto=700),
        "color": t["color"],
        "alineacion": t.get("alineacion") if t.get("alineacion") in _ALINEACIONES else "izquierda",
        "mayusculas": bool(t.get("mayusculas", False)),
        "interlineado": _flotante(t.get("interlineado", 1.14), "interlineado", defecto=1.14),
        "auto_ajuste": {
            "max_lineas": _entero(aj.get("max_lineas", 4), "auto_ajuste.max_lineas", defecto=4),
            "tam_min": _entero(aj.get("tam_min", 40), "auto_ajuste.tam_min", defecto=40),
        },
        "sombra": sombra_limpia,
        "chip": chip_limpio,
        # Borde de anclaje vertical del bloque: "abajo" => `y` es el borde INFERIOR y el
        # bloque crece hacia arriba (no se desborda aunque tenga más líneas). Default "arriba".
        "ancla": t.get("ancla") if t.get("ancla") in ("arriba", "abajo") else "arriba",
        "z": _entero(t.get("z", 20), "texto.z", defecto=20),
    }


def _validar_formato(nombre: str, f: Any) -> dict[str, Any]:
    _exige(isinstance(f, dict), f"El formato '{nombre}' debe ser un objeto.")
    base = FORMATOS[nombre]
    lienzo = f.get("lienzo") or {}
    textos = f.get("textos") or []
    _exige(isinstance(textos, list) and len(textos) <= 3,
           "Cada formato admite como máximo 3 bloques de texto.")
    return {
        "lienzo": {
            "w": _entero(lienzo.get("w", base["w"]), "formato.lienzo.w", defecto=base["w"]),
            "h": _entero(lienzo.get("h", base["h"]), "formato.lienzo.h", defecto=base["h"]),
            "safe_top": _entero(lienzo.get("safe_top", base["safe_top"]), "formato.lienzo.safe_top", defecto=base["safe_top"]),
            "safe_bottom": _entero(lienzo.get("safe_bottom", base["safe_bottom"]), "formato.lienzo.safe_bottom", defecto=base["safe_bottom"]),
        },
        "fondo": _validar_fondo(f.get("fondo") or {"tipo": "color", "color": "#111315"}),
        "foto_slot": _validar_foto_slot(f.get("foto_slot") or _foto_slot_full(base)),
        "overlay_inferior": _validar_overlay(f.get("overlay_inferior")),
        "logo": _validar_logo(f.get("logo") or _logo_defecto(base)),
        "textos": [_validar_texto(t) for t in textos],
    }


def _validar_overlay(ov: Any) -> dict[str, Any] | None:
    if not isinstance(ov, dict):
        return None
    return {
        "color": ov["color"] if _es_hex(ov.get("color")) else "#111315",
        "alto_frac": _flotante(ov.get("alto_frac", _DEGRADADO_ALTO_FRAC), "overlay.alto_frac", defecto=_DEGRADADO_ALTO_FRAC),
        "alpha": _entero(ov.get("alpha", _DEGRADADO_ALPHA), "overlay.alpha", defecto=_DEGRADADO_ALPHA),
    }


def validar(spec: Any) -> dict[str, Any]:
    """Valida y normaliza un spec completo de marca. Lanza `SpecError` (español) si algo falla."""
    _exige(isinstance(spec, dict), "El spec debe ser un objeto JSON.")
    fuentes = spec.get("fuentes") or {}
    formatos = spec.get("formatos") or {}
    _exige(isinstance(formatos, dict) and formatos, "El spec necesita al menos un formato.")
    limpio_formatos: dict[str, Any] = {}
    for nombre, f in formatos.items():
        _exige(nombre in FORMATOS,
               f"Formato desconocido '{nombre}'. Usa: " + ", ".join(FORMATOS) + ".")
        limpio_formatos[nombre] = _validar_formato(nombre, f)
    return {
        "version": VERSION,
        "marca": str(spec.get("marca", "")),
        "fuentes": {
            "sans": str(fuentes.get("sans", "Barlow")),
            "condensada": str(fuentes.get("condensada", "Barlow Condensed")),
        },
        "formatos": limpio_formatos,
    }


def migrar(spec: dict[str, Any]) -> dict[str, Any]:
    """Gancho de migración entre versiones del esquema. v1: identidad."""
    return spec


# --------------------------------------------------------------------------- #
# Spec por defecto derivado de los campos planos (continuidad con componer.py)  #
# --------------------------------------------------------------------------- #


def _foto_slot_full(base: dict[str, int]) -> dict[str, Any]:
    return {"x": 0, "y": 0, "w": base["w"], "h": base["h"],
            "ajuste": "cover", "foco": [0.5, 0.45], "z": 0}


def _logo_defecto(base: dict[str, int]) -> dict[str, Any]:
    # Esquina superior-izquierda (default histórico), respetando margen y zona segura.
    return {
        "tipo": "wordmark", "media_id": "",
        "wordmark": {"texto": "", "color": "#FFFFFF", "fondo": "#E30613",
                     "familia": "sans", "peso": 700},
        "x": _MARGEN, "y": base["safe_top"] + 24, "w": 220, "h": _LOGO_ALTO, "z": 30,
    }


def _logo_xy(posicion: str, base: dict[str, int], ancho: int, alto: int) -> tuple[int, int]:
    """Reproduce `componer._esquina_logo`: 4 esquinas con margen + zonas seguras."""
    izquierda = "izquierda" in posicion
    superior = "superior" in posicion
    x = _MARGEN if izquierda else (base["w"] - _MARGEN - ancho)
    y = (base["safe_top"] + 24) if superior else (base["h"] - base["safe_bottom"] - _MARGEN - alto)
    return x, y


def _formato_por_defecto(nombre: str, plana: dict[str, Any]) -> dict[str, Any]:
    base = FORMATOS[nombre]
    w, h = base["w"], base["h"]
    margin = _MARGEN
    tinta = str(plana.get("tinta", "#111315"))
    rojo = str(plana.get("rojo", "#E30613"))
    blanco = str(plana.get("blanco", "#FFFFFF"))
    condensada = bool(plana.get("titular_condensada", False))
    mayus = bool(plana.get("titular_mayusculas", False))
    logo_id = str(plana.get("logo", "") or "")
    logo_pos = str(plana.get("logo_posicion", "superior-izquierda"))
    wordmark = str(plana.get("wordmark", "") or "")
    etiqueta = str(plana.get("etiqueta_default", "") or "")

    # Titular: bloque inferior ANCLADO ABAJO (`ancla: "abajo"`): su `y` es el borde INFERIOR
    # (justo sobre el área segura) y el bloque crece hacia ARRIBA. Así un titular de 1 o de 3
    # líneas queda siempre pegado abajo SIN desbordarse. Limitado a 3 líneas (más sería ilegible
    # en la placa; el render trunca con "…").
    tam_max = 88 if nombre == "vertical" else 78
    bottom_limit = h - base["safe_bottom"] - margin
    max_lineas_tit = 3
    # Referencia para la pleca: el borde superior estimado de un titular de máximo de líneas.
    titular_top_ref = bottom_limit - int(tam_max * 1.14 * max_lineas_tit)

    # Logo: caja en la esquina configurada.
    logo_ancho = 220
    lx, ly = _logo_xy(logo_pos, base, logo_ancho, _LOGO_ALTO)

    textos = [
        {
            "id": "titular", "binding": "copy_in", "texto": "",
            "x": margin, "y": bottom_limit, "w": w - margin * 2,
            "familia": "condensada" if condensada else "sans",
            "tamano": tam_max, "peso": 800, "color": blanco, "alineacion": "izquierda",
            "mayusculas": mayus, "interlineado": 1.14,
            "auto_ajuste": {"max_lineas": max_lineas_tit, "tam_min": 40},
            "sombra": {"dx": 2, "dy": 2, "color": "#000000"},
            "chip": None, "ancla": "abajo", "z": 20,
        },
    ]
    if etiqueta:
        textos.insert(0, {
            "id": "pleca", "binding": "etiqueta_default", "texto": etiqueta,
            "x": margin, "y": titular_top_ref - 70, "w": w - margin * 2,
            "familia": "sans", "tamano": _PLECA_TAM, "peso": 700, "color": blanco,
            "alineacion": "izquierda", "mayusculas": True, "interlineado": 1.0,
            "auto_ajuste": {"max_lineas": 1, "tam_min": _PLECA_TAM},
            "sombra": None,
            "chip": {"color": rojo, "pad_x": _CHIP_PAD_X, "pad_y": _CHIP_PAD_Y, "radio": 0},
            "z": 21,
        })

    return {
        "lienzo": {"w": w, "h": h, "safe_top": base["safe_top"], "safe_bottom": base["safe_bottom"]},
        "fondo": {"tipo": "color", "color": tinta},
        "foto_slot": _foto_slot_full(base),
        "overlay_inferior": {"color": tinta, "alto_frac": _DEGRADADO_ALTO_FRAC, "alpha": _DEGRADADO_ALPHA},
        "logo": {
            "tipo": "imagen" if logo_id else "wordmark",
            "media_id": logo_id,
            "wordmark": {"texto": wordmark or "", "color": blanco, "fondo": rojo,
                         "familia": "sans", "peso": 700},
            "x": lx, "y": ly, "w": logo_ancho, "h": _LOGO_ALTO, "z": 30,
        },
        "textos": textos,
    }


def spec_por_defecto(marca: str, plana: dict[str, Any]) -> dict[str, Any]:
    """Deriva un spec COMPLETO (3 formatos) desde los campos planos efectivos de la marca.

    Reproduce el layout del compositor actual (márgenes, zonas seguras, titular inferior, pleca
    sobre el titular, logo en su esquina, degradado de legibilidad) para que una marca sin spec
    guardado siga produciendo la misma placa. `plana` = `plantillas_marca.obtener(marca)`.
    """
    return {
        "version": VERSION,
        "marca": marca,
        "fuentes": {"sans": "Barlow", "condensada": "Barlow Condensed"},
        "formatos": {n: _formato_por_defecto(n, plana) for n in FORMATOS},
    }
