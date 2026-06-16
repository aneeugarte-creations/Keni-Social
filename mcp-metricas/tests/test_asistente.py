"""Tests OFFLINE del asistente de onboarding.

Cubren la logica pura: construccion del dict, serializacion TOML (round-trip via
tomllib), merge no destructivo con config existente, enmascarado de tokens y
escritura atomica. NO hay red ni input() interactivo: se llaman las funciones
puras directamente. Los tokens son obviamente falsos (TOKEN_DE_EJEMPLO).
"""

from __future__ import annotations

import tomllib

import pytest

from keni_metricas import asistente as a

TOKEN_FALSO = "TOKEN_DE_EJEMPLO_meta_1234567890"
BEARER_FALSO = "BEARER_DE_EJEMPLO_x_abcdef9999"


# --- enmascarado -----------------------------------------------------------
def test_enmascarar_oculta_casi_todo():
    masc = a.enmascarar_token(TOKEN_FALSO)
    assert masc.endswith("7890")
    assert TOKEN_FALSO not in masc  # nunca el token completo
    assert set(masc[:-4]) == {"*"}


def test_enmascarar_vacio_y_placeholder():
    assert a.enmascarar_token("") == "(vacio)"
    assert a.enmascarar_token(None) == "(vacio)"
    assert a.enmascarar_token(a.PLACEHOLDER_TOKEN) == a.PLACEHOLDER_TOKEN


def test_enmascarar_token_corto_todo_oculto():
    assert a.enmascarar_token("abc") == "***"


# --- normalizacion ---------------------------------------------------------
def test_normalizar_id_marca():
    assert a.normalizar_id_marca("Claro Sports") == "claro_sports"
    assert a.normalizar_id_marca("  UnoTV!! ") == "unotv"
    assert a.normalizar_id_marca("a--b__c") == "a_b_c"


def test_normalizar_alcance_dedup_y_orden():
    assert a.normalizar_alcance("unotv, claro_sports, unotv") == ["unotv", "claro_sports"]
    assert a.normalizar_alcance(["x", "", "y", "x"]) == ["x", "y"]
    assert a.normalizar_alcance("") == []


def test_normalizar_alcance_filtra_a_ids_validos():
    out = a.normalizar_alcance("unotv, fantasma", ids_validos=["unotv", "claro_sports"])
    assert out == ["unotv"]


# --- construccion del dict -------------------------------------------------
def _plan_ejemplo() -> a.PlanConfig:
    return a.PlanConfig(
        fuente="real",
        marcas_cuenta=[
            a.MarcaEntrada(
                id="claro_sports",
                nombre="Claro Sports",
                plataformas={"facebook": "PAGE_ID", "instagram": "IG_ID", "tiktok": "IGNORADO"},
            ),
            a.MarcaEntrada(id="unotv", nombre="UnoTV", plataformas={"facebook": "PAGE2"}),
        ],
        alcance=["claro_sports"],
        credenciales={
            "meta": {"access_token": TOKEN_FALSO, "tipo_token": "system_user"},
            "x": {"bearer_token": BEARER_FALSO},
            "youtube": {},  # vacio: debe descartarse
        },
    )


def test_plan_a_dict_estructura():
    datos = a.plan_a_dict(_plan_ejemplo())
    assert datos["fuente"] == "real"
    assert datos["marcas"] == ["claro_sports"]
    # tiktok no lleva handle aunque se haya declarado uno
    cs = next(c for c in datos["cuenta"] if c["id"] == "claro_sports")
    assert "tiktok" not in cs["plataformas"]
    assert cs["plataformas"]["facebook"] == "PAGE_ID"
    # bloque vacio de youtube descartado; meta y x presentes
    assert set(datos["credenciales"]) == {"meta", "x"}
    assert datos["credenciales"]["meta"]["tipo_token"] == "system_user"


def test_plan_muestra_sin_marcas_ni_creds():
    datos = a.plan_a_dict(a.PlanConfig(fuente="muestra"))
    assert datos == {"fuente": "muestra"}
    assert "marcas" not in datos
    assert "credenciales" not in datos


# --- serializacion TOML (round-trip) ---------------------------------------
def test_serializar_round_trip():
    datos = a.plan_a_dict(_plan_ejemplo())
    texto = a.serializar_toml(datos)
    releido = tomllib.loads(texto)
    assert releido["fuente"] == "real"
    assert releido["marcas"] == ["claro_sports"]
    assert releido["credenciales"]["meta"]["access_token"] == TOKEN_FALSO
    assert releido["credenciales"]["meta"]["tipo_token"] == "system_user"
    assert releido["credenciales"]["x"]["bearer_token"] == BEARER_FALSO
    cuentas = {c["id"]: c for c in releido["cuenta"]}
    assert cuentas["claro_sports"]["plataformas"]["instagram"] == "IG_ID"
    assert cuentas["unotv"]["nombre"] == "UnoTV"


def test_serializar_escapa_comillas():
    datos = {"fuente": "real", "cuenta": [{"id": "x", "nombre": 'A "B" C'}]}
    releido = tomllib.loads(a.serializar_toml(datos))
    assert releido["cuenta"][0]["nombre"] == 'A "B" C'


def test_compatible_con_cargar_config(monkeypatch, tmp_path):
    """El TOML generado lo entiende config.cargar_config sin cambios."""
    from keni_metricas.config import cargar_config

    ruta = tmp_path / "config.toml"
    datos = a.plan_a_dict(_plan_ejemplo())
    a.escribir_config_atomico(ruta, datos)

    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(ruta))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    # El plan de ejemplo elige `real` (adaptadores), un fallback opt-in: habilitamos el
    # flag para que `cargar_config` acepte ese TOML generado (la fuente única es metricool).
    monkeypatch.setenv("KENI_METRICAS_PERMITIR_REAL", "1")
    cfg = cargar_config()
    assert cfg.fuente == "real"
    assert cfg.marcas == ["claro_sports"]
    ids = {c.id for c in cfg.cuentas}
    assert ids == {"claro_sports", "unotv"}
    assert cfg.credenciales["meta"]["access_token"] == TOKEN_FALSO


# --- merge no destructivo --------------------------------------------------
def test_fusionar_preserva_seccion_ajena():
    existente = {
        "fuente": "muestra",
        "seccion_ajena": {"clave": "valor"},  # algo que el asistente no genera
        "credenciales": {"tiktok": {"access_token": "VIEJO_TIKTOK"}},
    }
    nuevo = {
        "fuente": "real",
        "credenciales": {"meta": {"access_token": TOKEN_FALSO}},
    }
    out = a.fusionar_config(existente, nuevo)
    assert out["fuente"] == "real"  # el nuevo gana
    assert out["seccion_ajena"] == {"clave": "valor"}  # preservada
    # bloque tiktok no tocado se mantiene; meta nuevo se anade
    assert out["credenciales"]["tiktok"]["access_token"] == "VIEJO_TIKTOK"
    assert out["credenciales"]["meta"]["access_token"] == TOKEN_FALSO


def test_fusionar_credenciales_por_clave_no_pierde_app_secret():
    existente = {"credenciales": {"meta": {"access_token": "VIEJO", "app_id": "APPID", "app_secret": "S"}}}
    nuevo = {"credenciales": {"meta": {"access_token": TOKEN_FALSO}}}
    out = a.fusionar_config(existente, nuevo)
    meta = out["credenciales"]["meta"]
    assert meta["access_token"] == TOKEN_FALSO  # actualizado
    assert meta["app_id"] == "APPID"  # conservado
    assert meta["app_secret"] == "S"


def test_construir_y_fusionar_lee_existente(tmp_path):
    ruta = tmp_path / "config.toml"
    a.escribir_config_atomico(
        ruta,
        {"fuente": "muestra", "seccion_ajena": {"k": "v"}},
    )
    plan = a.PlanConfig(fuente="real", credenciales={"x": {"bearer_token": BEARER_FALSO}})
    out = a.construir_y_fusionar(plan, ruta)
    assert out["fuente"] == "real"
    assert out["seccion_ajena"] == {"k": "v"}
    assert out["credenciales"]["x"]["bearer_token"] == BEARER_FALSO


# --- escritura atomica -----------------------------------------------------
def test_escribir_atomico_crea_dir_y_permisos(tmp_path):
    import os
    import stat

    ruta = tmp_path / "sub" / "dir" / "config.toml"
    a.escribir_config_atomico(ruta, {"fuente": "muestra"})
    assert ruta.exists()
    # solo el dueno puede leer/escribir (0600)
    modo = stat.S_IMODE(os.stat(ruta).st_mode)
    assert modo == 0o600
    # no quedan temporales
    assert list(ruta.parent.glob(".config-*.tmp")) == []


def test_escribir_incluye_cabecera_y_no_filtra_token_en_log(tmp_path):
    ruta = tmp_path / "config.toml"
    datos = a.plan_a_dict(_plan_ejemplo())
    a.escribir_config_atomico(ruta, datos)
    texto = ruta.read_text(encoding="utf-8")
    assert texto.startswith("#")  # cabecera de comentario
    # el token SI esta en el archivo (es su sitio), pero el resumen lo enmascara:
    resumen = a.resumen_plan(_plan_ejemplo())
    assert TOKEN_FALSO not in resumen
    assert BEARER_FALSO not in resumen
    assert "system_user" in resumen  # metadatos no secretos si se muestran


# --- enmascarado del TOML mostrado (B3: --solo-mostrar no filtra tokens) ----
def test_enmascarar_credenciales_no_filtra_tokens():
    datos = a.plan_a_dict(_plan_ejemplo())
    masc = a.enmascarar_credenciales(datos)
    # no muta el original
    assert datos["credenciales"]["meta"]["access_token"] == TOKEN_FALSO
    # los secretos quedan enmascarados (no aparece el token completo)
    assert masc["credenciales"]["meta"]["access_token"] != TOKEN_FALSO
    assert masc["credenciales"]["meta"]["access_token"].endswith(TOKEN_FALSO[-4:])
    assert masc["credenciales"]["x"]["bearer_token"] != BEARER_FALSO
    # metadatos no secretos se conservan
    assert masc["credenciales"]["meta"]["tipo_token"] == "system_user"


def test_enmascarar_credenciales_sin_bloque_credenciales():
    datos = {"fuente": "muestra"}
    assert a.enmascarar_credenciales(datos) == {"fuente": "muestra"}


def test_solo_mostrar_no_filtra_token_completo(monkeypatch, capsys, tmp_path):
    """`--solo-mostrar` no debe imprimir NINGUN token en claro (ni resumen ni TOML)."""
    # el flujo interactivo se sustituye por un plan con tokens reales (falsos)
    monkeypatch.setattr(a, "flujo_interactivo", lambda: _plan_ejemplo())
    ruta = tmp_path / "config.toml"  # no debe escribirse

    rc = a.main(["--solo-mostrar", "--ruta", str(ruta)])
    assert rc == 0

    salida = capsys.readouterr().out
    # ni el token ni el bearer aparecen completos en NINGUNA parte de la salida
    assert TOKEN_FALSO not in salida
    assert BEARER_FALSO not in salida
    # pero el TOML si se muestra (con el bloque de credenciales enmascarado)
    assert "== TOML" in salida
    assert "access_token" in salida
    # y --solo-mostrar nunca escribe el archivo
    assert not ruta.exists()


# --- guia por plataforma ---------------------------------------------------
def test_guia_plataforma_menciona_docs_y_system_user():
    g_meta = a.texto_guia_plataforma("facebook")
    assert "System User" in g_meta
    assert "docs/credenciales.md" in g_meta
    assert "docs/plataformas/pieza-metricool.md" in g_meta
    # facebook e instagram comparten el bloque meta
    assert a.guia_plataforma("instagram") is a.guia_plataforma("facebook")
    assert "docs/" in a.texto_guia_plataforma("youtube")
    assert "bearer" in a.texto_guia_plataforma("x").lower()


@pytest.mark.parametrize("plat", a.PLATAFORMAS)
def test_toda_plataforma_tiene_guia(plat):
    g = a.guia_plataforma(plat)
    assert g["titulo"] and g["que"] and g["docs"]


# --- flujo interactivo: entrada/salida inyectables -------------------------
def _entrada_simulada(respuestas):
    """Devuelve un callable tipo input() que va entregando `respuestas` en orden.

    Lanza EOFError al agotarse (como un input() sin stdin), que el flujo trata
    como "valor por defecto"; util para no tener que enumerar cada prompt.
    """
    it = iter(respuestas)

    def _entrada(_prompt=""):
        try:
            return next(it)
        except StopIteration as exc:
            raise EOFError from exc

    return _entrada


def _capturar_salida():
    """Devuelve (lista_lineas, fn_salida) para inyectar como `salida=`."""
    lineas: list[str] = []

    def _salida(*args):
        lineas.append(" ".join(str(x) for x in args))

    return lineas, _salida


# --- indicador de progreso paso X/N ----------------------------------------
def test_flujo_muestra_marca_progreso_3_pasos():
    """En modo muestra el flujo tiene 3 etapas reales: paso X/3 (sin credenciales)."""
    # respuestas: fuente? (n=muestra), nombre marca (vacio -> termina), no hay
    # marcas asi que no se pregunta alcance.
    entrada = _entrada_simulada(["n", ""])
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)

    texto = "\n".join(lineas)
    assert "paso 1/3: Fuente de datos" in texto
    assert "paso 2/3: Marcas / cuentas" in texto
    assert "paso 3/3: Alcance" in texto
    # nunca aparece la etapa de credenciales en modo muestra
    assert "/3: Credenciales" not in texto
    assert "paso 4/" not in texto
    assert plan.fuente == "muestra"


def test_flujo_real_marca_progreso_4_pasos():
    """En modo real hay 4 etapas reales: incluye credenciales -> paso X/4."""
    # fuente? (s=real); marca: nombre, id, fb handle, ig vacio, yt vacio, x vacio;
    # fin de marcas (vacio); alcance (vacio=todas); credencial meta token; system user? (n)
    entrada = _entrada_simulada(
        [
            "s",            # fuente real
            "UnoTV",        # nombre marca
            "unotv",        # id
            "PAGE_ID",      # facebook handle
            "",             # instagram vacio
            "",             # youtube vacio
            "",             # x vacio
            "",             # fin de marcas
            "",             # alcance: todas
            TOKEN_FALSO,    # meta access_token
            "n",            # no es system user
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)

    texto = "\n".join(lineas)
    assert "paso 1/4: Fuente de datos" in texto
    assert "paso 2/4: Marcas / cuentas" in texto
    assert "paso 3/4: Alcance" in texto
    assert "paso 4/4: Credenciales" in texto
    assert plan.fuente == "real"
    assert plan.credenciales["meta"]["access_token"] == TOKEN_FALSO
    # el progreso (ni nada del flujo) imprime el token en claro
    assert TOKEN_FALSO not in texto


def test_etapas_segun_fuente():
    assert len(a._etapas("muestra")) == 3
    assert len(a._etapas("real")) == 4
    assert a.ETAPA_CREDENCIALES not in a._etapas("muestra")
    assert a.ETAPA_CREDENCIALES in a._etapas("real")


# --- recap final (sin tokens) + proximo paso -------------------------------
def test_recap_final_incluye_lo_configurado_y_proximo_paso():
    recap = a.recap_final(_plan_ejemplo())
    assert "Fuente de datos: real" in recap
    # marcas por nombre/id
    assert "Claro Sports (claro_sports)" in recap
    assert "UnoTV (unotv)" in recap
    # alcance declarado
    assert "claro_sports" in recap
    # credenciales: solo el bloque y su estado, jamas el valor
    assert "meta" in recap
    assert "token presente" in recap
    # proximo paso explicito
    assert "python -m keni_metricas.doctor" in recap


def test_recap_final_no_filtra_tokens():
    recap = a.recap_final(_plan_ejemplo())
    assert TOKEN_FALSO not in recap
    assert BEARER_FALSO not in recap
    # tampoco fragmentos largos del token
    assert TOKEN_FALSO[:-4] not in recap


def test_recap_final_muestra_pendiente_si_placeholder():
    plan = a.PlanConfig(
        fuente="real",
        credenciales={"meta": {"access_token": a.PLACEHOLDER_TOKEN}},
    )
    recap = a.recap_final(plan)
    assert "PENDIENTE" in recap
    # el placeholder es el valor literal, no un secreto, pero igual marcamos estado
    assert "meta" in recap


def test_recap_final_modo_muestra_sin_credenciales():
    plan = a.PlanConfig(fuente="muestra")
    recap = a.recap_final(plan)
    assert "Fuente de datos: muestra" in recap
    assert "ninguna" in recap.lower()
    assert "python -m keni_metricas.doctor" in recap


# --- aviso de incoherencia (handles/tokens reales pero fuente=muestra) ------
def test_incoherencia_handles_en_muestra_avisa():
    plan = a.PlanConfig(
        fuente="muestra",
        marcas_cuenta=[a.MarcaEntrada(id="unotv", nombre="UnoTV", plataformas={"facebook": "PAGE"})],
    )
    aviso = a.detectar_incoherencia(plan)
    assert aviso is not None
    assert "muestra" in aviso
    assert "real" in aviso  # sugiere cambiar a real


def test_incoherencia_tokens_reales_en_muestra_avisa():
    plan = a.PlanConfig(
        fuente="muestra",
        credenciales={"meta": {"access_token": TOKEN_FALSO}},
    )
    aviso = a.detectar_incoherencia(plan)
    assert aviso is not None
    # el aviso NO filtra el token
    assert TOKEN_FALSO not in aviso


def test_incoherencia_no_avisa_si_coherente():
    # muestra sin handles ni tokens: coherente -> None
    assert a.detectar_incoherencia(a.PlanConfig(fuente="muestra")) is None
    # fuente real: nunca es incoherente por esto
    assert a.detectar_incoherencia(_plan_ejemplo()) is None


def test_incoherencia_placeholder_no_cuenta_como_token_real():
    # un placeholder no es un token real -> sin handles, no hay incoherencia
    plan = a.PlanConfig(
        fuente="muestra",
        credenciales={"meta": {"access_token": a.PLACEHOLDER_TOKEN}},
    )
    assert a.detectar_incoherencia(plan) is None


def test_recap_incluye_aviso_de_incoherencia():
    plan = a.PlanConfig(
        fuente="muestra",
        marcas_cuenta=[a.MarcaEntrada(id="unotv", nombre="UnoTV", plataformas={"facebook": "PAGE"})],
    )
    recap = a.recap_final(plan)
    assert "AVISO" in recap


# --- main(): recap impreso sin tokens, tambien en --solo-mostrar -----------
def test_main_solo_mostrar_imprime_recap_sin_tokens(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(a, "flujo_interactivo", lambda: _plan_ejemplo())
    ruta = tmp_path / "config.toml"
    rc = a.main(["--solo-mostrar", "--ruta", str(ruta)])
    assert rc == 0
    salida = capsys.readouterr().out
    # el recap aparece y apunta a doctor
    assert "Recap de tu configuracion" in salida
    assert "python -m keni_metricas.doctor" in salida
    # y NO filtra tokens (ni resumen, ni TOML, ni recap)
    assert TOKEN_FALSO not in salida
    assert BEARER_FALSO not in salida
    assert not ruta.exists()


# ===========================================================================
# Ampliacion de cobertura: mas ramas del flujo interactivo (issue #52).
# Sin red ni input() real: se inyectan `entrada=`/`salida=` o se sustituye
# `flujo_interactivo` en main(). Verificamos COMPORTAMIENTO, no textos fragiles.
# ===========================================================================


# --- fuente: muestra vs real (rama de _preguntar_si_no por defecto) --------
def test_flujo_fuente_muestra_por_eof_defecto():
    """Sin responder a la fuente (EOF) cae al por_defecto = muestra (3 pasos)."""
    # entrada vacia: el primer prompt (fuente) ya lanza EOFError -> por_defecto (no).
    entrada = _entrada_simulada([])
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    assert plan.fuente == "muestra"
    assert plan.marcas_cuenta == []
    assert plan.alcance == []
    # con 0 marcas se entra en la rama "sin marcas declaradas"
    assert any("sin marcas" in ln.lower() for ln in lineas)


def test_flujo_fuente_real_con_respuesta_si():
    """Responder 's' a la fuente activa modo real (4 pasos)."""
    # fuente=s; sin marcas (vacio); no se llega a credenciales porque no hay bloques.
    entrada = _entrada_simulada(["s", ""])
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    assert plan.fuente == "real"
    texto = "\n".join(lineas)
    assert "paso 1/4" in texto


# --- varias marcas/cuentas declaradas en una pasada ------------------------
def test_flujo_declara_varias_marcas():
    """Se pueden declarar multiples marcas seguidas; cada una pide handles."""
    entrada = _entrada_simulada(
        [
            "n",            # fuente muestra
            "Claro Sports",  # marca 1 nombre
            "",             # id 1 -> usa sugerido (claro_sports)
            "FB1",          # facebook
            "IG1",          # instagram
            "",             # youtube vacio
            "",             # x vacio
            "UnoTV",        # marca 2 nombre
            "unotv",        # id 2 explicito
            "FB2",          # facebook
            "",             # instagram vacio
            "",             # youtube vacio
            "",             # x vacio
            "",             # fin de marcas
            "",             # alcance vacio (todas)
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)

    ids = [m.id for m in plan.marcas_cuenta]
    assert ids == ["claro_sports", "unotv"]
    # tiktok jamas se pregunta (sin handle); ningun handle de tiktok aparece
    primera = plan.marcas_cuenta[0]
    assert "tiktok" not in primera.plataformas
    assert primera.plataformas == {"facebook": "FB1", "instagram": "IG1"}
    assert plan.marcas_cuenta[1].plataformas == {"facebook": "FB2"}
    # cada marca anadida se confirma en la salida
    texto = "\n".join(lineas)
    assert "claro_sports" in texto
    assert "unotv" in texto


# --- alcance: limitado vs todas -------------------------------------------
def test_flujo_alcance_limitado_filtra_a_ids_validos():
    """Declarar alcance acotado guarda solo ids validos (descarta fantasmas)."""
    entrada = _entrada_simulada(
        [
            "n",            # muestra
            "UnoTV", "unotv", "", "", "", "",   # marca 1 (sin handles)
            "Claro", "claro", "", "", "", "",   # marca 2
            "",             # fin marcas
            "unotv, fantasma",  # alcance: uno valido + uno inexistente
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    # solo el id valido sobrevive; el fantasma se descarta
    assert plan.alcance == ["unotv"]


def test_flujo_alcance_todas_si_vacio():
    """Dejar el alcance vacio significa 'todas' (alcance == [])."""
    entrada = _entrada_simulada(
        [
            "n",
            "UnoTV", "unotv", "", "", "", "",
            "",     # fin marcas
            "",     # alcance vacio -> todas
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    assert plan.alcance == []
    # con marcas si se muestra la lista de marcas declaradas
    assert any("Marcas declaradas" in ln for ln in lineas)


# --- credenciales: declaradas, placeholder y system_user ------------------
def test_flujo_real_credenciales_placeholder_si_vacio():
    """En real, dejar el token vacio guarda el placeholder (no falla)."""
    entrada = _entrada_simulada(
        [
            "s",            # real
            "UnoTV", "unotv", "PAGE", "", "", "",  # marca con facebook -> bloque meta
            "",             # fin marcas
            "",             # alcance todas
            "",             # meta access_token vacio -> placeholder
            "n",            # no system user
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    assert plan.credenciales["meta"]["access_token"] == a.PLACEHOLDER_TOKEN
    # el placeholder no es un secreto: tipo_token no se anadio (respondio n)
    assert "tipo_token" not in plan.credenciales["meta"]
    # se ofrece tambien tiktok (bloque sin handle) con placeholder
    assert "tiktok" in plan.credenciales


def test_flujo_real_meta_system_user_anade_tipo_token():
    """Responder 's' a 'es System User?' anade tipo_token = system_user."""
    entrada = _entrada_simulada(
        [
            "s",            # real
            "UnoTV", "unotv", "PAGE", "", "", "",  # marca con facebook
            "",             # fin marcas
            "",             # alcance
            TOKEN_FALSO,    # meta access_token real
            "s",            # SI es system user -> rama de linea 645
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    assert plan.credenciales["meta"]["access_token"] == TOKEN_FALSO
    assert plan.credenciales["meta"]["tipo_token"] == "system_user"
    # ni el progreso ni el eco del token lo imprimen en claro
    texto = "\n".join(lineas)
    assert TOKEN_FALSO not in texto


def test_flujo_real_solo_tiktok_sin_handles():
    """Sin plataformas con handle, en real solo se ofrece el bloque tiktok."""
    entrada = _entrada_simulada(
        [
            "s",            # real
            "Marca", "marca", "", "", "", "",  # marca sin ningun handle
            "",             # fin marcas
            "",             # alcance
            TOKEN_FALSO,    # tiktok access_token
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    # solo tiktok (siempre ofrecido); ningun otro bloque
    assert set(plan.credenciales) == {"tiktok"}
    assert plan.credenciales["tiktok"]["access_token"] == TOKEN_FALSO


# --- incoherencia: handles reales + fuente muestra (via flujo completo) ----
def test_flujo_handles_en_muestra_genera_incoherencia():
    """Declarar handles pero quedarse en muestra -> detectar_incoherencia avisa."""
    entrada = _entrada_simulada(
        [
            "n",            # muestra
            "UnoTV", "unotv", "PAGE", "", "", "",  # handle real de facebook
            "",             # fin marcas
            "",             # alcance
        ]
    )
    lineas, salida = _capturar_salida()
    plan = a.flujo_interactivo(entrada=entrada, salida=salida)
    aviso = a.detectar_incoherencia(plan)
    assert aviso is not None
    assert "muestra" in aviso
    # el recap del plan tambien arrastra el aviso
    assert "AVISO" in a.recap_final(plan)


# --- resumen_plan con alcance (linea 676) ----------------------------------
def test_resumen_plan_con_alcance_lista_marcas():
    """resumen_plan lista el alcance cuando esta acotado, sin filtrar tokens."""
    resumen = a.resumen_plan(_plan_ejemplo())
    assert "gestionas (alcance) = claro_sports" in resumen
    # marca sin handles se reporta como tal
    plan_sin = a.PlanConfig(
        fuente="muestra",
        marcas_cuenta=[a.MarcaEntrada(id="x", nombre="X")],
    )
    assert "(sin handles)" in a.resumen_plan(plan_sin)


# --- main(): camino de escritura (confirma) y cancelacion ------------------
def test_main_escribe_cuando_se_confirma(monkeypatch, capsys, tmp_path):
    """main sin --solo-mostrar: si se confirma, escribe el archivo y recapea."""
    monkeypatch.setattr(a, "flujo_interactivo", lambda: _plan_ejemplo())
    # _preguntar_si_no de confirmacion -> 's' (escribir)
    monkeypatch.setattr(a, "_preguntar_si_no", lambda *args, **kwargs: True)
    ruta = tmp_path / "config.toml"
    rc = a.main(["--ruta", str(ruta)])
    assert rc == 0
    assert ruta.exists()
    salida = capsys.readouterr().out
    assert "Recap de tu configuracion" in salida
    # el config en disco SI contiene el token (es su sitio); pero el log no lo filtra
    assert TOKEN_FALSO not in salida
    assert TOKEN_FALSO in ruta.read_text(encoding="utf-8")


def test_main_cancela_no_escribe(monkeypatch, capsys, tmp_path):
    """Si la persona no confirma, main devuelve 1 y no escribe nada."""
    monkeypatch.setattr(a, "flujo_interactivo", lambda: _plan_ejemplo())
    monkeypatch.setattr(a, "_preguntar_si_no", lambda *args, **kwargs: False)
    ruta = tmp_path / "config.toml"
    rc = a.main(["--ruta", str(ruta)])
    assert rc == 1
    assert not ruta.exists()
    assert "Cancelado" in capsys.readouterr().out


# --- ruta_config(): ramas de entorno --------------------------------------
def test_ruta_config_respeta_env_explicito(monkeypatch, tmp_path):
    destino = tmp_path / "mi-config.toml"
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(destino))
    assert a.ruta_config() == destino


def test_ruta_config_usa_xdg_si_sin_env_explicito(monkeypatch, tmp_path):
    monkeypatch.delenv("KENI_METRICAS_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    ruta = a.ruta_config()
    assert ruta == tmp_path / "keni-metricas" / "config.toml"


# --- enmascarado: bloque de credenciales con valor no-dict (lineas 210-211) -
def test_enmascarar_credenciales_bloque_no_dict_se_conserva():
    """Un bloque cuyo valor no es dict se deja tal cual (no revienta)."""
    datos = {"credenciales": {"raro": "no-soy-un-dict", "meta": {"access_token": TOKEN_FALSO}}}
    masc = a.enmascarar_credenciales(datos)
    assert masc["credenciales"]["raro"] == "no-soy-un-dict"
    # el bloque normal si se enmascara
    assert masc["credenciales"]["meta"]["access_token"] != TOKEN_FALSO


# --- serializacion: escalares bool/int y tablas (lineas 336/338/347/352) ---
def test_serializar_bool_e_int_round_trip():
    datos = {"fuente": "real", "activo": True, "inactivo": False, "limite": 7}
    releido = tomllib.loads(a.serializar_toml(datos))
    assert releido["activo"] is True
    assert releido["inactivo"] is False
    assert releido["limite"] == 7


def test_es_tabla_simple_distingue_tablas():
    # no-dict -> False (linea 347 indirecta)
    assert a._es_tabla_simple("texto") is False
    # dict con sub-dict -> False
    assert a._es_tabla_simple({"a": {"b": 1}}) is False
    # dict con lista de dicts -> False (linea 352)
    assert a._es_tabla_simple({"a": [{"b": 1}]}) is False
    # dict de hojas -> True
    assert a._es_tabla_simple({"a": 1, "b": "x"}) is True


def test_serializar_seccion_con_hojas_y_subtabla(tmp_path):
    """Una seccion con hojas propias + sub-tabla emite [clave] y [clave.sub] (418-421)."""
    datos = {
        "credenciales": {
            "meta": {"access_token": TOKEN_FALSO, "extra": {"anidado": "v"}},
        }
    }
    texto = a.serializar_toml(datos)
    releido = tomllib.loads(texto)
    assert releido["credenciales"]["meta"]["access_token"] == TOKEN_FALSO
    assert releido["credenciales"]["meta"]["extra"]["anidado"] == "v"


# --- escritura atomica: limpieza del temporal ante fallo (lineas 454-457) ---
def test_escribir_atomico_limpia_temporal_si_falla(monkeypatch, tmp_path):
    """Si el replace final falla (tras crear el temporal), se limpia el .tmp."""
    import os as _os

    ruta = tmp_path / "config.toml"

    def _replace_boom(_src, _dst):
        raise RuntimeError("fallo simulado en os.replace")

    # os.replace ocurre DESPUES de mkstemp, asi que se ejercita el except/cleanup.
    monkeypatch.setattr(_os, "replace", _replace_boom)
    with pytest.raises(RuntimeError):
        a.escribir_config_atomico(ruta, {"fuente": "muestra"})
    # ni el archivo final ni temporales quedan tras el fallo (temporal eliminado)
    assert not ruta.exists()
    assert list(tmp_path.glob(".config-*.tmp")) == []
