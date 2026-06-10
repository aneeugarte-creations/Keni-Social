/**
 * Aviso de INGESTA ESTANCADA: cuando un canal (marca×red×formato) se queda atrás del resto
 * del feed de su marca (p.ej. los Reels de Facebook dejan de sincronizar mientras lo demás
 * entra al día), lo más probable es un problema de sincronización en la fuente (Metricool),
 * no que el equipo haya dejado de publicar. Lo mostramos con un símbolo de alerta ⚠️ para
 * cazarlo a tiempo en vez de descubrirlo a mano. Si no hay nada estancado, no se muestra.
 */
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { api } from "@/lib/api";
import { nombreFormato, nombreRed } from "@/lib/formato";

import { MARCA_TODAS } from "./Controles";

export function AlertaIngesta({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const { data } = useQuery({
    queryKey: ["metricas", "ingesta", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasIngesta({ rango: rangoActual, marca: marca_ }, signal),
  });

  const alertas = data?.alertas ?? [];
  if (alertas.length === 0) return null;

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-500/40 dark:bg-amber-500/10">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
        <div className="space-y-1.5">
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">
            Posible ingesta estancada en la fuente (Metricool)
          </p>
          <p className="text-xs text-amber-800/90 dark:text-amber-200/80">
            Estos canales se quedaron atrás del resto del feed de su marca. Suele ser un fallo
            de sincronización de Metricool con la red, no que se haya dejado de publicar.
          </p>
          <ul className="mt-1 space-y-1 text-xs text-amber-900 dark:text-amber-200 tabular-nums">
            {alertas.map((a) => (
              <li key={`${a.marca}-${a.red}-${a.formato}`}>
                <span className="font-medium">{a.marca}</span> · {nombreRed(a.red)}
                {a.formato ? ` · ${nombreFormato(a.formato)}` : ""} — sin piezas nuevas desde{" "}
                <span className="font-medium">{a.ultima_pieza}</span> ({a.dias_sin_piezas} días;{" "}
                {a.rezago_dias} por detrás del resto).
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
