"""Persistencia — dominio contenido. Barrel del paquete (implementación de db.py).

Split de `db_publicacion.py` en submódulos por sub-área (sin cambio de comportamiento ni de
superficie pública). Re-exporta TODO lo que consumían los clientes externos —públicos Y
privados— por sus DOS formas (`from .db_publicacion import X` e `import …db_publicacion; db_publicacion.X`)
y lo que el barrel `db.py` re-exporta a su vez. Incluye los símbolos compartidos de `_db_comun`
que el módulo original re-exponía (`Any`, `datetime`, `redes`, `_conectar`, constantes…), para
preservar EXACTAMENTE el `dir()` previo.
"""
from __future__ import annotations

# Símbolos compartidos de `_db_comun` que el módulo original re-exponía en su namespace
# (estaban en su `dir()` por ser imports a nivel de módulo). Se re-exportan para paridad exacta.
from .._comun import (
    CLASE_CONTENIDO,
    ESTADOS_PUBLICACION,
    ESTADOS_PIEZA,
    PRIORIDAD_CONTENIDO_DEFECTO,
    PRIORIDADES_EVENTO,
    TIPO_CONTENIDO_DEFECTO,
    TIPOS_CONTENIDO,
    Any,
    _conectar,
    datetime,
    redes,
    timedelta,
    uuid,
)
from ._contenido import (
    ConflictoVersion,
    _CAMPOS_EDITABLES_CONTENIDO,
    _COLS_PUBLICACION,
    _SELECT_PUBLICACION,
    _entero_no_negativo,
    _fila_a_publicacion,
    _fila_publicacion_nueva,
    _insertar_publicacion,
    actualizar_publicacion,
    reclamar_publicacion,
    borrar_publicacion,
    contar_publicacion_origen_desde,
    resumen_plan_por_categoria,
    crear_publicacion,
    existe_publicado_similar,
    ids_publicacion_con_copy,
    verificacion_fuente_por_publicacion,
    existe_publicado_similar_en_cache,
    listar_publicacion,
    listar_publicaciones_origenes,
    obtener_publicacion,
    reparar_verificacion_en_curso_sueltos,
    publicados_marca_cache,
    titulos_recientes_marca,
    id_titulos_recientes_marca,
)
from ._etiquetas import (
    _CAMPOS_EDITABLES_ETIQUETA,
    _COLS_ETIQUETA,
    _SELECT_ETIQUETA,
    _fila_a_etiqueta,
    actualizar_etiqueta,
    borrar_etiqueta,
    crear_etiqueta,
    existe_etiqueta_nombre,
    listar_etiquetas,
    obtener_etiqueta,
    obtener_etiqueta_por_nombre,
)
from ._plataforma import (
    _BOOLS_PIEZA,
    _CAMPOS_EDITABLES_PIEZA,
    _COLS_PIEZA,
    _SELECT_PIEZA,
    _fila_a_pieza,
    _insertar_pieza,
    actualizar_pieza_fila,
    borrar_pieza_fila,
    crear_pieza_fila,
    estado_pieza_por_publicacion,
    listar_piezas_fila,
    obtener_pieza_fila,
)

__all__ = [
    # concurrencia optimista (ADR 0012)
    "ConflictoVersion",
    # _db_comun (re-export para paridad de superficie)
    "Any",
    "CLASE_CONTENIDO",
    "ESTADOS_PUBLICACION",
    "ESTADOS_PIEZA",
    "PRIORIDADES_EVENTO",
    "PRIORIDAD_CONTENIDO_DEFECTO",
    "TIPOS_CONTENIDO",
    "TIPO_CONTENIDO_DEFECTO",
    "_conectar",
    "datetime",
    "redes",
    "timedelta",
    "uuid",
    # contenido (padre)
    "_COLS_PUBLICACION",
    "_SELECT_PUBLICACION",
    "_CAMPOS_EDITABLES_CONTENIDO",
    "_fila_a_publicacion",
    "_entero_no_negativo",
    "crear_publicacion",
    "listar_publicacion",
    "titulos_recientes_marca",
    "id_titulos_recientes_marca",
    "contar_publicacion_origen_desde",
    "resumen_plan_por_categoria",
    "verificacion_fuente_por_publicacion",
    "existe_publicado_similar",
    "publicados_marca_cache",
    "existe_publicado_similar_en_cache",
    "obtener_publicacion",
    "actualizar_publicacion",
    "reclamar_publicacion",
    "borrar_publicacion",
    # pieza (hijo)
    "_COLS_PIEZA",
    "_SELECT_PIEZA",
    "_BOOLS_PIEZA",
    "_CAMPOS_EDITABLES_PIEZA",
    "_fila_a_pieza",
    "crear_pieza_fila",
    "estado_pieza_por_publicacion",
    "listar_piezas_fila",
    "obtener_pieza_fila",
    "actualizar_pieza_fila",
    "borrar_pieza_fila",
    # etiquetas
    "_COLS_ETIQUETA",
    "_SELECT_ETIQUETA",
    "_CAMPOS_EDITABLES_ETIQUETA",
    "_fila_a_etiqueta",
    "crear_etiqueta",
    "listar_etiquetas",
    "obtener_etiqueta",
    "existe_etiqueta_nombre",
    "obtener_etiqueta_por_nombre",
    "actualizar_etiqueta",
    "borrar_etiqueta",
]

# Paridad EXACTA de `dir()` con el módulo plano previo: los submódulos quedan ligados como
# atributos del paquete tras importarlos (comportamiento estándar de paquetes). Se desligan del
# namespace para que la superficie pública (`dir()`/`from db_publicacion import *`) sea idéntica a
# la del fichero original; el código de los submódulos sigue accesible por su ruta de import.
del _contenido, _etiquetas, _plataforma  # noqa: F821 -- nombres de submódulo ligados por el import
