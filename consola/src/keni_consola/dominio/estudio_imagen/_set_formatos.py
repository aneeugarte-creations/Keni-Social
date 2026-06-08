"""Estudio de imagen — set multi-formato "de un tiro" desde UNA imagen aportada (Fase 3).

Submódulo de área del paquete `dominio.estudio_imagen`. Encaja la foto aportada a TODOS los
lienzos de la red destino por vía DETERMINISTA (Pillow, gratis) y estampa la identidad de marca.
La generación por IA NO interviene aquí.
"""

from __future__ import annotations

from typing import Any

from ... import formatos_red, marca_assets, marcas
from . import _ref
from ._comun import _FORMATOS_COMPONER, ASPECTOS, EstudioError

__all__ = ["_logo_de_marca", "_encajar_a_lienzo", "generar_set_formatos"]


def _logo_de_marca(marca: str) -> str | None:
    """Ruta de disco al logo (asset de marca, mock/oficial) o `None` si no hay/falla.

    `None` deja a `componer` usar el logo del spec (wordmark de texto por defecto): el flujo
    NUNCA se queda sin placa por falta de asset.
    """
    try:
        ruta = marca_assets.ruta_asset(marca, marca_assets.TIPO_LOGO)
    except marca_assets.MarcaAssetError:
        return None
    return ruta or None


def _encajar_a_lienzo(imagen: str, lienzo: str) -> str:
    """Encaja la imagen aportada al lienzo (DETERMINISTA) y devuelve el id de media resultante.

    Prefiere EXTENDER el fondo uniforme (no recorta al sujeto); si ningun borde es uniforme,
    el motor `extender` cae solo al recorte cubriente. Sin coste, sin IA. Devuelve el id del
    nuevo objeto de media ya encajado al lienzo, listo para estampar la marca encima.
    """
    res = _ref.editar(imagen, "extender", {"formato": lienzo, "metodo": "borde", "forzar": False})
    return res["id"]


def generar_set_formatos(
    imagen: str,
    *,
    marca: str,
    red: str = "",
    titular: str = "",
    etiqueta: str | None = None,
    aplicar_marca: bool = True,
) -> dict[str, Any]:
    """Desde UNA imagen aportada, produce el SET de formatos de una red (o todos los lienzos).

    Es el "de un tiro" de la Fase 3: el equipo trae la foto y la IA la encaja a TODOS los
    lienzos de la red destino (matriz `formatos_red`) y le aplica la identidad de marca,
    por via DETERMINISTA (Pillow, gratis, exacto). La generacion por IA NO interviene aqui.

    Flujo por lienzo (todo determinista):
      1. ENCAJAR la foto al lienzo extendiendo el fondo uniforme si se puede (no recorta al
         sujeto); si no, recorte cubriente.
      2. (si `aplicar_marca`) ESTAMPAR la plantilla de marca (logo del asset de la casa +
         pleca + titular) con `componer`. TODOS los lienzos llevan placa, incluido
         `horizontal` (16:9 de X): el SPEC deriva su layout en 1600×900 igual que los demas,
         asi que el formato de X sale `marcado:true` como feed/vertical/cuadrado.

    `red`: si es una red conocida, usa SUS lienzos (`formatos_red.lienzos_de`); si esta vacia
    o no se conoce, usa el set MAXIMO de lienzos canonicos. `etiqueta`: contrato de `componer`
    (None=default de marca, ""=sin pleca, texto=esa pleca).

    Devuelve `{red, marca, formatos:[{lienzo, aspecto, marcado, id, url}], imagenes:[...]}`.
    Los objetos intermedios (encajes sin marca) quedan como huerfanos del almacen (los recoge
    el GC de media, como las variantes no elegidas del Estudio).
    """
    if not marcas.es_marca(marca):
        raise EstudioError("Marca desconocida.")
    if not (imagen or "").strip():
        raise EstudioError("Falta la imagen aportada para generar el set de formatos.")

    lienzos = formatos_red.lienzos_de(red) if red else []
    if not lienzos:
        lienzos = formatos_red.lienzos_canonicos()

    logo_path = _ref._logo_de_marca(marca) if aplicar_marca else None
    resultados: list[dict[str, Any]] = []
    for lienzo in lienzos:
        encajada = _encajar_a_lienzo(imagen, lienzo)
        marcado = False
        salida_id, salida_url = encajada, f"/api/media/{encajada}"
        # El compositor por SPEC entiende todos los lienzos de FORMATOS (incl. `horizontal`,
        # 16:9 de X): cada uno estampa su placa con su layout derivado del spec.
        if aplicar_marca and lienzo in _FORMATOS_COMPONER:
            comp = _ref.componer(
                encajada, marca=marca, formato=lienzo, titular=titular,
                etiqueta=etiqueta, logo_path=logo_path,
            )
            salida_id, salida_url = comp["id"], comp["url"]
            marcado = True
        resultados.append(
            {
                "lienzo": lienzo,
                "aspecto": formatos_red.ASPECTOS.get(lienzo, ASPECTOS.get(lienzo, "")),
                "marcado": marcado,
                "id": salida_id,
                "url": salida_url,
            }
        )

    return {
        "red": red,
        "marca": marca,
        "formatos": resultados,
        "imagenes": [{"id": r["id"], "url": r["url"]} for r in resultados],
    }
