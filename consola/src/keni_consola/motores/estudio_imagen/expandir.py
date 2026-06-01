#!/usr/bin/env python3
"""Outpainting GENERATIVO del Estudio de imagen (vía OpenRouter).

Encaja una foto en un formato (p. ej. 4:5) EXTENDIENDO el fondo con IA. Es la "última
milla" del encaje cuando el fondo NO es uniforme y la vía determinista
(`editar.py extender`) no puede hacerlo: rellena solo la BANDA añadida.

UN SOLO PROVEEDOR — OpenRouter (gateway compatible con OpenAI):
  - Endpoint: POST https://openrouter.ai/api/v1/chat/completions (estilo chat).
  - La foto va como imagen de entrada (data URL base64) en `messages`; `modalities`
    pide salida de imagen; `image_config.strength` (0-1, bajo = más fiel al original)
    controla cuánto cambia. El modelo se elige por id (`--modelo`), sin tocar código:
    Gemini Flash Image, Seedream, FLUX, etc.
  - Clave única: OPENROUTER_API_KEY. Modelo por defecto: OPENROUTER_IMAGE_MODEL o
    el de abajo.

EL SUJETO NO SE TOCA: pase lo que pase el modelo, al final RE-COMPONEMOS la foto
original sobre su región exacta; el sujeto queda intacto pixel a pixel y la IA solo
aporta la banda de fondo.

MODO SIN KEY (degradado, no falla): explica cómo configurar la llave y entrega el
prompt de dirección de arte para rellenar la banda en tu herramienta.

Uso:
  python3 expandir.py --foto FOTO --formato feed \
      [--modelo openai/gpt-5.4-image-2] [--strength 0.4] \
      [--lado auto|arriba|abajo|izquierda|derecha] [--marca claro-sports] \
      [--prompt "..."] [--salida SAL]
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.stderr.write("ERROR: falta Pillow. Instálalo con:  python3 -m pip install pillow\n")
    raise SystemExit(2)

# Formatos de salida (px). Mismas medidas que editar.py / breaking-express.
FORMATOS = {
    "vertical": (1080, 1920),
    "feed": (1080, 1350),
    "cuadrado": (1080, 1080),
    "horizontal": (1920, 1080),
}

# Nota de estilo por marca (referencia; guía completa en
# skills-copy/.claude/skills/diseno-<marca>/guia-diseno.md).
ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creíble, alto contraste.",
    "claro-sports": "Estilo Claro Sports: deportivo, energía, alto contraste.",
    "claro": "Estilo Claro Sports: deportivo, energía, alto contraste.",
}

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Modelo de imagen por defecto (editable por --modelo o OPENROUTER_IMAGE_MODEL).
# Otros: bytedance/seedream-4.5 (preserva sujeto), black-forest-labs/flux..., etc.
_MODELO_DEFECTO = "openai/gpt-5.4-image-2"
_STRENGTH_DEFECTO = 0.4  # bajo = más fiel al original; afinar en la primera prueba real
_TIMEOUT = 120


# --------------------------------------------------------------------------- #
# Geometría del encaje (puro, sin red ni IA)                                  #
# --------------------------------------------------------------------------- #

def geometria(w0: int, h0: int, tw: int, th: int, lado: str = "auto") -> dict | None:
    """Layout para llevar (w0,h0) a la proporción tw/th AÑADIENDO lienzo (sin recortar).

    Devuelve dict {fw, fh, ox, oy, extra, eje, bandas} o None si ya está en proporción.
    `ox,oy` = dónde se pega la foto original en el lienzo final. `bandas` = lados a
    rellenar con su grosor en px. `lado` fuerza por qué lado se añade (auto = reparte).
    """
    objetivo, actual = tw / th, w0 / h0
    if abs(actual - objetivo) <= 0.005:
        return None
    if actual > objetivo:  # más ancha que el formato -> añadir ALTO
        fw, fh, extra, eje = w0, round(w0 / objetivo), round(w0 / objetivo) - h0, "v"
        if lado == "arriba":
            a, b = extra, 0
        elif lado == "abajo":
            a, b = 0, extra
        else:
            a, b = extra // 2, extra - extra // 2
        ox, oy, bandas = 0, a, [("arriba", a), ("abajo", b)]
    else:  # más alta/estrecha -> añadir ANCHO
        fw, fh, extra, eje = round(h0 * objetivo), h0, round(h0 * objetivo) - w0, "h"
        if lado == "izquierda":
            a, b = extra, 0
        elif lado == "derecha":
            a, b = 0, extra
        else:
            a, b = extra // 2, extra - extra // 2
        ox, oy, bandas = a, 0, [("izquierda", a), ("derecha", b)]
    return {"fw": fw, "fh": fh, "ox": ox, "oy": oy, "extra": extra, "eje": eje,
            "bandas": [(l, p) for l, p in bandas if p > 0]}


def _lienzo_base(img: "Image.Image", geo: dict) -> "Image.Image":
    """Lienzo extendido con la foto pegada y la banda rellena con el borde estirado.

    Es solo la BASE que se le manda al modelo (la foto + una banda continuada del
    borde); el modelo la mejora y, al final, re-componemos el sujeto original encima,
    así que esta base nunca contamina la foto.
    """
    w0, h0 = img.size
    canvas = Image.new("RGB", (geo["fw"], geo["fh"]))
    canvas.paste(img, (geo["ox"], geo["oy"]))
    for lado, px in geo["bandas"]:
        if lado == "arriba":
            canvas.paste(img.crop((0, 0, w0, 1)).resize((w0, px), Image.LANCZOS), (geo["ox"], 0))
        elif lado == "abajo":
            canvas.paste(img.crop((0, h0 - 1, w0, h0)).resize((w0, px), Image.LANCZOS), (geo["ox"], geo["oy"] + h0))
        elif lado == "izquierda":
            canvas.paste(img.crop((0, 0, 1, h0)).resize((px, h0), Image.LANCZOS), (0, geo["oy"]))
        else:
            canvas.paste(img.crop((w0 - 1, 0, w0, h0)).resize((px, h0), Image.LANCZOS), (geo["ox"] + w0, geo["oy"]))
    return canvas


def _png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Proveedor (OpenRouter) — punto INYECTABLE para los tests                    #
# --------------------------------------------------------------------------- #

def _openrouter_edit(canvas: bytes, prompt: str, *, clave: str, modelo: str, strength: float) -> bytes:
    """Edita la imagen con OpenRouter (chat/completions, imagen de entrada + strength).

    Los tests parchean `_PROVEEDOR_EXPANDIR`, así que esto NUNCA toca la red en CI.
    """
    import base64

    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("ERROR: falta httpx para OpenRouter.") from e
    data_url = "data:image/png;base64," + base64.b64encode(canvas).decode("ascii")
    resp = httpx.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {clave}", "Content-Type": "application/json"},
        json={
            "model": modelo,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}],
            "modalities": ["image", "text"],
            "image_config": {"strength": strength},
        },
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SystemExit(f"ERROR: OpenRouter devolvió {resp.status_code} al expandir.")
    try:
        url = resp.json()["choices"][0]["message"]["images"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise SystemExit("ERROR: OpenRouter no devolvió imagen (¿modelo sin salida de imagen?).") from e
    b64 = url.split(",", 1)[1] if "," in url else url
    return base64.b64decode(b64)


# Punto INYECTABLE: lo único que toca la red. Los tests lo reemplazan.
_PROVEEDOR_EXPANDIR = _openrouter_edit


# --------------------------------------------------------------------------- #
# Orquestador                                                                  #
# --------------------------------------------------------------------------- #

def _abrir(path: str) -> "Image.Image":
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ERROR: no existe la imagen: {p}")
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def _prompt(args, geo: dict) -> str:
    partes = [
        "Extiende SOLO el fondo de esta foto hacia la zona añadida (la banda),",
        "como continuación fotorrealista del fondo ya existente (cielo, gradas, escenario).",
        "NO añadas ni cambies personas, jugadores, rostros, texto, logotipos ni objetos.",
        "Sin marcas de agua. Coherencia de luz y color con la foto.",
    ]
    if args.prompt:
        partes.append(args.prompt.strip())
    clave = (args.marca or "").strip().lower().replace("_", "-")
    if clave == "clarosports":
        clave = "claro-sports"
    if clave in ESTILO_MARCA:
        partes.append(ESTILO_MARCA[clave])
    lados = ", ".join(l for l, _ in geo["bandas"])
    partes.append(f"Banda a rellenar: {lados}.")
    return " ".join(partes)


def _fallback_sin_key(prompt: str) -> int:
    print("Outpainting IA: no hay clave de OpenRouter configurada (modo dirección de arte).\n")
    print("Configura tu llave (no se guarda en archivos):")
    print('  export OPENROUTER_API_KEY="..."\n')
    print("Mientras tanto, extiende la banda de fondo en tu herramienta con este PROMPT:\n")
    print("  " + prompt + "\n")
    print("Luego pásame el resultado y lo reviso (legal/editorial) antes de publicar.")
    return 0


def expandir(args) -> dict | int:
    fclave = (args.formato or "feed").strip().lower()
    if fclave not in FORMATOS:
        raise SystemExit(f"ERROR: formato '{args.formato}' desconocido. Opciones: {', '.join(FORMATOS)}")
    if args.lado not in ("auto", "arriba", "abajo", "izquierda", "derecha"):
        raise SystemExit("ERROR: --lado inválido.")
    if not 0.0 <= args.strength <= 1.0:
        raise SystemExit("ERROR: --strength debe estar entre 0.0 y 1.0.")

    img = _abrir(args.foto)
    tw, th = FORMATOS[fclave]
    geo = geometria(*img.size, tw, th, args.lado)
    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(
        f"{Path(args.foto).stem}-{fclave}-ia.png")
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Ya está en proporción: nada que expandir (ni IA), solo redimensiona.
    if geo is None:
        img.resize((tw, th), Image.LANCZOS).save(destino, "PNG")
        return {"op": "expandir", "formato": fclave, "aplicado": "resize", "modelo": None,
                "bandas": [], "salidas": [{"formato": fclave, "tamano": f"{tw}x{th}", "salida": str(destino)}]}

    prompt = _prompt(args, geo)
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        return _fallback_sin_key(prompt)
    modelo = args.modelo or os.environ.get("OPENROUTER_IMAGE_MODEL") or _MODELO_DEFECTO

    canvas = _lienzo_base(img, geo)
    relleno = _PROVEEDOR_EXPANDIR(_png_bytes(canvas), prompt, clave=clave, modelo=modelo, strength=args.strength)

    res = Image.open(io.BytesIO(relleno)).convert("RGB").resize((geo["fw"], geo["fh"]), Image.LANCZOS)
    # Fidelidad: re-componemos la foto original encima -> el sujeto no se toca.
    res.paste(img, (geo["ox"], geo["oy"]))
    res.resize((tw, th), Image.LANCZOS).save(destino, "PNG")

    return {
        "op": "expandir",
        "formato": fclave,
        "aplicado": "expandir-ia",
        "modelo": modelo,
        "bandas": [{"lado": l, "px": p} for l, p in geo["bandas"]],
        "salidas": [{"formato": fclave, "tamano": f"{tw}x{th}", "salida": str(destino)}],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Outpainting generativo del Estudio de imagen (OpenRouter).")
    p.add_argument("--foto", required=True)
    p.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    p.add_argument("--modelo", default=None, help=f"Modelo de imagen en OpenRouter (def. {_MODELO_DEFECTO}).")
    p.add_argument("--strength", type=float, default=_STRENGTH_DEFECTO, help="0-1: cuánto cambia respecto al original (bajo = más fiel).")
    p.add_argument("--lado", default="auto", help="auto | arriba | abajo | izquierda | derecha")
    p.add_argument("--marca", default=None, help="unotv | claro-sports (nota de estilo).")
    p.add_argument("--prompt", default=None, help="Guía extra opcional para el relleno.")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    args = p.parse_args()

    info = expandir(args)
    if isinstance(info, int):  # modo sin key (dirección de arte)
        return info

    if info["aplicado"] == "expandir-ia":
        print(f"IA · {info['modelo']} (OpenRouter): se rellenó la banda de fondo (el sujeto no se toca).")
        print("  Pásalo por la revisión legal/editorial antes de publicar.")
        bandas = ", ".join(f"{b['lado']} +{b['px']}px" for b in info["bandas"])
        print(f"  Banda: {bandas}")
    else:
        print("Ya estaba en proporción: solo se redimensionó (sin IA).")
    for s in info["salidas"]:
        print(f"  {s.get('formato','')} {s['tamano']} -> {s['salida']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
