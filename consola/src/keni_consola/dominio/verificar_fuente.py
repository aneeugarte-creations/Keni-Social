"""Dominio QA EDITORIAL: parseo del informe de revisión de copy (PURO, sin HTTP).

Extraido de `api/verificar_fuente.py` para que el WORKER de generacion (#130 Fase 2) reconstruya
el post-procesado de un job de QA SIN importar de `api/` (corre fuera del proceso del back).
`api/verificar_fuente.py` reexporta estas funciones, asi que su contrato HTTP no cambia.

Frontera del producto: el QA SEÑALA (devuelve un informe con hallazgos), NO publica ni
reescribe. Aqui solo vive el PARSEO de la salida del prompt en ese informe estructurado.
"""

from __future__ import annotations

import json

from . import stream

# ETIQUETA DE ORIGEN del historial para las runs de QA (columna `origen` de
# `registrar_historial_prompt`), NO un id de prompt de la Biblioteca. Por eso NO lleva el
# prefijo `prompt/` ni se cataloga en `prompts_procesos.py` ni se resuelve con
# `libtexto.cuerpo_efectivo`: es un tipo INTERNO no editable. El prompt REAL de la QA de la
# fuente vive en la Biblioteca como `prompt/verificar` (lo resuelve `pipeline_contenido`).
# Es un valor ESTABLE: se persiste como `origen` en filas de historial en producción; cambiarlo
# partiría los datos históricos. Se conserva el nombre del constante por compatibilidad.
PROMPT_ID = "qa-editorial"

# Valores permitidos del informe estructurado (defensa: ignoramos cualquier otro).
_TIPOS = frozenset({"ortografia", "dato", "legal", "voz"})
_GRAVEDADES = frozenset({"error", "aviso"})

# Mapa del simbolo de semaforo (🟢/🟡/🔴) al verificacion interno estable, equivalente al
# ✅/⚠️/❌ del resto del producto (`stream._VEREDICTO_POR_SIMBOLO`).
_VERIFICACION_POR_SEMAFORO = {"🟢": "listo", "🟡": "revisar", "🔴": "no_publicar"}

# Tope defensivo de hallazgos que devolvemos (evita una salida abusiva del modelo).
_MAX_HALLAZGOS = 200


def _verificacion_de_texto(texto: str) -> str:
    """Deriva el verificacion del informe: primero el semaforo 🟢/🟡/🔴, luego ✅/⚠️/❌.

    El prompt abre con la linea de semaforo (🟢/🟡/🔴); si por lo que sea saliera con los
    simbolos clasicos, `stream.derivar_verdicto` los cubre. Devuelve "" si no hay ninguno.
    """
    for linea in texto.splitlines():
        if not linea.strip():
            continue
        for simbolo, valor in _VERIFICACION_POR_SEMAFORO.items():
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
    y mapea `verificación`/`resumen`/`hallazgos`. El `informe_texto` es el documento legible
    SIN ese bloque json y sin emojis del cuerpo (el verificacion se deriva ANTES de limpiar, asi
    no se pierde el simbolo). Degradacion robusta: si no hay JSON valido, `hallazgos=[]` y el
    informe queda como el texto completo (el QA nunca se rompe por un formato inesperado).

    Devuelve `{verificacion, resumen, hallazgos: [...], informe_texto}`.
    """
    salida = salida or ""
    verificacion = _verificacion_de_texto(salida)

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
        # El verificacion del JSON (semaforo) tiene prioridad si lo trae; si no, el de la 1a linea.
        v = datos.get("veredicto")
        if isinstance(v, str):
            for simbolo, valor in _VERIFICACION_POR_SEMAFORO.items():
                if simbolo in v:
                    verificacion = valor
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
        "verificacion_fuente": verificacion,
        "resumen": resumen,
        "hallazgos": hallazgos,
        "informe_texto": stream.quitar_emojis(texto_sin_json).strip(),
    }


# --------------------------------------------------------------------------- #
# QA DE LA FUENTE (pre-copy, rediseño QPC): verificación PERMISIVA de la NOTA de origen #
# --------------------------------------------------------------------------- #
# El QA se movió a ANTES del copy y por PIEZA (tema/fuente), no por plataforma: verificar la nota
# de origen antes de gastar tokens generando copy. Es PERMISIVO y devuelve un verificación
# ESTRUCTURADO con SOLO dos salidas: `no_verificado` (nada de peso en contra: seguir, la pieza
# llevará ⚠️) o `problema` (algo de peso: NO generar copy, marcar ❗ con los hallazgos). Por
# defecto `no_verificado` cuando hay duda (permisivo).

VERIFICACION_NO_VERIFICADO = "no_verificado"
VERIFICACION_PROBLEMA = "problema"

# Mapa del verificación editorial clásico (semáforo) al verificación de FUENTE: solo el rojo
# (`no_publicar`) cuenta como `problema`; verde/amarillo (o sin verificación) -> `no_verificado`
# (permisivo: ante la duda, deja pasar). Cubre que el prompt use el lenguaje de semáforo.
_FUENTE_PROBLEMA_DESDE = frozenset({"no_publicar"})

# CONTRATO del prompt de fuente (`prompt/verificar`): el campo JSON `veredicto` va en slug
# ASCII ("apta" | "problema").
_FUENTE_SLUG_APTA = "apta"
_FUENTE_SLUG_PROBLEMA = "problema"


def _slug_verificacion_fuente(salida: str) -> str:
    """Verificación del ÚLTIMO bloque ```json de la QA de FUENTE: "apta"/"problema" o "".

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


def parsear_verificacion_fuente(salida: str) -> dict[str, object]:
    """Parsea la salida de la QA de la FUENTE en un verificación ESTRUCTURADO permisivo.

    Reusa `parsear_informe` (mismo formato ```json con `verificación`/`resumen`/`hallazgos`), pero
    COLAPSA el verificación a dos valores de FUENTE:
      - `problema` si el JSON dice "problema" (slug del contrato) o 🔴 legado / el informe
        deriva `no_publicar`, O trae algún hallazgo de gravedad `error` (algo de peso),
      - `no_verificado` en cualquier otro caso (incluido sin verificación / formato inesperado /
        valor basura): PERMISIVO por diseño (ante la duda, deja pasar y la pieza llevará ⚠️).

    Devuelve `{verificacion, resumen, hallazgos: [...], informe_texto}` (mismas claves que
    `parsear_informe`, con `verificacion` ya colapsado a `no_verificado`/`problema`). PURO.
    """
    informe = parsear_informe(salida)
    crudo = str(informe.get("verificacion_fuente") or "")
    hallazgos = informe.get("hallazgos")
    hay_error = isinstance(hallazgos, list) and any(
        isinstance(h, dict) and h.get("gravedad") == "error" for h in hallazgos
    )
    slug = _slug_verificacion_fuente(salida)
    if slug == _FUENTE_SLUG_PROBLEMA:
        es_problema = True
    elif slug == _FUENTE_SLUG_APTA:
        # El JSON manda sobre la línea de semáforo; un hallazgo `error` sigue pesando.
        es_problema = hay_error
    else:
        es_problema = crudo in _FUENTE_PROBLEMA_DESDE or hay_error
    informe["verificacion_fuente"] = VERIFICACION_PROBLEMA if es_problema else VERIFICACION_NO_VERIFICADO
    return informe


def serializar_hallazgos(informe: dict[str, object]) -> str:
    """Serializa los hallazgos (+resumen) del informe de fuente a JSON para persistir en el tema.

    Compacto y autocontenido (lo lee la UI/API tal cual): `{resumen, hallazgos:[...]}`. "" si no
    hay nada que guardar (verificacion `no_verificado` sin hallazgos), para no engordar el registro.
    """
    hallazgos = informe.get("hallazgos") or []
    resumen = str(informe.get("resumen") or "")
    if not hallazgos and not resumen:
        return ""
    return json.dumps({"resumen": resumen, "hallazgos": hallazgos}, ensure_ascii=False)


def construir_procesar_verificacion_fuente(  # noqa: ANN201
    marca: str,
    titulo: str,
    autor: dict[str, str] | None = None,
    *,
    cluster_id: str = "",
):
    """Callback de post-procesado de la QA de la FUENTE: persiste el verificación donde toque.

    Parsea el verificación estructurado (`parsear_verificacion_fuente`), registra el informe en el
    historial (trazabilidad, sin piezas: esto SEÑALA, no publica) y ESCRIBE el verificación +
    hallazgos en el destino:

    El verificación se sella en la HISTORIA (`cluster_id`, ADR 0011 F3): QA sobre la fuente ANTES de
    materializar contenido (`repos.marcar_cluster_verificacion`); la admisión solo promueve las verificadas.
    NO encadena copy (la pieza aún no existe; nace en la admisión).

    Devuelve el verificación/informe para el sondeo del frontend. Se reconstruye igual en el worker
    (vía spec).
    """
    from .. import repos

    def procesar(salida: str, metricas: stream.MetricasRun | None) -> dict[str, object]:
        informe = parsear_verificacion_fuente(salida)
        historial_id = repos.registrar_historial_prompt(
            PROMPT_ID, marca, str(informe.get("informe_texto") or ""), piezas=[], titulo=titulo,
            metricas=stream.metricas_a_dict(metricas), autor=autor,
        )
        verificacion = str(informe.get("verificacion_fuente") or VERIFICACION_NO_VERIFICADO)
        # QA sobre la HISTORIA (cluster, pre-admisión, ADR 0011 F3): el verificación vive en el
        # cluster. La admisión del barrido de investigación promueve las `no_verificado` (hereda
        # el verificación al contenido) y deja fuera las `problema`. NO se encadena copy aquí (la
        # pieza aún no existe; nace en la admisión).
        if cluster_id:
            repos.marcar_cluster_verificacion(cluster_id, verificacion, serializar_hallazgos(informe))
        return {
            "informe": informe,
            "verificacion_fuente": verificacion,
            "historial_id": historial_id,
            "piezas": [],
            "publicaciones": [],
        }

    return procesar
