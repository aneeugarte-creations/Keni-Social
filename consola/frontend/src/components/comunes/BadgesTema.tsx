import { Badge } from "@/components/ui/badge";
import type { EstadoTema } from "@/types";

/**
 * Badges de gestión de un tema/ítem del Investigador (Fase 2b), compartidos por el
 * panel del Plan (ParrillaDia) y el de Descubrimiento (Radar):
 *
 *  - ESTADO: responde a "no sé qué ya está preparado". Pinta badge SOLO si el tema ya
 *    se gestionó ("En parrilla" / "Publicado"); lo `nuevo` (o ausente) es lo normal y
 *    NO ensucia con badge. Tono sobrio "ya gestionado" (verde discreto / muted).
 *  - PRIORIDAD: responde a "si pasa algo fuerte tiene que salir rápido". Una sola
 *    palabra, "Prioritario" (texto exacto, SIN emoji ni iconos), con un acento ámbar
 *    sobrio del tema para llamar la atención de forma profesional.
 *  - BREAKING: responde a "la señal del tema está acelerando, conviene atender ya".
 *    Etiqueta "En aumento" (texto exacto, SIN emoji ni iconos). Acento azul/cielo
 *    sobrio del sistema de diseño, DISTINTO del ámbar de "Prioritario" y del verde de
 *    "Publicado": máxima visibilidad sin estridencia. Va primero por ser lo más urgente.
 */

/** Badge de estado de gestión. `null` cuando el tema es nuevo (no se pinta). */
export function BadgeEstadoTema({ estado }: { estado?: EstadoTema }) {
  if (estado === "publicado") {
    // Verde sobrio: "ya salió, gestionado".
    return <Badge variant="ok">Publicado</Badge>;
  }
  if (estado === "en_parrilla") {
    // Muted/neutro: "ya está preparado en la parrilla del CM".
    return <Badge variant="secondary">En parrilla</Badge>;
  }
  return null;
}

/**
 * Badge de "breaking" (señal en aumento). `null` salvo que `breaking === true`.
 * Lo más urgente: va antes que "Prioritario" para máxima visibilidad.
 */
export function BadgeBreakingTema({ breaking }: { breaking?: boolean }) {
  if (breaking !== true) return null;
  // Acento azul/cielo sobrio del sistema de diseño: distinto del ámbar ("Prioritario")
  // y del verde ("Publicado"). Llama la atención sin estridencia, sin iconos ni emojis.
  return (
    <Badge
      variant="secondary"
      className="border-sky-500/40 bg-sky-500/20 text-sky-700 font-semibold uppercase tracking-wide dark:text-sky-300"
    >
      En aumento
    </Badge>
  );
}

/** Badge de prioridad. `null` salvo que el tema sea prioritario. */
export function BadgePrioridadTema({ prioritario }: { prioritario?: boolean }) {
  if (!prioritario) return null;
  // Acento ámbar sobrio del tema (token de la variante `aviso` reforzado): llama la
  // atención sin estridencia, sin iconos de fuego ni emojis. Una sola palabra.
  return (
    <Badge
      variant="aviso"
      className="border-amber-500/40 bg-amber-500/20 font-semibold uppercase tracking-wide"
    >
      Prioritario
    </Badge>
  );
}
