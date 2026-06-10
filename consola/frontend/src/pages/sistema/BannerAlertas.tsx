import { useQuery } from "@tanstack/react-query";
import { TriangleAlert } from "lucide-react";

import { api } from "@/lib/api";

import { INTERVALO_RECURSOS_MS } from "./lib";

/**
 * Banner de ALERTAS del panel Sistema: sintetiza en una sola franja todo lo que requiere
 * atención, a partir de las MISMAS queries que las secciones de abajo (React Query las
 * dedupe por queryKey: cero peticiones extra). Sin problemas no pinta nada.
 */
export function BannerAlertas() {
  const recursos = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const daemons = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const backups = useQuery({
    queryKey: ["sistema", "backups"],
    queryFn: ({ signal }) => api.sistemaBackups(signal),
    refetchInterval: INTERVALO_RECURSOS_MS * 4,
  });
  const cola = useQuery({
    queryKey: ["sistema", "cola"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const s3 = useQuery({
    queryKey: ["sistema", "s3"],
    queryFn: ({ signal }) => api.sistemaS3(signal),
    refetchInterval: INTERVALO_RECURSOS_MS * 4,
  });

  const problemas: string[] = [];

  for (const d of recursos.data?.discos ?? []) {
    if (d.porcentaje >= 85) {
      problemas.push(`Disco «${d.etiqueta}» al ${d.porcentaje.toFixed(0)}%`);
    }
  }
  for (const l of daemons.data?.daemons ?? []) {
    if (l.estado === "atrasado") problemas.push(`Daemon «${l.daemon}» atrasado (sin latido)`);
    if (l.estado === "error") problemas.push(`Daemon «${l.daemon}» con su último barrido en error`);
  }
  if (backups.data?.configurado) {
    if (backups.data.atrasado) problemas.push("Backup local atrasado (>26 h sin dump)");
    if (backups.data.estado && !backups.data.estado.ok) {
      problemas.push(`Último backup FALLÓ en «${backups.data.estado.paso}»`);
    }
  }
  if (cola.data?.cola_llena) problemas.push("Cola de generación LLENA (rechazando trabajo)");
  const presupuesto = cola.data?.presupuesto;
  if (presupuesto?.nivel === "agotado") problemas.push("Presupuesto de tokens AGOTADO (corte total)");
  if (presupuesto?.nivel === "solo_manual") problemas.push("Presupuesto de tokens al límite (solo manual)");
  if (presupuesto?.pausada) problemas.push("Generación pausada por kill switch");
  if (s3.data?.configurado && s3.data.salud === "err") {
    problemas.push("Almacenamiento S3 con error de salud");
  }

  if (problemas.length === 0) return null;

  return (
    <div
      role="alert"
      className="flex items-start gap-3 rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 text-sm"
    >
      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
      <div>
        <p className="font-medium text-amber-600 dark:text-amber-400">
          {problemas.length} aviso(s) que requieren atención
        </p>
        <ul className="mt-1 list-inside list-disc text-muted-foreground">
          {problemas.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}
