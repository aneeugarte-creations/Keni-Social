import type { Contenido, EventoRota, PrioridadEvento, TipoCoberturaEvento } from "@/types";

/** La COBERTURA de un evento: el partido + TODAS las personas que lo cubren (multi-cobertura). */
export type Cobertura = {
  eventoId: string;
  titulo: string;
  hora: string;
  orden: string;
  /**
   * Cómo se cubre el evento (transmisión con señal / solo imágenes), copiado del EVENTO de la rota.
   * El guion del partido lo respeta: en «solo imágenes» recorta los entregables de directo (la fase
   * «Durante»). `undefined` si el evento no se encuentra → guion completo (trato como transmisión).
   */
  tipoCobertura?: TipoCoberturaEvento;
  /**
   * Prioridad HEREDADA del EVENTO de la rota (las tareas de cobertura no la llevan): así una
   * cobertura «alta» puede saltar a la banda «Urgente ahora» del Panorama. `undefined` si el
   * evento no se encuentra (se trata como «media»). Resuelta vía el Map de eventos por id,
   * igual que `tipoCobertura`.
   */
  prioridad?: PrioridadEvento;
  /**
   * El EVENTO de la rota subyacente (si sigue en la lista cargada): la FUENTE para EDITAR o
   * BORRAR el partido desde su cobertura. La fila de cobertura se deriva de las TAREAS (su
   * título/fecha son una FOTO del evento tomada al cubrir), así que editar/borrar el partido
   * debe tocar el evento Y sus tareas; este puntero da el evento. `undefined` si no se encuentra
   * (la acción de editar/borrar no se ofrece).
   */
  evento?: EventoRota;
  cubridores: Contenido[];
  /**
   * ROLES soltados de un evento que SIGUE cubierto por otros: tareas de cobertura HUÉRFANAS
   * (sin responsable, su `formato` conserva el rol). Resurgen como «Por cubrir · <rol>»
   * re-cogibles DENTRO de la cobertura — el partido nunca desaparece (lo sostienen los demás
   * cubridores) y el rol liberado no se pierde de vista.
   */
  libres: Contenido[];
};

/** Un ítem de la lista: un evento por cubrir, su cobertura (≥1 dueño), o un encargo suelto. */
export type Item =
  | { kind: "evento"; clave: string; orden: string; evento: EventoRota }
  | { kind: "cobertura"; clave: string; orden: string; cobertura: Cobertura }
  | { kind: "tarea"; clave: string; orden: string; tarea: Contenido };

/**
 * Reparte tareas + eventos en las tres formas que pinta la lista:
 *  - `coberturas`: un evento con ≥1 cubridor (cada cubridor = una tarea clase='tarea' con
 *    `evento_id`). MULTI-COBERTURA: varias personas pueden cubrir el mismo evento.
 *  - `encargos`: tareas sueltas (sin `evento_id`), de UN dueño.
 *  - `eventosLibres`: eventos coverables con 0 cubridores → «Por cubrir».
 * Una tarea de cobertura SOLTADA (sin responsable) queda HUÉRFANA: su evento vuelve a «Por
 * cubrir» (se devuelve como `recuperable`, re-cogible) — el partido NUNCA se borra.
 */
export function agrupar(tareas: Contenido[], eventos: EventoRota[]) {
  const encargos = tareas.filter((t) => !t.evento_id);
  // EVENTO por id: para resolver `tipo_cobertura` de cada cobertura (vive en el evento, no en la tarea).
  const eventoPorId = new Map(eventos.map((e) => [e.id, e]));
  // Todas las tareas de cobertura (con `evento_id`) agrupadas por evento.
  const porEvento = new Map<string, Contenido[]>();
  for (const t of tareas) {
    if (!t.evento_id) continue;
    const lista = porEvento.get(t.evento_id) ?? [];
    lista.push(t);
    porEvento.set(t.evento_id, lista);
  }
  const coberturas: Cobertura[] = [];
  // `recuperables`: eventos cuya cobertura se SOLTÓ (solo tareas sueltas, sin dueño). El
  // partido sigue ahí; se pinta como «Por cubrir» (una tarea, re-cogible) para que no parezca
  // borrado. Así se recuperan los partidos que se soltaron por error.
  const recuperables: Contenido[] = [];
  for (const [eventoId, lista] of porEvento) {
    const cubridores = lista.filter((t) => t.responsable_id);
    if (cubridores.length > 0) {
      // El evento sigue cubierto por ≥1 persona; las tareas HUÉRFANAS (roles soltados) viajan
      // como `libres` para resurgir como «Por cubrir · <rol>» dentro de la misma cobertura.
      coberturas.push({
        eventoId,
        titulo: cubridores[0].titulo,
        hora: cubridores[0].hora_objetivo,
        orden: cubridores[0].fecha_objetivo || "9999-99-99",
        tipoCobertura: eventoPorId.get(eventoId)?.tipo_cobertura,
        prioridad: eventoPorId.get(eventoId)?.prioridad,
        evento: eventoPorId.get(eventoId),
        cubridores,
        libres: lista.filter((t) => !t.responsable_id),
      });
    } else {
      // Sin cubridores: el partido sigue y resurge como «Por cubrir». Si quedaron varios ROLES
      // soltados (distinto `formato`), resurge UNO por rol para no perder ninguno de vista
      // (dedupe por rol: si hay varias sueltas del mismo rol, basta una re-cogible).
      const rolesVistos = new Set<string>();
      for (const t of lista) {
        const rol = t.formato || "";
        if (rolesVistos.has(rol)) continue;
        rolesVistos.add(rol);
        recuperables.push(t);
      }
    }
  }
  // Eventos de la rota SIN ninguna tarea (nunca tocados) → «Por cubrir».
  const eventosLibres = eventos.filter(
    (e) => e.tipo_cobertura !== "no_cubrir" && !porEvento.has(e.id),
  );
  return { coberturas, encargos, eventosLibres, recuperables };
}
