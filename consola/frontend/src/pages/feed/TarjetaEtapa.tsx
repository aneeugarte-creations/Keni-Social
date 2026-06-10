/**
 * Badge de ETAPA IA de una pieza en el Feed de ideación (Flujo D, Fase 4).
 *
 * Es un LABEL del estado en la tubería ("Generando copy / Falta imagen / Para revisar /
 * Aprobada / Programada / Publicada"), con un punto de color por estado. NO usa spinner en
 * bucle: el feed enseña muchas piezas a la vez y un icono girando en cada una es ruido.
 *
 * LENGUAJE DE COLOR UNIFICADO con la Lista (`META_ESTADOS`): la misma pieza luce el MISMO
 * color en el Feed y en la Lista del hub — para-revisar=violeta, aprobada=azul,
 * programada=ámbar, publicada=esmeralda. El cian (sky) queda EXCLUSIVO de "en preparación"
 * (la IA o el equipo aún trabajan la pieza), que no existe como estado en la Lista.
 * La etapa la deriva `etapaDePublicacion` (ver `etapa.ts`), o el backend la trae resuelta.
 */
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { metaEstado } from "@/pages/publicaciones/meta";

import { etiquetaEtapa, META_ETAPA, type EtapaIa } from "./etapa";

/** Etapas "cerradas" → estado canónico de `META_ESTADOS` (hereda su color exacto). */
const ESTADO_DE_ETAPA = {
  aprobada: "aprobado",
  programada: "programado",
  publicada: "publicado",
  lista_para_revisar: "en_revision",
  en_borrador: "borrador",
} as const;

/** Color del punto por etapa, a juego con la clase del badge. */
const PUNTO_DE_ETAPA: Record<EtapaIa, string> = {
  generando_copy: "animate-pulse motion-reduce:animate-none bg-sky-500",
  generando_arte: "animate-pulse motion-reduce:animate-none bg-sky-500",
  en_borrador: "bg-zinc-400",
  lista_para_revisar: "bg-violet-500",
  aprobada: "bg-blue-500",
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
    : metaEstado(ESTADO_DE_ETAPA[etapa as keyof typeof ESTADO_DE_ETAPA]).clase;
  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5", clase, className)}
      title={meta.enCurso ? "La IA aún está trabajando esta pieza" : undefined}
    >
      <span
        className={cn("h-1.5 w-1.5 rounded-full", PUNTO_DE_ETAPA[etapa])}
        aria-hidden="true"
      />
      {etiqueta}
    </Badge>
  );
}
