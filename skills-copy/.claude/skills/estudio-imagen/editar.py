#!/usr/bin/env python3
"""Caja de herramientas DETERMINISTA del Estudio de imagen (sin IA).

Operaciones exactas y reproducibles sobre una imagen, con Pillow. No reinventan
la imagen: la recortan, redimensionan o componen texto de marca. Pensado para
fotos de noticia, donde la regla editorial es respetar el hecho (ver
docs/estudio-imagen.md §3).

Subcomandos:
  recortar       recorte cubriente (object-fit:cover) a un formato de red, o a todos
  redimensionar  cambia el tamaño manteniendo proporción (por ancho, alto o lado máx.)
  placa          tarjeta de texto (cita o dato) en marca, con o sin foto de fondo

Uso:
  python3 editar.py recortar --foto FOTO --formato feed [--salida SAL]
  python3 editar.py recortar --foto FOTO --todos [--salida-dir DIR]
  python3 editar.py redimensionar --foto FOTO --max 1080 [--salida SAL]
  python3 editar.py placa --texto "..." --marca unotv --formato feed \
      [--fuente-cita "— Autor"] [--foto FOTO] [--salida SAL]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
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
    """Lee tokens de la marca del marcas.json hermano del breaking; si no existe,
    cae a los defaults internos. Resuelve la ruta con pathlib relativo al script
    (../breaking-express/marcas.json) y NO duplica todo el JSON: solo toma los
    tokens que la placa necesita."""
    clave = _resolver_clave_marca(marca)
    cfg_path = Path(__file__).resolve().parent.parent / "breaking-express" / "marcas.json"
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

    print(f"Operación determinista: {info['op']} (la imagen no se reinventa).\n")
    if info["op"] == "placa":
        print(f"  Marca   : {info['marca']}  ·  Formato: {info['formato']}")
        print(f"  Fondo   : {'foto + degradado' if info['con_foto'] else 'marca (sin foto)'}")
        if info["tiene_cita"]:
            print("  Cita    : sí (atribución debajo)")
    for s in info["salidas"]:
        etiqueta = s.get("formato", "")
        etiqueta = f"{etiqueta} " if etiqueta else ""
        print(f"  {etiqueta}{s['tamano']} -> {s['salida']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
