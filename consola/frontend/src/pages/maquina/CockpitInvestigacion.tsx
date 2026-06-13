import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ListChecks, Play, Search, SquarePen } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import Algoritmos from "@/pages/Algoritmos";
import Cobertura from "@/pages/Cobertura";
import ContenidosHub from "@/pages/ContenidosHub";
import Fuentes from "@/pages/Fuentes";
import { PanelInvestigacion } from "@/pages/configuracion/SeccionFuncionalidad";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";
import { ChipInvestigacion } from "@/pages/noticias/ChipInvestigacion";
import { RielInvestigacion } from "@/pages/noticias/RielInvestigacion";

/**
 * Cockpit de INVESTIGACIÓN (`/maquina/investigacion`): la ÚNICA CASA del control y el monitor
 * del motor proactivo (descubre y verifica noticias). Una página con cuatro pestañas
 * (`?seccion=`), cada una REUTILIZANDO una superficie ya existente sin reescribirla:
 *
 *   1. PIPELINE (núcleo): la tira `PipelineEnVivo` recortada a Investigación (`soloProceso`) —
 *      Selección + Validación, cada etapa con su switch físico, sus excepciones por marca y su
 *      «Editar prompt» (Validación → `prompt/validacion`). Debajo, el riel de ingesta en vivo
 *      (`RielInvestigacion`), el chip de la cola del loop (`ChipInvestigacion`) y un panel de
 *      enlaces a TODOS los prompts de investigación (deep-link `?doc=` a la Biblioteca).
 *   2. MESA DE REDACCIÓN (output): el pool segmentado por líneas con usar/descartar in-place
 *      (`Cobertura`). Es lo que el humano revisa; la ruta vieja `/datos/investigacion` redirige
 *      a esta pestaña.
 *   3. FUENTES (input): los canales que alimentan el pool (`Fuentes`).
 *   4. CONTENIDOS (output atemporal): el banco EVERGREEN —piezas educativas/curiosas que no
 *      caducan— (`ContenidosHub`). Antes era sub-ruta del hub Investigación (`/datos/investigacion/
 *      contenidos`); al consolidarse la nav, su única casa es esta pestaña del cockpit (la ruta
 *      vieja sigue viva para deep-links).
 *   5. ALGORITMOS (input): inteligencia de plataforma + trends + sugerencias (`Algoritmos`).
 *      La ruta vieja `/contenido/texto/algoritmos` redirige aquí (es un input de investigación,
 *      no una herramienta de la Biblioteca).
 *
 * El menú «⋮» (no en la pestaña Algoritmos, que aporta el suyo) ofrece: el drawer de ajustes de
 * investigación (`PanelInvestigacion`), «Barrer ahora» de cada daemon del motor (ingesta,
 * tendencias, fusión, algoritmos) y el puente a la Cola compartida prefiltrada.
 */

/** Pestañas del cockpit (clave `?seccion=`). Pipeline es la vista por defecto. */
type Seccion = "pipeline" | "mesa" | "fuentes" | "contenidos" | "algoritmos";
const SECCIONES: readonly Seccion[] = [
  "pipeline",
  "mesa",
  "fuentes",
  "contenidos",
  "algoritmos",
];

/** Docs de la Biblioteca por etapa de la tira: el lápiz «Editar prompt» de Validación abre su
 *  doc (`?doc=`). Selección es mecánica (sin prompt propio): no lleva lápiz. */
const DOC_POR_ETAPA = { validacion: "prompt/validacion" } as const;

/** Daemons del motor de INVESTIGACIÓN: «Barrer ahora» fuerza un barrido inmediato (admin). */
const DAEMONS: readonly { id: string; etiqueta: string }[] = [
  { id: "ingesta", etiqueta: "ingesta" },
  { id: "trends", etiqueta: "tendencias" },
  { id: "fusion", etiqueta: "fusión" },
  { id: "algoritmos", etiqueta: "algoritmos" },
];

/** Prompts del motor de investigación, accesibles in-place (deep-link a la Biblioteca). El de
 *  Validación vive además en la tira; aquí está el repertorio completo del loop. */
const PROMPTS: readonly { etiqueta: string; doc: string }[] = [
  { etiqueta: "Validación / verificación", doc: "prompt/validacion" },
  { etiqueta: "Fusión de historias", doc: "prompt/fusion" },
  { etiqueta: "Traducción", doc: "prompt/traduccion" },
  { etiqueta: "Línea editorial", doc: "prompt/editorial" },
  { etiqueta: "Clasificación por marca", doc: "prompt/clasificacion-marca" },
  { etiqueta: "Sugerencias editoriales", doc: "prompt/sugerencias" },
];

export default function CockpitInvestigacion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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

  // ── Barrer ahora: fuerza un barrido del daemon elegido del motor de investigación (admin). ──
  const barrer = useMutation({
    mutationFn: (daemon: string) => api.sistemaDaemonBarrer(daemon),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      void queryClient.invalidateQueries({ queryKey: ["actividad", "cola"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const detalle = typeof e.cuerpo?.error === "string" ? e.cuerpo.error : null;
        toast.error(
          detalle ??
            "El motor de investigación está apagado por su ajuste: enciéndelo antes de barrer.",
        );
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  return (
    <>
      <TituloPagina titulo="Investigación" icono={Search} />
      {/* El menú propio del cockpit se oculta en la pestaña Algoritmos, que aporta el suyo
          (Nueva fuente, Sugerencias…): así no se solapan dos «⋮» en la barra. */}
      {seccion !== "algoritmos" && (
        <AccionesPagina>
          <MenuAcciones ajustesTitulo="Ajustes de investigación" ajustes={<PanelInvestigacion />}>
            {esAdmin &&
              DAEMONS.map((d) => (
                <ItemMenu
                  key={d.id}
                  icono={Play}
                  disabled={barrer.isPending}
                  onClick={() => barrer.mutate(d.id)}
                >
                  Barrer {d.etiqueta}
                </ItemMenu>
              ))}
            <ItemMenu
              icono={ListChecks}
              onClick={() => navigate("/maquina/cola?proceso=investigacion")}
            >
              Ver workers (Investigación)
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}

      <Tabs value={seccion} onValueChange={cambiarSeccion}>
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="mesa">Mesa de redacción</TabsTrigger>
          <TabsTrigger value="fuentes">Fuentes</TabsTrigger>
          <TabsTrigger value="contenidos">Contenidos</TabsTrigger>
          <TabsTrigger value="algoritmos">Algoritmos</TabsTrigger>
        </TabsList>

        {/* 1. PIPELINE (núcleo): tira recortada + riel/chip de ingesta + prompts del loop. */}
        <TabsContent value="pipeline" className="space-y-4">
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

          <RielInvestigacion />
          <ChipInvestigacion />

          {/* Prompts in-place: el repertorio completo del motor (deep-link a la Biblioteca). */}
          <Card>
            <CardHeader className="p-4 pb-2">
              <CardTitle className="flex items-center gap-1.5 text-sm">
                <SquarePen className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Prompts de investigación
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 pt-2">
              <p className="mb-2 text-sm text-muted-foreground">
                Cada etapa del motor se edita en la Biblioteca. Los de Selección/Validación
                también tienen su lápiz en la tira de arriba.
              </p>
              <div className="flex flex-col gap-1.5">
                {PROMPTS.map((p) => (
                  <Link
                    key={p.doc}
                    to={`/contenido/texto/documentos?doc=${encodeURIComponent(p.doc)}`}
                    className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-foreground underline-offset-4 hover:underline"
                  >
                    <SquarePen className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                    {p.etiqueta}
                  </Link>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* 2. MESA DE REDACCIÓN (output): el pool con usar/descartar (Cobertura). */}
        <TabsContent value="mesa">
          <Cobertura />
        </TabsContent>

        {/* 3. FUENTES (input): los canales que alimentan el pool. */}
        <TabsContent value="fuentes">
          <Fuentes />
        </TabsContent>

        {/* 4. CONTENIDOS (output atemporal): el banco EVERGREEN (ContenidosHub). */}
        <TabsContent value="contenidos">
          <ContenidosHub />
        </TabsContent>

        {/* 5. ALGORITMOS (input): inteligencia de plataforma + trends + sugerencias. */}
        <TabsContent value="algoritmos">
          <Algoritmos />
        </TabsContent>
      </Tabs>
    </>
  );
}
