"""Carrusel desde un post (acción MANUAL del feed): convierte un post YA redactado en un carrusel.

Cuando el equipo pulsa «Carrusel» en un post que aún no tiene slides, el feed ENCOLA un `claude -p`
READ-ONLY que parte la SUSTANCIA del copy en titulares de tarjetas (una idea por slide), sin tocar
el copy ni inventar nada. El post-procesado (en el worker) HORNEA cada titular como placa de la
marca (la misma plantilla efectiva de la portada) y escribe el MISMO `carrusel` JSON en todas las
piezas gemelas del contenido (formato carrusel -> IG/X/FB). La PORTADA se conserva: estos son los
slides que van DESPUÉS de ella.

Mismo patrón que `sugerir_hashtags`: el copy viaja DENTRO del prompt (autocontenido), así que el
spec del post-procesado solo lleva el `publicacion_id`; el carrusel es GEMELO entre redes, así que
se calcula UNA vez y se escribe idéntico en cada pieza. A diferencia del carrusel del pipeline
(panel multi-historia con foto por sub-historia), aquí no hay fotos por slide: cada tarjeta sale
como placa de SOLO TEXTO con la plantilla de la marca (igual que la portada de la captura).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from .. import marcas, redes, repos
from . import copy as dom_copy
from . import generar, jobspec

_log = logging.getLogger("keni_consola.carrusel")

PROMPT_CARRUSEL = "prompt/carrusel-desde-post"

# Tope ABSOLUTO de slides (el mismo del pipeline: 10 nativas de IG/FB - 1 de portada).
MAX_SLIDES = generar.MAX_SLIDES_CARRUSEL

# Longitud del carrusel que elige el equipo: rango (min, max) de slides que se pide al modelo.
# El `max` además ACOTA el parseo (un carrusel corto nunca se pasa de 5). "largo" es el defecto.
LONGITUDES: dict[str, tuple[int, int]] = {
    "corto": (4, 5),
    "largo": (8, 9),
}
LONGITUD_DEFECTO = "largo"


def _rango_longitud(longitud: str) -> tuple[int, int]:
    """(min, max) de slides para la longitud elegida; cae al defecto si no es válida."""
    return LONGITUDES.get(longitud) or LONGITUDES[LONGITUD_DEFECTO]

# Estados de pieza donde `aplicar_carrusel` ESCRIBE. La acción nace de un post recién flip-eado a
# carrusel (vuelve a `borrador`); se incluye `en_revision` por si la pieza avanzó mientras el job
# esperaba en la cola. `programado`/`publicado` quedan FUERA: lo que ya salió no se reescribe.
ESTADOS_EDITABLES = ("borrador", "en_revision")

# Herramientas VETADAS: la etapa solo razona sobre el copy y propone titulares; no escribe, no
# navega, no toca el tablero. Mismo criterio READ-ONLY que sugerir-hashtags / la crítica IA.
_TOOLS_VETADAS: tuple[str, ...] = (
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Bash",
    "WebFetch",
    "WebSearch",
    "mcp__keni-social__keni_crear_publicacion",
    "mcp__keni-social__keni_actualizar_publicacion",
    "mcp__keni-social__keni_enviar_a_revision",
    "mcp__keni-social__keni_aprobar",
    "mcp__keni-social__keni_rechazar",
)


class CarruselError(Exception):
    """El lanzamiento no aplica (pieza inexistente, sin copy del que partir un carrusel)."""


def _endurecer() -> dict[str, Any]:
    """Run READ-ONLY y barato: veta escritura/red, acota turnos y coste (solo elige titulares)."""
    return {
        "disallowed_tools": list(_TOOLS_VETADAS),
        "max_turns": 8,
        "max_budget_usd": 2.0,
    }


def _contexto_editorial(marca: str) -> str:
    """Voz/normas de la marca como contexto (best-effort, "" si no hay). Reusa `adjuntos_copy`."""
    try:
        docs = generar.adjuntos_copy(marca)
    except Exception:  # noqa: BLE001 -- el contexto editorial es opcional; nunca rompe el lanzamiento
        return ""
    cuerpos = [d.cuerpo.strip() for d in docs if getattr(d, "cuerpo", "").strip()]
    if not cuerpos:
        return ""
    return "\n\n## Contexto editorial de la marca\n\n" + "\n\n---\n\n".join(cuerpos)


def _componer_prompt(
    *, copy: str, copy_in: str, marca: str, min_slides: int, max_slides: int
) -> str:
    """Renderiza `prompt/carrusel-desde-post` con el copy, la portada, la voz y el rango de slides."""
    from .. import libprompts

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_CARRUSEL) or libprompts.cuerpo_inicial(PROMPT_CARRUSEL)
    sust = {
        "{{MARCA}}": marcas.etiqueta_de(marca) or marca or "la marca",
        "{{COPY}}": str(copy or "").strip() or "(sin copy)",
        "{{COPY_IN}}": str(copy_in or "").strip() or "(sin titular de portada)",
        "{{MIN_SLIDES}}": str(min_slides),
        "{{MAX_SLIDES}}": str(max_slides),
    }
    for marcador, valor in sust.items():
        cuerpo = cuerpo.replace(marcador, valor)
    # Inyecta el rango por CÓDIGO (no solo por placeholder del cuerpo): un equipo ya DESPLEGADO
    # tiene la versión del prompt en su store, donde el mínimo viajaba fijo, así que sustituir
    # {{MIN_SLIDES}} no le llegaría. Esta línea final MANDA y garantiza el rango de la longitud
    # elegida (corto 4-5 / largo 8-9) en cualquier versión del prompt (semilla o store).
    directiva = (
        f"\n\nLONGITUD: genera entre {min_slides} y {max_slides} tarjetas (slides), sin contar la "
        "portada. Es un requisito de formato; ajústate EXACTAMENTE a ese rango."
    )
    return cuerpo + directiva + _contexto_editorial(marca)


def lanzar_para_pieza(
    pieza_id: str, longitud: str = LONGITUD_DEFECTO, *, como_variante: bool = False
) -> dict[str, Any]:
    """ENCOLA la generación del carrusel a partir del copy de una pieza. Devuelve el registro.

    Lee el copy + el titular de portada de la pieza, compone el prompt (autocontenido) y lanza un
    `claude -p` READ-ONLY. `longitud` ∈ {corto (4-5 slides), largo (8-9)}; cae al defecto si no es
    válida. Lanza `CarruselError` si la pieza no existe o no hay copy del que partir.

    `como_variante` False (legado): el post-procesado hornea los slides y los ESCRIBE en las piezas
    existentes (sobrescribe); idempotente por `carrusel:{publicacion_id}:{longitud}`. True
    (conversión NO destructiva): crea piezas `variante='carrusel'` HERMANAS junto a las foto;
    idempotente por `carrusel:variante:{publicacion_id}:{longitud}` (run distinto del legado).
    """
    pieza = repos.obtener_pieza(pieza_id)
    if pieza is None:
        raise CarruselError("Esa publicación ya no existe.")
    copy = str(pieza.get("contenido") or "").strip()
    if not copy:
        raise CarruselError("El post no tiene copy del que generar un carrusel.")
    publicacion_id = str(pieza.get("publicacion_id") or "")
    if not publicacion_id:
        raise CarruselError("La pieza no está asociada a un contenido.")
    marca = str(pieza.get("marca") or "")
    copy_in = str(pieza.get("copy_in") or "")
    longitud = longitud if longitud in LONGITUDES else LONGITUD_DEFECTO
    min_slides, max_slides = _rango_longitud(longitud)

    procesar_spec = jobspec.construir_carrusel(
        publicacion_id=publicacion_id, max_slides=max_slides, como_variante=como_variante,
    )
    procesar = jobspec.reconstruir_procesar({"procesar": procesar_spec})
    prompt = _componer_prompt(
        copy=copy, copy_in=copy_in, marca=marca, min_slides=min_slides, max_slides=max_slides,
    )
    prefijo = "Variante carrusel" if como_variante else "Carrusel"
    clave = f"carrusel:variante:{publicacion_id}:{longitud}" if como_variante else f"carrusel:{publicacion_id}:{longitud}"
    return generar.lanzar(
        tipo="carrusel",
        titulo=f"{prefijo} {longitud} · {pieza.get('titulo', '') or 'post'}",
        marca=marca,
        prompt=prompt,
        procesar=procesar,
        procesar_spec=procesar_spec,
        endurecer=_endurecer(),
        clave_idem=clave,
        publicacion_id=publicacion_id,
    )


# --------------------------------------------------------------------------- #
# Post-procesado (corre en el WORKER al terminar el job)                        #
# --------------------------------------------------------------------------- #


def _parsear_slides(salida: str, max_slides: int = MAX_SLIDES) -> list[str]:
    """Extrae los `titular` de `{"slides": [{"titular": ...}]}` del JSON de la salida. [] si ilegible.

    El JSON del carrusel ANIDA (slides = lista de objetos), así que la extracción tolera llaves
    internas: prueba el bloque con vallas (captura GREEDY, hasta la última llave) y, si no cuela,
    el tramo de la primera `{` a la última `}` del texto. Acota a `max_slides` (el tope de la
    longitud elegida: un carrusel corto nunca se pasa de 5 aunque el modelo proponga más).
    """
    if not salida:
        return []
    texto = salida.strip()
    candidatos: list[str] = []
    valla = re.search(r"```(?:json)?\s*(\{.*\})\s*```", texto, re.DOTALL)
    if valla:
        candidatos.append(valla.group(1))
    ini, fin = texto.find("{"), texto.rfind("}")
    if ini != -1 and fin > ini:
        candidatos.append(texto[ini : fin + 1])
    for crudo in candidatos:
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            continue
        lista = datos.get("slides") if isinstance(datos, dict) else None
        if not isinstance(lista, list):
            continue
        titulares: list[str] = []
        for s in lista[:max_slides]:
            titular = str((s.get("titular") if isinstance(s, dict) else s) or "").strip()
            if titular:
                titulares.append(titular)
        return titulares
    return []


def hornear_slides(marca: str, titulares: list[str]) -> list[dict[str, str]]:
    """Hornea cada titular como placa de SOLO TEXTO de la marca. Devuelve los slides componibles.

    Reusa el MISMO renderer que el carrusel del pipeline (`dominio.copy._COMPONER_SLIDE`): plantilla
    efectiva de la marca + el titular como texto-en-imagen, sin foto. Un slide que no compone (marca
    sin plantilla, fallo del renderer) se OMITE. Cada slide guarda su `titular` como procedencia para
    poder re-editarlo como placa en el editor.
    """
    slides: list[dict[str, str]] = []
    for titular in titulares:
        res = dom_copy._COMPONER_SLIDE(marca, titular, "")
        objeto = res.get("objeto", "") if isinstance(res, dict) else (res or "")
        if not objeto:
            continue
        slides.append({"tipo": "imagen", "objeto": objeto, "titular": titular})
    return slides


def aplicar_carrusel(publicacion_id: str, titulares: list[str]) -> list[dict[str, str]]:
    """Hornea los slides y escribe el MISMO `carrusel` JSON en cada pieza EDITABLE del contenido.

    El carrusel es gemelo entre las redes del contenido: se hornea una vez y se persiste idéntico en
    cada pieza en `ESTADOS_EDITABLES`. Devuelve los slides escritos ([] si no hay piezas editables o
    ningún slide compuso — en ese caso el formato carrusel queda como sugerencia, igual que el
    pipeline). NO toca el formato: el flip a carrusel lo hace el feed antes de lanzar.
    """
    filas = repos.listar_piezas_fila(publicacion_id=publicacion_id) or []
    elegibles = [f for f in filas if str(f.get("estado") or "") in ESTADOS_EDITABLES]
    if not elegibles:
        return []
    marca = str(elegibles[0].get("marca") or "")
    slides = hornear_slides(marca, titulares)
    if not slides:
        _log.warning(
            "carrusel: sin slides componibles para el contenido %s; queda como sugerencia de formato",
            publicacion_id,
        )
        return []
    payload = json.dumps(slides, ensure_ascii=False)
    for f in elegibles:
        repos.actualizar_pieza(str(f.get("id") or ""), {"carrusel": payload})
    return slides


def crear_variante_carrusel(publicacion_id: str, titulares: list[str]) -> list[dict[str, str]]:
    """Conversión NO DESTRUCTIVA: crea piezas `variante='carrusel'` HERMANAS de las foto.

    Hornea los slides una vez y, por cada red de formato carrusel (IG/FB) que tenga pieza FOTO,
    crea una pieza nueva `variante='carrusel'` en borrador copiando el copy/copy_in/foto de la foto
    y con los slides horneados — SIN tocar la pieza foto (sigue viva; el feed muestra ambas como
    tarjetas hermanas). Idempotente: si ya existe la variante carrusel de una red, RE-HORNEA sus
    slides en vez de duplicarla. Devuelve los slides ([] si no hay piezas foto editables o ninguno
    compuso).
    """
    filas = repos.listar_piezas_fila(publicacion_id=publicacion_id) or []
    foto = [
        f for f in filas
        if (str(f.get("variante") or "foto")) == "foto"
        and str(f.get("estado") or "") in ESTADOS_EDITABLES
    ]
    if not foto:
        return []
    marca = str(foto[0].get("marca") or "")
    slides = hornear_slides(marca, titulares)
    if not slides:
        _log.warning(
            "carrusel: sin slides componibles para el contenido %s; no se crea variante", publicacion_id
        )
        return []
    payload = json.dumps(slides, ensure_ascii=False)
    redes_carrusel = set(redes.redes_de_formato(redes.FORMATO_CARRUSEL))
    existentes = {
        str(f.get("red") or ""): f
        for f in filas
        if (str(f.get("variante") or "foto")) == "carrusel"
    }
    for f in foto:
        red = str(f.get("red") or "")
        if red not in redes_carrusel:
            continue  # la variante carrusel solo va a las redes de su formato (IG/FB)
        ya = existentes.get(red)
        if ya is not None:
            # Idempotente: re-hornea la variante existente de esa red. Pero lo que ya salió no se
            # reescribe: una variante `programado`/`publicado` queda intacta (`carrusel` es campo
            # congelado de una pieza publicada), igual que el filtro de `aplicar_carrusel`.
            if str(ya.get("estado") or "") in ESTADOS_EDITABLES:
                repos.actualizar_pieza(str(ya.get("id") or ""), {"carrusel": payload})
            continue
        repos.crear_pieza_fila(
            publicacion_id=publicacion_id,
            red=red,
            marca=marca,
            estado="borrador",
            copy=str(f.get("copy") or ""),
            copy_in=str(f.get("copy_in") or ""),
            # Receta COMPLETA de la PORTADA de la foto: foto cruda, collage (hueco 0 con su
            # encuadre), reencuadre legado y plantilla. Sin esto la variante nacía sin portada
            # usable y, al editarla, divergía de la foto (la foto acababa en «Falta imagen»).
            foto=str(f.get("foto") or ""),
            fotos=str(f.get("fotos") or ""),
            foto_encuadre=str(f.get("foto_encuadre") or ""),
            plantilla_diseno_id=str(f.get("plantilla_diseno_id") or ""),
            imagen=str(f.get("imagen") or ""),
            imagen_fuente=str(f.get("imagen_fuente") or ""),
            carrusel=payload,
            variante="carrusel",
        )
    return slides


def construir_procesar_carrusel(
    *, publicacion_id: str, max_slides: int = MAX_SLIDES, como_variante: bool = False
):  # noqa: ANN201
    """Devuelve el callback `procesar(salida, metricas) -> dict` del job (corre en el worker).

    `max_slides` acota cuántos titulares se aceptan (el tope de la longitud elegida). `como_variante`
    True crea piezas carrusel hermanas (no destructivo); False (legado) sobrescribe las existentes.
    """

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        titulares = _parsear_slides(salida, max_slides)
        if como_variante:
            slides = crear_variante_carrusel(publicacion_id, titulares)
        else:
            slides = aplicar_carrusel(publicacion_id, titulares)
        return {"carrusel": {"slides": slides}}

    return procesar
