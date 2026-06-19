/**
 * DocumentoContexto (`/maquina/contexto/doc/*`) — la subpágina de UN documento que ACOMPAÑA a un
 * prompt maestro: un sub-prompt (p. ej. un envoltorio de red) o una pieza editorial (voz, reglas,
 * tropicalización…). Le da el MISMO control que a una etapa: editor completo (Acerca, versiones,
 * publicar), no un overlay. Se llega desde la pestaña «Acompaña» de la subpágina de la fase; «←»
 * vuelve a donde estabas (`navigate(-1)`).
 *
 * El id del documento lleva barras (`editorial/rrss/unotv/voz`, `prompt/envoltorios/redes`), de ahí
 * la ruta splat (`doc/*`).
 */
import { useQuery } from "@tanstack/react-query";
import { Bot, FileText } from "lucide-react";
import { Navigate, useNavigate, useParams } from "react-router-dom";

import { TituloPagina } from "@/components/layout/encabezado";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import { DetalleFase } from "@/pages/maquina/DetalleFase";
import type { FasePipeline } from "@/pages/monitor/PanelPipeline";

export default function DocumentoContexto() {
  const navigate = useNavigate();
  const { "*": docId } = useParams();
  const { marcaActiva } = useMarcaActiva();

  const docQuery = useQuery({
    queryKey: ["prompts-doc", docId],
    queryFn: ({ signal }) => api.documento(docId as string, signal),
    enabled: !!docId,
  });
  const doc = docQuery.data?.documento ?? null;

  // Sin id en la URL: no hay nada que mostrar, vuelve a la página Contexto.
  if (!docId) {
    return <Navigate to="/maquina/contexto" replace />;
  }

  // El detalle reusa DetalleFase con una fase sintética: solo su prompt + «Acerca» (un documento
  // que acompaña no tiene logs ni, normalmente, acompañamiento propio).
  const fase: FasePipeline = {
    nombre: doc?.titulo ?? docId.split("/").pop() ?? docId,
    es_ia: doc?.tipo === "prompt",
    claves: [],
    ayuda: doc?.descripcion ?? "",
    doc: docId,
  };

  return (
    <div className="flex h-full min-h-0 flex-col">
      <TituloPagina
        titulo={fase.nombre}
        icono={doc?.tipo === "prompt" ? Bot : FileText}
        onAtras={() => navigate(-1)}
      />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <DetalleFase fase={fase} proceso="herramientas" marca={marcaActiva} mostrarLogs={false} />
      </div>
    </div>
  );
}
