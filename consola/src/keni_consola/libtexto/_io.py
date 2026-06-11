"""Lectura / escritura de un documento (`.md` con frontmatter YAML + cuerpo).

El `id` se DERIVA siempre de la ruta (fuente de verdad); el frontmatter solo aporta
metadatos (título, fechas, clase, marcas, etc.).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from ._comun import (
    CLASES,
    ESTADO_DEFECTO,
    ESTADOS,
    ROLES_PROMPT,
    SALIDAS,
    TIPOS,
    Documento,
    TextoError,
    _lista_str,
)
from ._rutas import _id_de_ruta

__all__ = ["_parsear", "_serializar", "_leer"]


def _parsear(texto: str) -> tuple[dict[str, object], str]:
    """Separa frontmatter YAML (entre `---`) y cuerpo. Tolerante: sin frontmatter -> ({}, texto)."""
    if texto.startswith("---"):
        # Busca el cierre del bloque (segunda linea `---`).
        partes = texto.split("\n")
        cierre = None
        for i in range(1, len(partes)):
            if partes[i].strip() == "---":
                cierre = i
                break
        if cierre is not None:
            crudo = "\n".join(partes[1:cierre])
            cuerpo = "\n".join(partes[cierre + 1 :])
            try:
                meta = yaml.safe_load(crudo)
            except yaml.YAMLError:
                meta = None
            if isinstance(meta, dict):
                return meta, cuerpo.lstrip("\n")
    return {}, texto


def _serializar(doc: Documento) -> str:
    """Documento -> texto `.md` (frontmatter estable + cuerpo)."""
    meta: dict[str, object] = {
        "titulo": doc.titulo,
        "tipo": doc.tipo,
        "carpeta": doc.carpeta,
        "creado": doc.creado,
        "actualizado": doc.actualizado,
    }
    # Descripción HUMANA (no inyectada): se escribe solo si la hay, tras el título.
    if doc.descripcion:
        meta["descripcion"] = doc.descripcion
    if doc.tipo == "editorial":
        meta["clase"] = doc.clase
        meta["marcas"] = list(doc.marcas)
    elif doc.tipo == "prompt":
        if doc.salida:
            meta["salida"] = doc.salida
        if doc.rol:
            meta["rol"] = doc.rol
    # Metadatos transversales: solo se escriben si NO son el defecto, para no ensuciar el
    # frontmatter de los documentos existentes (que siguen leyendose con los defaults).
    if doc.estado and doc.estado != ESTADO_DEFECTO:
        meta["estado"] = doc.estado
    if doc.etiquetas:
        meta["etiquetas"] = list(doc.etiquetas)
    if doc.pipelines:
        meta["pipelines"] = list(doc.pipelines)
    if doc.prioridad:
        meta["prioridad"] = doc.prioridad
    cabecera = yaml.safe_dump(meta, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return f"---\n{cabecera}---\n\n{doc.cuerpo.rstrip()}\n"


def _leer(ruta: Path) -> Documento | None:
    """Lee un `.md` como Documento; None si no existe / corrupto. El id se DERIVA de la ruta."""
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None
    meta, cuerpo = _parsear(texto)
    try:
        doc_id = _id_de_ruta(ruta)
    except (ValueError, TextoError):
        return None
    partes = doc_id.split("/")
    tipo = partes[0]
    if tipo not in TIPOS:
        return None
    # `carpeta` se reconstruye de la ruta (fuente de verdad), no del frontmatter (que puede
    # quedar viejo tras un mv manual). El frontmatter aporta titulo/fechas/clase/marcas.
    carpeta = "/".join(partes[1:-1])
    titulo = meta.get("titulo")
    titulo = titulo.strip() if isinstance(titulo, str) and titulo.strip() else partes[-1].replace("-", " ")
    descripcion = meta.get("descripcion")
    descripcion = descripcion.strip() if isinstance(descripcion, str) else ""
    clase = meta.get("clase")
    clase = clase if isinstance(clase, str) and clase in CLASES else ""
    marcas_crudas = meta.get("marcas")
    marcas = [m for m in marcas_crudas if isinstance(m, str)] if isinstance(marcas_crudas, list) else []
    creado = meta.get("creado") if isinstance(meta.get("creado"), str) else ""
    actualizado = meta.get("actualizado") if isinstance(meta.get("actualizado"), str) else creado
    salida = meta.get("salida")
    salida = salida if isinstance(salida, str) and salida in SALIDAS else ""
    estado = meta.get("estado")
    estado = estado if isinstance(estado, str) and estado in ESTADOS else ESTADO_DEFECTO
    etiquetas = _lista_str(meta.get("etiquetas"))
    pipelines = _lista_str(meta.get("pipelines"))
    rol = meta.get("rol")
    rol = rol if tipo == "prompt" and isinstance(rol, str) and rol in ROLES_PROMPT else ""
    prioridad = meta.get("prioridad")
    prioridad = prioridad if isinstance(prioridad, int) and not isinstance(prioridad, bool) else 0
    return Documento(
        id=doc_id, titulo=titulo, descripcion=descripcion, tipo=tipo, carpeta=carpeta,
        cuerpo=cuerpo, creado=creado, actualizado=actualizado, clase=clase, marcas=marcas,
        salida=salida, estado=estado, etiquetas=etiquetas, pipelines=pipelines, rol=rol,
        prioridad=prioridad,
    )
