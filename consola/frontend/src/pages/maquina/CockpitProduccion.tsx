import { useQuery } from "@tanstack/react-query";
import { ListChecks, Pencil, Wand2 } from "lucide-react";
import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { TarjetaAccion } from "@/components/comunes/TarjetaAccion";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api } from "@/lib/api";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { PanelAjustes, PanelMaquinaContenido } from "@/pages/configuracion/SeccionFuncionalidad";
import { SeccionImagen } from "@/pages/configuracion/SeccionImagen";
import { SeccionPostproxy } from "@/pages/configuracion/SeccionPostproxy";
import { PanelLanzarArte } from "@/pages/maquina/PanelLanzarArte";
import { PanelPipeline, type FasePipeline } from "@/pages/monitor/PanelPipeline";
import { SeccionDaemons } from "@/pages/sistema/SeccionDaemons";
import { PanelLanzar } from "@/pages/texto/PanelLanzar";

// Grupos del catálogo que son TUNING DE SISTEMA (jobs, limpieza, alertas) y gobiernan CÓMO se
// produce: se ajustan desde el drawer del propio cockpit (la misma sección que vigila sus efectos).
const GRUPOS_SISTEMA = ["automatismos_generales", "tuning"] as const;

/** Maestro VIRTUAL de Producción: respaldo de las fases sin flag físico propio en el catálogo. */
const MAESTRO_PRODUCCION = "KENI_PRODUCCION";

// Las fases del MOTOR de auto-producción, en orden de flujo. Mismas tarjetas que Investigación
// (panel `PanelPipeline`): icono, switch (on/off), conteos de cola y «Editar prompt».
const FASES_PRODUCCION: readonly FasePipeline[] = [
  {
    nombre: "Redactar",
    es_ia: true,
    claves: ["KENI_PIPELINE_REDACTAR", MAESTRO_PRODUCCION],
    ayuda: "Redacta el copy que convierte la noticia verificada en pieza",
    doc: "prompt/redactar",
    queue: "redactar",
    excepciones: {
      base: MAESTRO_PRODUCCION,
      nota: "Apagar «Producción» en una marca la deja sin copy automático.",
    },
  },
  {
    nombre: "Revisar",
    es_ia: false,
    claves: ["KENI_PIPELINE_REVISAR", MAESTRO_PRODUCCION],
    ayuda: "Verifica la voz y la calidad del copy antes de avanzar",
    heredada: "con Producción",
  },
  {
    nombre: "Ilustrar",
    es_ia: true,
    claves: ["KENI_PIPELINE_ILUSTRAR", MAESTRO_PRODUCCION],
    ayuda: "Genera imagen por IA para los temas con copy y sin imagen",
    doc: "prompt/ilustrar",
    queue: "ilustrar",
    excepciones: {
      base: "KENI_PIPELINE_ILUSTRAR",
      nota: "Apagar «Ilustrar» en una marca la deja sin imagen por IA.",
    },
  },
  {
    nombre: "Aprobar",
    es_ia: false,
    claves: ["KENI_AUTO_PREAPROBACION"],
    ayuda: "El OK humano antes de programar la pieza",
    heredada: "el switch auto-aprueba las de bajo riesgo",
  },
  {
    nombre: "Publicar",
    es_ia: false,
    claves: ["KENI_PUBLICAR_REAL"],
    ayuda: "Postea de verdad en el programador (apagado: simulación)",
    excepciones: {
      base: "KENI_PUBLICAR_REAL",
      nota: "Apagar «Publicar» en una marca la deja en simulación (sin postear).",
    },
  },
];

/** Tipo de job → fase con cola: la redacción (copy/autogen) y la imagen IA. */
const QUEUE_POR_TIPO_PRODUCCION: Record<string, string> = {
  copy: "redactar",
  autogen: "redactar",
  imagen: "ilustrar",
};

// Prompts de las etapas manuales (Redactar/Ilustrar): el lanzamiento del cockpit los dispara
// contra una marca LOCAL, y su lápiz abre el editor in-place sin salir de la página.
const PROMPT_REDACTAR = "prompt/redactar";
const PROMPT_ILUSTRAR = "prompt/ilustrar";

/**
 * Cockpit de PRODUCCIÓN (`/maquina/produccion`): el motor que CONVIERTE noticias verificadas en
 * piezas publicables. Su FLUJO PROPIO es redactar → ilustrar → borradores → revisión, y la página
 * lo pinta en ese orden:
 *
 *   1. LANZAMIENTO MANUAL (acción principal): dos tarjetas (Redactar / Ilustrar) sobre la marca del
 *      switch GLOBAL. Click izquierdo abre el popup de lanzar; click derecho / long-press
 *      edita su prompt de la Biblioteca in-place (`EditorPromptOverlay`), también accesible
 *      desde un botón dentro del popup.
 *   2. BORRADORES → REVISIÓN: estado VIVO con cuántas piezas de la marca esperan revisión
 *      (cola de aprobación) y el atajo directo al Feed de revisión.
 *   3. MOTOR de auto-producción (panel `PanelPipeline` con TODAS las fases de Producción —Redactar ·
 *      Revisar · Ilustrar · Aprobar · Publicar—, cada una con su icono, switch, conteo vivo y
 *      «Editar prompt»). En su cabecera vive el maestro global «Máquina». Va al final: el manual es
 *      lo principal, no la tira.
 *   4. DRAWER de ajustes (⋮ → Ajustes): SOLO lo que gobierna cómo se redacta e ilustra —
 *      «Máquina de contenido» (admisión + topes), «Conexiones · Imagen IA» (imagen) y «Sistema»
 *      (automatismos + tuning). Sin presupuesto/economía (eso vive en Agentes).
 */
export default function CockpitProduccion() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams] = useSearchParams();
  const abrirAjustes = searchParams.get("tab") === "ajustes";
  const navigate = useNavigate();

  const cola = useQuery({
    queryKey: ["actividad", "cola", "todas"],
    queryFn: ({ signal }) => api.cola({}, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });

  // ── Lanzamiento manual: la marca la manda SIEMPRE el switch global (sin selector propio). ──
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const [redactarAbierto, setRedactarAbierto] = React.useState(false);
  const [ilustrarAbierto, setIlustrarAbierto] = React.useState(false);
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
  // La salida del prompt de Redactar decide el modo de lanzamiento (piezas → borradores por red).
  const docRedactarQuery = useQuery({
    queryKey: ["texto-doc", PROMPT_REDACTAR],
    queryFn: ({ signal }) => api.documento(PROMPT_REDACTAR, signal),
  });
  const marcasLanzar = React.useMemo(
    () => marcasQuery.data?.marcas ?? [],
    [marcasQuery.data],
  );

  // ── Borradores → revisión: cuántas piezas de la marca esperan revisión (cola de aprobación). ──
  const aprobacion = useQuery({
    queryKey: ["aprobacion", "cola"],
    queryFn: ({ signal }) => api.colaAprobacion(signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const marcaNombre = nombreActiva ?? "";
  const pendientesRevision = React.useMemo(
    () =>
      (aprobacion.data?.cola ?? []).filter((p) => !marcaActiva || p.marca === marcaActiva).length,
    [aprobacion.data, marcaActiva],
  );

  return (
    <>
      <TituloPagina titulo="Producción" icono={Wand2} />
      <AccionesPagina>
        <MenuAcciones
          ajustesTitulo="Ajustes de producción"
          ajustesAbiertoInicial={abrirAjustes}
          ajustes={
            <>
              {/* Drawer de PRODUCCIÓN: solo ajustes que gobiernan cómo se redacta e ilustra.
                  «Máquina de contenido» (admisión + topes) · «Conexiones · Imagen IA» (imagen) ·
                  «Sistema» (automatismos + tuning). Sin presupuesto/economía (vive en Agentes). */}
              <PanelMaquinaContenido />
              <SeccionImagen />
              <SeccionPostproxy />
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
            onClick={() => navigate("/maquina/computo?proceso=produccion")}
          >
            Ver cómputo (Producción)
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* 1. LANZAMIENTO MANUAL: dos tarjetas (Redactar / Ilustrar). Click izquierdo abre el popup de
          lanzar (con «Editar prompt» dentro); click derecho / long-press → «Editar prompt».
          La marca la manda el switch global; el popup deshabilita Lanzar si está en "Todas". */}
      <div className="grid gap-4 sm:grid-cols-2">
        <TarjetaAccion
          onPrimaria={() => setRedactarAbierto(true)}
          acciones={[
            { etiqueta: "Editar prompt", icono: Pencil, onClick: () => setPromptEditando(PROMPT_REDACTAR) },
          ]}
          etiquetaAcciones="Acciones de Redactar"
          className="p-5"
        >
          <p className="text-base font-medium">Redactar</p>
        </TarjetaAccion>
        <TarjetaAccion
          onPrimaria={() => setIlustrarAbierto(true)}
          acciones={[
            { etiqueta: "Editar prompt", icono: Pencil, onClick: () => setPromptEditando(PROMPT_ILUSTRAR) },
          ]}
          etiquetaAcciones="Acciones de Ilustrar"
          className="p-5"
        >
          <p className="text-base font-medium">Ilustrar</p>
        </TarjetaAccion>
      </div>

      {/* 2. BORRADORES → REVISIÓN: tarjeta entera clicable que lleva al Feed de revisión. */}
      <TarjetaAccion
        onPrimaria={() => navigate("/operacion/feed/feed")}
        etiquetaAcciones="Borradores pendientes"
        className="mt-4 p-4"
      >
        {aprobacion.isPending ? (
          <Skeleton className="h-6 w-48" />
        ) : (
          <p className="text-sm">
            <span className="text-lg font-semibold">{pendientesRevision}</span>{" "}
            {pendientesRevision === 1 ? "borrador pendiente" : "borradores pendientes"} de revisión
            {marcaNombre ? <span className="text-muted-foreground"> · {marcaNombre}</span> : null}
          </p>
        )}
      </TarjetaAccion>

      {/* 3. MOTOR de auto-producción: el pipeline COMPLETO de Producción como tarjetas grandes
          (Redactar · Revisar · Ilustrar · Aprobar · Publicar), cada una con su icono, switch,
          conteos de cola y «Editar prompt»; el maestro «Máquina» en la cabecera. */}
      <div className="mt-6">
        <PanelPipeline
          titulo="Pipeline en vivo"
          fases={FASES_PRODUCCION}
          queuePorTipo={QUEUE_POR_TIPO_PRODUCCION}
          cola={cola.data}
          esAdmin={esAdmin}
        />
      </div>

      {/* 4. SERVICIOS de la máquina NO-IA de este motor (recolección, programador, GC…): los
          daemons clase=maquina del proceso de producción. Solo admin (endpoint de daemons). */}
      {esAdmin && (
        <div className="mt-6 rounded-xl border border-dashed border-border/70 bg-muted/30 p-2">
          <SeccionDaemons
            clases={["maquina"]}
            motor="produccion"
            titulo="Servicios (no consumen IA)"
          />
        </div>
      )}

      {/* Lanzador de Redactar (reusa PanelLanzar): marca del switch global + «Editar prompt» dentro. */}
      <PanelLanzar
        promptId={PROMPT_REDACTAR}
        salida={docRedactarQuery.data?.documento.salida ?? "piezas"}
        marcas={marcasLanzar}
        areas={areasQuery.data?.areas ?? []}
        open={redactarAbierto}
        onOpenChange={setRedactarAbierto}
        onEditarPrompt={() => setPromptEditando(PROMPT_REDACTAR)}
      />

      {/* Lanzador de Ilustrar (rico): prompt editable, modelo, N alternativas y coste. */}
      <PanelLanzarArte
        marcas={marcasLanzar}
        open={ilustrarAbierto}
        onOpenChange={setIlustrarAbierto}
        onEditarPrompt={() => setPromptEditando(PROMPT_ILUSTRAR)}
      />

      {/* Editor de prompt in-place (redactar/ilustrar) sin salir de la página. */}
      <EditorPromptOverlay
        docId={promptEditando}
        abierto={promptEditando !== null}
        onCerrar={() => setPromptEditando(null)}
      />
    </>
  );
}
