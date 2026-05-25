"""Tests de la PREVISUALIZACION de imagenes del Estudio de imagen (Fase 2).

Las skills de imagen (estudio-imagen) producen ARCHIVOS .png con sus herramientas y
la salida de Claude (texto) MENCIONA esas rutas. La consola, al completar, importa
esas imagenes al almacen de media y las devuelve como `imagenes` en el `resultado`
para que el frontend las previsualice por `/api/media/...`.

TODO OFFLINE: NUNCA se llama a `claude` real; el lanzador se mockea con una salida
canned que menciona rutas .png reales escritas a disco por el propio test.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from keni_consola import media
from keni_consola.api import skills

from .conftest import _cliente, lanzador_generacion_completa

# PNG 1x1 valido (firma + IHDR + IDAT + IEND), suficiente para importar como imagen.
_PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000"
    "00907753de0000000c4944415408d76360000002000100" "05fe02fe"
    "dccc59e70000000049454e44ae426082"
)


def _sembrar_skill_imagen(tmp_path: Path) -> None:
    """Crea en el catalogo de skills (tmp) una skill de imagen: media=True, documento."""
    carpeta = tmp_path / "skills" / "estudio-imagen"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "SKILL.md").write_text("# estudio-imagen\n\nMesa de arte.\n", encoding="utf-8")
    meta = {
        "nombre": "Estudio de imagen",
        "explicacion": "Recorta/genera y revisa una imagen.",
        "grupo": "experimentales",
        "aplica_redes": False,
        "salida": "documento",
        "media": True,
        "orden": 36,
        "campos": [
            {"id": "imagen", "etiqueta": "Imagen (opcional)", "tipo": "archivo",
             "requerido": False, "placeholder": "", "ayuda": "", "opciones": [],
             "media_tipos": "image/*"},
            {"id": "peticion", "etiqueta": "Qué quieres hacer", "tipo": "textarea",
             "requerido": True, "placeholder": "", "ayuda": "", "opciones": [],
             "media_tipos": ""},
        ],
        "plantilla_invocacion": "usa estudio-imagen, marca {marca}.\n\n{peticion}\n",
    }
    (carpeta / "keni.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# Helpers puros                                                                #
# --------------------------------------------------------------------------- #


def test_rutas_imagen_en_texto_extrae_y_deduplica():
    salida = (
        "## Qué hice\n"
        "- recortar feed  ->  /tmp/keni-skills-x/foto-feed.png\n"
        "- recortar 1:1   ->  /tmp/keni-skills-x/foto-cuadrado.PNG\n"
        "- (repetida)     ->  /tmp/keni-skills-x/foto-feed.png\n"
        "Una mencion a un .txt /tmp/no.txt no cuenta.\n"
    )
    rutas = skills._rutas_imagen_en_texto(salida)
    assert rutas == [
        "/tmp/keni-skills-x/foto-feed.png",
        "/tmp/keni-skills-x/foto-cuadrado.PNG",
    ]


def test_rutas_imagen_en_texto_vacio():
    assert skills._rutas_imagen_en_texto("") == []
    assert skills._rutas_imagen_en_texto("sin ninguna ruta de imagen aquí") == []


def test_importar_imagen_copia_al_media(entorno):
    origen = entorno / "salida.png"
    origen.write_bytes(_PNG_1x1)
    nombre = media.importar_imagen(origen)
    assert nombre.endswith(".png")
    # El archivo importado vive en el almacen de media y es servible por su nombre.
    destino = media.resolver_media(nombre)
    assert destino is not None and destino.is_file()
    assert destino.read_bytes() == _PNG_1x1


def test_importar_imagen_ruta_inexistente_lanza(entorno):
    import pytest

    with pytest.raises(media.MediaError):
        media.importar_imagen(entorno / "no-existe.png")


def test_importar_imagen_no_imagen_lanza(entorno):
    txt = entorno / "nota.txt"
    txt.write_text("hola", encoding="utf-8")
    import pytest

    with pytest.raises(media.MediaError):
        media.importar_imagen(txt)


def test_cosechar_imagenes_omite_lo_que_no_existe(entorno):
    real = entorno / "real.png"
    real.write_bytes(_PNG_1x1)
    salida = f"hecho -> {real}\notra (fantasma) -> {entorno / 'fantasma.png'}\n"
    imagenes = skills.cosechar_imagenes(salida)
    # Solo la que existe se importa; la fantasma se omite (no rompe).
    assert len(imagenes) == 1
    assert imagenes[0]["url"].startswith("/api/media/")
    assert imagenes[0]["nombre"].endswith(".png")


# --------------------------------------------------------------------------- #
# Flujo end-to-end via el endpoint                                            #
# --------------------------------------------------------------------------- #


def _resultado(respuesta) -> dict:
    cuerpo = respuesta.json()
    gen = cuerpo["generacion"]
    assert gen["estado"] == "completado", gen
    return gen["resultado"]


def test_ejecutar_skill_imagen_previsualiza_y_sirve(entorno):
    _sembrar_skill_imagen(entorno)
    # La herramienta dejaria el .png en disco; lo simulamos escribiendolo.
    png = entorno / "foto-feed.png"
    png.write_bytes(_PNG_1x1)

    salida = (
        "✅ LISTO PARA APROBAR\n\n"
        "# Estudio de imagen — recorte a feed\n"
        "## Qué hice\n"
        f"- recortar feed (1080x1350)  ->  {png}\n\n"
        "## Revisión (legal/editorial)\n- Todo en orden.\n"
    )
    cli = _cliente(lanzar_generacion=lanzador_generacion_completa(salida))
    r = cli.post(
        "/api/skills/ejecutar",
        json={"skill": "estudio-imagen", "marca": "claro-sports",
              "valores": {"peticion": "recórtame esta foto a feed"}},
    )
    assert r.status_code == 200
    res = _resultado(r)
    # Salida documento + imagenes previsualizables.
    assert "documento" in res
    assert res["verdicto"] == "listo"
    assert res["piezas"] == []
    assert res["publicaciones"] == []
    assert "imagenes" in res and len(res["imagenes"]) == 1
    url = res["imagenes"][0]["url"]
    assert url.startswith("/api/media/")

    # La imagen previsualizada se SIRVE de verdad por la API de media.
    img = cli.get(url)
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == _PNG_1x1
