"""Lanzador NEUTRO de generaciones de IA (`claude -p`), único punto de lanzamiento.

Reemplaza a `dominio.skills.lanzar_generacion_*` tras retirar el sistema de skills. Compone
el prompt final (cuerpo del prompt + línea editorial adjunta + contexto + instrucción de
redes), crea el registro de generación y lo ENCOLA reutilizando la infra de `generaciones`
(`encolar_job_claude` + worker + sondeo). El post-procesado (parsear piezas, crear
borradores, etc.) llega como `procesar` + `procesar_spec` (kinds de `jobspec`, fábricas en
`dominio.copy`/`dominio.qa_editorial`/`dominio.hashtags`).

Los prompts son AUTOCONTENIDOS: la línea editorial y la entrada van DENTRO del prompt, así
que `claude` corre con un cwd NEUTRO (`jobspec.CWD_GENERACION`), sin depender de `skills-copy/`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import biblioteca, generaciones, marcas, redes
from . import jobspec

# Instrucción ADITIVA de estilo en todo prompt de generación (defensa en profundidad; además
# `quitar_emojis` los borra de forma determinista en el post-procesado de documento).
INSTRUCCION_SIN_EMOJIS = "No uses emojis en el copy."

# Catálogo de marcas (id -> nombre humano). Fuente única `keni_shared.marcas`.
_MARCA_NOMBRE: dict[str, str] = dict(marcas.opciones())
MARCAS_IDS = frozenset(_MARCA_NOMBRE)

# Tope del texto de entrada (nota/transcripción/contexto) en caracteres.
MAX_TEXTO = 200_000


def marca_valida(marca: object) -> bool:
    """True si `marca` es un id de marca del catálogo."""
    return isinstance(marca, str) and marca in MARCAS_IDS


def nombre_marca(marca: str) -> str:
    """Nombre humano de una marca (cae al id si no está en el catálogo)."""
    return _MARCA_NOMBRE.get(marca, marca)


def cwd_generacion() -> Path:
    """cwd writable y NEUTRO de `claude` para prompts autocontenidos (delega en jobspec)."""
    return jobspec.cwd_generacion()


def instruccion_redes(redes_ids: list[str]) -> str:
    """Instrucción ADITIVA: limita las redes y pide un bloque json con las piezas por red."""
    etiquetas = ", ".join(redes.nombre_por_id(r) for r in redes_ids)
    ids_json = ", ".join(f'"{r}"' for r in redes_ids)
    return (
        f"Genera el copy SOLO para estas redes: {etiquetas}. "
        "Mantén tu formato y tu auto-verificación habituales. "
        "Además, al FINAL de toda tu respuesta, añade un único bloque de código "
        'cercado ```json con esta forma exacta: {"piezas": [{"red": "<id>", '
        '"texto": "<copy de esa red>"}, ...]}, usando como <id> únicamente estos '
        f"valores: {ids_json}. Incluye una pieza por cada red pedida."
    )


def componer(
    cuerpo_prompt: str,
    adjuntos: list[biblioteca.Documento],
    bloque_contexto: str,
    *,
    sin_emojis: bool = False,
    redes_ids: list[str] | None = None,
) -> str:
    """Arma el prompt final autocontenido: prompt + editorial adjunta + contexto.

    `sin_emojis`/`redes_ids` son ADITIVOS y OPT-IN (específicos de copy): por defecto NO se
    añaden, para que un prompt cualquiera de la Biblioteca no quede forzado a "sin emojis"
    ni al bloque de piezas por red. Las features de copy los activan.
    """
    partes: list[str] = [cuerpo_prompt.strip()]
    if adjuntos:
        bloques = [f"## {d.titulo}\n\n{d.cuerpo.strip()}" for d in adjuntos]
        partes.append(
            "---\nLÍNEA EDITORIAL (material de referencia, no lo copies literal):\n\n"
            + "\n\n".join(bloques)
        )
    if bloque_contexto and bloque_contexto.strip():
        partes.append("---\nCONTEXTO:\n\n" + bloque_contexto.strip())
    texto = "\n\n".join(partes)
    if sin_emojis:
        texto = f"{texto}\n\n{INSTRUCCION_SIN_EMOJIS}"
    if redes_ids:
        texto = f"{texto}\n\n{instruccion_redes(redes_ids)}"
    return texto


def _autor_campos(autor: dict[str, str] | None) -> dict[str, str]:
    autor = autor or {}
    return {"autor_id": autor.get("id", "") or "", "autor_nombre": autor.get("usuario", "") or ""}


def lanzar(
    *,
    tipo: str,
    titulo: str,
    marca: str,
    prompt: str,
    procesar: generaciones.Procesar,
    procesar_spec: dict[str, Any],
    dir_temporal: Path | None = None,
    autor: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Crea el registro de generación, ENCOLA el trabajo y devuelve el registro (para sondeo).

    El back solo ENCOLA (responde al instante); un WORKER clava el job y corre `claude -p`
    con cwd NEUTRO. Maneja `ColaLlenaError` (la propaga -> 429 central) y limpia el temporal.
    """
    import shutil

    gen = generaciones.crear({
        "tipo": tipo,
        "marca": marca,
        "etiqueta": f"{titulo} · {nombre_marca(marca)}",
        **_autor_campos(autor),
    })
    spec = jobspec.construir(
        prompt=prompt,
        procesar=procesar_spec,
        cwd_kind=jobspec.CWD_GENERACION,
        dir_temporal=str(dir_temporal) if dir_temporal is not None else None,
    )
    try:
        generaciones.encolar_job_claude(
            gen["id"], prompt=prompt, cwd=cwd_generacion(), procesar=procesar,
            dir_temporal=dir_temporal, spec=spec,
        )
    except generaciones.ColaLlenaError:
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "motivo": generaciones.MOTIVO_COLA_LLENA,
            "error": "Hay demasiadas generaciones en curso; inténtalo en unos segundos.",
            "fecha_fin": generaciones.ahora_iso(),
        })
        raise
    except Exception:  # noqa: BLE001 -- nunca un traceback crudo; reflejamos el error en el registro
        if dir_temporal is not None:
            shutil.rmtree(dir_temporal, ignore_errors=True)
        generaciones.actualizar(gen["id"], {
            "estado": generaciones.ESTADO_ERROR, "error": "No se pudo iniciar la generación.",
            "fecha_fin": generaciones.ahora_iso(),
        })
    return generaciones.obtener(gen["id"]) or gen
