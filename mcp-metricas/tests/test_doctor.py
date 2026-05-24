"""Tests del autodiagnostico (`keni_metricas.doctor`).

Todo OFFLINE: config en tmp_path, `shutil.which` y las rutas del modelo de whisper
se inyectan/monkeypatchean. No se toca el PATH real ni la red. La comprobacion de
conectividad (`--validar`) NO es requerida por estos tests.
"""

from __future__ import annotations

import sys

import pytest

from keni_metricas.config import Config, CuentaConfig, cargar_config
from keni_metricas.doctor import (
    Estado,
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
