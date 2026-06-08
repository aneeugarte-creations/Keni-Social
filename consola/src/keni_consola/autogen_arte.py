"""Auto-generacion de ARTE (imagen) para temas del tablero con copy pero sin imagen (H2-b).

PROBLEMA QUE RESUELVE
=====================
El auto-copy (`autogen_copy.py`) deja BORRADORES de texto listos para revisar, pero el
equipo aun tiene que generar un arte a mano para cada uno. Objetivo de producto (peticion
de Angel): que tambien "se vaya generando parte del arte a medida que entran los temas".
Aqui un daemon (espejo de `autogen_copy`/`radar_auto`) barre el tablero cada N horas y, para
cada TEMA que YA tiene copy/borrador en alguna plataforma pero le FALTA imagen, genera UN
arte por IA (reutilizando el MISMO proveedor que el boton `/api/media/generar`) y lo ADJUNTA
a esa plataforma. La pieza sigue su flujo normal de revision/aprobacion humana.

SEGURO POR DISENO (CONSERVADOR)
===============================
  - GATEADO: el daemon solo arranca con `KENI_AUTOGEN_ARTE=1` (def OFF). Sin el flag, nada
    se auto-genera (el equipo hace el arte a mano, como hasta ahora).
  - SOLO TEMAS CON COPY Y SIN IMAGEN: solo procesa contenido 'contenido' no cerrado que
    tenga alguna `contenido_plataforma` con copy pero sin imagen. No inventa piezas.
  - SIN CREDENCIALES, NO HACE NADA: si no hay proveedor de imagen configurado, loguea y
    sigue (degrada con elegancia; no rompe el barrido).
  - CAP por barrido (`KENI_AUTOGEN_ARTE_MAX`, def 3): cada item llama al proveedor de
    imagen (coste); el cap evita avalanchas.
  - DEDUP: tras procesar, el tema se ETIQUETA `autogen-arte` para no re-generarlo barrido
    tras barrido. La seleccion lee esa etiqueta para saltarse lo ya hecho.
  - NO PUBLICA: solo adjunta el arte al borrador; la revision/aprobacion humana y la
    publicacion real (`KENI_PUBLICAR_REAL`) siguen gated, igual que siempre.

La SELECCION (`topics_sin_arte`) es PURA y testeable: recibe las plataformas por item como
un dict, asi no toca la DB. El LANZAMIENTO reutiliza `media.generar_imagen` (proveedor
inyectable/mockeable) sin reinventar la generacion de imagen: bajo riesgo.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any

from . import config, daemon_util, marcas, media, priorizacion, repos
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
        if config.marca_apagada(config.ENV_AUTOGEN_ARTE, item.get("marca") or ""):
            continue
        item_id = item.get("id")
        if item_id in ya_procesados:
            continue
        plataformas = plataformas_por_item.get(item_id, [])
        if not any(_tiene_copy(p) and _le_falta_imagen(p) for p in plataformas):
            continue
        elegidos.append(item)
    return elegidos


def prompt_arte(item: dict[str, Any]) -> str:
    """Prompt de imagen a partir del titulo + descripcion del tema (sin inventar datos).

    Pide una ilustracion editorial limpia, apta para redes, evitando texto incrustado
    (que los modelos de imagen renderizan mal) y sin datos sensibles inventados.
    """
    titulo = (item.get("titulo") or "").strip()
    descripcion = (item.get("descripcion") or "").strip()
    base = f"{titulo}. {descripcion}".strip(". ").strip() if descripcion else titulo
    if not base:
        return ""
    return (
        "Crea una imagen editorial para redes sociales que ilustre este tema: "
        f"{base}. "
        "Estilo limpio y profesional, composicion clara, sin texto incrustado ni "
        "logotipos. No inventes datos, rostros reconocibles ni cifras."
    )


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
    return {"contenido_id": item_id, "plataforma_id": objetivo["id"], "imagen": nombre}


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


def ejecutar_barrido() -> list[dict[str, Any]]:
    """Un barrido: lee el tablero, elige temas sin arte y los ilustra. Devuelve lo adjuntado.

    Si no hay proveedor de imagen, no hace nada (degrada con elegancia). Best-effort: un
    fallo por item se loguea y se sigue; no rompe el hilo.
    """
    if not media.proveedor_configurado():
        _log.info("Auto-arte: sin proveedor de imagen configurado; barrido omitido.")
        return []
    try:
        items = repos.listar_contenido()
    except Exception:  # noqa: BLE001 -- el tablero no disponible no debe romper el barrido
        _log.exception("No se pudo leer el tablero para la auto-generacion de arte.")
        return []
    elegidos = topics_sin_arte(
        items,
        plataformas_por_item=_plataformas_por_item(items),
        ya_procesados=ids_ya_procesados(),
        maximo=config.autogen_arte_max(),
        # El SCORE ordena que se auto-ilustra primero (la cola de trabajo de la IA).
        etiquetas_por_item=_etiquetas_por_item(),
        hoy=date.today(),
    )
    adjuntados: list[dict[str, Any]] = []
    for item in elegidos:
        try:
            res = lanzar_para_topic(item)
        except Exception:  # noqa: BLE001 -- un fallo por item no debe matar el barrido
            _log.exception("Fallo al auto-generar arte para un tema del tablero.")
            continue
        if res:
            adjuntados.append(res)
    if adjuntados:
        _log.info("Auto-arte: %d tema(s) ilustrado(s).", len(adjuntados))
    return adjuntados


def _intervalo_segundos() -> float:
    return config.autogen_arte_intervalo_horas() * 3600.0


def iniciar_autogen_arte(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de auto-generacion de arte (GATEADO EN VIVO).

    Pensado para el servidor real (`__main__`), NO para `crear_app` (los tests no lo
    arrancan, igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba
    `KENI_AUTOGEN_ARTE` en cada ciclo: apagar/encender en runtime aplica sin reiniciar
    (apagar en <= ~1 min; encender tras estar apagado dispara un barrido de inmediato). El
    hilo es daemon; un fallo de barrido se loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.autogen_arte_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="autogen-arte-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVA" if config.autogen_arte_activo() else "EN ESPERA (KENI_AUTOGEN_ARTE off)"
    _log.info(
        "Auto-generacion de arte %s, cada %.0f h (max/barrido=%d).",
        estado, intervalo / 3600.0, config.autogen_arte_max(),
    )
    return hilo
