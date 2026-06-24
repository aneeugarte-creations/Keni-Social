import type { MarcaDisponible, Pieza } from "../types.gen";
import type { Veredicto } from "./comun";

/**
 * Marca del selector con su `tipo` editorial: 'noticias' (pasa por investigación) o 'propio'
 * (contenido propio, sin panel de Noticias). Lo entrega `/api/piezas/opciones`; las de tipo
 * 'propio' ocultan el panel de Noticias. `tipo` es opcional por compatibilidad.
 */
export interface MarcaOpcion extends MarcaDisponible {
  tipo?: "noticias" | "propio";
  /** Nombre del panel de investigación de esta marca (p.ej. "Curiosidades"); "Noticias" por defecto. */
  etiqueta_investigacion?: string;
}

/** Resultado de programar una pieza en Metricool (preview dry-run o publicación real). */
export interface ResultadoProgramarMetricool {
  ok: boolean;
  /** true = solo se previsualizó (no se publicó); false = se publicó de verdad. */
  dry_run: boolean;
  /** Presente cuando ok=false: por qué no se pudo (sin credenciales, sin contenido…). */
  motivo?: string;
  /** Redes destino (nomenclatura Metricool: facebook/instagram/twitter/tiktok/youtube). */
  redes?: string[];
  /** Cuerpo exacto que se enviaría/envió al scheduler (preview). */
  cuerpo?: Record<string, unknown>;
  /** Id del post en Metricool (solo en publicación real). */
  id_post?: string;
  /** Estado por red devuelto por Metricool (solo en publicación real). */
  estados?: Record<string, string>;
}

/** Respuesta de POST /api/piezas/{id}/metricool. */
export interface RespuestaProgramarMetricool {
  resultado: ResultadoProgramarMetricool;
  /** Pieza tras el intento (actualizada a `publicado` si fue real); null si desapareció. */
  pieza: Pieza | null;
}

// --- Piezas ---

/** Estados del ciclo de vida de una publicación, en orden de avance.
 *
 * Se DERIVA del tipo generado `Pieza["estado"]` para no driftar del backend
 * (el flujo de aprobación de equipo, #9, añadió `en_revision`): si el backend cambia
 * el set de estados, este alias lo sigue solo. */
export type EstadoPieza = Pieza["estado"];

/** Una red social del catálogo (id canónico + límite de caracteres). */
export interface RedPieza {
  id: string;
  nombre: string;
  /** Límite de caracteres; `null` si la red no tiene límite. */
  limite: number | null;
}

/** Una opción de estado para los filtros. */
export interface EstadoOpcion {
  id: string;
  nombre: string;
}

/** Una línea editorial = etiqueta de clase `vertical` (la LÍNEA de contenido de una marca). */
export interface LineaEditorialOpcion {
  id: string;
  nombre: string;
  /** Marca dueña; "" = línea global (visible en todas las marcas). */
  marca: string;
}

/** Una entrada de la TAXONOMÍA del plan (Última hora · líneas · Evergreen): su `id` y su `nombre`
 *  legible (resuelto en el backend). El `id` es lo que viaja como `categoria` al crear/filtrar; el
 *  `nombre` es lo que se muestra. `franja` indica si tiene horario configurado. */
export interface CategoriaPlanOpcion {
  id: string;
  nombre: string;
  /** ¿Tiene FRANJA (horario)? «Crear post» solo ofrece las que sí (para que la pieza se
   *  programe); los FILTROS muestran toda la taxonomía. Ausente = trátala como sin franja. */
  franja?: boolean;
}

export interface OpcionesPiezas {
  redes: RedPieza[];
  estados: EstadoOpcion[];
  marcas: MarcaOpcion[];
  /** Catálogo PLANO de verticales (id→nombre) SOLO para resolver el nombre de `pieza.categoria`
   *  en el editor. NO es un eje de filtro: el filtro de líneas/categorías es `categorias`. */
  lineas: LineaEditorialOpcion[];
  /** TAXONOMÍA del plan POR marca (Última hora · líneas · Evergreen), nombre resuelto en el
   *  backend. ÚNICA fuente de "líneas/categorías" para el usuario: filtros (Feed/Lista) y alta
   *  «Crear post» (que se acota a las que tienen `franja`). */
  categorias: Record<string, CategoriaPlanOpcion[]>;
  /**
   * Gate maestro `KENI_PUBLICAR_REAL`. Si es `false`, las piezas programadas NO salen
   * solas (el programador opera en dry-run): el SPA avisa cuando hay programadas en cola.
   */
  publicar_real: boolean;
}

/** Cuerpo para crear una publicación. */
export interface CuerpoCrearPieza {
  titulo: string;
  marca: string;
  red: string;
  contenido: string;
  estado?: EstadoPieza;
  fecha_programada?: string | null;
  revision?: Veredicto;
  origen?: string | null;
  /** Nombre del archivo de imagen adjunto (vacío para ninguna). */
  imagen?: string;
}

export interface CuerpoCrearPiezasLote {
  piezas: CuerpoCrearPieza[];
}

/** Cuerpo parcial para actualizar una publicación. */
export interface CuerpoActualizarPieza {
  titulo?: string;
  contenido?: string;
  /** Texto que va DENTRO de la imagen (copy-in), distinto del contenido. */
  copy_in?: string;
  estado?: EstadoPieza;
  fecha_programada?: string | null;
  /** Marca/desmarca la publicación como evergreen. */
  evergreen?: boolean;
  /** Nombre del archivo de imagen adjunto (`""` para quitarla). */
  imagen?: string;
  /** Media id de la FOTO CRUDA de fondo (separada de la placa compuesta `imagen`). */
  foto?: string;
  /** Origen PROPIO declarado al REEMPLAZAR la imagen (galeria/subida/ia): el back LIMPIA el metadato
   *  de licencia heredado. Solo lo envían las acciones de reemplazo; las composiciones lo OMITEN
   *  para conservar el crédito de la foto compuesta. */
  imagen_origen?: string;
  /** "Quitar plantilla": publicar solo la foto, sin la placa de marca encima. */
  placa_oculta?: boolean;
  /** Plantilla del estudio elegida ("" para volver a la placa de marca por defecto). */
  plantilla_diseno_id?: string;
  /** Reencuadre manual de la foto dentro del marco 4:5 (JSON `{"foco":[x,y],"zoom":z}`; "" = sin reencuadre). */
  foto_encuadre?: string;
  /** COLLAGE: JSON array `[{objeto,foco,zoom}, …]`, una foto por hueco. "" = sin collage. */
  fotos?: string;
  /** CARRUSEL: slides EXTRA en crudo, JSON `[{tipo:"imagen"|"video",objeto}, …]` en orden de
   *  publicación (la portada es la imagen compuesta de siempre). "" = sin slides. */
  carrusel?: string;
  /** ESPEJO entre redes (vive en la idea): editar el contenido de una pieza lo propaga a sus
   *  redes hermanas. ON por defecto; OFF = cada red se edita por separado. */
  espejo?: boolean;
}

// --- Franjas (colas de publicación) ---

/** Una franja horaria de la cola de publicación. */
export interface Franja {
  id: string;
  /** Marca asociada (`""` si aplica a todas). */
  marca: string;
  marca_nombre: string;
  /** Red asociada (`""` si aplica a todas). */
  red: string;
  red_nombre: string;
  /** Día de la semana: 0=lunes .. 6=domingo. */
  dia_semana: number;
  /** Hora en formato "HH:MM" (UTC: el backend almacena instantes en UTC). */
  hora: string;
  /** Línea del plan a la que sirve: id de etiqueta vertical ('' = franja genérica). */
  categoria: string;
  /** Nombre legible de esa línea (o "Última hora"/"Evergreen"); '' si es genérica. */
  etiqueta?: string;
}

export interface RespuestaFranjas {
  franjas: Franja[];
}

export interface RespuestaFranja {
  franja: Franja;
}

/** Cuerpo para crear una franja. */
export interface CuerpoCrearFranja {
  dia_semana: number;
  hora: string;
  marca?: string;
  red?: string;
  /** Línea del plan ('' = genérica): la pieza de esa línea usa estos horarios. */
  categoria?: string;
}

/** Respuesta del borrado batch (`POST /api/piezas/borrar-lote`). */
export interface RespuestaBorrarLotePiezas {
  /** Cuántas se borraron de verdad. */
  borradas: number;
  /** Ids que NO se pudieron borrar (ya no existían); el resto del lote no se aborta. */
  fallos: string[];
}

export interface FiltrosPiezas {
  marca?: string;
  red?: string;
  estado?: string;
  /** Origen del contenido padre (el clon «Portal» del feed pide `origen='portal'`). */
  origen?: string;
  /** EXCLUSIÓN por origen (inverso de `origen`): el feed normal pide `excluir_origen='portal'`
   *  para mantenerse independiente del canal Portal. */
  excluir_origen?: string;
  /** LIMPIEZA del feed (filtros sobre el contenido padre): categoría del plan
   *  (breaking|mx|evergreen|internacional…). */
  categoria?: string;
  /** Tipo de contenido: ia | galeria | fuente. */
  tipo?: string;
  /** Nombre del medio de origen (fuente_nombre). */
  fuente?: string;
  /** Fase de producción: incompleto | producido | programado | publicado. */
  fase?: string;
  /** Antigüedad MÍNIMA en horas (presets >24h=24, >48h=48, >1 semana=168…). */
  antiguedad_h?: string;
  /** Id de la línea editorial (etiqueta vertical) por la que filtrar. */
  linea?: string;
  /** BÚSQUEDA por titular: subcadena (case-insensitive) sobre el título del tema padre. */
  busqueda?: string;
  /**
   * REPARTO ("la lista" de ClaroSports): id de usuario = piezas COGIDAS por esa persona;
   * `"sin"` = piezas LIBRES (por coger). El responsable vive en el `contenido` padre.
   */
  responsable?: string;
  /**
   * RANGO de `fecha_programada` (ISO `YYYY-MM-DD`): el CALENDARIO pide solo la ventana
   * visible (mes ± margen) en vez del conjunto completo, que el cap de 1000 filas truncaba
   * en silencio. Las piezas SIN fecha quedan FUERA del rango. Ambos opcionales.
   */
  desde?: string;
  hasta?: string;
  /** "1" para mostrar solo piezas evergreens. */
  evergreen?: string;
  /** Paginacion offset-based: tamaño de pagina; ausente = conjunto completo. */
  limite?: string;
  /** Paginacion offset-based: offset; ausente = 0. */
  desplazamiento?: string;
  /**
   * Paginacion KEYSET para el feed (scroll infinito): clave `"<creado>|<id>"` de la última
   * fila vista. Devuelve solo las piezas posteriores en el orden `creado DESC`. La respuesta
   * trae `paginacion.cursor_siguiente` para encadenar; ausente = primera página/desde el inicio.
   */
  cursor?: string;
  /**
   * Activa el MODO FEED (keyset/scroll infinito) en la PRIMERA página, que llega sin `cursor`:
   * acota a un tamaño de página y devuelve `paginacion.cursor_siguiente`. Sin esto (y sin
   * `limite`), el endpoint devuelve el conjunto completo (modo retrocompatible). `"1"` para activar.
   */
  feed?: string;
  /** Permite pasarse a `query()` (Record<string, string | undefined>). */
  [clave: string]: string | undefined;
}

// --- Conexiones (clave de imagen IA + tokens de redes) ---
//
// Los secretos son write-only: nunca llegan al frontend. Del servidor solo se
// recibe el estado (`configurado`/`conectado`) y, para la imagen IA, una
// `pista` no sensible (p. ej. los últimos caracteres de la clave).

/** Un modelo de imagen IA de la lista curada (id + etiqueta legible para el dropdown). */
export interface ModeloImagen {
  id: string;
  etiqueta: string;
}

/** Estado de la configuración del proveedor de imagen con IA. */
export interface RespuestaConexionImagen {
  proveedor: string;
  /** Modelo de imagen EN USO (con su precedencia: almacén > env > por defecto). */
  modelo: string;
  /** Lista curada de modelos disponibles para el dropdown del selector. */
  modelos: ModeloImagen[];
  configurado: boolean;
  /** Pista no sensible de la clave (nunca el valor completo). */
  pista: string;
}

/** Cuerpo para fijar el modelo de imagen IA. */
export interface CuerpoGuardarModeloImagen {
  modelo: string;
}

/** Respuesta al fijar el modelo de imagen IA (devuelve el modelo guardado). */
export interface RespuestaGuardarModeloImagen {
  modelo: string;
}

/** Cuerpo para guardar la clave del proveedor de imagen IA. */
export interface CuerpoGuardarConexionImagen {
  /** Identificador del proveedor (opcional; el backend tiene uno por defecto). */
  proveedor?: string;
  api_key: string;
}

/** Respuesta al guardar la clave de imagen IA. */
export interface RespuestaGuardarConexionImagen {
  configurado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba de conexión de imagen IA. */
export interface RespuestaProbarConexionImagen {
  ok: boolean;
  mensaje: string;
}

/** Estado de conexión de Metricool para UNA marca (sin exponer el token). */
export interface MarcaMetricool {
  marca: string;
  etiqueta: string;
  conectado: boolean;
  /** Pista no sensible del user_id (solo si está conectada). */
  user_id_pista?: string;
  /** blogId de Metricool (solo si está conectada; no es secreto). */
  blog_id?: string;
}

export interface RespuestaMetricool {
  marcas: MarcaMetricool[];
}

/** Cuerpo para descubrir las marcas (blogId) de un token de Metricool. */
export interface CuerpoPerfilesMetricool {
  user_token: string;
  user_id: string;
}

/** Una marca de Metricool descubierta vía simpleProfiles (sin token). */
export interface PerfilMetricool {
  blog_id: string;
  label: string;
}

/** Respuesta al descubrir marcas: lista de {blog_id, label}. */
export interface RespuestaPerfilesMetricool {
  marcas: PerfilMetricool[];
}

/** Cuerpo para guardar las credenciales de Metricool de una marca. */
export interface CuerpoGuardarMetricool {
  user_token: string;
  user_id: string;
  blog_id: string;
}

/** Respuesta al guardar una credencial de Metricool. */
export interface RespuestaGuardarMetricool {
  conectado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba en vivo de una credencial de Metricool. */
export interface RespuestaProbarMetricool {
  ok: boolean;
  detalle: string;
}

// ── Conexión Postproxy (publicación multi-red) ──────────────────────────────
// Postproxy tiene UNA api_key GLOBAL (no por marca) + un grupo de perfiles por
// marca. La api_key es write-only (solo se envía); del servidor llega el estado
// (configurado + pista no sensible) y, por marca, su grupo de perfiles.

/** Canal por el que una marca PUBLICA sus piezas. */
export type CanalPieza = "metricool" | "postproxy";

/** Estado de la conexión Postproxy de UNA marca dentro de la respuesta global. */
export interface MarcaPostproxy {
  marca: string;
  etiqueta: string;
  /** Grupo de perfiles de Postproxy de la marca (null si aún no se ha creado). */
  profile_group_id: string | null;
  /** Canal de publicación activo de la marca (default "metricool"). */
  canal: CanalPieza;
}

/** Respuesta de `GET /conexiones/postproxy`: estado global + marcas. */
export interface RespuestaPostproxy {
  configurado: boolean;
  /** Pista no sensible de la api_key (solo si está configurada). */
  pista: string | null;
  marcas: MarcaPostproxy[];
}

/** Cuerpo para guardar la api_key global de Postproxy (write-only). */
export interface CuerpoGuardarPostproxy {
  api_key: string;
}

/** Respuesta al guardar la api_key de Postproxy. */
export interface RespuestaGuardarPostproxy {
  configurado: true;
  mensaje: string;
}

/** Respuesta de la prueba en vivo de la conexión Postproxy. */
export interface RespuestaProbarPostproxy {
  ok: boolean;
  mensaje: string;
}

/** Cuerpo para fijar (o regenerar) el grupo de perfiles de una marca. */
export interface CuerpoGrupoPostproxy {
  profile_group_id?: string;
}

/** Respuesta al fijar el grupo de perfiles de una marca. */
export interface RespuestaGrupoPostproxy {
  profile_group_id: string;
  mensaje: string;
}

/** Cuerpo para iniciar el OAuth de conexión de una red de una marca. */
export interface CuerpoConectarPostproxy {
  platform: string;
  redirect_url: string;
}

/** Respuesta con la URL de OAuth a abrir en una pestaña nueva. */
export interface RespuestaConectarPostproxy {
  url: string;
}

/** Cuerpo para fijar el canal de publicación de una marca. */
export interface CuerpoCanalPostproxy {
  canal: CanalPieza;
}

/** Respuesta al fijar el canal de publicación de una marca. */
export interface RespuestaCanalPostproxy {
  canal: CanalPieza;
  mensaje: string;
}

// ── Conexión Google Analytics (GA4) ─────────────────────────────────────────
// Una app OAuth GLOBAL (client_id + client_secret write-only) que, una vez
// conectada por OAuth, se mapea a una propiedad GA4 por marca. El client_secret
// solo se envía; del servidor llega el estado (app_configurada, conectado) y el
// client_id (no secreto), más la propiedad mapeada de cada marca.

/** Estado de Google Analytics para UNA marca (sin exponer secretos). */
export interface MarcaGoogleAnalytics {
  marca: string;
  etiqueta: string;
  /** id numérico de la propiedad GA4 mapeada (vacío si no hay). */
  property_id: string;
  conectado: boolean;
}

/** Respuesta de `GET /conexiones/google-analytics`: estado global + marcas. */
export interface RespuestaGoogleAnalytics {
  app_configurada: boolean;
  conectado: boolean;
  /** client_id de la app OAuth (no secreto; vacío si no está configurada). */
  client_id: string;
  marcas: MarcaGoogleAnalytics[];
}

/** Cuerpo para guardar la app OAuth (client_secret write-only). */
export interface CuerpoAppGoogleAnalytics {
  client_id: string;
  client_secret: string;
}

/** Respuesta al guardar la app OAuth. */
export interface RespuestaAppGoogleAnalytics {
  app_configurada: boolean;
  mensaje: string;
}

/** Cuerpo para iniciar el OAuth de Google Analytics. */
export interface CuerpoConectarGoogleAnalytics {
  redirect_uri: string;
}

/** Respuesta con la URL de Google a abrir en el popup. */
export interface RespuestaConectarGoogleAnalytics {
  url: string;
}

/** Cuerpo para canjear el código del OAuth por el refresh_token. */
export interface CuerpoCanjearGoogleAnalytics {
  state: string;
  code: string;
}

/** Respuesta al canjear el código del OAuth. */
export interface RespuestaCanjearGoogleAnalytics {
  conectado: boolean;
  mensaje: string;
}

/** Una propiedad GA4 disponible para mapear a una marca. */
export interface PropiedadGoogleAnalytics {
  property_id: string;
  nombre: string;
  cuenta: string;
}

/** Respuesta al listar las propiedades GA4 de la cuenta conectada. */
export interface RespuestaPropiedadesGoogleAnalytics {
  propiedades: PropiedadGoogleAnalytics[];
}

/** Cuerpo para mapear una propiedad GA4 a una marca. */
export interface CuerpoPropiedadGoogleAnalytics {
  property_id: string;
}

/** Respuesta al mapear (o quitar) la propiedad GA4 de una marca. */
export interface RespuestaGuardarGoogleAnalytics {
  conectado: boolean;
  mensaje: string;
}

/** Respuesta de la prueba en vivo de la propiedad GA4 de una marca. */
export interface RespuestaProbarGoogleAnalytics {
  ok: boolean;
  filas: number;
  mensaje: string;
}
