"""Estudio de imagen — render del DOCUMENTO de capas (editor profesional) y plantilla con fotos.

Submódulo de área del paquete `dominio.estudio_imagen`. Valida/renderiza documentos de capas con
el motor Node (persistente y a bytes on-demand), inyecta fotos por hueco al componer desde una
plantilla guardada, y expone las fronteras API->dominio (validar documento/capas, hueco, encuadre).
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import Any

from ... import marcas, media, plantillas_marca, repos
from ...motores.estudio_imagen import documento as doc_capas
from . import _ref
from ._comun import (
    _FORMATOS_COMPONER,
    EstudioError,
    _materializar_logo,
    _nombre_local_plano,
)

__all__ = [
    "_refs_imagenes",
    "_fuentes_extra_de_marca",
    "normalizar_opciones_export",
    "renderizar_documento_bytes",
    "renderizar_documento",
    "_fotos_de",
    "_doc_plantilla_con_fotos",
    "componer_desde_plantilla",
    "componer_desde_plantilla_bytes",
    "parsear_encuadre",
    "validar_documento",
    "documento_tiene_hueco",
    "validar_capas",
    "documento_desde_plantilla",
]


def _refs_imagenes(capas: list[dict[str, Any]]) -> set[str]:
    """Ids de media referenciados por las capas (imagen.objeto + logo.media_id), recursivo en grupos."""
    refs: set[str] = set()
    for c in capas:
        if c.get("tipo") == "imagen" and (c.get("objeto") or "").strip():
            refs.add(c["objeto"])
        elif c.get("tipo") == "logo" and c.get("tipo_logo") == "imagen" and (c.get("media_id") or "").strip():
            refs.add(c["media_id"])
        elif c.get("tipo") == "grupo":
            refs |= _refs_imagenes(c.get("capas") or [])
    return refs


def _fuentes_extra_de_marca(marca: str, carpeta: Path) -> dict[str, str]:
    """Tipografías propias de la marca (activos tipo 'tipografia') -> {familia: ruta_archivo}.

    Materializa cada fuente subida (.woff2/.ttf) para que el renderer Node la registre y el PNG
    final use la fuente real. La familia es `metadatos.familia` o, si falta, el `nombre` del activo
    (mismo nombre con el que el editor la registra en cliente vía FontFace -> coinciden).
    """
    if not (marca or "").strip():
        return {}
    extra: dict[str, str] = {}
    for activo in repos.listar_marca_activos(marca=marca, tipo="tipografia"):
        objeto = (activo.get("objeto") or "").strip()
        if not objeto:
            continue
        try:
            meta = json.loads(activo.get("metadatos") or "{}")
        except (ValueError, TypeError):
            meta = {}
        familia = ((meta.get("familia") if isinstance(meta, dict) else "") or activo.get("nombre") or "").strip()
        if not familia:
            continue
        datos = media.leer_media(objeto)
        if datos is None:
            continue
        ruta = carpeta / f"fuente-{_nombre_local_plano(objeto)}"
        ruta.write_bytes(datos)
        extra[familia] = str(ruta)
    return extra


# Opciones de EXPORT del editor (descarga con formato/calidad/escala). El render por defecto
# (miniaturas, bake de pieza, composición de feed) NO pasa opciones -> PNG a escala 1.
_EXPORT_FORMATOS = ("png", "jpg")


def normalizar_opciones_export(opciones: dict[str, Any] | None) -> dict[str, Any]:
    """Valida/normaliza las opciones de exportación -> `{formato, calidad, escala}` (defaults png/90/1).

    `formato`: "png"|"jpg" (acepta "jpeg" como alias). `calidad`: 1-100 (solo aplica a jpg).
    `escala`: 0.25-4. `None` o `{}` -> defaults. Lanza `EstudioError` (mensaje en español) si algún
    valor está fuera de rango o no es numérico; lo recoge la API como 400.
    """
    op = opciones or {}
    if not isinstance(op, dict):
        raise EstudioError("Las opciones de exportación no son válidas.")

    formato = str(op.get("formato") or "png").strip().lower()
    if formato == "jpeg":
        formato = "jpg"
    if formato not in _EXPORT_FORMATOS:
        raise EstudioError("Formato de exportación no soportado. Usa: png o jpg.")

    try:
        escala = float(op.get("escala", 1))
    except (TypeError, ValueError) as exc:
        raise EstudioError("La escala de exportación debe ser un número.") from exc
    if not (0.25 <= escala <= 4):
        raise EstudioError("La escala de exportación debe estar entre 0.25 y 4.")

    try:
        calidad = int(op.get("calidad", 90))
    except (TypeError, ValueError) as exc:
        raise EstudioError("La calidad de exportación debe ser un número entero.") from exc
    if not (1 <= calidad <= 100):
        raise EstudioError("La calidad de exportación debe estar entre 1 y 100.")

    return {"formato": formato, "calidad": calidad, "escala": escala}


def renderizar_documento_bytes(
    documento: dict[str, Any],
    *,
    bindings: dict[str, str] | None = None,
    opciones: dict[str, Any] | None = None,
) -> bytes:
    """Valida y renderiza un DOCUMENTO de capas a los BYTES del archivo (motor Node), SIN persistir.

    Materializa cada imagen referenciada a un temporal y corre Node; devuelve los bytes. Lo usa el
    render ON-DEMAND (sirve por HTTP sin generar objetos). `opciones` (formato/calidad/escala) controla
    el encoding y la resolución del export (def PNG a escala 1). Lanza `EstudioError` si no valida/falla.
    """
    opciones = normalizar_opciones_export(opciones)
    try:
        doc = doc_capas.validar(documento)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc

    with tempfile.TemporaryDirectory(prefix="keni-doc-") as tmp:
        carpeta = Path(tmp)
        assets: dict[str, str] = {}
        refs = _refs_imagenes(doc["capas"])
        fondo = doc.get("fondo") or {}
        if fondo.get("tipo") == "imagen":
            mid = (fondo.get("imagen") or {}).get("media_id", "")
            if mid:
                refs.add(mid)
        for ref in refs:
            ruta = _materializar_logo(ref, carpeta)
            if ruta:
                assets[ref] = ruta

        fuentes_extra = _ref._fuentes_extra_de_marca(doc.get("marca", ""), carpeta)

        out = carpeta / "salida"
        payload = {
            "documento": doc,
            "assets": assets,
            "fuentes": doc.get("fuentes"),
            "fuentes_extra": fuentes_extra,
            "bindings": bindings or {},
            "opciones": opciones,
        }
        _ref._correr_render_documento(payload, out)
        return out.read_bytes()


def renderizar_documento(
    documento: dict[str, Any],
    *,
    bindings: dict[str, str] | None = None,
    opciones: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Renderiza un DOCUMENTO de capas y PERSISTE el archivo (content-addressed) -> `{id, url}`.

    Para flujos con asset DURABLE referenciado (bake del editor pro, export con descarga). El render
    on-demand usa `renderizar_documento_bytes` (sin persistir). `opciones` (formato/calidad/escala)
    fija el encoding: el media se persiste con la extensión/mimetype correctos (png o jpg).
    """
    opciones = normalizar_opciones_export(opciones)
    datos = renderizar_documento_bytes(documento, bindings=bindings, opciones=opciones)
    ext = "jpg" if opciones["formato"] == "jpg" else "png"
    try:
        nombre = media.guardar_bytes_contenido(datos, ext=ext)
    except media.MediaError as e:
        raise EstudioError(str(e)) from e
    return {"id": nombre, "url": f"/api/media/{nombre}"}


def _fotos_de(
    fotos: list[dict[str, Any]] | None,
    foto: str,
    foco: tuple[float, float] | list[float] | None,
    zoom: float,
) -> list[dict[str, Any]]:
    """Normaliza la entrada de fotos: si llega la lista de COLLAGE (`fotos`) se usa tal cual; si no,
    se construye una lista de UN elemento con la foto única + su reencuadre (retrocompat)."""
    if fotos:
        return fotos
    return [{"objeto": foto or "", "foco": foco, "zoom": zoom}]


def _doc_plantilla_con_fotos(
    documento: dict[str, Any] | str,
    fotos: list[dict[str, Any]],
) -> dict[str, Any]:
    """Inyecta UNA foto por HUECO (`es_foto`) del documento, en orden de `capas`.

    Devuelve una COPIA del documento lista para renderizar. `documento` puede ser dict o JSON
    string (lo que guarda `PlantillaDiseno`). `fotos[i]` (`{objeto, foco:[x,y]|None, zoom}`) va al
    hueco i; los huecos sin foto correspondiente quedan vacíos (placeholder). Las plantillas de solo
    texto/gráfica no tienen hueco y no reciben nada.
    """
    if isinstance(documento, str):
        try:
            documento = json.loads(documento or "{}")
        except (ValueError, TypeError) as exc:
            raise EstudioError("La plantilla no tiene un documento válido.") from exc
    doc = copy.deepcopy(documento)
    huecos = doc_capas.capas_foto(doc)
    for i, hueco in enumerate(huecos):
        spec = fotos[i] if i < len(fotos) else None
        if not isinstance(spec, dict):
            continue
        hueco["objeto"] = str(spec.get("objeto") or "")
        foco = spec.get("foco")
        if isinstance(foco, (list, tuple)) and len(foco) == 2:
            hueco["foco"] = [float(foco[0]), float(foco[1])]
        zoom = spec.get("zoom")
        if zoom and float(zoom) > 0:
            hueco["zoom"] = float(zoom)
    return doc


def componer_desde_plantilla(
    documento: dict[str, Any] | str,
    *,
    copy_in: str = "",
    foto: str = "",
    foco: tuple[float, float] | list[float] | None = None,
    zoom: float = 0.0,
    fotos: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Renderiza la plantilla con la(s) foto(s)+copy_in de la pieza y PERSISTE el PNG -> `{id, url}`.

    Inyecta UNA foto por hueco (`es_foto`) y el `copy_in` como binding del titular. `fotos` (collage)
    tiene prioridad; si no llega, usa la foto única (`foto`/`foco`/`zoom`) en el primer hueco.
    """
    doc = _doc_plantilla_con_fotos(documento, _fotos_de(fotos, foto, foco, zoom))
    return _ref.renderizar_documento(doc, bindings={"copy_in": copy_in})


def componer_desde_plantilla_bytes(
    documento: dict[str, Any] | str,
    *,
    copy_in: str = "",
    foto: str = "",
    foco: tuple[float, float] | list[float] | None = None,
    zoom: float = 0.0,
    fotos: list[dict[str, Any]] | None = None,
) -> bytes:
    """Como `componer_desde_plantilla` pero devuelve los BYTES del PNG SIN persistir (on-demand)."""
    doc = _doc_plantilla_con_fotos(documento, _fotos_de(fotos, foto, foco, zoom))
    return _ref.renderizar_documento_bytes(doc, bindings={"copy_in": copy_in})


def parsear_encuadre(encuadre: str) -> tuple[list[float] | None, float]:
    """Parsea el JSON de reencuadre de una pieza (`{"foco":[x,y],"zoom":z}`).

    Devuelve `(foco | None, zoom)`. Tolerante: "" o JSON inválido → `(None, 0.0)` (sin
    reencuadre). El foco se recorta a [0,1] y el zoom a [1, 6] para no romper el render.
    """
    if not (encuadre or "").strip():
        return None, 0.0
    try:
        datos = json.loads(encuadre)
    except (ValueError, TypeError):
        return None, 0.0
    if not isinstance(datos, dict):
        return None, 0.0
    foco_bruto = datos.get("foco")
    foco: list[float] | None = None
    if isinstance(foco_bruto, (list, tuple)) and len(foco_bruto) == 2:
        try:
            foco = [
                min(1.0, max(0.0, float(foco_bruto[0]))),
                min(1.0, max(0.0, float(foco_bruto[1]))),
            ]
        except (ValueError, TypeError):
            foco = None
    try:
        zoom = float(datos.get("zoom") or 0.0)
    except (ValueError, TypeError):
        zoom = 0.0
    if zoom:
        zoom = min(6.0, max(1.0, zoom))
    return foco, zoom


def validar_documento(documento: dict[str, Any]) -> dict[str, Any]:
    """Valida y normaliza un Documento de capas -> dict normalizado. Lanza EstudioError si falla.

    Lo usan las APIs que PERSISTEN un documento (plantillas de diseño, bloques) para no guardar
    JSON inválido. Mantiene la frontera API->dominio (la API no importa motores directamente).
    """
    try:
        return doc_capas.validar(documento)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc


def documento_tiene_hueco(documento: dict[str, Any]) -> bool:
    """True si el documento declara un hueco de foto explícito (`es_foto`). Frontera API->dominio."""
    return doc_capas.tiene_hueco_explicito(documento)


def validar_capas(capas: Any) -> list[dict[str, Any]]:
    """Valida una LISTA de capas (para bloques reutilizables) -> lista normalizada.

    Reusa el validador del Documento envolviendo las capas en un documento mínimo. Lanza
    EstudioError si alguna capa no valida.
    """
    doc = validar_documento({"formato": {"w": 1, "h": 1}, "capas": capas})
    return doc["capas"]


def documento_desde_plantilla(marca: str, formato: str) -> dict[str, Any]:
    """Documento de capas EDITABLE derivado de la plantilla de marca (punto de partida del editor).

    Toma el spec efectivo de la marca y adapta el formato pedido a un documento de capas. Así el
    editor abre una marca con su layout actual (foto + overlay + textos + logo) ya como capas.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if formato not in _FORMATOS_COMPONER:
        raise EstudioError("Formato no soportado. Usa: " + ", ".join(_FORMATOS_COMPONER) + ".")
    spec = plantillas_marca.obtener_spec(marca)
    try:
        return doc_capas.desde_spec(spec, formato)
    except doc_capas.DocumentoError as exc:
        raise EstudioError(str(exc)) from exc
