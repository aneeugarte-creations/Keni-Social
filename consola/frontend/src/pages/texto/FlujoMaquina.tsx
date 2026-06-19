/**
 * La LÍNEA de UNA máquina de la Biblioteca (`GET /api/texto/maquina`, ADR 0011):
 * las etapas en el ORDEN REAL del proceso, con conectores CSS puros y dos
 * tratamientos visuales claramente distintos:
 *   - etapa `prompt`  : tarjeta plena CLICABLE (título de etapa, nombre del doc,
 *     estado de publicación) que abre el detalle del documento;
 *   - etapa `mecanica`: nodo atenuado/fantasma (pill pequeña, no clicable) que
 *     cuenta la historia completa del proceso sin robar protagonismo.
 *
 * El evergreen (`seccion: "taller"`) se separa del flujo principal como anexo
 * «Taller». En Producción, bajo la etapa de Redactar, un enlace discreto lleva a la
 * pestaña «Estrategia de marca» (las capas editoriales ya no viven aquí).
 */
import { AlertTriangle, ArrowRight, CheckCircle2, Cog, Hammer } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { EtapaMaquina, EtapaPrompt, MaquinaTexto } from "@/types";

/** Enlace cruzado Biblioteca → página de proceso (ADR 0011 F2): cada máquina con página
 *  propia enlaza a su proceso EN VIVO. Importación no tiene página de proceso: sin enlace. */
const RUTA_PROCESO: Record<string, string> = {
  investigacion: "/maquina/investigacion",
  produccion: "/maquina/produccion",
};

/** Badge del estado de publicación de una etapa con prompt (producción / sin publicar). */
function BadgesPieza({ etapa }: { etapa: EtapaPrompt }) {
  return (
    <span className="flex shrink-0 flex-wrap items-center justify-end gap-1.5">
      {etapa.produccion ? (
        <Badge
          variant="ok"
          className="gap-1"
          title={`Versión de producción ${etapa.produccion.sha.slice(0, 8)} (${etapa.produccion.autor})`}
        >
          <span aria-hidden>●</span> producción
        </Badge>
      ) : (
        <span
          className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
          title="Sin versión publicada: los pipelines usan la copia de trabajo"
        >
          —
        </span>
      )}
      {etapa.sin_publicar ? (
        <Badge variant="aviso" className="gap-1" title="El borrador difiere de la versión publicada">
          <AlertTriangle className="h-3 w-3" aria-hidden /> sin publicar
        </Badge>
      ) : null}
    </span>
  );
}

/** Tarjeta plena de una etapa CON prompt: abre el detalle del documento. */
function TarjetaEtapa({
  etapa,
  tituloDoc,
  onAbrir,
}: {
  etapa: EtapaPrompt;
  tituloDoc: string | undefined;
  onAbrir: (docId: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onAbrir(etapa.doc_id)}
      className="w-full rounded-lg border border-border bg-card px-4 py-3 text-left shadow-sm transition-colors hover:border-keni/40 hover:bg-muted/40"
      title={`${etapa.titulo} — abrir el prompt`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className="block text-sm font-medium leading-snug">{etapa.titulo}</span>
          <span className="mt-0.5 block truncate text-xs text-muted-foreground">
            {tituloDoc ?? etapa.doc_id}
          </span>
        </span>
        <BadgesPieza etapa={etapa} />
      </span>
    </button>
  );
}

/** Nodo fantasma de una etapa MECÁNICA: contexto del proceso, sin prompt editable. */
function NodoMecanico({ etapa }: { etapa: EtapaMaquina }) {
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-full border border-dashed border-border/80 bg-muted/30 px-3 py-1 text-xs text-muted-foreground/80"
      title="Etapa automática sin prompt"
    >
      <Cog className="h-3 w-3 shrink-0 opacity-60" aria-hidden />
      <span className="truncate">{etapa.titulo}</span>
    </span>
  );
}

/** Conector vertical entre etapas (CSS puro, sin librerías de grafos). */
function Conector() {
  return <div className="mx-auto h-4 w-px bg-border" aria-hidden />;
}

export function FlujoMaquina({
  maquina,
  cargando,
  tituloDe,
  onAbrir,
  onIrAEstrategia,
}: {
  /** La máquina a pintar (`maquinas[i]` del endpoint), o `undefined` mientras carga. */
  maquina?: MaquinaTexto;
  cargando: boolean;
  /** Título legible de un doc de la línea (lookup en el listado); fallback: el id. */
  tituloDe: (docId: string) => string | undefined;
  onAbrir: (docId: string) => void;
  /** Solo Producción: salto a la pestaña «Estrategia de marca» bajo la etapa de Redactar. */
  onIrAEstrategia?: () => void;
}) {
  // Salud agregada y partición línea principal / anexo «Taller» (seccion === "taller").
  const { principales, taller, conCambios } = React.useMemo(() => {
    const etapas = maquina?.etapas ?? [];
    return {
      principales: etapas.filter((e) => e.tipo !== "prompt" || e.seccion !== "taller"),
      taller: etapas.filter(
        (e): e is EtapaPrompt => e.tipo === "prompt" && e.seccion === "taller",
      ),
      conCambios: etapas.filter((e) => e.tipo === "prompt" && e.sin_publicar).length,
    };
  }, [maquina]);

  if (cargando || !maquina) {
    return (
      <div className="w-full space-y-3" data-testid="maquina-cargando">
        <Skeleton className="h-12 w-2/3" />
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="w-full">
      {/* ───────── Cabecera de la máquina ───────── */}
      <header className="flex flex-wrap items-end justify-between gap-2 border-b border-border pb-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-tight">{maquina.titulo}</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">{maquina.subtitulo}</p>
          {RUTA_PROCESO[maquina.id] ? (
            <Link
              to={RUTA_PROCESO[maquina.id]}
              className="mt-1 inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
            >
              Ver el proceso en vivo
              <ArrowRight className="h-3 w-3" aria-hidden />
            </Link>
          ) : null}
        </div>
        {conCambios > 0 ? (
          <Badge variant="aviso" className="gap-1.5" title="Etapas cuyo prompt tiene cambios sin publicar">
            <AlertTriangle className="h-3 w-3" aria-hidden />
            {conCambios} {conCambios === 1 ? "etapa" : "etapas"} sin publicar
          </Badge>
        ) : (
          <Badge variant="ok" className="gap-1.5">
            <CheckCircle2 className="h-3 w-3" aria-hidden /> todo publicado
          </Badge>
        )}
      </header>

      {/* ───────── La línea principal ───────── */}
      <ol className="mt-5" aria-label={`Etapas de ${maquina.titulo}`}>
        {principales.map((e, i) => (
          <li key={e.id} className={e.tipo === "mecanica" ? "text-center" : undefined}>
            {i > 0 ? <Conector /> : null}
            {e.tipo === "prompt" ? (
              <>
                <TarjetaEtapa etapa={e} tituloDoc={tituloDe(e.doc_id)} onAbrir={onAbrir} />
                {e.id === "redactar" && onIrAEstrategia ? (
                  <button
                    type="button"
                    onClick={onIrAEstrategia}
                    className="mt-1.5 inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  >
                    Las capas editoriales de la marca viven en Estrategia de marca
                    <ArrowRight className="h-3 w-3" aria-hidden />
                  </button>
                ) : null}
              </>
            ) : (
              <NodoMecanico etapa={e} />
            )}
          </li>
        ))}
      </ol>

      {/* ───────── Anexo «Taller» (evergreen): fuera del flujo principal ───────── */}
      {taller.length > 0 ? (
        <section
          aria-label="Taller"
          className="mt-6 rounded-lg border border-dashed border-border bg-muted/20 p-4"
        >
          <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Hammer className="h-3.5 w-3.5" aria-hidden /> Taller
          </h3>
          <div className="mt-3 space-y-3">
            {taller.map((e) => (
              <TarjetaEtapa key={e.id} etapa={e} tituloDoc={tituloDe(e.doc_id)} onAbrir={onAbrir} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
