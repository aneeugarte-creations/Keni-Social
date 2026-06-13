import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, ListChecks, Play, Sparkles } from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { PanelAjustes, PanelMaquinaContenido } from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";
import { PanelLanzar } from "@/pages/texto/PanelLanzar";

// Grupos del catálogo que son TUNING DE SISTEMA (jobs, limpieza, alertas) y gobiernan CÓMO se
// produce: se ajustan desde el drawer del propio cockpit (la misma sección que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

// Docs de la Biblioteca de cada etapa de PRODUCCIÓN: el lápiz «Editar prompt» de cada tarjeta de
// la tira abre el doc (`?doc=`) en la Biblioteca.
const DOC_POR_ETAPA = { copy: "prompt/copy", arte: "prompt/arte" } as const;

// El daemon del motor de PRODUCCIÓN (copy→arte→avance): «Barrer ahora» fuerza un barrido inmediato.
const DAEMON_PRODUCCION = "pipeline";

// Prompt de la etapa Copy: el lanzamiento manual del cockpit lo dispara contra una marca local.
const PROMPT_COPY = "prompt/copy";

/**
 * Cockpit de PRODUCCIÓN (`/maquina/produccion`): el motor que CONVIERTE noticias verificadas en
 * piezas publicables (copy → arte → avance). Tiene cuatro piezas:
 *
 *   1. TIRA del motor de producción: `PipelineEnVivo` recortado a Producción (`soloProceso`),
 *      o sea SOLO Copy (`KENI_PIPELINE_COPY`) y Arte (`KENI_PIPELINE_ARTE`) — cada etapa con su
 *      conteo vivo, su toggle físico, sus excepciones por marca y su «Editar prompt» (deep-link
 *      a la Biblioteca). En su cabecera vive el maestro global «Máquina» (`KENI_MAQUINA`), que
 *      gobierna AMBOS motores con la misma mutación `useGuardarAjuste`. Las etapas de
 *      Investigación (Selección/Validación) NO se pintan aquí: son del cockpit de Investigación.
 *   2. DRAWER de ajustes (⋮ → Ajustes): SOLO lo que gobierna cómo se produce copy/arte —
 *      «Máquina de contenido» (admisión + topes), «Conexiones · Imagen IA» (arte) y «Sistema»
 *      (automatismos + tuning). La sección «Investigación» y «Métricas (Metricool)» se fueron
 *      (Investigación → su cockpit; Metricool → la Cola compartida).
 *   3. INPUT manual: lanzar Copy contra una marca LOCAL (selector propio, sin depender del switch
 *      global) reutilizando `PanelLanzar`.
 *   4. OUTPUT: puente a los borradores generados → revisión (Feed / Producción).
 *
 * «Barrer ahora» (admin) fuerza un barrido del daemon de producción sin esperar a su intervalo.
 */
export default function CockpitProduccion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams] = useSearchParams();
  // Deep-link heredado del Monitor: `?tab=ajustes` abre el drawer de ajustes directamente.
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // ── Lanzamiento manual de Copy (selector de marca LOCAL). ──
  const { marcaActiva } = useMarcaActiva();
  const [lanzarAbierto, setLanzarAbierto] = React.useState(false);
  const [marcaLocal, setMarcaLocal] = React.useState<string>("");
  const marcasQuery = useQuery({
    queryKey: ["texto-marcas"],
    queryFn: ({ signal }) => api.marcasTexto(signal),
  });
  const areasQuery = useQuery({
    queryKey: ["texto-areas"],
    queryFn: ({ signal }) => api.areasTexto(signal),
  });
  // La salida del prompt de Copy decide el modo de lanzamiento (piezas → borradores por red).
  const docCopyQuery = useQuery({
    queryKey: ["texto-doc", PROMPT_COPY],
    queryFn: ({ signal }) => api.documento(PROMPT_COPY, signal),
  });
  const marcasLanzar = React.useMemo(
    () => marcasQuery.data?.marcas ?? [],
    [marcasQuery.data],
  );
  // Marca local por defecto: la activa si es concreta y válida; si no, la primera del catálogo.
  React.useEffect(() => {
    if (marcaLocal && marcasLanzar.some((m) => m.id === marcaLocal)) return;
    const inicial =
      (marcaActiva && marcasLanzar.some((m) => m.id === marcaActiva) ? marcaActiva : null) ??
      marcasLanzar[0]?.id ??
      "";
    if (inicial) setMarcaLocal(inicial);
  }, [marcaActiva, marcasLanzar, marcaLocal]);

  // ── Barrer ahora: fuerza un barrido del daemon de producción (admin). ──
  const barrer = useMutation({
    mutationFn: () => api.sistemaDaemonBarrer(DAEMON_PRODUCCION),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      void queryClient.invalidateQueries({ queryKey: ["actividad", "cola"] });
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const detalle = typeof e.cuerpo?.error === "string" ? e.cuerpo.error : null;
        toast.error(
          detalle ?? "El motor de producción está apagado por su ajuste: enciéndelo antes de barrer.",
        );
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  return (
    <>
      <TituloPagina titulo="Producción" icono={Sparkles} />
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Ajustes de producción"
          ajustesAbiertoInicial={abrirAjustes}
          ajustes={
            <>
              {/* Drawer de PRODUCCIÓN: solo ajustes que gobiernan cómo se produce copy/arte.
                  «Máquina de contenido» (admisión + topes) · «Conexiones · Imagen IA» (arte) ·
                  «Sistema» (automatismos + tuning). Investigación y Metricool ya NO viven aquí. */}
              <PanelMaquinaContenido />
              <SeccionImagen />
              <PanelAjustes
                grupos={GRUPOS_SISTEMA}
                titulo="Sistema"
                descripcion="Automatismos, jobs, limpiezas, alertas y esfuerzo de razonamiento; sin reinicio."
              />
            </>
          }
        >
          {esAdmin && (
            <ItemMenu
              icono={Play}
              disabled={barrer.isPending}
              onClick={() => barrer.mutate()}
            >
              Barrer ahora (producción)
            </ItemMenu>
          )}
          <ItemMenu
            icono={ListChecks}
            onClick={() => navigate("/maquina/cola?proceso=produccion")}
          >
            Ver workers (Producción)
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* 1. TIRA del motor de producción: solo Copy y Arte (PipelineEnVivo recortado). */}
      {cola.isPending ? (
        <Skeleton className="h-40 w-full rounded-xl" />
      ) : cola.data ? (
        <PipelineEnVivo
          cola={cola.data}
          esAdmin={esAdmin}
          soloProceso="produccion"
          docPorEtapa={DOC_POR_ETAPA}
        />
      ) : null}

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        {/* 3. INPUT: lanzamiento manual de Copy con selector de marca LOCAL. */}
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm">Generar copy a mano</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-4 pt-2">
            <p className="text-sm text-muted-foreground">
              Lanza la etapa de Copy sobre una nota o texto, contra la marca que elijas (sin
              depender del switch global). El copy se guarda como borradores en el Feed.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <SelectorMarca
                marcas={marcasLanzar}
                valor={marcaLocal}
                onCambio={setMarcaLocal}
                incluirTodas={false}
                ariaLabel="Marca para generar copy"
                className="w-full sm:w-[200px]"
                disabled={marcasQuery.isPending || marcasLanzar.length === 0}
              />
              <Button
                variant="brand"
                disabled={!marcaLocal}
                onClick={() => setLanzarAbierto(true)}
              >
                <Sparkles className="mr-1 h-4 w-4" aria-hidden="true" />
                Generar copy
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* 4. OUTPUT: puente a los borradores generados → revisión. */}
        <Card>
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm">Borradores generados → revisión</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 p-4 pt-2 text-sm">
            <p className="text-muted-foreground">
              Lo que produce el motor sale como borrador; el criterio humano decide qué se publica.
            </p>
            <div className="flex flex-col gap-1.5">
              <Link
                to="/operacion/feed/feed"
                className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-4 hover:underline"
              >
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                Feed de revisión (aprobar / rechazar)
              </Link>
              <Link
                to="/maquina/cola"
                className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-4 hover:underline"
              >
                <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                Actividad (runs y trabajos de la máquina) en Workers
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Lanzador de Copy (reusa PanelLanzar) con la marca LOCAL impuesta vía `marcaForzada`. */}
      <PanelLanzar
        promptId={PROMPT_COPY}
        salida={docCopyQuery.data?.documento.salida ?? "piezas"}
        marcas={marcasLanzar}
        areas={areasQuery.data?.areas ?? []}
        open={lanzarAbierto}
        onOpenChange={setLanzarAbierto}
        marcaForzada={marcaLocal}
      />
    </>
  );
}
