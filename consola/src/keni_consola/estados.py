"""Constantes neutras de DOMINIO de la Consola Keni (allowlists de estados/metricas).

Modulo SIN dependencias internas: vive aparte de cualquier backend de persistencia
para que tanto el almacen de CONTENIDO (`ficheros.py`, YAML) como el OPERACIONAL
(`db.py`, SQLite) y la fachada (`repos.py`) puedan importarlo sin acoplarse entre si.

Antes estas constantes vivian en `db.py`; al separar el contenido (YAML) del dato
operacional (SQLite) se movieron aqui para que `ficheros.py` no dependa de `db.py`
por una simple allowlist (E5/H2, riesgo R5 del plan de persistencia).
"""

from __future__ import annotations

# Allowlists del tablero de contenido: la fuente CANONICA vive en keni-shared (la
# comparten esta Consola y el MCP de tablero); este modulo las re-exporta con sus
# nombres de siempre para que ningun import existente cambie.
from keni_shared import estados as _estados_compartidos

# Estados validos de una tarea/pendiente (operacional; vive en SQLite). El orden
# es el ciclo de vida: pendiente -> en curso -> hecha (#145, F5). "en_curso" se
# anadio al pasar el tablero a multiusuario; las tareas legadas solo tenian
# "pendiente"/"hecha" y siguen siendo validas (ambos estados se conservan).
ESTADOS_TAREA: tuple[str, ...] = ("pendiente", "en_curso", "hecha")

# Estados validos de una publicacion (flujo editorial; YAML). El flujo de aprobacion
# de equipo (#9, Fase 3) intercala `en_revision` entre el borrador y el aprobado:
#
#   borrador -> en_revision -> aprobado -> programado -> publicado
#                   |
#                   +-> (rechazo) -> borrador
#
# `en_revision` se anadio DESPUES del set original; un YAML legado nunca lo trae, asi
# que la lectura sigue siendo retrocompatible (los 4 estados originales validan igual).
# Estados del flujo de publicación (fuente única; usar estas constantes, no literales).
# `en_revision` se anadio DESPUES del set original (#9): el autor envia su pieza a revision;
# un revisor/admin la aprueba o la devuelve a borrador. Un YAML legado nunca lo trae, asi
# que la lectura sigue siendo retrocompatible (los 4 estados originales validan igual).
ESTADO_BORRADOR = "borrador"
ESTADO_EN_REVISION = "en_revision"
ESTADO_APROBADO = "aprobado"
ESTADO_PROGRAMADO = "programado"
ESTADO_PUBLICADO = "publicado"

ESTADOS_PUBLICACION: tuple[str, ...] = (
    ESTADO_BORRADOR,
    ESTADO_EN_REVISION,
    ESTADO_APROBADO,
    ESTADO_PROGRAMADO,
    ESTADO_PUBLICADO,
)

# Estados del seguimiento comercial: activa (se captura), pausada (se detuvo la
# pauta), cerrada (KPI entregado / reporte hecho). Operacional; vive en SQLite.
ESTADOS_COMERCIAL: tuple[str, ...] = ("activa", "pausada", "cerrada")

# Solo las activas entran en la captura programada.
ESTADO_COMERCIAL_ACTIVA = "activa"

# Metricas que un objetivo/umbral comercial puede seguir (misma forma que el resto
# del producto). `visualizaciones` e `interacciones` vienen del post real de Metricool;
# `alcance` solo en modo muestra (Metricool no lo da por pieza).
METRICAS_COMERCIAL: tuple[str, ...] = ("interacciones", "visualizaciones", "alcance")

# Roles de usuario (auth multiusuario, #130). `admin` gestiona usuarios y todo lo
# demas; `editor` usa la consola pero NO toca /api/usuarios.
ROLES_USUARIO: tuple[str, ...] = ("admin", "editor")
ROL_ADMIN = "admin"
ROL_EDITOR = "editor"

# Cargos del equipo (transcripciones AMX): describen la FUNCION en el equipo, no los
# permisos. Ortogonal a `ROLES_USUARIO` (que sigue siendo admin/editor). `cobertura` es
# el flag separado que dice si esa persona entra en la rota de turnos: hay cargos que
# por funcion no cubren (estrategia, fotografia, gerencia) y community managers que si.
#
# Ampliacion (organigrama dictado por Bernardo, AMX): se anaden cargos especificos por
# vertical/funcion que la version "plana" no capturaba (un `coordinador` real puede ser
# de redes, YouTube u operativo; Maira es `gerente_podcast`; Daiana/Jonathan son
# `creativo_vertical` de Fundacion/Nacion Gamer; Yustine es editorial de YouTube; Ale
# combina fotografia con QA). Los valores VIEJOS se conservan tal cual por retrocompat
# de usuarios legados creados antes de la ampliacion (no se les fuerza la migracion).
CARGOS_USUARIO: tuple[str, ...] = (
    # Catalogo original (retrocompat):
    "director",
    "gerente",
    "coordinador",
    "content_manager",
    "community_manager",
    "redactor",
    "guionista",
    "editorial",
    "estrategia",
    "fotografia",
    # Ampliacion (organigrama real de AMX):
    "coordinador_redes",        # jefe de redes de una marca (Diana UnoTV, Elias ClaroSports)
    "coordinador_youtube",      # coordinacion del canal de YouTube (Lalo YT)
    "gerente_podcast",          # gerencia del podcast Piso 15 (Maira)
    "creativo_vertical",        # creativo de una vertical (Jonathan NG, Daiana Fundacion)
    "editorial_youtube",        # editorial enfocada a YouTube (Yustine)
    "coordinador_invitados",    # coordinacion de invitados (uso futuro)
    "coordinador_operativo",    # coordinacion operativa (Mariana)
    "fotografia_qa",            # fotografia + QA editorial (Ale)
    "editor_video",             # edicion de video (uso futuro)
    "disenador",                # diseno grafico (uso futuro)
)

# Estados de un turno de la rota (F4 · #144): `propuesto` es lo que Keni genera;
# `aprobado` es lo que Elias publica al equipo (nada se publica antes de aprobar).
# Operacional; vive en SQLite. Lo COMPARTEN los turnos de cobertura de eventos
# (`rota_turnos`) y los turnos de trabajo del horario del equipo (`rota_turnos_trabajo`):
# misma frontera de aprobacion (Keni propone -> Elias aprueba y publica).
ESTADOS_ROTA: tuple[str, ...] = ("propuesto", "aprobado")
ESTADO_ROTA_PROPUESTO = "propuesto"
ESTADO_ROTA_APROBADO = "aprobado"

# Estados del flujo de SWAPS de turno (intercambios entre companeros, #175). Cuando un
# CM (A) pide a otro (B) cubrirle un turno, la solicitud nace `propuesto`; B `acepta` o
# `rechaza`; si acepta, Elias (admin) `aprueba` (que aplica el swap en
# `rota_turnos_trabajo` y la solicitud queda `aplicado`) o `rechazado_admin`. El
# solicitante puede `cancelar` mientras la solicitud no sea terminal.
#
# Terminales: aplicado, rechazado, rechazado_admin, cancelado.
ESTADOS_SWAP: tuple[str, ...] = (
    "propuesto",
    "aceptado",
    "rechazado",
    "aprobado",
    "aplicado",
    "rechazado_admin",
    "cancelado",
)
ESTADO_SWAP_PROPUESTO = "propuesto"
ESTADO_SWAP_ACEPTADO = "aceptado"
ESTADO_SWAP_RECHAZADO = "rechazado"
ESTADO_SWAP_APROBADO = "aprobado"
ESTADO_SWAP_APLICADO = "aplicado"
ESTADO_SWAP_RECHAZADO_ADMIN = "rechazado_admin"
ESTADO_SWAP_CANCELADO = "cancelado"
ESTADOS_SWAP_TERMINALES: tuple[str, ...] = (
    ESTADO_SWAP_APLICADO,
    ESTADO_SWAP_RECHAZADO,
    ESTADO_SWAP_RECHAZADO_ADMIN,
    ESTADO_SWAP_CANCELADO,
)

# Franjas LEGADAS de un turno de TRABAJO (pre-#XYZ, ola "franjas por semana"). Se conservan
# como nombres VIEJOS para que la MIGRACION (`_migrar_modelo_franjas` en `db.py`) sepa
# reconocer las filas pre-migracion con `franja='matutino'/'vespertino'/'descanso'`. Tras
# la migracion, los turnos referencian `rota_franjas.id` (franjas por semana, configurables,
# con solapes permitidos) y NO usan estos literales para nada operativo.
#
# Mientras quedan tests legados que pasan estos strings al crear un turno, los aceptamos por
# retrocompat y el repos los traduce a un `franja_id` real sembrando la semana por defecto
# (Mañana 08:00-16:00, Tarde 16:00-24:00). Codigo nuevo debe pasar `franja_id` directamente.
FRANJAS_TURNO_LEGACY: tuple[str, ...] = ("matutino", "vespertino", "descanso")
FRANJA_MATUTINO_LEGACY = "matutino"
FRANJA_VESPERTINO_LEGACY = "vespertino"
FRANJA_DESCANSO_LEGACY = "descanso"

# Nombres por defecto que sembramos para una semana nueva (las 2 franjas iniciales). Estos
# valores se usan al RENDERIZAR la primera vista de una semana sin franjas: la API siembra
# "Mañana" y "Tarde" con los rangos de `rota_config_franjas` (plantilla global) si existe,
# o con los DEFAULTs editoriales del dominio (`rota.py`).
NOMBRE_FRANJA_MANANA_DEFAULT = "Mañana"
NOMBRE_FRANJA_TARDE_DEFAULT = "Tarde"

# Alias retrocompat para call sites que aun no se han adaptado (se mantienen como
# tuplas/strings para no romper imports). Codigo NUEVO no deberia usarlos.
FRANJAS_TURNO: tuple[str, ...] = FRANJAS_TURNO_LEGACY
FRANJA_MATUTINO = FRANJA_MATUTINO_LEGACY
FRANJA_VESPERTINO = FRANJA_VESPERTINO_LEGACY
FRANJA_DESCANSO = FRANJA_DESCANSO_LEGACY
FRANJAS_TRABAJO: tuple[str, ...] = (FRANJA_MATUTINO_LEGACY, FRANJA_VESPERTINO_LEGACY)

# Tipos de una AUSENCIA del horario (F4 · #144): el proponedor los respeta por igual
# (cualquier ausencia que cubra una fecha excluye al miembro ese dia). `vacaciones` es el
# caso de Elias ("las vacaciones, esto por el acomodo"); `descanso` es un dia libre
# planificado; `baja` una ausencia medica/forzosa; `otro` el cajon de sastre. Operacional;
# vive en SQLite (`rota_ausencias.tipo`).
TIPOS_AUSENCIA: tuple[str, ...] = ("vacaciones", "descanso", "baja", "otro")

# Tipo de COBERTURA de un evento del calendario (F4 · #144, ola B). Elias distingue tres
# casos reales: `transmision` (sale con senal/transmision), `imagenes` ("algunos no los
# vamos a transmitir, pero si los cubrimos con imagenes y fotografias") y `no_cubrir` (se
# trackea en el calendario pero NO se asigna cobertura). DEFAULT `transmision`: un evento
# legado (sin tipo) se trata como transmision, asi que el proponedor lo sigue cubriendo.
# Operacional; vive en SQLite (`rota_eventos.tipo_cobertura`).
TIPOS_COBERTURA: tuple[str, ...] = ("transmision", "imagenes", "no_cubrir")
TIPO_COBERTURA_TRANSMISION = "transmision"
TIPO_COBERTURA_IMAGENES = "imagenes"
TIPO_COBERTURA_NO_CUBRIR = "no_cubrir"

# Solo estos tipos GENERAN un turno de cobertura al proponer la rota: `no_cubrir` queda
# fuera (se trackea pero no se asigna a nadie).
TIPOS_COBERTURA_ASIGNABLES: tuple[str, ...] = (
    TIPO_COBERTURA_TRANSMISION,
    TIPO_COBERTURA_IMAGENES,
)

# Estados validos de una PIEZA (un post individual asociado a un evento o programa
# evergreen; #150 PARRILLA 2026). Una transmision como "LIV GOLF Andalucia R1" genera
# varias piezas (pre-evento FB/IG/X, reel IG/TK, historia dia, post-evento); el flujo de
# produccion va `pendiente` -> `en_curso` -> `listo` -> `publicado`. Operacional;
# vive en Postgres (`rota_piezas.estado`).
ESTADOS_PIEZA: tuple[str, ...] = ("pendiente", "en_curso", "listo", "publicado")

# Prioridad de un evento del calendario (F4 · #144, ola B): pista visual para que el
# equipo decida que cubre primero. DEFAULT `media`. Operacional (`rota_eventos.prioridad`).
PRIORIDADES_EVENTO: tuple[str, ...] = ("alta", "media", "baja")
PRIORIDAD_EVENTO_DEFECTO = "media"

# --------------------------------------------------------------------------- #
# Tablero de CONTENIDO unificado (herramienta de community manager)            #
# --------------------------------------------------------------------------- #
# Unifica el tablero de tareas, las piezas de la rota y las publicaciones en un
# unico modelo padre+hijos (`contenido` + `contenido_plataforma`). Operacional;
# vive en Postgres. Ver `db.py` y `api/contenido.py`.

# `clase` de un item del tablero: contenido publicable (con filas por plataforma) o
# una tarea libre del equipo (relevo/recado, sin plataformas). Tupla CANONICA en
# keni-shared (`keni_shared.estados`): la comparte el MCP de tablero; aqui se
# RE-EXPORTA para no romper a los consumidores existentes de este modulo.
CLASES_CONTENIDO: tuple[str, ...] = _estados_compartidos.CLASES_CONTENIDO
CLASE_CONTENIDO = "contenido"
CLASE_TAREA = "tarea"

# ROLES de cobertura de un evento (Ola 2: «cobertura por roles tipados»). Cada cubridor cubre
# UN rol del evento; el reparto find-or-create es por (evento, persona, ROL), así una persona
# puede llevar VARIOS roles y dos personas roles distintos SIN solaparse. Los roles REUSAN el
# campo `formato` del contenido (NO hay migración): 'foto'/'video' ya son formatos del catálogo
# de publicación; 'texto'/'live' son texto libre que la columna admite (es `TEXT`, sin CHECK).
# Viven SOLO en tareas de cobertura (clase='tarea'), que NUNCA tocan el mapeo formato->redes del
# pipeline de publicación (`redes.redes_de_formato`, que no conoce 'texto'/'live').
ROLES_COBERTURA: tuple[str, ...] = ("foto", "video", "texto", "live")

# `flujo` editorial de un contenido: lo importante del dia, evergreen (always-on) o
# cobertura de un evento previsto. "" para tareas libres (clase=tarea). Canonica en
# keni-shared (re-exportada aqui, ver CLASES_CONTENIDO).
FLUJOS_CONTENIDO: tuple[str, ...] = _estados_compartidos.FLUJOS_CONTENIDO
FLUJO_IMPORTANTE = "importante"
FLUJO_EVERGREEN = "evergreen"
FLUJO_EVENTO = "evento"

# Prioridad de un contenido/tarea del tablero (misma escala que un evento).
PRIORIDADES_CONTENIDO: tuple[str, ...] = PRIORIDADES_EVENTO
PRIORIDAD_CONTENIDO_DEFECTO = PRIORIDAD_EVENTO_DEFECTO

# Taller EVERGREEN / brainstorming: estados de una IDEA de contenido evergreen. La IA (o una
# persona) PROPONE; el equipo APRUEBA o DESCARTA; solo para las aprobadas se genera la pieza
# (`flujo='evergreen'` en el tablero). Operacional; vive en Postgres (`evergreen_ideas.estado`).
ESTADOS_EVERGREEN_IDEA: tuple[str, ...] = ("propuesta", "aprobada", "generada", "descartada")
ESTADO_EVERGREEN_PROPUESTA = "propuesta"
ESTADO_EVERGREEN_APROBADA = "aprobada"
# La idea YA produjo su pieza (terminal feliz): sale del flujo activo al cajón histórico del
# taller — sin más acciones; el contenido vive su propio ciclo en el tablero.
ESTADO_EVERGREEN_GENERADA = "generada"
ESTADO_EVERGREEN_DESCARTADA = "descartada"

# Origen de una idea evergreen, todas en el MISMO banco (Contenidos):
#   - `ia`:      propuesta por la IA en el taller.
#   - `manual`:  tecleada a mano (alta rápida en el banco).
#   - `idea`:    aportación de "Idea del equipo" (antes en Fuentes-Internas).
#   - `interna`: aportación de "Interno AMX" (briefs/material de programa; antes en Fuentes).
ORIGENES_EVERGREEN_IDEA: tuple[str, ...] = ("ia", "manual", "idea", "interna")
# Orígenes que puede declarar una aportación MANUAL al crear (la IA usa su propio camino).
ORIGENES_EVERGREEN_IDEA_MANUAL: tuple[str, ...] = ("manual", "idea", "interna")

# Tipo de contenido: de DÓNDE sale la imagen de la pieza.
#   - `ia`:      se genera con IA (texto -> imagen).
#   - `galeria`: se sube/elige de la galería de medios.
#   - `fuente`:  se usa la imagen de la FUENTE original (nota/clip), vía su URL.
# Es una pista para la UI (qué afordancia de imagen resaltar), no una restricción dura.
TIPOS_CONTENIDO: tuple[str, ...] = ("ia", "galeria", "fuente")
TIPO_CONTENIDO_DEFECTO = "ia"

# `origen` de un item del tablero: de QUÉ fuente nació. Es texto libre en la DB (no hay
# enum duro en `repos.crear_contenido`), pero las FUENTES que la auto-generación de copy
# considera "tema redactable" se enumeran aquí, en el módulo neutro, para que tanto el
# daemon (`autogen_copy.ORIGENES_TOPIC`) como los flujos transversales referencien UN
# único valor en vez de literales sueltos.
#   - `import-calendario` · `radar-auto` · `radar` · `rss`: fuentes EXTERNAS (lo histórico).
#   - `equipo`: ALTA CREATIVA del equipo (Fase 1 / Flujo A). El equipo "postea" material
#     original (foto/nota/idea) con marca; se AUTO-GENERA SIEMPRE (decisión de dirección
#     2026-06-01: no opt-in). Es DISTINTO del alta tecleada legada (`origen=""`), que sigue
#     EXCLUIDA de la auto-generación (la genera quien la crea, si quiere). El endpoint/UI que
#     da de alta con este origen lo añade el Flujo A; aquí solo se fija el valor y la regla.
ORIGEN_EQUIPO = "equipo"

# Tema creado al USAR una historia del panel de noticias (`api/noticias.usar_historia`):
# curación HUMANA explícita (el equipo empujó esa historia, a menudo una breaking).
ORIGEN_HISTORIA = "historia"

# Tema creado por el ALTA DIRECTA de un post desde el feed (`api/contenido.post_directo`):
# el equipo teclea el COPY FINAL de la publicación (no material para redactar). NO está en
# `ORIGENES_AUTOGEN` a propósito: no hay nada que redactar (las piezas nacen con copy);
# el resto del flujo (arte por red, revisión, programación) las trata como a cualquier
# borrador depositado por el motor de copy.
ORIGEN_POST_DIRECTO = "post-directo"

# Tema creado desde el cajón PRESIDENCIA (`api/presidencia`): nota que llega por WhatsApp
# desde presidencia (texto + 4-5 imágenes y algún video) y que el equipo vuelca tal cual.
# Genera AUTOMÁTICAMENTE una pieza `formato='carrusel'` en el feed (portada con placa +
# resto del media en crudo). Es una publicación IMPUESTA desde fuera del área (la clase de
# etiqueta `origen` la distingue como `peticion_externa`). NO está en `ORIGENES_AUTOGEN`:
# su copy se lanza directo al crear la nota (como evergreen), no via el daemon de selección.
ORIGEN_PRESIDENCIA = "presidencia"

# Tema creado desde el cajón CLIPS (`api/clips`): vídeo/foto que llega por WhatsApp a los
# grupos de Claro Sports (Envíos Mundial, Ramón Mundial, Videos AS Claro, ClaroSports PS…) y
# que el equipo vuelca tal cual. Genera AUTOMÁTICAMENTE una pieza en el feed: `formato='video'`
# si es un clip de vídeo, `formato='carrusel'` si son fotos (portada con placa + slides). Como
# Presidencia, su copy se lanza DIRECTO al crear (no via el daemon de selección); por eso NO
# está en `ORIGENES_AUTOGEN`.
ORIGEN_CLIPS = "clips"

# Orígenes de FUENTE que la auto-generación de copy trata como "tema redactable" (un
# borrador se encola solo). Incluye las fuentes externas históricas + el alta creativa del
# equipo (`equipo`) + las historias curadas desde el panel (`historia`: sin esto, si su
# lanzamiento síncrono fallaba —cola llena, generación pausada, presupuesto— el tema moría
# sin copy y SIN REINTENTO, invisible para ambos motores; medido en el piloto con una
# breaking). El alta tecleada legada (`origen=""`) NO está aquí: queda fuera de la
# auto-generación a propósito.
ORIGENES_AUTOGEN: tuple[str, ...] = (
    "import-calendario",
    "radar-auto",
    "radar",
    "rss",
    ORIGEN_EQUIPO,
    ORIGEN_HISTORIA,
)

# Eje (clase) de una etiqueta editorial del tablero (ola "organizacion"). Una etiqueta
# clasifica transversalmente una pieza: una CAMPAÑA ("Mundial 2026"), una VERTICAL/sección
# editorial ("futbol", "espectaculos") o un TIPO de formato ("reel", "carrusel", "nota").
CLASES_ETIQUETA: tuple[str, ...] = ("campania", "vertical", "tipo", "origen")
CLASE_ETIQUETA_DEFECTO = "campania"

# Las dos clases que el auto-etiquetado aplica a cada pieza en la ingesta:
#   - `vertical` = la LÍNEA de contenido (futbol, beisbol, ultima hora...). Cada
#     línea lleva `keywords` (CSV) para clasificar sin coste de IA.
#   - `origen`   = de dónde nace la pieza: editorial propio (`interno`) o una
#     publicación impuesta desde fuera del área —gobierno, comercial, marketing—
#     (`peticion_externa`). Separa lo editorial de lo impuesto (clave para medir).
ORIGENES_PIEZA: tuple[str, ...] = ("interno", "peticion_externa")
ORIGEN_PIEZA_DEFECTO = "interno"

# Estado de un contenido a nivel PADRE (resumen editable / estado directo de una tarea
# libre). Cubre el ciclo de una tarea (pendiente/en_curso/hecha) y sirve de resumen.
# Canonica en keni-shared (re-exportada aqui, ver CLASES_CONTENIDO).
ESTADOS_CONTENIDO: tuple[str, ...] = _estados_compartidos.ESTADOS_CONTENIDO

# Estado de UNA fila por plataforma (`contenido_plataforma.estado`). Ciclo unificado que
# fusiona el de pieza (pendiente/en_curso/listo/publicado) y el editorial de publicacion
# (borrador/en_revision/aprobado/programado/publicado):
#
#   pendiente -> en_curso -> en_revision -> aprobado -> programado -> publicado
#
# Mapeos de migracion: `borrador` -> `pendiente`; `listo` (pieza) -> `aprobado`.
# Canonica en keni-shared (re-exportada aqui, ver CLASES_CONTENIDO).
ESTADOS_CONTENIDO_PLATAFORMA: tuple[str, ...] = _estados_compartidos.ESTADOS_CONTENIDO_PLATAFORMA

# Items del checklist "falta X" que se siguen por plataforma. Cada uno es un booleano en
# `contenido_plataforma` (`falta_copy`, `falta_imagen`, `falta_revision`, `falta_publicar`).
CHECKLIST_CONTENIDO: tuple[str, ...] = (
    "falta_copy",
    "falta_imagen",
    "falta_revision",
    "falta_publicar",
)

# --------------------------------------------------------------------------- #
# Ola COLABORACION: comentarios internos + versiones de copy + aprobacion      #
# multinivel sobre el tablero de contenido (inspirado en Planable).            #
# --------------------------------------------------------------------------- #

# Decision de UN nivel de la cadena de aprobacion multinivel de una pieza
# (`contenido_aprobaciones.decision`). `pendiente` = aun sin decidir; `aprobado` /
# `rechazado` = decision tomada (con decisor + sello de tiempo). Una pieza esta
# TOTALMENTE aprobada cuando todos sus niveles estan en `aprobado`; un `rechazado`
# en cualquier nivel para la cadena.
DECISIONES_APROBACION: tuple[str, ...] = ("pendiente", "aprobado", "rechazado")
DECISION_PENDIENTE = "pendiente"
DECISION_APROBADO = "aprobado"
DECISION_RECHAZADO = "rechazado"

# Veredictos validos de la QA DE LA FUENTE persistida en `contenido.qa_veredicto` (criba
# pre-copy). Allowlist CANONICA para el CHECK de esquema (ADR 0012). "" = sin cribar / a
# re-criba. Los valores NO viven en este modulo dependency-free (son del pipeline/dominio);
# se enumeran aqui como literales, con su origen, para no acoplar `estados` al pipeline:
#   - "en_curso":      SENTINEL en vuelo            (`pipeline_contenido._comun.QA_EN_CURSO`)
#   - "saltada":       QA desactivada para la marca (`pipeline_contenido._comun.QA_SALTADA`)
#   - "caducada":      tema que supero el TTL       (`pipeline_contenido._comun.QA_CADUCADA`)
#   - "no_verificado": apta para seguir (⚠️)        (`dominio.qa_editorial.VERDICTO_NO_VERIFICADO`)
#   - "problema":      algo de peso en contra (❗)   (`dominio.qa_editorial.VERDICTO_PROBLEMA`)
# Si se anade un veredicto nuevo en el pipeline, anadirlo AQUI (el CHECK lo rechazaria si no).
VEREDICTOS_QA_CONTENIDO: tuple[str, ...] = (
    "",
    "en_curso",
    "saltada",
    "caducada",
    "no_verificado",
    "problema",
)

# Cadena de aprobacion POR DEFECTO al pedir revision de una pieza (orden = nivel
# 1-based). Refleja el organigrama de redes de AMX: redaccion -> coordinacion ->
# direccion. Es solo la plantilla inicial; quien pide la revision puede mandar su
# propia lista de etiquetas (la cadena vive en datos, no en codigo).
CADENA_APROBACION_DEFECTO: tuple[str, ...] = (
    "Edición",
    "Coordinación",
    "Dirección",
)

# Cadena de aprobacion por defecto al MANDAR A REVISION una pieza desde el feed/tablero
# (el flujo "dale el OK"): DOS niveles humanos = los DOS OK que la pieza necesita para
# quedar lista, uno de "Edición" y otro de "Coordinación". Cada nivel aprobado es un "like"
# del equipo; con los dos OK (de personas distintas, nunca el autor) la pieza pasa SOLA a
# `aprobado`. Cadena vacia = sin
# aprobacion. (Historicamente era un unico nivel "Revisión"; los dos OK lo sustituyen para
# que el gate "minimo de aprobaciones" = 2 sea alcanzable y refleje "cuatro ojos" reales.)
CADENA_APROBACION_SIMPLE: tuple[str, ...] = ("Edición", "Coordinación")
