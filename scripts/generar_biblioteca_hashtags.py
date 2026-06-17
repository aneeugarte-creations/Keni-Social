#!/usr/bin/env python3
"""Genera la biblioteca de hashtags por marca a partir de TODO el historial.

La biblioteca es el POOL de candidatos que la etapa `sugerir_hashtags` ofrece al
revisar una pieza (solo cuando `falta_hashtags`). Se saca del historial real de
publicaciones de cada marca (UnoTV / Claro Sports), tal y como lo expone Metricool:
en producción ese historial vive cacheado en la tabla `metricas_cache`
(`payload->'piezas'[].texto` lleva el caption con los `#hashtag`).

Cómo se obtiene el insumo (read-only, reproducible):

    ssh latitude
    cd /home/ubuntu/keni-social/deploy
    docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A' <<'SQL'
    SELECT marca, tag, count(*) AS n FROM (
      SELECT (CASE WHEN clave LIKE '%:claro_sports' THEN 'claro-sports' ELSE 'unotv' END) AS marca,
             lower((regexp_matches(p->>'texto', '#([[:alnum:]_À-ɏ]+)', 'g'))[1]) AS tag
      FROM metricas_cache, LATERAL jsonb_array_elements(payload->'piezas') p
      WHERE clave IN ('v2:piezas_listado:rango:<desde>_<hasta>:claro_sports',
                      'v2:piezas_listado:rango:<desde>_<hasta>:unotv')
    ) s
    WHERE tag !~ '^[0-9]+$'           -- descarta fragmentos de entidad HTML (#8230, ...)
    GROUP BY marca, tag HAVING count(*) >= 8 ORDER BY marca, n DESC;
    SQL

El TSV resultante (`marca|tag|n`) se pasa por STDIN a este script:

    python3 scripts/generar_biblioteca_hashtags.py < htags_raw.tsv

y reescribe `consola/src/keni_consola/hashtags_biblioteca/datos/<marca>.json`.

Procesado: pliega acentos (á→a, ü→u; conserva ñ) para fusionar variantes
(`méxico`+`mexico`), se queda con la grafía más frecuente como forma a inyectar,
descarta lo poco común (umbral por defecto >= 20 usos) y ordena por frecuencia.

Las medianas por red (`ESTADISTICAS_RED`) salen de la consulta gemela `med.sql`
(adopción + percentile_cont(0.5)) y fijan CUÁNTOS hashtags sugerir por marca+red.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# Umbral de inclusión: un hashtag entra en la biblioteca si se usó >= estas veces
# en el historial de la marca (descarta duplicados y lo muy poco común).
UMBRAL = 20

# Adopción mínima para que una red merezca sugerencia. Por debajo (p.ej. YouTube,
# 2.3% de posts con hashtags) la red no usa hashtags: se sugieren 0.
ADOPCION_MINIMA = 0.25

# Tope de sugerencias por pieza (ninguna red real supera 5; deja margen).
MAX_SUGERENCIAS = 8

# Salida de `med.sql` (percentile_cont(0.5) de #hashtags por post, y adopción) sobre
# la ventana anual por marca. med_users = mediana entre los posts que SÍ etiquetan.
#   marca -> red -> (posts, adopcion, med_all, med_users)
ESTADISTICAS_RED: dict[str, dict[str, tuple[int, float, int, int]]] = {
    "claro-sports": {
        "facebook": (14290, 0.335, 0, 1),
        "instagram": (12317, 0.984, 5, 5),
        "youtube": (8636, 0.023, 0, 1),
        "tiktok": (2650, 0.999, 5, 5),
    },
    "unotv": {
        "facebook": (11996, 0.532, 1, 5),
        "instagram": (7868, 0.935, 5, 5),
        "tiktok": (2410, 0.940, 5, 5),
    },
}

# Ventana del historial usado para esta foto (para trazabilidad en el JSON).
VENTANA = "2025-06-17_2026-06-16"

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "consola/src/keni_consola/hashtags_biblioteca/datos"


def plegar(s: str) -> str:
    """Pliega marcas de acento (á→a, ü→u) conservando la ñ, para fusionar variantes."""
    out: list[str] = []
    for ch in s:
        if ch in "ñ":
            out.append(ch)
            continue
        descompuesto = unicodedata.normalize("NFD", ch)
        out.append("".join(c for c in descompuesto if unicodedata.category(c) != "Mn"))
    return "".join(out)


def cantidad_red(stats: tuple[int, float, int, int]) -> int:
    """CUÁNTOS sugerir en una red: la mediana entre quienes etiquetan, 0 si casi nadie."""
    _posts, adopcion, _med_all, med_users = stats
    if adopcion < ADOPCION_MINIMA:
        return 0
    return max(0, min(MAX_SUGERENCIAS, med_users))


def procesar(filas: list[tuple[str, str, int]]) -> dict[str, dict]:
    """De (marca, tag, n) crudas a {marca: biblioteca}. Pliega, fusiona, umbral, ordena."""
    # marca -> tag_plegado -> {grafia: n} (para elegir la grafía más usada)
    crudo: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for marca, tag, n in filas:
        crudo[marca][plegar(tag)][tag] += n

    bibliotecas: dict[str, dict] = {}
    for marca, plegados in crudo.items():
        hashtags: list[dict] = []
        for grafias in plegados.values():
            total = sum(grafias.values())
            if total < UMBRAL:
                continue
            forma = max(grafias.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
            hashtags.append({"tag": forma, "n": total})
        hashtags.sort(key=lambda h: (-h["n"], h["tag"]))

        stats = ESTADISTICAS_RED.get(marca, {})
        conteo_por_red = {red: cantidad_red(s) for red, s in stats.items()}
        bibliotecas[marca] = {
            "marca": marca,
            "ventana": VENTANA,
            "umbral": UMBRAL,
            "fuente": "metricas_cache (Metricool)",
            "conteo_por_red": conteo_por_red,
            "estadisticas_por_red": {
                red: {"posts": p, "adopcion": a, "mediana": m, "mediana_con_uso": mu}
                for red, (p, a, m, mu) in stats.items()
            },
            "hashtags": hashtags,
        }
    return bibliotecas


def leer_tsv(texto: str) -> list[tuple[str, str, int]]:
    filas: list[tuple[str, str, int]] = []
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        marca, tag, n = linea.split("|")
        filas.append((marca, tag, int(n)))
    return filas


def main() -> int:
    filas = leer_tsv(sys.stdin.read())
    bibliotecas = procesar(filas)
    DESTINO.mkdir(parents=True, exist_ok=True)
    for marca, biblioteca in bibliotecas.items():
        ruta = DESTINO / f"{marca}.json"
        ruta.write_text(json.dumps(biblioteca, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"{marca}: {len(biblioteca['hashtags'])} hashtags (>= {UMBRAL}) -> {ruta.name}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
