"""Generacion de ARTE (imagen) para temas con copy pero sin imagen — ETAPA del pipeline.

PROBLEMA QUE RESUELVE
=====================
La etapa de copy del pipeline deja BORRADORES de texto listos para revisar, pero el equipo
aun tiene que generar un arte a mano para cada uno. La ETAPA DE ARTE del pipeline (toggle
"Generar arte", `KENI_PIPELINE_ARTE`) corre TRAS la de copy y, para cada TEMA que YA tiene
copy/borrador en alguna plataforma pero le FALTA imagen, genera UN arte por IA (reutilizando
el MISMO proveedor que el boton `/api/media/generar`) y lo ADJUNTA a esa plataforma. La pieza
sigue su flujo normal de revision/aprobacion humana.

Antes existía un DAEMON suelto que barría el tablero; se RETIRÓ: la etapa vive ahora dentro
del barrido del pipeline (`pipeline_contenido.ejecutar_arte`), que reutiliza la SELECCIÓN
(`topics_sin_arte`) y el LANZAMIENTO (`lanzar_para_topic`) de este módulo.

SEGURO POR DISENO (CONSERVADOR)
===============================
  - GATEADO: la etapa solo ilustra con `KENI_PIPELINE_ARTE=1` (def OFF) + `KENI_MAQUINA=1`.
  - SOLO TEMAS CON COPY Y SIN IMAGEN: solo procesa contenido 'contenido' no cerrado que
    tenga alguna `contenido_plataforma` con copy pero sin imagen. No inventa piezas.
  - SIN CREDENCIALES, NO HACE NADA: si no hay proveedor de imagen configurado, no ilustra.
  - CAP por barrido (`KENI_AUTOGEN_ARTE_MAX`, def 3): cada item llama al proveedor de
    imagen (coste); el cap evita avalanchas.
  - DEDUP: tras procesar, el tema se ETIQUETA `autogen-arte` para no re-generarlo. La
    seleccion lee esa etiqueta para saltarse lo ya hecho.
  - NO PUBLICA: solo adjunta el arte al borrador; la revision/aprobacion humana y la
    publicacion real (`KENI_PUBLICAR_REAL`) siguen gated, igual que siempre.

La SELECCION (`topics_sin_arte`) es PURA y testeable: recibe las plataformas por item como
un dict, asi no toca la DB. El LANZAMIENTO reutiliza `media.generar_imagen` (proveedor
inyectable/mockeable) sin reinventar la generacion de imagen: bajo riesgo.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from . import config, generaciones, marcas, media, priorizacion, repos
from .estados import CLASE_CONTENIDO

_log = logging.getLogger("keni_consola.autogen_arte")

# Etiqueta-marca de dedup: un tema ya procesado para auto-arte la lleva (reservada).
ETIQUETA_AUTOGEN_ARTE = "autogen-arte"

# Estado terminal del contenido padre: ya no tiene sentido generarle arte.
_ESTADO_CERRADO = "hecha"


def _normaliza(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _id_etiqueta_autogen_arte(*, crear: bool = True) -> str:
    """Id de la etiqueta `autogen-arte` (la crea si no existe y `crear`). "" si no se puede."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == ETIQUETA_AUTOGEN_ARTE:
            return et.get("id", "")
    if not crear:
        return ""
    return repos.crear_etiqueta(nombre=ETIQUETA_AUTOGEN_ARTE).get("id", "")


def ids_ya_procesados() -> set[str]:
    """Ids de contenido ya procesados para auto-arte (etiqueta `autogen-arte`).

    Best-effort: si la lectura falla, devuelve set vacio (peor caso: un re-procesado, que
    el cap/historial acotan, nunca una excepcion que rompa el barrido).
    """
    try:
        et_id = _id_etiqueta_autogen_arte(crear=False)
        if not et_id:
            return set()
        return repos.ids_contenido_con_etiqueta(et_id)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar el barrido
        return set()


def _tiene_copy(plataforma: dict[str, Any]) -> bool:
    """True si la plataforma tiene copy redactado (texto no vacio)."""
    return bool((plataforma.get("copy") or "").strip())


def _le_falta_imagen(plataforma: dict[str, Any]) -> bool:
    """True si a la plataforma le falta imagen (sin nombre de media adjunto)."""
    return not bool((plataforma.get("imagen") or "").strip())


def _etiquetas_por_item() -> dict[str, list[str]]:
    """id de contenido -> NOMBRES de etiqueta resueltos (para el score). Best-effort: {}.

    `priorizacion.score_contenido` resuelve compromiso/evergreen por NOMBRE de etiqueta, asi que
    traducimos los ids a nombres. Un fallo de lectura deja el mapa vacio (el score cae a sus
    pesos base), nunca rompe el barrido.
    """
    try:
        nombres = {e.get("id", ""): e.get("nombre", "") for e in repos.listar_etiquetas()}
        return {
            cid: [nombres.get(eid, "") for eid in eids]
            for cid, eids in repos.etiquetas_por_contenido().items()
        }
    except Exception:  # noqa: BLE001 -- sin etiquetas legibles, el score usa sus pesos base
        return {}


def topics_sin_arte(
    items: list[dict[str, Any]],
    *,
    plataformas_por_item: dict[str, list[dict[str, Any]]],
    ya_procesados: set[str],
    maximo: int,
    etiquetas_por_item: dict[str, list[str]] | None = None,
    hoy: date | None = None,
) -> list[dict[str, Any]]:
    """Subconjunto de `items` del tablero que se debe auto-ilustrar (PURA, testeable).

    Reglas, en orden:
      - clase 'contenido' (no 'tarea'),
      - estado distinto de 'hecha' (cerrado),
      - con titulo no vacio (sin titulo no hay de que ilustrar),
      - con ALGUNA plataforma que tenga copy PERO le falte imagen,
      - no ya procesados (dedup por id, etiqueta `autogen-arte`),
      - se RECORTA a `maximo` (cap de seguridad por barrido).

    `plataformas_por_item` mapea id de contenido -> sus filas `contenido_plataforma`
    (dicts con al menos `copy` e `imagen`), inyectado para ser testeable sin DB.

    ORDEN (Flujo C): igual que en `autogen_copy.topics_pendientes`, si se pasan
    `etiquetas_por_item` (id -> NOMBRES) y `hoy`, se CONSUME `priorizacion.ordenar_por_score`
    ANTES de filtrar+capar, de modo que el arte se genera primero para los temas de MAYOR
    score. WRAPPER: solo consume `ordenar_por_score`, no toca la firma de `score_contenido`
    (compatible con el Flujo E). Sin esos argumentos, conserva el ORDEN de entrada (el tablero
    ya viene por prioridad+fecha). Determinista.
    """
    if etiquetas_por_item is not None and hoy is not None:
        items = priorizacion.ordenar_por_score(
            items, etiquetas_por_item=etiquetas_por_item, hoy=hoy
        )
    elegidos: list[dict[str, Any]] = []
    for item in items:
        if len(elegidos) >= maximo:
            break
        if (item.get("clase") or CLASE_CONTENIDO) != CLASE_CONTENIDO:
            continue
        if (item.get("estado") or "") == _ESTADO_CERRADO:
            continue
        if not (item.get("titulo") or "").strip():
            continue
        # Exclusión por marca: no auto-ilustramos temas de una marca apagada a mano para arte.
        if config.marca_apagada(config.ENV_PIPELINE_ARTE, item.get("marca") or ""):
            continue
        item_id = item.get("id")
        if item_id in ya_procesados:
            continue
        plataformas = plataformas_por_item.get(item_id, [])
        if not any(_tiene_copy(p) and _le_falta_imagen(p) for p in plataformas):
            continue
        elegidos.append(item)
    return elegidos


# Plantilla del prompt de auto-arte: vive en la Biblioteca de Texto como prompt EDITABLE
# (visible en la pestaña «Prompts»), no hardcodeada. El tema (titulo + descripcion) se inserta
# donde el equipo ponga el marcador `_MARCA_TEMA`. `_FALLBACK` es la red por si la lectura
# fallara o el cuerpo viniera vacio.
_PROMPT_ARTE_ID = "prompt/imagen/arte-noticia"
_MARCA_TEMA = "{{TEMA}}"
_PROMPT_ARTE_FALLBACK = (
    "Genera UNA sola fotografia realista para el feed de una marca de television que "
    "represente esta noticia: {{TEMA}}. Foto cruda, un unico encuadre fotografico, sin "
    "collage, marcos, placas, titulares, logotipos ni texto incrustado. Devuelve unicamente "
    "la imagen, no texto."
)


def _plantilla_arte() -> str:
    """Cuerpo EFECTIVO de la plantilla de arte (store del equipo > semilla del paquete).

    Import diferido de `libtexto` (evita ciclos). Si la lectura fallara o viniera vacia, cae
    al `_PROMPT_ARTE_FALLBACK` para no quedarnos sin prompt.
    """
    try:
        from . import libtexto

        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_ARTE_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar el auto-arte sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or _PROMPT_ARTE_FALLBACK


def prompt_arte(item: dict[str, Any]) -> str:
    """Prompt de imagen a partir del titulo + descripcion del tema (sin inventar datos).

    Toma la plantilla EDITABLE de la Biblioteca (`_PROMPT_ARTE_ID`) e inserta el tema donde
    esté el marcador `_MARCA_TEMA`; si el equipo lo quitó, adjunta el tema al final para no
    perderlo. Pide UNA foto cruda (sin marcos, placas ni texto editorial: eso lo compone la
    consola después). "" si el tema no tiene título (nada que ilustrar).
    """
    titulo = (item.get("titulo") or "").strip()
    descripcion = (item.get("descripcion") or "").strip()
    base = f"{titulo}. {descripcion}".strip(". ").strip() if descripcion else titulo
    if not base:
        return ""
    plantilla = _plantilla_arte()
    if _MARCA_TEMA in plantilla:
        return plantilla.replace(_MARCA_TEMA, base).strip()
    return f"{plantilla}\n\nTema: {base}".strip()


def _marca_legible(item: dict[str, Any]) -> str:
    """Nombre de marca legible si es valida, o "" (solo para el prompt/log; no se confia)."""
    marca = item.get("marca") or ""
    return marca if marca and marcas.es_marca(marca) else ""


def lanzar_para_topic(
    item: dict[str, Any], *, generar=media.generar_imagen
) -> dict[str, Any] | None:
    """Genera UN arte para un tema y lo adjunta a su 1a plataforma con copy sin imagen.

    Reutiliza la generacion de imagen existente (`media.generar_imagen`, inyectable para
    tests via `generar`) + `media.guardar_bytes`, y adjunta el nombre del media a la
    `contenido_plataforma` (poniendo `falta_imagen=False`). Etiqueta el tema `autogen-arte`
    para dedup. Devuelve un dict con `{contenido_id, plataforma_id, imagen}` o None si se
    omite (sin proveedor, sin plataforma candidata, prompt vacio).
    """
    if not media.proveedor_configurado():
        _log.info("Auto-arte: sin proveedor de imagen configurado; se omite.")
        return None
    item_id = item.get("id")
    if not item_id:
        return None
    # Localiza la primera plataforma con copy pero sin imagen (la candidata a ilustrar).
    try:
        plataformas = repos.listar_contenido_plataforma(item_id)
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, no hay donde adjuntar
        _log.exception("Auto-arte: no se pudieron leer las plataformas de un tema.")
        return None
    objetivo = next(
        (p for p in plataformas if _tiene_copy(p) and _le_falta_imagen(p)), None
    )
    if objetivo is None:
        return None
    prompt = prompt_arte(item)
    if not prompt:
        return None

    crudos = generar(prompt)
    nombre = media.guardar_bytes(crudos, ext="png")
    actualizado = repos.actualizar_contenido_plataforma(
        objetivo["id"], {"imagen": nombre, "falta_imagen": False}
    )
    # Dedup: marca el tema como ya procesado (best-effort; un fallo no debe romper el item).
    et_id = _id_etiqueta_autogen_arte()
    if et_id:
        repos.asignar_etiqueta(item_id, et_id)
    if actualizado is None:
        return None
    _registrar_actividad_arte(item, str(item_id), prompt, nombre)
    return {"contenido_id": item_id, "plataforma_id": objetivo["id"], "imagen": nombre}


def _registrar_actividad_arte(item: dict[str, Any], item_id: str, prompt: str, imagen: str) -> None:
    """Deja la generación de arte VISIBLE: una generación `tipo='imagen'` (con su PROMPT real) +
    el marcador de etapa ARTE correlacionado al tema (para Actividad IA y el detalle del pipeline).

    Best-effort: un fallo de traza no rompe la generación de arte. Import diferido de
    `pipeline_contenido` para no acoplar el módulo en carga (evita ciclo con `_barrido`).
    """
    marca = item.get("marca", "") or ""
    try:
        from .pipeline_contenido import ETAPA_ARTE, registrar_etapa

        gen = generaciones.crear({
            "tipo": "imagen",
            "marca": marca,
            "contenido_id": item_id,
            "prompt": prompt[:20000],
            "salida": f"Imagen generada: {imagen}",
            "etiqueta": f"Arte — {(item.get('titulo') or '')[:80]}",
            "estado": generaciones.ESTADO_COMPLETADO,
            "fase": generaciones.FASE_COMPLETADO,
            "fecha_fin": generaciones.ahora_iso(),
        })
        registrar_etapa(
            ETAPA_ARTE, marca, "Generación de arte",
            contenido_id=item_id, gen_id=(gen.get("id", "") if gen else ""),
        )
    except Exception:  # noqa: BLE001 -- la traza de actividad no debe romper el arte
        _log.warning("Auto-arte: no se pudo registrar la actividad del arte.", exc_info=True)


def _plataformas_por_item(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Mapa id de contenido -> sus filas de plataforma (best-effort; vacio si falla)."""
    mapa: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        item_id = item.get("id")
        if not item_id:
            continue
        try:
            mapa[item_id] = repos.listar_contenido_plataforma(item_id)
        except Exception:  # noqa: BLE001 -- una lectura fallida deja el item sin plataformas
            mapa[item_id] = []
    return mapa

