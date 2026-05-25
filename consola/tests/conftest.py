"""Fixtures compartidas de los tests de la Consola Keni (API JSON). Todo OFFLINE.

Aisla en `tmp_path` (env vars) toda la persistencia y configuracion para que
ningun test toque el disco real del usuario:
  - `KENI_CONSOLA_CONFIG`  -> consola.toml (allowlist de proyectos)
  - `KENI_CONSOLA_DB`      -> consola.db (SQLite: tareas + historial de skills)
  - `KENI_CONSOLA_RAIZ`    -> raiz de datos del backend de ficheros (YAML por marca)
  - `KENI_CONSOLA_INDICE`  -> indice SQLite regenerable del backend de ficheros
  - `KENI_CONSOLA_TAREAS`  -> tareas.json (solo para probar la migracion)
  - `KENI_CONSOLA_MEDIA`   -> dir de media (imagenes) aislado en tmp
  - `KENI_CONSOLA_SECRETOS`-> almacen de secretos (clave de imagen) aislado en tmp
  - `KENI_METRICAS_CONFIG` -> apunta a un archivo inexistente => fuente de muestra
  - `KENI_SKILLS_CWD`      -> cwd valido para skills (no toca el repo real)

Tambien BORRA `OPENAI_API_KEY` para que, por defecto, la generacion de imagen este
"no configurada" (camino 400). Los tests que prueban un proveedor lo parchean.

Nada de red, nada de tokens reales, nunca se llama a `claude` (el runner se mockea).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config + DB aisladas en tmp; metricas offline (fuente de muestra)."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    monkeypatch.setenv("KENI_SKILLS_CWD", str(tmp_path))
    # Almacen de generaciones (trabajos de IA en background) aislado en tmp.
    monkeypatch.setenv("KENI_CONSOLA_GENERACIONES", str(tmp_path / "generaciones"))
    return tmp_path


def _lanzador_run_noop(marca_id, run_id, prompt, *, cwd):  # noqa: ANN001
    """Fake del lanzador de runs en background: NO usa Popen ni red, deja el run tal cual.

    Por defecto el run queda en `estado="ejecutando"` (como recien lanzado). Los tests
    que quieran simular avance/terminacion parchean `api.agentes.lanzar_run_background`
    por una fake propia que escribe estados/medidas en el YAML.
    """
    return None


def _lanzador_generacion_noop(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
    """Fake del lanzador de generaciones de claude: NO usa Popen ni red.

    Deja la generacion en `estado="ejecutando"`. Los tests que necesiten el resultado
    pasan `lanzar_generacion=lanzador_generacion_completa(salida, metricas)` a `_cliente`.
    """
    import shutil as _sh

    if dir_temporal is not None:
        _sh.rmtree(dir_temporal, ignore_errors=True)
    return None


def _lanzador_imagen_noop(gen_id, *, generar):  # noqa: ANN001
    """Fake del lanzador de imagen: NO toca la red. Deja la generacion en `ejecutando`."""
    return None


def lanzador_generacion_completa(salida: str, metricas=None):  # noqa: ANN001
    """Fake del lanzador de claude que COMPLETA la generacion SINCRONAMENTE.

    Llama al `procesar` REAL con una `salida` canned (asi se cubre el post-procesado:
    piezas/publicaciones/historial/hashtags) y fija el registro en `completado`. Sin
    Popen ni red. Equivale a lo que antes hacia `monkeypatch.setattr(skills, "_runner", ...)`.
    """
    import shutil as _sh

    from keni_consola import generaciones
    from keni_consola.api import skills

    def lanzar(gen_id, *, prompt, cwd, procesar, dir_temporal=None):  # noqa: ANN001
        if dir_temporal is not None:
            _sh.rmtree(dir_temporal, ignore_errors=True)
        resultado = procesar(salida, metricas)
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "salida": salida,
                "metricas": skills.metricas_a_dict(metricas),
                "resultado": resultado,
                "fecha_fin": generaciones.ahora_iso(),
            },
        )

    return lanzar


def lanzador_imagen_completa(resultado: dict):
    """Fake del lanzador de imagen que COMPLETA la generacion con `resultado` (sin red)."""
    from keni_consola import generaciones

    def lanzar(gen_id, *, generar):  # noqa: ANN001
        generaciones.actualizar(
            gen_id,
            {
                "estado": generaciones.ESTADO_COMPLETADO,
                "resultado": resultado,
                "fecha_fin": generaciones.ahora_iso(),
            },
        )

    return lanzar


def lanzador_imagen_ejecuta():
    """Fake del lanzador de imagen que EJECUTA `generar` SINCRONAMENTE (sin hilo).

    Corre el `generar` real del endpoint (con su proveedor MOCK) y fija el estado segun
    el resultado. Asi se cubre el pipeline real (generar -> guardar -> servir) sin red.
    """
    from keni_consola import generaciones

    def lanzar(gen_id, *, generar):  # noqa: ANN001
        try:
            resultado = generar()
        except Exception as e:  # noqa: BLE001 -- reflejamos el error como la generacion real
            generaciones.actualizar(
                gen_id,
                {"estado": generaciones.ESTADO_ERROR, "error": str(e) or "error",
                 "fecha_fin": generaciones.ahora_iso()},
            )
            return
        generaciones.actualizar(
            gen_id,
            {"estado": generaciones.ESTADO_COMPLETADO, "resultado": resultado,
             "fecha_fin": generaciones.ahora_iso()},
        )

    return lanzar


def _cliente(abrir=None, lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None) -> TestClient:
    """TestClient de la app. Ningun lanzador toca nada real (mocks).

    `abrir` (interactivo), `lanzar_run` (runs headless), `lanzar_generacion` (trabajos de
    copy/RSS/hashtags) y `lanzar_imagen` (imagen) se inyectan por defecto a fakes
    inofensivas para que NUNCA se llame a `claude`, a un proveedor de imagen, ni se abra
    Terminal. Los tests que necesiten un resultado pasan una fake "completa".
    """
    if abrir is None:
        def abrir(_ruta):  # noqa: ANN001
            return "ok-mock"
    if lanzar_run is None:
        lanzar_run = _lanzador_run_noop
    if lanzar_generacion is None:
        lanzar_generacion = _lanzador_generacion_noop
    if lanzar_imagen is None:
        lanzar_imagen = _lanzador_imagen_noop

    return TestClient(
        app_modulo.crear_app(
            abrir=abrir,
            lanzar_run=lanzar_run,
            lanzar_generacion=lanzar_generacion,
            lanzar_imagen=lanzar_imagen,
        )
    )


@pytest.fixture
def cliente(entorno):
    """TestClient listo con el entorno aislado (mock de `abrir` inofensivo)."""
    return _cliente()
