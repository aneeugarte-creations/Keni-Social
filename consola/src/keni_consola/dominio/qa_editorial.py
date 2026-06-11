"""Dominio QA EDITORIAL: parseo del informe de revisión de copy (PURO, sin HTTP).

Extraido de `api/qa_editorial.py` para que el WORKER de generacion (#130 Fase 2) reconstruya
el post-procesado de un job de QA SIN importar de `api/` (corre fuera del proceso del back).
`api/qa_editorial.py` reexporta estas funciones, asi que su contrato HTTP no cambia.

Frontera del producto: el QA SEÑALA (devuelve un informe con hallazgos), NO publica ni
reescribe. Aqui solo vive el PARSEO de la salida del prompt en ese informe estructurado.
"""

from __future__ import annotations

import json

from . import stream

# Id del prompt que hace el QA editorial.
PROMPT_ID = "qa-editorial"

# Valores permitidos del informe estructurado (defensa: ignoramos cualquier otro).
_TIPOS = frozenset({"ortografia", "dato", "legal", "voz"})
_GRAVEDADES = frozenset({"error", "aviso"})

# Mapa del simbolo de semaforo (🟢/🟡/🔴) al verdicto interno estable, equivalente al
# ✅/⚠️/❌ del resto del producto (`stream._VEREDICTO_POR_SIMBOLO`).
_VERDICTO_POR_SEMAFORO = {"🟢": "listo", "🟡": "revisar", "🔴": "no_publicar"}

# Tope defensivo de hallazgos que devolvemos (evita una salida abusiva del modelo).
_MAX_HALLAZGOS = 200


def _verdicto_de_texto(texto: str) -> str:
    """Deriva el verdicto del informe: primero el semaforo 🟢/🟡/🔴, luego ✅/⚠️/❌.

    El prompt abre con la linea de semaforo (🟢/🟡/🔴); si por lo que sea saliera con los
    simbolos clasicos, `stream.derivar_verdicto` los cubre. Devuelve "" si no hay ninguno.
    """
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        for simbolo, valor in _VERDICTO_POR_SEMAFORO.items():
            if simbolo in linea:
                return valor
        return stream.derivar_verdicto(texto)
    return ""


def _hallazgo_limpio(crudo: object) -> dict[str, object] | None:
    """Normaliza un hallazgo del JSON del prompt o devuelve None si no es usable.

    Acota `tipo`/`gravedad` a los valores permitidos (un `tipo` desconocido se descarta;
    una `gravedad` desconocida cae a "aviso", la menos alarmante). Recorta los textos a un
    tope razonable. `no_verificable` solo es True para hallazgos de tipo `dato`.
    """
    if not isinstance(crudo, dict):
        return None
    tipo = crudo.get("tipo")
    if not isinstance(tipo, str) or tipo not in _TIPOS:
        return None
    gravedad = crudo.get("gravedad")
    if not isinstance(gravedad, str) or gravedad not in _GRAVEDADES:
        gravedad = "aviso"

    def _texto(clave: str) -> str:
        valor = crudo.get(clave)
        return valor.strip()[:1000] if isinstance(valor, str) else ""

    no_verificable = bool(crudo.get("no_verificable")) and tipo == "dato"
    return {
        "tipo": tipo,
        "gravedad": gravedad,
        "fragmento": _texto("fragmento"),
        "explicacion": _texto("explicacion"),
        "sugerencia": _texto("sugerencia"),
        "no_verificable": no_verificable,
    }


def parsear_informe(salida: str) -> dict[str, object]:
    """Parsea la salida del prompt en un INFORME estructurado para la UI.

    Localiza el ULTIMO bloque ```json cercado (igual criterio que `stream.parsear_salida`)
    y mapea `veredicto`/`resumen`/`hallazgos`. El `informe_texto` es el documento legible
    SIN ese bloque json y sin emojis del cuerpo (el verdicto se deriva ANTES de limpiar, asi
    no se pierde el simbolo). Degradacion robusta: si no hay JSON valido, `hallazgos=[]` y el
    informe queda como el texto completo (el QA nunca se rompe por un formato inesperado).

    Devuelve `{verdicto, resumen, hallazgos: [...], informe_texto}`.
    """
    salida = salida or ""
    verdicto = _verdicto_de_texto(salida)

    coincidencias = list(stream._RE_BLOQUE_JSON.finditer(salida))
    datos: object = None
    texto_sin_json = salida
    if coincidencias:
        ultima = coincidencias[-1]
        try:
            datos = json.loads(ultima.group(1))
        except (json.JSONDecodeError, ValueError):
            datos = None
        else:
            texto_sin_json = salida[: ultima.start()] + salida[ultima.end():]

    hallazgos: list[dict[str, object]] = []
    resumen = ""
    if isinstance(datos, dict):
        # El verdicto del JSON (semaforo) tiene prioridad si lo trae; si no, el de la 1a linea.
        v = datos.get("veredicto")
        if isinstance(v, str):
            for simbolo, valor in _VERDICTO_POR_SEMAFORO.items():
                if simbolo in v:
                    verdicto = valor
                    break
        r = datos.get("resumen")
        if isinstance(r, str):
            resumen = r.strip()[:500]
        crudos = datos.get("hallazgos")
        if isinstance(crudos, list):
            for cr in crudos[:_MAX_HALLAZGOS]:
                limpio = _hallazgo_limpio(cr)
                if limpio is not None:
                    hallazgos.append(limpio)

    return {
        "verdicto": verdicto,
        "resumen": resumen,
        "hallazgos": hallazgos,
        "informe_texto": stream.quitar_emojis(texto_sin_json).strip(),
    }


# --------------------------------------------------------------------------- #
# QA DE LA FUENTE (pre-copy, rediseño QPC): criba PERMISIVA de la NOTA de origen #
# --------------------------------------------------------------------------- #
# El QA se movió a ANTES del copy y por PIEZA (tema/fuente), no por plataforma: cribar la nota
# de origen antes de gastar tokens generando copy. Es PERMISIVO y devuelve un veredicto
# ESTRUCTURADO con SOLO dos salidas: `no_verificado` (nada de peso en contra: seguir, la pieza
# llevará ⚠️) o `problema` (algo de peso: NO generar copy, marcar ❗ con los hallazgos). Por
# defecto `no_verificado` cuando hay duda (permisivo).

VERDICTO_NO_VERIFICADO = "no_verificado"
VERDICTO_PROBLEMA = "problema"

# Mapa del veredicto editorial clásico (semáforo) al veredicto de FUENTE: solo el rojo
# (`no_publicar`) cuenta como `problema`; verde/amarillo (o sin veredicto) -> `no_verificado`
# (permisivo: ante la duda, deja pasar). Cubre que el prompt use el lenguaje de semáforo.
_FUENTE_PROBLEMA_DESDE = frozenset({"no_publicar"})

# CONTRATO del prompt de fuente (`prompt/validacion`): el campo JSON `veredicto` va en slug
# ASCII ("apta" | "problema"). Los emojis 🟢/🔴 se aceptan como LEGADO (piezas en vuelo o un
# prompt editado en producción aún viejo); el semáforo visual queda para la línea humana.
_FUENTE_SLUG_APTA = "apta"
_FUENTE_SLUG_PROBLEMA = "problema"


def _slug_veredicto_fuente(salida: str) -> str:
    """Veredicto del ÚLTIMO bloque ```json de la QA de FUENTE: "apta"/"problema" o "".

    Acepta el slug ASCII del contrato y el emoji legado 🟢/🔴. Cualquier otro valor (o sin
    bloque/clave) devuelve "" y el llamante cae al camino permisivo. PURO, nunca lanza.
    """
    coincidencias = list(stream._RE_BLOQUE_JSON.finditer(salida or ""))
    if not coincidencias:
        return ""
    try:
        datos = json.loads(coincidencias[-1].group(1))
    except (json.JSONDecodeError, ValueError):
        return ""
    if not isinstance(datos, dict):
        return ""
    v = datos.get("veredicto")
    if not isinstance(v, str):
        return ""
    if "🔴" in v:
        return _FUENTE_SLUG_PROBLEMA
    if "🟢" in v:
        return _FUENTE_SLUG_APTA
    v = v.strip().lower()
    return v if v in (_FUENTE_SLUG_APTA, _FUENTE_SLUG_PROBLEMA) else ""


def parsear_verdicto_fuente(salida: str) -> dict[str, object]:
    """Parsea la salida de la QA de la FUENTE en un veredicto ESTRUCTURADO permisivo.

    Reusa `parsear_informe` (mismo formato ```json con `veredicto`/`resumen`/`hallazgos`), pero
    COLAPSA el veredicto a dos valores de FUENTE:
      - `problema` si el JSON dice "problema" (slug del contrato) o 🔴 legado / el informe
        deriva `no_publicar`, O trae algún hallazgo de gravedad `error` (algo de peso),
      - `no_verificado` en cualquier otro caso (incluido sin veredicto / formato inesperado /
        valor basura): PERMISIVO por diseño (ante la duda, deja pasar y la pieza llevará ⚠️).

    Devuelve `{verdicto, resumen, hallazgos: [...], informe_texto}` (mismas claves que
    `parsear_informe`, con `verdicto` ya colapsado a `no_verificado`/`problema`). PURO.
    """
    informe = parsear_informe(salida)
    crudo = str(informe.get("verdicto") or "")
    hallazgos = informe.get("hallazgos")
    hay_error = isinstance(hallazgos, list) and any(
        isinstance(h, dict) and h.get("gravedad") == "error" for h in hallazgos
    )
    slug = _slug_veredicto_fuente(salida)
    if slug == _FUENTE_SLUG_PROBLEMA:
        es_problema = True
    elif slug == _FUENTE_SLUG_APTA:
        # El JSON manda sobre la línea de semáforo; un hallazgo `error` sigue pesando.
        es_problema = hay_error
    else:
        es_problema = crudo in _FUENTE_PROBLEMA_DESDE or hay_error
    informe["verdicto"] = VERDICTO_PROBLEMA if es_problema else VERDICTO_NO_VERIFICADO
    return informe


def serializar_hallazgos(informe: dict[str, object]) -> str:
    """Serializa los hallazgos (+resumen) del informe de fuente a JSON para persistir en el tema.

    Compacto y autocontenido (lo lee la UI/API tal cual): `{resumen, hallazgos:[...]}`. "" si no
    hay nada que guardar (verdicto `no_verificado` sin hallazgos), para no engordar el registro.
    """
    hallazgos = informe.get("hallazgos") or []
    resumen = str(informe.get("resumen") or "")
    if not hallazgos and not resumen:
        return ""
    return json.dumps({"resumen": resumen, "hallazgos": hallazgos}, ensure_ascii=False)


def construir_procesar_qa_fuente(  # noqa: ANN201
    marca: str,
    titulo: str,
    autor: dict[str, str] | None = None,
    *,
    contenido_id: str = "",
):
    """Callback de post-procesado de la QA de la FUENTE: persiste el veredicto en el TEMA.

    Parsea el veredicto estructurado (`parsear_verdicto_fuente`), registra el informe en el
    historial (trazabilidad, sin piezas: esto SEÑALA, no publica) y ESCRIBE el veredicto +
    hallazgos sobre el `contenido` (tema) de origen (`repos.actualizar_contenido`), para que la
    fase CD seleccione los `no_verificado` y la UI muestre ⚠️/❗ + hallazgos. Devuelve el
    veredicto/informe para el sondeo del frontend. Se reconstruye igual en el worker (vía spec).
    """
    from .. import repos

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        informe = parsear_verdicto_fuente(salida)
        historial_id = repos.registrar_historial_prompt(
            PROMPT_ID, marca, str(informe.get("informe_texto") or ""), piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        verdicto = str(informe.get("verdicto") or VERDICTO_NO_VERIFICADO)
        if contenido_id:
            repos.actualizar_contenido(
                contenido_id,
                {"qa_veredicto": verdicto, "qa_hallazgos": serializar_hallazgos(informe)},
            )
            # ENCADENADO QA->copy (por eventos): si la fuente paso la criba, dispara el copy
            # de ESE tema YA, sin esperar al siguiente barrido de 20 min (el barrido queda de
            # red de seguridad: recoge lo que el encadenado pierda, p. ej. con la cola llena).
            # Respeta los mismos gates que la fase CD (toggle copy global + por marca) dentro
            # de `encadenar_copy_tras_qa`. Best-effort: nunca rompe el post-procesado de QA.
            if verdicto != VERDICTO_PROBLEMA:
                try:
                    from ..pipeline_contenido import encadenar_copy_tras_qa

                    encadenar_copy_tras_qa(contenido_id, autor=autor)
                except Exception:  # noqa: BLE001 -- el barrido lo recogera
                    import logging

                    logging.getLogger("keni_consola.qa_editorial").warning(
                        "QA fuente: fallo el encadenado a copy (%s)", contenido_id, exc_info=True
                    )
        return {
            "informe": informe,
            "verdicto": verdicto,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }

    return procesar
