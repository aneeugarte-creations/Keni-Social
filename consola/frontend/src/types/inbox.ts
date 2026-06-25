/**
 * Inbox de SOLO lectura: mensajes directos (DMs) y comentarios de publicaciones
 * de Facebook e Instagram, leídos desde Metricool. El equipo los lee y actúa con
 * criterio fuera de la consola (aquí no se responde ni se escribe).
 *
 * Reflejan el contrato de `GET /api/inbox/conversaciones` y `GET /api/inbox/comentarios`.
 * Todas las claves vienen SIEMPRE (incluso `null`/`[]`); `por_red` trae 0..2 grupos
 * (una red sin datos no aparece). Las fechas llegan en ISO-8601 con offset CDMX.
 */

/** Participante de una conversación de mensajes directos (la audiencia). */
export interface ParticipanteInbox {
  id: string | null;
  nombre: string | null;
  avatar: string | null;
}

/** Un mensaje dentro de una conversación. Embebido (no hay detalle aparte). */
export interface MensajeDM {
  id: string | null;
  /** Autor del mensaje; se cruza con `participantes` para alinear el hilo. */
  autor_id: string | null;
  texto: string | null;
  fecha: string | null;
  /**
   * URLs del contenido del mensaje: publicaciones compartidas (links de instagram.com),
   * media enviada (URLs de CDN) o menciones de historia. El DM suele venir sin `texto` y
   * traer el contenido aquí.
   */
  adjuntos: string[];
}

/** Una conversación de mensajes directos, con sus mensajes embebidos. */
export interface Conversacion {
  id: string;
  red: string;
  /** `true` si la conversación espera respuesta del equipo. */
  pendiente: boolean;
  creado: string | null;
  actualizado: string | null;
  participantes: ParticipanteInbox[];
  /** Mensajes del hilo (orden de la fuente). */
  mensajes: MensajeDM[];
}

/** Las conversaciones de UNA red (Facebook o Instagram). */
export interface ConversacionesPorRed {
  red: string;
  conversaciones: Conversacion[];
}

/** Respuesta de `GET /api/inbox/conversaciones`. */
export interface RespuestaInboxConversaciones {
  /** 0..2 grupos (FB/IG); una red sin datos no aparece. Reciente primero. */
  por_red: ConversacionesPorRed[];
  generado_en: string;
}

/** Autor de un comentario o de una respuesta (la audiencia). */
export interface AutorComentario {
  id: string | null;
  nombre: string | null;
  avatar: string | null;
}

/** Respuesta anidada a un comentario (un solo nivel). */
export interface RespuestaComentarioInbox {
  id: string;
  autor: AutorComentario | null;
  texto: string | null;
  fecha: string | null;
  pendiente: boolean;
}

/** Un comentario de la audiencia sobre una publicación, con su contexto. */
export interface Comentario {
  id: string;
  red: string;
  /** `true` si el comentario espera respuesta del equipo. */
  pendiente: boolean;
  autor: AutorComentario | null;
  texto: string | null;
  fecha: string | null;
  /** Enlace permanente al comentario en la red. */
  permalink: string | null;
  /** Contexto: la publicación comentada (texto recortado, enlace y media). */
  post_id: string | null;
  post_texto: string | null;
  post_enlace: string | null;
  post_media: string[];
  respuestas: RespuestaComentarioInbox[];
}

/** Los comentarios de UNA red (Facebook o Instagram). */
export interface ComentariosPorRed {
  red: string;
  comentarios: Comentario[];
}

/** Respuesta de `GET /api/inbox/comentarios`. */
export interface RespuestaInboxComentarios {
  /** 0..2 grupos (FB/IG); una red sin datos no aparece. */
  por_red: ComentariosPorRed[];
  /** Ventana consultada (días). */
  dias: number;
  generado_en: string;
}
