#!/usr/bin/env python3
"""Compositor DETERMINISTA de piezas de "última hora" (breaking) para AMX.

Toma una FOTO y le superpone, de forma reproducible (no generativa), la
identidad de marca: degradado de legibilidad + pleca/etiqueta de breaking +
titular + logo (o wordmark de respaldo). Es determinista: no usa un modelo de
imagen. El copy lo redacta la skill aparte.

Por qué un script y no un prompt: el logo, la pleca y las zonas seguras son
SIEMPRE iguales por marca/formato. Codificarlos una vez = software determinista
que sale idéntico cada vez (la tesis de Keni: la IA diseña el proceso una vez y
deja de ser IA). Los valores de marca viven en `marcas.json` ([VERIFICAR]).

Uso:
    python3 componer.py --foto FOTO --marca unotv --titular "..." \
        [--formato vertical|feed|cuadrado] [--etiqueta "ÚLTIMA HORA"] \
        [--logo RUTA.png] [--salida SALIDA.png] [--config marcas.json]

Salida: escribe el PNG y, por stdout, un resumen legible + bloque DATOS para la
skill (ruta, tamaño, marca, formato, si se usó logo real o wordmark de respaldo).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError:
    sys.stderr.write(
        "ERROR: falta Pillow. Instálalo una vez con:  python3 -m pip install pillow\n"
    )
    raise SystemExit(2)


# --------------------------------------------------------------------------- #
# Fuentes (busca en el sistema; cae a la fuente por defecto de Pillow)         #
# --------------------------------------------------------------------------- #

# Candidatas por estilo. Son rutas/comunes en macOS y Linux; si ninguna existe
# se usa la fuente por defecto de Pillow (escalable desde Pillow 10).
_FUENTES_BOLD = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/Library/Fonts/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
]
_FUENTES_CONDENSADA = [
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/System/Library/Fonts/Supplemental/Arial Narrow Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    "Impact.ttf",
] + _FUENTES_BOLD


def cargar_fuente(tam: int, condensada: bool = False):
    """Primera fuente disponible al tamaño pedido; default escalable si no hay."""
    candidatas = _FUENTES_CONDENSADA if condensada else _FUENTES_BOLD
    for ruta in candidatas:
        try:
            return ImageFont.truetype(ruta, tam)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=tam)  # Pillow >= 10
    except TypeError:
        return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# Utilidades de color y texto                                                  #
# --------------------------------------------------------------------------- #


def hex_a_rgb(valor: str) -> tuple[int, int, int]:
    s = (valor or "").lstrip("#")
    if len(s) != 6:
        return (17, 19, 21)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def ancho_texto(draw: ImageDraw.ImageDraw, texto: str, fuente) -> float:
    return draw.textlength(texto, font=fuente)


def envolver(draw: ImageDraw.ImageDraw, texto: str, fuente, max_ancho: float) -> list[str]:
    """Word-wrap codicioso al ancho disponible (parte palabras larguísimas)."""
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        palabras = parrafo.split()
        if not palabras:
            continue
        actual = palabras[0]
        for palabra in palabras[1:]:
            tentativa = f"{actual} {palabra}"
            if ancho_texto(draw, tentativa, fuente) <= max_ancho:
                actual = tentativa
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


def ajustar_titular(
    draw: ImageDraw.ImageDraw,
    texto: str,
    max_ancho: float,
    max_alto: float,
    *,
    condensada: bool,
    tam_max: int,
    tam_min: int = 40,
    max_lineas: int = 4,
):
    """Baja el tamaño de fuente hasta que el titular cabe en ancho×alto y ≤max_lineas."""
    for tam in range(tam_max, tam_min - 1, -2):
        fuente = cargar_fuente(tam, condensada=condensada)
        lineas = envolver(draw, texto, fuente, max_ancho)
        alto_linea = int(tam * 1.14)
        if len(lineas) <= max_lineas and len(lineas) * alto_linea <= max_alto:
            return fuente, lineas, alto_linea
    # No cupo ni al mínimo: recorta a max_lineas con elipsis.
    fuente = cargar_fuente(tam_min, condensada=condensada)
    lineas = envolver(draw, texto, fuente, max_ancho)[:max_lineas]
    if lineas:
        lineas[-1] = lineas[-1].rstrip() + "…"
    return fuente, lineas, int(tam_min * 1.14)


# --------------------------------------------------------------------------- #
# Composición                                                                  #
# --------------------------------------------------------------------------- #


def recorte_cubriente(img: Image.Image, w: int, h: int) -> Image.Image:
    """Redimensiona y recorta al centro para CUBRIR w×h sin deformar (object-fit:cover)."""
    return ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=(0.5, 0.45))


def lienzo_placeholder(w: int, h: int, tinta) -> Image.Image:
    """Lienzo w×h gris con un hint centrado 'Sube una foto' (hueco de la foto vacío).

    Sustituye a la foto cuando aún no hay imagen: la plantilla (logo + pleca + titular) se
    estampa igual encima, así se ve la marca con el copy y solo falta subir la foto. El gris
    es neutro y suficientemente oscuro para que el texto blanco del titular siga legible.
    """
    gris = (63, 66, 70)  # gris medio-oscuro, neutro
    img = Image.new("RGBA", (w, h), gris + (255,))
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    # Recuadro punteado central como "marco de foto vacío".
    lado = int(min(w, h) * 0.30)
    x0, y0, x1, y1 = cx - lado, cy - lado, cx + lado, cy + lado
    borde = (150, 154, 158)
    paso = 28
    for x in range(x0, x1, paso):  # bordes superior e inferior punteados
        draw.line([(x, y0), (min(x + paso // 2, x1), y0)], fill=borde, width=4)
        draw.line([(x, y1), (min(x + paso // 2, x1), y1)], fill=borde, width=4)
    for y in range(y0, y1, paso):  # bordes izquierdo y derecho punteados
        draw.line([(x0, y), (x0, min(y + paso // 2, y1))], fill=borde, width=4)
        draw.line([(x1, y), (x1, min(y + paso // 2, y1))], fill=borde, width=4)
    # Texto del hint, centrado.
    fuente = cargar_fuente(max(28, int(min(w, h) * 0.05)))
    hint = "Sube una foto"
    tw = ancho_texto(draw, hint, fuente)
    draw.text((cx - tw / 2, cy - lado - 64), hint, font=fuente, fill=borde)
    return img


def degradado_inferior(w: int, h: int, color_rgb, alto_frac: float = 0.58, alpha_max: int = 238) -> Image.Image:
    """Capa RGBA con degradado oscuro de abajo (opaco) hacia arriba (transparente)."""
    band = max(1, int(h * alto_frac))
    rampa = Image.new("L", (1, band), 0)
    px = rampa.load()
    for y in range(band):
        t = y / max(1, band - 1)
        px[0, y] = int(alpha_max * (t ** 1.5))
    rampa = rampa.resize((w, band))
    capa = Image.new("RGBA", (w, h), color_rgb + (0,))
    alpha = Image.new("L", (w, h), 0)
    alpha.paste(rampa, (0, h - band))
    capa.putalpha(alpha)
    return capa


def dibujar_chip_etiqueta(draw, x, y_bottom, texto, fuente, rojo, blanco):
    """Pleca de breaking: caja roja con la etiqueta en blanco. Devuelve su alto."""
    pad_x, pad_y = 24, 14
    izq, sup, der, inf = draw.textbbox((0, 0), texto, font=fuente)
    tw, th = der - izq, inf - sup
    chip_w = tw + pad_x * 2
    chip_h = th + pad_y * 2
    y_top = y_bottom - chip_h
    draw.rectangle([x, y_top, x + chip_w, y_bottom], fill=rojo)
    draw.text((x + pad_x - izq, y_top + pad_y - sup), texto, font=fuente, fill=blanco)
    return chip_h


# Esquinas validas para colocar el logo (espejo de `plantillas_marca.POSICIONES`).
POSICIONES_LOGO = (
    "superior-izquierda",
    "superior-derecha",
    "inferior-izquierda",
    "inferior-derecha",
)


def _esquina_logo(posicion: str, ancho: int, alto: int, w: int, h: int,
                  margin: int, safe_top: int, safe_bottom: int) -> tuple[int, int]:
    """Coordenada (x, y) de la esquina superior-izquierda del logo segun `posicion`.

    Respeta el margen lateral y las zonas seguras (`safe_top`/`safe_bottom`). Default
    (`superior-izquierda`) reproduce el comportamiento previo (x=margin, y=safe_top+24).
    """
    pos = posicion if posicion in POSICIONES_LOGO else POSICIONES_LOGO[0]
    izquierda = "izquierda" in pos
    superior = "superior" in pos
    x = margin if izquierda else (w - margin - ancho)
    y = (safe_top + 24) if superior else (h - safe_bottom - margin - alto)
    return x, y


def dibujar_logo(img, draw, cfg_marca, x, y, blanco, rojo, *, posicion=None,
                 w=None, h=None, margin=56, safe_top=60, safe_bottom=96):
    """Pega el logo real si existe; si no, dibuja un wordmark de respaldo. Devuelve usado_real.

    Si se pasan `posicion` + dimensiones del lienzo (`w`/`h`), coloca el logo/wordmark en la
    esquina indicada (4 esquinas, respetando margenes y zonas seguras). Sin `posicion` (o sin
    `w`/`h`), usa la coordenada (`x`, `y`) que reciba: retrocompat = superior-izquierda.
    """
    ruta_logo = (cfg_marca.get("logo") or "").strip()
    if ruta_logo and Path(ruta_logo).is_file():
        try:
            logo = Image.open(ruta_logo).convert("RGBA")
            destino_h = 96
            ratio = destino_h / logo.height
            ancho = max(1, int(logo.width * ratio))
            logo = logo.resize((ancho, destino_h), Image.LANCZOS)
            if posicion is not None and w is not None and h is not None:
                x, y = _esquina_logo(posicion, ancho, destino_h, w, h, margin, safe_top, safe_bottom)
            img.alpha_composite(logo, (x, y))
            return True
        except OSError:
            pass
    # Wordmark de respaldo: chip blanco con el nombre de marca en rojo.
    texto = cfg_marca.get("wordmark") or cfg_marca.get("nombre") or "AMX"
    fuente = cargar_fuente(40)
    izq, sup, der, inf = draw.textbbox((0, 0), texto, font=fuente)
    tw, th = der - izq, inf - sup
    pad_x, pad_y = 20, 12
    chip_w = tw + pad_x * 2
    chip_h = th + pad_y * 2
    if posicion is not None and w is not None and h is not None:
        x, y = _esquina_logo(posicion, chip_w, chip_h, w, h, margin, safe_top, safe_bottom)
    draw.rounded_rectangle([x, y, x + chip_w, y + chip_h], radius=10, fill=blanco)
    draw.text((x + pad_x - izq, y + pad_y - sup), texto, font=fuente, fill=rojo)
    return False


def aplicar_overlays(img, rutas):
    """Superpone PNGs transparentes a TAMAÑO COMPLETO (escalados al lienzo), encima de todo.

    Es el camino fiel al flujo del equipo: el "archivo de breaking" y la "marca de agua"
    ya son artes de la casa (logo + pleca diseñados), así que se componen tal cual, no se
    redibujan. Devuelve (aplicados, faltantes)."""
    aplicados, faltantes = [], []
    for r in rutas:
        if not r:
            continue
        p = Path(r)
        if not p.is_file():
            faltantes.append(str(r))
            continue
        try:
            ov = Image.open(p).convert("RGBA")
        except OSError:
            faltantes.append(str(r))
            continue
        if ov.size != img.size:
            ov = ov.resize(img.size, Image.LANCZOS)
        img.alpha_composite(ov)
        aplicados.append(str(p))
    return aplicados, faltantes


def componer(args) -> dict:
    cfg_path = Path(args.config) if args.config else Path(__file__).with_name("marcas.json")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

    # Resolver marca (acepta alias clarosports/claro_sports).
    clave = args.marca.strip().lower().replace("_", "-")
    if clave == "clarosports":
        clave = "claro-sports"
    marcas = cfg.get("marcas", {})
    if clave not in marcas:
        raise SystemExit(f"ERROR: marca '{args.marca}' desconocida. Opciones: {', '.join(marcas)}")
    m = dict(marcas[clave])
    if args.logo:  # --logo de la CLI pisa el de marcas.json
        m["logo"] = args.logo

    # Overlays precargados de la marca (marca de agua + archivo de breaking de la casa)
    # + los que pase la CLI. Se superponen a tamaño completo al final.
    overlays = [m.get("marca_agua"), m.get("overlay_breaking")]
    overlays += list(getattr(args, "marca_agua", None) or [])
    overlays += list(args.overlay or [])
    overlays = [r for r in overlays if r]
    tiene_overlays = any(Path(r).is_file() for r in overlays)

    formatos = cfg.get("formatos", {})
    fclave = (args.formato or "vertical").strip().lower()
    if fclave not in formatos:
        raise SystemExit(f"ERROR: formato '{args.formato}' desconocido. Opciones: {', '.join(formatos)}")
    f = formatos[fclave]
    w, h = f["w"], f["h"]
    safe_top, safe_bottom = f.get("safe_top", 60), f.get("safe_bottom", 96)

    rojo = hex_a_rgb(m["rojo"])
    tinta = hex_a_rgb(m["tinta"])
    blanco = hex_a_rgb(m.get("blanco", "#FFFFFF"))
    margin = 56

    # Lienzo base: la FOTO recortada al formato, o —si no hay foto— un PLACEHOLDER
    # gris con un hint "Sube una foto". El placeholder deja la plantilla (logo + pleca +
    # titular) lista y solo a falta de la foto; subirla después recompone con la foto real.
    placeholder = bool(getattr(args, "placeholder", False)) or not (args.foto or "").strip()
    if placeholder:
        img = lienzo_placeholder(w, h, tinta)
        draw = ImageDraw.Draw(img)
    else:
        foto_path = Path(args.foto)
        if not foto_path.is_file():
            raise SystemExit(f"ERROR: no existe la foto: {foto_path}")
        base = Image.open(foto_path)
        base = ImageOps.exif_transpose(base).convert("RGBA")
        img = recorte_cubriente(base, w, h)
        draw = ImageDraw.Draw(img)

    # 2) Titular (de abajo hacia arriba, por encima de la zona insegura inferior).
    #    El degradado de legibilidad solo se pone si hay titular sintético; con overlays
    #    de la casa la pieza ya trae su diseño y no se oscurece la foto.
    titular = (args.titular or "").strip()
    if m.get("titular_mayusculas"):
        titular = titular.upper()
    bottom_limit = h - safe_bottom - margin
    headline_top = bottom_limit
    if titular:
        img.alpha_composite(degradado_inferior(w, h, tinta))
        max_ancho = w - margin * 2
        max_alto = h * 0.42
        tam_max = 88 if fclave == "vertical" else 78
        fuente, lineas, alto_linea = ajustar_titular(
            draw, titular, max_ancho, max_alto,
            condensada=bool(m.get("titular_condensada")), tam_max=tam_max,
        )
        bloque_h = len(lineas) * alto_linea
        headline_top = bottom_limit - bloque_h
        y = headline_top
        for ln in lineas:
            draw.text((margin + 2, y + 2), ln, font=fuente, fill=(0, 0, 0))  # sombra
            draw.text((margin, y), ln, font=fuente, fill=blanco)
            y += alto_linea

    # 3) Pleca / etiqueta de breaking SINTÉTICA, justo encima del titular.
    #    Si hay overlays de la casa, por defecto NO se dibuja (el overlay ya trae su pleca).
    if args.etiqueta is not None:
        etiqueta = args.etiqueta
    elif tiene_overlays:
        etiqueta = ""
    else:
        etiqueta = m.get("etiqueta_default", "ÚLTIMA HORA")
    etiqueta = (etiqueta or "").strip().upper()
    if etiqueta:
        chip_bottom = headline_top - 22
        f_et = cargar_fuente(36)
        dibujar_chip_etiqueta(draw, margin, chip_bottom, etiqueta, f_et, rojo, blanco)

    # 4) Logo sintético solo si NO hay overlays (el overlay de la casa ya trae el logo).
    logo_real = False
    if not tiene_overlays:
        logo_real = dibujar_logo(
            img, draw, m, margin, safe_top + 24, blanco, rojo,
            posicion=m.get("logo_posicion"), w=w, h=h,
            margin=margin, safe_top=safe_top, safe_bottom=safe_bottom,
        )

    # 5) Overlays a TAMAÑO COMPLETO, encima de todo (marca de agua + archivo de breaking).
    overlays_aplicados, overlays_faltantes = aplicar_overlays(img, overlays)

    # Guardar.
    if args.salida:
        salida = Path(args.salida)
    elif placeholder:
        salida = Path(f"plantilla-{clave}-{fclave}.png")
    else:
        salida = foto_path.with_name(f"{foto_path.stem}-breaking-{clave}-{fclave}.png")
    salida.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(salida, "PNG")

    return {
        "salida": str(salida),
        "marca": m.get("nombre", clave),
        "marca_id": clave,
        "formato": fclave,
        "tamano": f"{w}x{h}",
        "placeholder": placeholder,
        "etiqueta": etiqueta,
        "titular": titular,
        "logo_real": logo_real,
        "logo_via_overlay": tiene_overlays,
        "overlays": overlays_aplicados,
        "overlays_faltantes": overlays_faltantes,
        "verificar": m.get("verificar", ""),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Compositor determinista de piezas de breaking para AMX.")
    p.add_argument("--foto", default=None,
                   help="Ruta de la foto. Si se omite (o con --placeholder), se compone una "
                        "plantilla con el hueco de la foto vacío (placeholder 'Sube una foto').")
    p.add_argument("--placeholder", action="store_true",
                   help="Compone la plantilla SIN foto: fondo gris con hint 'Sube una foto'.")
    p.add_argument("--marca", required=True, help="unotv | claro-sports")
    p.add_argument("--titular", default="", help="Titular corto (el hecho) sobreimpreso.")
    p.add_argument("--formato", default="vertical", help="vertical | feed | cuadrado")
    p.add_argument("--etiqueta", default=None, help="Texto de la pleca (def. por marca). '' para omitir.")
    p.add_argument("--logo", default=None, help="Ruta PNG del logo (sobrescribe el de marcas.json).")
    p.add_argument("--overlay", action="append", default=None,
                   help="PNG transparente a superponer a tamaño completo (p. ej. el archivo de breaking de la casa). Repetible.")
    p.add_argument("--marca-agua", dest="marca_agua", action="append", default=None,
                   help="PNG de marca de agua a superponer a tamaño completo. Repetible.")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG (def. junto a la foto).")
    p.add_argument("--config", default=None, help="Ruta de marcas.json (def. junto al script).")
    args = p.parse_args()

    info = componer(args)

    print("Pieza de breaking compuesta (determinista).\n")
    print(f"  Archivo : {info['salida']}")
    print(f"  Marca   : {info['marca']}  ·  Formato: {info['formato']} ({info['tamano']})")
    print(f"  Pleca   : {info['etiqueta'] or '(sin pleca sintética)'}")
    print(f"  Titular : {info['titular'] or '(sin titular)'}")
    if info.get("overlays"):
        print("  Overlays: " + ", ".join(Path(o).name for o in info["overlays"]) + " (a tamaño completo, encima)")
        print("  Logo    : viene del overlay de la casa (marca de agua / archivo de breaking).")
    elif not info["logo_real"]:
        print("  Logo    : WORDMARK DE RESPALDO (no se encontró el PNG del logo real).")
        print("            Aporta el logo en marcas.json ('logo') o con --logo para la versión final.")
    else:
        print("  Logo    : logo real aplicado.")
    if info.get("overlays_faltantes"):
        print("  AVISO   : overlays no encontrados: " + ", ".join(info["overlays_faltantes"]))
    if info["verificar"]:
        print(f"  [VERIFICAR] {info['verificar']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
