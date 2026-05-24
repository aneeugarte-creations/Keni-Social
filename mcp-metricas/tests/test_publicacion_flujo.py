"""Tests del flujo de aprobacion punta-a-punta (DRY-RUN salvo donde se mockea).

Cubren: construccion de borradores desde entrada (dict / JSON / TOML), encolado
(incluido el agendado), y que el dry-run devuelve los payloads esperados SIN
ninguna peticion de red. Tambien el gating de la publicacion real en la CLI.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest
import respx
from pydantic import ValidationError

from keni_metricas.publicacion import AdaptadorPublicacionMeta, ColaPublicacion
from keni_metricas.publicacion.flujo import (
    EntradaPublicacion,
    cargar_entradas,
    construir_borradores,
    ejecutar_flujo,
    llenar_cola,
    main,
    parsear_entradas,
    render_reporte,
)
from keni_metricas.publicacion.meta import BASE, PublicacionNoConfigurada
from keni_metricas.schema import Plataforma

AHORA = datetime(2026, 5, 24, 12, 0, 0)


def _entrada_fb_dict(texto: str = "Hola FB") -> dict:
    return {"plataforma": "facebook", "cuenta": "PAGE", "texto": texto}


def _entrada_ig_dict() -> dict:
    return {
        "plataforma": "instagram",
        "cuenta": "IGID",
        "texto": "Hola IG",
        "media": [{"tipo": "imagen", "url": "https://e/x.jpg"}],
        "hashtags": ["#Deporte", "Deporte", "futbol"],
    }


# --- parseo / construccion de borradores -----------------------------------
def test_parsear_dict_suelto_construye_borrador():
    entradas = parsear_entradas(_entrada_fb_dict("uno"))
    assert len(entradas) == 1
    b = entradas[0].a_borrador()
    assert b.plataforma is Plataforma.facebook
    assert b.cuenta == "PAGE"
    assert b.texto_final() == "uno"


def test_parsear_clave_publicaciones_lista():
    datos = {"publicaciones": [_entrada_fb_dict("a"), _entrada_ig_dict()]}
    entradas = parsear_entradas(datos)
    assert [e.plataforma for e in entradas] == [Plataforma.facebook, Plataforma.instagram]


def test_parsear_lista_directa():
    entradas = parsear_entradas([_entrada_fb_dict("a"), _entrada_fb_dict("b")])
    assert len(entradas) == 2


def test_construir_borradores_aplica_validacion_y_hashtags():
    entradas = parsear_entradas(_entrada_ig_dict())
    borradores = construir_borradores(entradas)
    b = borradores[0]
    # hashtags normalizados (sin '#', sin duplicados, en orden)
    assert b.hashtags == ["Deporte", "futbol"]
    assert b.texto_final() == "Hola IG\n\n#Deporte #futbol"


def test_entrada_plataforma_no_meta_falla():
    with pytest.raises(ValidationError):
        EntradaPublicacion.model_validate({"plataforma": "tiktok", "cuenta": "X"}).a_borrador()


def test_parsear_publicaciones_no_lista_falla():
    with pytest.raises(ValueError, match="lista"):
        parsear_entradas({"publicaciones": {"plataforma": "facebook", "cuenta": "X"}})


# --- carga desde archivo (JSON / TOML) -------------------------------------
def test_cargar_entradas_json(tmp_path):
    ruta = tmp_path / "pubs.json"
    ruta.write_text(
        json.dumps({"publicaciones": [_entrada_fb_dict("desde json"), _entrada_ig_dict()]}),
        encoding="utf-8",
    )
    entradas = cargar_entradas(ruta)
    assert len(entradas) == 2
    assert entradas[0].texto == "desde json"


def test_cargar_entradas_toml(tmp_path):
    ruta = tmp_path / "pubs.toml"
    ruta.write_text(
        """
        [[publicaciones]]
        plataforma = "facebook"
        cuenta = "PAGE"
        texto = "desde toml"

        [[publicaciones]]
        plataforma = "instagram"
        cuenta = "IGID"
        texto = "ig toml"
        hashtags = ["deporte"]

          [[publicaciones.media]]
          tipo = "imagen"
          url = "https://e/x.jpg"
        """,
        encoding="utf-8",
    )
    entradas = cargar_entradas(ruta)
    assert len(entradas) == 2
    assert entradas[0].texto == "desde toml"
    assert entradas[1].media[0].url == "https://e/x.jpg"


def test_cargar_entradas_extension_no_soportada(tmp_path):
    ruta = tmp_path / "pubs.yaml"
    ruta.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Extension no soportada"):
        cargar_entradas(ruta)


# --- encolado ---------------------------------------------------------------
def test_llenar_cola_respeta_publicar_en():
    entradas = parsear_entradas(
        [
            {**_entrada_fb_dict("ya")},
            {**_entrada_fb_dict("futuro"), "publicar_en": "2026-05-24T18:00:00"},
        ]
    )
    cola = llenar_cola(entradas, AdaptadorPublicacionMeta(creds={}))
    assert isinstance(cola, ColaPublicacion)
    assert len(cola.items) == 2
    assert cola.items[0].publicar_en is None
    assert cola.items[1].publicar_en == datetime(2026, 5, 24, 18, 0, 0)


# --- dry-run: payloads esperados y CERO red ---------------------------------
@respx.mock
def test_flujo_dry_run_payloads_y_cero_red():
    # Mockeamos las rutas para detectar CUALQUIER toque de red.
    respx.post(f"{BASE}/PAGE/feed").mock(return_value=httpx.Response(200, json={"id": "x"}))
    respx.post(f"{BASE}/IGID/media").mock(return_value=httpx.Response(200, json={"id": "x"}))
    respx.post(f"{BASE}/IGID/media_publish").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )

    entradas = parsear_entradas([_entrada_fb_dict("Hola FB"), _entrada_ig_dict()])
    res = ejecutar_flujo(entradas, ahora=AHORA)  # dry-run por defecto

    assert res.dry_run is True
    assert res.encolados == 2
    assert len(res.resultados) == 2  # ambas sin hora -> vencidas ya

    fb, ig = res.resultados
    assert fb.plataforma is Plataforma.facebook
    assert fb.peticiones[0].paso == "fb_feed"
    assert fb.peticiones[0].url == f"{BASE}/PAGE/feed"
    assert fb.peticiones[0].data == {"message": "Hola FB"}

    pasos_ig = [p.paso for p in ig.peticiones]
    assert pasos_ig == ["ig_container", "ig_publish"]
    assert ig.peticiones[0].data == {
        "image_url": "https://e/x.jpg",
        "caption": "Hola IG\n\n#Deporte #futbol",
    }

    # propiedad central de seguridad: CERO peticiones reales
    assert respx.calls.call_count == 0
    # dry-run no consume la cola (no se marca publicado): no se observa aqui pero
    # se garantiza por ColaPublicacion; el flujo no debe filtrar el token.
    for r in res.resultados:
        for pet in r.peticiones:
            assert "access_token" not in pet.data


def test_flujo_dry_run_es_el_defecto():
    """ejecutar_flujo sin publicar_real debe ser dry-run (cero red garantizada)."""
    entradas = parsear_entradas(_entrada_fb_dict("x"))
    res = ejecutar_flujo(entradas, ahora=AHORA)
    assert res.dry_run is True


def test_flujo_no_dispara_agendado_futuro():
    entradas = parsear_entradas(
        [{**_entrada_fb_dict("futuro"), "publicar_en": (AHORA + timedelta(days=1)).isoformat()}]
    )
    res = ejecutar_flujo(entradas, ahora=AHORA)
    assert res.encolados == 1
    assert res.resultados == []  # agendado a futuro: no vence


def test_flujo_publicar_real_sin_token_no_toca_red():
    """publicar_real=True sin token => PublicacionNoConfigurada ANTES de red."""
    entradas = parsear_entradas(_entrada_fb_dict("x"))
    with pytest.raises(PublicacionNoConfigurada):
        ejecutar_flujo(
            entradas,
            adaptador=AdaptadorPublicacionMeta(creds={}),
            ahora=AHORA,
            publicar_real=True,
        )


# --- camino REAL (mockeado) -------------------------------------------------
@respx.mock
def test_flujo_publicar_real_con_token_hace_post():
    ruta = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "PAGE_1"})
    )
    entradas = parsear_entradas(_entrada_fb_dict("real"))
    res = ejecutar_flujo(
        entradas,
        adaptador=AdaptadorPublicacionMeta(creds={"access_token": "tok"}),
        ahora=AHORA,
        publicar_real=True,
    )
    assert ruta.called
    assert res.dry_run is False
    assert res.resultados[0].id_publicacion == "PAGE_1"


# --- reporte ----------------------------------------------------------------
def test_render_reporte_dry_run_legible():
    entradas = parsear_entradas([_entrada_fb_dict("Hola"), _entrada_ig_dict()])
    res = ejecutar_flujo(entradas, ahora=AHORA)
    texto = render_reporte(res, entradas)
    assert "DRY-RUN" in texto
    assert "NADA se ha publicado" in texto
    assert "PAGE/feed" in texto
    assert "ig_container" in texto and "ig_publish" in texto
    assert "Encolados: 2" in texto


def test_render_reporte_muestra_agendado_no_vencido():
    entradas = parsear_entradas(
        [{**_entrada_fb_dict("futuro"), "publicar_en": (AHORA + timedelta(days=1)).isoformat()}]
    )
    res = ejecutar_flujo(entradas, ahora=AHORA)
    texto = render_reporte(res, entradas)
    assert "Encolado" in texto
    assert "nada vencido a esta hora" in texto


# --- CLI --------------------------------------------------------------------
@respx.mock
def test_cli_dry_run_json_sin_red(tmp_path, capsys):
    ruta_red = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )
    archivo = tmp_path / "pubs.json"
    archivo.write_text(json.dumps(_entrada_fb_dict("Hola CLI")), encoding="utf-8")

    code = main([str(archivo), "--formato", "json"])
    assert code == 0
    salida = capsys.readouterr().out
    assert '"dry_run": true' in salida
    assert "PAGE/feed" in salida
    assert not ruta_red.called
    assert respx.calls.call_count == 0


@respx.mock
def test_cli_publicar_real_sin_confirmacion_bloquea(tmp_path, capsys):
    ruta_red = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )
    archivo = tmp_path / "pubs.json"
    archivo.write_text(json.dumps(_entrada_fb_dict("x")), encoding="utf-8")

    code = main([str(archivo), "--publicar-real"])  # sin --si-publicar
    assert code == 2
    err = capsys.readouterr().err
    assert "confirmacion" in err
    assert not ruta_red.called  # bloqueado ANTES de cualquier red


@respx.mock
def test_cli_publicar_real_confirmado_sin_token_falla_sin_red(tmp_path, capsys):
    ruta_red = respx.post(f"{BASE}/PAGE/feed").mock(
        return_value=httpx.Response(200, json={"id": "x"})
    )
    archivo = tmp_path / "pubs.json"
    archivo.write_text(json.dumps(_entrada_fb_dict("x")), encoding="utf-8")

    # La CLI no carga credenciales => sin token => falla, sin tocar la red.
    code = main([str(archivo), "--publicar-real", "--si-publicar"])
    assert code == 1
    assert not ruta_red.called
    assert respx.calls.call_count == 0


def test_cli_archivo_inexistente(capsys):
    code = main(["/no/existe/pubs.json"])
    assert code == 2
    assert "no existe" in capsys.readouterr().err


def test_cli_entrada_invalida(tmp_path, capsys):
    archivo = tmp_path / "pubs.json"
    archivo.write_text(json.dumps({"plataforma": "tiktok", "cuenta": "X"}), encoding="utf-8")
    code = main([str(archivo)])
    assert code == 2
    assert "Error en la entrada" in capsys.readouterr().err


def test_b6_cli_flujo_error_pydantic_sin_url_ni_ingles(tmp_path, capsys):
    """B6: el CLI del flujo mostraba el dump de pydantic (ingles + URL).

    Ahora extrae solo el mensaje limpio del primer error (en espanol).
    """
    archivo = tmp_path / "pubs.json"
    archivo.write_text(json.dumps({"plataforma": "tiktok", "cuenta": "X"}), encoding="utf-8")
    code = main([str(archivo)])
    assert code == 2
    err = capsys.readouterr().err
    assert "Error en la entrada" in err
    assert "Entrada para Meta solo admite" in err  # mensaje del validador, en espanol
    assert "errors.pydantic.dev" not in err  # sin la URL
    assert "validation error for" not in err  # sin el dump en ingles
    assert "input_value=" not in err
