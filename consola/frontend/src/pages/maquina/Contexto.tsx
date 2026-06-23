/**
 * Contexto (`/maquina/contexto`) — la página ÚNICA de la máquina: el pipeline de cada motor ES la
 * estructura de la página. Tres pestañas: Investigación y Producción (los motores, con sus fases
 * desplegables, interruptor on/off y logs en vivo) y Herramientas (TODOS los agentes independientes
 * que se lanzan a mano: material recibido del equipo, ideación, crítica y envoltorios, en cajas por
 * tipo). De cada fase cuelga su prompt y el contexto editorial que inyecta. Sustituye a los dos
 * cockpits de pipeline y a la antigua página plana «Todos los documentos»: cada prompt se alcanza por
 * su etapa, y los editoriales por la pestaña «Contexto» del propio prompt.
 *
 * El menú «⋮» (solo en los motores) trae los ajustes del motor de la pestaña activa. Bajo el
 * pipeline, los daemons clase=maquina del motor («Servicios», solo admin).
 */
import { useQuery } from "@tanstack/react-query";
import { Code2, Factory, Telescope, Wrench } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, PestanasSeccion, type PestanaSeccion } from "@/components/layout/encabezado";
import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import {
  PanelAjustes,
  PanelInvestigacion,
  PanelMaquinaPublicacion,
} from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import {
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  GRUPOS_DESARROLLO,
  GRUPOS_HERRAMIENTAS,
  MAESTRO_INVESTIGACION,
  MAESTRO_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  slugFase,
} from "@/pages/maquina/fases";
import { SeccionCadenaAprobacion } from "@/pages/maquina/SeccionCadenaAprobacion";
import { ServiciosMaquina } from "@/pages/maquina/ServiciosMaquina";
import { PanelAgentes } from "@/pages/monitor/PanelAgentes";
import {
  ControlesMaquina,
  type FasePipeline,
  PanelPipeline,
} from "@/pages/monitor/PanelPipeline";

type Proceso = "investigacion" | "produccion" | "herramientas" | "desarrollo";
const PROCESOS: readonly Proceso[] = [
  "investigacion",
  "produccion",
  "herramientas",
  "desarrollo",
];
/** Sub-secciones de la máquina (clave `?proceso=`). La subnav vive en el topbar (como Métricas). */
const PESTANAS: PestanaSeccion[] = [
  { valor: "investigacion", etiqueta: "Investigación", icono: Telescope },
  { valor: "produccion", etiqueta: "Producción", icono: Factory },
  { valor: "herramientas", etiqueta: "Herramientas", icono: Wrench },
  { valor: "desarrollo", etiqueta: "Desarrollo", icono: Code2 },
];

// Grupos del catálogo que gobiernan CÓMO se produce (jobs, limpieza, alertas): se ajustan desde el
// drawer del propio Contexto (la misma página que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

export default function Contexto() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const { marcaActiva } = useMarcaActiva();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const param = searchParams.get("proceso");
  const proceso: Proceso = PROCESOS.includes(param as Proceso) ? (param as Proceso) : "investigacion";
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  // Solo los dos MOTORES tienen ajustes/servicios/cola; Herramientas es un catálogo de agentes
  // independientes que se lanzan a mano (sin daemon).
  const esMotor = proceso === "investigacion" || proceso === "produccion";
  const cambiarProceso = (valor: string) =>
    setSearchParams(
      (prev) => {
        prev.set("proceso", valor);
        return prev;
      },
      { replace: true },
    );

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
    enabled: esMotor,
  });

  // El drawer de ⋮ depende de la pestaña activa: ajustes del motor que se está mirando.
  const ajustes =
    proceso === "produccion" ? (
      <>
        <PanelMaquinaPublicacion />
        <SeccionImagen />
        <PanelAjustes
          grupos={GRUPOS_SISTEMA}
          titulo="Sistema"
          descripcion="Automatismos, jobs, limpiezas, alertas y esfuerzo de razonamiento; sin reinicio."
        />
      </>
    ) : (
      <PanelInvestigacion />
    );

  return (
    <>
      <PestanasSeccion pestanas={PESTANAS} activo={proceso} onSelect={cambiarProceso} />
      {/* El control de la máquina (maestro del proceso activo + interruptor general) y, en los
          motores, los ajustes «⋮» viven en el flanco de acciones del topbar —como el selector de
          Métricas—, no en una fila dentro del cuerpo. */}
      <AccionesPagina>
        <div className="flex items-center gap-2">
          <ControlesMaquina
            claveMaestro={
              proceso === "investigacion"
                ? MAESTRO_INVESTIGACION
                : proceso === "produccion"
                  ? MAESTRO_PRODUCCION
                  : undefined
            }
            esAdmin={esAdmin}
            marcaActiva={marcaActiva}
          />
          {esMotor && (
            <MenuAcciones
              ajustesTitulo={proceso === "produccion" ? "Ajustes de producción" : "Ajustes de investigación"}
              ajustesAbiertoInicial={abrirAjustes}
              ajustes={ajustes}
            />
          )}
        </div>
      </AccionesPagina>

      {proceso === "investigacion" && (
        <div className="mt-4">
          <PanelPipeline
            fases={FASES_INVESTIGACION}
            queuePorTipo={QUEUE_INVESTIGACION}
            admisionEn="verificar"
            cola={cola.data}
            esAdmin={esAdmin}
            claveMaestro={MAESTRO_INVESTIGACION}
            marcaActiva={marcaActiva}
            onAbrirFase={(fase: FasePipeline) =>
              navigate(`/maquina/contexto/investigacion/${slugFase(fase.nombre)}`)
            }
          />
          {esAdmin && <ServiciosMaquina motor="investigacion" />}
        </div>
      )}

      {proceso === "produccion" && (
        <div className="mt-4">
          <PanelPipeline
            fases={FASES_PRODUCCION}
            queuePorTipo={QUEUE_PRODUCCION}
            cola={cola.data}
            esAdmin={esAdmin}
            claveMaestro={MAESTRO_PRODUCCION}
            marcaActiva={marcaActiva}
            onAbrirFase={(fase: FasePipeline) =>
              navigate(`/maquina/contexto/produccion/${slugFase(fase.nombre)}`)
            }
          />
          {/* El umbral de likes vive en la sección «Cadena de aprobación» del pipeline (justo
              tras la Crítica), no al final: es parte de esa cadena, no un servicio. */}
          {esAdmin && <SeccionCadenaAprobacion marcaActiva={marcaActiva} />}
          {esAdmin && <ServiciosMaquina motor="produccion" />}
        </div>
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
