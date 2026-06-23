/**
 * Badge de ETAPA IA de una pieza en el Feed de ideación (Flujo D, Fase 4).
 *
 * Es un LABEL del estado en la pipeline ("Generando copy / Falta imagen / Para revisar /
 * Aprobada / Programada / Publicada"), con un punto de color por estado. NO usa spinner en
 * bucle: el feed enseña muchas piezas a la vez y un icono girando en cada una distrae.
 *
 * LENGUAJE DE COLOR UNIFICADO con la Lista (`META_ESTADOS`): la misma pieza luce el MISMO
 * color en el Feed y en la Lista del hub — para-revisar=violeta,
 * programada=ámbar, publicada=esmeralda. El cian (sky) queda EXCLUSIVO de "en preparación"
 * (la IA o el equipo aún trabajan la pieza), que no existe como estado en la Lista.
 * La etapa la deriva `etapaDePieza` (ver `etapa.ts`), o el backend la trae resuelta.
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { metaEstado } from "@/pages/piezas/meta";

import { etiquetaEtapa, META_ETAPA, type EtapaIa } from "./etapa";

/** Etapas "cerradas" → estado canónico de `META_ESTADOS` (hereda su color exacto). */
const ESTADO_DE_ETAPA = {
  programada: "programado",
  publicada: "publicado",
  lista_para_revisar: "en_revision",
} as const;

/** Acciones del EQUIPO pendientes en revisión (placa/hashtags): badge ámbar "hay que hacer
 *  algo", distinto del cian "IA trabajando" y del violeta "te toca el OK". */
const ACCIONES_EQUIPO = new Set<EtapaIa>(["faltan_fotos", "falta_copy_in", "falta_hashtags"]);
const CLASE_ACCION_EQUIPO = "border-transparent bg-amber-500/15 text-amber-700 dark:text-amber-300";

/** Color del punto por etapa, a juego con la clase del badge. */
const PUNTO_DE_ETAPA: Record<EtapaIa, string> = {
  generando_copy: "animate-pulse motion-reduce:animate-none bg-sky-500",
  generando_arte: "animate-pulse motion-reduce:animate-none bg-sky-500",
  faltan_fotos: "bg-amber-500",
  falta_copy_in: "bg-amber-500",
  falta_hashtags: "bg-amber-500",
  lista_para_revisar: "bg-violet-500",
  programada: "bg-amber-500",
  publicada: "bg-emerald-500",
};

export function BadgeEtapa({
  etapa,
  formato,
  className,
}: {
  etapa: EtapaIa;
  /** Ola F: formato de la pieza ('foto'|'video'); ajusta la etiqueta de 'generando_arte'. */
  formato?: string;
  className?: string;
}) {
  const meta = META_ETAPA[etapa];
  const etiqueta = etiquetaEtapa(etapa, formato);
  const clase = meta.enCurso
    ? "border-transparent bg-sky-500/15 text-sky-700 dark:text-sky-300"
    : ACCIONES_EQUIPO.has(etapa)
      ? CLASE_ACCION_EQUIPO
      : metaEstado(ESTADO_DE_ETAPA[etapa as keyof typeof ESTADO_DE_ETAPA]).clase;
  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5", clase, className)}
    >
      <span
        className={cn("h-1.5 w-1.5 rounded-full", PUNTO_DE_ETAPA[etapa])}
        aria-hidden="true"
      />
      {etiqueta}
    </Badge>
  );
}
