#!/usr/bin/env python3
"""Outpainting GENERATIVO del Estudio de imagen.

Encaja una foto en un formato (p. ej. 4:5) EXTENDIENDO el fondo con IA. Es la "última
milla" del encaje cuando el fondo NO es uniforme y la vía determinista
(`editar.py extender`) no puede hacerlo: rellena solo la BANDA añadida.

CÓMO FUNCIONA:
  - El SUJETO no se toca. La banda a rellenar va por MÁSCARA (OpenAI) y, pase lo que
    pase, al final RE-COMPONEMOS la foto original sobre su región exacta: el sujeto
    queda intacto pixel a pixel; la IA solo aporta la banda de fondo.
  - La llave vive en tu máquina (variables de entorno), nunca en el código.

PROVEEDOR INTERCAMBIABLE: elige según la clave disponible (o --proveedor):
  - openai: endpoint de EDICIÓN con máscara (gpt-image-1). La API regenera solo la
    banda enmascarada. Clave: OPENAI_API_KEY.
  - gemini: edición por imagen+instrucción ("Nano Banana"). Clave: GEMINI_API_KEY /
    GOOGLE_API_KEY.

MODO SIN KEY (degradado, no falla): explica cómo configurar la llave y entrega el
prompt de dirección de arte para rellenar la banda en tu herramienta.

Uso:
  python3 expandir.py --foto FOTO --formato feed \
      [--proveedor auto|openai|gemini] [--lado auto|arriba|abajo|izquierda|derecha] \
      [--marca claro-sports] [--prompt "..."] [--salida SAL]
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

# Nota de estilo por marca (referencia; guía completa en diseno-redes-amx).
ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creíble, alto contraste.",
    "claro-sports": "Estilo Claro Sports: deportivo, energía, alto contraste.",
    "claro": "Estilo Claro Sports: deportivo, energía, alto contraste.",
}

_OPENAI_URL = "https://api.openai.com/v1/images/edits"
_OPENAI_MODELO = "gpt-image-1"
_GEMINI_MODELO = "gemini-2.5-flash-image"
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


def _banda_caja(lado: str, geo: dict) -> tuple[int, int, int, int]:
    fw, fh = geo["fw"], geo["fh"]
    px = dict(geo["bandas"])[lado]
    if lado == "arriba":
        return (0, 0, fw, px)
    if lado == "abajo":
        return (0, fh - px, fw, fh)
    if lado == "izquierda":
        return (0, 0, px, fh)
    return (fw - px, 0, fw, fh)


def _lienzo_base(img: "Image.Image", geo: dict) -> "Image.Image":
    """Lienzo extendido con la foto pegada y la banda rellena con el borde estirado.

    Es solo una BASE: con OpenAI la banda se regenera por máscara; con Gemini sirve
    de contexto. El sujeto se re-compone al final, así que esta base nunca contamina
    la foto original.
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


def _mascara(geo: dict) -> "Image.Image":
    """Máscara RGBA: TRANSPARENTE en la banda (la IA edita ahí), OPACA en el resto."""
    mask = Image.new("RGBA", (geo["fw"], geo["fh"]), (0, 0, 0, 255))
    for lado, _ in geo["bandas"]:
        mask.paste((0, 0, 0, 0), _banda_caja(lado, geo))
    return mask


def _png_bytes(img: "Image.Image") -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _size_openai(geo: dict) -> str:
    fw, fh = geo["fw"], geo["fh"]
    if fh > fw * 1.05:
        return "1024x1536"
    if fw > fh * 1.05:
        return "1536x1024"
    return "1024x1024"


# --------------------------------------------------------------------------- #
# Proveedores (intercambiables) — punto INYECTABLE para los tests             #
# --------------------------------------------------------------------------- #

def _openai_edit(canvas: bytes, mask: bytes, prompt: str, clave: str, size: str) -> bytes:
    import base64

    try:
        import httpx
    except ImportError as e:  # pragma: no cover
        raise SystemExit("ERROR: falta httpx para el proveedor OpenAI.") from e
    resp = httpx.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {clave}"},
        data={"model": _OPENAI_MODELO, "prompt": prompt, "n": "1", "size": size},
        files={"image": ("canvas.png", canvas, "image/png"),
               "mask": ("mask.png", mask, "image/png")},
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SystemExit(f"ERROR: OpenAI devolvió {resp.status_code} al expandir.")
    return base64.b64decode(resp.json()["data"][0]["b64_json"])


def _gemini_edit(canvas: bytes, prompt: str, clave: str) -> bytes:
    try:
        from google import genai
    except ImportError as e:  # pragma: no cover
        raise SystemExit("ERROR: falta google-genai. Instálalo: pip install google-genai") from e
    client = genai.Client(api_key=clave)
    imagen = Image.open(io.BytesIO(canvas))
    resp = client.models.generate_content(model=_GEMINI_MODELO, contents=[prompt, imagen])
    for cand in getattr(resp, "candidates", []) or []:
        for part in getattr(cand.content, "parts", []) or []:
            datos = getattr(part, "inline_data", None)
            if datos and getattr(datos, "data", None):
                return datos.data
    raise SystemExit("ERROR: el modelo no devolvió imagen al expandir.")


def _generar_relleno_real(canvas: bytes, mask: bytes, prompt: str, *,
                          proveedor: str, clave: str, size: str) -> bytes:
    """Despacho real al proveedor. Los tests parchean `_PROVEEDOR_EXPANDIR`."""
    if proveedor == "openai":
        return _openai_edit(canvas, mask, prompt, clave, size)
    return _gemini_edit(canvas, prompt, clave)


# Punto INYECTABLE: lo único que toca la red. Los tests lo reemplazan.
_PROVEEDOR_EXPANDIR = _generar_relleno_real


def _elegir_proveedor(forzado: str) -> tuple[str | None, str | None]:
    """(proveedor, clave) según --proveedor y las claves del entorno; (None,None) si no hay."""
    if forzado == "openai":
        return ("openai", os.environ.get("OPENAI_API_KEY"))
    if forzado == "gemini":
        return ("gemini", os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
    if os.environ.get("OPENAI_API_KEY"):
        return ("openai", os.environ["OPENAI_API_KEY"])
    g = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if g:
        return ("gemini", g)
    return (None, None)


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
    print("Outpainting IA: no hay API key configurada (modo dirección de arte).\n")
    print("Configura UNA llave (no se guarda en archivos):")
    print('  export OPENAI_API_KEY="..."     # edición con máscara (gpt-image-1)')
    print('  export GEMINI_API_KEY="..."     # o Gemini "Nano Banana"\n')
    print("Mientras tanto, extiende la banda de fondo en tu herramienta con este PROMPT:\n")
    print("  " + prompt + "\n")
    print("Luego pásame el resultado y lo reviso (legal/editorial) antes de publicar.")
    return 0


def expandir(args) -> dict | int:
    fclave = (args.formato or "feed").strip().lower()
    if fclave not in FORMATOS:
        raise SystemExit(f"ERROR: formato '{args.formato}' desconocido. Opciones: {', '.join(FORMATOS)}")
    if args.proveedor not in ("auto", "openai", "gemini"):
        raise SystemExit("ERROR: --proveedor debe ser auto | openai | gemini.")
    if args.lado not in ("auto", "arriba", "abajo", "izquierda", "derecha"):
        raise SystemExit("ERROR: --lado inválido.")

    img = _abrir(args.foto)
    tw, th = FORMATOS[fclave]
    geo = geometria(*img.size, tw, th, args.lado)
    destino = Path(args.salida) if args.salida else Path(args.foto).with_name(
        f"{Path(args.foto).stem}-{fclave}-ia.png")
    destino.parent.mkdir(parents=True, exist_ok=True)

    # Ya está en proporción: nada que expandir (ni IA), solo redimensiona.
    if geo is None:
        img.resize((tw, th), Image.LANCZOS).save(destino, "PNG")
        return {"op": "expandir", "formato": fclave, "aplicado": "resize", "proveedor": None,
                "bandas": [], "salidas": [{"formato": fclave, "tamano": f"{tw}x{th}", "salida": str(destino)}]}

    prompt = _prompt(args, geo)
    proveedor, clave = _elegir_proveedor(args.proveedor)
    if proveedor is None or clave is None:
        return _fallback_sin_key(prompt)

    canvas = _lienzo_base(img, geo)
    relleno = _PROVEEDOR_EXPANDIR(_png_bytes(canvas), _png_bytes(_mascara(geo)), prompt,
                                  proveedor=proveedor, clave=clave, size=_size_openai(geo))

    res = Image.open(io.BytesIO(relleno)).convert("RGB").resize((geo["fw"], geo["fh"]), Image.LANCZOS)
    # Fidelidad: re-componemos la foto original encima -> el sujeto no se toca.
    res.paste(img, (geo["ox"], geo["oy"]))
    res.resize((tw, th), Image.LANCZOS).save(destino, "PNG")

    return {
        "op": "expandir",
        "formato": fclave,
        "aplicado": "expandir-ia",
        "proveedor": proveedor,
        "bandas": [{"lado": l, "px": p} for l, p in geo["bandas"]],
        "salidas": [{"formato": fclave, "tamano": f"{tw}x{th}", "salida": str(destino)}],
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Outpainting generativo del Estudio de imagen.")
    p.add_argument("--foto", required=True)
    p.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    p.add_argument("--proveedor", default="auto", help="auto | openai | gemini")
    p.add_argument("--lado", default="auto", help="auto | arriba | abajo | izquierda | derecha")
    p.add_argument("--marca", default=None, help="unotv | claro-sports (nota de estilo).")
    p.add_argument("--prompt", default=None, help="Guía extra opcional para el relleno.")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    args = p.parse_args()

    info = expandir(args)
    if isinstance(info, int):  # modo sin key (dirección de arte)
        return info

    if info["aplicado"] == "expandir-ia":
        print(f"IA · proveedor {info['proveedor']}: se rellenó la banda de fondo (el sujeto no se toca).")
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
