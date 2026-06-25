/**
 * Heurística de alineación del hilo de mensajes directos.
 *
 * No tenemos el id de la página/marca en el contrato, así que distinguimos los dos
 * lados del chat cruzando el `autor_id` del mensaje con los `participantes` de la
 * conversación: los `participantes` son la AUDIENCIA (la persona con la que se habla;
 * traen nombre y avatar). Por tanto:
 *   - mensaje cuyo `autor_id` coincide con un participante → ENTRANTE (audiencia), izquierda.
 *   - mensaje sin `autor_id` o con uno que no es participante → SALIENTE (el propio
 *     negocio/página respondiendo), derecha.
 *
 * Es una heurística honesta para un MVP de lectura: si la fuente llegara a incluir a
 * la página entre los participantes, sus mensajes se pintarían como entrantes — una
 * degradación tolerable (el hilo se sigue leyendo en orden), nunca un fallo.
 */
import type { Conversacion, MensajeDM, ParticipanteInbox } from "@/types";

/** `true` si el mensaje lo escribió la audiencia (entrante); `false` si el negocio (saliente). */
export function esMensajeEntrante(
  mensaje: Pick<MensajeDM, "autor_id">,
  participantes: ParticipanteInbox[],
): boolean {
  if (!mensaje.autor_id) return false;
  return participantes.some((p) => p.id != null && p.id === mensaje.autor_id);
}

/** Nombre legible de la audiencia de una conversación (primer participante con nombre). */
export function nombreAudiencia(conversacion: Pick<Conversacion, "participantes">): string {
  const conNombre = conversacion.participantes.find((p) => p.nombre && p.nombre.trim() !== "");
  return conNombre?.nombre ?? "Sin nombre";
}

/** Avatar de la audiencia de una conversación (primer participante con avatar), o null. */
export function avatarAudiencia(
  conversacion: Pick<Conversacion, "participantes">,
): string | null {
  return conversacion.participantes.find((p) => p.avatar)?.avatar ?? null;
}
