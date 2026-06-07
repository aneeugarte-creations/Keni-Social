/**
 * Badge de ETAPA IA de una pieza en el Feed de ideación (Flujo D, Fase 4).
 *
 * Es un LABEL del estado en la tubería ("Generando copy / Generando arte / Lista para
 * revisar / Aprobada / Programada / Publicada"), con un punto de color por estado. NO usa
 * spinner en bucle: el feed enseña muchas piezas a la vez y un icono girando en cada una es
 * ruido; el color del punto (ámbar = la IA trabaja, azul = espera tu OK, verde = lista/ya
 * salió) basta para leer el estado de un vistazo. La etapa la deriva `etapaDePublicacion`
 * (ver `etapa.ts`), o el backend (Flujo C) la trae ya resuelta.
 */
import { cn } from "@/lib/utils";

import { etiquetaEtapa, META_ETAPA, type EtapaIa } from "./etapa";

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
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        meta.enCurso
          ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
          : etapa === "lista_para_revisar"
            ? "bg-sky-500/15 text-sky-700 dark:text-sky-300"
            : "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
        className,
      )}
      title={meta.enCurso ? "La IA aún está trabajando esta pieza" : undefined}
    >
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          meta.enCurso
            ? "bg-amber-500"
            : etapa === "lista_para_revisar"
              ? "bg-sky-500"
              : "bg-emerald-500",
        )}
        aria-hidden="true"
      />
      {etiqueta}
    </span>
  );
}
