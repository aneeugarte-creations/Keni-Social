/**
 * Contexto (`/maquina/contexto`) — la página ÚNICA de la máquina: tres pestañas.
 * Pipeline — el flujo completo FUENTE→FEED con toggles individuales y cascada de críticas.
 * Herramientas — todos los agentes independientes que se lanzan a mano (cajas por tipo).
 * Desarrollo — los prompts del motor de auto-desarrollo (cajas por tipo).
 */
import { Code2, GitBranch, Wrench } from "lucide-react";
import { useSearchParams } from "react-router-dom";

import { PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { GRUPOS_DESARROLLO, GRUPOS_HERRAMIENTAS } from "@/pages/maquina/fases";
import { PipelineUnificado } from "@/pages/maquina/PipelineUnificado";
import { PanelAgentes } from "@/pages/monitor/PanelAgentes";

type Proceso = "pipeline" | "herramientas" | "desarrollo";
const PROCESOS: readonly Proceso[] = ["pipeline", "herramientas", "desarrollo"];

const PESTANAS: PestanaSeccion[] = [
  { valor: "pipeline", etiqueta: "Pipeline", icono: GitBranch },
  { valor: "herramientas", etiqueta: "Herramientas", icono: Wrench },
  { valor: "desarrollo", etiqueta: "Desarrollo", icono: Code2 },
];

export default function Contexto() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const { marcaActiva } = useMarcaActiva();
  const [searchParams, setSearchParams] = useSearchParams();
  const param = searchParams.get("proceso");
  const proceso: Proceso = PROCESOS.includes(param as Proceso) ? (param as Proceso) : "pipeline";

  const cambiarProceso = (valor: string) =>
    setSearchParams(
      (prev) => {
        prev.set("proceso", valor);
        return prev;
      },
      { replace: true },
    );

  return (
    <>
      <PestanasSeccion pestanas={PESTANAS} activo={proceso} onSelect={cambiarProceso} />

      {proceso === "pipeline" && (
        <PipelineUnificado esAdmin={esAdmin} marcaActiva={marcaActiva} />
      )}

      {/* Herramientas: TODOS los agentes independientes (sin daemon). NO son un pipeline: se agrupan
          en CAJAS por tipo (sin conectores); clicar abre la SUBPÁGINA del agente, sin pop-up. */}
      {proceso === "herramientas" && (
        <div className="mt-4">
          <PanelAgentes grupos={GRUPOS_HERRAMIENTAS} esAdmin={esAdmin} proceso="herramientas" />
        </div>
      )}

      {/* Desarrollo: los prompts del motor de auto-desarrollo (clase editorial `desarrollo`). No es
          un pipeline ni un motor con interruptor; se presenta igual que Herramientas (cajas por tipo)
          y clicar abre la SUBPÁGINA del agente, sin pop-up. */}
      {proceso === "desarrollo" && (
        <div className="mt-4">
          <PanelAgentes grupos={GRUPOS_DESARROLLO} esAdmin={esAdmin} proceso="desarrollo" />
        </div>
      )}
    </>
  );
}
