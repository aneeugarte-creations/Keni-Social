"""Investigación de una idea EVERGREEN aprobada → MATERIAL VERIFICADO → tema del pipeline.

Espejo del motor de noticias: al APROBAR una idea evergreen se lanza un `claude -p` con web
(`prompt/investigar-evergreen`) que investiga el tema y devuelve `{viable, material, fuentes}`. Si
es viable, el post-procesado crea un TEMA del pipeline (`origen='pipeline'`, `flujo='evergreen'`,
verificación `verificado` + el material en `copy_pendiente`) que PRODUCCIÓN recoge igual que una
historia de noticias (decisor→redactar→ilustrar/stock→revisión), sin tocar el seam de producción.
Si no es viable, la idea vuelve a `aprobada` (reintentable) y no nace ningún tema.
"""

from __future__ import annotations

import json
from typing import Any

from .. import config, generaciones, libprompts, marcas, redes, repos
from ..dominio import generar as gen_dom
from ..dominio import jobspec
from ..estados import ESTADO_EVERGREEN_APROBADA, ESTADO_EVERGREEN_GENERADA
from ..tiempo import hoy_utc
from ._admitir import _copy_pendiente_de
from ._comun import (
    _FORMATO_PIPELINE,
    ORIGEN_PIPELINE,
    TIPO_PIPELINE,
    VERIFICACION_VERIFICADO,
    _log,
)

__all__ = [
    "lanzar_investigar_idea",
    "construir_procesar_investigar_evergreen",
]

# id del prompt EDITABLE de investigación (cuerpo base en la inicial del paquete). Cierra con un
# bloque ```json``` `{viable, material, fuentes}` que el post-procesado parsea.
PROMPT_INVESTIGAR_ID = "prompt/investigar-evergreen"


def _endurecer_investigar() -> dict[str, Any] | None:
    """Overrides `endurecer` de la investigación: mismo runtime fuerte que la verificación de la fuente.

    Investigar es un paso FUERTE con web (abre fuentes y corrobora): corre con los knobs de
    `config.verificacion_fuente_*` (modelo Opus / esfuerzo alto / timeout holgado). Se omiten las
    claves vacías (cada una cae a su global). None si no hay ningún override.
    """
    overrides: dict[str, Any] = {}
    modelo = config.verificacion_fuente_modelo()
    if modelo:
        overrides["modelo"] = modelo
    esfuerzo = config.verificacion_fuente_esfuerzo()
    if esfuerzo:
        overrides["esfuerzo"] = esfuerzo
    timeout = config.verificacion_fuente_timeout()
    if timeout > 0:
        overrides["timeout"] = timeout
    return overrides or None


def _nota_de_idea(titulo: str, descripcion: str) -> str:
    """Nota de partida de la investigación: título + descripción de la idea, recortada al tope."""
    return "\n\n".join(p for p in (titulo, descripcion) if p)[: gen_dom.MAX_TEXTO]


def _contexto_investigar(nota: str) -> str:
    """Bloque de contexto de la investigación: la idea evergreen aprobada a investigar."""
    return "Idea evergreen aprobada a investigar:\n\n" + nota


def lanzar_investigar_idea(
    idea: dict[str, Any], *, autor: dict[str, str] | None
) -> dict[str, Any] | None:
    """Lanza la investigación (`claude -p` con web) de una idea evergreen aprobada vía la cola.

    Compone el prompt (`prompt/investigar-evergreen` + editorial de la marca, pipeline `verificar`)
    con la idea como CONTEXTO y lo encola con runtime fuerte (`_endurecer_investigar`). ASÍNCRONO:
    devuelve la generación para sondeo. Al completar, su post-procesado crea el tema (si viable) o
    revierte la idea a `aprobada`. None si no se puede lanzar (sin marca válida / sin prompt).
    `ColaLlenaError` se PROPAGA al llamante. Si el job termina en error, `al_fallar` revierte la idea.
    """
    idea_id = (idea.get("id") or "").strip()
    if not idea_id:
        return None
    marca = (idea.get("marca") or "").strip()
    if not marca or not marcas.es_marca(marca):
        return None
    titulo = (idea.get("titulo") or "").strip()
    descripcion = (idea.get("descripcion") or "").strip()
    nota = _nota_de_idea(titulo, descripcion)
    if not nota.strip():
        return None

    cuerpo = libprompts.cuerpo_efectivo(PROMPT_INVESTIGAR_ID)
    if not cuerpo:
        return None  # sin prompt de investigación no hay paso: la idea queda aprobada (reintentable).

    prompt = gen_dom.componer(
        cuerpo,
        libprompts.editoriales_de_marca(marca, pipeline="verificar"),
        _contexto_investigar(nota),
    )
    return gen_dom.lanzar(
        tipo=TIPO_PIPELINE,
        titulo=f"Investigar · {titulo}",
        marca=marca,
        prompt=prompt,
        publicacion_id="",
        clave_idem=generaciones.clave_idempotencia(
            (autor or {}).get("id", ""), TIPO_PIPELINE, marca, "investigar-evergreen", idea_id
        ),
        procesar=construir_procesar_investigar_evergreen(idea_id, marca, titulo, autor),
        procesar_spec=jobspec.construir_investigar_evergreen(
            idea_id=idea_id, marca=marca, titulo=titulo, autor=autor
        ),
        autor=autor,
        endurecer=_endurecer_investigar(),
        # Frontera ADR 0011: investigar es INVESTIGACION (motor de evergreen), no producción.
        proceso=generaciones.PROCESO_INVESTIGACION,
        al_fallar={"revertir_idea_evergreen": idea_id},
    )


def _parsear(salida: str) -> dict[str, Any]:
    """Parsea el contrato `{viable, material, fuentes}` de la salida del investigador. ROBUSTO.

    Busca el ÚLTIMO bloque ```json … ``` y, si no lo hay, el último objeto JSON de la salida. Ante
    cualquier fallo (sin JSON, JSON inválido, forma inesperada) devuelve `viable=False` (FAIL-CLOSED:
    sin material verificado no se produce nada). `fuentes` se normaliza a lista de strings.
    """
    crudo = _extraer_json(salida)
    if not crudo:
        return {"viable": False, "material": "", "fuentes": []}
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {"viable": False, "material": "", "fuentes": []}
    if not isinstance(datos, dict):
        return {"viable": False, "material": "", "fuentes": []}
    material = datos.get("material")
    material = material.strip() if isinstance(material, str) else ""
    fuentes = [
        str(f).strip() for f in (datos.get("fuentes") or []) if isinstance(f, (str,)) and str(f).strip()
    ]
    return {"viable": bool(datos.get("viable")), "material": material, "fuentes": fuentes}


def _extraer_json(salida: str) -> str:
    """Extrae el JSON crudo de la salida: último bloque cercado ```json…``` o último objeto `{…}`. "" si no hay."""
    import re

    texto = salida or ""
    cercados = re.findall(r"```json\s*(.*?)\s*```", texto, re.DOTALL | re.IGNORECASE)
    if cercados:
        return cercados[-1].strip()
    # Sin cerca: el último objeto JSON balanceado del texto (de la última `{` que cierre bien).
    inicio = texto.rfind("{")
    while inicio != -1:
        profundidad = 0
        for i in range(inicio, len(texto)):
            if texto[i] == "{":
                profundidad += 1
            elif texto[i] == "}":
                profundidad -= 1
                if profundidad == 0:
                    return texto[inicio : i + 1].strip()
        inicio = texto.rfind("{", 0, inicio)
    return ""


def construir_procesar_investigar_evergreen(  # noqa: ANN201
    idea_id: str, marca: str, titulo: str, autor: dict[str, str] | None
):
    """Callback de post-procesado de la investigación: crea el tema (si viable) o revierte la idea.

    Parsea `{viable, material, fuentes}`. Si NO es viable o `material` está vacío: no crea tema y
    revierte la idea a `aprobada` (reintentable). Si es viable: crea un TEMA del pipeline
    (`origen='pipeline'`, `flujo='evergreen'`, verificación `verificado`, el material en `descripcion`
    y en `copy_pendiente`) que producción recoge igual que una historia verificada, enlaza la idea
    (`generada` + `publicacion_id`) y registra el material en el historial. Se reconstruye igual en
    el worker (vía spec). Devuelve `{viable, publicacion_id?, piezas: []}` para el sondeo.
    """

    def procesar(salida: str, _metricas: object) -> dict[str, object]:
        datos = _parsear(salida)
        material = str(datos.get("material") or "")
        if not datos.get("viable") or not material.strip():
            # Sin material verificado: nada se produce; la idea vuelve a `aprobada` (reintentable).
            try:
                repos.actualizar_evergreen_idea(idea_id, {"estado": ESTADO_EVERGREEN_APROBADA})
            except Exception:  # noqa: BLE001 -- best-effort; la idea ya estaba aprobada al lanzar
                _log.warning("evergreen: no se pudo revertir la idea %s tras no-viable", idea_id, exc_info=True)
            return {"viable": False, "piezas": []}

        fuentes = list(datos.get("fuentes") or [])
        redes_ids = list(redes.redes_de_formato(_FORMATO_PIPELINE))
        # El material es la NOTA de origen del tema: se serializa en `copy_pendiente` (sin RSS/fotos)
        # igual que una historia, para que la fase de producción lo redacte sin re-investigar.
        trabajo = {"fuente": {}, "item": {"clave": ""}, "imagen": "", "fotos_notas": [], "n_notas": 0}
        tema = repos.crear_publicacion(
            clase="contenido",
            flujo="evergreen",
            titulo=(titulo or "Evergreen")[:300],
            descripcion=material[:5000],
            marca=marca,
            origen=ORIGEN_PIPELINE,
            formato=_FORMATO_PIPELINE,
            fecha_objetivo=hoy_utc().isoformat(),
            copy_pendiente=_copy_pendiente_de(trabajo, material, redes_ids),
            # MATERIAL VERIFICADO: el tema nace `verificado` para que producción lo recoja directo.
            verificacion_fuente=VERIFICACION_VERIFICADO,
            verificar_hallazgos=json.dumps({"fuentes": fuentes}, ensure_ascii=False),
        )
        try:
            repos.actualizar_evergreen_idea(
                idea_id, {"estado": ESTADO_EVERGREEN_GENERADA, "publicacion_id": tema["id"]}
            )
        except Exception:  # noqa: BLE001 -- el tema ya existe; el enlace de la idea es trazabilidad
            _log.warning("evergreen: no se pudo enlazar la idea %s a su tema", idea_id, exc_info=True)
        try:
            repos.registrar_historial_prompt(
                PROMPT_INVESTIGAR_ID, marca, material, piezas=[], titulo=titulo, autor=autor
            )
        except Exception:  # noqa: BLE001 -- el historial es trazabilidad, nunca rompe el post-procesado
            pass
        return {"viable": True, "publicacion_id": tema["id"], "piezas": []}

    return procesar
