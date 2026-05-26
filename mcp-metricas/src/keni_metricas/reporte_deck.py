"""Reporte semanal de deportes (Claro Sports) en presentacion (deck PPTX).

Reproduce el reporte que el equipo de redes de Claro Sports arma a mano cada
semana en Canva, pero generado automatico desde las metricas:

1. Mejores piezas de la semana: las N mejores de cada plataforma (Instagram,
   TikTok, Facebook) ordenadas por visualizaciones + interacciones, con su link.
2. Promocion de cuentas hermanas: algunos posteos de la semana de Claro Sports TV
   y Csport Golf, para seguir dandoles difusion.
3. Agenda editorial de la proxima semana: eventos principales y transmisiones
   propias, con que/como se van a cubrir. Curaduria manual (gustos del publico),
   se carga desde un TOML (--agenda); ver `agenda-editorial.ejemplo.toml`.

Read-only respecto a las redes: lee metricas y escribe un .pptx local; nunca
publica. `python-pptx` es opcional (extra `deck`) y se importa de forma perezosa,
para no cargar el MCP/servidor con una dependencia que solo usa este reporte.

Usable como CLI (`keni-reporte-deck`) para correr a mano o por cron.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from keni_shared import cuentas as _cuentas

from .formato import miles
from .fuentes.base import CuentaNoEncontrada
from .schema import Pieza, Plataforma

if TYPE_CHECKING:
    from .fuentes.base import FuenteMetricas

# La marca del reporte y sus cuentas hermanas (las que se promocionan aparte).
# Se DERIVAN de `keni_shared.cuentas` (H3/E1, fuente unica): antes vivian aqui y
# la consola las reexportaba via `servicio`; ahora ambos las leen del mismo sitio.
CUENTA_PRINCIPAL = _cuentas.CUENTA_DEPORTES_PRINCIPAL
CUENTAS_HERMANAS: tuple[str, ...] = _cuentas.CUENTAS_DEPORTES_HERMANAS
# Las tres plataformas que el reporte destaca, en el orden en que salen.
PLATAFORMAS_DESTACADAS: tuple[Plataforma, ...] = (
    Plataforma.instagram,
    Plataforma.tiktok,
    Plataforma.facebook,
)

# Nombres legibles de las plataformas para los titulos del deck.
_NOMBRE_PLATAFORMA: dict[str, str] = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "facebook": "Facebook",
    "x": "X",
    "youtube": "YouTube",
}


def _score(p: Pieza) -> int:
    """Criterio de orden del reporte: visualizaciones + interacciones."""
    return p.visualizaciones + p.interacciones


def _pieza_dict(p: Pieza) -> dict:
    return {
        "plataforma": p.plataforma.value,
        "titulo": p.titulo,
        "visualizaciones": p.visualizaciones,
        "interacciones": p.interacciones,
        "url": p.url,
        "publicado": p.publicado.isoformat(),
    }


def _mejores_por_plataforma(
    fuente: FuenteMetricas,
    cuenta_id: str,
    rango: str,
    plataformas: tuple[Plataforma, ...],
    n: int,
) -> dict[Plataforma, list[Pieza]]:
    """Top-n por plataforma. Usa el metodo dedicado de la fuente si lo expone
    (la muestra garantiza n por plataforma); si no, cae a agrupar un pool amplio
    de `mejores_piezas` (portable a cualquier FuenteMetricas y respeta el
    acotamiento por marca de FuenteScoped)."""
    plataformas = tuple(plataformas)
    metodo = getattr(fuente, "mejores_por_plataforma", None)
    if callable(metodo):
        return metodo(cuenta_id, rango, list(plataformas), n)

    pool_n = max(n * max(len(plataformas), 1) * 4, 20)
    pool = fuente.mejores_piezas(cuenta_id, rango, pool_n)
    por_plat: dict[Plataforma, list[Pieza]] = {p: [] for p in plataformas}
    for pieza in pool:
        if pieza.plataforma in por_plat:
            por_plat[pieza.plataforma].append(pieza)
    for p in por_plat:
        por_plat[p] = sorted(por_plat[p], key=_score, reverse=True)[:n]
    return por_plat


def agenda_vacia() -> dict:
    """Agenda placeholder cuando no se pasa --agenda."""
    return {
        "principales": [],
        "propios": [],
        "nota": "Pendiente de curaduria — agrega los eventos con --agenda (ver agenda-editorial.ejemplo.toml).",
    }


def cargar_agenda(ruta: str | Path) -> dict:
    """Carga la agenda editorial de la proxima semana desde un TOML.

    Formato (curaduria manual): una tabla `[[evento]]` por evento, con `nombre`,
    `plan` (que/como lo vamos a cubrir) y `tipo` ('principal' = evento externo
    que cubrimos, 'propio' = transmision propia). Devuelve los eventos agrupados
    en {'principales': [...], 'propios': [...]}.
    """
    p = Path(ruta).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"No existe el archivo de agenda: {p}")
    import tomllib

    try:
        datos = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"La agenda {p} tiene un error de sintaxis TOML: {e}") from e

    principales: list[dict] = []
    propios: list[dict] = []
    for i, ev in enumerate(datos.get("evento", []), 1):
        if not isinstance(ev, dict):
            raise ValueError(f"La entrada [[evento]] #{i} de la agenda no es una tabla valida.")
        nombre = str(ev.get("nombre", "")).strip()
        if not nombre:
            raise ValueError(f"La entrada [[evento]] #{i} de la agenda no tiene 'nombre'.")
        item = {"nombre": nombre, "plan": str(ev.get("plan", "")).strip()}
        tipo = str(ev.get("tipo", "principal")).strip().lower()
        if tipo in ("principal", "principales", "externo"):
            principales.append(item)
        elif tipo in ("propio", "propia", "propios", "transmision"):
            propios.append(item)
        else:
            raise ValueError(
                f"La entrada [[evento]] #{i} ('{nombre}') tiene un 'tipo' invalido: {tipo!r}. "
                "Usa 'principal' (evento externo) o 'propio' (transmision propia)."
            )
    return {"principales": principales, "propios": propios}


def construir_reporte_deportes(
    fuente: FuenteMetricas,
    *,
    rango: str = "semana",
    n_por_plataforma: int = 3,
    n_hermanas: int = 3,
    agenda: dict | None = None,
) -> dict:
    """Arma la estructura JSON-serializable del reporte semanal de deportes.

    Lanza `CuentaNoEncontrada` si la cuenta principal (Claro Sports) no esta en
    la fuente, y `ValueError` si el rango es invalido.
    """
    n_por_plataforma = max(1, min(int(n_por_plataforma), 10))
    n_hermanas = max(0, min(int(n_hermanas), 10))

    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    por_plat = _mejores_por_plataforma(fuente, CUENTA_PRINCIPAL, rango, PLATAFORMAS_DESTACADAS, n_por_plataforma)
    mejores = [
        {"plataforma": p.value, "piezas": [_pieza_dict(x) for x in por_plat.get(p, [])]}
        for p in PLATAFORMAS_DESTACADAS
    ]

    hermanas: list[dict] = []
    for cid in CUENTAS_HERMANAS:
        try:
            piezas = fuente.mejores_piezas(cid, rango, n_hermanas) if n_hermanas else []
        except CuentaNoEncontrada:
            continue  # cuenta hermana no configurada en esta fuente: se omite
        hermanas.append(
            {"cuenta": cid, "nombre": nombres.get(cid, cid), "piezas": [_pieza_dict(x) for x in piezas]}
        )

    return {
        "tipo": "reporte_deportes",
        "rango": rango,
        "generado": datetime.now(UTC).isoformat(timespec="seconds"),
        "fuente": fuente.nombre,
        "cuenta": {"id": CUENTA_PRINCIPAL, "nombre": nombres.get(CUENTA_PRINCIPAL, CUENTA_PRINCIPAL)},
        "mejores_por_plataforma": mejores,
        "promocion_hermanas": hermanas,
        "agenda": agenda or agenda_vacia(),
    }


# --- Render PPTX ------------------------------------------------------------

# Paleta de marca: un patron fijo para que todas las laminas salgan iguales.
_ROJO = (0xE2, 0x23, 0x1A)
_TINTA = (0x17, 0x18, 0x1C)
_GRIS = (0x70, 0x74, 0x7B)
_BLANCO = (0xFF, 0xFF, 0xFF)


def _cargar_pptx():
    """Importa python-pptx de forma perezosa; mensaje claro si falta el extra."""
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.enum.text import MSO_ANCHOR
        from pptx.util import Inches, Pt
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'Falta python-pptx para generar el deck. Instala el extra: pip install "keni-metricas[deck]".'
        ) from e
    return Presentation, Inches, Pt, RGBColor, MSO_SHAPE, MSO_ANCHOR


def render_pptx(rep: dict, ruta: str | Path) -> Path:
    """Renderiza el reporte a un .pptx con la linea visual de la marca y lo guarda."""
    Presentation, Inches, Pt, RGBColor, MSO_SHAPE, MSO_ANCHOR = _cargar_pptx()
    rojo, tinta, gris, blanco = (RGBColor(*c) for c in (_ROJO, _TINTA, _GRIS, _BLANCO))

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    ancho = prs.slide_width

    def diapo(titulo: str, subtitulo: str | None = None):
        slide = prs.slides.add_slide(prs.slide_layouts[6])  # layout en blanco
        barra = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, ancho, Inches(1.15))
        barra.fill.solid()
        barra.fill.fore_color.rgb = rojo
        barra.line.fill.background()
        barra.shadow.inherit = False
        tf = barra.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.margin_left = Inches(0.5)
        tf.margin_right = Inches(0.4)
        run = tf.paragraphs[0].add_run()
        run.text = titulo
        run.font.size = Pt(27)
        run.font.bold = True
        run.font.color.rgb = blanco
        if subtitulo:
            p = tf.add_paragraph()
            r = p.add_run()
            r.text = subtitulo
            r.font.size = Pt(13)
            r.font.color.rgb = blanco
        return slide

    def cuerpo(slide):
        tb = slide.shapes.add_textbox(Inches(0.6), Inches(1.45), Inches(12.1), Inches(5.7))
        tb.text_frame.word_wrap = True
        return tb.text_frame

    def parrafo(tf, texto, *, size=16, bold=False, color=tinta, antes=8):
        primero = len(tf.paragraphs) == 1 and not tf.paragraphs[0].runs
        p = tf.paragraphs[0] if primero else tf.add_paragraph()
        if not primero:
            p.space_before = Pt(antes)
        run = p.add_run()
        run.text = texto
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
        return p

    # 1. Portada
    sub = f"{rep['rango']} — generado {rep['generado'][:10]} · fuente: {rep['fuente']}"
    s = diapo(f"Reporte semanal · {rep['cuenta']['nombre']}", sub)
    parrafo(
        cuerpo(s),
        "Mejores piezas por plataforma · promocion de cuentas hermanas · agenda de la proxima semana.",
        size=15,
        color=gris,
        antes=0,
    )

    # 2. Mejores piezas, una lamina por plataforma
    for bloque in rep["mejores_por_plataforma"]:
        nombre = _NOMBRE_PLATAFORMA.get(bloque["plataforma"], bloque["plataforma"].title())
        tf = cuerpo(diapo(f"Top {nombre} de la semana"))
        if not bloque["piezas"]:
            parrafo(tf, "Sin piezas en el periodo.", color=gris, antes=0)
        for i, pz in enumerate(bloque["piezas"], 1):
            parrafo(tf, f"{i}. {pz['titulo']}", size=18, bold=True, antes=0 if i == 1 else 14)
            parrafo(
                tf,
                f"{miles(pz['visualizaciones'])} vistas · {miles(pz['interacciones'])} interacciones",
                size=14,
                antes=2,
            )
            if pz.get("url"):
                parrafo(tf, pz["url"], size=12, color=gris, antes=1)

    # 3. Promocion de cuentas hermanas
    tf = cuerpo(diapo("Promocion · cuentas hermanas"))
    if not rep["promocion_hermanas"]:
        parrafo(tf, "Sin cuentas hermanas configuradas.", color=gris, antes=0)
    for j, herm in enumerate(rep["promocion_hermanas"]):
        parrafo(tf, herm["nombre"], size=18, bold=True, color=rojo, antes=0 if j == 0 else 16)
        if not herm["piezas"]:
            parrafo(tf, "Sin posteos en el periodo.", size=13, color=gris, antes=2)
        for pz in herm["piezas"]:
            plat = _NOMBRE_PLATAFORMA.get(pz["plataforma"], pz["plataforma"])
            parrafo(tf, f"· {pz['titulo']} ({plat}, {miles(pz['visualizaciones'])} vistas)", size=14, antes=3)

    # 4. Agenda de la proxima semana (eventos principales + transmisiones propias)
    ag = rep["agenda"]
    nota = ag.get("nota")
    for titulo, clave in (
        ("Proxima semana · eventos principales", "principales"),
        ("Proxima semana · transmisiones propias", "propios"),
    ):
        tf = cuerpo(diapo(titulo))
        items = ag.get(clave) or []
        if not items:
            parrafo(tf, nota or "Pendiente de curaduria.", color=gris, antes=0)
            continue
        for k, ev in enumerate(items):
            parrafo(tf, ev["nombre"], size=18, bold=True, antes=0 if k == 0 else 14)
            if ev.get("plan"):
                parrafo(tf, ev["plan"], size=14, antes=2)

    destino = Path(ruta).expanduser()
    destino.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(destino))
    return destino


def _a_pdf(ruta_pptx: Path) -> Path | None:
    """Convierte el .pptx a PDF con LibreOffice si esta disponible; None si no."""
    import shutil
    import subprocess

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(ruta_pptx.parent), str(ruta_pptx)],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    pdf = ruta_pptx.with_suffix(".pdf")
    return pdf if pdf.exists() else None


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="keni-reporte-deck",
        description="Reporte semanal de deportes (Claro Sports) en presentacion (deck PPTX).",
    )
    ap.add_argument("--rango", default="semana", help="semana | mes | 7d | 30d (def: semana)")
    ap.add_argument("--top", type=int, default=3, help="nº de piezas por plataforma (def: 3)")
    ap.add_argument("--agenda", help="ruta a un TOML con la agenda editorial de la proxima semana")
    ap.add_argument("--salida", help="ruta del .pptx (def: reporte-deportes-<fecha>.pptx)")
    ap.add_argument(
        "--formato",
        choices=["pptx", "json"],
        default="pptx",
        help="pptx (def) | json (datos estructurados, sin render)",
    )
    ap.add_argument(
        "--pdf",
        action="store_true",
        help="ademas del pptx, intenta convertir a PDF (requiere LibreOffice)",
    )
    args = ap.parse_args(argv)

    from .config import cargar_config, construir_fuente

    fuente = construir_fuente(cargar_config())

    agenda = None
    if args.agenda:
        try:
            agenda = cargar_agenda(args.agenda)
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}", file=sys.stderr)
            return 2

    try:
        rep = construir_reporte_deportes(fuente, rango=args.rango, n_por_plataforma=args.top, agenda=agenda)
    except (ValueError, CuentaNoEncontrada) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.formato == "json":
        texto = json.dumps(rep, ensure_ascii=False, indent=2)
        if args.salida:
            Path(args.salida).expanduser().write_text(texto, encoding="utf-8")
            print(f"Datos escritos en {args.salida}")
        else:
            print(texto)
        return 0

    destino = (
        Path(args.salida).expanduser()
        if args.salida
        else Path(f"reporte-deportes-{date.today().isoformat()}.pptx")
    )
    try:
        destino = render_pptx(rep, destino)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    print(f"Deck escrito en {destino}")

    if args.pdf:
        pdf = _a_pdf(destino)
        if pdf:
            print(f"PDF escrito en {pdf}")
        else:
            print("Aviso: no se pudo generar el PDF (¿LibreOffice instalado?). El .pptx sí se genero.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
