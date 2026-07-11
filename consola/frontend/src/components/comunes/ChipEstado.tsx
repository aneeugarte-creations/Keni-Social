/**
 * ChipEstado: badge ÚNICO de estados de trabajo en toda la consola.
 *
 * Un solo vocabulario visual para los estados de GENERACIÓN (registro de `claude -p`:
 * ejecutando/completado/error/lanzado), de ETAPA/RUN de pipeline (ok/en_curso/revisar/
 * pendiente/saltada/fallo) y de JOB de cola (pendiente/reclamado). La misma
 * etiqueta y el mismo color significan lo mismo en toda la consola.
 */

import type { BadgeProps } from "@/components/ui/badge";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { EstadoDaemon } from "@/types";

type Aspecto = { variant: BadgeProps["variant"]; clase?: string; texto: string };

// Estado (cualquier dominio) -> aspecto. Sinónimos entre dominios apuntan al MISMO
// aspecto: «completado» (generación) y «ok» (pipeline) son la misma cosa para el ojo.
// Los colores salen de las variantes semánticas de `Badge` (ok/info/aviso/error), la
// receta única de badge de estado del sistema de diseño (docs/sistema-diseno.md).
const ASPECTO: Record<string, Aspecto> = {
  // Terminales felices.
  ok: { variant: "ok", texto: "Completado" },
  completado: { variant: "ok", texto: "Completado" },
  // En curso (generación ejecutando / etapa en curso / job reclamado).
  en_curso: { variant: "info", texto: "En curso" },
  ejecutando: { variant: "info", texto: "En curso" },
  reclamado: { variant: "info", texto: "En curso" },
  // Esperando turno.
  pendiente: { variant: "outline", clase: "text-muted-foreground", texto: "Pendiente" },
  lanzado: { variant: "outline", clase: "text-muted-foreground", texto: "En cola" },
  // Atención humana / verificaciones.
  revisar: { variant: "aviso", texto: "Revisar" },
  saltada: { variant: "outline", clase: "text-muted-foreground/60 border-dashed line-through", texto: "Omitida" },
  // Terminales con problema.
  fallo: { variant: "error", texto: "Error" },
  error: { variant: "error", texto: "Error" },
};

const DESCONOCIDO: Aspecto = { variant: "outline", clase: "text-muted-foreground", texto: "—" };

/** Aspecto de un estado (etiqueta + variante); cae a un neutro si no se reconoce. */
export function aspectoEstado(estado: string): Aspecto {
  return ASPECTO[estado] ?? { ...DESCONOCIDO, texto: estado || "—" };
}

// Receta de tinte por variante semántica, como clases sueltas, para elementos que NO son
// `<Badge>` (p. ej. las cajas de etapa de `TiraEtapas`). Mismo color que el Badge.
const CLASE_VARIANTE: Partial<Record<NonNullable<BadgeProps["variant"]>, string>> = {
  ok: "border-transparent bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  info: "border-transparent bg-sky-500/15 text-sky-700 dark:text-sky-300",
  aviso: "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300",
  error: "border-transparent bg-destructive/10 text-destructive",
};

/** Clases de color de un estado para elementos crudos; texto muted si no hay tinte. */
export function claseEstado(estado: string): string {
  const a = aspectoEstado(estado);
  return (a.variant && CLASE_VARIANTE[a.variant]) || a.clase || "text-muted-foreground";
}

export function ChipEstado({ estado, className }: { estado: string; className?: string }) {
  const a = aspectoEstado(estado);
  return (
    <Badge variant={a.variant} className={cn("border", a.clase, className)}>
      {a.texto}
    </Badge>
  );
}

// Nivel de la ECONOMÍA DE TOKENS (`presupuesto_ia.nivel`): mismo principio, otro dominio.
// Lo comparten el Monitor (donde se opera) y el panel Sistema (donde se observa), para
// que el mismo nivel se llame y pinte IGUAL en ambos.
const NIVEL_PRESUPUESTO: Record<string, Aspecto> = {
  normal: { variant: "ok", texto: "Normal" },
  solo_manual: { variant: "aviso", texto: "Solo manual" },
  agotado: { variant: "error", texto: "Agotado" },
  pausado: { variant: "error", texto: "Pausado" },
};

export function ChipNivelPresupuesto({ nivel, className }: { nivel: string; className?: string }) {
  const a = NIVEL_PRESUPUESTO[nivel] ?? { ...DESCONOCIDO, texto: nivel || "—" };
  return (
    <Badge variant={a.variant} className={cn("border", a.clase, className)}>
      {a.texto}
    </Badge>
  );
}

// Estado de un DAEMON (`latidos.estado`): mismo principio que arriba, otro dominio. Lo comparten
// el panel Sistema (donde se observan los servicios) y los cockpits de la Máquina (Agentes /
// Servicios), para que el mismo estado se llame y pinte IGUAL en ambos. Cae a las variantes
// semánticas de Badge (ok/error/aviso/info); «inactivo» (gate apagado) es un neutro gris.
const ESTADO_DAEMON: Record<EstadoDaemon, Aspecto> = {
  ok: { variant: "ok", texto: "OK" },
  error: { variant: "error", texto: "Error" },
  atrasado: { variant: "aviso", texto: "Atrasado" },
  // Su interruptor propio está ON pero la máquina está apagada: no corre, pero no es un fallo.
  en_espera: { variant: "info", texto: "En espera (máquina apagada)" },
  // El gate del daemon está apagado por su ajuste (mismo lenguaje que el 409 de «Barrer ahora»).
  inactivo: { variant: "outline", clase: "bg-muted text-muted-foreground", texto: "Apagado por ajuste" },
  // Registrado en el arranque pero sin ningún latido todavía (BD recién migrada o hilo que
  // nunca llegó a arrancar): no es «apagado» (eso late con activo=0) ni «atrasado» (eso latió).
  sin_datos: { variant: "outline", clase: "bg-muted text-muted-foreground", texto: "Sin datos" },
};

export function ChipEstadoDaemon({ estado, className }: { estado: EstadoDaemon; className?: string }) {
  const a = ESTADO_DAEMON[estado];
  return (
    <Badge variant={a.variant} className={cn(a.clase, className)}>
      {a.texto}
    </Badge>
  );
}
