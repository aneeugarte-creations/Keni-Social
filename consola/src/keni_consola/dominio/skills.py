"""Dominio SKILLS: construccion de prompts, cosecha de imagenes y post-procesado de copy.

Logica de negocio PURA (sin HTTP) extraida de `api/skills.py` (hallazgo H6): el handler
HTTP se queda solo orquestando peticiones; aqui vive lo que NO depende del transporte:

  - Construccion del prompt de invocacion de una skill (`construir_prompt*`), incluida la
    instruccion aditiva de "sin emojis".
  - Cosecha de las imagenes que una skill de imagen menciona por ruta en su salida, para
    previsualizarlas en la consola (`cosechar_imagenes`).
  - Creacion de las publicaciones (borrador) por pieza generada
    (`crear_publicaciones_desde_piezas`).
  - Los callbacks de post-procesado (`construir_procesar_copy` / `_documento`) que corren
    al COMPLETARSE una generacion: parsean la salida, registran el historial y crean los
    artefactos. Son fabricas de callbacks puras (no tocan HTTP).

Depende del DOMINIO (`stream`, `publicaciones`) y de los modulos hoja de la consola
(`redes`, `repos`, `skills_catalogo`, `media`): NO importa de `api/`. `generaciones` solo
importa `dominio.stream`, asi que `dominio.skills -> generaciones` no crea ciclo.
"""

from __future__ import annotations

import re

from .. import generaciones, redes, repos, skills_catalogo
from . import stream
from .publicaciones import publicacion_a_dict

# Instruccion ADITIVA de estilo que se anade a TODO prompt de generacion: el copy
# no debe llevar emojis. Es defensa en profundidad; ademas `quitar_emojis` los borra
# de forma determinista por si el modelo igual mete alguno.
_INSTRUCCION_SIN_EMOJIS = "No uses emojis en el copy."


# --------------------------------------------------------------------------- #
# Construccion del prompt de invocacion de una skill                           #
# --------------------------------------------------------------------------- #


def _instruccion_redes(redes_ids: list[str]) -> str:
    """Instruccion ADITIVA: limita las redes y pide un bloque json con las piezas.

    No cambia el copy ni la auto-verificacion de la skill; solo (a) acota a las
    redes pedidas y (b) anade, AL FINAL, un bloque ```json con `piezas` para esas
    redes, que la consola parsea luego. `redes_ids` ya viene validado contra las
    redes canonicas (en orden fijo).
    """
    etiquetas = ", ".join(redes.nombre_por_id(r) for r in redes_ids)
    ids_json = ", ".join(f'"{r}"' for r in redes_ids)
    return (
        f"Genera el copy SOLO para estas redes: {etiquetas}. "
        "Mantén tu formato y tu auto-verificación habituales. "
        "Además, al FINAL de toda tu respuesta, añade un único bloque de código "
        'cercado ```json con esta forma exacta: {"piezas": [{"red": "<id>", '
        '"texto": "<copy de esa red>"}, ...]}, usando como <id> únicamente estos '
        f"valores: {ids_json}. Incluye una pieza por cada red pedida."
    )


def _prompt_generico(verbo: str, skill: str, marca: str, contenido: str, redes_ids: list[str] | None) -> str:
    """Construye un prompt cuando la skill NO esta en el catalogo (back-compat puro)."""
    base = f"usa {skill} con {verbo}, marca {marca}:\n\n{contenido}"
    base = f"{base}\n\n{_INSTRUCCION_SIN_EMOJIS}"
    if redes_ids:
        return f"{base}\n\n{_instruccion_redes(redes_ids)}"
    return base


def construir_prompt(skill: str, marca: str, texto: str, redes_ids: list[str] | None = None) -> str:
    """Construye el prompt de invocacion headless para una skill+marca+texto (BACK-COMPAT).

    Mapea `texto` al PRIMER campo de texto de la skill y delega en
    `skills_catalogo.render_invocacion` (la via dinamica de archivos). Si la skill no
    esta en el catalogo (caso raro / legado), cae a un prompt generico equivalente al
    de antes. Lo usa `api.rss.generar` sin cambios. El texto viaja como argumento de
    subprocess (no por shell): sin inyeccion. La instruccion ADITIVA de redes solo se
    anade si la skill `aplica_redes`.
    """
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return _prompt_generico("la siguiente nota", skill, marca, texto, redes_ids)
    campo = skilldef.primer_campo_texto()
    valores = {campo.id: texto} if campo is not None else {}
    return skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)


def construir_prompt_ruta(
    skill: str, marca: str, ruta: str, redes_ids: list[str] | None = None
) -> str:
    """Construye el prompt para una skill de MEDIA que parte de una RUTA de archivo.

    Mapea `ruta` al campo de tipo archivo de la skill (o, si no hay, al primer campo) y
    delega en `render_invocacion`. Cae a un prompt generico si la skill no esta en el
    catalogo (back-compat).
    """
    skilldef = skills_catalogo.obtener(skill)
    if skilldef is None:
        return _prompt_generico("el archivo en esta ruta", skill, marca, ruta, redes_ids)
    campo = skilldef.campo_archivo() or skilldef.primer_campo_texto()
    valores = {campo.id: ruta} if campo is not None else {}
    return skills_catalogo.render_invocacion(skilldef, marca, valores, redes_ids)


# --------------------------------------------------------------------------- #
# Cosecha de IMAGENES de salida (skills de imagen: estudio-imagen)             #
# --------------------------------------------------------------------------- #
#
# Las skills de imagen (estudio-imagen) producen ARCHIVOS .png con las herramientas
# deterministas (editar.py/componer.py) o el adaptador generativo (generar.py). La
# salida de Claude es texto (el documento del revisor) que MENCIONA las rutas de esos
# archivos. Para PREVISUALIZARLOS en la Consola, tras completar la generacion
# localizamos esas rutas, las importamos al almacen de media (`/api/media/...`) y las
# devolvemos como `imagenes` en el `resultado`.

# Extensiones de imagen que reconocemos en la salida (las que producen las herramientas).
_EXT_IMAGEN = ("png", "jpg", "jpeg", "webp", "gif")

# Ruta a un archivo de imagen dentro del texto: una ruta absoluta (POSIX) o relativa con
# separadores, terminada en una extension de imagen. Tolera comillas/parentesis alrededor.
_RE_RUTA_IMAGEN = re.compile(
    r"(/?(?:[^\s\"'`<>|]+/)+[^\s\"'`<>|]+\.(?:" + "|".join(_EXT_IMAGEN) + r"))",
    re.IGNORECASE,
)

# Tope defensivo de imagenes que importamos de una sola salida (evita abusos).
_MAX_IMAGENES = 12


def _rutas_imagen_en_texto(salida: str) -> list[str]:
    """Extrae rutas de archivos de imagen mencionadas en la salida (orden, sin duplicar)."""
    if not salida:
        return []
    vistas: list[str] = []
    for m in _RE_RUTA_IMAGEN.finditer(salida):
        ruta = m.group(1)
        if ruta not in vistas:
            vistas.append(ruta)
    return vistas


def cosechar_imagenes(salida: str) -> list[dict[str, str]]:
    """Importa al almacen de media las imagenes que la salida menciona por ruta.

    Localiza rutas de archivos de imagen en `salida`, importa al media (copia) las que
    existan y sean imagenes validas, y devuelve `[{nombre, url}]` para previsualizarlas.
    Tolerante: una ruta que no exista o no se pueda importar simplemente se OMITE (la
    previsualizacion es un extra, nunca debe romper la generacion). Limita a
    `_MAX_IMAGENES` para no abusar del almacen.
    """
    from .. import media

    imagenes: list[dict[str, str]] = []
    for ruta in _rutas_imagen_en_texto(salida):
        if len(imagenes) >= _MAX_IMAGENES:
            break
        try:
            nombre = media.importar_imagen(ruta)
        except media.MediaError:
            continue  # ruta inexistente / no es imagen / demasiado grande: se omite
        except Exception:  # noqa: BLE001 -- la previsualizacion nunca rompe la generacion
            continue
        imagenes.append({"nombre": nombre, "url": f"/api/media/{nombre}"})
    return imagenes


# --------------------------------------------------------------------------- #
# Creacion de publicaciones (borrador) por pieza                              #
# --------------------------------------------------------------------------- #


def crear_publicaciones_desde_piezas(
    piezas: list[dict[str, object]],
    *,
    marca: str,
    titulo: str,
    verdicto: str,
    origen: str,
    redes_filtro: set[str] | None = None,
) -> list[dict[str, object]]:
    """Crea UNA publicacion (borrador) por pieza y devuelve sus dicts serializados.

    Cada pieza aporta `red` y `contenido`. Si `redes_filtro` no es None, solo se
    crean las piezas cuya red este en el filtro. `marca`/`titulo`/`verdicto`/`origen`
    son comunes a todas. El estado siempre nace como `borrador`.
    """
    creadas: list[dict[str, object]] = []
    for pieza in piezas:
        red = pieza.get("red")
        contenido = pieza.get("contenido")
        if not isinstance(red, str) or not redes.es_red(red):
            continue
        if redes_filtro is not None and red not in redes_filtro:
            continue
        if not isinstance(contenido, str):
            contenido = ""
        pub = repos.crear_publicacion(
            marca,
            red,
            titulo=titulo,
            contenido=contenido,
            estado="borrador",
            veredicto=verdicto,
            origen=origen,
        )
        creadas.append(publicacion_a_dict(pub))
    return creadas


# --------------------------------------------------------------------------- #
# Callbacks de post-procesado de una generacion (corren al completarse)        #
# --------------------------------------------------------------------------- #


def construir_procesar_copy(
    skill: str,
    marca: str,
    *,
    redes_ids: list[str],
    titulo_dado: str,
    texto_base: str,
    con_imagenes: bool = False,
) -> generaciones.Procesar:
    """Devuelve el callback de post-procesado de una generacion de copy/RSS.

    El callback `procesar(salida, metricas) -> dict` corre al COMPLETARSE el trabajo:
    parsea la salida cruda en piezas/verdicto, registra el historial (con sus metricas),
    AUTO-GUARDA una publicacion (borrador) por pieza y devuelve la MISMA forma que antes
    entregaba la generacion sincrona: `{resultado, historial_id, verdicto, piezas,
    publicaciones}`. Es lo que se guarda como `resultado` del registro de generacion.
    Si `con_imagenes` (skill de imagen), ademas importa las imagenes producidas al media
    y las anade como `imagenes` para previsualizarlas.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        parsed = stream.parsear_salida(salida, redes_ids)
        titulo = titulo_dado or stream.derivar_titulo(texto_base or str(parsed["resultado"]))
        historial_id = repos.registrar_historial_skill(
            skill, marca, parsed["resultado"], piezas=parsed["piezas"], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas),
        )
        publicaciones = crear_publicaciones_desde_piezas(
            parsed["piezas"], marca=marca, titulo=titulo,
            verdicto=parsed["verdicto"], origen=historial_id,
        )
        resultado: dict[str, object] = {
            "resultado": parsed["resultado"],
            "historial_id": historial_id,
            "verdicto": parsed["verdicto"],
            "piezas": parsed["piezas"],
            "publicaciones": publicaciones,
        }
        if con_imagenes:
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar


def construir_procesar_documento(
    skill: str,
    marca: str,
    *,
    titulo_base: str,
    titulo_dado: str = "",
    con_imagenes: bool = False,
) -> generaciones.Procesar:
    """Callback de post-procesado de una skill de salida `documento` (sin piezas).

    El callback `procesar(salida, metricas) -> dict` corre al COMPLETARSE el trabajo:
    limpia emojis del documento, deriva el verdicto de la primera linea ✅/⚠️/❌, deriva
    un titulo (del primer campo de texto o del documento), registra el historial SIN
    piezas y NO auto-crea publicaciones. Devuelve
    `{documento, verdicto, historial_id, piezas: [], publicaciones: []}`. Si
    `con_imagenes` (skill de imagen, p.ej. estudio-imagen), ademas importa las imagenes
    producidas al media y las anade como `imagenes` para previsualizarlas.
    """

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        doc = stream.quitar_emojis(salida)
        verdicto = stream.derivar_verdicto(salida)
        titulo = titulo_dado or stream.derivar_titulo(titulo_base or doc)
        historial_id = repos.registrar_historial_skill(
            skill, marca, doc, piezas=[], titulo=titulo, metricas=stream.metricas_a_dict(metricas),
        )
        resultado: dict[str, object] = {
            "documento": doc,
            "verdicto": verdicto,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }
        if con_imagenes:
            # La cosecha lee las RUTAS de la salida CRUDA (no del documento sin emojis).
            resultado["imagenes"] = cosechar_imagenes(salida)
        return resultado

    return procesar
