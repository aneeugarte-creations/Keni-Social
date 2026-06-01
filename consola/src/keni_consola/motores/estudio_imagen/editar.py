#!/usr/bin/env python3
"""Caja de herramientas DETERMINISTA del Estudio de imagen (sin IA).

Operaciones exactas y reproducibles sobre una imagen, con Pillow: la recortan,
redimensionan, comprimen o componen texto de marca.

Subcomandos:
  recortar       recorte cubriente (object-fit:cover) a un formato de red, o a todos
  redimensionar  cambia el tamaño manteniendo proporción (por ancho, alto o lado máx.)
  comprimir      baja el PESO del archivo a un objetivo conservando el tamaño (formato "full")
  extender       encaja la foto en un formato extendiendo SOLO el fondo uniforme (cielo/negro)
  placa          tarjeta de texto (cita o dato) en marca, con o sin foto de fondo

Uso:
  python3 editar.py recortar --foto FOTO --formato feed [--salida SAL]
  python3 editar.py recortar --foto FOTO --todos [--salida-dir DIR]
  python3 editar.py redimensionar --foto FOTO --max 1080 [--salida SAL]
  python3 editar.py comprimir --foto FOTO --peso-max-mb 2 [--max 2560] [--salida SAL]
  python3 editar.py extender --foto FOTO --formato feed [--metodo borde] [--salida SAL]
  python3 editar.py placa --texto "..." --marca unotv --formato feed \
      [--fuente-cita "— Autor"] [--foto FOTO] [--salida SAL]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageStat
except ImportError:
    sys.stderr.write("ERROR: falta Pillow. Instálalo con:  python3 -m pip install pillow\n")
    raise SystemExit(2)


# Formatos de salida (ancho x alto). Mismas medidas que marcas.json del breaking.
FORMATOS = {
    "vertical": (1080, 1920),   # 9:16 — Reels / TikTok / Shorts / Stories
    "feed": (1080, 1350),       # 4:5  — post IG / Facebook
    "cuadrado": (1080, 1080),   # 1:1
    "horizontal": (1920, 1080),  # 16:9 — YouTube / web
}

# Defaults internos por marca, por si no se encuentra el marcas.json hermano del
# breaking-express. No duplicamos TODO el JSON: solo los tokens que la placa usa
# (color de acento, tinta de fondo, blanco, y estilo de titular por marca).
MARCAS_DEFAULT = {
    "unotv": {
        "nombre": "UnoTV",
        "rojo": "#E30613",
        "tinta": "#111315",
        "blanco": "#FFFFFF",
        "titular_mayusculas": False,
        "titular_condensada": False,
    },
    "claro-sports": {
        "nombre": "Claro Sports",
        "rojo": "#CF2E2E",
        "tinta": "#0A0A0A",
        "blanco": "#FFFFFF",
        "titular_mayusculas": True,
        "titular_condensada": True,
    },
}


# --------------------------------------------------------------------------- #
# Fuentes y texto (copiados de breaking-express/componer.py para que el skill   #
# sea autónomo; misma lógica, sin importar nada del hermano).                   #
# --------------------------------------------------------------------------- #

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


def hex_a_rgb(valor: str) -> tuple[int, int, int]:
    s = (valor or "").lstrip("#")
    if len(s) != 6:
        return (17, 19, 21)
    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _ancho_texto(draw: "ImageDraw.ImageDraw", texto: str, fuente) -> float:
    return draw.textlength(texto, font=fuente)


def envolver(draw: "ImageDraw.ImageDraw", texto: str, fuente, max_ancho: float) -> list[str]:
    """Word-wrap codicioso al ancho disponible (parte palabras larguísimas)."""
    lineas: list[str] = []
    for parrafo in texto.split("\n"):
        palabras = parrafo.split()
        if not palabras:
            continue
        actual = palabras[0]
        for palabra in palabras[1:]:
            tentativa = f"{actual} {palabra}"
            if _ancho_texto(draw, tentativa, fuente) <= max_ancho:
                actual = tentativa
            else:
                lineas.append(actual)
                actual = palabra
        lineas.append(actual)
    return lineas


def ajustar_titular(
    draw: "ImageDraw.ImageDraw",
    texto: str,
    max_ancho: float,
    max_alto: float,
    *,
    condensada: bool,
    tam_max: int,
    tam_min: int = 40,
    max_lineas: int = 4,
):
    """Baja el tamaño de fuente hasta que el texto cabe en ancho×alto y ≤max_lineas."""
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


def recorte_cubriente(img: "Image.Image", w: int, h: int) -> "Image.Image":
    """Redimensiona y recorta al centro para CUBRIR w×h sin deformar (object-fit:cover)."""
    return ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=(0.5, 0.45))


def degradado_inferior(w: int, h: int, color_rgb, alto_frac: float = 0.62, alpha_max: int = 242) -> "Image.Image":
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


# --------------------------------------------------------------------------- #
# Resolución de marca                                                           #
# --------------------------------------------------------------------------- #


def _resolver_clave_marca(marca: str) -> str:
    """Normaliza el id de marca (acepta alias clarosports/claro_sports)."""
    clave = (marca or "").strip().lower().replace("_", "-")
    if clave == "clarosports":
        clave = "claro-sports"
    return clave


def cargar_marca(marca: str) -> dict:
    """Lee tokens de la marca del marcas.json hermano; si no existe, cae a los
    defaults internos. Resuelve la ruta con pathlib relativo al script
    (marcas.json en el mismo dir, relocalizado desde breaking-express) y NO
    duplica todo el JSON: solo toma los tokens que la placa necesita."""
    clave = _resolver_clave_marca(marca)
    cfg_path = Path(__file__).resolve().parent / "marcas.json"
    m: dict | None = None
    if cfg_path.is_file():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            marcas = cfg.get("marcas", {})
            if clave in marcas:
                m = dict(marcas[clave])
        except (OSError, ValueError):
            m = None
    if m is None:
        if clave not in MARCAS_DEFAULT:
            opciones = ", ".join(sorted(set(MARCAS_DEFAULT) | set(_marcas_disponibles(cfg_path))))
            raise SystemExit(f"ERROR: marca '{marca}' desconocida. Opciones: {opciones}")
        m = dict(MARCAS_DEFAULT[clave])
    m["_id"] = clave
    return m


def _marcas_disponibles(cfg_path: Path) -> list[str]:
    if not cfg_path.is_file():
        return []
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return list(cfg.get("marcas", {}))
    except (OSError, ValueError):
        return []


# --------------------------------------------------------------------------- #
# Operaciones                                                                   #
# --------------------------------------------------------------------------- #


def abrir(path: str) -> "Image.Image":
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ERROR: no existe la imagen: {p}")
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def recortar(args) -> dict:
    img = abrir(args.foto)
    stem = Path(args.foto).stem
    centro = (args.cx, args.cy)
    objetivos = list(FORMATOS) if args.todos else [args.formato]
    salidas = []
    for fmt in objetivos:
        if fmt not in FORMATOS:
            raise SystemExit(f"ERROR: formato '{fmt}' desconocido. Opciones: {', '.join(FORMATOS)}")
        w, h = FORMATOS[fmt]
        pieza = ImageOps.fit(img, (w, h), method=Image.LANCZOS, centering=centro)
        if args.salida and not args.todos:
            destino = Path(args.salida)
        else:
            base_dir = Path(args.salida_dir) if args.salida_dir else Path(args.foto).parent
            destino = base_dir / f"{stem}-{fmt}.png"
        destino.parent.mkdir(parents=True, exist_ok=True)
        pieza.save(destino, "PNG")
        salidas.append({"formato": fmt, "tamano": f"{w}x{h}", "salida": str(destino)})
    return {"op": "recortar", "salidas": salidas}


def redimensionar(args) -> dict:
    img = abrir(args.foto)
    w0, h0 = img.size
    if args.max:
        ratio = args.max / max(w0, h0)
        w, h = round(w0 * ratio), round(h0 * ratio)
    elif args.ancho and args.alto:
        w, h = args.ancho, args.alto
    elif args.ancho:
        w = args.ancho
        h = round(h0 * (args.ancho / w0))
    elif args.alto:
        h = args.alto
        w = round(w0 * (args.alto / h0))
    else:
        raise SystemExit("ERROR: indica --max, --ancho y/o --alto.")
    pieza = img.resize((max(1, w), max(1, h)), Image.LANCZOS)
    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(f"{Path(args.foto).stem}-{w}x{h}.png")
    destino.parent.mkdir(parents=True, exist_ok=True)
    pieza.save(destino, "PNG")
    return {"op": "redimensionar", "salidas": [{"tamano": f"{w}x{h}", "salida": str(destino)}]}


def _codificar(img: "Image.Image", fmt: str, calidad: int) -> bytes:
    """Codifica la imagen a bytes en memoria con la calidad dada (jpg | webp)."""
    buf = io.BytesIO()
    if fmt == "webp":
        img.save(buf, "WEBP", quality=calidad, method=6)
    else:
        img.save(buf, "JPEG", quality=calidad, optimize=True, progressive=True)
    return buf.getvalue()


def _mejor_calidad(img: "Image.Image", fmt: str, calidad_min: int, objetivo: int):
    """Mayor calidad cuyo peso ≤ objetivo (busca de alta a baja). (bytes, q) o (None, None)."""
    for q in range(92, calidad_min - 1, -4):
        data = _codificar(img, fmt, q)
        if len(data) <= objetivo:
            return data, q
    return None, None


def comprimir(args) -> dict:
    """Formato "full": baja el PESO del archivo a un objetivo conservando el tamaño.

    Para eventos masivos con internet malo: el original no sube. Busca la calidad
    JPEG/WebP más alta que quepa bajo el peso objetivo, conservando las dimensiones
    (con un resize pequeño opcional vía --max). Si ni la calidad mínima alcanza el
    objetivo, reduce el tamaño en pasos hasta lograrlo (lo deja anotado).
    """
    img = abrir(args.foto)
    w0, h0 = img.size
    fmt = (args.formato_archivo or "jpg").strip().lower()
    if fmt not in ("jpg", "webp"):
        raise SystemExit(f"ERROR: formato-archivo '{fmt}' desconocido. Opciones: jpg, webp")
    if args.peso_max_mb <= 0:
        raise SystemExit("ERROR: --peso-max-mb debe ser > 0.")
    objetivo = int(args.peso_max_mb * 1024 * 1024)
    calidad_min = max(10, min(95, int(args.calidad_min)))
    piso = 1080  # no bajamos del lado largo de las redes al reducir tamaño

    if args.max and max(w0, h0) > args.max:
        ratio = args.max / max(w0, h0)
        img = img.resize((max(1, round(w0 * ratio)), max(1, round(h0 * ratio))), Image.LANCZOS)
    redujo = img.size != (w0, h0)

    data, q = _mejor_calidad(img, fmt, calidad_min, objetivo)
    while data is None and max(img.size) > piso:
        img = img.resize((max(1, round(img.size[0] * 0.9)), max(1, round(img.size[1] * 0.9))), Image.LANCZOS)
        redujo = True
        data, q = _mejor_calidad(img, fmt, calidad_min, objetivo)
    if data is None:  # mejor esfuerzo al piso, con la calidad mínima
        data, q = _codificar(img, fmt, calidad_min), calidad_min

    ext = "jpg" if fmt == "jpg" else "webp"
    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(f"{Path(args.foto).stem}-full.{ext}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(data)

    return {
        "op": "comprimir",
        "formato_archivo": ext,
        "calidad": q,
        "peso_kb": round(len(data) / 1024),
        "peso_objetivo_kb": round(objetivo / 1024),
        "bajo_objetivo": len(data) <= objetivo,
        "redujo_tamano": redujo,
        "salidas": [{"tamano": f"{img.size[0]}x{img.size[1]}", "salida": str(destino)}],
    }


def _std_borde(img: "Image.Image", lado: str, prof: int):
    """(desviación máx. de color, color medio RGB) de la franja de borde `lado`."""
    w0, h0 = img.size
    if lado == "arriba":
        caja = (0, 0, w0, min(h0, prof))
    elif lado == "abajo":
        caja = (0, max(0, h0 - prof), w0, h0)
    elif lado == "izquierda":
        caja = (0, 0, min(w0, prof), h0)
    else:  # derecha
        caja = (max(0, w0 - prof), 0, w0, h0)
    st = ImageStat.Stat(img.crop(caja))
    return max(st.stddev[:3]), tuple(round(c) for c in st.mean[:3])


def _banda(img: "Image.Image", lado: str, px: int, metodo: str) -> "Image.Image":
    """Franja de relleno para extender el fondo por un lado, sin inventar contenido."""
    w0, h0 = img.size
    if lado in ("arriba", "abajo"):
        if metodo == "color":
            _, color = _std_borde(img, lado, min(h0, 16))
            return Image.new("RGB", (w0, px), color)
        linea = img.crop((0, 0, w0, 1)) if lado == "arriba" else img.crop((0, h0 - 1, w0, h0))
        return linea.resize((w0, px), Image.LANCZOS)
    if metodo == "color":
        _, color = _std_borde(img, lado, min(w0, 16))
        return Image.new("RGB", (px, h0), color)
    linea = img.crop((0, 0, 1, h0)) if lado == "izquierda" else img.crop((w0 - 1, 0, w0, h0))
    return linea.resize((px, h0), Image.LANCZOS)


def extender(args) -> dict:
    """Encaja la foto en un formato extendiendo SOLO el fondo uniforme (cielo/negro).

    Cuando la foto no cabe completa en el formato (p. ej. 4:5) y lo que falta es solo
    cielo o solo el negro del fondo, se AÑADE lienzo por ese lado (no se recorta al
    sujeto). El relleno estira el borde uniforme: no inventa contenido. Si ningún borde
    es uniforme o haría falta extender demasiado, cae al recorte cubriente normal y lo
    marca (`extension_segura: false`): ahí pasa a `expandir.py`, que rellena el fondo con
    IA. --forzar extiende igualmente aunque el borde no sea uniforme.
    """
    img = abrir(args.foto)
    w0, h0 = img.size
    fclave = (args.formato or "feed").strip().lower()
    if fclave not in FORMATOS:
        raise SystemExit(f"ERROR: formato '{args.formato}' desconocido. Opciones: {', '.join(FORMATOS)}")
    metodo = (args.metodo or "borde").strip().lower()
    if metodo not in ("borde", "color"):
        raise SystemExit(f"ERROR: metodo '{metodo}' desconocido. Opciones: borde, color")
    tw, th = FORMATOS[fclave]
    objetivo_ratio = tw / th
    r0 = w0 / h0
    umbral = float(args.umbral_uniforme)
    max_ext = float(args.max_ext)

    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(f"{Path(args.foto).stem}-{fclave}-ext.png")
    destino.parent.mkdir(parents=True, exist_ok=True)

    def _resultado(aplicado, segura, lados_info, motivo):
        return {
            "op": "extender",
            "formato": fclave,
            "aplicado": aplicado,
            "extension_segura": segura,
            "metodo": metodo,
            "lados": lados_info,
            "motivo": motivo,
            "salidas": [{"formato": fclave, "tamano": f"{tw}x{th}", "salida": str(destino)}],
        }

    # Ya está en la proporción del formato: nada que inventar, solo redimensiona.
    if abs(r0 - objetivo_ratio) <= 0.005:
        img.resize((tw, th), Image.LANCZOS).save(destino, "PNG")
        return _resultado("resize", True, [], "")

    if r0 > objetivo_ratio:  # más ancha que el formato -> añadir ALTO (vertical)
        final_w, final_h = w0, round(w0 / objetivo_ratio)
        extra, dim_final, lados = final_h - h0, final_h, ("arriba", "abajo")
    else:  # más alta/estrecha -> añadir ANCHO (horizontal)
        final_w, final_h = round(h0 * objetivo_ratio), h0
        extra, dim_final, lados = final_w - w0, final_w, ("izquierda", "derecha")

    vertical = lados[0] in ("arriba", "abajo")
    prof = max(2, min(16, h0 if vertical else w0))
    std_a, _ = _std_borde(img, lados[0], prof)
    std_b, _ = _std_borde(img, lados[1], prof)
    unif_a, unif_b = std_a < umbral, std_b < umbral
    frac = extra / dim_final
    segura = (unif_a or unif_b) and frac <= max_ext

    if not segura and not args.forzar:
        motivos = []
        if not (unif_a or unif_b):
            motivos.append("ningún borde del fondo es uniforme (no es solo cielo/negro)")
        if frac > max_ext:
            motivos.append(f"haría falta extender {frac:.0%} (máximo {max_ext:.0%})")
        ImageOps.fit(img, (tw, th), method=Image.LANCZOS, centering=(0.5, 0.4)).save(destino, "PNG")
        return _resultado("recorte", False, [], "; ".join(motivos))

    # Reparto del 'extra': solo por el/los lado(s) uniforme(s) (con --forzar, se reparte).
    if unif_a and unif_b:
        a, b = extra // 2, extra - extra // 2
    elif unif_a:
        a, b = extra, 0
    elif unif_b:
        a, b = 0, extra
    else:  # --forzar sin bordes uniformes
        a, b = extra // 2, extra - extra // 2

    canvas = Image.new("RGB", (final_w, final_h))
    if vertical:
        canvas.paste(img, (0, a))
        if a > 0:
            canvas.paste(_banda(img, "arriba", a, metodo), (0, 0))
        if b > 0:
            canvas.paste(_banda(img, "abajo", b, metodo), (0, a + h0))
        lados_info = [{"lado": "arriba", "px": a}, {"lado": "abajo", "px": b}]
    else:
        canvas.paste(img, (a, 0))
        if a > 0:
            canvas.paste(_banda(img, "izquierda", a, metodo), (0, 0))
        if b > 0:
            canvas.paste(_banda(img, "derecha", b, metodo), (a + w0, 0))
        lados_info = [{"lado": "izquierda", "px": a}, {"lado": "derecha", "px": b}]
    lados_info = [ll for ll in lados_info if ll["px"] > 0]

    canvas.resize((tw, th), Image.LANCZOS).save(destino, "PNG")
    motivo = "" if segura else f"forzado: extensión no segura ({frac:.0%}, bordes no uniformes)"
    return _resultado("extension", segura, lados_info, motivo)


def placa(args) -> dict:
    """Genera una PLACA / TARJETA DE TEXTO (cita o dato) en marca.

    Sin --foto: fondo de marca (tinta o blanco con barra de acento) y texto a
    alto contraste; si hay --fuente-cita, la pone debajo más pequeña ("— Autor").
    Con --foto: recorte cubriente al formato + degradado oscuro + texto encima,
    fuera de las zonas inseguras.
    Estilo: UnoTV sobrio (caja normal); Claro Sports impacto (mayúsculas,
    condensada). Auto-ajuste de tamaño con ajustar_titular para que el texto quepa.
    """
    fclave = (args.formato or "feed").strip().lower()
    if fclave not in FORMATOS:
        raise SystemExit(f"ERROR: formato '{args.formato}' desconocido. Opciones: {', '.join(FORMATOS)}")
    w, h = FORMATOS[fclave]

    m = cargar_marca(args.marca)
    clave = m["_id"]
    rojo = hex_a_rgb(m.get("rojo", "#E30613"))
    tinta = hex_a_rgb(m.get("tinta", "#111315"))
    blanco = hex_a_rgb(m.get("blanco", "#FFFFFF"))
    mayusculas = bool(m.get("titular_mayusculas"))
    condensada = bool(m.get("titular_condensada"))

    texto = (args.texto or "").strip()
    if not texto:
        raise SystemExit("ERROR: --texto vacío. Indica el contenido de la placa.")
    if mayusculas:
        texto = texto.upper()
    fuente_cita = (args.fuente_cita or "").strip()

    margin = 72
    # Zonas inseguras: márgenes generosos arriba/abajo para que el texto no
    # quede pegado a bordes ni a la UI de las redes en vertical.
    safe_top = 220 if fclave == "vertical" else 96
    safe_bottom = 420 if fclave == "vertical" else 120

    con_foto = bool(args.foto)
    if con_foto:
        base = ImageOps.exif_transpose(Image.open(_validar_foto(args.foto))).convert("RGBA")
        img = recorte_cubriente(base, w, h)
        # Degradado oscuro de legibilidad (texto blanco anclado abajo).
        img.alpha_composite(degradado_inferior(w, h, tinta))
        texto_fill = blanco
        con_sombra = True
    else:
        img = Image.new("RGBA", (w, h), tinta + (255,))
        # Barra/acento de marca en la parte superior (dentro de zona segura).
        draw0 = ImageDraw.Draw(img)
        barra_y = safe_top - 28
        draw0.rectangle([margin, barra_y, margin + 140, barra_y + 14], fill=rojo)
        texto_fill = blanco
        con_sombra = False

    draw = ImageDraw.Draw(img)

    max_ancho = w - margin * 2
    # Reserva alto para la fuente de la cita debajo, si la hay.
    reserva_cita = 0
    fuente_attr = None
    if fuente_cita:
        tam_cita = 46 if fclave != "vertical" else 52
        fuente_attr = cargar_fuente(tam_cita, condensada=condensada)
        reserva_cita = int(tam_cita * 1.4)

    # Alto disponible para el bloque de texto principal, entre las zonas seguras.
    alto_disponible = h - safe_top - safe_bottom - reserva_cita
    tam_max = 96 if fclave == "vertical" else 84
    fuente, lineas, alto_linea = ajustar_titular(
        draw, texto, max_ancho, alto_disponible,
        condensada=condensada, tam_max=tam_max,
    )
    bloque_h = len(lineas) * alto_linea

    if con_foto:
        # Anclado abajo, por encima de la zona insegura inferior.
        bottom_limit = h - safe_bottom
        y = bottom_limit - bloque_h - reserva_cita
        y = max(safe_top, y)
    else:
        # Centrado verticalmente en la zona segura (todo el bloque + cita).
        total_h = bloque_h + reserva_cita
        y = safe_top + max(0, (h - safe_top - safe_bottom - total_h) // 2)

    for ln in lineas:
        if con_sombra:
            draw.text((margin + 2, y + 2), ln, font=fuente, fill=(0, 0, 0))
        draw.text((margin, y), ln, font=fuente, fill=texto_fill)
        y += alto_linea

    if fuente_cita and fuente_attr is not None:
        y_cita = y + int(alto_linea * 0.25)
        # La atribución va en el acento de marca para distinguirla del cuerpo.
        cita_fill = rojo if not con_foto else blanco
        if con_sombra:
            draw.text((margin + 2, y_cita + 2), fuente_cita, font=fuente_attr, fill=(0, 0, 0))
        draw.text((margin, y_cita), fuente_cita, font=fuente_attr, fill=cita_fill)

    # Guardar.
    if args.salida:
        destino = Path(args.salida)
    elif con_foto:
        destino = Path(args.foto).with_name(f"{Path(args.foto).stem}-placa-{clave}-{fclave}.png")
    else:
        destino = Path.cwd() / f"placa-{clave}-{fclave}.png"
    destino.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(destino, "PNG")

    return {
        "op": "placa",
        "marca": m.get("nombre", clave),
        "marca_id": clave,
        "formato": fclave,
        "con_foto": con_foto,
        "tiene_cita": bool(fuente_cita),
        "salidas": [{"formato": fclave, "tamano": f"{w}x{h}", "salida": str(destino)}],
    }


def _validar_foto(path: str) -> Path:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ERROR: no existe la foto: {p}")
    return p


def main() -> int:
    p = argparse.ArgumentParser(description="Caja determinista del Estudio de imagen (sin IA).")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("recortar", help="Recorte cubriente a un formato (o a todos).")
    pr.add_argument("--foto", required=True)
    pr.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    pr.add_argument("--todos", action="store_true", help="Genera todos los formatos.")
    pr.add_argument("--salida", default=None, help="Ruta de salida (solo con un formato).")
    pr.add_argument("--salida-dir", dest="salida_dir", default=None, help="Carpeta de salida (con --todos).")
    pr.add_argument("--cx", type=float, default=0.5, help="Centro horizontal del recorte (0-1).")
    pr.add_argument("--cy", type=float, default=0.4, help="Centro vertical del recorte (0-1).")
    pr.set_defaults(func=recortar)

    pd = sub.add_parser("redimensionar", help="Cambia tamaño manteniendo proporción.")
    pd.add_argument("--foto", required=True)
    pd.add_argument("--max", type=int, default=None, help="Lado máximo en px (mantiene proporción).")
    pd.add_argument("--ancho", type=int, default=None)
    pd.add_argument("--alto", type=int, default=None)
    pd.add_argument("--salida", default=None)
    pd.set_defaults(func=redimensionar)

    pc = sub.add_parser("comprimir", help="Baja el PESO del archivo a un objetivo, conservando el tamaño (formato 'full').")
    pc.add_argument("--foto", required=True)
    pc.add_argument("--peso-max-mb", dest="peso_max_mb", type=float, default=2.0, help="Peso objetivo máximo en MB (default 2).")
    pc.add_argument("--max", type=int, default=None, help="Lado máximo en px (resize pequeño opcional; vacío = conserva tamaño).")
    pc.add_argument("--formato-archivo", dest="formato_archivo", default="jpg", help="jpg | webp")
    pc.add_argument("--calidad-min", dest="calidad_min", type=int, default=60, help="Calidad mínima antes de reducir tamaño (default 60).")
    pc.add_argument("--salida", default=None)
    pc.set_defaults(func=comprimir)

    pe = sub.add_parser("extender", help="Encaja en un formato extendiendo SOLO el fondo uniforme (cielo/negro), sin recortar al sujeto.")
    pe.add_argument("--foto", required=True)
    pe.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    pe.add_argument("--metodo", default="borde", help="borde (estira el borde) | color (color sólido del borde)")
    pe.add_argument("--max-ext", dest="max_ext", type=float, default=0.25, help="Fracción máxima del lado que se permite extender (default 0.25).")
    pe.add_argument("--umbral-uniforme", dest="umbral_uniforme", type=float, default=16.0, help="Desviación estándar máx. para considerar un borde uniforme (0-255).")
    pe.add_argument("--forzar", action="store_true", help="Extiende aunque el borde no sea uniforme o supere el máximo.")
    pe.add_argument("--salida", default=None)
    pe.set_defaults(func=extender)

    pp = sub.add_parser("placa", help="Tarjeta de texto (cita o dato) en marca, con o sin foto.")
    pp.add_argument("--texto", required=True, help="Texto principal de la placa (la cita o el dato).")
    pp.add_argument("--marca", required=True, help="unotv | claro-sports")
    pp.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    pp.add_argument("--fuente-cita", dest="fuente_cita", default=None, help="Atribución debajo, p. ej. '— Autor'.")
    pp.add_argument("--foto", default=None, help="Foto de fondo opcional (recorte + degradado + texto encima).")
    pp.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    pp.set_defaults(func=placa)

    args = p.parse_args()
    info = args.func(args)

    print(f"Operación determinista: {info['op']}.\n")
    if info["op"] == "placa":
        print(f"  Marca   : {info['marca']}  ·  Formato: {info['formato']}")
        print(f"  Fondo   : {'foto + degradado' if info['con_foto'] else 'marca (sin foto)'}")
        if info["tiene_cita"]:
            print("  Cita    : sí (atribución debajo)")
    if info["op"] == "comprimir":
        estado = "≤ objetivo" if info["bajo_objetivo"] else "POR ENCIMA del objetivo (mejor esfuerzo)"
        print(f"  Peso    : {info['peso_kb']} KB ({estado} {info['peso_objetivo_kb']} KB)  ·  calidad {info['calidad']}  ·  {info['formato_archivo']}")
        if info["redujo_tamano"]:
            print("  Nota    : se redujo el tamaño para alcanzar el peso objetivo.")
    if info["op"] == "extender":
        encaje = {"extension": "fondo extendido", "recorte": "recorte cubriente (no se pudo extender)", "resize": "ya estaba en proporción"}.get(info["aplicado"], info["aplicado"])
        sello = "fondo uniforme" if info["extension_segura"] else "⚠️ borde no uniforme (usa expandir.py / IA)"
        print(f"  Encaje  : {encaje}  ·  {sello}")
        if info["lados"]:
            print("  Extendido: " + ", ".join(f"{ll['lado']} +{ll['px']}px" for ll in info["lados"]) + f"  (método {info['metodo']})")
        if info["motivo"]:
            print(f"  Motivo  : {info['motivo']}")
    for s in info["salidas"]:
        etiqueta = s.get("formato", "")
        etiqueta = f"{etiqueta} " if etiqueta else ""
        print(f"  {etiqueta}{s['tamano']} -> {s['salida']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
