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
                   sombra:{dx,dy,color,desenfoque?,opacidad?}|null, flip_h?, flip_v? }
                   # flip_h/flip_v: volteo (espejo) horizontal/vertical alrededor del centro de la
                   # caja. Booleanos opcionales; solo se persisten si True (def False).
      texto   -> { texto, binding:copy_in|etiqueta_default|null, familia, tamano, peso, color,
                   alineacion, mayusculas, interlineado, auto_ajuste:{max_lineas,tam_min},
                   sombra:{dx,dy,color,desenfoque?,opacidad?}|null,
                   relleno_degradado:{desde,hasta,angulo?}|null, chip:{color,pad_x,pad_y,radio}|null,
                   curva:{radio}|null, ancla:arriba|abajo, valign:arriba|centro|abajo,
                   cursiva?, subrayado?, tachado? }
                   # curva: texto en ARCO (radio px; +=arriba/sonrisa, -=abajo/ceño). Sólo si radio!=0.
                   # cursiva/subrayado/tachado: booleanos opcionales, solo se persisten si True
                   # (def False). El tachado es combinable con el subrayado (línea a media altura).
                   # La cursiva solo surte efecto en familias con itálica real (FAMILIAS_CON_CURSIVA
                   # en dibujar.mjs); el render la ignora para el resto (sin oblicuas sintéticas).
                   # valign: alineación VERTICAL del texto dentro de la CAJA (cuando h>0). La caja
                   # es de alto fijo: el texto se auto-encoge para caber. `ancla` queda por
                   # compatibilidad (camino legado h<=0, sin caja).
      logo    -> { tipo_logo:imagen|wordmark, media_id, wordmark:{texto,color,fondo,familia,peso},
                   flip_h?, flip_v? }  # volteo horizontal/vertical (opcional, solo si True)
      marco   -> { forma (catálogo de formas | linea), relleno|null, relleno_degradado:{desde,hasta,angulo?}|null,
                   borde:{color,grosor}|null, radio, sombra:{dx,dy,color,desenfoque?,opacidad?}|null }
      overlay -> { color, alto_frac, alpha }            # degradado de legibilidad (banda inferior)
      grupo   -> { capas:[ Capa, ... ] }                # bloque reutilizable (almacén de capas)

NO depende de Pillow ni de red: solo dicts. El renderer Node (`render_node/dibujar.mjs::
dibujarDocumento`) y el editor TS (`editor/documento.ts`) consumen el mismo JSON. Los mensajes
de error salen en español (la API los devuelve como 400).
"""

from __future__ import annotations

import math
import uuid
from typing import Any

from . import spec_plantilla as _spec

# Versión del esquema (para migraciones futuras vía `migrar`).
VERSION = 1

TIPOS_CAPA = ("imagen", "texto", "logo", "marco", "overlay", "grupo")
# Catálogo de FORMAS compartido (espejo de `pathForma` en `render_node/dibujar.mjs` y de
# `CATALOGO_FORMAS` en `documento.ts`). El marco además admite "linea" (trazo recto, no rellenable).
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


def _entero(valor: Any, campo: str, minimo: int | None = None, maximo: int | None = None, defecto: int = 0) -> int:
    """Convierte un valor a entero o lanza DocumentoError con mensaje en español.

    Valida que esté en rango [minimo, maximo] si se especifican.
    """
    if valor is None or valor == "":
        return defecto
    # Solo el CAST va en el try: `DocumentoError` hereda de `ValueError`, así que si las
    # comprobaciones de rango se hicieran aquí dentro, el `except` las recazaría como "número
    # entero válido" y perderíamos el mensaje específico de límite. Por eso van fuera del try.
    try:
        num = int(valor)
    except (ValueError, TypeError, OverflowError):
        raise DocumentoError(f"'{campo}' debe ser un número entero válido.")
    if not math.isfinite(num):
        raise DocumentoError(f"'{campo}' debe ser un número válido.")
    if minimo is not None and num < minimo:
        raise DocumentoError(f"'{campo}' no puede ser menor a {minimo}.")
    if maximo is not None and num > maximo:
        raise DocumentoError(f"'{campo}' no puede ser mayor a {maximo}.")
    return num


def _flotante(valor: Any, campo: str, minimo: float | None = None, maximo: float | None = None, defecto: float = 0.0) -> float:
    """Convierte un valor a flotante o lanza DocumentoError con mensaje en español.

    Valida que esté en rango [minimo, maximo] si se especifican.
    """
    if valor is None or valor == "":
        return defecto
    # Igual que en `_entero`: el cast va en el try y las comprobaciones de rango fuera, para no
    # recazar el `DocumentoError` de límite (es `ValueError`) y perder su mensaje específico.
    try:
        num = float(valor)
    except (ValueError, TypeError, OverflowError):
        raise DocumentoError(f"'{campo}' debe ser un número válido.")
    if not math.isfinite(num):
        raise DocumentoError(f"'{campo}' debe ser un número válido.")
    if minimo is not None and num < minimo:
        raise DocumentoError(f"'{campo}' no puede ser menor a {minimo}.")
    if maximo is not None and num > maximo:
        raise DocumentoError(f"'{campo}' no puede ser mayor a {maximo}.")
    return num


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
    # Sin `or 0`: un valor inválido como `{}` (falsy) NO debe coalescer a 0 y colarse; `_flotante`
    # ya trata None/"" como 0 vía `defecto`, y un tipo no numérico lanza DocumentoError (400).
    rotacion_val = c.get("rotacion", 0)
    opacidad_val = _flotante(op, "opacidad", minimo=0.0, maximo=1.0, defecto=1.0)
    base = {
        "id": _id(c),
        **caja,
        "rotacion": _flotante(rotacion_val, "rotacion", defecto=0.0),
        "opacidad": opacidad_val,
        "z": _entero(c.get("z", 0), "z", defecto=0),
        "visible": bool(c.get("visible", True)),
        "bloqueada": bool(c.get("bloqueada", False)),
    }
    # `nombre` (etiqueta editable en el panel de capas) es opcional: solo se persiste si lo trae,
    # para no ensuciar los documentos antiguos. El render lo ignora.
    if isinstance(nombre, str) and nombre.strip():
        base["nombre"] = nombre.strip()
    # `mezcla` (modo de fusión): solo se persiste si se aparta de "normal" (source-over), para que
    # los documentos sin él validen y se rindan en modo normal.
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
        "dx": _entero(s.get("dx", 2), "sombra.dx", defecto=2),
        "dy": _entero(s.get("dy", 2), "sombra.dy", defecto=2),
        "color": s["color"] if _es_hex(s.get("color")) else "#000000",
    }
    desenfoque = s.get("desenfoque")
    if _num(desenfoque) and float(desenfoque) > 0:
        out["desenfoque"] = float(desenfoque)
    opacidad = s.get("opacidad")
    if _num(opacidad) and 0 <= float(opacidad) < 1:
        out["opacidad"] = float(opacidad)
    return out


def _curva(c: Any) -> dict[str, Any] | None:
    """Normaliza el texto curvo {radio}. `radio` en px (positivo = arco hacia arriba, negativo =
    hacia abajo). Solo se persiste si es un número != 0 — así un texto recto no ensucia el JSON ni
    cambia el render legado. Devuelve None si no viene curva o `radio` es 0/ inválido."""
    if not isinstance(c, dict):
        return None
    radio = c.get("radio")
    if not _num(radio) or float(radio) == 0:
        return None
    return {"radio": float(radio)}


def _stops(g: Any) -> list[dict[str, Any]] | None:
    """Normaliza las paradas multi-stop {pos,color} de un degradado. Devuelve la lista (≥2 paradas
    con color hex válido) o None si no hay multi-stop válido (se usa desde/hasta)."""
    raw = g.get("stops") if isinstance(g, dict) else None
    if not isinstance(raw, list):
        return None
    out = []
    for s in raw:
        if isinstance(s, dict) and _es_hex(s.get("color")):
            pos = s.get("pos", 0)
            out.append({"pos": min(1.0, max(0.0, float(pos) if _num(pos) else 0.0)), "color": s["color"]})
    if len(out) < 2:
        return None
    out.sort(key=lambda s: s["pos"])
    return out


def _relleno_degradado(g: Any) -> dict[str, Any] | None:
    """Normaliza un degradado {desde,hasta,angulo?,tipo?,stops?} (texto/marco). Solo se persiste si
    trae `desde` y `hasta` válidos; si no, None (relleno sólido como hasta ahora). `tipo` (lineal/
    radial) y `stops` (multi-parada) son aditivos y retrocompatibles."""
    if not isinstance(g, dict):
        return None
    if not (_es_hex(g.get("desde")) and _es_hex(g.get("hasta"))):
        return None
    out: dict[str, Any] = {
        "desde": g["desde"],
        "hasta": g["hasta"],
        "angulo": float(g.get("angulo", 180)),
    }
    # `tipo` solo se persiste si es "radial" (lineal es el default; no ensucia documentos viejos).
    if g.get("tipo") == "radial":
        out["tipo"] = "radial"
    stops = _stops(g)
    if stops is not None:
        out["stops"] = stops
    return out


def _duotono(d: Any) -> dict[str, str] | None:
    """Normaliza un tinte duotono {sombra,luz} (hex validados). None si falta o es inválido."""
    if not isinstance(d, dict):
        return None
    if not (_es_hex(d.get("sombra")) and _es_hex(d.get("luz"))):
        return None
    return {"sombra": d["sombra"], "luz": d["luz"]}


def _filtros(f: Any) -> dict[str, Any] | None:
    if not isinstance(f, dict):
        return None
    out: dict[str, Any] = {}
    for k, defecto in (("brillo", 1.0), ("contraste", 1.0), ("saturacion", 1.0), ("desenfoque", 0.0)):
        v = f.get(k)
        if _num(v):
            out[k] = float(v)
        else:
            out[k] = defecto
    duotono = _duotono(f.get("duotono"))
    # Solo persistir si algo se aparta del neutro (evita datos irrelevantes en el JSON). El duotono cuenta como
    # "no neutro" aunque brillo/contraste sigan a 1.
    neutro = out["brillo"] == 1 and out["contraste"] == 1 and out["saturacion"] == 1 and out["desenfoque"] == 0
    if neutro and duotono is None:
        return None
    if duotono is not None:
        out["duotono"] = duotono
    return out


def _crop(c: Any) -> dict[str, float] | None:
    """Normaliza un recorte no destructivo {cx,cy,cw,ch} en fracciones 0..1 de la fuente. None si no
    viene o es el recorte completo (toda la imagen), para no ensuciar documentos viejos."""
    if not isinstance(c, dict):
        return None
    cx = min(1.0, max(0.0, float(c["cx"]))) if _num(c.get("cx")) else 0.0
    cy = min(1.0, max(0.0, float(c["cy"]))) if _num(c.get("cy")) else 0.0
    cw = min(1.0 - cx, max(0.0, float(c["cw"]))) if _num(c.get("cw")) else 1.0 - cx
    ch = min(1.0 - cy, max(0.0, float(c["ch"]))) if _num(c.get("ch")) else 1.0 - cy
    # Recorte completo (toda la imagen) => None: render idéntico al legado.
    if cx == 0.0 and cy == 0.0 and cw >= 1.0 and ch >= 1.0:
        return None
    if cw <= 0.0 or ch <= 0.0:
        return None
    return {"cx": cx, "cy": cy, "cw": cw, "ch": ch}


def _radios(r: Any) -> list[float] | None:
    """Normaliza un radio por esquina [tl,tr,br,bl] (px ≥ 0). None si no es una lista de 4 o si todos
    son 0 (entonces manda el `radio` uniforme). Si está, manda sobre `radio` en el render."""
    if not isinstance(r, (list, tuple)) or len(r) != 4:
        return None
    vals = [max(0.0, float(v)) if _num(v) else 0.0 for v in r]
    if all(v == 0.0 for v in vals):
        return None
    return vals


def _aplica_flip(c: dict[str, Any], out: dict[str, Any]) -> None:
    """Persiste `flip_h`/`flip_v` (volteo espejo horizontal/vertical) IN PLACE, SOLO si son True.

    Booleanos opcionales con default False: igual que `mezcla`, un documento sin volteo (o con volteo
    False) no ensucia el JSON ni cambia el render legado. Aplica a capas imagen y logo.
    """
    if bool(c.get("flip_h")):
        out["flip_h"] = True
    if bool(c.get("flip_v")):
        out["flip_v"] = True


def _capa_imagen(c: dict[str, Any]) -> dict[str, Any]:
    foco = c.get("foco") or [0.5, 0.5]
    _exige_doc(
        isinstance(foco, (list, tuple)) and len(foco) == 2 and all(_num(f) for f in foco),
        "El foco de la imagen debe ser [x,y] entre 0 y 1.",
    )
    zoom = c.get("zoom", 1)
    radio = c.get("radio", 0)
    radios = _radios(c.get("radios"))
    crop = _crop(c.get("crop"))
    radio_val = _entero(radio, "radio", minimo=0, defecto=0)
    zoom_val = _flotante(zoom, "zoom", minimo=1.0, maximo=6.0, defecto=1.0)
    img = {
        **_base(c),
        "tipo": "imagen",
        "objeto": str(c.get("objeto", "") or ""),
        "ajuste": c.get("ajuste") if c.get("ajuste") in _AJUSTES else "cover",
        "foco": [float(foco[0]), float(foco[1])],
        # Forma del recorte de la imagen: "rect" (def) o "elipse" (círculo si la caja es cuadrada).
        # `radio` redondea las esquinas del rect (px ≥ 0); se ignora con forma "elipse". Se persisten
        # siempre con su default para que el contrato sea estable; documentos viejos validan igual.
        "forma": c.get("forma") if c.get("forma") in _FORMAS_IMAGEN else "rect",
        "radio": radio_val,
        # Reencuadre dentro del marco: factor de acercamiento (1 = ajuste base). Acotado a [1, 6].
        "zoom": zoom_val,
        # `es_foto`: ESTA capa es el HUECO DE FOTO de la plantilla — la única donde entra la foto de
        # la pieza al aplicarla. Toda plantilla del estudio tiene exactamente una (obligatoria y
        # bloqueada en el editor). `objeto` guarda una foto de muestra para la miniatura.
        "es_foto": bool(c.get("es_foto", False)),
        "filtros": _filtros(c.get("filtros")),
        # Sombra del rectángulo de la imagen (opcional): solo se persiste si viene.
        "sombra": _sombra(c.get("sombra")),
    }
    # Aditivos y retrocompatibles: solo se persisten si vienen (no ensucian documentos viejos).
    #   `radios` (esquina por esquina) manda sobre `radio`; `crop` recorta la fuente (no destructivo).
    if radios is not None:
        img["radios"] = radios
    if crop is not None:
        img["crop"] = crop
    # Volteo (flip) horizontal/vertical: opcional, solo se persiste si True.
    _aplica_flip(c, img)
    return img


def _capa_texto(c: dict[str, Any]) -> dict[str, Any]:
    _exige_doc(c.get("binding") in _spec._BINDINGS, "El binding debe ser copy_in, etiqueta_default o nulo.")
    _exige_doc(_es_hex(c.get("color")), "El color del texto debe ser hex #RRGGBB.")
    chip = c.get("chip")
    chip_limpio = None
    if isinstance(chip, dict):
        _exige_doc(_es_hex(chip.get("color")), "El color del chip debe ser hex #RRGGBB.")
        chip_limpio = {
            "color": chip["color"],
            "pad_x": _entero(chip.get("pad_x", _CHIP_PAD_X), "chip.pad_x", defecto=_CHIP_PAD_X),
            "pad_y": _entero(chip.get("pad_y", _CHIP_PAD_Y), "chip.pad_y", defecto=_CHIP_PAD_Y),
            "radio": _entero(chip.get("radio", 0), "chip.radio", minimo=0, defecto=0),
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
    tamano_val = _entero(c.get("tamano", 64), "tamano", minimo=4, maximo=2000, defecto=64)
    peso_val = _entero(c.get("peso", 700), "peso", defecto=700)
    max_lineas_val = _entero(aj.get("max_lineas", 4), "auto_ajuste.max_lineas", minimo=1, maximo=50, defecto=4)
    tam_min_val = _entero(aj.get("tam_min", 40), "auto_ajuste.tam_min", minimo=4, maximo=2000, defecto=40)
    out: dict[str, Any] = {
        **_base(c),
        "tipo": "texto",
        "texto": str(c.get("texto", "")),
        "binding": c.get("binding"),
        "familia": familia,
        "tamano": tamano_val,
        "peso": peso_val,
        "color": c["color"],
        "alineacion": c.get("alineacion") if c.get("alineacion") in _ALINEACIONES else "izquierda",
        "mayusculas": bool(c.get("mayusculas", False)),
        "interlineado": float(c.get("interlineado", 1.14)),
        "interletra": float(c.get("interletra", 0)) if _num(c.get("interletra")) else 0.0,
        "auto_ajuste": {
            "max_lineas": max_lineas_val,
            "tam_min": tam_min_val,
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
    # Cursiva, subrayado y tachado (opcionales, retrocompatibles): booleanos con default False;
    # solo se persisten si vienen a True (igual que flip_h/flip_v). La cursiva solo surte efecto
    # en familias con itálica real (FAMILIAS_CON_CURSIVA en dibujar.mjs); el render ignora el flag
    # para el resto (nunca se sintetizan oblicuas). El tachado (línea a media altura) es
    # combinable con el subrayado; ninguno aplica al texto en arco (`curva`).
    if bool(c.get("cursiva")):
        out["cursiva"] = True
    if bool(c.get("subrayado")):
        out["subrayado"] = True
    if bool(c.get("tachado")):
        out["tachado"] = True
    # Texto curvo (texto en arco): solo se persiste si trae un radio != 0, para no ensuciar los
    # documentos antiguos ni alterar el render legado (sin `curva` => texto recto idéntico).
    curva = _curva(c.get("curva"))
    if curva is not None:
        out["curva"] = curva
    return out


def _capa_logo(c: dict[str, Any]) -> dict[str, Any]:
    tipo_logo = c.get("tipo_logo")
    _exige_doc(tipo_logo in _spec._TIPOS_LOGO, "El tipo de logo debe ser imagen o wordmark.")
    wm = c.get("wordmark") or {}
    logo = {
        **_base(c),
        "tipo": "logo",
        "tipo_logo": tipo_logo,
        "media_id": str(c.get("media_id", "") or ""),
        "wordmark": {
            "texto": str(wm.get("texto", "")),
            "color": wm["color"] if _es_hex(wm.get("color")) else "#FFFFFF",
            "fondo": wm["fondo"] if _es_hex(wm.get("fondo")) else "#E30613",
            "familia": wm["familia"] if isinstance(wm.get("familia"), str) and wm.get("familia") else "sans",
            "peso": _entero(wm.get("peso", 700), "wordmark.peso", defecto=700),
        },
    }
    # Volteo (flip) horizontal/vertical: opcional, solo se persiste si True.
    _aplica_flip(c, logo)
    return logo


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
    radios = _radios(c.get("radios"))
    radio_val = _entero(c.get("radio", 0), "radio", minimo=0, defecto=0)
    marco = {
        **_base(c),
        "tipo": "marco",
        "forma": forma,
        "relleno": relleno if _es_hex(relleno) else None,
        # Degradado del relleno (sustituye a `relleno` cuando viene). Solo se persiste si es válido.
        "relleno_degradado": _relleno_degradado(c.get("relleno_degradado")),
        "borde": borde_limpio,
        "radio": radio_val,
        # Sombra de la forma del marco (opcional): solo se persiste si viene.
        "sombra": _sombra(c.get("sombra")),
    }
    # `radios` (radio por esquina) manda sobre `radio`; aditivo, solo se persiste si viene.
    if radios is not None:
        marco["radios"] = radios
    return marco


def _capa_overlay(c: dict[str, Any]) -> dict[str, Any]:
    # `alto_frac` (fracción 0..1 de la caja que ocupa la banda) se ACOTA en vez de rechazarse para
    # no brickear documentos ya guardados con un float fuera de rango al re-validarlos. Lo no
    # numérico sí lanza DocumentoError (400 en español) como el resto de campos.
    alto_frac = _flotante(c.get("alto_frac", _spec._DEGRADADO_ALTO_FRAC), "alto_frac", defecto=_spec._DEGRADADO_ALTO_FRAC)
    overlay = {
        **_base(c),
        "tipo": "overlay",
        "color": c["color"] if _es_hex(c.get("color")) else "#111315",
        "alto_frac": min(1.0, max(0.0, alto_frac)),
        "alpha": _entero(c.get("alpha", _spec._DEGRADADO_ALPHA), "alpha", minimo=0, maximo=255, defecto=_spec._DEGRADADO_ALPHA),
    }
    # `lado` ("arriba"/"abajo"): la banda se pega al borde superior o al inferior (def). Solo se
    # persiste si es "arriba" (retrocompat: los overlays históricos no lo llevan y son inferiores).
    if c.get("lado") == "arriba":
        overlay["lado"] = "arriba"
    return overlay


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
    w = _entero(f["w"], "formato.w", minimo=16, maximo=8000)
    h = _entero(f["h"], "formato.h", minimo=16, maximo=8000)
    return {
        "w": w,
        "h": h,
        "safe_top": _entero(f.get("safe_top", 0), "formato.safe_top", minimo=0, defecto=0),
        "safe_bottom": _entero(f.get("safe_bottom", 0), "formato.safe_bottom", minimo=0, defecto=0),
        # Márgenes laterales (encuadre): aditivos y retrocompatibles. Documentos sin ellos => 0.
        "safe_left": _entero(f.get("safe_left", 0), "formato.safe_left", minimo=0, defecto=0),
        "safe_right": _entero(f.get("safe_right", 0), "formato.safe_right", minimo=0, defecto=0),
    }


# Máximo de huecos de foto por plantilla (collage). Más allá es un error de diseño; acotamos para
# no desbordar el editor ni el almacén de fotos por pieza.
MAX_HUECOS_FOTO = 12

# Máximo de capas por documento (incluidas capas hijas de grupos). Límite defensivo contra DoS.
MAX_CAPAS_DOCUMENTO = 200


def _contar_capas_recursivo(capas: list[dict[str, Any]] | None) -> int:
    """Cuenta el número TOTAL de capas incluyendo capas hijas de grupos."""
    if not isinstance(capas, list):
        return 0
    total = len(capas)
    for c in capas:
        if isinstance(c, dict) and c.get("tipo") == "grupo":
            total += _contar_capas_recursivo(c.get("capas"))
    return total


def _normalizar_hueco_foto(capas: list[dict[str, Any]]) -> None:
    """Acota los huecos de foto (`es_foto`) a un máximo de collage, IN PLACE.

    Una plantilla puede declarar VARIOS huecos (collage de 2..12 fotos): se conservan TODOS, en
    orden de aparición, hasta `MAX_HUECOS_FOTO`; los que sobren se desmarcan (estado de diseño
    inválido). NO auto-designa ninguno si no hay marcas —esa es decisión del diseñador (el estudio
    lo exige). `componer` coloca una foto por hueco vía `capas_foto`.
    """
    marcadas = [c for c in capas if c.get("tipo") == "imagen" and c.get("es_foto")]
    for c in marcadas[MAX_HUECOS_FOTO:]:
        c["es_foto"] = False


def validar(doc: Any) -> dict[str, Any]:
    """Valida y normaliza un Documento completo. Lanza `DocumentoError` (español) si algo falla."""
    _exige_doc(isinstance(doc, dict), "El documento debe ser un objeto JSON.")
    capas = doc.get("capas")
    _exige_doc(isinstance(capas, list), "El documento necesita una lista 'capas'.")
    fuentes = doc.get("fuentes") or {}
    capas_ok = [_validar_capa(c) for c in capas]
    total_capas = _contar_capas_recursivo(capas_ok)
    _exige_doc(
        total_capas <= MAX_CAPAS_DOCUMENTO,
        f"El documento tiene demasiadas capas ({total_capas}). Máximo permitido: {MAX_CAPAS_DOCUMENTO}.",
    )
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


def capas_foto(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """TODAS las capas que son hueco de foto (`es_foto`), en ORDEN de aparición en `capas`.

    Una plantilla de COLLAGE declara N huecos (2..12); el orden del array `capas` es el CONTRATO con
    el editor y con el almacén de fotos por hueco de la pieza (`fotos[i]` va al hueco i). Si no hay
    ninguna marcada, cae al respaldo legado de `capa_foto` (una sola, plantillas antiguas): lista de
    0 o 1. Las plantillas de solo texto/gráfica devuelven [].
    """
    marcadas = [
        c
        for c in (doc.get("capas") or [])
        if isinstance(c, dict) and c.get("tipo") == "imagen" and c.get("es_foto")
    ]
    if marcadas:
        return marcadas
    una = capa_foto(doc)
    return [una] if una is not None else []


def cuenta_huecos_foto(doc: dict[str, Any]) -> int:
    """Número de HUECOS de foto que tiene la plantilla (0 si es de solo texto/gráfica)."""
    return len(capas_foto(doc))


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
