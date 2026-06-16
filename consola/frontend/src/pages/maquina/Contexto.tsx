/**
 * Contexto (`/maquina/contexto`) — la página ÚNICA de la máquina: el pipeline de cada motor ES la
 * estructura de la página. Dos pestañas, Investigación y Producción; en cada una, las fases en orden
 * de flujo como filas desplegables. De cada fase cuelga TODO lo suyo —su prompt, el contexto editorial
 * que inyecta y sus logs en vivo— y su interruptor on/off. Sustituye a los dos cockpits de pipeline y
 * a la antigua Biblioteca/Texto: aquí se ve qué SABE y qué HACE cada máquina, en un solo sitio.
 *
 * El menú «⋮» trae los ajustes del motor de la pestaña activa (Investigación: ajustes del motor;
 * Producción: máquina de contenido + imagen IA + sistema) y un puente a Agentes (cómputo). Bajo el
 * pipeline, los daemons clase=maquina del motor («Servicios», solo admin).
 */
import { useQuery } from "@tanstack/react-query";
import { FileText, Layers, ListChecks } from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { BibliotecaDocumentos } from "@/pages/maquina/BibliotecaDocumentos";
import {
  PanelAjustes,
  PanelInvestigacion,
  PanelMaquinaContenido,
} from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import {
  FASES_INVESTIGACION,
  FASES_PRODUCCION,
  QUEUE_INVESTIGACION,
  QUEUE_PRODUCCION,
  slugFase,
} from "@/pages/maquina/fases";
import { ServiciosMaquina } from "@/pages/maquina/ServiciosMaquina";
import { type FasePipeline, PanelPipeline } from "@/pages/monitor/PanelPipeline";

type Proceso = "investigacion" | "produccion";

// Grupos del catálogo que gobiernan CÓMO se produce (jobs, limpieza, alertas): se ajustan desde el
// drawer del propio Contexto (la misma página que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

export default function Contexto() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const proceso: Proceso =
    searchParams.get("proceso") === "produccion" ? "produccion" : "investigacion";
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  const [bibliotecaAbierta, setBibliotecaAbierta] = React.useState(false);
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
  });

  // El drawer de ⋮ depende de la pestaña activa: ajustes del motor que se está mirando.
  const ajustes =
    proceso === "produccion" ? (
      <>
        <PanelMaquinaContenido />
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
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo={proceso === "produccion" ? "Ajustes de producción" : "Ajustes de investigación"}
          ajustesAbiertoInicial={abrirAjustes}
          ajustes={ajustes}
        >
          <ItemMenu icono={FileText} onClick={() => setBibliotecaAbierta(true)}>
            Todos los documentos
          </ItemMenu>
          <ItemMenu
            icono={ListChecks}
            onClick={() => navigate(`/maquina/computo?proceso=${proceso}`)}
          >
            Ver cómputo
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      <Tabs value={proceso} onValueChange={cambiarProceso}>
        <TabsList>
          <TabsTrigger value="investigacion">Investigación</TabsTrigger>
          <TabsTrigger value="produccion">Producción</TabsTrigger>
        </TabsList>

        <TabsContent value="investigacion" className="mt-4">
          <PanelPipeline
            titulo="Investigación — descubre y verifica noticias"
            fases={FASES_INVESTIGACION}
            queuePorTipo={QUEUE_INVESTIGACION}
            admisionEn="verificar"
            cola={cola.data}
            esAdmin={esAdmin}
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
            onAbrirFase={(fase: FasePipeline) =>
              navigate(`/maquina/contexto/produccion/${slugFase(fase.nombre)}`)
            }
          />
          {esAdmin && <ServiciosMaquina motor="produccion" />}
        </TabsContent>
      </Tabs>

      <BibliotecaDocumentos
        abierto={bibliotecaAbierta}
        onCerrar={() => setBibliotecaAbierta(false)}
      />
    </>
  );
}
