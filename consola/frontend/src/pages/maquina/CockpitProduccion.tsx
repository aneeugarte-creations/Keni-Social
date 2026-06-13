import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Image as ImageIcon, ListChecks, Pencil, Sparkles } from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { PanelAjustes, PanelMaquinaContenido } from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { PanelLanzarArte } from "@/pages/maquina/PanelLanzarArte";
import { PipelineEnVivo } from "@/pages/monitor/PipelineEnVivo";
import { PanelLanzar } from "@/pages/texto/PanelLanzar";

// Grupos del catálogo que son TUNING DE SISTEMA (jobs, limpieza, alertas) y gobiernan CÓMO se
// produce: se ajustan desde el drawer del propio cockpit (la misma sección que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

// Docs de la Biblioteca de cada etapa de PRODUCCIÓN: el lápiz «Editar prompt» de cada tarjeta de
// la tira los abre in-place (overlay), igual que el lanzamiento manual.
const DOC_POR_ETAPA = { copy: "prompt/copy", arte: "prompt/arte" } as const;

// Prompts de las etapas manuales (Copy/Arte): el lanzamiento del cockpit los dispara contra
// una marca LOCAL, y su lápiz abre el editor in-place sin salir de la página.
const PROMPT_COPY = "prompt/copy";
const PROMPT_ARTE = "prompt/arte";

/**
 * Cockpit de PRODUCCIÓN (`/maquina/produccion`): el motor que CONVIERTE noticias verificadas en
 * piezas publicables. Su FLUJO PROPIO es copy → arte → borradores → revisión, y la página lo
 * pinta en ese orden:
 *
 *   1. LANZAMIENTO MANUAL (acción principal): sobre una marca LOCAL (selector propio, sin
 *      depender del switch global) el equipo dispara «Generar copy» y «Generar arte». Cada
 *      acción deja editar su prompt de la Biblioteca in-place (`EditorPromptOverlay`).
 *   2. BORRADORES → REVISIÓN: estado VIVO con cuántas piezas de la marca esperan revisión
 *      (cola de aprobación) y el atajo directo al Feed de revisión.
 *   3. MOTOR de auto-producción (tira `PipelineEnVivo` recortado a Producción: solo Copy y
 *      Arte, cada etapa con su conteo vivo, su toggle y su «Editar prompt»). En su cabecera vive
 *      el maestro global «Máquina». Va al final: el manual es lo principal, no la tira.
 *   4. DRAWER de ajustes (⋮ → Ajustes): SOLO lo que gobierna cómo se produce copy/arte —
 *      «Máquina de contenido» (admisión + topes), «Conexiones · Imagen IA» (arte) y «Sistema»
 *      (automatismos + tuning). Sin presupuesto/economía (eso vive en Agentes).
 */
export default function CockpitProduccion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams] = useSearchParams();
  // Deep-link heredado del Monitor: `?tab=ajustes` abre el drawer de ajustes directamente.
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  const navigate = useNavigate();

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // ── Marca LOCAL del lanzamiento manual (selector propio, compartido por copy y arte). ──
  const { marcaActiva } = useMarcaActiva();
  const [marcaLocal, setMarcaLocal] = React.useState<string>("");
  const [copyAbierto, setCopyAbierto] = React.useState(false);
  const [arteAbierto, setArteAbierto] = React.useState(false);
  // Prompt que se está editando in-place (overlay), o `null`.
  const [promptEditando, setPromptEditando] = React.useState<string | null>(null);

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

  // ── Borradores → revisión: cuántas piezas de la marca esperan revisión (cola de aprobación). ──
  const aprobacion = useQuery({
    queryKey: ["aprobacion", "cola"],
    queryFn: ({ signal }) => api.colaAprobacion(signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const marcaNombre = marcasLanzar.find((m) => m.id === marcaLocal)?.nombre ?? "";
  const pendientesRevision = React.useMemo(
    () =>
      (aprobacion.data?.cola ?? []).filter((p) => !marcaLocal || p.marca === marcaLocal).length,
    [aprobacion.data, marcaLocal],
  );

  const sinMarca = marcasQuery.isPending || marcasLanzar.length === 0;

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
                  «Sistema» (automatismos + tuning). Sin presupuesto/economía (vive en Agentes). */}
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
          <ItemMenu
            icono={ListChecks}
            onClick={() => navigate("/maquina/cola?proceso=produccion")}
          >
            Ver agentes (Producción)
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* 1. LANZAMIENTO MANUAL (acción principal): copy → arte sobre una marca LOCAL. */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 p-4 pb-2">
          <CardTitle className="text-sm">Crear a mano</CardTitle>
          <SelectorMarca
            marcas={marcasLanzar}
            valor={marcaLocal}
            onCambio={setMarcaLocal}
            incluirTodas={false}
            ariaLabel="Marca para crear a mano"
            className="w-full sm:w-[220px]"
            disabled={sinMarca}
          />
        </CardHeader>
        <CardContent className="p-4 pt-2">
          <p className="mb-3 text-sm text-muted-foreground">
            Lanza copy o arte sobre la marca elegida (sin depender del switch global). El
            resultado se guarda como borradores; el criterio humano decide qué se publica.
          </p>
          <div className="grid gap-3 sm:grid-cols-2">
            {/* Copy */}
            <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium">Copy</p>
                <p className="text-xs text-muted-foreground">Texto por red desde una nota.</p>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <Button variant="brand" disabled={!marcaLocal} onClick={() => setCopyAbierto(true)}>
                  <Sparkles className="mr-1 h-4 w-4" aria-hidden="true" />
                  Generar copy
                </Button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  onClick={() => setPromptEditando(PROMPT_COPY)}
                >
                  <Pencil className="h-3 w-3" aria-hidden="true" /> Editar prompt
                </button>
              </div>
            </div>
            {/* Arte */}
            <div className="flex items-center justify-between gap-2 rounded-lg border border-border p-3">
              <div>
                <p className="text-sm font-medium">Arte</p>
                <p className="text-xs text-muted-foreground">Imágenes con IA (tiene coste).</p>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <Button variant="brand" disabled={!marcaLocal} onClick={() => setArteAbierto(true)}>
                  <ImageIcon className="mr-1 h-4 w-4" aria-hidden="true" />
                  Generar arte
                </Button>
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                  onClick={() => setPromptEditando(PROMPT_ARTE)}
                >
                  <Pencil className="h-3 w-3" aria-hidden="true" /> Editar prompt
                </button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 2. BORRADORES → REVISIÓN: estado vivo + atajo al Feed. */}
      <Card className="mt-4">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div>
            {aprobacion.isPending ? (
              <Skeleton className="h-6 w-48" />
            ) : (
              <p className="text-sm">
                <span className="text-lg font-semibold">{pendientesRevision}</span>{" "}
                {pendientesRevision === 1 ? "borrador pendiente" : "borradores pendientes"} de
                revisión
                {marcaNombre ? <span className="text-muted-foreground"> · {marcaNombre}</span> : null}
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              Lo que produce el motor sale como borrador; nada se publica sin criterio humano.
            </p>
          </div>
          <Button variant="outline" onClick={() => navigate("/operacion/feed/feed")}>
            Ir a revisión
            <ArrowRight className="ml-1 h-4 w-4" aria-hidden="true" />
          </Button>
        </CardContent>
      </Card>

      {/* 3. MOTOR de auto-producción: tira recortada a Producción (solo Copy y Arte). */}
      {cola.isPending ? (
        <Skeleton className="mt-6 h-40 w-full rounded-xl" />
      ) : cola.data ? (
        <div className="mt-6">
          <PipelineEnVivo
            cola={cola.data}
            esAdmin={esAdmin}
            soloProceso="produccion"
            docPorEtapa={DOC_POR_ETAPA}
          />
        </div>
      ) : null}

      {/* Lanzador de Copy (reusa PanelLanzar) con la marca LOCAL impuesta vía `marcaForzada`. */}
      <PanelLanzar
        promptId={PROMPT_COPY}
        salida={docCopyQuery.data?.documento.salida ?? "piezas"}
        marcas={marcasLanzar}
        areas={areasQuery.data?.areas ?? []}
        open={copyAbierto}
        onOpenChange={setCopyAbierto}
        marcaForzada={marcaLocal}
      />

      {/* Lanzador de Arte (rico): prompt editable, modelo, N alternativas y coste. */}
      <PanelLanzarArte
        marcas={marcasLanzar}
        open={arteAbierto}
        onOpenChange={setArteAbierto}
        marcaForzada={marcaLocal}
      />

      {/* Editor de prompt in-place (copy/arte) sin salir de la página. */}
      <EditorPromptOverlay
        docId={promptEditando}
        abierto={promptEditando !== null}
        onCerrar={() => setPromptEditando(null)}
      />
    </>
  );
}
