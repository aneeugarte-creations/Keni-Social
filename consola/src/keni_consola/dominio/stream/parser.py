"""Parser del dominio STREAM: reparto de la salida cruda en piezas por red.

Aqui vive el parseo del texto generado por `claude` en piezas por plataforma: localizar
el bloque ```json cercado (o, como fallback, repartir por encabezados de plataforma),
mapear cada pieza a su red canonica, la variante de copy UNIFICADO (un copy + copy_in
para todas las redes, con `texto_corto` para las redes estrechas y carrusel editorial) y
la reparacion tolerante del objeto plano cuando el modelo deja comillas sin escapar.
Logica PURA: no importa de `api/` ni de `generaciones`.
"""

from __future__ import annotations

import json
import re

from ... import limites_plataforma
from .texto import quitar_emojis

# Bloque ```json ... ``` cercado (el ultimo de la salida es el de las piezas).
# Tolera "json"/"JSON" tras las comillas y espacios; captura el cuerpo (no greedy).
_RE_BLOQUE_JSON = re.compile(r"```[ \t]*[jJ][sS][oO][nN][ \t]*\r?\n(.*?)```", re.DOTALL)


# --------------------------------------------------------------------------- #
# Reparto de la salida en piezas por red (JSON cercado o, fallback, encabezados) #
# --------------------------------------------------------------------------- #

# Variantes tolerantes de etiqueta -> id canonico de `redes`. En minusculas y sin
# `#`/`*`/`:` (esos se quitan al normalizar el encabezado). El orden no importa: el
# reparto final se emite en el orden fijo de las redes pedidas.
_ALIAS_RED: dict[str, str] = {
    "x": "x",
    "x/twitter": "x",
    "twitter": "x",
    "instagram": "instagram",
    "ig": "instagram",
    "facebook": "facebook",
    "fb": "facebook",
    "tiktok": "tiktok",
    "youtube": "youtube",
}

# Encabezado de plataforma: linea cuyo unico contenido (ignorando `#`/`##`, `**`,
# `:` y espacios) es una de las etiquetas conocidas. Captura la etiqueta cruda.
# El sufijo tolera `:` y `*` en cualquier orden ("Instagram:", "**Twitter**",
# "**Instagram:**").
_RE_ENCABEZADO_RED = re.compile(
    r"^[ \t]*#{0,6}[ \t]*\*{0,2}[ \t]*"
    r"([A-Za-z][A-Za-z/]*)"
    r"[ \t]*[:*]*[ \t]*$"
)


def _id_red_de_encabezado(linea: str) -> str | None:
    """Si `linea` es un encabezado de plataforma reconocible, devuelve su id canonico.

    Tolera `#`/`##`/.../`**`/`:` alrededor de la etiqueta ("## X", "**Twitter:**",
    "Instagram:", "IG"). Devuelve None si la linea no es uno de esos encabezados.
    """
    m = _RE_ENCABEZADO_RED.match(linea)
    if m is None:
        return None
    return _ALIAS_RED.get(m.group(1).strip().lower())


def _repartir_por_encabezados(texto: str, redes_ids: list[str]) -> dict[str, str]:
    """Parte `texto` por encabezados de plataforma y asigna el cuerpo a cada red.

    Recorre las lineas: cada encabezado reconocible abre una seccion; el texto hasta
    el siguiente encabezado (o el fin) es el copy de esa red. Acota a `redes_ids`
    (ignora redes fuera de las pedidas) y deja la primera ocurrencia ante duplicados.
    Devuelve `{red_id: copy}` (vacio si no hay encabezados reconocibles).
    """
    permitidas = set(redes_ids)
    por_red: dict[str, list[str]] = {}
    actual: str | None = None
    for linea in texto.splitlines():
        red = _id_red_de_encabezado(linea)
        if red is not None:
            # Solo abrimos seccion para redes pedidas y no vistas antes.
            actual = red if (red in permitidas and red not in por_red) else None
            if actual is not None:
                por_red[actual] = []
            continue
        if actual is not None:
            por_red[actual].append(linea)
    return {red: "\n".join(cuerpo).strip() for red, cuerpo in por_red.items()}


def _piezas_desde_por_red(
    por_red: dict[str, str],
    redes_ids: list[str],
    copy_in_por_red: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    """Construye las piezas en el ORDEN FIJO de las redes pedidas.

    El `contenido` se emite TAL CUAL (la politica de emojis vive en el prompt + la
    editorial de la marca, no en una limpieza posterior: Claro Sports los lleva y
    UnoTV no) y `caracteres = len(contenido)`. Solo incluye redes en `por_red`.

    `copy_in_por_red` (opcional) aporta el TEXTO EN IMAGEN (copy-in) por red; se limpia
    con `quitar_emojis` (el contrato del prompt: la placa va SIEMPRE sin emojis), `""`
    si la red no lo trae. `caracteres` sigue midiendo SOLO el `contenido`.
    """
    copy_in_por_red = copy_in_por_red or {}
    piezas: list[dict[str, object]] = []
    for r in redes_ids:
        if r not in por_red:
            continue
        contenido = por_red[r].strip()
        piezas.append({
            "red": r,
            "contenido": contenido,
            "caracteres": len(contenido),
            "copy_in": quitar_emojis(copy_in_por_red.get(r, "")),
        })
    return piezas


def parsear_salida(salida: str, redes_ids: list[str]) -> dict[str, object]:
    """Parte la salida cruda en `resultado` limpio + `piezas`.

    - Localiza el ULTIMO bloque ```json cercado y lo `json.loads`; mapea su clave
      `piezas` a `[{red, contenido, caracteres}]` (solo redes en `redes_ids`, en
      orden fijo; `caracteres` = len(contenido)).
    - QUITA ese bloque json del texto para que `resultado` quede limpio.
    - FALLBACK: si no hay bloque JSON valido (o no trae `piezas` utilizables), intenta
      repartir el texto por ENCABEZADOS de plataforma. Si tampoco hay encabezados
      reconocibles, `piezas=[]` (comportamiento previo).
    - `resultado` y el `contenido` de cada pieza conservan los emojis que el modelo
      escribio (la politica de emojis vive en el prompt + editorial de marca); solo el
      `copy_in` (texto de placa) se limpia con `quitar_emojis`.

    Devuelve `{"resultado": str, "piezas": [...]}`.
    """
    salida = salida or ""

    coincidencias = list(_RE_BLOQUE_JSON.finditer(salida))
    datos = None
    limpio = salida.strip()
    if coincidencias:
        ultima = coincidencias[-1]
        try:
            datos = json.loads(ultima.group(1))
        except (json.JSONDecodeError, ValueError):
            # JSON malformado: dejamos el texto tal cual (incluido el bloque), sin piezas via JSON.
            datos = None
        else:
            # Texto LIMPIO: quitamos solo el ultimo bloque json (el de las piezas).
            limpio = (salida[: ultima.start()] + salida[ultima.end():]).strip()

    por_red: dict[str, str] = {}
    # Texto EN IMAGEN (copy-in) por red, en paralelo a `por_red`. Solo lo aporta la via JSON
    # (cada pieza puede traer `copy_in`); el fallback por encabezados no lo conoce.
    copy_in_por_red: dict[str, str] = {}
    permitidas = set(redes_ids)
    crudas = datos.get("piezas") if isinstance(datos, dict) else None
    if isinstance(crudas, list):
        for cruda in crudas:
            if not isinstance(cruda, dict):
                continue
            red = cruda.get("red")
            texto = cruda.get("texto")
            if not isinstance(red, str) or red not in permitidas:
                continue  # ignora redes desconocidas o fuera de las pedidas
            if not isinstance(texto, str):
                continue
            if red in por_red:
                continue  # primera gana ante duplicados (contenido + copy_in juntos)
            por_red[red] = texto
            copy_in = cruda.get("copy_in")
            copy_in_por_red[red] = copy_in if isinstance(copy_in, str) else ""

    # FALLBACK: sin piezas via JSON, intenta repartir por encabezados de plataforma.
    if not por_red:
        por_red = _repartir_por_encabezados(limpio, redes_ids)

    piezas = _piezas_desde_por_red(por_red, redes_ids, copy_in_por_red)
    return {"resultado": limpio, "piezas": piezas}


def parsear_salida_unificada(salida: str, redes_ids: list[str]) -> dict[str, object]:
    """Variante de `parsear_salida` para copy UNIFICADO: UN copy + UN copy_in para TODAS las redes.

    A diferencia de `parsear_salida` (una pieza por red, vía el array `piezas`), aquí el bloque
    ```json final trae un OBJETO PLANO `{"texto", "copy_in"}` (+ opcional `texto_corto`); ese copy
    + copy_in se EMITE para CADA red de `redes_ids`. Así X nunca queda sin `copy_in`.

    `texto_corto` (opcional): versión condensada para las redes ESTRECHAS. Cada red usa
    `texto_corto` SOLO si su límite técnico es menor que la longitud de `texto` (p. ej. Instagram
    =2200 frente a un copy más largo); las más anchas (X=25000, Facebook sin tope…) usan `texto`
    completo. Sin `texto_corto`, todas heredan `texto`: un copy demasiado largo para una red lo
    descartará luego la validación de longitud, no este parser.

    `tipo` (opcional, DOS tipos de output del pipeline): cuando la historia trae varias fotos
    de fuente, el prompt deja al modelo DECIDIR entre `"post"` (una imagen, lo de siempre) y
    `"carrusel"` EDITORIAL (portada paraguas + un slide con titular por SUB-HISTORIA). Se
    valida contra ese par cerrado; ausente, otro valor o sin JSON -> `"post"` (degradación
    honesta: nunca se arma un carrusel por accidente).

    `slides` (solo con `tipo=carrusel`): `[{titular, foto}, …]` depurados — `titular` no vacío
    SIN emojis (es texto de placa, misma política que `copy_in`) y `foto` el número del
    catálogo del prompt (int >= 0; 0 = sin foto, valores raros caen a 0). Tope
    `_MAX_SLIDES`. Con `tipo=post` (o slides ilegibles), lista vacía.

    Resiliente: si el modelo emite el array `piezas` (forma vieja), toma la PRIMERA pieza con
    `texto`. Si no hay JSON utilizable, el copy es el texto limpio entero (fallback). `resultado`
    y el `contenido` conservan los emojis que el modelo escribió (la política de emojis vive en
    el prompt + editorial de marca); el `copy_in` (placa) se limpia SIEMPRE con `quitar_emojis`.
    Devuelve `{"resultado": str, "piezas": [...], "tipo": str, "slides": [...]}`
    (misma forma que `parsear_salida` + el `tipo` elegido y sus `slides`).
    """
    salida = salida or ""

    coincidencias = list(_RE_BLOQUE_JSON.finditer(salida))
    datos = None
    limpio = salida.strip()
    if coincidencias:
        ultima = coincidencias[-1]
        bloque = ultima.group(1)
        try:
            datos = json.loads(bloque)
        except (json.JSONDecodeError, ValueError):
            # El error típico del modelo es dejar comillas SIN ESCAPAR dentro de un valor (una
            # cita: «..."x"...»), que invalida el JSON. Como el objeto del copy es PLANO y de claves
            # conocidas, lo recuperamos de forma tolerante anclando cada valor en la siguiente clave
            # o el `}`.
            datos = _objeto_copy_tolerante(bloque)
        if datos is not None:
            limpio = (salida[: ultima.start()] + salida[ultima.end():]).strip()

    texto_base: str | None = None
    texto_corto = ""
    copy_in_base = ""
    tipo = "post"
    slides: list[dict[str, object]] = []
    if isinstance(datos, dict):
        # Tipo de output (post|carrusel): par CERRADO; cualquier otra cosa cae a "post".
        if datos.get("tipo") == "carrusel":
            tipo = "carrusel"
            slides = _slides_de(datos.get("slides"))
        if isinstance(datos.get("texto"), str):
            texto_base = datos["texto"]
            tc = datos.get("texto_corto")
            texto_corto = tc if isinstance(tc, str) else ""
            ci = datos.get("copy_in")
            copy_in_base = ci if isinstance(ci, str) else ""
        else:
            # Resiliencia: el modelo emitió el array `piezas`; usamos la PRIMERA con `texto`.
            crudas = datos.get("piezas")
            if isinstance(crudas, list):
                for cruda in crudas:
                    if isinstance(cruda, dict) and isinstance(cruda.get("texto"), str):
                        texto_base = cruda["texto"]
                        ci = cruda.get("copy_in")
                        copy_in_base = ci if isinstance(ci, str) else ""
                        break

    # FALLBACK: sin JSON utilizable, el copy es el texto limpio entero.
    if texto_base is None:
        texto_base = limpio

    contenido_largo = texto_base.strip()
    contenido_corto = texto_corto.strip()
    copy_in_base = quitar_emojis(copy_in_base)
    piezas: list[dict[str, object]] = []
    for r in redes_ids:
        # Una red usa el copy CORTO solo si su límite técnico no admite el largo (p. ej. Instagram
        # =2200 vs un copy más largo). Sin `texto_corto`, todas usan el largo.
        limite = limites_plataforma.limite_de(r)
        usar_corto = bool(contenido_corto) and limite is not None and len(contenido_largo) > limite
        contenido = contenido_corto if usar_corto else contenido_largo
        piezas.append(
            {"red": r, "contenido": contenido, "caracteres": len(contenido), "copy_in": copy_in_base}
        )
    return {"resultado": limpio, "piezas": piezas, "tipo": tipo, "slides": slides}


# Claves del OBJETO PLANO del copy unificado. Las usa la reparación tolerante para anclar el FIN
# de cada valor (la `"` que precede a la siguiente clave o al cierre `}`), de modo que una comilla
# SIN ESCAPAR dentro de un valor (cita) no rompa la extracción como sí rompe a `json.loads`.
_CLAVES_COPY: tuple[str, ...] = ("texto", "texto_corto", "copy_in", "tipo", "slides")
_FRONTERA_VALOR = r'(?=\s*,\s*"(?:' + "|".join(_CLAVES_COPY) + r')"\s*:|\s*\})'


def _desescapar_json_str(s: str) -> str:
    """Deshace los escapes JSON comunes de un valor string extraído a mano (PURA).

    Solo los escapes que un modelo usa de verdad (`\\"`, `\\n`, `\\t`, `\\r`, `\\/`, `\\\\`). NO
    usa `unicode_escape` (rompería los acentos UTF-8). Las comillas internas que el modelo dejó
    SIN escapar ya están bien tal cual; esto solo normaliza las que sí escapó."""
    return re.sub(
        r'\\(["ntr/\\])',
        lambda m: {'"': '"', "n": "\n", "t": "\t", "r": "\r", "/": "/", "\\": "\\"}[m.group(1)],
        s,
    )


def _objeto_copy_tolerante(bloque: str) -> dict[str, str] | None:
    """Recupera `{texto, texto_corto, copy_in, tipo}` de un bloque JSON que `json.loads` rechazó.

    El fallo habitual del modelo es una comilla SIN ESCAPAR dentro de un valor (una cita textual),
    que invalida el JSON entero. Como el objeto del copy unificado es PLANO y de claves CONOCIDAS,
    extraemos cada valor string anclando su cierre en la `"` que precede a la siguiente clave
    conocida o al `}` final (`_FRONTERA_VALOR`): así las comillas internas (que NO van seguidas de
    `, "clave":`) no cortan el valor. Devuelve None si ni siquiera encuentra `texto` (entonces el
    caller cae al fallback de texto plano de siempre). NO recupera `slides` (si el JSON se rompió,
    el carrusel se degrada a post: nunca se arma uno por accidente con datos a medias)."""
    obj: dict[str, str] = {}
    for clave in ("texto", "texto_corto", "copy_in", "tipo"):
        m = re.search(
            r'"' + clave + r'"\s*:\s*"(.*?)"' + _FRONTERA_VALOR, bloque, re.DOTALL
        )
        if m is not None:
            obj[clave] = _desescapar_json_str(m.group(1))
    return obj if obj.get("texto") else None


# Tope de SLIDES de un carrusel editorial (10 nativas de IG/FB - 1 de portada). Espejo de
# `generar.MAX_SLIDES_CARRUSEL` (no se importa: `stream` es parseo puro, sin ese acople).
_MAX_SLIDES = 9


def _slides_de(crudo: object) -> list[dict[str, object]]:
    """Repara el array `slides` del json del copy a `[{titular, foto}, …]` (PURA).

    `titular` se limpia con `quitar_emojis` (es texto DE PLACA, como `copy_in`); slides sin
    titular útil se omiten. `foto` es el NÚMERO del catálogo numerado que vio el modelo
    (1-based; 0 = sin foto); un valor no entero o negativo cae a 0. Tope `_MAX_SLIDES`.
    """
    if not isinstance(crudo, list):
        return []
    slides: list[dict[str, object]] = []
    for s in crudo:
        if not isinstance(s, dict):
            continue
        titular = quitar_emojis(s.get("titular") if isinstance(s.get("titular"), str) else "")
        if not titular.strip():
            continue
        foto = s.get("foto")
        # bool es subclase de int: un `true` accidental no debe contar como foto 1.
        n_foto = foto if isinstance(foto, int) and not isinstance(foto, bool) and foto > 0 else 0
        slides.append({"titular": titular.strip(), "foto": n_foto})
        if len(slides) >= _MAX_SLIDES:
            break
    return slides
