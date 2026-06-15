import { useQuery } from "@tanstack/react-query";
import { ListChecks, Search } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import Algoritmos from "@/pages/Algoritmos";
import Cobertura from "@/pages/Cobertura";
import ContenidosHub from "@/pages/ContenidosHub";
import Fuentes from "@/pages/Fuentes";
import { PanelInvestigacion } from "@/pages/configuracion/SeccionFuncionalidad";
import { RielInvestigacion } from "@/pages/noticias/RielInvestigacion";

/**
 * Cockpit de INVESTIGACIÓN (`/maquina/investigacion`): la casa del motor PROACTIVO que descubre
 * y verifica noticias. A diferencia de Producción (que se lanza a mano), Investigación es un
 * flujo continuo —recolectar → agrupar → admitir → verificar → mesa de redacción— y el cockpit
 * lo ordena de ENTRADA a SALIDA en pestañas agrupadas (`?seccion=`), cada una REUTILIZANDO una
 * superficie ya existente sin reescribirla:
 *
 *   ENTRADA
 *     · FUENTES (`Fuentes`): los canales que alimentan el pool.
 *     · ALGORITMOS (`Algoritmos`): inteligencia de plataforma + trends. La ruta
 *       vieja `/contenido/texto/algoritmos` redirige aquí.
 *   PROCESO
 *     · PIPELINE (núcleo): UN solo proceso en dos fases. Antes (en el flujo), la línea INFORMATIVA de
 *       el pipeline CONSOLIDADO (`RielInvestigacion` sobre `PanelPipeline`): TODAS las fases del
 *       tramo aguas arriba como tarjetas grandes en orden, cada una con su icono, switch (on/off),
 *       conteos de cola y «Editar prompt»/«Excepciones» en el menú; el maestro «Máquina» en la
 *       cabecera. El repertorio completo de prompts vive en la Biblioteca (Texto · Documentos).
 *   SALIDA
 *     · MESA DE REDACCIÓN (`Cobertura`): el pool segmentado por líneas con usar/descartar; lo que
 *       el humano revisa. La ruta vieja `/datos/investigacion` redirige aquí.
 *     · CONTENIDOS (`ContenidosHub`): el banco EVERGREEN —piezas que no caducan—.
 *
 * El menú «⋮» (oculto en Algoritmos, que aporta el suyo) ofrece los ajustes del motor
 * (`PanelInvestigacion`) y un puente a Agentes prefiltrado. Los daemons (barridos manuales) viven
 * ahora en la página Agentes, no aquí.
 */

/** Pestañas del cockpit (clave `?seccion=`), en orden de flujo entrada→proceso→salida. */
type Seccion = "fuentes" | "algoritmos" | "pipeline" | "mesa" | "contenidos";
const SECCIONES: readonly Seccion[] = [
  "fuentes",
  "algoritmos",
  "pipeline",
  "mesa",
  "contenidos",
];

export default function CockpitInvestigacion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const seccionParam = searchParams.get("seccion");
  const seccion: Seccion = SECCIONES.includes(seccionParam as Seccion)
    ? (seccionParam as Seccion)
    : "pipeline";
  const cambiarSeccion = (valor: string) => {
    setSearchParams(
      (prev) => {
        prev.set("seccion", valor);
        return prev;
      },
      { replace: true },
    );
  };

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  return (
    <>
      <TituloPagina titulo="Investigación" icono={Search} />
      {/* El menú propio del cockpit se oculta en la pestaña Algoritmos, que aporta el suyo
          (Refrescar…): así no se solapan dos «⋮» en la barra. */}
      {seccion !== "algoritmos" && (
        <AccionesPagina>
          <MenuAcciones ajustesTitulo="Ajustes de investigación" ajustes={<PanelInvestigacion />}>
            <ItemMenu icono={ListChecks} onClick={() => navigate("/maquina/cola")}>
              Ver agentes
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}

      <Tabs value={seccion} onValueChange={cambiarSeccion}>
        {/* Pestañas agrupadas por fase del flujo: Entrada → Proceso → Salida. */}
        <TabsList className="h-auto flex-wrap gap-y-1">
          <span className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Entrada
          </span>
          <TabsTrigger value="fuentes">Fuentes</TabsTrigger>
          <TabsTrigger value="algoritmos">Algoritmos</TabsTrigger>
          <span className="mx-1 hidden h-4 w-px bg-border sm:block" aria-hidden="true" />
          <span className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Proceso
          </span>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <span className="mx-1 hidden h-4 w-px bg-border sm:block" aria-hidden="true" />
          <span className="px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Salida
          </span>
          <TabsTrigger value="mesa">Mesa de redacción</TabsTrigger>
          <TabsTrigger value="contenidos">Contenidos</TabsTrigger>
        </TabsList>

        {/* ENTRADA · FUENTES: los canales que alimentan el pool. */}
        <TabsContent value="fuentes">
          <Fuentes />
        </TabsContent>

        {/* ENTRADA · ALGORITMOS: inteligencia de plataforma + trends. */}
        <TabsContent value="algoritmos">
          <Algoritmos />
        </TabsContent>

        {/* PROCESO · PIPELINE (núcleo): el pipeline CONSOLIDADO — todas las fases del tramo aguas
            arriba como tarjetas grandes en orden, cada una con su icono, switch (on/off), conteos
            de cola, «Editar prompt» y excepciones; el maestro «Máquina» en la cabecera. */}
        <TabsContent value="pipeline">
          <RielInvestigacion cola={cola.data} esAdmin={esAdmin} />
        </TabsContent>

        {/* SALIDA · MESA DE REDACCIÓN: el pool con usar/descartar (Cobertura). */}
        <TabsContent value="mesa">
          <Cobertura />
        </TabsContent>

        {/* SALIDA · CONTENIDOS: el banco EVERGREEN (ContenidosHub). */}
        <TabsContent value="contenidos">
          <ContenidosHub />
        </TabsContent>
      </Tabs>
    </>
  );
}
