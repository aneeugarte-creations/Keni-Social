/**
 * FaseDetalle (`/maquina/contexto/:proceso/:fase`) — la subpágina de UNA fase del pipeline. Antes
 * era un panel desplegable bajo la fila; ahora es su propia página: cabecera con vuelta a Contexto
 * (en su pestaña) + icono y nombre de la fase, y debajo su detalle (Prompt · Contexto · Logs).
 * El interruptor on/off de la fase vive en la fila de la lista (Contexto), no aquí.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, Cog } from "lucide-react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { DetalleFase } from "@/pages/maquina/DetalleFase";
import {
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  slugFase,
} from "@/pages/maquina/fases";

export default function FaseDetalle() {
  const navigate = useNavigate();
  const { proceso: procesoParam, fase: faseSlug } = useParams();
  const { marcaActiva } = useMarcaActiva();
  const proceso = procesoParam === "produccion" ? "produccion" : "investigacion";
  const fases = proceso === "produccion" ? FASES_PRODUCCION : FASES_INVESTIGACION;
  const queuePorTipo = proceso === "produccion" ? QUEUE_PRODUCCION : QUEUE_INVESTIGACION;
  const fase = fases.find((f) => slugFase(f.nombre) === faseSlug);

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // Fase inexistente (slug roto): vuelve a la pestaña del proceso.
  if (!fase) {
    return <Navigate to={`/maquina/contexto?proceso=${proceso}`} replace />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      <div className="flex items-start gap-3">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 shrink-0"
          aria-label="Volver a Contexto"
          onClick={() => navigate(`/maquina/contexto?proceso=${proceso}`)}
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          {/* Solo icono + nombre: la descripción vive en la tarjeta «Acerca de» del editor
              (debajo), para no duplicarla aquí y en el panel. */}
          <div className="flex items-center gap-1.5 text-lg font-semibold leading-tight">
            {fase.es_ia ? (
              <Bot className="h-5 w-5 shrink-0" aria-label="IA" />
            ) : (
              <Cog className="h-5 w-5 shrink-0 text-muted-foreground" aria-label="determinista" />
            )}
            {fase.nombre}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <DetalleFase
          fase={fase}
          proceso={proceso}
          marca={marcaActiva}
          cola={cola.data}
          queuePorTipo={queuePorTipo}
        />
      </div>
    </div>
  );
}
