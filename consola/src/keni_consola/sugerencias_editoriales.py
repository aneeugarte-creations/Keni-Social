"""Sugerencias editoriales: job DIARIO que convierte noticias de algoritmo importantes en
propuestas de cambio a la ficha editorial de cada plataforma y a sus limites.

QUE HACE
========
Una vez al dia (gateado), mira las noticias de `noticias_algoritmo` que son IMPORTANTES
(`nivel='alta'` o `es_cambio`) y aun NO procesadas (`sugerida=0`), las agrupa por
plataforma y, por cada plataforma afectada (con tope), lanza UN `claude -p` que recibe la
ficha editorial actual + el limite actual + esas noticias, y PROPONE cambios concretos.
Las propuestas se guardan en `sugerencias_editoriales` (estado 'nueva') para que el equipo
las revise y aplique a mano. NO escribe la ficha ni cambia limites por su cuenta.

POR QUE EL DAEMON ENCOLA (no ejecuta claude)
============================================
El contenedor de daemons NO tiene el binario `claude` ni el token (por diseno: los daemons
AGENDAN, el `worker` EJECUTA). Asi que el barrido ENCOLA una generacion de tipo prompt
(post-procesado IDENTIDAD: el texto queda en `salida`), el worker corre `claude -p`, y este
barrido SONDEA el registro de la generacion (vive en el volumen `/data` compartido) hasta
que completa, parsea la salida y persiste las sugerencias. Mismo patron de encolado que la
Texto; el unico anadido es el sondeo del resultado desde el daemon.

HONESTIDAD: el prompt pide proponer SOLO cambios que las noticias justifiquen; si una
noticia no implica un cambio editorial real, no se inventa. Una plataforma sin cambios
propuestos igualmente marca sus noticias como procesadas (no se re-pregunta cada dia).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from . import libtexto, config, daemon_util, limites_plataforma, repos
from .dominio import generar, jobspec, json_llm

_log = logging.getLogger("keni_consola.sugerencias_editoriales")

# Importancia minima para entrar al digest: nivel alto O marcada como cambio de algoritmo.
_NIVEL_IMPORTANTE = "alta"
# Plataformas sin ficha propia (no se mapea 'general' a una ficha concreta): se omiten del
# digest editorial (su cobertura es informativa, no editable como una ficha de red).
_SIN_FICHA = frozenset({"general"})
# Cuanto esperar a que el worker complete UNA generacion (claude -p) antes de rendirse.
_TIMEOUT_GENERACION_SEG = 240.0
_SONDEO_SEG = 4.0


def ficha_id_de(plataforma: str) -> str:
    """Id del documento de texto de la ficha editorial de una plataforma."""
    return f"editorial/plataformas/{plataforma}"


# --------------------------------------------------------------------------- #
# Seleccion (PURA, testeable): que noticias entran y agrupadas por plataforma   #
# --------------------------------------------------------------------------- #


def es_importante(noticia: dict[str, Any]) -> bool:
    """True si la noticia merece una sugerencia editorial (nivel alto o cambio de algoritmo)."""
    return noticia.get("nivel") == _NIVEL_IMPORTANTE or bool(noticia.get("es_cambio"))


def seleccionar(noticias: list[dict[str, Any]], *, maximo: int) -> dict[str, list[dict[str, Any]]]:
    """Agrupa las noticias importantes por plataforma y limita a `maximo` plataformas (PURA).

    Descarta las que no son importantes y las plataformas sin ficha (`general`). Prioriza las
    plataformas con MAS noticias importantes (las de mayor señal editorial). Determinista.
    """
    por_plataforma: dict[str, list[dict[str, Any]]] = {}
    for n in noticias:
        if not es_importante(n):
            continue
        plat = n.get("plataforma") or "general"
        if plat in _SIN_FICHA:
            continue
        por_plataforma.setdefault(plat, []).append(n)
    # Plataformas con mas noticias importantes primero; corta a `maximo`.
    ordenadas = sorted(por_plataforma.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return dict(ordenadas[: max(0, maximo)])


# --------------------------------------------------------------------------- #
# Composicion del prompt + parseo de la respuesta                               #
# --------------------------------------------------------------------------- #


# La plantilla del prompt vive en la Biblioteca de Texto como prompt EDITABLE (pestaña
# «Prompts»), no hardcodeada. Los 4 datos dinámicos se insertan en sus marcadores. Si el store
# fallara, la red es la SEMILLA del paquete (fuente única, sin texto duplicado aquí).
_PROMPT_SUGERENCIAS_ID = "prompt/sugerencias"


def _plantilla_sugerencias() -> str:
    """Cuerpo EFECTIVO de la plantilla (store del equipo > semilla del paquete)."""
    try:
        cuerpo = (libtexto.cuerpo_efectivo(_PROMPT_SUGERENCIAS_ID) or "").strip()
    except Exception:  # noqa: BLE001 -- nunca dejar el digest sin prompt por un fallo de lectura
        cuerpo = ""
    return cuerpo or libtexto.cuerpo_semilla(_PROMPT_SUGERENCIAS_ID).strip()


def componer_prompt(
    plataforma: str, noticias: list[dict[str, Any]], *, ficha: str, limite: int | None
) -> str:
    """Arma el prompt de `claude -p` para una plataforma (ficha + limite + noticias).

    La plantilla es EDITABLE en la Biblioteca (`_PROMPT_SUGERENCIAS_ID`); aquí solo insertamos
    los 4 datos en sus marcadores `{{PLATAFORMA}}` `{{FICHA}}` `{{LIMITE}}` `{{NOTICIAS}}`.
    """
    nombre = plataforma.capitalize()
    limite_txt = f"{limite} caracteres" if limite else "sin límite duro definido"
    ficha_txt = ficha.strip() or "(todavía no hay ficha editorial para esta plataforma)"
    lineas_noticias = []
    for n in noticias:
        partes = [f"- {n.get('titulo', '').strip()}"]
        if n.get("resumen"):
            partes.append(f"  resumen: {n['resumen'].strip()}")
        if n.get("enlace"):
            partes.append(f"  fuente: {n['enlace'].strip()}")
        lineas_noticias.append("\n".join(partes))
    noticias_txt = "\n".join(lineas_noticias)

    # Orden: la PLATAFORMA primero (aparece varias veces); los datos libres (ficha/noticias) al
    # final, para que su contenido no se reescanee en busca de otros marcadores.
    return (
        _plantilla_sugerencias()
        .replace("{{PLATAFORMA}}", nombre)
        .replace("{{LIMITE}}", limite_txt)
        .replace("{{FICHA}}", ficha_txt)
        .replace("{{NOTICIAS}}", noticias_txt)
    )


_TIPOS_SUGERENCIA = ("editorial", "limite")


def parsear_sugerencias(salida: str) -> list[dict[str, str]]:
    """Extrae las sugerencias del texto de `claude` (extractor compartido `json_llm`).

    Espera una LISTA JSON (cruda o en un bloque ```json```). Cada elemento valido aporta
    `{tipo, titulo, detalle}` (tipo cae a 'editorial' si no es valido). Si no hay JSON
    parseable pero hay texto, NO inventa estructura: devuelve []. El llamante decide el
    fallback. Nunca lanza.
    """
    datos = json_llm.extraer_lista(salida or "")
    if datos is None:
        return []
    salida_sug: list[dict[str, str]] = []
    for item in datos:
        if not isinstance(item, dict):
            continue
        titulo = str(item.get("titulo", "")).strip()
        detalle = str(item.get("detalle", "")).strip()
        if not titulo and not detalle:
            continue
        tipo = str(item.get("tipo", "editorial")).strip().lower()
        if tipo not in _TIPOS_SUGERENCIA:
            tipo = "editorial"
        salida_sug.append({"tipo": tipo, "titulo": titulo or "(sin título)", "detalle": detalle})
    return salida_sug


# --------------------------------------------------------------------------- #
# Ejecucion: encolar la generacion + sondear el resultado + persistir           #
# --------------------------------------------------------------------------- #


def _esperar_generacion(gen_id: str, *, timeout: float = _TIMEOUT_GENERACION_SEG) -> dict[str, Any] | None:
    """Sondea el registro de la generacion hasta que complete o falle. None si agota timeout.

    El worker (otro proceso) escribe el registro en el volumen `/data` compartido; aqui solo
    LEEMOS. Importacion diferida de `generaciones` para no acoplar el modulo al arranque.
    """
    from . import generaciones

    esperado = 0.0
    while esperado < timeout:
        gen = generaciones.obtener(gen_id)
        if gen is not None and gen.get("estado") != generaciones.ESTADO_EJECUTANDO:
            return gen
        time.sleep(_SONDEO_SEG)
        esperado += _SONDEO_SEG
    return None


def procesar_plataforma(plataforma: str, noticias: list[dict[str, Any]]) -> int:
    """Genera y persiste las sugerencias de UNA plataforma. Devuelve cuántas creó.

    Marca las noticias como `sugerida` solo si la generacion completa (con o sin sugerencias),
    para no re-procesarlas; si el worker falla/timeout, las deja para el proximo barrido.
    """
    from . import generaciones

    ficha_doc = libtexto.obtener(ficha_id_de(plataforma))
    ficha = ficha_doc.cuerpo if ficha_doc is not None else ""
    limite = limites_plataforma.limite_de(plataforma)
    prompt = componer_prompt(plataforma, noticias, ficha=ficha, limite=limite)

    procesar_spec = jobspec.construir_prompt_lib()
    gen = generar.lanzar(
        tipo="prompt",
        titulo=f"Sugerencias editoriales · {plataforma.capitalize()}",
        marca="",
        prompt=prompt,
        procesar=jobspec.reconstruir_procesar({"procesar": procesar_spec}),
        procesar_spec=procesar_spec,
        # Sugerencias = SALIDA ESTRUCTURADA (se parsea a filas `sugerencia_editorial`; el usuario
        # no ve la salida cruda) y es un barrido interno (sin prompt controlado por el usuario):
        # bajo riesgo. No se veta la web por-callsite; queda la veta global `Bash Write Edit`.
    )
    gen_final = _esperar_generacion(gen["id"])
    if gen_final is None or gen_final.get("estado") == generaciones.ESTADO_ERROR:
        _log.warning("Sugerencias %s: la generación no completó; se reintenta mañana.", plataforma)
        return 0

    sugerencias = parsear_sugerencias(gen_final.get("salida", ""))
    ids = [n["id"] for n in noticias]
    creadas = 0
    for s in sugerencias:
        ficha_id = ficha_id_de(plataforma) if s["tipo"] == "editorial" else ""
        repos.crear_sugerencia_editorial(
            plataforma=plataforma, tipo=s["tipo"], titulo=s["titulo"],
            detalle=s["detalle"], ficha_id=ficha_id, noticia_ids=ids,
        )
        creadas += 1
    # Procesadas: no se vuelven a sugerir (haya o no propuestas).
    for nid in ids:
        repos.marcar_noticia_algoritmo(nid, sugerida=True)
    return creadas


def ejecutar_barrido() -> dict[str, Any]:
    """Un barrido del digest: selecciona, procesa por plataforma y persiste. Best-effort.

    Devuelve `{plataformas, sugerencias}` (cuantas plataformas se procesaron y cuantas
    sugerencias se crearon). Si no hay noticias importantes pendientes, no llama a claude.
    """
    pendientes = repos.listar_noticias_algoritmo(solo_no_sugeridas=True, limite=300)
    grupos = seleccionar(pendientes, maximo=config.sugerencias_editoriales_max())
    total = 0
    for plataforma, noticias in grupos.items():
        try:
            total += procesar_plataforma(plataforma, noticias)
        except Exception:  # noqa: BLE001 -- una plataforma que falla no rompe el barrido
            _log.exception("Sugerencias editoriales: fallo procesando %s.", plataforma)
    if grupos:
        _log.info(
            "Sugerencias editoriales: %d plataforma(s) procesada(s) -> %d sugerencia(s).",
            len(grupos), total,
        )
    return {"plataformas": len(grupos), "sugerencias": total}


def _resumen_barrido(res: dict[str, Any]) -> str:
    """Resumen corto del digest editorial para el historial."""
    sugerencias = (res or {}).get("sugerencias", 0)
    plataformas = (res or {}).get("plataformas", 0)
    if not sugerencias:
        return "sin novedad"
    return f"{sugerencias} sugerencia(s) en {plataformas} plataforma(s)"


def _intervalo_segundos() -> float:
    """Intervalo del digest en segundos (a partir de `KENI_SUGERENCIAS_EDITORIALES_INTERVALO_HORAS`)."""
    return config.sugerencias_editoriales_intervalo_horas() * 3600.0


def iniciar_sugerencias_editoriales(intervalo_segundos: float | None = None) -> threading.Thread:
    """Arranca el hilo demonio del digest editorial (GATEADO EN VIVO).

    El hilo arranca SIEMPRE y comprueba `KENI_SUGERENCIAS_EDITORIALES` en cada ciclo (toggle
    en caliente). Def OFF. Solo ENCOLA generaciones (las ejecuta el worker); no publica nada.
    No lo arranca `crear_app` (los tests no levantan daemons), solo `__main__`/`daemons`.
    """
    intervalo = intervalo_segundos if intervalo_segundos is not None else _intervalo_segundos()

    def bucle() -> None:
        daemon_util.bucle_gateado(
            activo_fn=config.gate_maquina(config.sugerencias_editoriales_activo),
            intervalo_seg_fn=lambda: intervalo,
            sweep_fn=ejecutar_barrido,
            log=_log,
            resumen_fn=_resumen_barrido,
        )

    hilo = threading.Thread(target=bucle, name="sugerencias-editoriales-daemon", daemon=True)
    hilo.start()
    estado = "ACTIVO" if config.sugerencias_editoriales_activo() else "EN ESPERA (KENI_SUGERENCIAS_EDITORIALES off)"
    _log.info("Digest de sugerencias editoriales %s, cada %.0f h.", estado, intervalo / 3600.0)
    return hilo
