#!/usr/bin/env python3
"""Adaptador GENERATIVO del Estudio de imagen (IA por API, vía OpenRouter).

Genera imágenes (ilustraciones, fondos, gráficos, conceptos) con un modelo de imagen
a través de OpenRouter (gateway compatible con OpenAI): un solo endpoint y una sola
clave para cualquier modelo (Gemini Flash Image, Seedream, FLUX…), elegible por id.

La llave vive en tu máquina: la API key se lee de la variable de entorno
OPENROUTER_API_KEY, NUNCA del código ni de un archivo versionado.

MODO SIN KEY (degradado, no falla): si no hay key, explica cómo configurarla y
entrega el "prompt de dirección de arte" listo para pegar en tu herramienta.

Uso:
  python3 generar.py --prompt "..." [--marca claro-sports] [--formato feed] \
      [--modelo openai/gpt-5.4-image-2] [--salida SAL]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Relación de aspecto sugerida por formato (para el prompt / la petición a la API).
ASPECTOS = {
    "vertical": "9:16",
    "feed": "4:5",
    "cuadrado": "1:1",
    "horizontal": "16:9",
}

# Nota de estilo por marca (referencia; la guía completa está en
# skills-copy/.claude/skills/diseno-<marca>/guia-diseno.md).
ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creíble, alto contraste, rojo #E30613 como acento puntual.",
    "claro-sports": "Estilo Claro Sports: deportivo, energía, alto contraste, rojo #CF2E2E de marca.",
    "claro": "Estilo Claro Sports: deportivo, energía, alto contraste, rojo #CF2E2E de marca.",
}

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# Modelo por defecto (editable por --modelo o OPENROUTER_IMAGE_MODEL).
MODELO_DEFECTO = "openai/gpt-5.4-image-2"
_TIMEOUT = 120


def construir_prompt(args) -> str:
    partes = [args.prompt.strip()]
    if args.marca:
        clave = args.marca.strip().lower().replace("_", "-")
        if clave == "clarosports":
            clave = "claro-sports"
        nota = ESTILO_MARCA.get(clave)
        if nota:
            partes.append(nota)
    if args.formato in ASPECTOS:
        partes.append(f"Relación de aspecto {ASPECTOS[args.formato]}.")
    return " ".join(partes)


def salida_sin_key(prompt: str) -> int:
    print("IA generativa: no hay clave de OpenRouter configurada (modo dirección de arte).\n")
    print("Configura tu llave UNA vez (no se guarda en archivos):")
    print('  export OPENROUTER_API_KEY="tu_api_key"\n')
    print("Mientras tanto, copia este PROMPT en tu herramienta (Nano Banana/Gemini, DALL·E, Ideogram…):\n")
    print("  " + prompt + "\n")
    print("Luego pásame la imagen generada y la reviso (legal/editorial) antes de publicar.")
    return 0


def generar_con_openrouter(prompt: str, modelo: str, salida: Path, api_key: str) -> int:
    import base64

    try:
        import httpx
    except ImportError:
        sys.stderr.write("ERROR: falta httpx. Instálalo con:  python3 -m pip install httpx\n")
        return 2
    resp = httpx.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": modelo,
            "messages": [{"role": "user", "content": prompt}],
            "modalities": ["image", "text"],
        },
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        sys.stderr.write(f"ERROR: OpenRouter devolvió {resp.status_code} al generar.\n")
        return 1
    try:
        url = resp.json()["choices"][0]["message"]["images"][0]["image_url"]["url"]
    except (KeyError, IndexError, TypeError, ValueError):
        sys.stderr.write("ERROR: OpenRouter no devolvió imagen. Revisa el prompt o el modelo.\n")
        return 1
    b64 = url.split(",", 1)[1] if "," in url else url
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_bytes(base64.b64decode(b64))
    print(f"Imagen generada (IA, {modelo} vía OpenRouter): {salida}")
    print("Recuerda: pásala por la revisión legal/editorial antes de publicar.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Adaptador generativo (IA) del Estudio de imagen.")
    p.add_argument("--prompt", required=True, help="Qué generar (ilustración/fondo/gráfico).")
    p.add_argument("--marca", default=None, help="unotv | claro-sports (inyecta nota de estilo).")
    p.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    p.add_argument("--modelo", default=None, help=f"Modelo de imagen en OpenRouter (def. {MODELO_DEFECTO}).")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    args = p.parse_args()

    prompt = construir_prompt(args)
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return salida_sin_key(prompt)

    modelo = args.modelo or os.environ.get("OPENROUTER_IMAGE_MODEL") or MODELO_DEFECTO
    salida = Path(args.salida) if args.salida else Path.cwd() / "generada.png"
    return generar_con_openrouter(prompt, modelo, salida, api_key)


if __name__ == "__main__":
    raise SystemExit(main())
