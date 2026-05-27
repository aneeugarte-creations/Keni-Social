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

from .formato import AVISO_MUESTRA_TXT, es_fuente_muestra, miles
from .fuentes.base import CuentaNoEncontrada
from .schema import RANGO_SEMANA_CERRADA, Pieza, Plataforma, resolver_rango

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

# Etiqueta legible del rango para los titulos del deck/preview.
_ETIQUETA_RANGO: dict[str, str] = {
    "semana_cerrada": "Semana cerrada",
    "semana": "Últimos 7 días",
    "7d": "Últimos 7 días",
    "mes": "Últimos 30 días",
    "30d": "Últimos 30 días",
}


def etiqueta_periodo(rep: dict) -> str:
    """Texto del periodo del reporte: "lun 18 — dom 24 may 2026" si hay fechas.

    Cae a la etiqueta del rango si el reporte no trae `periodo` (compatibilidad
    con dicts antiguos). Pensado para el subtitulo de la portada y la preview.
    """
    etiqueta = _ETIQUETA_RANGO.get(rep.get("rango", ""), rep.get("rango", ""))
    periodo = rep.get("periodo") or {}
    desde, hasta = periodo.get("desde"), periodo.get("hasta")
    if not (desde and hasta):
        return etiqueta
    try:
        d = date.fromisoformat(desde)
        h = date.fromisoformat(hasta)
    except (TypeError, ValueError):
        return etiqueta
    _meses = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
    if d.year == h.year:
        rango_fechas = f"{d.day} {_meses[d.month - 1]} — {h.day} {_meses[h.month - 1]} {h.year}"
    else:
        rango_fechas = f"{d.day} {_meses[d.month - 1]} {d.year} — {h.day} {_meses[h.month - 1]} {h.year}"
    return f"{etiqueta} · {rango_fechas}"


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
    rango: str = RANGO_SEMANA_CERRADA,
    n_por_plataforma: int = 3,
    n_hermanas: int = 3,
    agenda: dict | None = None,
) -> dict:
    """Arma la estructura JSON-serializable del reporte semanal de deportes.

    Por defecto el rango es `semana_cerrada`: lunes->domingo de la ultima semana
    natural cerrada (domingo incluido), el reporte del lunes (#141). El periodo
    resuelto (desde/hasta) va en el reporte para que el deck lo muestre.

    Las CUENTAS HERMANAS se piden a la misma capa de metricas que la cuenta
    principal: si la fuente es la muestra, salen rotuladas como muestra; si es real
    pero la cuenta no esta configurada (faltan permisos Meta/TikTok), se marca
    `sin_datos_reales` y NO se inventan cifras (honestidad, regla de producto).

    Lanza `CuentaNoEncontrada` si la cuenta principal (Claro Sports) no esta en
    la fuente, y `ValueError` si el rango es invalido.
    """
    n_por_plataforma = max(1, min(int(n_por_plataforma), 10))
    n_hermanas = max(0, min(int(n_hermanas), 10))

    # Periodo concreto del reporte (valida el rango y lo expone para el deck/preview).
    desde, hasta, _dias = resolver_rango(rango)

    es_muestra = es_fuente_muestra(fuente.nombre)
    nombres = {c.id: c.nombre for c in fuente.cuentas()}
    por_plat = _mejores_por_plataforma(fuente, CUENTA_PRINCIPAL, rango, PLATAFORMAS_DESTACADAS, n_por_plataforma)
    mejores = [
        {"plataforma": p.value, "piezas": [_pieza_dict(x) for x in por_plat.get(p, [])]}
        for p in PLATAFORMAS_DESTACADAS
    ]

    hermanas: list[dict] = []
    for cid in CUENTAS_HERMANAS:
        item: dict = {
            "cuenta": cid,
            "nombre": nombres.get(cid, cid),
            "piezas": [],
            # rotulo honesto de procedencia: "muestra" | "real" | "sin_datos_reales"
            "datos": "muestra" if es_muestra else "real",
        }
        if n_hermanas:
            try:
                piezas = fuente.mejores_piezas(cid, rango, n_hermanas)
                item["piezas"] = [_pieza_dict(x) for x in piezas]
            except CuentaNoEncontrada:
                # La fuente NO tiene esta cuenta hermana (p.ej. la real, sin permisos
                # Meta/TikTok para ella). No la omitimos en silencio: la mostramos sin
                # cifras y rotulada, para no fingir datos que no tenemos (#141).
                item["datos"] = "sin_datos_reales"
        hermanas.append(item)

    return {
        "tipo": "reporte_deportes",
        "rango": rango,
        "periodo": {"desde": desde.isoformat(), "hasta": hasta.isoformat()},
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
    sub = f"{etiqueta_periodo(rep)} — generado {rep['generado'][:10]} · fuente: {rep['fuente']}"
    s = diapo(f"Reporte semanal · {rep['cuenta']['nombre']}", sub)
    tf_portada = cuerpo(s)
    # Aviso DESTACADO si son datos de muestra (no solo el campo `fuente` del
    # subtitulo): rojo y en negrita para que sea imposible confundir cifras
    # sinteticas con reales en un deck que ve un humano (issue #131).
    if es_fuente_muestra(rep.get("fuente")):
        parrafo(tf_portada, AVISO_MUESTRA_TXT, size=16, bold=True, color=rojo, antes=0)
    parrafo(
        tf_portada,
        "Mejores piezas por plataforma · promocion de cuentas hermanas · agenda de la proxima semana.",
        size=15,
        color=gris,
        antes=0 if not es_fuente_muestra(rep.get("fuente")) else 10,
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

    # 3. Promocion de cuentas hermanas (Claro Sports TV, Csport Golf)
    tf = cuerpo(diapo("Promocion · cuentas hermanas"))
    if not rep["promocion_hermanas"]:
        parrafo(tf, "Sin cuentas hermanas configuradas.", color=gris, antes=0)
    for j, herm in enumerate(rep["promocion_hermanas"]):
        parrafo(tf, herm["nombre"], size=18, bold=True, color=rojo, antes=0 if j == 0 else 16)
        # Honestidad de procedencia por cuenta (#141): si la fuente real no tiene
        # esta cuenta (faltan permisos), se dice y NO se inventan numeros.
        if herm.get("datos") == "sin_datos_reales":
            parrafo(tf, "Sin datos reales (cuenta no conectada todavía).", size=13, color=gris, antes=2)
            continue
        if not herm["piezas"]:
            parrafo(tf, "Sin posteos en el periodo.", size=13, color=gris, antes=2)
        for pz in herm["piezas"]:
            plat = _NOMBRE_PLATAFORMA.get(pz["plataforma"], pz["plataforma"])
            parrafo(
                tf,
                f"· {pz['titulo']} ({plat}, {miles(pz['visualizaciones'])} vistas · "
                f"{miles(pz['interacciones'])} interacciones)",
                size=14,
                antes=3,
            )
            if pz.get("url"):
                parrafo(tf, f"  {pz['url']}", size=11, color=gris, antes=1)

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


# --- Render PDF nativo (reportlab, sin LibreOffice) -------------------------


def _cargar_reportlab():
    """Importa reportlab de forma perezosa; mensaje claro si falta el extra."""
    try:
        from reportlab.lib.colors import Color
        from reportlab.lib.pagesizes import landscape
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
    except ModuleNotFoundError as e:
        raise RuntimeError(
            'Falta reportlab para generar el PDF nativo. Instala el extra: pip install "keni-metricas[deck]".'
        ) from e
    return canvas, landscape, inch, Color


def render_pdf(rep: dict, ruta: str | Path) -> Path:
    """Renderiza el reporte a PDF NATIVO (reportlab), sin LibreOffice (#141).

    Mismo contenido y misma estructura de laminas que `render_pptx` (portada, top
    por red, cuentas hermanas, agenda) con la linea visual roja de Claro Sports,
    en formato 16:9 horizontal. Portable: reportlab es Python puro, no necesita
    binarios externos. Lanza `RuntimeError` si falta el extra.
    """
    canvas, landscape, inch, Color = _cargar_reportlab()
    rojo = Color(*[c / 255 for c in _ROJO])
    tinta = Color(*[c / 255 for c in _TINTA])
    gris = Color(*[c / 255 for c in _GRIS])
    blanco = Color(*[c / 255 for c in _BLANCO])

    # Misma proporcion 16:9 que el deck (13.333 x 7.5 in).
    ancho, alto = 13.333 * inch, 7.5 * inch
    destino = Path(ruta).expanduser()
    destino.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(destino), pagesize=(ancho, alto))

    margen = 0.6 * inch
    barra_alto = 1.15 * inch

    def nueva_lamina(titulo: str, subtitulo: str | None = None):
        # Barra de titulo roja (linea visual de marca).
        c.setFillColor(rojo)
        c.rect(0, alto - barra_alto, ancho, barra_alto, stroke=0, fill=1)
        c.setFillColor(blanco)
        c.setFont("Helvetica-Bold", 27)
        y_titulo = alto - (0.62 * inch if subtitulo else 0.72 * inch)
        c.drawString(0.5 * inch, y_titulo, titulo)
        if subtitulo:
            c.setFont("Helvetica", 13)
            c.drawString(0.5 * inch, alto - 0.95 * inch, subtitulo)
        # cursor del cuerpo (de arriba a abajo)
        return [alto - barra_alto - 0.35 * inch]

    def linea(cursor, texto, *, size=16, bold=False, color=tinta, antes=8, sangria=0.0):
        cursor[0] -= antes
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        # recorte simple para no desbordar el ancho util
        max_chars = int((ancho - 2 * margen - sangria * inch) / (size * 0.5))
        if len(texto) > max_chars > 3:
            texto = texto[: max_chars - 1] + "…"
        c.drawString(margen + sangria * inch, cursor[0], texto)
        cursor[0] -= size * 1.05

    def cerrar_lamina():
        c.showPage()

    # 1. Portada
    cur = nueva_lamina(
        f"Reporte semanal · {rep['cuenta']['nombre']}",
        f"{etiqueta_periodo(rep)} — generado {rep['generado'][:10]} · fuente: {rep['fuente']}",
    )
    if es_fuente_muestra(rep.get("fuente")):
        linea(cur, AVISO_MUESTRA_TXT, size=15, bold=True, color=rojo, antes=10)
    linea(
        cur,
        "Mejores piezas por plataforma · promocion de cuentas hermanas · agenda de la proxima semana.",
        size=14,
        color=gris,
        antes=12,
    )
    cerrar_lamina()

    # 2. Mejores piezas, una lamina por plataforma
    for bloque in rep["mejores_por_plataforma"]:
        nombre = _NOMBRE_PLATAFORMA.get(bloque["plataforma"], bloque["plataforma"].title())
        cur = nueva_lamina(f"Top {nombre} de la semana")
        if not bloque["piezas"]:
            linea(cur, "Sin piezas en el periodo.", color=gris, antes=0)
        for i, pz in enumerate(bloque["piezas"], 1):
            linea(cur, f"{i}. {pz['titulo']}", size=18, bold=True, antes=0 if i == 1 else 14)
            linea(
                cur,
                f"{miles(pz['visualizaciones'])} vistas · {miles(pz['interacciones'])} interacciones",
                size=14,
                antes=2,
            )
            if pz.get("url"):
                linea(cur, pz["url"], size=11, color=gris, antes=1)
        cerrar_lamina()

    # 3. Promocion de cuentas hermanas
    cur = nueva_lamina("Promocion · cuentas hermanas")
    if not rep["promocion_hermanas"]:
        linea(cur, "Sin cuentas hermanas configuradas.", color=gris, antes=0)
    for j, herm in enumerate(rep["promocion_hermanas"]):
        linea(cur, herm["nombre"], size=18, bold=True, color=rojo, antes=0 if j == 0 else 16)
        if herm.get("datos") == "sin_datos_reales":
            linea(cur, "Sin datos reales (cuenta no conectada todavía).", size=13, color=gris, antes=2)
            continue
        if not herm["piezas"]:
            linea(cur, "Sin posteos en el periodo.", size=13, color=gris, antes=2)
        for pz in herm["piezas"]:
            plat = _NOMBRE_PLATAFORMA.get(pz["plataforma"], pz["plataforma"])
            linea(
                cur,
                f"· {pz['titulo']} ({plat}, {miles(pz['visualizaciones'])} vistas · "
                f"{miles(pz['interacciones'])} interacciones)",
                size=14,
                antes=3,
            )
    cerrar_lamina()

    # 4. Agenda de la proxima semana
    ag = rep["agenda"]
    nota = ag.get("nota")
    for titulo, clave in (
        ("Proxima semana · eventos principales", "principales"),
        ("Proxima semana · transmisiones propias", "propios"),
    ):
        cur = nueva_lamina(titulo)
        items = ag.get(clave) or []
        if not items:
            linea(cur, nota or "Pendiente de curaduria.", color=gris, antes=0)
        else:
            for k, ev in enumerate(items):
                linea(cur, ev["nombre"], size=18, bold=True, antes=0 if k == 0 else 14)
                if ev.get("plan"):
                    linea(cur, ev["plan"], size=14, antes=2)
        cerrar_lamina()

    c.save()
    return destino


# NOTA: el camino antiguo de PDF dependia de LibreOffice (convertir el .pptx con
# `soffice --convert-to pdf`). Se RETIRO en favor de `render_pdf` (reportlab, nativo
# y portable, sin binarios externos). Ver `docs/reporte-deportes.md` y el issue #141.


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="keni-reporte-deck",
        description="Reporte semanal de deportes (Claro Sports) en presentacion (deck PPTX).",
    )
    ap.add_argument(
        "--rango",
        default=RANGO_SEMANA_CERRADA,
        help="semana_cerrada (def, lun->dom de la semana cerrada) | semana | mes | 7d | 30d",
    )
    ap.add_argument("--top", type=int, default=3, help="nº de piezas por plataforma (def: 3)")
    ap.add_argument("--agenda", help="ruta a un TOML con la agenda editorial de la proxima semana")
    ap.add_argument("--salida", help="ruta de salida (def: reporte-deportes-<fecha>.<ext>)")
    ap.add_argument(
        "--formato",
        choices=["pptx", "pdf", "json"],
        default="pptx",
        help="pptx (def) | pdf (nativo, sin LibreOffice) | json (datos, sin render)",
    )
    ap.add_argument(
        "--pdf",
        action="store_true",
        help="ademas del pptx, genera tambien el PDF nativo (reportlab, sin LibreOffice)",
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

    ext = "pdf" if args.formato == "pdf" else "pptx"
    destino = (
        Path(args.salida).expanduser()
        if args.salida
        else Path(f"reporte-deportes-{date.today().isoformat()}.{ext}")
    )
    try:
        if args.formato == "pdf":
            destino = render_pdf(rep, destino)
        else:
            destino = render_pptx(rep, destino)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
    print(f"Deck escrito en {destino}")

    # --pdf: PDF adicional al lado del .pptx (solo tiene sentido cuando el formato
    # principal es pptx). Camino NATIVO (reportlab), no requiere LibreOffice.
    if args.pdf and args.formato == "pptx":
        try:
            pdf = render_pdf(rep, destino.with_suffix(".pdf"))
            print(f"PDF escrito en {pdf}")
        except RuntimeError as e:
            print(f"Aviso: no se pudo generar el PDF ({e}). El .pptx sí se genero.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
