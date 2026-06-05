"""Auto-generacion de COPY al entrar un tema al tablero (fase3 auto-produccion, H2).

PROBLEMA QUE RESUELVE
=====================
Las fuentes (import de calendario, radar-auto, radar, RSS) meten TEMAS al tablero, pero el
copy solo se genera si ALGUIEN pulsa "generar" para cada uno. Objetivo de producto (peticion
de Angel): que el copy "se vaya generando a medida que entran los temas", para que el equipo
llegue por la manana y tenga BORRADORES listos para revisar, no temas en crudo. Aqui un daemon
(espejo de `radar_auto`) barre el tablero cada N horas y, para cada tema alimentado por una
fuente que AUN no tiene copy y SI tiene marca, ENCOLA una generacion de copy por el MISMO
camino que el boton manual del asistente (el lanzador NEUTRO `dominio.generar.lanzar_copy`).
El borrador resultante cae en la cola de revision (`/revision/editorial`) como cualquier otro.

SEGURO POR DISENO (CONSERVADOR)
===============================
  - GATEADO: el daemon solo arranca con `KENI_AUTOGEN=1` (def OFF). Sin el flag, nada se
    auto-genera (el equipo genera a mano, como hasta ahora).
  - SOLO FUENTES: solo procesa temas cuyo `origen` es de una FUENTE (`ORIGENES_TOPIC`); el
    contenido manual del equipo NO se toca (lo genera quien lo crea, si quiere).
  - REQUIERE MARCA: sin marca no hay voz/tropicalizacion; esos temas se omiten (el equipo
    asigna marca y entran al siguiente barrido).
  - CAP por barrido (`KENI_AUTOGEN_MAX`, def 3): cada item lanza un `claude -p`; el cap evita
    avalanchas. El cap del worker (`KENI_MAX_JOBS`) sigue aplicando aguas abajo.
  - DEDUP: tras encolar, el tema se ETIQUETA `autogen` para no re-generarlo barrido tras
    barrido. La seleccion lee esa etiqueta para saltarse lo ya hecho.
  - NO PUBLICA: el borrador nace `borrador` y pasa por la MISMA revision/aprobacion humana;
    la publicacion real (vía Metricool) sigue gated por `KENI_PUBLICAR_REAL`.

La SELECCION (`topics_pendientes`) es PURA y testeable. El LANZAMIENTO reutiliza el pipeline
existente sin tocar el contrato de borradores ni el jobspec: por eso es de bajo riesgo.
"""

from __future__ import annotations

import logging
import threading
from datetime import date
from typing import Any

from . import config, daemon_util, generaciones, marcas, priorizacion, redes, repos
from .dominio import generar as dom_generar
from .estados import CLASE_CONTENIDO, ORIGENES_AUTOGEN

_log = logging.getLogger("keni_consola.autogen_copy")

# Origenes de contenido que cuentan como "tema redactable" (un borrador se encola solo).
# Fuente UNICA del vocabulario: `estados.ORIGENES_AUTOGEN` (modulo neutro), para que los
# flujos transversales no compitan por este literal. Incluye las fuentes externas historicas
# (import-calendario, radar-auto, radar, rss) Y el alta creativa del equipo (`equipo`), que
# la direccion decidio auto-generar SIEMPRE (2026-06-01). El alta TECLEADA legada (origen "")
# sigue EXCLUIDA a proposito: no auto-generamos lo que el equipo teclea sin marcar como alta.
ORIGENES_TOPIC: frozenset[str] = frozenset(ORIGENES_AUTOGEN)

# Etiqueta de origen del historial para el copy auto-generado (nota -> piezas por red, con
# auto-verificacion). Tras retirar el sistema de skills, el copy va por el lanzador NEUTRO
# (`dominio.generar.lanzar_copy`), que compone el prompt copy-desde-nota autocontenido; este
# valor es solo la etiqueta de procedencia en el historial.
ORIGEN_HISTORIAL = "copy-desde-nota"

# Etiqueta-marca de dedup: un tema ya encolado para auto-generacion la lleva.
ETIQUETA_AUTOGEN = "autogen"

# Estado terminal del contenido padre: ya no tiene sentido generarle copy.
_ESTADO_CERRADO = "hecha"


def _normaliza(texto: object) -> str:
    return " ".join(("" if texto is None else str(texto)).strip().lower().split())


def _id_etiqueta_autogen(*, crear: bool = True) -> str:
    """Id de la etiqueta `autogen` (la crea si no existe y `crear`). "" si no se puede."""
    for et in repos.listar_etiquetas():
        if _normaliza(et.get("nombre", "")) == ETIQUETA_AUTOGEN:
            return et.get("id", "")
    if not crear:
        return ""
    return repos.crear_etiqueta(nombre=ETIQUETA_AUTOGEN).get("id", "")


def ids_ya_generados() -> set[str]:
    """Ids de contenido ya encolados para auto-generacion (etiqueta `autogen`).

    Best-effort: si la lectura falla, devuelve set vacio (peor caso: un re-encolado, que el
    propio worker/historial acotan, nunca una excepcion que rompa el barrido).
    """
    try:
        et_id = _id_etiqueta_autogen(crear=False)
        if not et_id:
            return set()
        return repos.ids_contenido_con_etiqueta(et_id)
    except Exception:  # noqa: BLE001 -- un fallo de lectura no debe abortar el barrido
        return set()


def _etiquetas_por_item() -> dict[str, list[str]]:
    """id de contenido -> NOMBRES de etiqueta resueltos (para el score). Best-effort: {}.

    `priorizacion.score_contenido` resuelve compromiso/green por NOMBRE de etiqueta, asi que
    traducimos los ids a nombres. Un fallo de lectura deja el mapa vacio (el score cae a sus
    pesos base: prioridad/flujo/fecha/frescura), nunca rompe el barrido.
    """
    try:
        nombres = {e.get("id", ""): e.get("nombre", "") for e in repos.listar_etiquetas()}
        return {
            cid: [nombres.get(eid, "") for eid in eids]
            for cid, eids in repos.etiquetas_por_contenido().items()
        }
    except Exception:  # noqa: BLE001 -- sin etiquetas legibles, el score usa sus pesos base
        return {}


def topics_pendientes(
    items: list[dict[str, Any]],
    *,
    ya_generados: set[str],
    maximo: int,
    etiquetas_por_item: dict[str, list[str]] | None = None,
    hoy: date | None = None,
) -> list[dict[str, Any]]:
    """Subconjunto de `items` del tablero que se debe auto-generar (PURA, testeable).

    Reglas, en orden:
      - clase 'contenido' (no 'tarea'),
      - `origen` de una FUENTE (`ORIGENES_TOPIC`),
      - estado distinto de 'hecha' (cerrado),
      - con marca valida (sin marca no hay voz),
      - con titulo no vacio,
      - no ya generados (dedup por id),
      - se RECORTA a `maximo` (cap de seguridad por barrido).

    ORDEN (Flujo C): el SCORE de priorizacion ordena la COLA DE TRABAJO de la IA (que se
    auto-genera primero), no solo la vista Panel-9am. Si se pasan `etiquetas_por_item` (id ->
    NOMBRES) y `hoy`, se CONSUME `priorizacion.ordenar_por_score` ANTES de filtrar+capar, de
    modo que con cap entran los temas de MAYOR score. Es un WRAPPER que solo CONSUME esa
    funcion: no toca la firma de `score_contenido` (compatible con que el Flujo E la enriquezca
    despues). Si no se pasan, conserva el ORDEN de entrada (el tablero ya viene por
    prioridad+fecha). Determinista en ambos casos.
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
        if (item.get("origen") or "") not in ORIGENES_TOPIC:
            continue
        if (item.get("estado") or "") == _ESTADO_CERRADO:
            continue
        marca = item.get("marca") or ""
        if not marca or not marcas.es_marca(marca):
            continue
        # Exclusión por marca: no auto-generamos copy de una marca apagada a mano para auto-copy.
        if config.marca_apagada(config.ENV_AUTOGEN, marca):
            continue
        if not (item.get("titulo") or "").strip():
            continue
        if item.get("id") in ya_generados:
            continue
        elegidos.append(item)
    return elegidos


def _nota_de(item: dict[str, Any]) -> str:
    """Nota de partida del copy: titulo + descripcion del tema (sin inventar)."""
    titulo = (item.get("titulo") or "").strip()
    descripcion = (item.get("descripcion") or "").strip()
    return f"{titulo}\n\n{descripcion}".strip() if descripcion else titulo


def _redes_de(item: dict[str, Any]) -> list[str]:
    """Redes objetivo: las del propio tema si las tiene; si no, las redes por defecto."""
    try:
        plataformas = repos.listar_contenido_plataforma(item["id"])
    except Exception:  # noqa: BLE001 -- sin plataformas legibles, caemos al defecto
        plataformas = []
    reds = [p.get("red") for p in plataformas if redes.es_red(p.get("red") or "")]
    if reds:
        return list(dict.fromkeys(reds))
    # Defecto: la lista canonica de redes (la misma que usa el asistente/copy del tablero).
    return redes.ids()


def lanzar_para_topic(item: dict[str, Any]) -> dict[str, Any] | None:
    """Encola una generacion de copy para un tema y lo marca como generado. None si se omite.

    Reutiliza el lanzador NEUTRO `dominio.generar.lanzar_copy` (mismo camino que el boton
    manual del asistente y que `api/rss.generar`): compone el prompt copy-desde-nota
    autocontenido (semilla + editorial de la marca + la nota del tema), encola en background
    y el borrador entra a la cola de revision. `contenido_id` NIDA el borrador bajo el tema.
    """
    marca = item.get("marca") or ""
    if not marca or not marcas.es_marca(marca):
        return None
    nota = _nota_de(item)
    if not nota:
        return None
    redes_ids = _redes_de(item)
    gen = dom_generar.lanzar_copy(
        tipo="autogen",
        marca=marca,
        contexto=nota,
        redes_ids=redes_ids,
        titulo="Auto-copy",
        titulo_dado=(item.get("titulo") or "").strip()[:300],
        texto_base=nota,
        origen_historial=ORIGEN_HISTORIAL,
        autor=None,
        # Lista viva: el borrador auto-generado cuelga del tema origen (su tarjeta lo
        # muestra y sigue fluyendo por aprobacion/programador), no como contenido suelto.
        contenido_id=item.get("id") or "",
    )
    # Dedup: marca el tema como ya encolado (solo si el encolado no lanzo). Best-effort.
    et_id = _id_etiqueta_autogen()
    if et_id:
        repos.asignar_etiqueta(item["id"], et_id)
    return gen


def ejecutar_barrido() -> list[dict[str, Any]]:
    """Un barrido: lee el tablero, elige temas pendientes y encola copy. Devuelve lo lanzado.

    Best-effort: un fallo por item se loguea y se sigue; si la cola esta llena, se corta el
    barrido (reintenta el siguiente, sin marcar los no lanzados).

    SINGLE-FLIGHT cross-proceso (advisory lock de Postgres): el daemon y el endpoint a demanda
    comparten este barrido; su dedup (`ids_ya_generados`) es leer-luego-escribir en Python, asi
    que dos barridos solapados podrian lanzar `claude -p` para el MISMO tema dos veces. El lock
    hace que un segundo barrido concurrente salga de inmediato con lista vacia (no lanza nada).
    """
    from . import db

    with db.lock_barrido("autogen_copy") as ok:
        if not ok:
            _log.debug("Auto-generacion: otro barrido en curso; se omite este.")
            return []
        return _ejecutar_barrido()


def _ejecutar_barrido() -> list[dict[str, Any]]:
    """Cuerpo del barrido de auto-generacion (ya bajo el single-flight de `ejecutar_barrido`)."""
    try:
        items = repos.listar_contenido()
    except Exception:  # noqa: BLE001 -- el tablero no disponible no debe romper el barrido
        _log.exception("No se pudo leer el tablero para la auto-generacion.")
        return []
    elegidos = topics_pendientes(
        items,
        ya_generados=ids_ya_generados(),
        maximo=config.autogen_max(),
        # El SCORE ordena que se auto-genera primero (la cola de trabajo de la IA, no solo
        # el Panel-9am). Best-effort: si no se pueden resolver las etiquetas, cae al orden
        # del tablero (prioridad+fecha) sin romper el barrido.
        etiquetas_por_item=_etiquetas_por_item(),
        hoy=date.today(),
    )
    lanzados: list[dict[str, Any]] = []
    for item in elegidos:
        try:
            gen = lanzar_para_topic(item)
        except generaciones.ColaLlenaError:
            _log.info("Auto-generacion: cola llena; el resto entra en el proximo barrido.")
            break
        except Exception:  # noqa: BLE001 -- un fallo por item no debe matar el barrido
            _log.exception("Fallo al auto-generar copy para un tema del tablero.")
            continue
        if gen:
            lanzados.append(gen)
    if lanzados:
        _log.info("Auto-generacion: %d tema(s) encolado(s) para copy.", len(lanzados))
    return lanzados


def _intervalo_segundos() -> float:
    return config.autogen_intervalo_horas() * 3600.0


def iniciar_autogen(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio de auto-generacion de copy (GATEADO EN VIVO).

    Pensado para el servidor real (`__main__`), NO para `crear_app` (los tests no lo arrancan,
    igual que el resto de daemons). El hilo arranca SIEMPRE y comprueba `KENI_AUTOGEN` en cada
    ciclo: apagar/encender en runtime aplica sin reiniciar (apagar en <= ~1 min; encender tras
    estar apagado dispara un barrido de inmediato). El hilo es daemon; un fallo de barrido se
    loguea y NO lo mata.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.autogen_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
        )

    hilo = threading.Thread(target=bucle, name="autogen-copy-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVA" if config.autogen_activo() else "EN ESPERA (KENI_AUTOGEN off)"
    _log.info(
        "Auto-generacion de copy %s, cada %.0f h (max/barrido=%d).",
        estado, intervalo / 3600.0, config.autogen_max(),
    )
    return hilo
