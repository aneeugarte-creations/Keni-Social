"""Dominio QA EDITORIAL: parseo del informe de revisión de copy (PURO, sin HTTP).

Extraido de `api/qa_editorial.py` para que el WORKER de generacion (#130 Fase 2) reconstruya
el post-procesado de un job de QA SIN importar de `api/` (corre fuera del proceso del back).
`api/qa_editorial.py` reexporta estas funciones, asi que su contrato HTTP no cambia.

Frontera del producto: el QA SEÑALA (devuelve un informe con hallazgos), NO publica ni
reescribe. Aqui solo vive el PARSEO de la salida de la skill en ese informe estructurado.
"""

from __future__ import annotations

import json

from . import stream

# Id de la skill que hace el QA (vive en skills-copy/.claude/skills/).
SKILL_ID = "qa-editorial"

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

    La skill abre con la linea de semaforo (🟢/🟡/🔴); si por lo que sea saliera con los
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
    """Normaliza un hallazgo del JSON de la skill o devuelve None si no es usable.

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
    """Parsea la salida de la skill en un INFORME estructurado para la UI.

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


def construir_procesar_qa(marca: str, titulo: str, autor: dict[str, str] | None = None):  # noqa: ANN201
    """Callback de post-procesado del QA: parsea el informe y registra el historial (sin piezas).

    NO auto-crea publicaciones (esto SEÑALA, no publica). Devuelve `{informe, verdicto,
    historial_id, piezas: [], publicaciones: []}` para el sondeo del frontend. `autor`
    (atribucion por usuario, #130 Fase 1) se propaga al historial. Lo usan tanto el lanzador
    in-proceso (tests) como el worker (reconstruido desde el spec).
    """
    from .. import repos

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        informe = parsear_informe(salida)
        historial_id = repos.registrar_historial_skill(
            SKILL_ID, marca, informe["informe_texto"], piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        return {
            "informe": informe,
            "verdicto": informe["verdicto"],
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }

    return procesar
