"""CLI: muestra el payload DRY-RUN de un borrador de publicacion para Meta.

    python -m keni_metricas.publicacion --plataforma instagram --cuenta IG_ID \\
        --texto "Hola" --imagen https://ej.com/foto.jpg --hashtag deporte

SEGURIDAD: esta CLI es DRY-RUN puro. NO toca la red, NO publica. Solo imprime la
peticion EXACTA que se enviaria. La publicacion real vive en la API del
adaptador (`publicar(..., dry_run=False)`), fuera de esta CLI, y exige token.
"""

from __future__ import annotations

import argparse
import json
import sys

from pydantic import ValidationError

from ..schema import Plataforma
from .meta import AdaptadorPublicacionMeta
from .modelos import Borrador, MediaRef, TipoMedia


def construir_borrador(args: argparse.Namespace) -> Borrador:
    media: list[MediaRef] = []
    if args.imagen:
        media.append(MediaRef(tipo=TipoMedia.imagen, url=args.imagen))
    if args.video:
        media.append(MediaRef(tipo=TipoMedia.video, url=args.video))
    return Borrador(
        plataforma=Plataforma(args.plataforma),
        cuenta=args.cuenta,
        texto=args.texto or "",
        media=media,
        hashtags=args.hashtag or [],
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m keni_metricas.publicacion",
        description="Muestra el payload DRY-RUN de una publicacion para Meta (NO publica).",
    )
    ap.add_argument("--plataforma", required=True, choices=["facebook", "instagram"])
    ap.add_argument("--cuenta", required=True, help="Page ID (FB) o IG User ID (IG)")
    ap.add_argument("--texto", default="", help="cuerpo del post (sin hashtags)")
    ap.add_argument("--imagen", help="URL publica de una imagen")
    ap.add_argument("--video", help="URL publica de un video")
    ap.add_argument(
        "--hashtag", action="append", help="hashtag (sin '#'); repetible: --hashtag a --hashtag b"
    )
    ap.add_argument("--formato", choices=["json", "texto"], default="texto")
    args = ap.parse_args(argv)

    # B2/B6: tanto la construccion del borrador como `publicar()` van dentro del
    # try. Instagram sin media lanza ValueError en `publicar()`; sin esto la CLI
    # reventaba con un traceback crudo. Los errores de pydantic se muestran con
    # su mensaje limpio (sin el texto en ingles ni la URL errors.pydantic.dev).
    try:
        borrador = construir_borrador(args)
        # Adaptador SIN credenciales: imposible publicar de verdad desde la CLI.
        adaptador = AdaptadorPublicacionMeta(creds={})
        resultado = adaptador.publicar(borrador, dry_run=True)  # SIEMPRE dry-run aqui
    except ValidationError as e:
        print(f"Error: {e.errors()[0]['msg']}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.formato == "json":
        print(json.dumps(resultado.como_dict(), ensure_ascii=False, indent=2))
    else:
        print(_render_texto(resultado, borrador))
    return 0


def _render_texto(resultado, borrador: Borrador) -> str:
    out: list[str] = []
    out.append(f"# DRY-RUN publicacion — {resultado.plataforma.value} / {resultado.cuenta}")
    out.append("(NADA se ha publicado. Esto es solo lo que se enviaria.)\n")
    out.append("Texto final:")
    out.append(borrador.texto_final() or "(vacio)")
    out.append("")
    for i, pet in enumerate(resultado.peticiones, 1):
        out.append(f"## Peticion {i}/{len(resultado.peticiones)} — {pet.paso}")
        out.append(f"{pet.metodo} {pet.url}")
        out.append("data:")
        out.append(json.dumps(pet.data, ensure_ascii=False, indent=2))
        out.append("")
    out.append("**NADA se ha publicado. Esto es DRY-RUN; no hubo peticiones de red.**")
    return "\n".join(out)


if __name__ == "__main__":
    raise SystemExit(main())
