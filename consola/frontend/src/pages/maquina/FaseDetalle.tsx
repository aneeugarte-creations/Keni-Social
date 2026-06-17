/**
 * FaseDetalle (`/maquina/contexto/:proceso/:fase`) — la subpágina de UNA fase del pipeline. Antes
 * era un panel desplegable bajo la fila; ahora es su propia página: cabecera con vuelta a Contexto
 * (en su pestaña) + icono y nombre de la fase, y debajo su detalle (Prompt · Contexto · Logs).
 * El interruptor on/off de la fase vive en la fila de la lista (Contexto), no aquí.
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, Cog } from "lucide-react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
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
  tieneContenido,
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

  // Fase inexistente (slug roto) o SIN contenido propio (su subpágina Prompt · Contexto · Logs no
  // aportaría nada, p. ej. Admitir: no es IA ni tiene prompt): vuelve a la pestaña del proceso.
  if (!fase || !tieneContenido(fase)) {
    return <Navigate to={`/maquina/contexto?proceso=${proceso}`} replace />;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* La cabecera (← volver + icono + nombre de la fase) vive en la BARRA SUPERIOR del shell,
          no como fila del cuerpo. La descripción vive en la tarjeta «Acerca de» (dentro de
          DetalleFase, sobre las pestañas), así que aquí no se duplica. */}
      <TituloPagina
        titulo={fase.nombre}
        icono={fase.es_ia ? Bot : Cog}
        onAtras={() => navigate(`/maquina/contexto?proceso=${proceso}`)}
      />

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
