/**
 * Contexto (`/maquina/contexto`) — la página ÚNICA de la máquina: el pipeline de cada motor ES la
 * estructura de la página. Cuatro pestañas: Investigación y Producción (los motores, con sus fases
 * desplegables, interruptor on/off y logs en vivo), Importación (las herramientas de material
 * recibido del equipo) y Herramientas (prompts independientes: crítica, hashtags, envoltorios,
 * asistente). De cada fase cuelga su prompt y el contexto editorial que inyecta. Sustituye a los dos
 * cockpits de pipeline y a la antigua página plana «Todos los documentos»: cada prompt se alcanza por
 * su etapa, y los editoriales por la pestaña «Contexto» del propio prompt.
 *
 * El menú «⋮» (solo en los motores) trae los ajustes del motor de la pestaña activa y un puente a
 * Agentes (cómputo). Bajo el pipeline, los daemons clase=maquina del motor («Servicios», solo admin).
 */
import { useQuery } from "@tanstack/react-query";
import { Layers, ListChecks } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  FASES_HERRAMIENTAS,
  FASES_IMPORTACION,
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  MAESTRO_INVESTIGACION,
  MAESTRO_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  QUEUE_VACIA,
  slugFase,
} from "@/pages/maquina/fases";
import { ServiciosMaquina } from "@/pages/maquina/ServiciosMaquina";
import { type FasePipeline, PanelPipeline } from "@/pages/monitor/PanelPipeline";

type Proceso = "investigacion" | "produccion" | "importacion" | "herramientas";
const PROCESOS: readonly Proceso[] = ["investigacion", "produccion", "importacion", "herramientas"];

// Grupos del catálogo que gobiernan CÓMO se produce (jobs, limpieza, alertas): se ajustan desde el
// drawer del propio Contexto (la misma página que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

export default function Contexto() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const param = searchParams.get("proceso");
  const proceso: Proceso = PROCESOS.includes(param as Proceso) ? (param as Proceso) : "investigacion";
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  // Solo los dos MOTORES tienen ajustes/servicios/cola; Importación y Herramientas son catálogos de
  // prompts que se lanzan a mano (sin daemon).
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
      <TituloPagina titulo="Contexto" icono={Layers} />
      {esMotor ? (
        <AccionesPagina>
          <MenuAcciones
            ajustesTitulo={proceso === "produccion" ? "Ajustes de producción" : "Ajustes de investigación"}
            ajustesAbiertoInicial={abrirAjustes}
            ajustes={ajustes}
          >
            <ItemMenu
              icono={ListChecks}
              onClick={() => navigate(`/maquina/computo?proceso=${proceso}`)}
            >
              Ver cómputo
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      ) : null}

      <Tabs value={proceso} onValueChange={cambiarProceso}>
        <TabsList>
          <TabsTrigger value="investigacion">Investigación</TabsTrigger>
          <TabsTrigger value="produccion">Producción</TabsTrigger>
          <TabsTrigger value="importacion">Importación</TabsTrigger>
          <TabsTrigger value="herramientas">Herramientas</TabsTrigger>
        </TabsList>

        <TabsContent value="investigacion" className="mt-4">
          <PanelPipeline
            titulo="Investigación — descubre y verifica noticias"
            fases={FASES_INVESTIGACION}
            queuePorTipo={QUEUE_INVESTIGACION}
            admisionEn="verificar"
            cola={cola.data}
            esAdmin={esAdmin}
            claveMaestro={MAESTRO_INVESTIGACION}
            onAbrirFase={(fase: FasePipeline) =>
              navigate(`/maquina/contexto/investigacion/${slugFase(fase.nombre)}`)
            }
          />
          {esAdmin && <ServiciosMaquina motor="investigacion" />}
        </TabsContent>

        <TabsContent value="produccion" className="mt-4">
          <PanelPipeline
            titulo="Producción — convierte noticias verificadas en piezas"
            fases={FASES_PRODUCCION}
            queuePorTipo={QUEUE_PRODUCCION}
            cola={cola.data}
            esAdmin={esAdmin}
            claveMaestro={MAESTRO_PRODUCCION}
            onAbrirFase={(fase: FasePipeline) =>
              navigate(`/maquina/contexto/produccion/${slugFase(fase.nombre)}`)
            }
          />
          {esAdmin && <ServiciosMaquina motor="produccion" />}
        </TabsContent>

        {/* Importación y Herramientas: catálogos de prompts independientes (sin daemon). Mismo diseño
            de filas; clicar abre el prompt en el editor (overlay), sin subpágina de fase. */}
        <TabsContent value="importacion" className="mt-4">
          <PanelPipeline
            titulo="Importación — material recibido del equipo"
            fases={FASES_IMPORTACION}
            queuePorTipo={QUEUE_VACIA}
            esAdmin={esAdmin}
          />
        </TabsContent>

        <TabsContent value="herramientas" className="mt-4">
          <PanelPipeline
            titulo="Herramientas — prompts de apoyo (no son etapa de la máquina)"
            fases={FASES_HERRAMIENTAS}
            queuePorTipo={QUEUE_VACIA}
            esAdmin={esAdmin}
          />
        </TabsContent>
      </Tabs>
    </>
  );
}
