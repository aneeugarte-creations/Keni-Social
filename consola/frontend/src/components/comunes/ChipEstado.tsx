/**
 * ChipEstado: badge ÚNICO de estados de trabajo en toda la consola.
 *
 * Un solo vocabulario visual para los estados de GENERACIÓN (registro de `claude -p`:
 * ejecutando/completado/error/lanzado), de ETAPA/RUN de pipeline (ok/en_curso/revisar/
 * pendiente/saltada/fallo) y de JOB de cola (pendiente/reclamado). Antes cada página
 * tenía su mapeo (Actividad `presentacionEstado`, Pipelines `ASPECTO`, conversión inline
 * en Pipelines para estados de generación) y el mismo concepto se llamaba distinto
 * («OK» vs «Completado», «Visualizando…» vs «En curso»). Consolidado aquí: misma
 * etiqueta y mismo color signifiquen lo mismo estés en la página que estés.
 */

import type { BadgeProps } from "@/components/ui/badge";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

type Aspecto = { variant: BadgeProps["variant"]; clase?: string; texto: string };

// Paletas compartidas (también las usa la tira de etapas de Pipelines vía `aspectoEstado`).
const VERDE = "bg-emerald-500/15 text-emerald-600 border-emerald-500/30";
const CIELO = "bg-sky-500/15 text-sky-600 border-sky-500/30";
const AMBAR = "bg-amber-500/15 text-amber-600 border-amber-500/30";

// Estado (cualquier dominio) -> aspecto. Sinónimos entre dominios apuntan al MISMO
// aspecto: «completado» (generación) y «ok» (pipeline) son la misma cosa para el ojo.
const ASPECTO: Record<string, Aspecto> = {
  // Terminales felices.
  ok: { variant: "secondary", clase: VERDE, texto: "Completado" },
  completado: { variant: "secondary", clase: VERDE, texto: "Completado" },
  // En curso (generación ejecutando / etapa en curso / job reclamado).
  en_curso: { variant: "secondary", clase: CIELO, texto: "En curso" },
  ejecutando: { variant: "secondary", clase: CIELO, texto: "En curso" },
  reclamado: { variant: "secondary", clase: CIELO, texto: "En curso" },
  // Esperando turno.
  pendiente: { variant: "outline", clase: "text-muted-foreground", texto: "Pendiente" },
  lanzado: { variant: "outline", clase: "text-muted-foreground", texto: "Lanzado" },
  // Atención humana / cribas.
  revisar: { variant: "secondary", clase: AMBAR, texto: "Revisar" },
  saltada: { variant: "outline", clase: "text-muted-foreground/60 border-dashed line-through", texto: "Saltada" },
  // Terminales con problema.
  fallo: { variant: "destructive", texto: "Error" },
  error: { variant: "destructive", texto: "Error" },
};

const DESCONOCIDO: Aspecto = { variant: "outline", clase: "text-muted-foreground", texto: "—" };

/** Aspecto de un estado (etiqueta + variante); cae a un neutro si no se reconoce. */
export function aspectoEstado(estado: string): Aspecto {
  return ASPECTO[estado] ?? { ...DESCONOCIDO, texto: estado || "—" };
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
  normal: { variant: "secondary", clase: VERDE, texto: "Normal" },
  solo_manual: { variant: "secondary", clase: AMBAR, texto: "Solo manual" },
  agotado: { variant: "destructive", texto: "Agotado" },
  pausado: { variant: "destructive", texto: "Pausado" },
};

export function ChipNivelPresupuesto({ nivel, className }: { nivel: string; className?: string }) {
  const a = NIVEL_PRESUPUESTO[nivel] ?? { ...DESCONOCIDO, texto: nivel || "—" };
  return (
    <Badge variant={a.variant} className={cn("border", a.clase, className)}>
      {a.texto}
    </Badge>
  );
}
