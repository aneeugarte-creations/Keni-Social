"""Tests de la Crítica IA (post-aprobación con visión): nivel final de la cadena del feed.

Dos capas:
  - PURAS (sin DB, corren siempre en CI): parseo del revision JSON, textos del comentario,
    elección del arte a prefetchear.
  - INTEGRACIÓN (fixture `entorno`, Postgres en CI): con `KENI_CRITICA_IA` ON, `enviar_a_revision`
    añade el nivel IA AL FINAL; los dos OK humanos NO programan (dejan la IA pendiente); nadie
    decide el nivel IA a mano; y el voto del crítico (aprueba → programa / rechaza → dislike +
    comentario que frena) se aplica con `aplicar_revision`. El override `forzar` desbloquea.

El encolado real del worker (`lanzar_para_publicacion`) se monkeypatchea en los tests de flujo:
aquí probamos el cableado de la cadena y el efecto del voto, no la ejecución de `claude -p`.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from keni_consola import app as app_modulo
from keni_consola import auth, config, repos
from keni_consola.dominio import colaboracion, critica_ia

from .conftest import TOKEN_PRUEBA

_ORIGIN = {"Origin": "http://testserver"}
_CLAVE = "clave-de-prueba-123"
_MARCA = "unotv"


# --------------------------------------------------------------------------- #
# PURAS (sin DB)                                                               #
# --------------------------------------------------------------------------- #


def test_parsear_revision_json_plano():
    v = critica_ia._parsear_revision('{"veredicto": "aprueba", "problemas": []}')
    assert v == {"veredicto": "aprueba", "problemas": []}


def test_parsear_revision_dentro_de_valla_de_codigo():
    salida = 'Aquí va mi juicio:\n```json\n{"veredicto": "rechaza", "comentario": "arte falso"}\n```\n'
    v = critica_ia._parsear_revision(salida)
    assert v["veredicto"] == "rechaza"
    assert v["comentario"] == "arte falso"


def test_parsear_revision_con_texto_alrededor():
    v = critica_ia._parsear_revision('blah blah {"veredicto": "aprueba"} fin')
    assert v == {"veredicto": "aprueba"}


def test_parsear_revision_ilegible_es_none():
    assert critica_ia._parsear_revision("") is None
    assert critica_ia._parsear_revision("no hay json aquí") is None
    assert critica_ia._parsear_revision("{roto") is None


def test_texto_comentario_lista_problemas_y_recomendacion():
    v = {
        "veredicto": "rechaza",
        "comentario": "La imagen es sintética.",
        "problemas": [
            {"tipo": "arte_sintetico", "severidad": "alta", "detalle": "humanos irreales"},
            {"tipo": "coherencia", "severidad": "alta", "detalle": "el titular no entrega el dato"},
        ],
        "recomendacion_formato": "carrusel",
    }
    texto = critica_ia._texto_comentario(v)
    assert "sintética" in texto
    assert "humanos irreales" in texto
    assert "no entrega el dato" in texto
    assert "carrusel" in texto.lower()


def test_texto_comentario_sin_revision_pide_revision_humana():
    texto = critica_ia._texto_comentario(None)
    assert "revisa" in texto.lower()


def test_resumen_nivel_aprobado_vs_rechazado():
    assert "sin objeciones" in critica_ia._resumen_nivel({"veredicto": "aprueba"}, "aprobado").lower()
    r = critica_ia._resumen_nivel({"comentario": "imagen falsa"}, "rechazado")
    assert "imagen falsa" in r


def test_arte_para_prefetch_prefiere_foto_real():
    clave, ext = critica_ia._arte_para_prefetch({"foto": "abc.jpeg", "imagen": "placa.png"})
    assert clave == "abc.jpeg" and ext == "jpeg"


def test_arte_para_prefetch_cae_a_imagen_si_no_hay_foto():
    clave, ext = critica_ia._arte_para_prefetch({"foto": "", "imagen": "placa.png"})
    assert clave == "placa.png" and ext == "png"


def test_arte_para_prefetch_sin_arte():
    assert critica_ia._arte_para_prefetch({"imagen_fuente": "http://x/y.jpg"}) == ("", "")


# --------------------------------------------------------------------------- #
# INTEGRACIÓN (fixture `entorno`, Postgres en CI)                              #
# --------------------------------------------------------------------------- #


def _app():
    return app_modulo.crear_app(token=TOKEN_PRUEBA, bootstrap=False)


def _cli_usuario(usuario: str, rol: str = "editor") -> TestClient:
    auth.crear_usuario(usuario, _CLAVE, rol)
    c = TestClient(_app())
    r = c.post("/api/auth/login", json={"usuario": usuario, "password": _CLAVE}, headers=_ORIGIN)
    assert r.status_code == 200
    return c


def _crear_borrador(cli: TestClient, **campos) -> dict:
    base = {"marca": _MARCA, "red": "x", "titulo": "T", "contenido": "C"}
    base.update(campos)
    r = cli.post("/api/publicaciones", json=base, headers=_ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()["publicacion"]


def _activar_flag(monkeypatch, *, encolado=None):
    """Enciende `KENI_CRITICA_IA` y (opcional) sustituye el lanzador del worker por un recorder."""
    monkeypatch.setattr(config, "critica_ia_activa", lambda: True)
    if encolado is not None:
        monkeypatch.setattr(critica_ia, "lanzar_para_publicacion", encolado)


def _a_ia_pendiente(monkeypatch) -> tuple[str, list]:
    """Lleva una pieza a «dos OK humanos + nivel IA pendiente». Devuelve (pid, llamadas_lanzar)."""
    llamadas: list[str] = []
    _activar_flag(monkeypatch, encolado=lambda pid: llamadas.append(pid))
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    pid = pub["id"]
    autora.post(f"/api/aprobacion/{pid}/enviar-a-revision", headers=_ORIGIN)
    _cli_usuario("beto").post(f"/api/aprobacion/{pid}/aprobar", headers=_ORIGIN)
    _cli_usuario("caro").post(f"/api/aprobacion/{pid}/aprobar", headers=_ORIGIN)
    return pid, llamadas


def test_enviar_a_revision_anade_nivel_ia_al_final(entorno, monkeypatch):
    _activar_flag(monkeypatch)
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    cadena = repos.listar_aprobaciones(pub["id"])
    assert len(cadena) == 3
    ultimo = sorted(cadena, key=lambda n: n["nivel"])[-1]
    assert colaboracion.es_nivel_critica_ia(ultimo)
    assert ultimo["etiqueta"] == colaboracion.ETIQUETA_CRITICA_IA


def test_sin_flag_la_cadena_es_de_dos_niveles(entorno, monkeypatch):
    monkeypatch.setattr(config, "critica_ia_activa", lambda: False)
    autora = _cli_usuario("ana")
    pub = _crear_borrador(autora)
    autora.post(f"/api/aprobacion/{pub['id']}/enviar-a-revision", headers=_ORIGIN)
    cadena = repos.listar_aprobaciones(pub["id"])
    assert len(cadena) == 2
    assert colaboracion.nivel_critica_ia(cadena) is None


def test_dos_ok_humanos_no_programan_y_encolan_la_critica(entorno, monkeypatch):
    pid, llamadas = _a_ia_pendiente(monkeypatch)
    pub = repos.obtener_publicacion(pid)
    # La pieza NO pasa a aprobado/programado: queda en revisión esperando a la IA.
    assert pub["estado"] == "en_revision"
    # El hook encoló la crítica exactamente una vez al cerrarse la parte humana.
    assert llamadas == [pid]
    # El nivel IA sigue pendiente.
    assert colaboracion.nivel_critica_ia(repos.listar_aprobaciones(pid))["decision"] == "pendiente"


def test_humano_no_puede_decidir_el_nivel_ia(entorno, monkeypatch):
    pid, _ = _a_ia_pendiente(monkeypatch)
    # Una cuarta persona intenta «aprobar» cuando el nivel actual es el de la IA: 409 claro.
    r = _cli_usuario("dani").post(f"/api/aprobacion/{pid}/aprobar", headers=_ORIGIN)
    assert r.status_code == 409
    assert "crítica ia" in r.json()["error"].lower()


def test_revision_aprueba_completa_la_cadena(entorno, monkeypatch):
    pid, _ = _a_ia_pendiente(monkeypatch)
    decision = critica_ia.aplicar_revision(pid, {"veredicto": "aprueba", "problemas": []})
    assert decision == "aprobado"
    pub = repos.obtener_publicacion(pid)
    # Sin franja no se inventa fecha: queda aprobada (programar es ortogonal, ya cubierto aparte).
    assert pub["estado"] in ("aprobado", "programado")
    ia = colaboracion.nivel_critica_ia(repos.listar_aprobaciones(pid))
    assert ia["decision"] == "aprobado"
    assert ia["decisor_id"] == colaboracion.DECISOR_CRITICA_ID


def test_revision_rechaza_deja_dislike_y_comentario_que_frena(entorno, monkeypatch):
    pid, _ = _a_ia_pendiente(monkeypatch)
    decision = critica_ia.aplicar_revision(
        pid,
        {
            "veredicto": "rechaza",
            "comentario": "La imagen es sintética; cámbiala por una foto real.",
            "problemas": [{"tipo": "arte_sintetico", "severidad": "alta", "detalle": "humanos irreales"}],
        },
    )
    assert decision == "rechazado"
    pub = repos.obtener_publicacion(pid)
    # Dislike de IA: la pieza NO se aprueba; queda en revisión con la objeción.
    assert pub["estado"] == "en_revision"
    ia = colaboracion.nivel_critica_ia(repos.listar_aprobaciones(pid))
    assert ia["decision"] == "rechazado"
    # Hay un comentario SIN resolver (gate B): frena la programación.
    plat = repos.obtener_contenido_plataforma(pid)
    assert repos.comentarios_sin_resolver(plat["contenido_id"], pid) >= 1


def test_revision_ilegible_rechaza_por_seguridad(entorno, monkeypatch):
    pid, _ = _a_ia_pendiente(monkeypatch)
    decision = critica_ia.aplicar_revision(pid, None)
    assert decision == "rechazado"
    assert repos.obtener_publicacion(pid)["estado"] == "en_revision"


def test_forzar_override_de_un_dislike_de_ia(entorno, monkeypatch):
    pid, _ = _a_ia_pendiente(monkeypatch)
    critica_ia.aplicar_revision(
        pid, {"veredicto": "rechaza", "comentario": "arte sintético"}
    )
    # Un coordinador FUERZA la pieza a pesar del dislike: queda aprobada y la objeción se cierra.
    coord = _cli_usuario("jefa", rol="admin")
    r = coord.post(f"/api/aprobacion/{pid}/forzar", headers=_ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["publicacion"]["estado"] in ("aprobado", "programado")
    plat = repos.obtener_contenido_plataforma(pid)
    assert repos.comentarios_sin_resolver(plat["contenido_id"], pid) == 0
