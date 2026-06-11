/**
 * Vista "La máquina" de la Biblioteca de Prompts: el RIEL de pipelines en el ORDEN REAL
 * de ejecución (GET /api/texto/maquina). Cada grupo (Ingesta → Priorización → Producción →
 * Talleres) es una sección con sus etapas como tarjetas clicables; bajo la etapa de copy
 * se pinta el ENSAMBLAJE EDITORIAL de la marca activa (las capas, en el orden real en que
 * se adjuntan al prompt). Conectores CSS puros (sin librerías de grafos); en pantallas
 * estrechas los grupos apilan en vertical.
 */
import { AlertTriangle, ChevronDown, ChevronRight, Layers } from "lucide-react";
import * as React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type {
  CapaMaquina,
  EstadoPublicacionDoc,
  GrupoMaquina,
  ValidacionEditorial,
} from "@/types";

/** Nombre humano de cada pilar editorial (para las capas que FALTAN en la pila). */
const PILAR_LABEL: Record<string, string> = {
  marca: "Marca",
  voz: "Voz",
  plataforma: "Plataforma",
  tropicalizacion: "Tropicalización",
  reglas: "Reglas",
};

function nombrePilar(p: string): string {
  return PILAR_LABEL[p] ?? p.charAt(0).toUpperCase() + p.slice(1);
}

/** Badge del estado de publicación de un documento del riel (producción / sin puntero). */
function BadgesPublicacion({ estado }: { estado: EstadoPublicacionDoc }) {
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      {estado.produccion ? (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-700 dark:text-emerald-300"
          title={`Versión de producción ${estado.produccion.sha.slice(0, 8)} (${estado.produccion.autor})`}
        >
          <span aria-hidden>●</span> v. de producción
        </span>
      ) : (
        <span
          className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
          title="Sin versión publicada: los pipelines usan la copia de trabajo"
        >
          —
        </span>
      )}
      {estado.sin_publicar ? (
        <span
          className="inline-flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:text-amber-300"
          title="El borrador difiere de la versión publicada"
        >
          <AlertTriangle className="h-3 w-3" aria-hidden /> sin publicar
        </span>
      ) : null}
    </span>
  );
}

/** Pila de capas editoriales bajo la etapa de copy: el ensamblaje real de la marca. */
function PilaCapas({
  capas,
  validacion,
  nombreMarca,
  onAbrir,
}: {
  capas: CapaMaquina[];
  validacion?: ValidacionEditorial;
  nombreMarca: string | null;
  onAbrir: (docId: string) => void;
}) {
  return (
    <div className="mt-2 overflow-hidden rounded-md border border-dashed border-border bg-muted/20">
      <div className="flex items-center gap-1.5 border-b border-dashed border-border px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground">
        <Layers className="h-3 w-3" aria-hidden />
        Ensamblaje editorial{nombreMarca ? ` · ${nombreMarca}` : ""}
      </div>
      {!nombreMarca ? (
        <p className="px-2.5 py-2 text-xs text-muted-foreground">
          Elige una marca para ver su ensamblaje editorial.
        </p>
      ) : capas.length === 0 && (validacion?.faltan?.length ?? 0) === 0 ? (
        <p className="px-2.5 py-2 text-xs text-muted-foreground">
          Esta marca aún no tiene capas editoriales activas.
        </p>
      ) : (
        <ol className="divide-y divide-border/60">
          {capas.map((c) => (
            <li key={c.doc_id}>
              <button
                type="button"
                onClick={() => onAbrir(c.doc_id)}
                className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs hover:bg-muted/60"
                title={`${c.titulo} — abrir documento`}
              >
                <span className="w-4 shrink-0 text-right tabular-nums text-muted-foreground">
                  {c.orden}.
                </span>
                {c.clase ? (
                  <span className="shrink-0 rounded bg-keni/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-keni">
                    {c.clase}
                  </span>
                ) : null}
                <span className="min-w-0 flex-1 truncate">{c.titulo}</span>
                {c.sin_publicar ? (
                  <AlertTriangle
                    className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400"
                    aria-label="Cambios sin publicar"
                  />
                ) : null}
              </button>
            </li>
          ))}
          {(validacion?.faltan ?? []).map((p) => (
            <li
              key={`falta-${p}`}
              className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-muted-foreground"
              title={validacion?.recomendacion || "Pilar editorial sin cubrir para esta marca"}
            >
              <span className="w-4 shrink-0 text-right tabular-nums">·</span>
              <span className="min-w-0 flex-1 truncate">
                {nombrePilar(p)} — vacía
              </span>
              <AlertTriangle
                className="h-3 w-3 shrink-0 text-amber-600 dark:text-amber-400"
                aria-hidden
              />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function VistaMaquina({
  grupos,
  capas,
  validacion,
  nombreMarca,
  cargando,
  tituloDe,
  onAbrir,
}: {
  grupos: GrupoMaquina[];
  capas: CapaMaquina[];
  /** Diagnóstico de pilares editoriales de la marca (para señalar capas vacías). */
  validacion?: ValidacionEditorial;
  /** Nombre legible de la marca activa, o `null` en la vista agregada. */
  nombreMarca: string | null;
  cargando: boolean;
  /** Título legible de un doc del riel (lookup en el listado); fallback: el id. */
  tituloDe: (docId: string) => string | undefined;
  onAbrir: (docId: string) => void;
}) {
  if (cargando) {
    return (
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4" data-testid="maquina-cargando">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:gap-3">
      {grupos.map((g, i) => (
        <React.Fragment key={g.id}>
          {i > 0 ? (
            // Conector ENTRE grupos: flecha hacia la derecha en el riel horizontal,
            // hacia abajo cuando los grupos apilan en vertical.
            <div className="flex shrink-0 items-center justify-center text-muted-foreground/50 xl:mt-10" aria-hidden>
              <ChevronDown className="h-4 w-4 xl:hidden" />
              <ChevronRight className="hidden h-4 w-4 xl:block" />
            </div>
          ) : null}
          <section className="min-w-0 flex-1" aria-label={g.titulo}>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {g.titulo}
            </h3>
            <ol className="mt-2">
              {g.etapas.map((e, j) => (
                <li key={e.id}>
                  {j > 0 ? (
                    // Conector ENTRE etapas del mismo grupo: línea vertical (CSS puro).
                    <div className="mx-auto h-3 w-px bg-border" aria-hidden />
                  ) : null}
                  <button
                    type="button"
                    onClick={() => onAbrir(e.doc_id)}
                    className="w-full rounded-md border border-border bg-card px-3 py-2.5 text-left shadow-sm transition-colors hover:border-keni/40 hover:bg-muted/40"
                    title={`${e.titulo} — abrir el prompt`}
                  >
                    <span className="block text-sm font-medium leading-snug">{e.titulo}</span>
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {tituloDe(e.doc_id) ?? e.doc_id}
                    </span>
                    <span className="mt-1.5 block">
                      <BadgesPublicacion estado={e} />
                    </span>
                  </button>
                  {/* Bajo la etapa de copy: las capas editoriales que se le adjuntan. */}
                  {g.id === "produccion" && e.id === "copy" ? (
                    <PilaCapas
                      capas={capas}
                      validacion={validacion}
                      nombreMarca={nombreMarca}
                      onAbrir={onAbrir}
                    />
                  ) : null}
                </li>
              ))}
            </ol>
          </section>
        </React.Fragment>
      ))}
    </div>
  );
}
