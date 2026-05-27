"""Fixtures compartidas de los tests de la Consola Keni (API JSON). Todo OFFLINE.

Aisla en `tmp_path` (env vars) toda la persistencia y configuracion para que
ningun test toque el disco real del usuario:
  - `KENI_CONSOLA_CONFIG`  -> consola.toml (allowlist de proyectos)
  - `KENI_CONSOLA_DB`      -> consola.db (SQLite: tareas + comercial)
  - `KENI_CONSOLA_RAIZ`    -> raiz de datos del backend de ficheros (YAML por marca)
  - `KENI_CONSOLA_INDICE`  -> indice SQLite regenerable del backend de ficheros
  - `KENI_CONSOLA_TAREAS`  -> tareas.json (solo para probar la migracion)
  - `KENI_CONSOLA_MEDIA`   -> dir de media (imagenes) aislado en tmp
  - `KENI_CONSOLA_SECRETOS`-> almacen de secretos (clave de imagen) aislado en tmp
  - `KENI_CONSOLA_PREFERENCIAS`-> preferencias (esfuerzo de generacion) aisladas en tmp
  - `KENI_CONSOLA_SUGERENCIAS`-> buzon de sugerencias (JSON local) aislado en tmp
  - `KENI_CONSOLA_TERMOMETRO`-> config del Termometro mundial (JSON local) aislada en tmp
  - `KENI_METRICAS_CONFIG` -> apunta a un archivo inexistente => fuente de muestra
  - `KENI_SKILLS_CWD`      -> cwd valido para skills (no toca el repo real)
  - `KENI_SKILLS_DIR`      -> catalogo de skills FALSO en tmp (sembrado; no toca skills-copy/)

Tambien BORRA `OPENAI_API_KEY` para que, por defecto, la generacion de imagen este
"no configurada" (camino 400). Los tests que prueban un proveedor lo parchean.

Nada de red, nada de tokens reales, nunca se llama a `claude` (el runner se mockea).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.testclient import TestClient

from keni_consola import app as app_modulo

# --------------------------------------------------------------------------- #
# Catalogo de skills FALSO, aislado en tmp (env KENI_SKILLS_DIR)              #
# --------------------------------------------------------------------------- #
#
# Los tests NO deben leer/escribir el `skills-copy/` real del repo. `entorno` apunta
# `KENI_SKILLS_DIR` a un tmp y lo siembra con UNAS POCAS skills falsas que cubren las
# tres formas: piezas+redes, documento y media (archivo). Conservamos los MISMOS ids
# que ya usan los tests existentes (`copy-desde-nota`, `clip-a-copy`) para no reescribir
# test_api_rss / test_metricas_runs, y anadimos un `resumen-tendencia` de salida documento.

_SKILLS_SEMILLA: dict[str, dict] = {
    # piezas + aplica_redes (como copy-desde-nota real)
    "copy-desde-nota": {
        "md": "# copy-desde-nota\n\nConvierte una nota en copy por red.\n",
        "meta": {
            "nombre": "Copy desde nota",
            "explicacion": "Convierte una nota en copy listo para publicar por red.",
            "grupo": "validadas",
            "aplica_redes": True,
            "salida": "piezas",
            "media": False,
            "orden": 10,
            "campos": [
                {
                    "id": "fuente",
                    "etiqueta": "Nota o transcripción",
                    "tipo": "textarea",
                    "requerido": True,
                    "placeholder": "Pega aquí la nota…",
                    "ayuda": "",
                    "opciones": [],
                    "media_tipos": "",
                }
            ],
            "plantilla_invocacion": "usa copy-desde-nota con la siguiente nota, marca {marca}:\n\n{fuente}\n",
        },
    },
    # documento (sin redes)
    "resumen-tendencia": {
        "md": "# resumen-tendencia\n\nResume un tema en un brief.\n",
        "meta": {
            "nombre": "Resumen de tendencia",
            "explicacion": "Resume un tema en un brief corto.",
            "grupo": "validadas",
            "aplica_redes": False,
            "salida": "documento",
            "media": False,
            "orden": 40,
            "campos": [
                {
                    "id": "fuentes",
                    "etiqueta": "Fuentes del tema",
                    "tipo": "textarea",
                    "requerido": True,
                    "placeholder": "Pega aquí las fuentes…",
                    "ayuda": "",
                    "opciones": [],
                    "media_tipos": "",
                }
            ],
            "plantilla_invocacion": "usa resumen-tendencia con las siguientes fuentes, marca {marca}:\n\n{fuentes}\n",
        },
    },
    # media (archivo) + piezas (como clip-a-copy real)
    "clip-a-copy": {
        "md": "# clip-a-copy\n\nDe un video/audio a copy por red.\n",
        "meta": {
            "nombre": "Clip a copy",
            "explicacion": "De un video o audio saca copy por red.",
            "grupo": "experimentales",
            "aplica_redes": True,
            "salida": "piezas",
            "media": True,
            "orden": 20,
            "campos": [
                {
                    "id": "archivo",
                    "etiqueta": "Video o audio",
                    "tipo": "archivo",
                    "requerido": True,
                    "placeholder": "",
                    "ayuda": "",
                    "opciones": [],
                    "media_tipos": "video/*,audio/*",
                }
            ],
            "plantilla_invocacion": "usa clip-a-copy con el archivo en esta ruta, marca {marca}:\n\n{archivo}\n",
        },
    },
}


def sembrar_skills(dir_skills: Path, skills: dict[str, dict] | None = None) -> Path:
    """Crea un catalogo de skills falso en `dir_skills` (una carpeta por skill).

    `skills` mapea `id -> {"md": <SKILL.md>, "meta": <dict de keni.yaml>}`. Por defecto
    siembra `_SKILLS_SEMILLA` (piezas+redes, documento, media). Devuelve `dir_skills`.
    """
    import yaml

    skills = skills if skills is not None else _SKILLS_SEMILLA
    for skill_id, contenido in skills.items():
        carpeta = dir_skills / skill_id
        carpeta.mkdir(parents=True, exist_ok=True)
        (carpeta / "SKILL.md").write_text(contenido["md"], encoding="utf-8")
        (carpeta / "keni.yaml").write_text(
            yaml.safe_dump(contenido["meta"], allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    return dir_skills


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Config + DB aisladas en tmp; metricas offline; catalogo de skills falso en tmp."""
    monkeypatch.setenv("KENI_CONSOLA_CONFIG", str(tmp_path / "consola.toml"))
    monkeypatch.setenv("KENI_CONSOLA_DB", str(tmp_path / "consola.db"))
    monkeypatch.setenv("KENI_CONSOLA_RAIZ", str(tmp_path / "datos"))
    monkeypatch.setenv("KENI_CONSOLA_INDICE", str(tmp_path / "indice.sqlite"))
    monkeypatch.setenv("KENI_CONSOLA_TAREAS", str(tmp_path / "tareas.json"))
    monkeypatch.setenv("KENI_CONSOLA_MEDIA", str(tmp_path / "media"))
    monkeypatch.setenv("KENI_CONSOLA_SECRETOS", str(tmp_path / "secretos.toml"))
    monkeypatch.setenv("KENI_CONSOLA_PREFERENCIAS", str(tmp_path / "preferencias.toml"))
    monkeypatch.setenv("KENI_CONSOLA_SUGERENCIAS", str(tmp_path / "sugerencias.json"))
    monkeypatch.setenv("KENI_CONSOLA_TERMOMETRO", str(tmp_path / "termometro.json"))
    # Token de sesion (#134): lo borramos del entorno para que `crear_app` use el que
    # le pasamos (TOKEN_PRUEBA) y no uno del shell del usuario. Determinismo en tests.
    monkeypatch.delenv("KENI_CONSOLA_TOKEN", raising=False)
    monkeypatch.setenv("KENI_METRICAS_CONFIG", str(tmp_path / "noexiste.toml"))
    monkeypatch.delenv("KENI_METRICAS_FUENTE", raising=False)
    monkeypatch.delenv("KENI_METRICAS_MARCAS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KENI_METRICAS_HISTORICO", "0")
    monkeypatch.setenv("KENI_SKILLS_CWD", str(tmp_path))
    # Catalogo de skills aislado en tmp (NO toca el `skills-copy/` real) + sembrado.
    dir_skills = tmp_path / "skills"
    sembrar_skills(dir_skills)
    monkeypatch.setenv("KENI_SKILLS_DIR", str(dir_skills))
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
        # Igual que el lanzador real: el temporal se borra DESPUES de `procesar`, porque
        # el post-procesado de las skills de imagen importa al media los .png que la skill
        # dejo en ese dir. Borrarlo antes los perderia (ver generaciones._finalizar).
        try:
            resultado = procesar(salida, metricas)
        finally:
            if dir_temporal is not None:
                _sh.rmtree(dir_temporal, ignore_errors=True)
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


# Token de sesion FIJO para los tests (#134). `_cliente` lo inyecta a `crear_app` y
# lo manda por defecto en CADA peticion del TestClient, asi los ~600 tests existentes
# de la API pasan la barrera de auth sin cambios. Los tests de seguridad construyen un
# cliente SIN este header (`_cliente_sin_token`) para probar el rechazo (401/403).
TOKEN_PRUEBA = "token-de-prueba-1234567890"


def _cliente(
    abrir=None, lanzar_run=None, lanzar_generacion=None, lanzar_imagen=None,
    token=TOKEN_PRUEBA, autenticar=True, bootstrap=False,
) -> TestClient:
    """TestClient de la app. Ningun lanzador toca nada real (mocks).

    `abrir` (interactivo), `lanzar_run` (runs headless), `lanzar_generacion` (trabajos de
    copy/RSS/hashtags) y `lanzar_imagen` (imagen) se inyectan por defecto a fakes
    inofensivas para que NUNCA se llame a `claude`, a un proveedor de imagen, ni se abra
    Terminal. Los tests que necesiten un resultado pasan una fake "completa".

    `token` fija el token de sesion de la app (#134). Si `autenticar` (def), el cliente
    manda `Authorization: Bearer <token>` por defecto en cada peticion para que los tests
    de API existentes pasen la auth sin cambios. Pasa `autenticar=False` para probar el
    rechazo sin token.

    `bootstrap` (def False): los tests que NO prueban la auth multiusuario (#130) no
    crean el admin inicial, asi evitan el coste del hash scrypt y siguen pasando por la
    via del TOKEN. Los tests de auth/usuarios lo activan (o crean usuarios a mano).
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

    cabeceras = {"Authorization": f"Bearer {token}"} if autenticar else None
    return TestClient(
        app_modulo.crear_app(
            abrir=abrir,
            lanzar_run=lanzar_run,
            lanzar_generacion=lanzar_generacion,
            lanzar_imagen=lanzar_imagen,
            token=token,
            bootstrap=bootstrap,
        ),
        headers=cabeceras,
    )


@pytest.fixture
def cliente(entorno):
    """TestClient listo con el entorno aislado (mock de `abrir` inofensivo)."""
    return _cliente()
