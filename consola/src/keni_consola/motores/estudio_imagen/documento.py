"""Esquema del DOCUMENTO de capas: el formato canónico del editor profesional.

Generaliza el SPEC de plantilla de marca (`spec_plantilla.py`, de slots fijos: 1 foto + 1 logo +
3 textos) a un **documento de capas arbitrarias** que el editor (navegador, react-konva) y el
servidor (Node + @napi-rs/canvas) renderizan idéntico. Es la base del editor tipo Canva: capas
de tipo `imagen`, `texto`, `logo`, `marco`, `overlay` y `grupo`, apiladas por `z`.

    Documento = {
      version, marca?, fuentes?:{sans,condensada},
      formato: {w, h, safe_top, safe_bottom},
      fondo:   Fondo,                 # color | degradado | imagen (mismo contrato que el spec)
      capas:   [ Capa, ... ]          # orden de pintado = z ascendente
    }

    Capa base = { id, tipo, x, y, w, h, rotacion, opacidad, z, visible, bloqueada }
      imagen  -> { objeto, ajuste:cover|contain, foco:[fx,fy], forma (catálogo de formas), radio,
                   filtros:{brillo,contraste,saturacion,desenfoque},
                   sombra:{dx,dy,color,desenfoque?,opacidad?}|null }
      texto   -> { texto, binding:copy_in|etiqueta_default|null, familia, tamano, peso, color,
                   alineacion, mayusculas, interlineado, auto_ajuste:{max_lineas,tam_min},
                   sombra:{dx,dy,color,desenfoque?,opacidad?}|null,
                   relleno_degradado:{desde,hasta,angulo?}|null, chip:{color,pad_x,pad_y,radio}|null,
                   ancla:arriba|abajo, valign:arriba|centro|abajo }
                   # valign: alineación VERTICAL del texto dentro de la CAJA (cuando h>0). La caja
                   # es de alto fijo: el texto se auto-encoge para caber. `ancla` queda por
                   # compatibilidad (camino legado h<=0, sin caja).
      logo    -> { tipo_logo:imagen|wordmark, media_id, wordmark:{texto,color,fondo,familia,peso} }
      marco   -> { forma (catálogo de formas | linea), relleno|null, relleno_degradado:{desde,hasta,angulo?}|null,
                   borde:{color,grosor}|null, radio, sombra:{dx,dy,color,desenfoque?,opacidad?}|null }
      overlay -> { color, alto_frac, alpha }            # degradado de legibilidad (banda inferior)
      grupo   -> { capas:[ Capa, ... ] }                # bloque reutilizable (almacén de capas)

NO depende de Pillow ni de red: solo dicts. El renderer Node (`render_node/dibujar.mjs::
dibujarDocumento`) y el editor TS (`editor/documento.ts`) consumen el mismo JSON. Los mensajes
de error salen en español (la API los devuelve como 400).
"""

from __future__ import annotations

import uuid
from typing import Any

from . import spec_plantilla as _spec

# Versión del esquema (para migraciones futuras vía `migrar`).
VERSION = 1

TIPOS_CAPA = ("imagen", "texto", "logo", "marco", "overlay", "grupo")
# Catálogo de FORMAS compartido (espejo de `pathForma` en `render_node/dibujar.mjs` y de
# `CATALOGO_FORMAS` en `documento.ts`). Retrocompat: "rect"/"elipse" eran las únicas; las nuevas
# se añaden con default seguro "rect". El marco además admite "linea" (trazo recto, no rellenable).
_FORMAS = ("rect", "elipse", "triangulo", "rombo", "pentagono", "hexagono", "estrella", "flecha")
_FORMAS_MARCO = (*_FORMAS, "linea")
_FORMAS_IMAGEN = _FORMAS
# Modos de fusión por capa (espejo de `MAPA_MEZCLA` en `render_node/dibujar.mjs`). "normal" =
# source-over (default); solo se persiste si se aparta de "normal" para no ensuciar el JSON.
_MEZCLAS = ("normal", "multiplicar", "trama", "superponer", "aclarar", "oscurecer")

# Reutilizamos los predicados y constantes del spec (única fuente de verdad de validación
# elemental): hex, número, alineaciones, ajustes, fondo, chip/pad por defecto.
_es_hex = _spec._es_hex
_num = _spec._num
_exige = _spec._exige
_ALINEACIONES = _spec._ALINEACIONES
_AJUSTES = _spec._AJUSTES
_CHIP_PAD_X = _spec._CHIP_PAD_X
_CHIP_PAD_Y = _spec._CHIP_PAD_Y


class DocumentoError(ValueError):
    """Error de validación del documento de capas, con mensaje en español para la UI."""


# --------------------------------------------------------------------------- #
# Validación                                                                   #
# --------------------------------------------------------------------------- #


def _exige_doc(cond: bool, msg: str) -> None:
    if not cond:
        raise DocumentoError(msg)


def _id(c: dict[str, Any]) -> str:
    v = c.get("id")
    return v if isinstance(v, str) and v else uuid.uuid4().hex[:12]


def _caja(c: Any, ctx: str) -> dict[str, float]:
    _exige_doc(isinstance(c, dict), f"{ctx} debe ser un objeto con x,y,w,h.")
    for k in ("x", "y", "w", "h"):
        _exige_doc(_num(c.get(k)), f"{ctx}: '{k}' debe ser numérico.")
    return {k: float(c[k]) for k in ("x", "y", "w", "h")}


def _base(c: dict[str, Any]) -> dict[str, Any]:
    """Campos comunes a toda capa (geometría + estado)."""
    caja = _caja(c, "La capa")
    op = c.get("opacidad", 1)
    nombre = c.get("nombre")
    base = {
        "id": _id(c),
        **caja,
        "rotacion": float(c.get("rotacion", 0) or 0),
        "opacidad": float(op) if _num(op) and 0 <= float(op) <= 1 else 1.0,
        "z": int(c.get("z", 0)),
        "visible": bool(c.get("visible", True)),
        "bloqueada": bool(c.get("bloqueada", False)),
    }
    # `nombre` (etiqueta editable en el panel de capas) es opcional: solo se persiste si lo trae,
    # para no ensuciar los documentos antiguos. El render lo ignora.
    if isinstance(nombre, str) and nombre.strip():
        base["nombre"] = nombre.strip()
    # `mezcla` (modo de fusión): solo se persiste si se aparta de "normal" (source-over), para que
    # los documentos sin él validen y rindan idénticos a antes.
    mezcla = c.get("mezcla")
    if mezcla in _MEZCLAS and mezcla != "normal":
        base["mezcla"] = mezcla
    return base


def _sombra(s: Any) -> dict[str, Any] | None:
    """Normaliza una sombra {dx,dy,color,desenfoque?,opacidad?}. `desenfoque`/`opacidad` solo se
    persisten si se apartan del default (0 / 1) — así una sombra plana no ensucia el JSON ni cambia
    el render legado. Devuelve None si no viene sombra."""
    if not isinstance(s, dict):
        return None
    out: dict[str, Any] = {
        "dx": int(s.get("dx", 2)),
        "dy": int(s.get("dy", 2)),
        "color": s["color"] if _es_hex(s.get("color")) else "#000000",
    }
    desenfoque = s.get("desenfoque")
    if _num(desenfoque) and float(desenfoque) > 0:
        out["desenfoque"] = float(desenfoque)
    opacidad = s.get("opacidad")
    if _num(opacidad) and 0 <= float(opacidad) < 1:
        out["opacidad"] = float(opacidad)
    return out


def _relleno_degradado(g: Any) -> dict[str, Any] | None:
    """Normaliza un relleno por degradado {desde,hasta,angulo?} (hex validados). Solo se persiste si
    trae `desde` y `hasta` válidos; si no, None (relleno sólido como hasta ahora)."""
    if not isinstance(g, dict):
        return None
    if not (_es_hex(g.get("desde")) and _es_hex(g.get("hasta"))):
        return None
    return {
        "desde": g["desde"],
        "hasta": g["hasta"],
        "angulo": float(g.get("angulo", 180)),
    }


def _filtros(f: Any) -> dict[str, float] | None:
    if not isinstance(f, dict):
        return None
    out: dict[str, float] = {}
    for k, defecto in (("brillo", 1.0), ("contraste", 1.0), ("saturacion", 1.0), ("desenfoque", 0.0)):
        v = f.get(k)
        if _num(v):
            out[k] = float(v)
        else:
            out[k] = defecto
    # Solo persistir si algo se aparta del neutro (evita ruido en el JSON).
    if out["brillo"] == 1 and out["contraste"] == 1 and out["saturacion"] == 1 and out["desenfoque"] == 0:
        return None
    return out


def _capa_imagen(c: dict[str, Any]) -> dict[str, Any]:
    foco = c.get("foco") or [0.5, 0.5]
    _exige_doc(
        isinstance(foco, (list, tuple)) and len(foco) == 2 and all(_num(f) for f in foco),
        "El foco de la imagen debe ser [x,y] entre 0 y 1.",
    )
    zoom = c.get("zoom", 1)
    radio = c.get("radio", 0)
    return {
        **_base(c),
        "tipo": "imagen",
        "objeto": str(c.get("objeto", "") or ""),
        "ajuste": c.get("ajuste") if c.get("ajuste") in _AJUSTES else "cover",
        "foco": [float(foco[0]), float(foco[1])],
        # Forma del recorte de la imagen: "rect" (def) o "elipse" (círculo si la caja es cuadrada).
        # `radio` redondea las esquinas del rect (px ≥ 0); se ignora con forma "elipse". Se persisten
        # siempre con su default para que el contrato sea estable; documentos viejos validan igual.
        "forma": c.get("forma") if c.get("forma") in _FORMAS_IMAGEN else "rect",
        "radio": max(0, int(radio)) if _num(radio) else 0,
        # Reencuadre dentro del marco: factor de acercamiento (1 = ajuste base). Acotado a [1, 6].
        "zoom": min(6.0, max(1.0, float(zoom))) if _num(zoom) else 1.0,
        # `es_foto`: ESTA capa es el HUECO DE FOTO de la plantilla — la única donde entra la foto de
        # la pieza al aplicarla. Toda plantilla del estudio tiene exactamente una (obligatoria y
        # bloqueada en el editor). `objeto` guarda una foto de muestra para la miniatura.
        "es_foto": bool(c.get("es_foto", False)),
        "filtros": _filtros(c.get("filtros")),
        # Sombra del rectángulo de la imagen (opcional): solo se persiste si viene.
        "sombra": _sombra(c.get("sombra")),
    }


def _capa_texto(c: dict[str, Any]) -> dict[str, Any]:
    _exige_doc(c.get("binding") in _spec._BINDINGS, "El binding debe ser copy_in, etiqueta_default o nulo.")
    _exige_doc(_es_hex(c.get("color")), "El color del texto debe ser hex #RRGGBB.")
    chip = c.get("chip")
    chip_limpio = None
    if isinstance(chip, dict):
        _exige_doc(_es_hex(chip.get("color")), "El color del chip debe ser hex #RRGGBB.")
        chip_limpio = {
            "color": chip["color"],
            "pad_x": int(chip.get("pad_x", _CHIP_PAD_X)),
            "pad_y": int(chip.get("pad_y", _CHIP_PAD_Y)),
            "radio": int(chip.get("radio", 0)),
        }
    sombra_limpia = _sombra(c.get("sombra"))
    # Contorno del texto (legibilidad sobre fotos): solo si trae grosor > 0.
    contorno = c.get("contorno")
    contorno_limpio = None
    if isinstance(contorno, dict) and _num(contorno.get("grosor")) and float(contorno["grosor"]) > 0:
        contorno_limpio = {
            "color": contorno["color"] if _es_hex(contorno.get("color")) else "#000000",
            "grosor": float(contorno["grosor"]),
        }
    aj = c.get("auto_ajuste") or {}
    familia = c["familia"] if isinstance(c.get("familia"), str) and c.get("familia") else "sans"
    return {
        **_base(c),
        "tipo": "texto",
        "texto": str(c.get("texto", "")),
        "binding": c.get("binding"),
        "familia": familia,
        "tamano": int(c.get("tamano", 64)),
        "peso": int(c.get("peso", 700)),
        "color": c["color"],
        "alineacion": c.get("alineacion") if c.get("alineacion") in _ALINEACIONES else "izquierda",
        "mayusculas": bool(c.get("mayusculas", False)),
        "interlineado": float(c.get("interlineado", 1.14)),
        "interletra": float(c.get("interletra", 0)) if _num(c.get("interletra")) else 0.0,
        "auto_ajuste": {
            "max_lineas": int(aj.get("max_lineas", 4)),
            "tam_min": int(aj.get("tam_min", 40)),
        },
        "sombra": sombra_limpia,
        # Degradado del relleno (sustituye al color sólido cuando viene). Solo se persiste si es válido.
        "relleno_degradado": _relleno_degradado(c.get("relleno_degradado")),
        "contorno": contorno_limpio,
        "chip": chip_limpio,
        "ancla": c.get("ancla") if c.get("ancla") in ("arriba", "abajo") else "arriba",
        # `valign` (alineación vertical en la caja) deriva de `ancla` si falta, para que las
        # plantillas antiguas (que solo traían `ancla`) sigan validando sin cambios.
        "valign": (
            c.get("valign")
            if c.get("valign") in ("arriba", "centro", "abajo")
            else ("abajo" if c.get("ancla") == "abajo" else "arriba")
        ),
    }


def _capa_logo(c: dict[str, Any]) -> dict[str, Any]:
    tipo_logo = c.get("tipo_logo")
    _exige_doc(tipo_logo in _spec._TIPOS_LOGO, "El tipo de logo debe ser imagen o wordmark.")
    wm = c.get("wordmark") or {}
    return {
        **_base(c),
        "tipo": "logo",
        "tipo_logo": tipo_logo,
        "media_id": str(c.get("media_id", "") or ""),
        "wordmark": {
            "texto": str(wm.get("texto", "")),
            "color": wm["color"] if _es_hex(wm.get("color")) else "#FFFFFF",
            "fondo": wm["fondo"] if _es_hex(wm.get("fondo")) else "#E30613",
            "familia": wm["familia"] if isinstance(wm.get("familia"), str) and wm.get("familia") else "sans",
            "peso": int(wm.get("peso", 700)),
        },
    }


def _capa_marco(c: dict[str, Any]) -> dict[str, Any]:
    forma = c.get("forma") if c.get("forma") in _FORMAS_MARCO else "rect"
    relleno = c.get("relleno")
    borde = c.get("borde")
    borde_limpio = None
    if isinstance(borde, dict) and _num(borde.get("grosor")) and float(borde["grosor"]) > 0:
        borde_limpio = {
            "color": borde["color"] if _es_hex(borde.get("color")) else "#000000",
            "grosor": float(borde["grosor"]),
        }
    return {
        **_base(c),
        "tipo": "marco",
        "forma": forma,
        "relleno": relleno if _es_hex(relleno) else None,
        # Degradado del relleno (sustituye a `relleno` cuando viene). Solo se persiste si es válido.
        "relleno_degradado": _relleno_degradado(c.get("relleno_degradado")),
        "borde": borde_limpio,
        "radio": int(c.get("radio", 0)),
        # Sombra de la forma del marco (opcional): solo se persiste si viene.
        "sombra": _sombra(c.get("sombra")),
    }


def _capa_overlay(c: dict[str, Any]) -> dict[str, Any]:
    return {
        **_base(c),
        "tipo": "overlay",
        "color": c["color"] if _es_hex(c.get("color")) else "#111315",
        "alto_frac": float(c.get("alto_frac", _spec._DEGRADADO_ALTO_FRAC)),
        "alpha": int(c.get("alpha", _spec._DEGRADADO_ALPHA)),
    }


def _capa_grupo(c: dict[str, Any]) -> dict[str, Any]:
    hijas = c.get("capas")
    _exige_doc(isinstance(hijas, list), "Un grupo debe tener una lista 'capas'.")
    return {
        **_base(c),
        "tipo": "grupo",
        "capas": [_validar_capa(h) for h in hijas],
    }


_DESPACHO = {
    "imagen": _capa_imagen,
    "texto": _capa_texto,
    "logo": _capa_logo,
    "marco": _capa_marco,
    "overlay": _capa_overlay,
    "grupo": _capa_grupo,
}


def _validar_capa(c: Any) -> dict[str, Any]:
    _exige_doc(isinstance(c, dict), "Cada capa debe ser un objeto.")
    tipo = c.get("tipo")
    _exige_doc(tipo in TIPOS_CAPA, "El tipo de capa debe ser: " + ", ".join(TIPOS_CAPA) + ".")
    return _DESPACHO[tipo](c)


def _validar_formato(f: Any) -> dict[str, int]:
    _exige_doc(isinstance(f, dict), "El documento necesita un objeto 'formato' con w,h.")
    _exige_doc(_num(f.get("w")) and _num(f.get("h")), "El formato necesita 'w' y 'h' numéricos.")
    return {
        "w": int(f["w"]),
        "h": int(f["h"]),
        "safe_top": int(f.get("safe_top", 0)),
        "safe_bottom": int(f.get("safe_bottom", 0)),
    }


def _normalizar_hueco_foto(capas: list[dict[str, Any]]) -> None:
    """Garantiza COMO MUCHO un hueco de foto (`es_foto`) entre las capas imagen, IN PLACE.

    Si varias capas imagen vienen marcadas, conserva la de MENOR z (el fondo) y desmarca el resto:
    el hueco de foto es único por plantilla. NO auto-designa una si no hay ninguna marcada —esa es
    decisión del diseñador (el estudio la exige y la bloquea); aquí solo se evita el estado ambiguo
    de tener dos. `componer` usa luego `capa_foto` (con respaldo al fondo) para colocar la foto.
    """
    marcadas = [c for c in capas if c.get("tipo") == "imagen" and c.get("es_foto")]
    if len(marcadas) <= 1:
        return
    conservar = min(marcadas, key=lambda c: c.get("z", 0))
    for c in marcadas:
        if c is not conservar:
            c["es_foto"] = False


def validar(doc: Any) -> dict[str, Any]:
    """Valida y normaliza un Documento completo. Lanza `DocumentoError` (español) si algo falla."""
    _exige_doc(isinstance(doc, dict), "El documento debe ser un objeto JSON.")
    capas = doc.get("capas")
    _exige_doc(isinstance(capas, list), "El documento necesita una lista 'capas'.")
    fuentes = doc.get("fuentes") or {}
    capas_ok = [_validar_capa(c) for c in capas]
    _normalizar_hueco_foto(capas_ok)
    return {
        "version": VERSION,
        "marca": str(doc.get("marca", "")),
        "fuentes": {
            "sans": str(fuentes.get("sans", "Barlow")),
            "condensada": str(fuentes.get("condensada", "Barlow Condensed")),
        },
        "formato": _validar_formato(doc.get("formato")),
        "fondo": _spec._validar_fondo(doc.get("fondo") or {"tipo": "color", "color": "#111315"}),
        "capas": capas_ok,
    }


def capa_foto(doc: dict[str, Any]) -> dict[str, Any] | None:
    """Devuelve la capa que es el HUECO DE FOTO de un documento, o None si la plantilla no lleva foto.

    Preferencia: la capa imagen marcada `es_foto`. Respaldo (plantillas antiguas sin marcar): la
    capa imagen de MAYOR área que cubra casi todo el lienzo (un fondo a sangre), nunca un logo
    pequeño. Si no hay ninguna imagen grande, la plantilla es de solo texto/gráfica: None.
    """
    capas = [c for c in (doc.get("capas") or []) if isinstance(c, dict) and c.get("tipo") == "imagen"]
    marcada = next((c for c in capas if c.get("es_foto")), None)
    if marcada is not None:
        return marcada
    fmt = doc.get("formato") or {}
    area_lienzo = float(fmt.get("w", 0)) * float(fmt.get("h", 0))
    if area_lienzo <= 0:
        return None
    # Respaldo SOLO para plantillas legadas: una imagen que cubra ≥60% del lienzo es un fondo de foto;
    # un logo pequeño (como el de la esquina) nunca lo cubre, así que no se confunde con el hueco.
    grandes = [c for c in capas if (float(c.get("w", 0)) * float(c.get("h", 0))) >= 0.6 * area_lienzo]
    if not grandes:
        return None
    return max(grandes, key=lambda c: float(c.get("w", 0)) * float(c.get("h", 0)))


def tiene_hueco_explicito(doc: dict[str, Any]) -> bool:
    """True si el documento tiene una capa imagen marcada `es_foto` (hueco de foto EXPLÍCITO).

    Lo exige el estudio al guardar una plantilla: toda plantilla debe declarar dónde va la foto.
    """
    return any(
        isinstance(c, dict) and c.get("tipo") == "imagen" and c.get("es_foto")
        for c in (doc.get("capas") or [])
    )


def migrar(doc: dict[str, Any]) -> dict[str, Any]:
    """Gancho de migración entre versiones del esquema. v1: identidad."""
    return doc


# --------------------------------------------------------------------------- #
# Adaptador: un FORMATO del spec de plantilla -> Documento de capas            #
# --------------------------------------------------------------------------- #


def desde_spec(spec: dict[str, Any], formato: str) -> dict[str, Any]:
    """Convierte un FORMATO del spec de plantilla de marca en un Documento de capas equivalente.

    Preserva el render: el `foto_slot` pasa a una capa imagen (z 0), el `overlay_inferior` a una
    capa overlay, cada bloque de `textos` a una capa texto, y el `logo` a una capa logo —
    conservando sus `z`. Así una plantilla existente se edita y renderiza por el mismo camino que
    un documento nuevo, sin migración explícita del store. `spec` debe estar ya validado
    (`spec_plantilla.validar`).
    """
    f = (spec.get("formatos") or {}).get(formato)
    _exige_doc(isinstance(f, dict), f"El spec no tiene el formato '{formato}'.")
    lienzo = f["lienzo"]
    capas: list[dict[str, Any]] = []

    s = f["foto_slot"]
    capas.append({
        "id": "foto", "tipo": "imagen", "objeto": "",
        "x": s["x"], "y": s["y"], "w": s["w"], "h": s["h"],
        "ajuste": s.get("ajuste", "cover"), "foco": s.get("foco", [0.5, 0.45]),
        "es_foto": True,  # el foto_slot del spec ES el hueco de foto (obligatorio).
        "z": int(s.get("z", 0)),
    })

    ov = f.get("overlay_inferior")
    if ov:
        capas.append({
            "id": "overlay", "tipo": "overlay",
            "x": 0, "y": 0, "w": lienzo["w"], "h": lienzo["h"],
            "color": ov["color"], "alto_frac": ov["alto_frac"], "alpha": ov["alpha"],
            "z": 10,
        })

    for t in f.get("textos", []):
        capas.append({
            **{k: t[k] for k in ("x", "y", "w") if k in t},
            "id": t.get("id", "texto"), "tipo": "texto", "h": 0,
            "texto": t.get("texto", ""), "binding": t.get("binding"),
            "familia": t.get("familia", "sans"), "tamano": t.get("tamano", 64),
            "peso": t.get("peso", 700), "color": t.get("color", "#FFFFFF"),
            "alineacion": t.get("alineacion", "izquierda"), "mayusculas": t.get("mayusculas", False),
            "interlineado": t.get("interlineado", 1.14), "auto_ajuste": t.get("auto_ajuste"),
            "sombra": t.get("sombra"), "chip": t.get("chip"), "ancla": t.get("ancla", "arriba"),
            # valign deriva de ancla por defecto (las plantillas del spec solo traen `ancla`).
            "valign": t.get("valign", "abajo" if t.get("ancla") == "abajo" else "arriba"),
            "z": int(t.get("z", 20)),
        })

    lg = f.get("logo")
    if lg:
        capas.append({
            "id": "logo", "tipo": "logo", "tipo_logo": lg.get("tipo", "wordmark"),
            "media_id": lg.get("media_id", ""), "wordmark": lg.get("wordmark"),
            "x": lg["x"], "y": lg["y"], "w": lg["w"], "h": lg["h"],
            "z": int(lg.get("z", 30)),
        })

    return validar({
        "version": VERSION,
        "marca": spec.get("marca", ""),
        "fuentes": spec.get("fuentes"),
        "formato": {
            "w": lienzo["w"], "h": lienzo["h"],
            "safe_top": lienzo.get("safe_top", 0), "safe_bottom": lienzo.get("safe_bottom", 0),
        },
        "fondo": f.get("fondo"),
        "capas": capas,
    })
