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


def _nivel(
    id_: str, nivel: int, decision: str = "pendiente", decisor_id: str = ""
) -> dict[str, object]:
    return {
        "id": id_,
        "nivel": nivel,
        "decision": decision,
        "etiqueta": f"N{nivel}",
        "decisor_id": decisor_id,
    }


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


def test_estado_cadena_un_solo_rechazo_sigue_pendiente():
    # Un dislike NO para la cadena de dos niveles: falta el segundo para rechazar.
    cadena = [_nivel("a", 1, "rechazado"), _nivel("b", 2, "pendiente")]
    assert colaboracion.estado_cadena(cadena) == "pendiente"


def test_estado_cadena_rechazado_con_dos_dislikes():
    # Dos dislikes (de dos niveles) alcanzan el umbral: la pieza queda rechazada.
    cadena = [_nivel("a", 1, "rechazado"), _nivel("b", 2, "rechazado")]
    assert colaboracion.estado_cadena(cadena) == "rechazado"


def test_estado_cadena_un_ok_y_un_dislike_es_empate_pendiente():
    # Un OK y un dislike en la cadena de dos: ni aprobada ni rechazada (lo desatasca un coord).
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "rechazado")]
    assert colaboracion.estado_cadena(cadena) == "pendiente"


def test_estado_cadena_un_solo_nivel_se_rechaza_con_un_dislike():
    # En una cadena de 1 nivel no hay un segundo dislike que pedir: basta uno (umbral = 1).
    cadena = [_nivel("a", 1, "rechazado")]
    assert colaboracion.estado_cadena(cadena) == "rechazado"


def test_umbral_rechazo_es_dos_o_el_largo_de_la_cadena():
    assert colaboracion.umbral_rechazo([_nivel("a", 1), _nivel("b", 2), _nivel("c", 3)]) == 2
    assert colaboracion.umbral_rechazo([_nivel("a", 1)]) == 1
    assert colaboracion.umbral_rechazo([]) == 0


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


def test_nivel_actual_sigue_tras_un_solo_rechazo():
    # Un dislike aislado NO para la cadena: el siguiente nivel sigue disponible (segundo dislike).
    cadena = [_nivel("a", 1, "rechazado"), _nivel("b", 2, "pendiente")]
    actual = colaboracion.nivel_actual(cadena)
    assert actual is not None and actual["id"] == "b"


def test_nivel_actual_none_tras_dos_rechazos():
    # Alcanzado el umbral de rechazo, la cadena es terminal: no hay más decisiones útiles.
    cadena = [_nivel("a", 1, "rechazado"), _nivel("b", 2, "rechazado")]
    assert colaboracion.nivel_actual(cadena) is None


def test_nivel_actual_none_en_empate_sin_pendientes():
    # Un OK + un dislike (sin pendientes): empate, no hay nivel que decidir (lo fuerza un coord).
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "rechazado")]
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
# cadena_simple: defecto al mandar a revision = los dos OK (editor + coord)     #
# --------------------------------------------------------------------------- #


def test_cadena_simple_son_los_dos_ok():
    etiquetas = colaboracion.cadena_simple()
    assert etiquetas == ["Edición", "Coordinación"]


def test_decidir_misma_persona_no_da_los_dos_ok():
    """Quien ya decidio un nivel de la cadena no puede decidir el otro (segundo OK = otra persona)."""
    cadena = [
        _nivel("n1", 1, "aprobado") | {"decisor_id": "u2"},
        _nivel("n2", 2, "pendiente"),
    ]
    _, error = colaboracion.decidir(
        cadena[1], cadena, "aprobado", {"id": "u2", "usuario": "beto"}, rol="editor",
        autor_pieza_id="u1",
    )
    assert error is not None and "otra persona" in error.lower()


def test_decidir_admin_no_puede_dar_los_dos_ok_el_mismo():
    """Ni el admin firma los DOS OK: el segundo par de ojos no vale si es la misma persona."""
    cadena = [
        _nivel("n1", 1, "aprobado") | {"decisor_id": "u2"},
        _nivel("n2", 2, "pendiente"),
    ]
    campos, error = colaboracion.decidir(
        cadena[1], cadena, "aprobado", {"id": "u2", "usuario": "jefa"}, rol="admin",
        autor_pieza_id="u1",
    )
    assert campos is None and error is not None and "otra persona" in error.lower()


def test_decidir_admin_da_un_ok_de_pieza_propia():
    """El admin SÍ desatasca aprobar su PROPIA pieza (un OK), sin haber decidido otro nivel."""
    cadena = [_nivel("n1", 1, "pendiente"), _nivel("n2", 2, "pendiente")]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u1", "usuario": "jefa"}, rol="admin",
        autor_pieza_id="u1",
    )
    assert error is None and campos is not None


# --------------------------------------------------------------------------- #
# deshacer_decision: retirar la decision propia (toggle del feed)             #
# --------------------------------------------------------------------------- #


def test_deshacer_devuelve_el_nivel_propio():
    """El revisor retira SU OK: devuelve el id de su nivel para resetearlo a pendiente."""
    cadena = [
        _nivel("n1", 1, "aprobado", decisor_id="u2"),
        _nivel("n2", 2, "pendiente"),
    ]
    nivel_id, error = colaboracion.deshacer_decision(cadena, "u2")
    assert error is None and nivel_id == "n1"


def test_deshacer_un_dislike_propio():
    """También se retira un dislike propio (quita tu rechazo, vuelve a pendiente)."""
    cadena = [
        _nivel("n1", 1, "rechazado", decisor_id="u2"),
        _nivel("n2", 2, "pendiente"),
    ]
    nivel_id, error = colaboracion.deshacer_decision(cadena, "u2")
    assert error is None and nivel_id == "n1"


def test_deshacer_sin_decision_propia_falla():
    cadena = [_nivel("n1", 1, "aprobado", decisor_id="otro"), _nivel("n2", 2, "pendiente")]
    nivel_id, error = colaboracion.deshacer_decision(cadena, "u2")
    assert nivel_id is None and error is not None


def test_deshacer_sin_sesion_falla():
    cadena = [_nivel("n1", 1, "aprobado", decisor_id="u2")]
    nivel_id, error = colaboracion.deshacer_decision(cadena, "")
    assert nivel_id is None and error is not None


def test_deshacer_bloqueado_si_hay_decision_posterior():
    """No se deshace un nivel inferior si ya hay uno superior decidido (dejaría un hueco)."""
    cadena = [
        _nivel("n1", 1, "aprobado", decisor_id="u2"),
        _nivel("n2", 2, "aprobado", decisor_id="u3"),
    ]
    nivel_id, error = colaboracion.deshacer_decision(cadena, "u2")
    assert nivel_id is None and error is not None and "posterior" in error.lower()


def test_campos_nivel_pendiente_resetea_decisor_y_sello():
    campos = colaboracion.CAMPOS_NIVEL_PENDIENTE
    assert campos["decision"] == "pendiente"
    assert campos["decisor_id"] == "" and campos["decisor_nombre"] == ""
    assert campos["decidido_en"] == ""


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


# --------------------------------------------------------------------------- #
# Item A: minimo de aprobaciones (gate de gobernanza)                          #
# --------------------------------------------------------------------------- #


def test_contar_aprobados_cuenta_solo_los_aprobados():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado"), _nivel("c", 3, "pendiente")]
    assert colaboracion.contar_aprobados(cadena) == 2


def test_contar_aprobaciones_humanas_excluye_auto_y_pendientes():
    # Solo cuentan los OK con decisor HUMANO (id propio): ni el QA/pre-aprobación "auto" ni vacíos
    # ni los pendientes. Es la métrica de "aprobaciones reales que se pierden al editar".
    cadena = [
        {"id": "qa", "nivel": 1, "decision": "aprobado", "etiqueta": "QA Editorial", "decisor_id": "auto"},
        {"id": "ed", "nivel": 2, "decision": "aprobado", "etiqueta": "Edición", "decisor_id": "u7"},
        {"id": "co", "nivel": 3, "decision": "pendiente", "etiqueta": "Coordinación", "decisor_id": ""},
    ]
    assert colaboracion.contar_aprobaciones_humanas(cadena) == 1


def test_contar_aprobaciones_humanas_cero_si_solo_auto():
    cadena = [
        {"id": "qa", "nivel": 1, "decision": "aprobado", "etiqueta": "QA Editorial", "decisor_id": "auto"},
    ]
    assert colaboracion.contar_aprobaciones_humanas(cadena) == 0


def test_cumple_minimo_aprobaciones_no_cumple_devuelve_conteo():
    cadena = [_nivel("a", 1, "aprobado")]
    cumple, aprobados = colaboracion.cumple_minimo_aprobaciones(cadena, 2)
    assert cumple is False and aprobados == 1


def test_cumple_minimo_aprobaciones_cumple_con_justo():
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado")]
    cumple, aprobados = colaboracion.cumple_minimo_aprobaciones(cadena, 2)
    assert cumple is True and aprobados == 2


def test_cumple_minimo_cero_desactiva_el_gate():
    cumple, _ = colaboracion.cumple_minimo_aprobaciones([], 0)
    assert cumple is True


# --------------------------------------------------------------------------- #
# Item C: cargo requerido por nivel                                           #
# --------------------------------------------------------------------------- #


def test_cargo_requerido_por_etiqueta_del_organigrama():
    assert colaboracion.cargo_requerido_para("Coordinación") == "coordinador"
    assert colaboracion.cargo_requerido_para("Dirección") == "director"
    assert colaboracion.cargo_requerido_para("Edición") == ""


def test_cargo_satisface_sin_requisito_siempre():
    assert colaboracion.cargo_satisface("", "redactor") is True


def test_cargo_satisface_coincidencia_y_especializacion():
    assert colaboracion.cargo_satisface("coordinador", "coordinador") is True
    # Una especializacion del cargo generico tambien satisface.
    assert colaboracion.cargo_satisface("coordinador", "coordinador_redes") is True
    # Un cargo distinto no satisface.
    assert colaboracion.cargo_satisface("director", "coordinador") is False
    # Sin cargo no satisface un requisito.
    assert colaboracion.cargo_satisface("director", "") is False


def test_decidir_bloquea_si_el_cargo_no_satisface():
    cadena = [{"id": "a", "nivel": 1, "decision": "pendiente", "cargo_requerido": "director"}]
    _, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u2", "usuario": "beto"}, rol="editor",
        autor_pieza_id="u1", cargo_decisor="redactor",
    )
    assert error is not None and "cargo" in error.lower()


def test_decidir_permite_si_el_cargo_satisface():
    cadena = [{"id": "a", "nivel": 1, "decision": "pendiente", "cargo_requerido": "coordinador"}]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u2", "usuario": "beto"}, rol="editor",
        autor_pieza_id="u1", cargo_decisor="coordinador_redes",
    )
    assert error is None and campos is not None


def test_decidir_admin_ignora_el_cargo_requerido():
    cadena = [{"id": "a", "nivel": 1, "decision": "pendiente", "cargo_requerido": "director"}]
    campos, error = colaboracion.decidir(
        cadena[0], cadena, "aprobado", {"id": "u2", "usuario": "jefa"}, rol="admin",
        autor_pieza_id="u1", cargo_decisor="redactor",
    )
    assert error is None and campos is not None


# --------------------------------------------------------------------------- #
# Nivel "Crítica IA" (post-aprobacion): marcador, deteccion y disparo          #
# --------------------------------------------------------------------------- #


def _nivel_ia(decision: str = "pendiente") -> dict[str, object]:
    return {
        "id": "ia",
        "nivel": 3,
        "decision": decision,
        "etiqueta": colaboracion.ETIQUETA_CRITICA_IA,
        "decisor_id": "",
        "cargo_requerido": colaboracion.CARGO_IA_CRITICO,
    }


def test_es_nivel_critica_ia_por_su_cargo_reservado():
    assert colaboracion.es_nivel_critica_ia(_nivel_ia()) is True
    assert colaboracion.es_nivel_critica_ia(_nivel("a", 1)) is False


def test_es_etiqueta_critica_ia_laxa():
    assert colaboracion.es_etiqueta_critica_ia("crítica ia") is True
    assert colaboracion.es_etiqueta_critica_ia(colaboracion.ETIQUETA_CRITICA_IA) is True
    assert colaboracion.es_etiqueta_critica_ia("Coordinación") is False


def test_nivel_critica_ia_lo_encuentra_o_none():
    cadena = [_nivel("a", 1, "aprobado"), _nivel_ia()]
    assert colaboracion.nivel_critica_ia(cadena)["id"] == "ia"
    assert colaboracion.nivel_critica_ia([_nivel("a", 1)]) is None


def test_cargo_de_nivel_ia_siempre_lleva_cargo_reservado():
    # El nivel IA lleva su cargo reservado AUNQUE la cadena no exija cargos humanos.
    assert (
        colaboracion.cargo_de_nivel(colaboracion.ETIQUETA_CRITICA_IA, con_cargos=False)
        == colaboracion.CARGO_IA_CRITICO
    )
    # Un nivel humano sin cargos -> "" ; con cargos -> el del organigrama.
    assert colaboracion.cargo_de_nivel("Coordinación", con_cargos=False) == ""
    assert colaboracion.cargo_de_nivel("Coordinación", con_cargos=True) == "coordinador"


def test_cargo_reservado_ia_no_lo_satisface_ningun_humano():
    # La regla de cargos existente impide que una persona decida el nivel IA por el feed.
    assert colaboracion.cargo_satisface(colaboracion.CARGO_IA_CRITICO, "coordinador") is False
    assert colaboracion.cargo_satisface(colaboracion.CARGO_IA_CRITICO, "director") is False


def test_humanos_aprobados_ia_pendiente_dispara_solo_cuando_toca():
    # Los dos humanos OK y la IA pendiente -> dispara.
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado"), _nivel_ia("pendiente")]
    assert colaboracion.humanos_aprobados_ia_pendiente(cadena) is True
    # Falta un humano -> no dispara.
    cadena2 = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "pendiente"), _nivel_ia("pendiente")]
    assert colaboracion.humanos_aprobados_ia_pendiente(cadena2) is False
    # La IA ya votó -> no dispara (no re-encola).
    cadena3 = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado"), _nivel_ia("rechazado")]
    assert colaboracion.humanos_aprobados_ia_pendiente(cadena3) is False
    # Sin nivel IA (flag OFF) -> no aplica.
    cadena4 = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado")]
    assert colaboracion.humanos_aprobados_ia_pendiente(cadena4) is False


def test_dislike_de_ia_no_rechaza_la_cadena_de_tres_por_si_solo():
    # [humano OK, humano OK, IA dislike] -> 1 rechazo < umbral 2 -> sigue "pendiente"
    # (la pieza queda en revisión con el dislike + comentario; no se marca rechazada de golpe).
    cadena = [_nivel("a", 1, "aprobado"), _nivel("b", 2, "aprobado"), _nivel_ia("rechazado")]
    assert colaboracion.estado_cadena(cadena) == "pendiente"


def test_aprobaciones_humanas_excluye_al_critico_ia():
    cadena = [
        _nivel("a", 1, "aprobado", decisor_id="u1"),
        _nivel("b", 2, "aprobado", decisor_id="u2"),
        {"id": "ia", "nivel": 3, "decision": "aprobado",
         "decisor_id": colaboracion.DECISOR_CRITICA_ID},
    ]
    assert colaboracion.contar_aprobaciones_humanas(cadena) == 2
    # pero cuenta los 3 como aprobaciones totales (gate de minimo).
    assert colaboracion.contar_aprobados(cadena) == 3
