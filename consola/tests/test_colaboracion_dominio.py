"""Tests de la LOGICA PURA de la cadena de aprobacion (`dominio.colaboracion`).

Tras la consolidacion (#9 → aprobacion unica), la aprobacion multinivel es el UNICO modelo:
una cadena de niveles ordenados sobre una pieza. Este modulo prueba la logica PURA (sin DB
ni HTTP): el resumen del estado global, que nivel toca decidir, la decision de un nivel
(orden + "otro par de ojos"), la cadena SIMPLE (defecto longitud 1) y el puente cadena ->
estado editorial de la publicacion (lo que lee el programador).

Son funciones puras: no hay Postgres, asi que NO se saltan (corren siempre, tambien en CI).
"""

from __future__ import annotations

from keni_consola.dominio import colaboracion


def _nivel(id_: str, nivel: int, decision: str = "pendiente") -> dict[str, object]:
    return {"id": id_, "nivel": nivel, "decision": decision, "etiqueta": f"N{nivel}"}


# --------------------------------------------------------------------------- #
# estado_cadena: resumen global de la cadena                                  #
# --------------------------------------------------------------------------- #


def test_estado_cadena_vacia_es_sin_cadena():
    assert colaboracion.estado_cadena([]) == "sin_cadena"


def test_estado_cadena_pendiente_si_quedan_niveles():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "pendiente")]
    assert colaboracion.estado_cadena(cadena) == "pendiente"


def test_estado_cadena_aprobado_si_todos_aprobados():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado")]
    assert colaboracion.estado_cadena(cadena) == "aprobado"


def test_estado_cadena_rechazado_si_algun_nivel_rechazado():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "rechazado")]
    assert colaboracion.estado_cadena(cadena) == "rechazado"


# --------------------------------------------------------------------------- #
# nivel_actual: el primer pendiente por orden                                 #
# --------------------------------------------------------------------------- #


def test_nivel_actual_es_el_primer_pendiente_por_orden():
    cadena = [_nivel("b", 2, "pendiente"), _nivel("a", 1, "aprobado"), _nivel("c", 3, "pendiente")]
    actual = colaboracion.nivel_actual(cadena)
    assert actual is not None and actual["id"] == "b"


def test_nivel_actual_none_si_cadena_completa():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado")]
    assert colaboracion.nivel_actual(cadena) is None


def test_nivel_actual_none_si_hay_rechazo():
    cadena = [_nivel("a", 1, "rechazado"), _nivel("b", 2, "pendiente")]
    assert colaboracion.nivel_actual(cadena) is None


# --------------------------------------------------------------------------- #
# decidir: orden + "otro par de ojos"                                         #
# --------------------------------------------------------------------------- #


def test_decidir_aprueba_el_nivel_actual():
    cadena = [_nivel("a", 1)]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u2", "usuario": "beto"}, rol="editor",
        autor_pieza_id="u1",
    )
    assert error is None
    assert campos is not None
    assert campos["decision"] == "aprobado"
    assert campos["decisor_nombre"] == "beto"
    assert campos["decidido_en"]


def test_decidir_rechaza_decision_invalida():
    cadena = [_nivel("a", 1)]
    _, error = colaboracion.decidir(
        cadena[0], cadena, "quiza", None, rol=None,
    )
    assert error is not None


def test_decidir_no_permite_saltarse_el_orden():
    cadena = [_nivel("a", 1, "pendiente"), _nivel("b", 2, "pendiente")]
    # Intentar decidir el nivel 2 cuando el 1 sigue pendiente.
    _, error = colaboracion.decidir(
        cadena[1], cadena, "aprobado", {"id": "u2", "usuario": "beto"}, rol="editor",
    )
    assert error is not None and "anteriores" in error.lower()


def test_decidir_no_permite_redecidir_un_nivel():
    cadena = [_nivel("a", 1, "aprobado")]
    _, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u2"}, rol="editor",
    )
    assert error is not None and "ya fue decidido" in error.lower()


def test_decidir_otro_par_de_ojos_bloquea_al_autor():
    cadena = [_nivel("a", 1)]
    _, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u1", "usuario": "ana"}, rol="editor",
        autor_pieza_id="u1",
    )
    assert error is not None and "tu propia pieza" in error.lower()


def test_decidir_admin_puede_aprobar_su_propia_pieza():
    cadena = [_nivel("a", 1)]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u1", "usuario": "jefa"}, rol="admin",
        autor_pieza_id="u1",
    )
    assert error is None and campos is not None


def test_decidir_token_mantenimiento_puede_decidir():
    cadena = [_nivel("a", 1)]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", None, rol=None, autor_pieza_id="u1",
    )
    assert error is None and campos is not None


# --------------------------------------------------------------------------- #
# cadena_simple: defecto longitud 1 = aprobacion simple                       #
# --------------------------------------------------------------------------- #


def test_cadena_simple_es_un_unico_nivel():
    etiquetas = colaboracion.cadena_simple()
    assert len(etiquetas) == 1
    assert isinstance(etiquetas[0], str) and etiquetas[0]


# --------------------------------------------------------------------------- #
# estado_publicacion_para: puente cadena -> estado editorial (programador)     #
# --------------------------------------------------------------------------- #


def test_estado_publicacion_para_aprobado():
    assert colaboracion.estado_publicacion_para("aprobado") == "aprobado"


def test_estado_publicacion_para_pendiente_es_en_revision():
    assert colaboracion.estado_publicacion_para("pendiente") == "en_revision"


def test_estado_publicacion_para_rechazado_vuelve_a_borrador():
    assert colaboracion.estado_publicacion_para("rechazado") == "borrador"


def test_estado_publicacion_para_sin_cadena_no_toca_estado():
    # Cadena vacia: ninguna aprobacion configurada -> no se altera el estado editorial.
    assert colaboracion.estado_publicacion_para("sin_cadena") is None
