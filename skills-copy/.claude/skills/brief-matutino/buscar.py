#!/usr/bin/env python3
"""brief-matutino: reúne señales de noticias para el brief de la mañana.

Trae titulares RECIENTES de GOOGLE NEWS (RSS, por tema) y las búsquedas en
TENDENCIA de GOOGLE TRENDS (RSS, por país), las normaliza con su antigüedad,
descarta lo más viejo que la ventana indicada y lo imprime como markdown
escaneable por stdout. Solo stdlib; sin dependencias ni claves.

Este script NO decide nada: solo recopila señales públicas y gratuitas. La
jerarquización y la sugerencia de formato las hace la skill (Claude) leyendo
esta salida + lo que el usuario pegue a mano (X, TikTok, cuentas que sigue).

Uso:
    python3 buscar.py --temas "selección mexicana; mañanera; sismo" --horas 36
    python3 buscar.py --temas "..." --geo MX --max-por-tema 6 --no-trends

Degrada con elegancia: si una fuente falla (sin red, formato cambiado, timeout),
se omite con un aviso y el resto sigue. Nunca revienta con un traceback crudo.
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

_UA = "Mozilla/5.0 (brief-matutino; +keni-social) Python-urllib"
_TIMEOUT = 12
# Espacio de nombres de Google Trends RSS (ht:approx_traffic, ht:news_item, …).
_NS_HT = "{https://trends.google.com/trending/rss}"


# --------------------------------------------------------------------------- #
# Utilidades                                                                   #
# --------------------------------------------------------------------------- #


def _bajar(url: str) -> str | None:
    """GET con User-Agent y timeout. Devuelve el cuerpo o None si algo falla."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 -- http(s) fijo
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001 -- el script degrada, no revienta
        print(f"  · aviso: no se pudo leer una fuente ({type(e).__name__}).", file=sys.stderr)
        return None


def _edad(pub: str | None) -> tuple[float | None, str]:
    """De un `pubDate` RFC-822 saca (horas_de_antiguedad, texto legible)."""
    if not pub:
        return None, "fecha desconocida"
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        horas = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except (TypeError, ValueError):
        return None, "fecha desconocida"
    if horas < 0:
        horas = 0.0
    if horas < 1:
        return horas, "hace <1 h"
    if horas < 24:
        return horas, f"hace {int(horas)} h"
    dias, resto = divmod(int(horas), 24)
    return horas, f"hace {dias} d {resto} h"


def _texto(elem, *nombres: str) -> str:
    """Primer hijo no vacío entre `nombres` (tolerante a None)."""
    for nombre in nombres:
        hijo = elem.find(nombre)
        if hijo is not None and hijo.text and hijo.text.strip():
            return hijo.text.strip()
    return ""


def _items(xml: str) -> list[ET.Element]:
    """Parsea el RSS y devuelve sus <item> (lista vacía si el XML es inválido)."""
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        return []
    return raiz.findall(".//item")


# --------------------------------------------------------------------------- #
# Fuentes                                                                      #
# --------------------------------------------------------------------------- #


def noticias_por_tema(tema: str, *, geo: str, hl: str, horas: int, maximo: int) -> list[dict]:
    """Titulares de Google News para `tema`, dentro de la ventana de frescura."""
    consulta = urllib.parse.quote(f"{tema} when:2d")
    ceid = f"{geo}:{hl.split('-')[0]}"
    url = (
        f"https://news.google.com/rss/search?q={consulta}"
        f"&hl={hl}&gl={geo}&ceid={urllib.parse.quote(ceid)}"
    )
    xml = _bajar(url)
    if not xml:
        return []
    salida: list[dict] = []
    for item in _items(xml):
        horas_edad, legible = _edad(_texto(item, "pubDate"))
        if horas_edad is not None and horas_edad > horas:
            continue
        salida.append(
            {
                "titular": _texto(item, "title"),
                "fuente": _texto(item, "source") or "—",
                "link": _texto(item, "link"),
                "horas": horas_edad if horas_edad is not None else 1e9,
                "edad": legible,
            }
        )
    salida.sort(key=lambda d: d["horas"])
    return salida[:maximo]


def tendencias(geo: str) -> list[dict]:
    """Búsquedas en tendencia ahora mismo en `geo` (Google Trends RSS)."""
    url = f"https://trends.google.com/trending/rss?geo={urllib.parse.quote(geo)}"
    xml = _bajar(url)
    if not xml:
        return []
    salida: list[dict] = []
    for item in _items(xml):
        trafico = _texto(item, f"{_NS_HT}approx_traffic")
        nota = item.find(f"{_NS_HT}news_item")
        nota_titulo = _texto(nota, f"{_NS_HT}news_item_title") if nota is not None else ""
        nota_url = _texto(nota, f"{_NS_HT}news_item_url") if nota is not None else ""
        _, legible = _edad(_texto(item, "pubDate"))
        salida.append(
            {
                "trend": _texto(item, "title"),
                "trafico": trafico,
                "edad": legible,
                "nota_titulo": nota_titulo,
                "nota_url": nota_url,
            }
        )
    return salida


# --------------------------------------------------------------------------- #
# Salida                                                                        #
# --------------------------------------------------------------------------- #


def _temas(crudo: str) -> list[str]:
    """Divide los temas por salto de línea o ';' (sin vacíos, sin duplicados)."""
    bruto = [t.strip() for parte in crudo.splitlines() for t in parte.split(";")]
    vistos: list[str] = []
    for t in bruto:
        if t and t.lower() not in {v.lower() for v in vistos}:
            vistos.append(t)
    return vistos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reúne señales para el brief de la mañana.")
    ap.add_argument("--temas", default="", help="Temas a vigilar (uno por línea o separados por ';').")
    ap.add_argument("--geo", default="MX", help="País (ISO-3166), def. MX.")
    ap.add_argument("--hl", default="es-419", help="Idioma de Google News, def. es-419.")
    ap.add_argument("--horas", type=int, default=36, help="Ventana de frescura en horas, def. 36.")
    ap.add_argument("--max-por-tema", type=int, default=6, help="Máx. titulares por tema, def. 6.")
    ap.add_argument("--no-trends", action="store_true", help="No consultar Google Trends.")
    ap.add_argument("--no-news", action="store_true", help="No consultar Google News.")
    args = ap.parse_args(argv)

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"# Señales del día (buscar.py · {ahora} · ventana {args.horas} h · {args.geo})\n")
    hubo_algo = False

    if not args.no_trends:
        trs = tendencias(args.geo)
        print(f"## Tendencias en Google Trends ({args.geo})\n")
        if trs:
            hubo_algo = True
            for t in trs:
                traf = f" · ~{t['trafico']}" if t["trafico"] else ""
                print(f"- **{t['trend']}**{traf} · {t['edad']}")
                if t["nota_titulo"]:
                    print(f"  - nota: {t['nota_titulo']} {('— ' + t['nota_url']) if t['nota_url'] else ''}".rstrip())
        else:
            print("_(sin datos de Trends ahora; usa las señales que pegó el usuario)_")
        print()

    if not args.no_news:
        temas = _temas(args.temas)
        print(f"## Noticias por tema (Google News, ≤ {args.horas} h)\n")
        if not temas:
            print("_(no se indicaron temas)_\n")
        for tema in temas:
            notas = noticias_por_tema(
                tema, geo=args.geo, hl=args.hl, horas=args.horas, maximo=args.max_por_tema
            )
            print(f"### {tema}")
            if notas:
                hubo_algo = True
                for n in notas:
                    print(f"- **{n['titular']}** · {n['fuente']} · {n['edad']}")
                    if n["link"]:
                        print(f"  - {n['link']}")
            else:
                print("_(sin titulares recientes dentro de la ventana)_")
            print()

    if not hubo_algo:
        print(
            "> No se obtuvieron señales en línea (puede ser falta de red o que Google "
            "cambió el feed). Continúa el brief con las señales que pegó el usuario."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
