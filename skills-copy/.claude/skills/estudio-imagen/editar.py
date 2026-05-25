#!/usr/bin/env python3
"""Caja de herramientas DETERMINISTA del Estudio de imagen (sin IA).

Operaciones exactas y reproducibles sobre una imagen, con Pillow. No reinventan
la imagen: la recortan o redimensionan. Pensado para fotos de noticia, donde la
regla editorial es respetar el hecho (ver docs/estudio-imagen.md §3).

Subcomandos:
  recortar       recorte cubriente (object-fit:cover) a un formato de red, o a todos
  redimensionar  cambia el tamaño manteniendo proporción (por ancho, alto o lado máx.)

Uso:
  python3 editar.py recortar --foto FOTO --formato feed [--salida SAL]
  python3 editar.py recortar --foto FOTO --todos [--salida-dir DIR]
  python3 editar.py redimensionar --foto FOTO --max 1080 [--salida SAL]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
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


def abrir(path: str) -> Image.Image:
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

    args = p.parse_args()
    info = args.func(args)

    print(f"Operación determinista: {info['op']} (la imagen no se reinventa).\n")
    for s in info["salidas"]:
        etiqueta = s.get("formato", "")
        etiqueta = f"{etiqueta} " if etiqueta else ""
        print(f"  {etiqueta}{s['tamano']} -> {s['salida']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
