"""CLI `keni-termometro`: genera el Termometro mundial de forma PROGRAMADA (cron 07:00).

La consola arma el termometro EN SEGUNDO PLANO desde la web (`POST /api/termometro/generar`),
pero a las 7:00 normalmente no hay nadie con la consola abierta. Este CLI hace lo mismo
SIN servidor y de forma SINCRONA, pensado para un cron / launchd:

  1. Lee la config guardada del termometro (marca, numero, regiones) — la misma que la web.
  2. Reune las noticias del dia: por defecto, de los FEEDS RSS activos (el "rastreo"); o de
     un archivo con `--noticias-file` (curaduria manual).
  3. Corre la skill `termometro-mundial` con `claude -p --output-format json` (sincrono).
  4. Registra el resultado en el HISTORIAL de skills, donde el community lo encuentra al
     llegar (Consola -> Generar copy -> Historial). No publica nada: es un borrador.

Uso:

    keni-termometro                         # usa la config guardada + RSS
    keni-termometro --marca claro-sports    # fuerza la marca
    keni-termometro --noticias-file hoy.txt # noticias de un archivo (no RSS)
    keni-termometro --dry-run               # imprime el prompt y NO llama a claude

El unico punto que toca el binario `claude` es `_ejecutar_claude` (reasignable: los tests
lo sustituyen por una fake con salida canned, sin red). La descarga de RSS vive tras
`rss._DESCARGADOR`, igualmente mockeable. Errores en espanol, sin tracebacks.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import biblioteca, preferencias, redes, repos, termometro
from .api import rss
from .api.termometro import ORIGEN_HISTORIAL, PROMPT_ID, _contexto, titulo_termometro
from .dominio import copy as dom_copy
from .dominio import generar as gen_dom
from .dominio import stream

# Wall-timeout (s) de la generacion programada. Mas holgado que la web porque corre sola.
_TIMEOUT_DEF = 600

# Cuantas noticias del RSS como mucho se pasan a la skill (ella elige el top 5-8).
_MAX_NOTICIAS_RSS = 25


class TermometroCronError(RuntimeError):
    """Fallo controlado del cron, con mensaje ya en espanol."""


def _argv_claude_json(prompt: str) -> list[str]:
    """argv de `claude -p <prompt> --output-format json [--effort N] [--max-budget-usd N]`.

    A diferencia de la web (stream-json para el progreso en vivo), aqui basta `json`:
    la salida se parsea de una vez con `stream.parsear_resultado_json`. Sin shell.
    """
    return [
        "claude", "-p", prompt,
        "--output-format", "json",
        *preferencias.arg_esfuerzo(),
        *stream.arg_presupuesto(),
    ]


def _ejecutar_claude_real(prompt: str, *, cwd: Path, timeout: int) -> str:
    """Corre `claude` SINCRONO y devuelve su stdout. Lanza `TermometroCronError` si falla."""
    if shutil.which("claude") is None:
        raise TermometroCronError(
            "No se encontró Claude Code en este equipo. Instálalo para generar el termómetro."
        )
    try:
        proc = subprocess.run(  # noqa: S603 -- argv lista, sin shell; prompt como argumento
            _argv_claude_json(prompt),
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise TermometroCronError(f"La generación tardó demasiado (más de {timeout} s) y se canceló.") from e
    except (OSError, ValueError) as e:
        raise TermometroCronError("No se pudo iniciar la generación del termómetro.") from e
    return proc.stdout


# Punto INYECTABLE: lo unico que toca el binario `claude`. Los tests lo reemplazan.
_ejecutar_claude = _ejecutar_claude_real


def _formatear_item(item: dict[str, object]) -> str:
    """Una linea de noticia para el prompt: '- titulo (fuente) — resumen [enlace]'."""
    titulo = str(item.get("titulo", "")).strip()
    linea = f"- {titulo}"
    fuente = str(item.get("fuente_nombre", "")).strip()
    if fuente:
        linea += f" ({fuente})"
    resumen = str(item.get("resumen", "")).strip()
    if resumen:
        linea += f" — {resumen}"
    enlace = str(item.get("enlace", "")).strip()
    if enlace:
        linea += f" [{enlace}]"
    return linea


def reunir_noticias_rss(*, marca: str = "", limite: int = _MAX_NOTICIAS_RSS) -> str:
    """Reune titulares recientes de los feeds RSS activos como texto para la skill.

    Toma los feeds `activo`; si hay `marca`, se queda con los de esa marca o sin marca
    (generales/internacionales). Aplica los filtros incluir/excluir de cada feed. Un
    feed que falla se OMITE (no rompe el cron). Devuelve hasta `limite` lineas.
    """
    fuentes = [f for f in repos.listar_fuentes_rss() if f.get("activo", True)]
    if marca:
        fuentes = [f for f in fuentes if f.get("marca") in ("", None, marca)]
    lineas: list[str] = []
    for fuente in fuentes:
        if len(lineas) >= limite:
            break
        try:
            items = rss.leer_items_fuente(fuente)
        except Exception:  # noqa: BLE001 -- un feed roto no debe tumbar el cron
            continue
        incluir = str(fuente.get("incluir", ""))
        excluir = str(fuente.get("excluir", ""))
        for item in items:
            if len(lineas) >= limite:
                break
            if not str(item.get("titulo", "")).strip():
                continue
            if not rss.item_pasa_filtros(item, incluir, excluir):
                continue
            lineas.append(_formatear_item(item))
    return "\n".join(lineas)


def generar_termometro(
    *,
    marca: str,
    noticias: str,
    numero: str = "",
    regiones: str = "",
    fecha: str = "",
    dry_run: bool = False,
    timeout: int = _TIMEOUT_DEF,
) -> dict[str, object]:
    """Arma el termometro de forma SINCRONA. Devuelve el resultado (o `{prompt}` en dry-run).

    Renderiza la invocacion del prompt `termometro-mundial`, corre `claude` (salvo dry-run),
    parsea la salida en PIEZAS por red y registra el historial. NO auto-crea publicaciones
    (procesar de galería): el community elige las redes al guardar desde la web. Mismo camino
    que la generación web, para que el termómetro del cron sea igual de "guardable".
    Lanza `TermometroCronError` si el prompt no esta instalado o si la generacion falla.
    """
    cuerpo = biblioteca.cuerpo_efectivo(PROMPT_ID)
    if cuerpo is None:
        raise TermometroCronError(
            "No está disponible el prompt del termómetro. Reinstala la Consola."
        )
    valores = {"noticias": noticias, "numero": numero, "regiones": regiones, "fecha": fecha}
    redes_ids = redes.ids()
    prompt = gen_dom.componer(
        cuerpo, biblioteca.editoriales_de_marca(marca), _contexto(valores),
        sin_emojis=True, redes_ids=redes_ids,
    )
    if dry_run:
        return {"prompt": prompt, "dry_run": True}

    stdout = _ejecutar_claude(prompt, cwd=gen_dom.cwd_generacion(), timeout=timeout)
    try:
        texto, metricas = stream.parsear_resultado_json(stdout)
    except stream.GeneracionError as e:
        raise TermometroCronError(str(e)) from e
    if not texto.strip():
        raise TermometroCronError("El asistente terminó sin devolver un termómetro.")

    titulo = titulo_termometro(fecha)
    procesar = dom_copy.construir_procesar_galeria(
        ORIGEN_HISTORIAL, marca, redes_ids=redes_ids, titulo_base=titulo, titulo_dado=titulo,
    )
    return procesar(texto, metricas)


def _construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="keni-termometro",
        description="Genera el Termómetro mundial (galería diaria de internacionales) para el cron.",
    )
    p.add_argument("--marca", default="", help="Marca (id canónico). Si se omite, usa la de la config.")
    p.add_argument("--numero", default="", help="Número de slides 5–8. Si se omite, usa la config.")
    p.add_argument("--regiones", default=None, help="Regiones a cubrir (CSV). Si se omite, usa la config.")
    p.add_argument("--fecha", default="", help="Fecha del termómetro (YYYY-MM-DD). Def.: hoy.")
    p.add_argument("--noticias-file", default="", help="Archivo con las noticias (en vez de RSS).")
    p.add_argument("--limite", type=int, default=_MAX_NOTICIAS_RSS, help="Máx. de noticias del RSS.")
    p.add_argument("--timeout", type=int, default=_TIMEOUT_DEF, help="Wall-timeout en segundos.")
    p.add_argument("--dry-run", action="store_true", help="Imprime el prompt y NO llama a claude.")
    return p


def _leer_noticias(args: argparse.Namespace, marca: str) -> str:
    """Resuelve las noticias: del archivo (`--noticias-file`) o del RSS activo."""
    if args.noticias_file:
        try:
            return Path(args.noticias_file).read_text(encoding="utf-8")
        except OSError as e:
            raise TermometroCronError(f"No se pudo leer el archivo de noticias: {args.noticias_file}.") from e
    return reunir_noticias_rss(marca=marca, limite=args.limite)


def main(argv: list[str] | None = None) -> int:
    args = _construir_parser().parse_args(argv)
    config = termometro.obtener()

    marca = (args.marca or config["marca"]).strip()
    if not marca:
        print(
            "No hay marca configurada para el termómetro. Pásala con --marca o guárdala en la consola.",
            file=sys.stderr,
        )
        return 1

    numero = args.numero or str(config["numero"])
    regiones = config["regiones"] if args.regiones is None else args.regiones
    fecha = args.fecha or date.today().isoformat()

    try:
        noticias = _leer_noticias(args, marca)
    except TermometroCronError as e:
        print(str(e), file=sys.stderr)
        return 1
    if not noticias.strip():
        print(
            "No hay noticias para armar el termómetro (sin feeds RSS activos con items ni archivo). "
            "Configura feeds en la consola o usa --noticias-file.",
            file=sys.stderr,
        )
        return 1

    try:
        resultado = generar_termometro(
            marca=marca, noticias=noticias, numero=numero, regiones=regiones,
            fecha=fecha, dry_run=args.dry_run, timeout=args.timeout,
        )
    except TermometroCronError as e:
        print(str(e), file=sys.stderr)
        return 1

    if args.dry_run:
        print(resultado["prompt"])
        return 0

    historial_id = resultado.get("historial_id", "")
    verdicto = resultado.get("verdicto", "")
    print(f"Termómetro generado para {marca} ({fecha}). Historial: {historial_id} · veredicto: {verdicto or '—'}.")
    print("Revísalo en la consola: Generar copy → Historial.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
