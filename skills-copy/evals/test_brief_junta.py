#!/usr/bin/env python3
"""Tests del cruce "ya publicado / pendiente" del brief de la junta (F2, #142).

Cubren el script `publicado.py` de la skill `brief-matutino`: que lee el historial
editorial (publicaciones YAML de la Consola), respeta la ventana de días, y degrada
con HONESTIDAD cuando no hay almacén o no hay piezas recientes (sin inventar).

Python puro + PyYAML (que el CI estatico instala). Sin modelo, sin red, sin whisper.
Si no hay pytest, este fichero también corre como script con un mini-runner al final.

    python3 skills-copy/evals/test_brief_junta.py
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

_SKILL_DIR = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "brief-matutino"
_PUBLICADO_PY = _SKILL_DIR / "publicado.py"


def _cargar_publicado():
    """Importa publicado.py como módulo aislado (no está en un paquete)."""
    spec = importlib.util.spec_from_file_location("brief_publicado", _PUBLICADO_PY)
    assert spec and spec.loader, f"no se pudo cargar {_PUBLICADO_PY}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


publicado = _cargar_publicado()


# --------------------------------------------------------------------------- #
# Helpers: sembrar un almacén de publicaciones en disco                       #
# --------------------------------------------------------------------------- #


def _sembrar(raiz: Path, marca: str, *, titulo: str, red: str = "instagram",
            estado: str = "publicado", origen: str = "copy-desde-nota",
            hace_horas: float = 1.0) -> None:
    """Escribe un YAML de publicación con la forma que escribe la Consola."""
    carpeta = raiz / marca / "publicaciones"
    carpeta.mkdir(parents=True, exist_ok=True)
    creado = (datetime.now() - timedelta(hours=hace_horas)).isoformat(timespec="seconds")
    cuerpo = (
        f"titulo: {titulo}\n"
        f"red: {red}\n"
        f"estado: {estado}\n"
        "veredicto: ok\n"
        "evergreen: false\n"
        f"fecha_creacion: '{creado}'\n"
        f"fecha_actualizacion: '{creado}'\n"
        "fecha_programada: ''\n"
        f"origen: {origen}\n"
        "imagen: ''\n"
        "contenido: |-\n"
        "  Cuerpo de prueba.\n"
        "  Segunda línea (no debe colarse en la cabecera).\n"
    )
    nombre = "".join(c for c in titulo.lower() if c.isalnum())[:12] or "pub"
    (carpeta / f"{nombre}.yaml").write_text(cuerpo, encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1) El script existe y es ejecutable como módulo                             #
# --------------------------------------------------------------------------- #


def test_publicado_existe():
    assert _PUBLICADO_PY.is_file(), f"no existe {_PUBLICADO_PY}"


# --------------------------------------------------------------------------- #
# 2) Lee piezas dentro de la ventana                                          #
# --------------------------------------------------------------------------- #


def test_trabajado_lee_piezas_recientes():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        _sembrar(raiz, "claro-sports", titulo="Golazo de México", hace_horas=2)
        items, aviso = publicado.trabajado("claro-sports", dias=4, raiz=raiz)
        assert aviso is None, f"no debería avisar con datos: {aviso}"
        assert len(items) == 1
        it = items[0]
        assert it["titulo"] == "Golazo de México"
        assert it["red"] == "instagram"
        assert it["estado"] == "publicado"
        assert it["origen"] == "copy-desde-nota"


def test_trabajado_ordena_reciente_primero():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        _sembrar(raiz, "unotv", titulo="Nota vieja", hace_horas=20)
        _sembrar(raiz, "unotv", titulo="Nota nueva", hace_horas=1)
        items, aviso = publicado.trabajado("unotv", dias=4, raiz=raiz)
        assert aviso is None
        assert [it["titulo"] for it in items] == ["Nota nueva", "Nota vieja"]


# --------------------------------------------------------------------------- #
# 3) Respeta la ventana de días                                               #
# --------------------------------------------------------------------------- #


def test_trabajado_descarta_fuera_de_ventana():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        # 10 días atrás, ventana de 4 días -> no entra, y avisa de "nada reciente".
        _sembrar(raiz, "claro-sports", titulo="Muy vieja", hace_horas=24 * 10)
        items, aviso = publicado.trabajado("claro-sports", dias=4, raiz=raiz)
        assert items == []
        assert aviso is not None and "pendiente" in aviso.lower()


# --------------------------------------------------------------------------- #
# 4) Degradación honesta: sin almacén / vacío                                 #
# --------------------------------------------------------------------------- #


def test_degrada_sin_almacen():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)  # ninguna marca sembrada
        items, aviso = publicado.trabajado("claro-sports", dias=4, raiz=raiz)
        assert items == []
        assert aviso is not None
        assert "pendiente" in aviso.lower()
        # No debe inventar: el aviso menciona que NO hay almacén / historial.
        assert "almacén" in aviso.lower() or "historial" in aviso.lower()


def test_degrada_carpeta_vacia():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        (raiz / "claro-sports" / "publicaciones").mkdir(parents=True)
        items, aviso = publicado.trabajado("claro-sports", dias=4, raiz=raiz)
        assert items == []
        assert aviso is not None and "pendiente" in aviso.lower()


# --------------------------------------------------------------------------- #
# 5) El lector mínimo (sin PyYAML) no se traga el bloque `contenido: |`        #
# --------------------------------------------------------------------------- #


def test_lector_minimo_corta_en_el_bloque_contenido():
    texto = (
        "titulo: Prueba\n"
        "red: tiktok\n"
        "estado: borrador\n"
        "fecha_creacion: '2026-05-27T10:00:00'\n"
        "origen: clip-a-copy\n"
        "contenido: |-\n"
        "  titulo: ESTO-NO-DEBE-LEERSE\n"
        "  red: ESTO-TAMPOCO\n"
    )
    datos = publicado._leer_yaml_minimo(texto)
    assert datos["titulo"] == "Prueba"
    assert datos["red"] == "tiktok"
    assert datos["estado"] == "borrador"
    assert datos["origen"] == "clip-a-copy"
    # El cuerpo indentado bajo `contenido: |-` NO debe sobrescribir la cabecera.
    assert "ESTO" not in datos["titulo"]
    assert datos["red"] == "tiktok"


# --------------------------------------------------------------------------- #
# 6) La CLI imprime markdown escaneable y degrada con un aviso `>`            #
# --------------------------------------------------------------------------- #


def _correr_cli(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(_PUBLICADO_PY), *args],
        capture_output=True, text=True, check=True,
    )
    return proc.stdout


def test_cli_con_datos_lista_la_pieza():
    with tempfile.TemporaryDirectory() as tmp:
        raiz = Path(tmp)
        _sembrar(raiz, "claro-sports", titulo="Final del Clausura", hace_horas=3)
        salida = _correr_cli("--marca", "claro-sports", "--raiz", str(raiz), "--dias", "4")
        assert "Ya trabajado por nosotros" in salida
        assert "Final del Clausura" in salida


def test_cli_sin_datos_degrada_honesto():
    with tempfile.TemporaryDirectory() as tmp:
        salida = _correr_cli("--marca", "unotv", "--raiz", tmp)
        assert salida.lstrip().splitlines()  # no vacío
        assert ">" in salida  # bloque de aviso de degradación
        assert "PENDIENTE" in salida.upper()


# --------------------------------------------------------------------------- #
# mini-runner para correr sin pytest (`python3 test_brief_junta.py`)          #
# --------------------------------------------------------------------------- #


def _main() -> int:
    funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fallos = 0
    for f in funcs:
        try:
            f()
            print(f"PASS {f.__name__}")
        except AssertionError as e:
            fallos += 1
            print(f"FAIL {f.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            fallos += 1
            print(f"ERROR {f.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(funcs) - fallos}/{len(funcs)} pruebas OK")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(_main())
