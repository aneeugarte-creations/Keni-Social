#!/usr/bin/env python3
"""Retoque GENERATIVO por INSTRUCCIÓN del Estudio de imagen (vía OpenRouter).

Toma una imagen y una instrucción en lenguaje natural ("oscurece el cielo", "haz el
fondo más cálido", "quita el reflejo del cristal") y devuelve una GENERACIÓN nueva con
ese cambio aplicado. Es image-to-image sobre TODA la imagen, a diferencia de
`expandir.py` (outpainting: solo rellena una banda añadida sin tocar el sujeto). Aquí el
modelo SÍ reinterpreta la escena según la instrucción.

UN SOLO PROVEEDOR — OpenRouter (gateway compatible con OpenAI), idéntico a `expandir.py`:
  - Endpoint: POST https://openrouter.ai/api/v1/chat/completions (estilo chat).
  - La imagen va como imagen de entrada (data URL base64) en `messages`; `modalities`
    pide salida de imagen. `image_config.strength` (0-1) controla cuánto cambia: por
    defecto MEDIO-ALTO (el retoque sí transforma, al contrario que el outpainting).
  - Clave única: OPENROUTER_API_KEY. Modelo por defecto: OPENROUTER_IMAGE_MODEL o el de
    abajo.

MODO SIN KEY (degradado, no falla): explica cómo configurar la llave y entrega el prompt
de dirección de arte para aplicar el retoque en otra herramienta.

Uso:
  python3 retocar.py --foto FOTO --instruccion "oscurece el cielo" \
      [--modelo openai/gpt-5.4-image-2] [--strength 0.6] [--salida SAL]
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

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Modelo de imagen por defecto (editable por --modelo o OPENROUTER_IMAGE_MODEL).
_MODELO_DEFECTO = "openai/gpt-5.4-image-2"
# Retoque: por defecto cambia MÁS que el outpainting (que es fiel). Medio-alto.
_STRENGTH_DEFECTO = 0.6
_TIMEOUT = 120


def _png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# Proveedor (OpenRouter) — punto INYECTABLE para los tests                    #
# --------------------------------------------------------------------------- #

def _openrouter_edit(imagen: bytes, prompt: str, *, clave: str, modelo: str, strength: float) -> bytes:
    """Edita la imagen con OpenRouter (chat/completions, imagen de entrada + strength).

    Los tests parchean `_PROVEEDOR_RETOCAR`, así que esto NUNCA toca la red en CI.
    """
    import base64

    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("ERROR: falta httpx para OpenRouter.") from e
    data_url = "data:image/png;base64," + base64.b64encode(imagen).decode("ascii")
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
        raise SystemExit(f"ERROR: OpenRouter devolvió {resp.status_code} al retocar.")
    try:
        url = resp.json()["choices"][0]["message"]["images"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise SystemExit("ERROR: OpenRouter no devolvió imagen (¿modelo sin salida de imagen?).") from e
    b64 = url.split(",", 1)[1] if "," in url else url
    return base64.b64decode(b64)


# Punto INYECTABLE: lo único que toca la red. Los tests lo reemplazan.
_PROVEEDOR_RETOCAR = _openrouter_edit


# --------------------------------------------------------------------------- #
# Orquestador                                                                  #
# --------------------------------------------------------------------------- #

def _abrir(path: str) -> "Image.Image":
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"ERROR: no existe la imagen: {p}")
    return ImageOps.exif_transpose(Image.open(p)).convert("RGB")


def _prompt(instruccion: str) -> str:
    return (
        "Aplica esta indicación de retoque fotográfico a la imagen, MANTENIENDO la composición, "
        "el encuadre y el contenido salvo lo que la indicación pida cambiar. No añadas texto, "
        "logotipos ni marcas de agua. Coherencia fotorrealista de luz, color y perspectiva.\n\n"
        f"Indicación: {instruccion.strip()}"
    )


def _fallback_sin_key(prompt: str) -> int:
    print("Retoque IA: no hay clave de OpenRouter configurada (modo dirección de arte).\n")
    print("Configura tu llave (no se guarda en archivos):")
    print('  export OPENROUTER_API_KEY="..."\n')
    print("Mientras tanto, aplica este retoque en tu herramienta con este PROMPT:\n")
    print("  " + prompt + "\n")
    print("Luego pásame el resultado y lo reviso (legal/editorial) antes de publicar.")
    return 0


def retocar(args) -> dict | int:
    instruccion = (args.instruccion or "").strip()
    if not instruccion:
        raise SystemExit("ERROR: falta --instruccion (qué retoque aplicar).")
    if not 0.0 <= args.strength <= 1.0:
        raise SystemExit("ERROR: --strength debe estar entre 0.0 y 1.0.")

    img = _abrir(args.foto)
    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(
        f"{Path(args.foto).stem}-retoque.png")
    destino.parent.mkdir(parents=True, exist_ok=True)

    prompt = _prompt(instruccion)
    clave = os.environ.get("OPENROUTER_API_KEY")
    if not clave:
        return _fallback_sin_key(prompt)
    modelo = args.modelo or os.environ.get("OPENROUTER_IMAGE_MODEL") or _MODELO_DEFECTO

    w0, h0 = img.size
    salida = _PROVEEDOR_RETOCAR(_png_bytes(img), prompt, clave=clave, modelo=modelo, strength=args.strength)
    # Conserva el tamaño original (el modelo puede devolver otra resolución).
    res = Image.open(io.BytesIO(salida)).convert("RGB").resize((w0, h0), Image.LANCZOS)
    res.save(destino, "PNG")

    return {
        "op": "retocar",
        "instruccion": instruccion,
        "modelo": modelo,
        "salidas": [{"tamano": f"{w0}x{h0}", "salida": str(destino)}],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Retoque generativo por instrucción del Estudio (OpenRouter).")
    p.add_argument("--foto", required=True)
    p.add_argument("--instruccion", required=True, help='Qué cambiar, p. ej. "oscurece el cielo".')
    p.add_argument("--modelo", default=None, help=f"Modelo de imagen en OpenRouter (def. {_MODELO_DEFECTO}).")
    p.add_argument("--strength", type=float, default=_STRENGTH_DEFECTO,
                   help="0-1: cuánto cambia respecto al original (alto = cambia más).")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    args = p.parse_args()

    info = retocar(args)
    if isinstance(info, int):  # modo sin key (dirección de arte)
        return info

    print(f"IA · {info['modelo']} (OpenRouter): retoque aplicado ({info['instruccion']}).")
    print("  Pásalo por la revisión legal/editorial antes de publicar.")
    for s in info["salidas"]:
        print(f"  {s['tamano']} -> {s['salida']}")
    print("\nDATOS " + json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
