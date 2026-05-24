"""Tests del autodiagnostico (`keni_metricas.doctor`).

Todo OFFLINE: config en tmp_path, `shutil.which` y las rutas del modelo de whisper
se inyectan/monkeypatchean. No se toca el PATH real ni la red. La comprobacion de
conectividad (`--validar`) NO es requerida por estos tests.
"""

from __future__ import annotations

import sys

import pytest

from keni_metricas.config import Config, ConfigInvalida, CuentaConfig, cargar_config
from keni_metricas.doctor import (
    Estado,
    Resultado,
    cierre_accionable,
    codigo_salida,
    comprobar_binario,
    comprobar_config,
    comprobar_credenciales,
    comprobar_fuente,
    comprobar_marcas,
    comprobar_modelo_whisper,
    comprobar_python,
    ejecutar_chequeos,
    main,
    renderizar,
    resumir_credenciales,
    validar_conectividad,
)
from keni_metricas.schema import Plataforma

# --- helpers ----------------------------------------------------------------


def _which_falso(presentes: set[str]):
    """Fabrica un sustituto de shutil.which que solo 'encuentra' lo indicado."""

    def _which(nombre: str):
        return f"/usr/local/bin/{nombre}" if nombre in presentes else None

    return _which


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch, tmp_path):
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_WHISPER_MODEL", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))


# --- Python -----------------------------------------------------------------


def test_python_actual_ok():
    r = comprobar_python()
    assert r.estado is Estado.OK
    assert r.extra["version"] == tuple(sys.version_info[:3])


def test_python_viejo_es_error():
    r = comprobar_python(version=(3, 9, 0))
    assert r.estado is Estado.ERROR
    assert not r.ok


def test_python_310_es_error():
    assert comprobar_python(version=(3, 10, 12)).estado is Estado.ERROR


# --- Config -----------------------------------------------------------------


def test_config_ausente_es_aviso(tmp_path):
    r = comprobar_config(ruta=tmp_path / "nope.toml")
    assert r.estado is Estado.AVISO
    assert r.extra["existe"] is False


def test_config_valido_ok(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('fuente = "muestra"\n', encoding="utf-8")
    r = comprobar_config(ruta=p)
    assert r.estado is Estado.OK
    assert r.extra["existe"] is True


def test_config_roto_es_error(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("esto no es = = toml valido [[[", encoding="utf-8")
    r = comprobar_config(ruta=p)
    assert r.estado is Estado.ERROR
    assert "parsear" in r.detalle or "leer" in r.detalle


# --- Fuente -----------------------------------------------------------------


def test_fuente_muestra_se_construye():
    r = comprobar_fuente(Config(fuente="muestra"))
    assert r.estado is Estado.OK
    assert r.extra["fuente"] == "muestra"


def test_fuente_real_se_construye_sin_credenciales():
    # FuenteCompuesta se construye aunque no haya adaptadores disponibles.
    r = comprobar_fuente(Config(fuente="real"))
    assert r.estado is Estado.OK
    assert r.extra["fuente"] == "real"


# --- Marcas / cuentas -------------------------------------------------------


def test_marcas_sin_cuentas_es_aviso():
    r = comprobar_marcas(Config(fuente="muestra"))
    assert r.estado is Estado.AVISO
    assert r.extra["cuentas"] == []


def test_marcas_con_cuentas_ok():
    cfg = Config(
        fuente="real",
        cuentas=[
            CuentaConfig(id="claro_sports", nombre="Claro Sports", plataformas={}),
            CuentaConfig(id="unotv", nombre="UnoTV", plataformas={}),
        ],
        marcas=["claro_sports"],
    )
    r = comprobar_marcas(cfg)
    assert r.estado is Estado.OK
    assert ("claro_sports", "Claro Sports") in r.extra["cuentas"]
    assert r.extra["alcance"] == ["claro_sports"]
    assert "claro_sports" in r.detalle


# --- Credenciales (sin filtrar secretos) ------------------------------------


def test_credenciales_muestra_son_avisos():
    resultados = comprobar_credenciales(Config(fuente="muestra"))
    # facebook, instagram, youtube, x, tiktok -> 5 lineas
    assert len(resultados) == 5
    assert all(r.estado is Estado.AVISO for r in resultados)


def test_credenciales_presentes_marcan_ok_y_no_filtran_secreto():
    secreto = "EAAB-super-secreto-123"
    cfg = Config(
        fuente="real",
        credenciales={
            "meta": {"access_token": secreto},
            "x": {"bearer_token": "AAAA-bearer"},
        },
    )
    resultados = comprobar_credenciales(cfg)
    por_plat = {r.extra["plataforma"]: r for r in resultados}
    # meta cubre facebook + instagram
    assert por_plat["facebook"].estado is Estado.OK
    assert por_plat["instagram"].estado is Estado.OK
    assert por_plat["x"].estado is Estado.OK
    # sin credenciales para estas
    assert por_plat["youtube"].estado is Estado.AVISO
    assert por_plat["tiktok"].estado is Estado.AVISO
    # NUNCA aparece el valor del secreto en lo que se renderiza
    informe = renderizar(resultados)
    assert secreto not in informe
    assert "AAAA-bearer" not in informe
    for r in resultados:
        assert secreto not in r.detalle


def test_x_acepta_access_token_como_alternativa():
    cfg = Config(fuente="real", credenciales={"x": {"access_token": "tok"}})
    por_plat = {r.extra["plataforma"]: r for r in comprobar_credenciales(cfg)}
    assert por_plat["x"].estado is Estado.OK


def test_credencial_vacia_cuenta_como_ausente():
    cfg = Config(fuente="real", credenciales={"meta": {"access_token": ""}})
    por_plat = {r.extra["plataforma"]: r for r in comprobar_credenciales(cfg)}
    assert por_plat["facebook"].estado is Estado.AVISO


# --- Credenciales agrupadas en UNA linea (UX-roadmap #4) --------------------


def test_resumir_credenciales_muestra_es_una_linea_aviso():
    r = resumir_credenciales(Config(fuente="muestra"))
    # Un unico Resultado, no una lista de 5.
    assert isinstance(r, Resultado)
    assert r.nombre == "Credenciales"
    assert r.estado is Estado.AVISO  # faltan credenciales -> AVISO, nunca ERROR
    assert not r.es_error
    # Resumen "0/5 plataformas conectadas" y la coletilla tranquilizadora.
    assert "0/5 plataformas conectadas" in r.detalle
    assert "muestra" in r.detalle
    # El detalle por plataforma se conserva de forma compacta y en extra.
    assert r.extra["total"] == 5
    assert r.extra["conectadas"] == 0
    assert set(r.extra["por_plataforma"]) == {
        "facebook",
        "instagram",
        "youtube",
        "x",
        "tiktok",
    }
    assert all(v is False for v in r.extra["por_plataforma"].values())


def test_resumir_credenciales_todas_conectadas_es_ok():
    cfg = Config(
        fuente="real",
        credenciales={
            "meta": {"access_token": "t"},
            "youtube": {"access_token": "t"},
            "x": {"bearer_token": "t"},
            "tiktok": {"access_token": "t"},
        },
    )
    r = resumir_credenciales(cfg)
    assert r.estado is Estado.OK
    assert "5/5 plataformas conectadas" in r.detalle
    assert r.extra["conectadas"] == 5


def test_resumir_credenciales_parcial_es_aviso_y_no_filtra_secreto():
    secreto = "EAAB-super-secreto-123"
    cfg = Config(fuente="real", credenciales={"meta": {"access_token": secreto}})
    r = resumir_credenciales(cfg)
    assert r.estado is Estado.AVISO
    # meta cubre facebook + instagram -> 2 conectadas de 5
    assert "2/5 plataformas conectadas" in r.detalle
    assert secreto not in r.detalle


def test_ejecutar_chequeos_credenciales_en_una_sola_linea(tmp_path):
    # Antes habia 5 lineas "Credenciales <plataforma>"; ahora UNA "Credenciales".
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    resultados = ejecutar_chequeos(
        Config(fuente="muestra"),
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[modelo],
    )
    lineas_cred = [r for r in resultados if r.nombre.startswith("Credenciales")]
    assert len(lineas_cred) == 1
    assert lineas_cred[0].nombre == "Credenciales"
    # Y nunca aparecen las viejas lineas por plataforma en el render.
    texto = renderizar(resultados)
    assert "Credenciales facebook" not in texto
    assert "Credenciales tiktok" not in texto
    assert texto.count("Credenciales:") == 1


# --- Binarios (which inyectado) ---------------------------------------------


def test_binario_presente_ok():
    r = comprobar_binario("ffmpeg", pista="instala", which=_which_falso({"ffmpeg"}))
    assert r.estado is Estado.OK
    assert r.extra["ruta"] == "/usr/local/bin/ffmpeg"


def test_binario_ausente_es_error():
    r = comprobar_binario("whisper-cli", pista="brew install whisper-cpp", which=_which_falso(set()))
    assert r.estado is Estado.ERROR
    assert "brew install whisper-cpp" in r.detalle
    assert r.extra["ruta"] is None


# --- Modelo whisper ---------------------------------------------------------


def test_modelo_en_ruta_conocida_ok(tmp_path):
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    r = comprobar_modelo_whisper(rutas=[tmp_path / "no.bin", modelo])
    assert r.estado is Estado.OK
    assert r.extra["ruta"] == str(modelo)
    assert r.extra["origen"] == "ruta"


def test_modelo_ausente_es_error(tmp_path):
    r = comprobar_modelo_whisper(rutas=[tmp_path / "a.bin", tmp_path / "b.bin"])
    assert r.estado is Estado.ERROR
    assert r.extra["ruta"] is None


def test_modelo_via_env_ok(tmp_path):
    modelo = tmp_path / "mi-modelo.bin"
    modelo.write_bytes(b"fake")
    r = comprobar_modelo_whisper(env_modelo=str(modelo), rutas=[])
    assert r.estado is Estado.OK
    assert r.extra["origen"] == "env"


def test_modelo_env_inexistente_es_error(tmp_path):
    r = comprobar_modelo_whisper(env_modelo=str(tmp_path / "no-existe.bin"))
    assert r.estado is Estado.ERROR
    assert r.extra["origen"] == "env"


# --- Orquestacion / render / codigo de salida -------------------------------


def test_ejecutar_chequeos_todo_listo(tmp_path):
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    cfg = Config(fuente="muestra")
    resultados = ejecutar_chequeos(
        cfg,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[modelo],
    )
    # ningun ❌ -> codigo 0
    assert codigo_salida(resultados) == 0
    assert all(not r.es_error for r in resultados)


def test_ejecutar_chequeos_falla_si_falta_binario_o_modelo(tmp_path):
    cfg = Config(fuente="muestra")
    resultados = ejecutar_chequeos(
        cfg,
        which=_which_falso(set()),  # ni whisper-cli ni ffmpeg
        rutas_modelo=[tmp_path / "nada.bin"],  # sin modelo
    )
    assert codigo_salida(resultados) == 1
    errores = [r for r in resultados if r.es_error]
    nombres = {r.nombre for r in errores}
    assert "binario whisper-cli" in nombres
    assert "binario ffmpeg" in nombres
    assert "modelo whisper" in nombres


def test_renderizar_incluye_resumen_y_iconos(tmp_path):
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    resultados = ejecutar_chequeos(
        Config(fuente="muestra"),
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[modelo],
    )
    texto = renderizar(resultados)
    assert "Autodiagnostico de keni-metricas" in texto
    assert "Resumen:" in texto
    assert Estado.OK.value in texto


# --- Cierre accionable: "que hacer ahora" (UX-roadmap #4) -------------------


def test_cierre_accionable_sin_errores_apunta_al_asistente():
    listos = [comprobar_python()]  # solo OK, ningun ❌
    cierre = cierre_accionable(listos)
    assert "Que hacer ahora" in cierre
    assert "python -m keni_metricas.asistente" in cierre


def test_cierre_accionable_con_errores_remite_a_las_lineas_error():
    rotos = [comprobar_python(version=(3, 9, 0))]  # un ❌
    cierre = cierre_accionable(rotos)
    assert "Que hacer ahora" in cierre
    assert "❌" in cierre
    # No debe sugerir el asistente cuando hay errores que resolver primero.
    assert "asistente" not in cierre


def test_renderizar_cierra_con_siguiente_paso_despues_del_resumen(tmp_path):
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    resultados = ejecutar_chequeos(
        Config(fuente="muestra"),
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[modelo],
    )
    texto = renderizar(resultados)
    # El cierre va DESPUES de la linea de resumen.
    pos_resumen = texto.index("Resumen:")
    pos_cierre = texto.index("Que hacer ahora")
    assert pos_cierre > pos_resumen
    # Con muestra y todo OK -> apunta al asistente.
    assert "python -m keni_metricas.asistente" in texto


def test_renderizar_con_error_cierra_remitiendo_a_lineas_error(tmp_path):
    # Sin whisper-cli/ffmpeg ni modelo -> hay ❌, el cierre cambia.
    resultados = ejecutar_chequeos(
        Config(fuente="muestra"),
        which=_which_falso(set()),
        rutas_modelo=[tmp_path / "no.bin"],
    )
    texto = renderizar(resultados)
    assert "Que hacer ahora" in texto
    assert "❌" in texto
    assert "python -m keni_metricas.asistente" not in texto


def test_codigo_salida_pura():
    listos = [comprobar_python()]
    assert codigo_salida(listos) == 0
    rotos = [comprobar_python(version=(3, 9, 0))]
    assert codigo_salida(rotos) == 1


# --- CLI (main) con config en tmp + which monkeypatcheado -------------------


def test_main_devuelve_0_cuando_todo_ok(monkeypatch, tmp_path, capsys):
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    # config valido en disco -> ✅ en config y fuente muestra por defecto
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('fuente = "muestra"\n', encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(cfg_file))
    monkeypatch.setenv("KENI_WHISPER_MODEL", str(modelo))
    # whisper-cli y ffmpeg "presentes"
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(doctor.shutil, "which", _which_falso({"whisper-cli", "ffmpeg"}))

    rc = main([])
    salida = capsys.readouterr().out
    assert rc == 0
    assert "Resumen:" in salida


def test_main_devuelve_1_cuando_falta_entorno(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    # sin whisper-cli/ffmpeg ni modelo -> debe fallar
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(doctor.shutil, "which", _which_falso(set()))
    monkeypatch.setattr(doctor, "_rutas_modelo_whisper", lambda: [tmp_path / "no.bin"])

    rc = main([])
    capsys.readouterr()
    assert rc == 1


def test_ejecutar_chequeos_lee_modelo_de_env_por_defecto(monkeypatch, tmp_path):
    # Sin inyectar env_modelo, debe honrar KENI_WHISPER_MODEL (como transcribir.sh).
    modelo = tmp_path / "ggml-large-v3-turbo.bin"
    modelo.write_bytes(b"fake")
    monkeypatch.setenv("KENI_WHISPER_MODEL", str(modelo))
    resultados = ejecutar_chequeos(
        Config(fuente="muestra"),
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        # rutas_modelo se deja por defecto: solo deberia pasar por la env var
    )
    modelo_r = next(r for r in resultados if r.nombre == "modelo whisper")
    assert modelo_r.estado is Estado.OK
    assert modelo_r.extra["origen"] == "env"


def test_main_env_modelo_inexistente_es_error(monkeypatch, tmp_path, capsys):
    # KENI_WHISPER_MODEL apuntando a un archivo ausente -> ❌ y rc=1.
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.setenv("KENI_WHISPER_MODEL", str(tmp_path / "no-model.bin"))
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(doctor.shutil, "which", _which_falso({"whisper-cli", "ffmpeg"}))
    rc = main([])
    salida = capsys.readouterr().out
    assert rc == 1
    assert "modelo whisper" in salida


def test_validar_offline_con_muestra_no_hace_red(monkeypatch, tmp_path):
    # --validar con fuente muestra: solo avisos, sin red, sin ❌ extra.
    cfg = cargar_config()  # fuente muestra por defecto
    resultados = ejecutar_chequeos(
        cfg,
        validar=True,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[tmp_path / "no.bin"],  # modelo ausente -> 1 error esperado
    )
    conectividad = [r for r in resultados if r.nombre.startswith("Conectividad")]
    assert conectividad, "deberia incluir una linea de conectividad"
    assert all(r.estado is Estado.AVISO for r in conectividad)


def test_validar_con_credenciales_marca_adaptador_disponible():
    cfg = Config(
        fuente="real",
        cuentas=[CuentaConfig(id="claro_sports", nombre="Claro Sports", plataformas={Plataforma.x: "123"})],
        credenciales={"x": {"bearer_token": "AAAA"}},
    )
    resultados = ejecutar_chequeos(
        cfg,
        validar=True,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[],
        env_modelo=None,
    )
    por_nombre = {r.nombre: r for r in resultados if r.nombre.startswith("Conectividad")}
    assert "Conectividad x" in por_nombre
    assert por_nombre["Conectividad x"].estado is Estado.OK


# --- Regresion B1: un config corrupto NO debe tumbar el doctor --------------


def test_config_corrupto_se_reporta_como_error_sin_crashear(tmp_path, monkeypatch):
    """Un config.toml mal formado debe salir como ❌ en el informe, no como traceback.

    Es justo lo que el doctor existe para diagnosticar: antes, `cargar_config`
    lanzaba `ConfigInvalida` y tumbaba el propio doctor.
    """
    malo = tmp_path / "config.toml"
    malo.write_text("no valido [[[\n", encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(malo))

    resultados = ejecutar_chequeos(
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[],
        env_modelo=None,
    )
    por_nombre = {r.nombre: r for r in resultados}
    assert por_nombre["Configuracion"].estado is Estado.ERROR
    # Los chequeos que dependen de la config se omiten (no se puede construir).
    assert "Fuente" not in por_nombre
    # Los chequeos independientes (Python, whisper) siguen presentes.
    assert por_nombre["Python"].estado is Estado.OK
    assert codigo_salida(resultados) == 1


def test_main_con_config_corrupto_devuelve_1_y_no_lanza(tmp_path, monkeypatch, capsys):
    malo = tmp_path / "config.toml"
    malo.write_text("clave = sin comillas ni valor [[[\n", encoding="utf-8")
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(malo))
    monkeypatch.setenv("KENI_WHISPER_MODEL", "")

    rc = main([])  # no debe lanzar
    salida = capsys.readouterr().out
    assert rc == 1
    assert "❌" in salida
    assert "Configuracion" in salida


# --- comprobar_fuente: rama de error al construir ---------------------------


def test_comprobar_fuente_error_se_reporta_como_error(monkeypatch):
    """Si construir_fuente lanza, comprobar_fuente devuelve ❌ con el detalle."""
    import keni_metricas.doctor as doctor

    def _explota(_cfg):
        raise RuntimeError("boom al construir")

    monkeypatch.setattr(doctor, "construir_fuente", _explota)
    r = comprobar_fuente(Config(fuente="real"))
    assert r.estado is Estado.ERROR
    assert "real" in r.detalle
    assert "boom al construir" in r.detalle
    assert r.extra["fuente"] == "real"


# --- cierre_accionable: rama con/sin error de forma directa -----------------


def test_cierre_accionable_lista_vacia_es_camino_sin_error():
    # Sin resultados no hay ningun ❌ -> camino "listo para demo".
    cierre = cierre_accionable([])
    assert "Que hacer ahora" in cierre
    assert "asistente" in cierre


# --- ejecutar_chequeos: cfg None defensivo (config invalida) ----------------


def test_ejecutar_chequeos_cfg_none_por_config_invalida(monkeypatch, tmp_path):
    """Si cargar_config lanza ConfigInvalida, el doctor reporta ❌ y no crashea.

    A diferencia del test con TOML roto en disco, aqui forzamos directamente la
    excepcion para ejercitar la rama defensiva de ejecutar_chequeos sin depender
    del parser de TOML.
    """
    import keni_metricas.doctor as doctor

    def _config_invalida():
        raise ConfigInvalida("config a proposito invalida")

    monkeypatch.setattr(doctor, "cargar_config", _config_invalida)
    resultados = ejecutar_chequeos(
        cfg=None,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[tmp_path / "no.bin"],
        env_modelo=None,
    )
    por_nombre = {r.nombre: r for r in resultados}
    assert por_nombre["Configuracion"].estado is Estado.ERROR
    assert "config a proposito invalida" in por_nombre["Configuracion"].detalle
    # Los chequeos dependientes de cfg se omiten.
    assert "Fuente" not in por_nombre
    assert "Cuentas" not in por_nombre
    # Los independientes siguen.
    assert por_nombre["Python"].estado is Estado.OK
    assert codigo_salida(resultados) == 1


def test_ejecutar_chequeos_cfg_none_sin_excepcion_mensaje_generico(monkeypatch, tmp_path):
    """Si cargar_config devuelve None sin lanzar, el detalle usa el texto generico."""
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(doctor, "cargar_config", lambda: None)
    resultados = ejecutar_chequeos(
        cfg=None,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[tmp_path / "no.bin"],
        env_modelo=None,
    )
    cfg_res = next(r for r in resultados if r.nombre == "Configuracion")
    assert cfg_res.estado is Estado.ERROR
    assert "No se pudo cargar la configuracion" in cfg_res.detalle


def test_validar_no_se_ejecuta_si_cfg_es_none(monkeypatch, tmp_path):
    """Con config invalida (cfg None), --validar NO debe añadir lineas Conectividad."""
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(
        doctor, "cargar_config", lambda: (_ for _ in ()).throw(ConfigInvalida("x"))
    )
    resultados = ejecutar_chequeos(
        cfg=None,
        validar=True,
        which=_which_falso({"whisper-cli", "ffmpeg"}),
        rutas_modelo=[tmp_path / "no.bin"],
        env_modelo=None,
    )
    assert not any(r.nombre.startswith("Conectividad") for r in resultados)


# --- validar_conectividad: ramas offline (todo monkeypatcheado, CERO red) ----


def test_validar_conectividad_fuente_no_construye(monkeypatch):
    """Si construir_fuente lanza, devuelve un unico AVISO (no crashea, no red)."""
    import keni_metricas.doctor as doctor

    monkeypatch.setattr(
        doctor,
        "construir_fuente",
        lambda _cfg: (_ for _ in ()).throw(RuntimeError("no se pudo")),
    )
    res = validar_conectividad(Config(fuente="real"))
    assert len(res) == 1
    assert res[0].nombre == "Conectividad"
    assert res[0].estado is Estado.AVISO
    assert "no se pudo construir la fuente" in res[0].detalle


def test_validar_conectividad_adaptadores_fallan_al_cargar(monkeypatch):
    """Fuente real construida, pero cargar adaptadores lanza -> AVISO."""
    import keni_metricas.doctor as doctor

    class _FuenteReal:
        nombre = "real"

    monkeypatch.setattr(doctor, "construir_fuente", lambda _cfg: _FuenteReal())
    monkeypatch.setattr(
        doctor,
        "_adaptadores_desde_config",
        lambda _cfg: (_ for _ in ()).throw(ImportError("modulo roto")),
    )
    res = validar_conectividad(Config(fuente="real"))
    assert len(res) == 1
    assert res[0].estado is Estado.AVISO
    assert "no se pudieron cargar los adaptadores" in res[0].detalle


def test_validar_conectividad_sin_adaptadores(monkeypatch):
    """Fuente real sin ningun adaptador con credenciales -> AVISO 'nada que validar'."""
    import keni_metricas.doctor as doctor

    class _FuenteReal:
        nombre = "real"

    monkeypatch.setattr(doctor, "construir_fuente", lambda _cfg: _FuenteReal())
    monkeypatch.setattr(doctor, "_adaptadores_desde_config", lambda _cfg: {})
    res = validar_conectividad(Config(fuente="real"))
    assert len(res) == 1
    assert res[0].estado is Estado.AVISO
    assert "nada que validar" in res[0].detalle


def test_validar_conectividad_adaptador_lanza_y_no_disponible(monkeypatch):
    """Un adaptador que lanza en disponible() y otro que devuelve False -> ambos AVISO."""
    import keni_metricas.doctor as doctor

    class _FuenteReal:
        nombre = "real"

    class _AdLanza:
        def disponible(self):
            raise RuntimeError("token caducado")

    class _AdNoDisponible:
        def disponible(self):
            return False

    monkeypatch.setattr(doctor, "construir_fuente", lambda _cfg: _FuenteReal())
    monkeypatch.setattr(
        doctor,
        "_adaptadores_desde_config",
        lambda _cfg: {"x": _AdLanza(), "youtube": _AdNoDisponible()},
    )
    res = validar_conectividad(Config(fuente="real"))
    por_nombre = {r.nombre: r for r in res}
    assert por_nombre["Conectividad x"].estado is Estado.AVISO
    assert "fallo al comprobarse" in por_nombre["Conectividad x"].detalle
    assert "token caducado" in por_nombre["Conectividad x"].detalle
    assert por_nombre["Conectividad youtube"].estado is Estado.AVISO
    assert "no disponible" in por_nombre["Conectividad youtube"].detalle


def test_validar_conectividad_adaptador_disponible_ok(monkeypatch):
    """Adaptador disponible() True -> Conectividad OK (rama positiva sin red)."""
    import keni_metricas.doctor as doctor

    class _FuenteReal:
        nombre = "real"

    class _AdOk:
        def disponible(self):
            return True

    monkeypatch.setattr(doctor, "construir_fuente", lambda _cfg: _FuenteReal())
    monkeypatch.setattr(doctor, "_adaptadores_desde_config", lambda _cfg: {"x": _AdOk()})
    res = validar_conectividad(Config(fuente="real"))
    assert len(res) == 1
    assert res[0].nombre == "Conectividad x"
    assert res[0].estado is Estado.OK
