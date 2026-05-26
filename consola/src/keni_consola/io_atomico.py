"""Escritura atómica de texto a fichero — única implementación de la Consola.

El patrón «temporal en el mismo directorio + `os.replace`» estaba copiado en ~10
módulos de dominio (ficheros, agentes, sugerencias, secretos, skills_catalogo,
termometro, preferencias, generaciones). Esto lo unifica en una sola función
(hallazgo H7 / N2 de la re-auditoría).

Garantías:
  - El fichero destino nunca queda a medias: se escribe a un temporal en el MISMO
    directorio (mismo sistema de ficheros, así `os.replace` es atómico) y solo al
    final se renombra sobre el destino.
  - Si la escritura falla, el temporal se borra y se propaga el error; el destino
    queda intacto.
  - El directorio padre se crea si no existe.
  - `modo` opcional aplica `os.chmod` al temporal ANTES del replace (p.ej. `0o600`
    para secretos), así el fichero final nace ya con los permisos correctos.

NO sabe de YAML/JSON/TOML: recibe el TEXTO ya serializado. Las funciones
`_escribir_yaml`/`_escribir` de cada módulo siguen siendo dueñas de su formato y
delegan el commit a disco aquí.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def escribir_atomico(
    ruta: str | os.PathLike[str],
    texto: str,
    *,
    modo: int | None = None,
    prefijo: str = ".tmp-",
    sufijo: str | None = None,
) -> None:
    """Escribe `texto` en `ruta` de forma ATÓMICA (temporal + `os.replace`).

    Args:
        ruta: destino. Su directorio padre se crea si no existe.
        texto: contenido ya serializado (UTF-8).
        modo: si se da, `os.chmod(temporal, modo)` antes del replace (p.ej. 0o600).
        prefijo: prefijo del nombre del temporal (oculto, empieza por punto).
        sufijo: sufijo del temporal; por defecto la extensión del destino
            (`ruta.suffix`), para que herramientas que miran la extensión no se
            confundan con el temporal.
    """
    destino = Path(ruta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    if sufijo is None:
        sufijo = destino.suffix

    fd, tmp_nombre = tempfile.mkstemp(dir=str(destino.parent), prefix=prefijo, suffix=sufijo)
    tmp = Path(tmp_nombre)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(texto)
        if modo is not None:
            os.chmod(tmp, modo)
        os.replace(tmp, destino)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
