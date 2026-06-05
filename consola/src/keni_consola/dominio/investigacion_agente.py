"""Agente de investigacion: corre un brief y devuelve candidatos fechados (Ola 6).

PATRON
======
Espeja `insumos_parse._ejecutar_claude_json` y `importador_calendario._ejecutar_claude_json`:
subproceso SINCRONO `claude -p <prompt> --output-format json [--model X]` con timeout alto
(300 s para que el agente pueda hacer busquedas web). Ejecutor INYECTABLE (tests pasan un
fake sin tocar red ni binario). Extraccion tolerante del JSON de respuesta.

CONTRATO
========
`correr_brief(brief, *, fecha, ejecutor=None) -> tuple[list[dict], list[dict]]`
  - Construye un prompt de investigacion web y devuelve (candidatos, errores).
  - Cada candidato es un dict {titulo, resumen, por_que, fuente, enlace, idioma, marca}.
  - La marca del brief se normaliza nombre->id para que el llamante pueda insertar
    directamente en `inv_candidato`.
  - El ejecutor por defecto llama al binario `claude`; en tests se inyecta uno falso.
  - El llamante SIEMPRE corre esto en un threadpool (no bloquea el event loop de Starlette).
  - Los candidatos proponen; NUNCA crean tablero ni publican.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

from .. import config, marcas

_log = logging.getLogger("keni_consola.dominio.investigacion_agente")

# Wall-timeout del subproceso `claude` para investigacion. Mas alto que insumos (180 s)
# porque el agente puede necesitar hacer busquedas web y esperar resultados.
_CLAUDE_TIMEOUT_S = 300

# Tipo del ejecutor inyectable: (prompt) -> texto final.
# Diferencia con insumos: no necesitamos `add-dir` (no hay archivo que leer).
Ejecutor = Callable[[str], str]

# Normalizacion de marcas: id canonico y etiqueta -> id.
_MARCAS_IDS = {m[0] for m in marcas.opciones()}
_MARCAS_POR_ETIQUETA: dict[str, str] = {
    etiqueta.lower(): id_ for id_, etiqueta in marcas.opciones()
}


def _normalizar_marca(valor: Any) -> str:
    """Nombre/etiqueta/id de marca -> id canonico, o '' si no se reconoce."""
    if not isinstance(valor, str):
        return ""
    s = valor.strip()
    if not s:
        return ""
    if s in _MARCAS_IDS:
        return s
    return _MARCAS_POR_ETIQUETA.get(s.lower(), "")


def _ejecutar_claude_json(prompt: str) -> str:
    """Corre `claude -p <prompt> --output-format json [--model X]` y devuelve el texto final.

    Sincrono, acotado por `_CLAUDE_TIMEOUT_S`. Hereda el entorno (incluido
    `CLAUDE_CODE_OAUTH_TOKEN`). No usar en tests: se inyecta un ejecutor falso.
    """
    from . import stream  # import perezoso: evita ciclo dominio<->dominio

    if shutil.which("claude") is None:
        raise RuntimeError("El asistente (claude) no esta disponible en el servidor.")
    modelo = config.insumos_modelo()
    argv: list[str] = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        *stream.arg_skip_permisos(),
    ]
    if modelo:
        argv += ["--model", modelo]
    res = subprocess.run(  # noqa: S603 -- argv fijo, sin shell; prompt va como argumento
        argv,
        capture_output=True,
        text=True,
        timeout=_CLAUDE_TIMEOUT_S,
        check=False,
        env=dict(os.environ),
    )
    if res.returncode != 0:
        raise RuntimeError((res.stderr or "claude termino con error").strip()[:300])
    try:
        envelope = json.loads(res.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return res.stdout or ""
    if isinstance(envelope, dict):
        return str(envelope.get("result") or "")
    return res.stdout or ""


def _extraer_candidatos(texto: str) -> list[Any] | None:
    """Extrae la lista de candidatos del texto de Claude. Tolerante a fences y wrappers."""
    if not texto or not texto.strip():
        return None
    s = texto.strip()
    # Elimina fences ```json ... ```.
    cerca = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if cerca:
        s = cerca.group(1).strip()
    data: Any = None
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, ValueError):
        inicio = next((i for i, c in enumerate(s) if c in "[{"), -1)
        if inicio < 0:
            return None
        try:
            data = json.loads(s[inicio:])
        except (json.JSONDecodeError, ValueError):
            return None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for clave in ("candidatos", "candidates", "items", "resultados"):
            if isinstance(data.get(clave), list):
                return data[clave]
    return None


def _construir_prompt(brief: dict[str, Any], *, fecha: str) -> str:
    """Construye el prompt de investigacion web para el brief dado."""
    marca_etiqueta = ""
    marca_id = _normalizar_marca(brief.get("marca") or "")
    if marca_id:
        # Busca la etiqueta legible de la marca.
        for mid, etq in marcas.opciones():
            if mid == marca_id:
                marca_etiqueta = etq
                break
    linea = str(brief.get("linea") or "").strip()
    instrucciones = str(brief.get("instrucciones") or "").strip()
    idiomas_csv = str(brief.get("idiomas") or "").strip()
    nombre = str(brief.get("nombre") or "brief").strip()

    contexto_marca = f"Marca/cuenta: {marca_etiqueta or marca_id}" if (marca_etiqueta or marca_id) else ""
    contexto_linea = f"Linea/tema: {linea}" if linea else ""
    contexto_idiomas = f"Idiomas a rastrear: {idiomas_csv}" if idiomas_csv else "Idiomas: cualquiera (prioriza espanol)"
    contexto_fecha = f"Fecha editorial: {fecha}"

    encabezado_marca = f"\n{contexto_marca}" if contexto_marca else ""
    encabezado_linea = f"\n{contexto_linea}" if contexto_linea else ""

    return (
        f"Eres un agente de investigacion para redes sociales. Brief: {nombre}.{encabezado_marca}"
        f"{encabezado_linea}\n{contexto_fecha}\n{contexto_idiomas}\n\n"
        f"Instrucciones especificas: {instrucciones}\n\n"
        "Investiga en la web y encuentra los temas mas relevantes PARA HOY relacionados con "
        "este brief. Devuelve EXCLUSIVAMENTE un objeto JSON con la forma "
        '{"candidatos": [ ... ]}, sin ningun texto adicional ni explicacion. '
        "Cada elemento de `candidatos` es un objeto con:\n"
        '- "titulo": titular corto del tema (OBLIGATORIO).\n'
        '- "resumen": descripcion del tema en 2-3 oraciones.\n'
        '- "por_que": por que es relevante HOY para esta marca/linea (1-2 oraciones).\n'
        '- "fuente": nombre del medio o plataforma de origen.\n'
        '- "enlace": URL del articulo/post fuente, o "".\n'
        '- "idioma": codigo ISO del idioma del tema (ej: "es", "en").\n'
        "Si no encuentras temas relevantes, devuelve {\"candidatos\": []}."
    )


def _normalizar_candidatos(
    registros: list[Any],
    *,
    brief: dict[str, Any],
    fecha: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Lista de dicts de Claude -> (candidatos normalizados, errores). PURO."""
    marca_id = _normalizar_marca(brief.get("marca") or "")
    linea = str(brief.get("linea") or "").strip()
    brief_id = str(brief.get("id") or "")
    candidatos: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = []
    for i, reg in enumerate(registros, start=1):
        if not isinstance(reg, dict):
            errores.append({"fila": i, "motivo": "El registro no es un objeto; se omitio."})
            continue
        titulo = str(reg.get("titulo") or "").strip()
        if not titulo:
            errores.append({"fila": i, "motivo": "Registro sin titulo; se omitio."})
            continue
        candidatos.append({
            "brief_id": brief_id,
            "fecha": fecha,
            "marca": marca_id,
            "linea": linea,
            "titulo": titulo[:500],
            "resumen": str(reg.get("resumen") or "").strip()[:2000],
            "por_que": str(reg.get("por_que") or "").strip()[:1000],
            "fuente": str(reg.get("fuente") or "").strip()[:300],
            "enlace": str(reg.get("enlace") or "").strip()[:1000],
            "idioma": str(reg.get("idioma") or "es").strip()[:10],
            "estado": "nuevo",
        })
    return candidatos, errores


def correr_brief(
    brief: dict[str, Any],
    *,
    fecha: str,
    ejecutor: Ejecutor | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Investiga el brief y devuelve (candidatos, errores).

    Candidatos son dicts listos para `db.crear_inv_candidatos` (sin id/creado).
    Errores son dicts `{fila, motivo}`. Ejecutor inyectable: tests pasan un fake,
    produccion usa el subproceso real de `claude`. SINCRONO: el llamante debe
    correr esto en threadpool para no bloquear el event loop.
    """
    correr = ejecutor or _ejecutar_claude_json
    prompt = _construir_prompt(brief, fecha=fecha)
    salida = ""
    try:
        salida = correr(prompt)
    except Exception as exc:  # noqa: BLE001 -- cualquier fallo del agente => error legible
        _log.warning("correr_brief '%s' fallo: %s", brief.get("nombre", "?"), exc)
        return [], [{"fila": 0, "motivo": f"No se pudo investigar: {exc}"}]
    registros = _extraer_candidatos(salida)
    if registros is None:
        return [], [{"fila": 0, "motivo": "El agente no devolvio candidatos en JSON legible."}]
    return _normalizar_candidatos(registros, brief=brief, fecha=fecha)
