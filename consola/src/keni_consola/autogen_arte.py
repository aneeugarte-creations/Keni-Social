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

POR LA COLA (antes SÍNCRONO)
============================
La generación del arte ANTES corría SÍNCRONA dentro del barrido (con un ThreadPool propio,
fuera del sistema de cola/carriles/reintentos/idempotencia). Eso tenía dos problemas: (1) sin
idempotencia real, un crash entre `media.generar_imagen(prompt)` —que ya gastó el proveedor— y
el etiquetado de éxito RE-GASTABA el proveedor en el siguiente barrido; (2) mezclaba trabajo de
imagen (I/O + algo de CPU) fuera de la cola de jobs. AHORA `lanzar_para_topic` solo SELECCIONA
y ENCOLA un job de PROCESO (`jobspec.PROC_IMAGEN`) vía `dominio.generar.lanzar_arte`, con CLAVE
DE IDEMPOTENCIA ESTABLE (tema+marca+prompt-base); el WORKER, en su CARRIL de proceso (no bloquea
el copy), corre `ejecutar_arte_job` —que llama a `media.generar_imagen`, sube la imagen y la
adjunta a la pieza—. La semántica observable se conserva: NO publica, deja la imagen en el
borrador, y el dedup por etiqueta `autogen-arte` se asigna AL ÉXITO (en el ejecutor).

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


def prompt_arte(item: dict[str, Any]) -> str:
    """Mensaje de USUARIO (el TEMA a ilustrar) para el generador de imagen del auto-arte.

    La DIRECTIVA del generador (foto realista, sin texto/placas; "Arte" en la Biblioteca) viaja
    en el mensaje de SISTEMA, que `media.generar_imagen` añade automáticamente; aquí solo aportamos
    el tema, a partir del título + descripción. "" si no hay título (nada que ilustrar).
    """
    titulo = (item.get("titulo") or "").strip()
    descripcion = (item.get("descripcion") or "").strip()
    return f"{titulo}. {descripcion}".strip(". ").strip() if descripcion else titulo


def _marca_legible(item: dict[str, Any]) -> str:
    """Nombre de marca legible si es valida, o "" (solo para el prompt/log; no se confia)."""
    marca = item.get("marca") or ""
    return marca if marca and marcas.es_marca(marca) else ""


def lanzar_para_topic(item: dict[str, Any]) -> dict[str, Any] | None:
    """SELECCIONA la plataforma a ilustrar y ENCOLA un job de arte (antes era SÍNCRONO).

    Localiza la 1a plataforma del tema con copy pero sin imagen y, vía
    `dominio.generar.lanzar_arte`, ENCOLA un job de PROCESO (`jobspec.PROC_IMAGEN`) con CLAVE DE
    IDEMPOTENCIA ESTABLE. El WORKER (carril de proceso) genera la imagen y la adjunta a la pieza
    FUERA del barrido (`ejecutar_arte_job`), heredando idempotencia + reintentos + carril. Antes
    esta función llamaba a `media.generar_imagen` EN LÍNEA y adjuntaba la imagen aquí mismo.

    Devuelve el REGISTRO de generación encolado (para sondeo/conteo) —o el run en vuelo si ya
    había uno con esta clave (idempotencia)—, o None si se OMITE (sin proveedor, sin plataforma
    candidata, prompt vacío). Los gates SAFE se conservan: el cap por barrido y el dedup por
    etiqueta `autogen-arte` los aplican los llamadores (`topics_sin_arte`/`ids_ya_procesados`);
    la etiqueta se asigna AL ÉXITO dentro del ejecutor, NO al encolar (dedup-al-éxito, como el
    copy): un arte que falla NO queda etiquetado y el barrido lo reintenta, mientras la clave de
    idempotencia evita el doble lanzamiento del que sigue en vuelo. Propaga `ColaLlenaError`
    (backpressure) para que el barrido la recoja en el próximo tick.
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
    # Import diferido: `dominio.generar` no se acopla en carga (evita ciclos al importar).
    from .dominio import generar

    return generar.lanzar_arte(
        contenido_id=str(item_id),
        plataforma_id=str(objetivo.get("id") or ""),
        marca=item.get("marca", "") or "",
        titulo=item.get("titulo", "") or "",
        prompt=prompt,
    )


def _resolver_objetivo_arte(
    contenido_id: str, plataforma_id: str
) -> dict[str, Any] | None:
    """Plataforma a ilustrar, RE-RESUELTA fresca en el worker (idempotencia natural).

    Si `plataforma_id` sigue teniendo copy SIN imagen, ésa; si no (la ilustró un humano, o un
    intento previo del propio job antes de marcar terminal), la PRIMERA plataforma del tema con
    copy y sin imagen. None si ya no queda candidata: el ejecutor lo trata como un no-op idempotente
    (no re-genera ni re-sube). Best-effort: una lectura fallida devuelve None (el reaper lo recoge).
    """
    if not contenido_id:
        return None
    try:
        plataformas = repos.listar_contenido_plataforma(contenido_id)
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, no hay donde adjuntar
        _log.exception("Auto-arte: no se pudieron leer las plataformas del tema %s.", contenido_id)
        return None
    if plataforma_id:
        for p in plataformas:
            if p.get("id") == plataforma_id and _tiene_copy(p) and _le_falta_imagen(p):
                return p
    return next((p for p in plataformas if _tiene_copy(p) and _le_falta_imagen(p)), None)


def ejecutar_arte_job(gen_id: str, spec: dict[str, Any]) -> None:
    """EJECUTOR del job de proceso `imagen` (lo despacha el worker en el carril de proceso).

    Genera UN arte (`media.generar_imagen`), lo sube (`media.guardar_bytes`) y lo adjunta a la
    pieza objetivo (`falta_imagen=False`), reportando estado a `generaciones` igual que los
    ejecutores de ASR/vídeo. Etiqueta el tema `autogen-arte` (dedup AL ÉXITO) y deja la traza en
    Actividad IA + el pipeline de la pieza (`registrar_arte`). NO publica: la imagen queda en el
    borrador para la revisión humana de siempre.

    IDEMPOTENTE ante re-claim del reaper / re-encolado: si la pieza ya NO tiene plataforma con copy
    sin imagen (un intento previo del MISMO job ya la adjuntó antes de marcar terminal, o un humano
    la ilustró), COMPLETA sin volver a llamar al proveedor —ni doble gasto ni doble subida—. El
    contrato de firma (`ejecutar(gen_id, spec)`) es el de todos los jobs de proceso.
    """
    contenido_id = (spec.get("contenido_id") or "").strip()
    plataforma_id = (spec.get("plataforma_id") or "").strip()
    marca = spec.get("marca") or ""
    titulo = spec.get("titulo") or ""
    prompt = (spec.get("prompt") or "").strip()
    try:
        if not prompt:
            _terminar_error_arte(gen_id, "Falta el tema (prompt) del arte.")
            return
        if not media.proveedor_configurado():
            _terminar_error_arte(
                gen_id, "No hay proveedor de imagen configurado para generar el arte."
            )
            return
        objetivo = _resolver_objetivo_arte(contenido_id, plataforma_id)
        if objetivo is None:
            # Sin candidata: idempotente. Completa SIN gastar el proveedor (la pieza ya está
            # ilustrada, o un intento previo la adjuntó). El barrido no la re-elige (etiqueta).
            generaciones.actualizar(gen_id, {
                "estado": generaciones.ESTADO_COMPLETADO,
                "resultado": {
                    "contenido_id": contenido_id,
                    "omitido": "el tema ya no tiene una plataforma con copy sin imagen",
                },
                "fecha_fin": generaciones.ahora_iso(),
            })
            return
        generaciones.actualizar(
            gen_id, {"estado": generaciones.ESTADO_EJECUTANDO, "fase": "generando imagen"}
        )
        crudos = media.generar_imagen(prompt)
        nombre = media.guardar_bytes(crudos, ext="png")
        repos.actualizar_contenido_plataforma(
            objetivo["id"], {"imagen": nombre, "falta_imagen": False}
        )
        # Dedup: marca el tema como ya procesado (best-effort; un fallo no debe romper el cierre).
        et_id = _id_etiqueta_autogen_arte()
        if et_id and contenido_id:
            repos.asignar_etiqueta(contenido_id, et_id)
        registrar_arte(
            contenido_id=contenido_id, marca=marca, titulo=titulo, prompt=prompt, imagen=nombre,
        )
        generaciones.actualizar(gen_id, {
            "estado": generaciones.ESTADO_COMPLETADO,
            "resultado": {
                "contenido_id": contenido_id,
                "plataforma_id": objetivo["id"],
                "imagen": nombre,
            },
            "fecha_fin": generaciones.ahora_iso(),
        })
    except media.MediaError as e:
        _terminar_error_arte(gen_id, str(e) or "No se pudo generar la imagen del arte.")
    except Exception as e:  # noqa: BLE001 -- red de seguridad: nunca dejar el job sin terminal
        _log.exception("autogen_arte.ejecutar_arte_job: fallo inesperado (gen %s)", gen_id)
        _terminar_error_arte(gen_id, f"Error inesperado al generar el arte: {e}")


def _terminar_error_arte(gen_id: str, mensaje: str) -> None:
    """Marca la generación de arte en error con un mensaje claro en español (para Actividad IA)."""
    _log.warning("autogen_arte (gen %s): %s", gen_id, mensaje)
    generaciones.actualizar(gen_id, {
        "estado": generaciones.ESTADO_ERROR,
        "error": mensaje,
        "fecha_fin": generaciones.ahora_iso(),
    })


def registrar_arte(
    *, contenido_id: str, marca: str, titulo: str, prompt: str, imagen: str
) -> None:
    """Registra una generación de ARTE en el pipeline de SU pieza (`contenido_id`).

    Deja DOS trazas correlacionadas por `contenido_id`: una generación `tipo='pipeline'` con el
    PROMPT real y la salida, y el marcador de etapa ARTE. Así el arte —tanto el auto-arte del
    pipeline como el botón manual «Generar con IA»— sale en Actividad IA y en el detalle del
    pipeline de la pieza, NO como una generación suelta. Sin `contenido_id` no registra (no hay
    pipeline al que colgar). Best-effort: un fallo de traza no rompe la generación. Import diferido
    de `pipeline_contenido` para no acoplar en carga (evita ciclo con `_barrido`).
    """
    if not contenido_id:
        return
    marca = marca or ""
    try:
        from .pipeline_contenido import ETAPA_ARTE, registrar_etapa

        gen = generaciones.crear({
            "tipo": "pipeline",
            "marca": marca,
            "contenido_id": contenido_id,
            "prompt": prompt[:20000],
            "salida": f"Imagen generada: {imagen}",
            "etiqueta": f"Arte — {(titulo or '')[:80]}",
            "estado": generaciones.ESTADO_COMPLETADO,
            "fase": generaciones.FASE_COMPLETADO,
            "fecha_fin": generaciones.ahora_iso(),
        })
        registrar_etapa(
            ETAPA_ARTE, marca, "Generación de arte",
            contenido_id=contenido_id, gen_id=(gen.get("id", "") if gen else ""),
        )
    except Exception:  # noqa: BLE001 -- la traza de actividad no debe romper el arte
        _log.warning("Arte: no se pudo registrar la actividad del arte.", exc_info=True)


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

