"""Estudio de imagen — composición de marca DETERMINISTA (plantilla: logo + pleca + titular).

Submódulo de área del paquete `dominio.estudio_imagen`. Render por SPEC con el motor ÚNICO Node
(`render_node`, lo diseñado en el editor = lo que sale). Cubre la composición persistente, el
render a bytes on-demand y la previa del editor visual.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ... import marcas, media, plantillas_marca
from ...motores.estudio_imagen import spec_plantilla
from . import _ref
from ._comun import (
    _FORMATOS_COMPONER,
    EstudioError,
    _materializar,
    _materializar_logo,
)

__all__ = [
    "_componer_node_bytes",
    "_componer_node",
    "componer_bytes",
    "previsualizar_spec_bytes",
    "componer",
]


def _componer_node_bytes(
    imagen: str, *, marca: str, fmt: str, titular: str, etiqueta: str | None,
    logo_path: str | None = None,
) -> tuple[bytes, bool]:
    """Render por SPEC con el motor Node y devuelve `(png_bytes, placeholder)` SIN persistir.

    Render PURO a memoria: materializa los assets en un temporal, corre Node y devuelve los
    bytes del PNG. NO escribe en el almacén de media (lo usa el render ON-DEMAND, que sirve los
    bytes por HTTP sin generar objetos). `logo_path` sustituye al logo del spec (flujo de arte).
    """
    plana = plantillas_marca.obtener(marca)
    spec = plantillas_marca.obtener_spec(marca)
    formato_spec = spec.get("formatos", {}).get(fmt)
    if not formato_spec:
        raise EstudioError(f"El spec de la marca no tiene el formato '{fmt}'.")
    placeholder = not (imagen or "").strip()
    # Pleca efectiva (contrato de `etiqueta`): None=default de marca; ""=omitir; texto=ese.
    etiqueta_efectiva = plana.get("etiqueta_default", "") if etiqueta is None else etiqueta

    with tempfile.TemporaryDirectory(prefix="keni-render-") as tmp:
        carpeta = Path(tmp)
        foto = None if placeholder else str(_materializar(imagen, carpeta))
        logo_cfg = formato_spec.get("logo") or {}
        ruta_logo = logo_path or _materializar_logo(logo_cfg.get("media_id", ""), carpeta)
        fondo_cfg = formato_spec.get("fondo") or {}
        ruta_fondo = ""
        if fondo_cfg.get("tipo") == "imagen":
            ruta_fondo = _materializar_logo((fondo_cfg.get("imagen") or {}).get("media_id", ""), carpeta)

        out = carpeta / "salida.png"
        payload = {
            "spec": spec,
            "formato": fmt,
            "placeholder": placeholder,
            "foto": foto,
            "assets": {"logo": ruta_logo or None, "fondo": ruta_fondo or None},
            "bindings": {"copy_in": titular or "", "etiqueta_default": etiqueta_efectiva or ""},
        }
        _ref._correr_render_node(payload, out)
        return out.read_bytes(), placeholder


def _componer_node(
    imagen: str, *, marca: str, fmt: str, titular: str, etiqueta: str | None,
    logo_path: str | None = None,
) -> dict[str, Any]:
    """Render por SPEC que PERSISTE el PNG (content-addressed) y devuelve `{id,url,imagenes,info}`.

    Lo usan los flujos que necesitan un asset DURABLE referenciado (bake del editor pro, arte
    multi-formato, materialización al PUBLICAR). El render on-demand usa `_componer_node_bytes`
    (sin persistir). `logo_path` sustituye al logo del spec.
    """
    datos, placeholder = _componer_node_bytes(
        imagen, marca=marca, fmt=fmt, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )
    try:
        nombre = media.guardar_bytes_contenido(datos, ext="png")
    except media.MediaError as e:
        raise EstudioError(str(e)) from e
    return {
        "id": nombre, "url": f"/api/media/{nombre}",
        "imagenes": [{"id": nombre, "url": f"/api/media/{nombre}"}],
        "info": {"op": "componer", "marca": marca, "formato": fmt,
                 "placeholder": placeholder, "motor": "node"},
    }


def componer_bytes(
    imagen: str, *, marca: str, formato: str = "feed", titular: str = "",
    etiqueta: str | None = None, logo_path: str | None = None,
) -> bytes:
    """Compone la placa de marca y devuelve los BYTES del PNG SIN persistir (render on-demand).

    Misma firma que `componer` pero efímero: no escribe en el almacén. Valida marca y formato.
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if formato not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )
    datos, _ = _componer_node_bytes(
        imagen, marca=marca, fmt=formato, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )
    return datos


def previsualizar_spec_bytes(
    spec: dict[str, Any], formato: str, *, titular: str = "", etiqueta_default: str = "",
) -> bytes:
    """Renderiza un SPEC en EDICIÓN (sin guardar) en placeholder y devuelve los BYTES, SIN persistir.

    Lo usa el editor visual del diseñador para ver "lo que sale" mientras se diseña. La previa es
    función pura del spec en edición: NO se almacena (se sirve por HTTP, efímera). Valida el spec,
    renderiza con Node (placeholder, sin foto) con un titular/pleca de muestra y devuelve el PNG.
    """
    fmt = formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError("Formato no soportado. Usa: " + ", ".join(_FORMATOS_COMPONER) + ".")
    try:
        spec_ok = spec_plantilla.validar(spec)
    except spec_plantilla.SpecError as exc:
        raise EstudioError(str(exc)) from exc
    if fmt not in spec_ok.get("formatos", {}):
        raise EstudioError(f"El spec no tiene el formato '{fmt}'.")

    with tempfile.TemporaryDirectory(prefix="keni-preview-") as tmp:
        carpeta = Path(tmp)
        logo_cfg = spec_ok["formatos"][fmt].get("logo") or {}
        ruta_logo = _materializar_logo(logo_cfg.get("media_id", ""), carpeta)
        fondo_cfg = spec_ok["formatos"][fmt].get("fondo") or {}
        ruta_fondo = ""
        if fondo_cfg.get("tipo") == "imagen":
            ruta_fondo = _materializar_logo((fondo_cfg.get("imagen") or {}).get("media_id", ""), carpeta)
        out = carpeta / "preview.png"
        payload = {
            "spec": spec_ok, "formato": fmt, "placeholder": True, "foto": None,
            "assets": {"logo": ruta_logo or None, "fondo": ruta_fondo or None},
            "bindings": {"copy_in": titular or "Titular de ejemplo",
                         "etiqueta_default": etiqueta_default or ""},
        }
        _ref._correr_render_node(payload, out)
        return out.read_bytes()


def componer(
    imagen: str,
    *,
    marca: str,
    formato: str = "feed",
    titular: str = "",
    etiqueta: str | None = None,
    autor: dict[str, str] | None = None,
    logo_path: str | None = None,
) -> dict[str, Any]:
    """Compone la PLANTILLA de marca y devuelve `{id,url,imagenes,info}` (firma estable).

    Render por SPEC con el motor **Node** (`render_node`, único motor: lo diseñado en el editor
    es lo que sale). Si Node falla, lanza `EstudioError` (los llamantes lo manejan: la auto-gen
    de copy es tolerante y omite la placa; la API devuelve 4xx).

    `imagen`: id de media de la foto; `""` => PLANTILLA con el hueco de foto vacío (placeholder
    "Sube una foto"). `etiqueta`: `None` => etiqueta_default de la marca; `""` => sin pleca;
    texto => esa pleca. `formato`: `vertical|feed|cuadrado|horizontal` (cada uno tiene su SPEC).
    `logo_path`: ruta de disco a un logo (asset de marca mock/oficial) que sustituye al del
    spec; `None` usa el logo de la plantilla (comportamiento normal).
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    fmt = formato
    if fmt not in _FORMATOS_COMPONER:
        raise EstudioError(
            "Formato no soportado para componer. Usa: " + ", ".join(_FORMATOS_COMPONER) + "."
        )
    return _componer_node(
        imagen, marca=marca, fmt=fmt, titular=titular, etiqueta=etiqueta, logo_path=logo_path
    )
