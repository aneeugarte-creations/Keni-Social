"""Perfiles de PATRONES editoriales por marca, derivados de métricas reales (Metricool).

Separa "lo que la marca hace" de "lo que le funciona": sobre las piezas publicadas de
una marca (texto + rendimiento por red), compara el cuartil TOP por engagement contra el
cuartil FONDO y destila bandas medibles (longitud, emojis, hashtags, gancho en mayúsculas,
pregunta) en un PERFIL JSON por marca. Ese perfil alimenta dos consumidores:

  - El doc editorial generado `editorial/rrss/<marca>/patrones` (vía `renderizar_doc`),
    que se inyecta al pipeline de copy junto a la voz: el modelo escribe a la primera
    dentro de las bandas reales de la marca, no de la intuición.
  - El VERIFICADOR de voz (`verificar_pieza`), un lint determinista que corre en el
    post-procesado del copy ANTES de la revisión humana: una pieza fuera de patrón no se
    bloquea, se ANOTA y degrada el revision `listo` -> `revisar`.

El perfil es REGENERABLE (`keni_consola.produccion.patrones_derivar`, CLI + daemon opcional): la
base viaja en el paquete (`patrones_inicial/<marca>.json`) y el runtime puede
sobrescribirla bajo el dir de datos (`<dir_config>/patrones/<marca>.json`), misma
filosofía base/store que `libprompts`. Sin perfil para una marca/red el verificador
NO inventa: devuelve sin avisos (degradación honesta).

Capas: este módulo es PURO (texto + dicts); no importa `dominio` ni toca red/BD.
La extracción de Metricool vive en `patrones_derivar` (frontera con keni_metricas).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

__all__ = [
    "rasgos_texto",
    "derivar_perfil",
    "cargar_perfil",
    "verificar_pieza",
    "renderizar_doc",
    "dir_perfiles_data",
    "dir_perfiles_inicial",
]

# Versión del esquema del perfil. Un cambio de forma incompatible la sube; el cargador
# ignora (con WARN del llamante) un perfil de versión mayor a la conocida.
VERSION_PERFIL = 1

# Mínimo de piezas de una marca×red para derivar bandas (cuartiles de >=20 piezas):
# por debajo, el perfil de esa red se omite (sin datos suficientes no se inventa).
MIN_MUESTRAS_RED = 80

# Piezas con menos visualizaciones que esto se excluyen de la derivación: con base
# diminuta el engagement_pct es basura (3 likes / 40 vistas = 7.5%) y contamina los
# cuartiles. No afecta al verificador (que mira texto, no métricas).
MIN_VISUALIZACIONES = 50

# --- Rasgos medibles de un texto -------------------------------------------------

# Mismos rangos pictográficos que `dominio.stream._RE_EMOJI`. DUPLICADO A PROPÓSITO:
# este módulo debe ser importable desde `dominio.copy` sin ciclos, así que no importa
# `dominio.stream`; si tocas un rango aquí, revisa allí (y viceversa).
_RE_EMOJI = re.compile(
    "["
    "\U0001f600-\U0001f64f"
    "\U0001f300-\U0001f5ff"
    "\U0001f680-\U0001f6ff"
    "\U0001fa70-\U0001faff"
    "\U0001f900-\U0001f9ff"
    "\U0001f1e6-\U0001f1ff"
    "\U00002600-\U000026ff"
    "\U00002700-\U000027bf"
    "]",
    flags=re.UNICODE,
)
# Modificadores que NO cuentan como emoji propio (unen/estilizan secuencias).
_RE_EMOJI_MODIFICADOR = re.compile("[\U0000fe0f\U0000200d\U0001f3fb-\U0001f3ff]")
# Bandera = PAR de regional indicators; se cuenta como UN emoji (ver `contar_emojis`).
_RE_BANDERA = re.compile("[\U0001f1e6-\U0001f1ff]{2}")

_RE_HASHTAG = re.compile(r"#[\wÀ-ɏ]+", re.UNICODE)


def contar_emojis(texto: str) -> int:
    """Número de emojis VISIBLES (aprox): codepoints pictográficos sin modificadores.

    Una bandera (par de regional indicators) cuenta 1; los selectores de variante,
    ZWJ y tonos de piel no cuentan. Una secuencia ZWJ compleja (👨‍👩‍👧) cuenta sus
    miembros — sobreestima, pero es estable y barato; las bandas del perfil se
    derivan con ESTA MISMA medida, así que el lint compara manzanas con manzanas.
    """
    if not texto:
        return 0
    limpio = _RE_EMOJI_MODIFICADOR.sub("", texto)
    limpio = _RE_BANDERA.sub("\U0001f1e6", limpio)  # cada bandera -> un solo cp
    return len(_RE_EMOJI.findall(limpio))


def contar_hashtags(texto: str) -> int:
    """Número de hashtags (#palabra, con acentos) en el texto."""
    return len(_RE_HASHTAG.findall(texto or ""))


def tiene_gancho_mayusculas(texto: str) -> bool:
    """True si el texto ABRE con un gancho en mayúsculas (>=6 letras antes de la primera
    minúscula), tipo "¡CHIVAS RECUPERÓ LA IDENTIDAD!" o "TITULAR CORTO | desarrollo".

    Solo mira la primera línea: ignora emojis, dígitos y puntuación; corta en la primera
    letra minúscula. 6 letras dejan fuera siglas sueltas ("NASA anunció...") sin perder
    ganchos cortos reales ("¡GOLAZO!").
    """
    primera = (texto or "").strip().splitlines()[0] if (texto or "").strip() else ""
    mayusculas = 0
    for c in primera:
        if c.isalpha():
            if c.islower():
                break
            mayusculas += 1
    return mayusculas >= 6


def tiene_pregunta(texto: str) -> bool:
    """True si el texto plantea una pregunta (¿ o ?)."""
    return "?" in (texto or "") or "¿" in (texto or "")


def rasgos_texto(texto: str) -> dict[str, object]:
    """Rasgos medibles de un copy: la MISMA medida en derivación y verificación."""
    t = texto or ""
    lineas_con_texto = [ln for ln in t.splitlines() if ln.strip()]
    return {
        "longitud": len(t),
        "emojis": contar_emojis(t),
        "hashtags": contar_hashtags(t),
        "gancho_mayusculas": tiene_gancho_mayusculas(t),
        "pregunta": tiene_pregunta(t),
        "multilinea": len(lineas_con_texto) > 1,
    }


# --- Derivación del perfil --------------------------------------------------------


def _percentil(valores: list[float], p: float) -> float:
    """Percentil por rango más cercano (lista YA ordenada). 0 si la lista está vacía."""
    if not valores:
        return 0.0
    k = max(0, min(len(valores) - 1, round(p / 100.0 * (len(valores) - 1))))
    return float(valores[k])


def _resumen_grupo(piezas: list[dict[str, object]]) -> dict[str, object]:
    """Estadísticos de un grupo de piezas (top o fondo) sobre sus rasgos de texto."""
    rasgos = [rasgos_texto(str(p.get("texto") or "")) for p in piezas]
    longitudes = sorted(float(r["longitud"]) for r in rasgos)
    emojis = sorted(float(r["emojis"]) for r in rasgos)
    hashtags = sorted(float(r["hashtags"]) for r in rasgos)
    engagement = sorted(float(p.get("engagement_pct") or 0.0) for p in piezas)

    def _pct(cond: list) -> float:
        return round(100.0 * sum(cond) / len(rasgos), 1) if rasgos else 0.0

    return {
        "n": len(piezas),
        "engagement_mediana_pct": round(_percentil(engagement, 50), 2),
        "longitud": {
            "p10": int(_percentil(longitudes, 10)),
            "p25": int(_percentil(longitudes, 25)),
            "p50": int(_percentil(longitudes, 50)),
            "p75": int(_percentil(longitudes, 75)),
            "p90": int(_percentil(longitudes, 90)),
        },
        "emojis": {
            "p50": int(_percentil(emojis, 50)),
            "p90": int(_percentil(emojis, 90)),
            "p95": int(_percentil(emojis, 95)),
        },
        "hashtags": {
            "p50": int(_percentil(hashtags, 50)),
            "p90": int(_percentil(hashtags, 90)),
            "p95": int(_percentil(hashtags, 95)),
        },
        "pct_gancho_mayusculas": _pct([r["gancho_mayusculas"] for r in rasgos]),
        "pct_pregunta": _pct([r["pregunta"] for r in rasgos]),
        "pct_multilinea": _pct([r["multilinea"] for r in rasgos]),
    }


def _formatos_top(piezas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Distribución de `formato` en un grupo (los 3 más frecuentes, con %)."""
    conteo: dict[str, int] = {}
    for p in piezas:
        f = str(p.get("formato") or "").strip()
        if f:
            conteo[f] = conteo.get(f, 0) + 1
    total = sum(conteo.values())
    if not total:
        return []
    top = sorted(conteo.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return [{"formato": f, "pct": round(100.0 * n / total, 1)} for f, n in top]


def _reglas_lint(top: dict[str, object], fondo: dict[str, object]) -> dict[str, object]:
    """Deriva las reglas del verificador a partir de top vs fondo. CONSERVADOR:
    solo emite una regla cuando el contraste es claro; en la duda, None (sin aviso).

    Son los umbrales del LINT, no la recomendación editorial (esa es la banda p25-p75
    del top, que viaja en el doc generado): el lint solo avisa cuando una pieza se
    sale de lo que la marca publica con éxito (fuera de p5-p95 del top) o pisa un
    rasgo que distingue al cuartil fondo.
    """
    lon_top: dict = top["longitud"]  # type: ignore[assignment]
    lon_fondo: dict = fondo["longitud"]  # type: ignore[assignment]
    # Banda de longitud tolerada: margen amplio sobre el top para no dar falsos
    # positivos... salvo que el FONDO tenga una FIRMA clara de longitud:
    #   - "el parrafón muere" (mediana del fondo >> mediana del top): tope más ceñido.
    #   - "el telegrama muere" (mediana del fondo << mediana del top): mínimo a medio
    #     camino entre el p75 del fondo y el p25 del top (separa ambas poblaciones).
    longitud_max = int(lon_top["p90"] * 1.5) if lon_top["p90"] else None
    longitud_min = int(lon_top["p10"] / 2) if lon_top["p10"] >= 80 else None
    if lon_fondo["p50"] > 1.5 * lon_top["p50"] and lon_top["p90"]:
        longitud_max = int(lon_top["p90"] * 1.2)
    if lon_fondo["p50"] < 0.5 * lon_top["p50"]:
        longitud_min = int((lon_fondo["p75"] + lon_top["p25"]) / 2)
    reglas: dict[str, object] = {
        "longitud_max": longitud_max,
        "longitud_min": longitud_min,
        "emojis_max": int(top["emojis"]["p95"]),  # type: ignore[index]
        "hashtags_max": int(top["hashtags"]["p95"]),  # type: ignore[index]
        "gancho_mayusculas": None,
        "pregunta": None,
    }
    pct_top = float(top["pct_gancho_mayusculas"])  # type: ignore[arg-type]
    pct_fondo = float(fondo["pct_gancho_mayusculas"])  # type: ignore[arg-type]
    if pct_top >= 60.0:
        reglas["gancho_mayusculas"] = "esperado"
    elif pct_top <= 25.0 and pct_fondo >= 30.0 and pct_fondo >= 2.5 * pct_top:
        # Firma del cuartil peor (p.ej. Nación Gamer en Facebook: 86% del fondo abre
        # en mayúsculas vs 22% del top): el gancho a gritos no es el registro.
        reglas["gancho_mayusculas"] = "evitar"
    pr_top = float(top["pct_pregunta"])  # type: ignore[arg-type]
    pr_fondo = float(fondo["pct_pregunta"])  # type: ignore[arg-type]
    if pr_top <= 12.0 and pr_fondo >= 1.5 * pr_top and pr_fondo >= 15.0:
        reglas["pregunta"] = "evitar"
    return reglas


def derivar_perfil(
    piezas: list[dict[str, object]],
    marca: str,
    *,
    desde: str = "",
    hasta: str = "",
    generado: str = "",
    min_muestras: int = MIN_MUESTRAS_RED,
) -> dict[str, object]:
    """Deriva el perfil de patrones de `marca` desde sus piezas publicadas.

    `piezas`: dicts con al menos `red`, `texto`, `engagement_pct`, `visualizaciones`
    (la forma de `Pieza.model_dump()` de keni_metricas, o el JSONL del extractor).
    Por red: ordena por engagement, separa cuartil TOP y FONDO y resume rasgos de
    ambos + reglas de lint. Una red con menos de `min_muestras` piezas útiles se
    omite. PURA: no lee disco ni red; `generado` lo aporta el llamante (timestamp).
    """
    por_red: dict[str, list[dict[str, object]]] = {}
    for p in piezas:
        texto = str(p.get("texto") or "").strip()
        if not texto:
            continue  # sin texto no hay patrón de copy que medir
        try:
            vis = int(p.get("visualizaciones") or 0)
        except (TypeError, ValueError):
            vis = 0
        if vis < MIN_VISUALIZACIONES:
            continue
        por_red.setdefault(str(p.get("red") or ""), []).append(p)

    redes: dict[str, dict[str, object]] = {}
    for red, lote in sorted(por_red.items()):
        if not red or len(lote) < min_muestras:
            continue
        orden = sorted(lote, key=lambda p: float(p.get("engagement_pct") or 0.0))
        cuarto = max(20, len(orden) // 4)
        fondo, top = orden[:cuarto], orden[-cuarto:]
        resumen_top, resumen_fondo = _resumen_grupo(top), _resumen_grupo(fondo)
        redes[red] = {
            "muestras": len(lote),
            "top": resumen_top,
            "fondo": resumen_fondo,
            "formatos_top": _formatos_top(top),
            "lint": _reglas_lint(resumen_top, resumen_fondo),
        }

    return {
        "version": VERSION_PERFIL,
        "marca": marca,
        "ventana": {"desde": desde, "hasta": hasta},
        "piezas": sum(r["muestras"] for r in redes.values()),  # type: ignore[misc]
        "generado": generado,
        "redes": redes,
    }


# --- Carga del perfil (data dir > base del paquete) ----------------------------


def dir_perfiles_inicial() -> Path:
    """Dir de los perfiles BASE que viajan en el paquete (`patrones_inicial/`)."""
    return Path(__file__).resolve().parent / "patrones_inicial"


def dir_perfiles_data() -> Path:
    """Dir de perfiles del RUNTIME (`<dir_config>/patrones`): lo escribe la re-derivación.

    Override por `KENI_PATRONES_DIR` (tests). Gana sobre la base, igual que el
    store de texto gana sobre `prompts_inicial`.
    """
    import os

    env = os.environ.get("KENI_PATRONES_DIR")
    if env:
        return Path(env).expanduser()
    from . import rutas

    return rutas.dir_config() / "patrones"


def cargar_perfil(marca: str) -> dict[str, object] | None:
    """Perfil de `marca` (id canónico slug-guion): runtime si existe, si no base.

    None si no hay perfil o no es utilizable (JSON roto, versión desconocida,
    sin `redes`): el verificador entonces NO avisa nada (sin datos no se inventa).
    """
    if not isinstance(marca, str) or not re.fullmatch(r"[a-z0-9-]+", marca or ""):
        return None
    for base in (dir_perfiles_data(), dir_perfiles_inicial()):
        ruta = base / f"{marca}.json"
        if not ruta.is_file():
            continue
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if (
            isinstance(datos, dict)
            and int(datos.get("version") or 0) <= VERSION_PERFIL
            and isinstance(datos.get("redes"), dict)
        ):
            return datos
    return None


# --- Verificador de voz (lint determinista del copy generado) ---------------------


def verificar_pieza(
    marca: str, red: str, texto: str, *, copy_unico: bool = True
) -> list[str]:
    """Avisos de PATRÓN de una pieza generada, contra el perfil real de la marca.

    Devuelve frases legibles para el revisor (vacío = dentro de patrón). NUNCA lanza
    ni bloquea: el consumidor decide (el post-procesado degrada `listo` -> `revisar`).
    `copy_unico`: el copy unificado va SIN hashtags por contrato (los pone el equipo);
    en ese modo cualquier hashtag es aviso aunque el patrón de la red los lleve.
    """
    avisos: list[str] = []
    r = rasgos_texto(texto)
    if copy_unico and int(r["hashtags"]) > 0:  # type: ignore[arg-type]
        avisos.append(
            f"{red}: lleva {r['hashtags']} hashtag(s); el copy unificado va sin hashtags "
            "(los añade el equipo por grupos)"
        )
    perfil = cargar_perfil(marca)
    redes = perfil.get("redes") if isinstance(perfil, dict) else None
    datos_red = redes.get(red) if isinstance(redes, dict) else None
    if not isinstance(datos_red, dict):
        return avisos
    lint = datos_red.get("lint")
    if not isinstance(lint, dict):
        return avisos

    emojis_max = lint.get("emojis_max")
    if isinstance(emojis_max, int) and int(r["emojis"]) > emojis_max:  # type: ignore[arg-type]
        detalle = "la marca publica sin emojis en esta red" if emojis_max == 0 else f"máx. medido {emojis_max}"
        avisos.append(f"{red}: {r['emojis']} emoji(s) — fuera del patrón real ({detalle})")
    if not copy_unico:
        hashtags_max = lint.get("hashtags_max")
        if isinstance(hashtags_max, int) and int(r["hashtags"]) > hashtags_max:  # type: ignore[arg-type]
            avisos.append(
                f"{red}: {r['hashtags']} hashtags — por encima del patrón real (máx. {hashtags_max})"
            )
    lon = int(r["longitud"])  # type: ignore[arg-type]
    lon_max, lon_min = lint.get("longitud_max"), lint.get("longitud_min")
    if isinstance(lon_max, int) and lon > lon_max:
        avisos.append(
            f"{red}: {lon} caracteres — los parrafones rinden mal en esta marca "
            f"(banda real hasta ~{lon_max})"
        )
    elif isinstance(lon_min, int) and lon < lon_min:
        avisos.append(
            f"{red}: {lon} caracteres — el telegrama sin contexto es el patrón del "
            f"cuartil peor (banda real desde ~{lon_min})"
        )
    gancho = lint.get("gancho_mayusculas")
    if gancho == "esperado" and not r["gancho_mayusculas"]:
        avisos.append(f"{red}: falta el gancho en MAYÚSCULAS de apertura, sello de la marca")
    elif gancho == "evitar" and r["gancho_mayusculas"]:
        avisos.append(f"{red}: gancho en MAYÚSCULAS — no es el registro de esta marca")
    if lint.get("pregunta") == "evitar" and r["pregunta"]:
        avisos.append(
            f"{red}: pregunta en el copy — correlaciona con el cuartil peor de esta marca"
        )
    return avisos


def avisos_de_piezas(
    marca: str, piezas: list[dict[str, object]], *, copy_unico: bool = True
) -> list[str]:
    """Avisos de patrón de un LOTE de piezas parseadas (forma de `stream.parsear_salida*`).

    En copy unificado el texto suele coincidir entre redes (X puede llevar una versión más
    corta): se lintea CADA pieza y se deduplican los avisos idénticos salvo el prefijo de red,
    conservando la red más restrictiva (la primera).
    """
    avisos: list[str] = []
    vistos: set[str] = set()
    for pieza in piezas:
        red = str(pieza.get("red") or "")
        texto = str(pieza.get("contenido") or "")
        for aviso in verificar_pieza(marca, red, texto, copy_unico=copy_unico):
            clave = aviso.split(": ", 1)[-1] if copy_unico else aviso
            if clave in vistos:
                continue
            vistos.add(clave)
            avisos.append(aviso)
    return avisos


# --- Render del doc editorial generado --------------------------------------------

_NOMBRE_RED = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "x": "X / Twitter",
}


def _linea_banda(etiqueta: str, grupo: dict[str, object]) -> str:
    lon: dict = grupo["longitud"]  # type: ignore[assignment]
    return (
        f"- {etiqueta}: longitud {lon['p25']}–{lon['p75']} (mediana {lon['p50']}), "
        f"emojis mediana {grupo['emojis']['p50']}, "  # type: ignore[index]
        f"hashtags mediana {grupo['hashtags']['p50']}; "  # type: ignore[index]
        f"{grupo['pct_gancho_mayusculas']}% abre en MAYÚSCULAS, "
        f"{grupo['pct_pregunta']}% pregunta."
    )


def renderizar_doc(perfil: dict[str, object], etiqueta_marca: str) -> str:
    """Cuerpo markdown del doc editorial `patrones` de una marca (SIN frontmatter).

    Lo que el redactor (humano o modelo) necesita saber de los DATOS: la banda del
    cuartil top por red, el contraste con el fondo y las señales con regla clara.
    El criterio cualitativo (léxico, temas, qué nunca hacer) NO va aquí: vive en
    `voz`/`reglas`, curados por humanos. Este doc se REGENERA entero.
    """
    v: dict = perfil.get("ventana") or {}  # type: ignore[assignment]
    lineas = [
        f"# Patrones medidos · {etiqueta_marca}",
        "",
        f"Derivado automáticamente de {perfil.get('piezas', 0):,} piezas publicadas "
        f"({v.get('desde', '?')} → {v.get('hasta', '?')}), comparando el cuartil de mayor "
        "engagement (TOP) contra el peor (FONDO) por red. Regenerable con "
        "`python -m keni_consola.produccion.patrones_derivar`; NO editar a mano (el criterio "
        "editorial va en Voz/Reglas). Estas bandas son recomendación medida: el copy "
        "nuevo debe caer dentro de la banda TOP de su red.",
        "",
    ]
    redes: dict = perfil.get("redes") or {}  # type: ignore[assignment]
    for red in ("instagram", "facebook", "tiktok", "youtube", "x"):
        datos = redes.get(red)
        if not isinstance(datos, dict):
            continue
        top: dict = datos["top"]
        fondo: dict = datos["fondo"]
        lineas.append(f"## {_NOMBRE_RED.get(red, red)} ({datos['muestras']:,} piezas)")
        lineas.append("")
        lineas.append(_linea_banda("TOP", top))
        lineas.append(_linea_banda("FONDO", fondo))
        if datos.get("formatos_top"):
            formatos = ", ".join(
                f"{f['formato']} ({f['pct']}%)" for f in datos["formatos_top"]  # type: ignore[index]
            )
            lineas.append(f"- Formatos del top: {formatos}.")
        lint: dict = datos.get("lint") or {}
        senales: list[str] = []
        if lint.get("gancho_mayusculas") == "esperado":
            senales.append("abre SIEMPRE con gancho en mayúsculas")
        elif lint.get("gancho_mayusculas") == "evitar":
            senales.append("sin gancho en mayúsculas (no es el registro)")
        if lint.get("pregunta") == "evitar":
            senales.append("evita la pregunta retórica (correlaciona con el cuartil peor)")
        if lint.get("emojis_max") == 0:
            senales.append("sin emojis")
        elif isinstance(lint.get("emojis_max"), int):
            senales.append(f"emojis hasta {lint['emojis_max']}")
        if senales:
            lineas.append(f"- Reglas claras del dato: {'; '.join(senales)}.")
        lineas.append("")
    return "\n".join(lineas).strip() + "\n"
