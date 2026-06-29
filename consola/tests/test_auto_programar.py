"""Auto-programación: una pieza con sus 2 OK se encola SOLA a su próximo hueco.

COLAPSO 2026-06: ya no hay estado de reposo `aprobado`. Una pieza queda `en_revision` con su
cadena de likes; cuando junta el mínimo de OK, `programar_si_aprobada` la mueve a `programado`
si hay hueco (si no, sigue `en_revision`). Los helpers de aquí montan esa cadena ya aprobada.

OFFLINE (Postgres de pruebas vía fixture `cliente`). Igual que los tests de `encolar`,
inyectamos un "ahora" fijo parcheando el `datetime` del módulo de piezas (de donde
`calcular_hueco_para` lee `now()`), de modo que el hueco calculado sea determinista.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from keni_consola import auto_programar, repos
from keni_consola.api import piezas as ap

# Miércoles 2026-05-20 10:00 (weekday()==2).
_AHORA = datetime(2026, 5, 20, 10, 0)


class _AhoraFijo(datetime):
    @classmethod
    def now(cls, tz=None):  # noqa: ANN001
        return _AHORA


@pytest.fixture
def ahora_fijo(monkeypatch):
    """Ancla `datetime.now()` del módulo de piezas (lo usa el cálculo de hueco)."""
    # `calcular_hueco_para` (lee `datetime.now()`) vive en el submódulo `programacion`: el ancla
    # se parchea ahí, no en el facade del paquete.
    monkeypatch.setattr(ap.programacion, "datetime", _AhoraFijo)
    return _AHORA


def _sellar_cadena_aprobada(pid: str) -> None:
    """Monta una cadena de 2 niveles y los SELLA aprobados (los 2 OK), lista para auto-programar."""
    plat = repos.obtener_pieza_fila(pid)
    repos.crear_cadena_aprobacion(
        pieza_id=pid,
        publicacion_id=plat["publicacion_id"],
        etiquetas=["Edición", "Coordinación"],
        cargos=["", ""],
    )
    for i, nivel in enumerate(repos.listar_aprobaciones(pid)):
        repos.actualizar_aprobacion(
            nivel["id"],
            {
                "decision": "aprobado",
                "decisor_id": f"rev{i}",
                "decisor_nombre": f"Rev{i}",
                "decidido_en": "2026-05-20T09:00",
            },
        )


def _crear_aprobada(cliente, **campos) -> str:
    """Crea una pieza `en_revision` con su cadena de 2 OK YA aprobada (lista para auto-programar).

    Si se pasa otro `estado` (p. ej. `borrador`), se crea tal cual SIN cadena (para los tests que
    comprueban que la auto-programación no toca lo que no está en revisión con sus likes).
    """
    base = {"marca": "unotv", "red": "x", "titulo": "T", "contenido": "C", "estado": "en_revision"}
    base.update(campos)
    r = cliente.post("/api/piezas", json=base)
    assert r.status_code == 200, r.text
    pid = r.json()["pieza"]["id"]
    if base["estado"] == "en_revision":
        _sellar_cadena_aprobada(pid)
    return pid


def test_aprobada_sin_franja_se_queda_en_revision(cliente, ahora_fijo):
    # Sin franja aplicable NO se inventa fecha: la pieza se queda en revisión (con sus likes).
    pid = _crear_aprobada(cliente)
    assert auto_programar.programar_si_aprobada(pid) is None
    assert repos.obtener_pieza(pid)["estado"] == "en_revision"


def test_aprobada_se_programa_en_proximo_hueco(cliente, ahora_fijo):
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})  # mié 15:00
    pid = _crear_aprobada(cliente)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["estado"] == "programado"
    assert actualizada["fecha_programada"] == "2026-05-20T15:00"


def test_no_reusa_hueco_de_una_publicada_con_fecha_futura(cliente, ahora_fijo):
    """Una pieza `publicado` cuya fecha sigue en el FUTURO aún reserva su hueco: una nueva
    aprobada NO debe caer en el mismo minuto. (El índice de unicidad es parcial —solo
    'programado'—, así que el cálculo de hueco lo cubre explícitamente.)"""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})  # mié 15:00
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "16:00"})  # mié 16:00
    # Publicada (misma marca/red) ocupando el slot de las 15:00, con fecha aún futura.
    repos.crear_pieza(
        "unotv", "x", titulo="Pub futura", contenido="C",
        estado="publicado", fecha_programada="2026-05-20T15:00",
    )
    pid = _crear_aprobada(cliente)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    # 15:00 está ocupado por la publicada-futura -> cae en el siguiente hueco (16:00).
    assert actualizada["fecha_programada"] == "2026-05-20T16:00"


def test_no_programa_en_hueco_demasiado_proximo(cliente, ahora_fijo):
    """GUARDIA anti-"tiempo vencido": un hueco a menos del margen mínimo (ahora+5) no sirve para
    publicar a tiempo, así que se SALTA al siguiente. Con `ahora`=10:00, la franja de las 10:03
    queda por debajo del piso (10:05) y se cae a la de las 11:00."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "10:03"})  # demasiado pronto
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "11:00"})  # primer hueco válido
    pid = _crear_aprobada(cliente)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T11:00"


def _vincular_cluster(pid: str, *, categoria: str = "mx", breaking: int = 0) -> None:
    """Vincula la pieza a una HISTORIA del pool (cluster→contenido), como al promoverla."""
    plat = repos.obtener_pieza_fila(pid)
    assert plat and plat.get("publicacion_id")
    repos.upsert_noticia_cluster({
        "id": f"cl-{pid[:8]}", "titulo": "Historia origen", "resumen": "", "marca": "unotv",
        "categoria": categoria, "geo": "MX", "clave": f"t:{pid[:8]}", "n_items": 1,
        "n_fuentes": 2, "idiomas": ["es"], "senal": 0, "score": 0.7, "breaking": breaking,
        "primer_visto": "2026-05-19T00:00:00", "ultimo_visto": "2026-05-19T00:00:00",
        "estado": "usado", "verificacion": "corroborada",
    })
    repos.actualizar_noticia_cluster(f"cl-{pid[:8]}", publicacion_id=plat["publicacion_id"])


def test_breaking_se_programa_al_instante(cliente, ahora_fijo):
    """Una pieza BREAKING no espera franja: se programa a ahora+margen (minuto libre)."""
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, breaking=1)
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T10:05"  # _AHORA + _MARGEN_MINIMO_MIN


def test_categoria_usa_sus_horarios_del_plan(cliente, ahora_fijo):
    """Una pieza de una categoría se programa en las franjas de SU categoría, no en las genéricas."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "12:00"})  # genérica mié 12:00
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:45", "marca": "unotv", "categoria": "internacional"},
    )
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, categoria="internacional")
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T14:45"


def test_slug_de_categoria_se_traduce_a_linea_del_plan(cliente, ahora_fijo):
    """El plan guarda sus franjas con el ID de la LÍNEA; la pieza trae el SLUG editorial.

    `calcular_hueco_para` traduce slug -> id de línea, así que una pieza 'internacional' cae en la
    franja de la línea Internacional (su id), NO en la genérica. SIN la traducción, el slug no
    casaría con el id y la pieza caería en la genérica de las 12:00.
    """
    from keni_consola import bootstrap_categorias

    bootstrap_categorias.inicializar_categorias()  # siembra las líneas (categoria) de unotv
    et = repos.obtener_etiqueta_por_nombre("Internacional", "categoria", "unotv")
    assert et is not None, "la línea Internacional debe existir tras inicializar_categorias"
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "12:00", "marca": "unotv"})  # genérica
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:45", "marca": "unotv", "categoria": et["id"]},
    )
    pid = _crear_aprobada(cliente)
    _vincular_cluster(pid, categoria="internacional")
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T14:45"


def test_sin_categoria_sin_genericas_cae_al_plan(cliente, ahora_fijo):
    """Marca de una línea sin franjas genéricas: una pieza sin categoría usa el plan, no se queda
    sin programar."""
    from keni_consola import bootstrap_categorias

    bootstrap_categorias.inicializar_categorias()
    et = repos.obtener_etiqueta_por_nombre("Internacional", "categoria", "unotv")
    assert et is not None
    # ÚNICA franja de la marca, con categoría de línea (no hay genérica).
    cliente.post(
        "/api/franjas",
        json={"dia_semana": 2, "hora": "14:45", "marca": "unotv", "categoria": et["id"]},
    )
    pid = _crear_aprobada(cliente)  # sin cluster -> categoría ''
    actualizada = auto_programar.programar_si_aprobada(pid)
    assert actualizada is not None
    assert actualizada["fecha_programada"] == "2026-05-20T14:45"


def test_redes_de_un_tema_comparten_hora(cliente, ahora_fijo):
    """El hueco se ocupa POR (marca, red): piezas del mismo tema en redes distintas salen a
    la MISMA hora (espejo del índice de unicidad de slot por marca+red+fecha)."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00", "marca": "unotv"})
    pid_x = _crear_aprobada(cliente, red="x")
    pid_ig = _crear_aprobada(cliente, red="instagram")
    a = auto_programar.programar_si_aprobada(pid_x)
    b = auto_programar.programar_si_aprobada(pid_ig)
    assert a is not None and b is not None
    assert a["fecha_programada"] == b["fecha_programada"] == "2026-05-20T15:00"


def test_no_programa_si_no_esta_aprobada(cliente, ahora_fijo):
    # Solo actúa sobre `en_revision` con sus likes: un borrador con franja disponible NO se toca.
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    pid = _crear_aprobada(cliente, estado="borrador")
    assert auto_programar.programar_si_aprobada(pid) is None
    assert repos.obtener_pieza(pid)["estado"] == "borrador"


def test_no_resucita_si_dejo_de_estar_aprobada(cliente, ahora_fijo, monkeypatch):
    """CARRERA (CAS): entre que la auto-programación lee la pieza `en_revision` y escribe
    `programado`, otro flujo la movió (p. ej. una edición la resetea a `borrador`). El CAS sobre
    `estado` evita RESUCITARLA a `programado` pisando el estado/fecha que dejó el humano."""
    cliente.post("/api/franjas", json={"dia_semana": 2, "hora": "15:00"})
    pid = _crear_aprobada(cliente)

    real_hueco = ap.programacion.calcular_hueco_para

    def _hueco_con_carrera(pub, ahora=None):  # noqa: ANN001
        # Simula la carrera: la pieza deja de estar en revisión (vuelve a borrador) JUSTO antes de
        # la escritura, como si otro flujo la editara entre la lectura y el UPDATE condicional.
        repos.actualizar_pieza(pid, {"estado": "borrador", "fecha_programada": ""})
        return real_hueco(pub, ahora)

    # `_encolar_en_hueco_libre` llama a `calcular_hueco_para` del submódulo `programacion`: el
    # parche debe vivir ahí para que el encolado lo recoja (no en el facade del paquete).
    monkeypatch.setattr(ap.programacion, "calcular_hueco_para", _hueco_con_carrera)
    # No la programa (el CAS no aplica) y no lanza: best-effort.
    assert auto_programar.programar_si_aprobada(pid) is None
    despues = repos.obtener_pieza(pid)
    assert despues["estado"] == "borrador"  # sigue en el estado nuevo, NO resucitada
    assert despues["fecha_programada"] == ""  # ni le pisó la fecha
