#!/usr/bin/env python3
"""Adaptador GENERATIVO del Estudio de imagen (IA por API).

Genera imágenes NO documentales (ilustraciones, fondos, gráficos, conceptos) con
un modelo de imagen. Proveedor por defecto: Google Gemini ("Nano Banana").

DOS LÍNEAS ROJAS (ver docs/estudio-imagen.md §3):
  1. NO altera fotos de noticia reales. Con --foto-real se NIEGA y propone la vía
     determinista (editar.py / componer.py). Es una regla editorial de credibilidad.
  2. La llave vive en tu máquina: la API key se lee de una variable de entorno
     (GEMINI_API_KEY / GOOGLE_API_KEY), NUNCA del código ni de un archivo versionado.

MODO SIN KEY (degradado, no falla): si no hay key, explica cómo configurarla y
entrega el "prompt de dirección de arte" listo para pegar en tu herramienta
(Nano Banana/Gemini, DALL·E, Ideogram, Sora…), que es el patrón de cero coste de
07-innovacion/diseno-redes-amx. Así la herramienta es útil aun sin API conectada.

Uso:
  python3 generar.py --prompt "..." [--marca claro-sports] [--formato feed] \
      [--modelo gemini-2.5-flash-image] [--salida SAL] [--foto-real]
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

# Nota de estilo por marca (referencia; la guía completa está en diseno-redes-amx).
ESTILO_MARCA = {
    "unotv": "Estilo UnoTV: noticias, sobrio, creíble, alto contraste, rojo #E30613 como acento puntual.",
    "claro-sports": "Estilo Claro Sports: deportivo, energía, alto contraste, rojo #CF2E2E de marca.",
    "claro": "Estilo Claro Sports: deportivo, energía, alto contraste, rojo #CF2E2E de marca.",
}

MODELO_DEFECTO = "gemini-2.5-flash-image"  # "Nano Banana". Pro: gemini-3-pro-image. Confirmar.


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
    partes.append("Ilustración/gráfico, NO una foto realista de un hecho noticioso real.")
    return " ".join(partes)


def salida_sin_key(prompt: str) -> int:
    print("IA generativa: no hay API key configurada (modo dirección de arte).\n")
    print("Para generar dentro de keni-social, configura tu llave UNA vez (no se guarda en archivos):")
    print('  export GEMINI_API_KEY="tu_api_key"     # o GOOGLE_API_KEY')
    print("  python3 -m pip install google-genai     # SDK del proveedor por defecto\n")
    print("Mientras tanto, copia este PROMPT en tu herramienta (Nano Banana/Gemini, DALL·E, Ideogram…):\n")
    print("  " + prompt + "\n")
    print("Luego pásame la imagen generada y la reviso (legal/editorial) antes de publicar.")
    return 0


def generar_con_gemini(prompt: str, modelo: str, salida: Path, api_key: str) -> int:
    try:
        from google import genai  # SDK google-genai
    except ImportError:
        sys.stderr.write(
            "ERROR: falta el SDK. Instálalo con:  python3 -m pip install google-genai\n"
        )
        return 2
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(model=modelo, contents=[prompt])
    # Extrae la primera parte con datos de imagen.
    for cand in getattr(resp, "candidates", []) or []:
        for part in getattr(cand.content, "parts", []) or []:
            datos = getattr(part, "inline_data", None)
            if datos and getattr(datos, "data", None):
                salida.parent.mkdir(parents=True, exist_ok=True)
                salida.write_bytes(datos.data)
                print(f"Imagen generada (IA, {modelo}): {salida}")
                print("Recuerda: pásala por la revisión legal/editorial antes de publicar.")
                return 0
    sys.stderr.write("ERROR: el modelo no devolvió imagen. Revisa el prompt o el modelo.\n")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Adaptador generativo (IA) del Estudio de imagen.")
    p.add_argument("--prompt", required=True, help="Qué generar (ilustración/fondo/gráfico).")
    p.add_argument("--marca", default=None, help="unotv | claro-sports (inyecta nota de estilo).")
    p.add_argument("--formato", default="feed", help="vertical | feed | cuadrado | horizontal")
    p.add_argument("--modelo", default=MODELO_DEFECTO, help=f"Modelo de imagen (def. {MODELO_DEFECTO}).")
    p.add_argument("--salida", default=None, help="Ruta de salida PNG.")
    p.add_argument("--foto-real", dest="foto_real", action="store_true",
                   help="Marca que la entrada es una foto de noticia real (activa el guardrail).")
    args = p.parse_args()

    # GUARDRAIL editorial: la IA no altera fotos de noticia reales.
    if args.foto_real:
        print("BLOQUEADO (regla editorial §3): la IA no altera fotos de noticia reales.")
        print("Una foto de noticia se respeta, no se reinventa (credibilidad de UnoTV/Claro Sports).")
        print("Para tratar la foto usa la vía DETERMINISTA:")
        print("  · recortar/redimensionar  -> editar.py")
        print("  · logo + pleca + breaking -> ../breaking-express/componer.py")
        print("Si necesitas una ILUSTRACIÓN nueva (no la foto), vuelve a llamarme sin --foto-real.")
        return 3

    prompt = construir_prompt(args)
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        return salida_sin_key(prompt)

    salida = Path(args.salida) if args.salida else Path.cwd() / "generada.png"
    return generar_con_gemini(prompt, args.modelo, salida, api_key)


if __name__ == "__main__":
    raise SystemExit(main())
