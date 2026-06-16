/**
 * ServiciosMaquina — los daemons NO-IA de un motor (recolección, programador, GC…) bajo el
 * pipeline en la página «Contexto», con EL MISMO formato de fila que las etapas (`FilaFasePipeline`)
 * y separados del pipeline por una línea horizontal. Por fila: estado + interruptor on/off (su
 * `clave_gate`). La gestión completa (barridos, histórico) sigue en Agentes › Sistema.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { FilaFasePipeline } from "@/pages/monitor/PanelPipeline";
import { ChipEstadoDaemon, formatoIntervalo } from "@/pages/sistema/SeccionDaemons";
import { INTERVALO_RECURSOS_MS } from "@/pages/sistema/lib";
import type { Proceso } from "@/types";

export function ServiciosMaquina({ motor }: { motor: Proceso }) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });
  const guardar = useGuardarAjuste();
  const guardandoClave = guardar.isPending ? (guardar.variables?.clave ?? null) : null;
  const onToggle = (clave: string, valor: boolean) =>
    guardar.mutate(
      { clave, valor },
      { onSuccess: () => void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] }) },
    );

  const daemons = (query.data?.daemons ?? []).filter(
    (d) => d.clase === "maquina" && d.motor === motor,
  );
  // Sin servicios (o aún cargando): nada que separar — no pintamos la línea.
  if (daemons.length === 0) return null;

  return (
    <div className="mt-6">
      <hr className="mb-4 border-border/60" />
      <h3 className="mb-3 text-sm font-semibold">Servicios (no consumen IA)</h3>
      <ol className="w-full space-y-2">
        {daemons.map((d) => (
          <li key={d.daemon}>
            <FilaFasePipeline
              esIa={false}
              nombre={d.etiqueta}
              ayuda={`cada ${formatoIntervalo(d.intervalo_seg)}`}
              derecha={
                <>
                  <ChipEstadoDaemon estado={d.estado} />
                  {d.clave_gate ? (
                    <Switch
                      checked={Boolean(d.gate_activo)}
                      disabled={guardandoClave === d.clave_gate}
                      onCheckedChange={(v) => onToggle(d.clave_gate as string, v)}
                      aria-label={`Encender/apagar el servicio ${d.daemon}`}
                    />
                  ) : (
                    <span className="text-xs text-muted-foreground">Siempre activo</span>
                  )}
                </>
              }
            />
          </li>
        ))}
      </ol>
    </div>
  );
}
