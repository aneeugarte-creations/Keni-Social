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

# Hashtags FIJOS de la marca (su firma: nombre/portal/lema) que van casi en cada post y NO dependen
# del tema. La etapa los inyecta SIEMPRE (no los elige la IA por relevancia, que se los saltaba). Se
# detectan por DATOS, no a mano: un tag es fijo si lo usa una fracción enorme de los posts de la
# marca (`ADOPCION_FIJO`), o si es el handle de la marca (su slug / "portal"+slug) con uso sólido
# (`FIJO_HANDLE_MIN`). Se cap­ean a `MAX_FIJOS` para dejar sitio a los temáticos.
ADOPCION_FIJO = 0.40
FIJO_HANDLE_MIN = 0.15
MAX_FIJOS = 2

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
    "fundacion": {
        "facebook": (279, 1.000, 5, 5),
        "instagram": (101, 1.000, 5, 5),
        "tiktok": (7, 0.857, 4, 4),
    },
    "nacion-gamer": {
        "facebook": (3957, 0.776, 3, 4),
        "instagram": (3866, 0.792, 3, 4),
        "tiktok": (846, 0.920, 4, 4),
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


def plano_de(marca: str) -> str:
    """Slug de la marca sin separadores (p. ej. `claro-sports` -> `clarosports`)."""
    return "".join(c for c in marca.lower() if c.isalnum())


def handles_de(marca: str) -> set[str]:
    """Tags que son el HANDLE de la marca: su slug sin separadores y "portal"+slug (p. ej.
    `claro-sports` -> {clarosports, portalclarosports}; `unotv` -> {unotv, portalunotv})."""
    plano = plano_de(marca)
    return {plano, f"portal{plano}"} if plano else set()


def excluidos_de(marca: str) -> set[str]:
    """Tags OPERATIVOS que NUNCA se sugieren: el `portal{slug}` que la web usa para detectar e
    incrustar los vídeos de redes (p. ej. `portalunotv`, `portalclarosports`). No es un hashtag
    de audiencia: es una señal máquina del equipo, así que se saca de candidatos Y de fijos."""
    plano = plano_de(marca)
    return {f"portal{plano}"} if plano else set()


def fijos_de(marca: str, adopcion: dict[str, float]) -> list[str]:
    """FIJOS de la marca por DATOS: muy usados (`ADOPCION_FIJO`) o el handle con uso sólido
    (`FIJO_HANDLE_MIN`). Plegados, ordenados por adopción desc, capados a `MAX_FIJOS`."""
    handles = handles_de(marca)
    cand: dict[str, float] = {}
    for tag, adop in adopcion.items():
        plg = plegar(tag)
        if adop >= ADOPCION_FIJO or (plg in handles and adop >= FIJO_HANDLE_MIN):
            cand[plg] = max(cand.get(plg, 0.0), adop)
    return [t for t, _ in sorted(cand.items(), key=lambda kv: -kv[1])[:MAX_FIJOS]]


def procesar(
    filas: list[tuple[str, str, int]], adopcion: dict[str, dict[str, float]]
) -> dict[str, dict]:
    """De (marca, tag, n) crudas a {marca: biblioteca}. Pliega, fusiona, umbral, ordena, marca fijos."""
    # marca -> tag_plegado -> {grafia: n} (para elegir la grafía más usada)
    crudo: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for marca, tag, n in filas:
        crudo[marca][plegar(tag)][tag] += n

    bibliotecas: dict[str, dict] = {}
    for marca, plegados in crudo.items():
        excluidos = {plegar(t) for t in excluidos_de(marca)}
        hashtags: list[dict] = []
        forma_de_plegado: dict[str, str] = {}
        for plg, grafias in plegados.items():
            total = sum(grafias.values())
            forma = max(grafias.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
            forma_de_plegado[plg] = forma
            if total < UMBRAL or plg in excluidos:
                continue
            hashtags.append({"tag": forma, "n": total})
        hashtags.sort(key=lambda h: (-h["n"], h["tag"]))

        # Fijos en la grafía de la biblioteca (forma más usada); solo los que están en el pool.
        en_pool = {h["tag"] for h in hashtags}
        fijos = [
            forma_de_plegado.get(plg, plg)
            for plg in fijos_de(marca, adopcion.get(marca, {}))
            if forma_de_plegado.get(plg, plg) in en_pool
        ]

        stats = ESTADISTICAS_RED.get(marca, {})
        conteo_por_red = {red: cantidad_red(s) for red, s in stats.items()}
        bibliotecas[marca] = {
            "marca": marca,
            "ventana": VENTANA,
            "umbral": UMBRAL,
            "fuente": "metricas_cache (Metricool)",
            "conteo_por_red": conteo_por_red,
            "fijos": fijos,
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


def leer_adopcion(ruta: Path | None) -> dict[str, dict[str, float]]:
    """Lee la adopción por tag (`marca|tag|adopcion`) de `adop.sql`. {} si no se pasa archivo.

    Sin este archivo no se marcan fijos (la biblioteca sigue siendo válida, solo sin firma fija).
    """
    adop: dict[str, dict[str, float]] = defaultdict(dict)
    if ruta is None or not ruta.is_file():
        return adop
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        marca, tag, valor = linea.split("|")
        adop[marca][tag] = float(valor)
    return adop


def main() -> int:
    ruta_adop = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    adopcion = leer_adopcion(ruta_adop)
    filas = leer_tsv(sys.stdin.read())
    bibliotecas = procesar(filas, adopcion)
    DESTINO.mkdir(parents=True, exist_ok=True)
    for marca, biblioteca in bibliotecas.items():
        ruta = DESTINO / f"{marca}.json"
        ruta.write_text(json.dumps(biblioteca, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"{marca}: {len(biblioteca['hashtags'])} hashtags (>= {UMBRAL}), "
            f"fijos={biblioteca['fijos']} -> {ruta.name}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
