"""Esquema del SPEC de plantilla de marca: capas por formato, fuente de verdad del render.

Una "plantilla" pasa de ser campos planos (color, logo + 1 de 4 esquinas, pleca...) a un SPEC
de CAPAS por formato (9:16 / 4:5 / 1:1) que el equipo diseña visualmente y que TANTO el editor
(navegador, react-konva) COMO el servidor (Node + node-canvas) renderizan idéntico. Este módulo
es el contrato canónico: define el esquema, lo valida y deriva un spec por defecto desde los
campos planos actuales (continuidad visual sin migración explícita).

Coordenadas: píxeles sobre el lienzo de cada formato (1080×1920 / 1080×1350 / 1080×1080).

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

from typing import Any

# Versión del esquema (para migraciones futuras vía `migrar`).
VERSION = 1

# Geometría base de cada formato (espejo de `marcas.json:formatos`). El spec la incrusta por
# formato para que editor y servidor compartan exactamente el lienzo y las zonas seguras.
FORMATOS: dict[str, dict[str, int]] = {
    "vertical": {"w": 1080, "h": 1920, "safe_top": 220, "safe_bottom": 420},
    "feed": {"w": 1080, "h": 1350, "safe_top": 60, "safe_bottom": 96},
    "cuadrado": {"w": 1080, "h": 1080, "safe_top": 60, "safe_bottom": 96},
}

# Familias lógicas de fuente -> el renderer y el editor las resuelven a su archivo embebido.
FAMILIAS = ("sans", "condensada")

_AJUSTES = ("cover", "contain")
_ALINEACIONES = ("izquierda", "centro", "derecha")
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
    return isinstance(v, str) and len(v) == 7 and v[0] == "#" and all(
        c in "0123456789abcdefABCDEF" for c in v[1:]
    )


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _exige(cond: bool, msg: str) -> None:
    if not cond:
        raise SpecError(msg)


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
        limpio["degradado"] = {
            "desde": g["desde"], "hasta": g["hasta"],
            "angulo": float(g.get("angulo", 180)),
        }
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
        "z": int(s.get("z", 0)),
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
            "familia": wm.get("familia") if wm.get("familia") in FAMILIAS else "sans",
            "peso": int(wm.get("peso", 700)),
        },
        **caja,
        "z": int(lg.get("z", 30)),
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
            "pad_x": int(chip.get("pad_x", _CHIP_PAD_X)),
            "pad_y": int(chip.get("pad_y", _CHIP_PAD_Y)),
            "radio": int(chip.get("radio", 0)),
        }
    sombra = t.get("sombra")
    sombra_limpia = None
    if isinstance(sombra, dict):
        sombra_limpia = {
            "dx": int(sombra.get("dx", 2)), "dy": int(sombra.get("dy", 2)),
            "color": sombra["color"] if _es_hex(sombra.get("color")) else "#000000",
        }
    aj = t.get("auto_ajuste") or {}
    _exige(_es_hex(t.get("color")), "El color del texto debe ser hex #RRGGBB.")
    _exige(t.get("familia") in FAMILIAS, "La familia del texto debe ser sans o condensada.")
    return {
        "id": tid,
        "binding": t.get("binding"),
        "texto": str(t.get("texto", "")),
        "x": caja["x"], "y": caja["y"], "w": caja["w"],
        "familia": t["familia"],
        "tamano": int(t.get("tamano", 64)),
        "peso": int(t.get("peso", 700)),
        "color": t["color"],
        "alineacion": t.get("alineacion") if t.get("alineacion") in _ALINEACIONES else "izquierda",
        "mayusculas": bool(t.get("mayusculas", False)),
        "interlineado": float(t.get("interlineado", 1.14)),
        "auto_ajuste": {
            "max_lineas": int(aj.get("max_lineas", 4)),
            "tam_min": int(aj.get("tam_min", 40)),
        },
        "sombra": sombra_limpia,
        "chip": chip_limpio,
        "z": int(t.get("z", 20)),
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
            "w": int(lienzo.get("w", base["w"])),
            "h": int(lienzo.get("h", base["h"])),
            "safe_top": int(lienzo.get("safe_top", base["safe_top"])),
            "safe_bottom": int(lienzo.get("safe_bottom", base["safe_bottom"])),
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
        "alto_frac": float(ov.get("alto_frac", _DEGRADADO_ALTO_FRAC)),
        "alpha": int(ov.get("alpha", _DEGRADADO_ALPHA)),
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

    # Titular: bloque inferior (igual que componer.py). bottom_limit = h - safe_bottom - margin.
    # Reservamos ~2 líneas para que el default quede anclado cerca del borde inferior seguro.
    tam_max = 88 if nombre == "vertical" else 78
    bottom_limit = h - base["safe_bottom"] - margin
    titular_y = bottom_limit - int(tam_max * 1.14 * 2)

    # Logo: caja en la esquina configurada.
    logo_ancho = 220
    lx, ly = _logo_xy(logo_pos, base, logo_ancho, _LOGO_ALTO)

    textos = [
        {
            "id": "titular", "binding": "copy_in", "texto": "",
            "x": margin, "y": titular_y, "w": w - margin * 2,
            "familia": "condensada" if condensada else "sans",
            "tamano": tam_max, "peso": 800, "color": blanco, "alineacion": "izquierda",
            "mayusculas": mayus, "interlineado": 1.14,
            "auto_ajuste": {"max_lineas": 4, "tam_min": 40},
            "sombra": {"dx": 2, "dy": 2, "color": "#000000"},
            "chip": None, "z": 20,
        },
    ]
    if etiqueta:
        textos.insert(0, {
            "id": "pleca", "binding": "etiqueta_default", "texto": etiqueta,
            "x": margin, "y": titular_y - 70, "w": w - margin * 2,
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
