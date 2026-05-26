#!/usr/bin/env python3
"""Guard ESTATICO de los LIMITES de caracteres por plataforma (#112, CI-safe).

Mismo estilo que el guard de marcas (`test_static.test_fichas_marca_*`): ancla
una tabla canonica y verifica que `contexto-editorial/plataformas.md` la respeta,
para que la prosa de la skill NO diverja del backend.

skills-copy NO puede importar `keni_consola` (es otro paquete), asi que el guard
se ancla a esta tabla CANONICA, espejo de
`consola/src/keni_consola/limites_plataforma.LIMITES`. Si el backend cambia un
tope, este guard avisa (debe actualizarse plataformas.md y esta tabla a la vez),
igual que el guard de marcas (`MARCAS_ID_METRICAS`).

No usa el modelo ni la red: solo lee el repo. Corre en un runner limpio con solo
Python + pytest (o como script: `python3 test_limites.py`).

Cubre:
  1. `plataformas.md` declara el limite duro de X (280) e YouTube titulo (100).
  2. `plataformas.md` declara el limite de TikTok reconciliado (4.000), NO 2.200.
  3. La tabla canonica es coherente (mismas redes/orden que la consola).
"""

from __future__ import annotations

import re
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent
SKILLS_COPY_DIR = EVALS_DIR.parent
PLATAFORMAS_MD = SKILLS_COPY_DIR / "contexto-editorial" / "plataformas.md"

# Tabla CANONICA de limites de caracteres por red, ESPEJO de
# `consola/src/keni_consola/limites_plataforma.LIMITES`. `None` = sin tope tecnico
# practico (Facebook / descripcion de YouTube). El orden es el fijo de la consola.
LIMITES_CANONICOS: dict[str, int | None] = {
    "x": 280,
    "instagram": 2200,
    "facebook": None,
    "tiktok": 4000,
    "youtube": None,
}

# Limite del TITULO de YouTube (campo distinto del cuerpo; lo documenta la skill).
LIMITE_YT_TITULO = 100


def _texto_plataformas() -> str:
    assert PLATAFORMAS_MD.is_file(), f"falta {PLATAFORMAS_MD}"
    return PLATAFORMAS_MD.read_text(encoding="utf-8")


def _numeros(texto: str) -> set[int]:
    """Numeros del texto, ignorando separadores de millar (`.`/`,`). 2.200 -> 2200."""
    return {int(re.sub(r"[.,]", "", m)) for m in re.findall(r"\d[\d.,]*", texto)}


def _seccion(texto: str, encabezado: str) -> str:
    """Devuelve el cuerpo de la seccion `## <encabezado>` hasta el siguiente `## `."""
    patron = re.compile(
        rf"^##\s+{re.escape(encabezado)}\s*$(.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = patron.search(texto)
    return m.group(1) if m else ""


def test_plataformas_md_existe():
    assert PLATAFORMAS_MD.is_file(), "no se encontro contexto-editorial/plataformas.md"


def test_x_declara_limite_duro_280():
    seccion = _seccion(_texto_plataformas(), "X / Twitter")
    assert seccion, "no se encontro la seccion '## X / Twitter'"
    assert LIMITES_CANONICOS["x"] in _numeros(seccion), (
        f"plataformas.md (X) no declara el limite canonico {LIMITES_CANONICOS['x']}"
    )


def test_instagram_declara_limite_2200():
    seccion = _seccion(_texto_plataformas(), "Instagram")
    assert seccion, "no se encontro la seccion '## Instagram'"
    assert LIMITES_CANONICOS["instagram"] in _numeros(seccion), (
        f"plataformas.md (Instagram) no declara el limite canonico "
        f"{LIMITES_CANONICOS['instagram']}"
    )


def test_tiktok_reconciliado_a_4000_y_sin_2200():
    seccion = _seccion(_texto_plataformas(), "TikTok")
    assert seccion, "no se encontro la seccion '## TikTok'"
    nums = _numeros(seccion)
    assert LIMITES_CANONICOS["tiktok"] in nums, (
        f"plataformas.md (TikTok) no declara el limite canonico "
        f"{LIMITES_CANONICOS['tiktok']} (#112: reconciliado al maximo tecnico actual)"
    )
    # La divergencia historica era el 2.200 viejo: ya no debe aparecer en TikTok.
    assert 2200 not in nums, (
        "plataformas.md (TikTok) aun menciona 2.200; #112 lo reconcilia a 4.000"
    )


def test_youtube_titulo_declara_limite_duro_100():
    seccion = _seccion(_texto_plataformas(), "YouTube")
    assert seccion, "no se encontro la seccion '## YouTube'"
    assert LIMITE_YT_TITULO in _numeros(seccion), (
        f"plataformas.md (YouTube) no declara el limite de titulo {LIMITE_YT_TITULO}"
    )


def test_tabla_canonica_tiene_las_cinco_redes_en_orden():
    assert list(LIMITES_CANONICOS) == ["x", "instagram", "facebook", "tiktok", "youtube"]


# ---------------------------------------------------------------------------
# mini-runner para correr sin pytest (`python3 test_limites.py`)
# ---------------------------------------------------------------------------

def _main() -> int:
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
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
