"""Persistencia — dominio contenido. Barrel del paquete (implementación de db.py).

Split de `db_contenido.py` en submódulos por sub-área (sin cambio de comportamiento ni de
superficie pública). Re-exporta TODO lo que consumían los clientes externos —públicos Y
privados— por sus DOS formas (`from .db_contenido import X` e `import …db_contenido; db_contenido.X`)
y lo que el barrel `db.py` re-exporta a su vez. Incluye los símbolos compartidos de `_db_comun`
que el módulo original re-exponía (`Any`, `datetime`, `redes`, `_conectar`, constantes…), para
preservar EXACTAMENTE el `dir()` previo.
"""
from __future__ import annotations

# Símbolos compartidos de `_db_comun` que el módulo original re-exponía en su namespace
# (estaban en su `dir()` por ser imports a nivel de módulo). Se re-exportan para paridad exacta.
from .._db_comun import (
    CLASE_CONTENIDO,
    ESTADOS_CONTENIDO,
    ESTADOS_CONTENIDO_PLATAFORMA,
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
    _CAMPOS_EDITABLES_CONTENIDO,
    _COLS_CONTENIDO,
    _SELECT_CONTENIDO,
    _entero_no_negativo,
    _fila_a_contenido,
    _fila_contenido_nueva,
    _insertar_contenido,
    actualizar_contenido,
    borrar_contenido,
    contar_contenido_origen_desde,
    crear_contenido,
    existe_publicado_similar,
    ids_contenido_con_copy,
    existe_publicado_similar_en_cache,
    listar_contenido,
    listar_contenido_origenes,
    listar_contenido_vencido,
    obtener_contenido,
    sanear_qa_en_curso_huerfanos,
    publicados_marca_cache,
    titulos_recientes_marca,
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
    _BOOLS_CONTENIDO_PLATAFORMA,
    _CAMPOS_EDITABLES_CONTENIDO_PLATAFORMA,
    _COLS_CONTENIDO_PLATAFORMA,
    _SELECT_CONTENIDO_PLATAFORMA,
    _fila_a_contenido_plataforma,
    _insertar_contenido_plataforma,
    actualizar_contenido_plataforma,
    borrar_contenido_plataforma,
    crear_contenido_plataforma,
    estado_pieza_por_contenido,
    listar_contenido_plataforma,
    obtener_contenido_plataforma,
)

__all__ = [
    # _db_comun (re-export para paridad de superficie)
    "Any",
    "CLASE_CONTENIDO",
    "ESTADOS_CONTENIDO",
    "ESTADOS_CONTENIDO_PLATAFORMA",
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
    "_COLS_CONTENIDO",
    "_SELECT_CONTENIDO",
    "_CAMPOS_EDITABLES_CONTENIDO",
    "_fila_a_contenido",
    "_entero_no_negativo",
    "crear_contenido",
    "listar_contenido",
    "listar_contenido_vencido",
    "titulos_recientes_marca",
    "contar_contenido_origen_desde",
    "existe_publicado_similar",
    "publicados_marca_cache",
    "existe_publicado_similar_en_cache",
    "obtener_contenido",
    "actualizar_contenido",
    "borrar_contenido",
    # contenido_plataforma (hijo)
    "_COLS_CONTENIDO_PLATAFORMA",
    "_SELECT_CONTENIDO_PLATAFORMA",
    "_BOOLS_CONTENIDO_PLATAFORMA",
    "_CAMPOS_EDITABLES_CONTENIDO_PLATAFORMA",
    "_fila_a_contenido_plataforma",
    "crear_contenido_plataforma",
    "estado_pieza_por_contenido",
    "listar_contenido_plataforma",
    "obtener_contenido_plataforma",
    "actualizar_contenido_plataforma",
    "borrar_contenido_plataforma",
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
# namespace para que la superficie pública (`dir()`/`from db_contenido import *`) sea idéntica a
# la del fichero original; el código de los submódulos sigue accesible por su ruta de import.
del _contenido, _etiquetas, _plataforma  # noqa: F821 -- nombres de submódulo ligados por el import
