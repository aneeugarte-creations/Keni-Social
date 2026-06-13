import { useQuery } from "@tanstack/react-query";
import { ListChecks, Sparkles } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import {
  PanelAjustes,
  PanelInvestigacion,
  PanelMaquinaContenido,
} from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { SeccionMetricool } from "@/pages/configuracion/SeccionMetricool";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";

// Grupos del catálogo que son TUNING DE SISTEMA (jobs, limpieza, alertas): se ajustan
// desde el drawer de la máquina (la misma sección que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

/**
 * Cockpit de PRODUCCIÓN (`/maquina/produccion`) — ESQUELETO (fase 2A).
 *
 * El cockpit real (genera copy/arte: la máquina que produce contenido publicable) lo rellena
 * la fase 2C. De momento aloja temporalmente DOS piezas que se relocalizaron del antiguo
 * Monitor y que NO van en la Cola compartida: la TIRA DE ETAPAS (PipelineEnVivo, con su
 * toggle maestro y los switches por etapa) y el DRAWER DE AJUSTES de la máquina (Máquina de
 * contenido · Investigación · Conexiones · Sistema). Así no se pierde funcionalidad ni
 * deep-links (`?tab=ajustes`) hasta que 2B/2C las recoloquen en su sitio definitivo.
 */
export default function CockpitProduccion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams] = useSearchParams();
  // Deep-link heredado del Monitor: `?tab=ajustes` abre el drawer de ajustes directamente.
  const abrirAjustes = searchParams.get("tab") === "ajustes";

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  return (
    <>
      <TituloPagina titulo="Producción" icono={Sparkles} />
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Ajustes de la máquina"
          ajustesAbiertoInicial={abrirAjustes}
          ajustes={
            <>
              {/* Drawer ÚNICO de los ajustes de la máquina: Máquina de contenido ·
                  Investigación (motor de noticias) · Conexiones (imagen IA + Metricool) ·
                  Sistema (automatismos + tuning; el esfuerzo de razonamiento se pinta como
                  select del grupo `tuning`). Se aloja aquí temporalmente (fase 2A). */}
              <PanelMaquinaContenido />
              <PanelInvestigacion />
              <SeccionImagen />
              <SeccionMetricool />
              <PanelAjustes
                grupos={GRUPOS_SISTEMA}
                titulo="Sistema"
                descripcion="Automatismos, jobs, limpiezas, alertas y esfuerzo de razonamiento; sin reinicio."
              />
            </>
          }
        />
      </AccionesPagina>

      <Card className="mb-6 border-dashed">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm text-muted-foreground">
            Cockpit de Producción — en construcción (fase siguiente)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2 p-4 pt-0 text-sm text-muted-foreground">
          <p>
            Aquí vivirá el motor de PRODUCCIÓN (genera copy y arte). Por ahora aloja la tira de
            etapas y el drawer de ajustes de la máquina (⋯), relocalizados del antiguo Monitor.
          </p>
          <p>
            La vista global del worker/cola está en{" "}
            <Link
              className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-4 hover:underline"
              to="/maquina/cola?proceso=produccion"
            >
              <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
              Cola (filtrada a Producción)
            </Link>
            .
          </p>
        </CardContent>
      </Card>

      {/* PIPELINE EN VIVO: la tira de etapas de la máquina (Selección → Validación → Copy →
          Arte) con el toggle maestro y los switches por etapa. Relocalizada del Monitor;
          fase 2C decidirá su sitio definitivo dentro del cockpit. */}
      {cola.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : cola.data ? (
        <PipelineEnVivo cola={cola.data} esAdmin={esAdmin} />
      ) : null}
    </>
  );
}
