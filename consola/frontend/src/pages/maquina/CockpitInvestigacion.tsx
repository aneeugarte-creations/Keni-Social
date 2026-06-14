import { useQuery } from "@tanstack/react-query";
import { ListChecks, Search, SquarePen } from "lucide-react";
import { useNavigate, useSearchParams } from "react-router-dom";
import * as React from "react";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import Algoritmos from "@/pages/Algoritmos";
import Cobertura from "@/pages/Cobertura";
import ContenidosHub from "@/pages/ContenidosHub";
import Fuentes from "@/pages/Fuentes";
import { PanelInvestigacion } from "@/pages/configuracion/SeccionFuncionalidad";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";
import { RielInvestigacion } from "@/pages/noticias/RielInvestigacion";

/**
 * Cockpit de INVESTIGACIÓN (`/maquina/investigacion`): la casa del motor PROACTIVO que descubre
 * y verifica noticias. A diferencia de Producción (que se lanza a mano), Investigación es un
 * flujo continuo —descubrir → agrupar → seleccionar → validar → mesa de redacción— y el cockpit
 * lo ordena de ENTRADA a SALIDA en pestañas agrupadas (`?seccion=`), cada una REUTILIZANDO una
 * superficie ya existente sin reescribirla:
 *
 *   ENTRADA
 *     · FUENTES (`Fuentes`): los canales que alimentan el pool.
 *     · ALGORITMOS (`Algoritmos`): inteligencia de plataforma + trends. La ruta
 *       vieja `/contenido/texto/algoritmos` redirige aquí.
 *   PROCESO
 *     · PIPELINE (núcleo): UN solo proceso en dos tramos. Aguas arriba, el riel INFORMATIVO de
 *       ingesta (`RielInvestigacion`: la máquina descubre/agrupa/rankea sola). En el control,
 *       la tira `PipelineEnVivo` recortada a Investigación (`soloProceso`) —Selección + Validación,
 *       cada etapa con su switch y su «Editar prompt» en overlay—. Debajo, el índice editable de
 *       TODOS los prompts del motor (también in-place, vía `EditorPromptOverlay`).
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

/** Docs de la Biblioteca por etapa de la tira de control: el lápiz «Editar prompt» de Validación
 *  abre su doc en overlay. Selección es mecánica (sin prompt propio): no lleva lápiz. */
const DOC_POR_ETAPA = { validacion: "prompt/validacion" } as const;

/** Prompts del motor de investigación, editables IN-PLACE (overlay). El de Validación vive además
 *  en la tira de control y varios tienen su lápiz en el riel; aquí está el repertorio completo. */
const PROMPTS: readonly { etiqueta: string; doc: string }[] = [
  { etiqueta: "Validación / verificación", doc: "prompt/validacion" },
  { etiqueta: "Fusión de historias", doc: "prompt/fusion" },
  { etiqueta: "Traducción", doc: "prompt/traduccion" },
  { etiqueta: "Línea editorial", doc: "prompt/editorial" },
  { etiqueta: "Clasificación por marca", doc: "prompt/clasificacion-marca" },
];

export default function CockpitInvestigacion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Prompt abierto en el overlay «Editar prompt» del índice de prompts (in-place).
  const [docAbierto, setDocAbierto] = React.useState<string | null>(null);

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
        {/* Pestañas agrupadas por tramo del flujo: Entrada → Proceso → Salida. */}
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

        {/* PROCESO · PIPELINE (núcleo): UN proceso en dos tramos —aguas arriba (informativo) y
            control (Selección/Validación)— más el índice editable de prompts. */}
        <TabsContent value="pipeline" className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Un solo proceso en dos tramos: <strong className="font-medium text-foreground">aguas
            arriba</strong> la máquina descubre, agrupa y ordena sola; en el{" "}
            <strong className="font-medium text-foreground">control</strong> tú decides qué pasa
            por Selección y Validación.
          </p>

          {/* Tramo 1 · aguas arriba (automático, informativo). */}
          <RielInvestigacion />

          {/* Tramo 2 · control (Selección + Validación), con switches y «Editar prompt». */}
          <section className="space-y-2">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Control · tú decides
            </h3>
            <p className="text-xs text-muted-foreground">
              Selección: qué entra al pool. Validación: el embudo de control de calidad que
              contrasta fuentes antes de la mesa.
            </p>
            {cola.isPending ? (
              <Skeleton className="h-40 w-full rounded-xl" />
            ) : cola.data ? (
              <PipelineEnVivo
                cola={cola.data}
                esAdmin={esAdmin}
                soloProceso="investigacion"
                docPorEtapa={DOC_POR_ETAPA}
              />
            ) : null}
          </section>

          {/* Índice de prompts del motor, editable IN-PLACE (overlay, sin salir del cockpit). */}
          {esAdmin && (
            <Card>
              <CardHeader className="p-4 pb-2">
                <CardTitle className="flex items-center gap-1.5 text-sm">
                  <SquarePen className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Prompts del motor
                </CardTitle>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <p className="mb-2 text-sm text-muted-foreground">
                  Edita cualquier prompt sin salir de aquí.
                </p>
                <div className="flex flex-col gap-1.5">
                  {PROMPTS.map((p) => (
                    <button
                      key={p.doc}
                      type="button"
                      onClick={() => setDocAbierto(p.doc)}
                      className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline"
                    >
                      <SquarePen className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                      {p.etiqueta}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
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

      <EditorPromptOverlay
        docId={docAbierto}
        abierto={docAbierto !== null}
        onCerrar={() => setDocAbierto(null)}
      />
    </>
  );
}
