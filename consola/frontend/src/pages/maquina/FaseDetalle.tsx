/**
 * FaseDetalle (`/maquina/contexto/:proceso/:fase`) — la subpágina de UNA fase. Para los dos MOTORES
 * (investigación / producción) es una fase del pipeline: cabecera con vuelta a Contexto + icono y
 * nombre, y debajo su detalle (Prompt · Contexto · Logs). Para las pestañas-catálogo (herramientas /
 * desarrollo) es un agente suelto: mismo encabezado y SOLO su Prompt + «Acerca» (no encola ni deja
 * histórico, así que sin Logs). Sustituye al antiguo pop-up: cada agente vive en su propia URL.
 * El interruptor on/off de la fase (en los motores) vive en la fila de la lista (Contexto), no aquí.
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
  agentesDe,
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  slugFase,
  tieneContenido,
} from "@/pages/maquina/fases";

const PROCESOS = ["investigacion", "produccion", "herramientas", "desarrollo"] as const;
type Proceso = (typeof PROCESOS)[number];

export default function FaseDetalle() {
  const navigate = useNavigate();
  const { proceso: procesoParam, fase: faseSlug } = useParams();
  const { marcaActiva } = useMarcaActiva();
  const proceso: Proceso = PROCESOS.includes(procesoParam as Proceso)
    ? (procesoParam as Proceso)
    : "investigacion";
  // Catálogo de agentes sueltos (Herramientas / Desarrollo): se lanzan a mano, sin pipeline.
  const esCatalogo = proceso === "herramientas" || proceso === "desarrollo";

  const fases = esCatalogo
    ? agentesDe(proceso)
    : proceso === "produccion"
      ? FASES_PRODUCCION
      : FASES_INVESTIGACION;
  const queuePorTipo = proceso === "produccion" ? QUEUE_PRODUCCION : QUEUE_INVESTIGACION;
  const fase = fases.find((f) => slugFase(f.nombre) === faseSlug);

  // La cola solo alimenta los logs de los motores; en el catálogo no se pide.
  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
    enabled: !esCatalogo,
  });

  // Fase inexistente (slug roto) o, en los motores, SIN contenido propio (su subpágina no aportaría
  // nada, p. ej. Admitir): vuelve a la pestaña del proceso. Un agente del catálogo siempre tiene
  // prompt, así que `tieneContenido` se cumple.
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
          mostrarLogs={!esCatalogo}
        />
      </div>
    </div>
  );
}
