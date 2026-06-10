// Galería visual de plantillas de diseño: rejilla de miniaturas para elegir una de un vistazo
// (mucho mejor que un desplegable). Filtra por la marca de la pestaña activa (el llamante).
// Pestaña de tipo: "Fotos" (default) / "Miniaturas" (portadas de video).
// Organización estilo Canva: búsqueda + chips de categoría + rejilla agrupada por categoría.
//
// Dos envoltorios sobre el MISMO contenido (`ContenidoPlantillas`):
//  - `GaleriaPlantillas`: diálogo modal (overlay) — flujos que interrumpen (DialogoEditar, vídeo).
//  - `ContenidoPlantillas` directo: panel «Diseño» del rail del editor (columna ~350px), estilo
//    Canva: búsqueda y chips quedan FIJOS arriba (fuera del área con scroll).

import { Copy, Image, Repeat, Trash2, Video, X } from "lucide-react";
import { useRef, useState } from "react";

import {
  BadgeCategoria,
  BuscadorPlantillas,
  ChipsCategoria,
  useFiltroPlantillas,
} from "@/components/plantillas/FiltroPlantillas";
import { urlMedia, type PlantillaDiseno } from "@/lib/api";
import { agruparPorCategoria } from "@/lib/categoriasPlantilla";

import { Telon, useCerrarConEscape } from "./Telon";

type FiltroTipo = "foto" | "miniatura";

/** Badge de tipo: pequeña etiqueta visual sobre la tarjeta de plantilla. */
function BadgeTipo({ tipo }: { tipo: "foto" | "miniatura" }) {
  return tipo === "miniatura" ? (
    <span className="inline-flex items-center gap-0.5 rounded bg-violet-100 px-1 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
      <Video className="h-2.5 w-2.5" />
      Miniatura
    </span>
  ) : (
    <span className="inline-flex items-center gap-0.5 rounded bg-sky-100 px-1 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
      <Image className="h-2.5 w-2.5" />
      Foto
    </span>
  );
}

interface PropsContenido {
  plantillas: PlantillaDiseno[];
  onCargar: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece borrar (modo SELECTOR, p. ej. elegir plantilla para una pieza). */
  onBorrar?: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece duplicar (modo SELECTOR). */
  onDuplicar?: (p: PlantillaDiseno) => void;
  /** Si se omite, no se ofrece renombrar (modo SELECTOR). */
  onRenombrar?: (p: PlantillaDiseno, nombre: string) => void;
  /** Si se omite, no se ofrece marcar/desmarcar la plantilla para la ROTACIÓN (modo SELECTOR). */
  onRotar?: (p: PlantillaDiseno, rotar: boolean) => void;
  /** Si se omite, el badge de categoría es solo informativo (modo SELECTOR). */
  onCategorizar?: (p: PlantillaDiseno, categoria: string) => void;
  /** Si se pasa, el selector de tipo queda fijo y no se puede cambiar (ej: DialogoEditar). */
  tipoFijo?: "foto" | "miniatura";
  /** Modo PANEL estrecho (columna del rail ~350px): rejilla fija de 2 columnas y padding menor. */
  compacto?: boolean;
}

/**
 * Contenido de la galería (filtro de tipo + búsqueda/chips fijos + rejilla con scroll), SIN
 * envoltorio modal: reutilizable como panel «Diseño» del rail del editor o dentro del diálogo.
 */
export function ContenidoPlantillas({
  plantillas,
  onCargar,
  onBorrar,
  onDuplicar,
  onRenombrar,
  onRotar,
  onCategorizar,
  tipoFijo,
  compacto,
}: PropsContenido) {
  const [editId, setEditId] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>(tipoFijo ?? "foto");
  const [imagenRota, setImagenRota] = useState<Set<string>>(new Set());

  // Ref para rastrear si el commit ya se ejecutó (evita doble PATCH en blur después de Enter).
  const commitHecho = useRef(false);

  const tipoEfectivo = tipoFijo ?? filtroTipo;
  const plantillasTipo = plantillas.filter((p) => (p.tipo ?? "foto") === tipoEfectivo);
  // Búsqueda + chip de categoría (client-side) SOBRE las del tipo activo.
  const { q, setQ, categoria, setCategoria, presentes, filtradas } =
    useFiltroPlantillas(plantillasTipo);
  const grupos = agruparPorCategoria(filtradas);

  const commit = (p: PlantillaDiseno) => {
    // Si el commit ya se hizo, noop. Así evitamos doble PATCH: Enter ejecuta commit,
    // luego onBlur sería un noop.
    if (commitHecho.current) return;
    commitHecho.current = true;

    const n = editVal.trim();
    if (n && n !== p.nombre) onRenombrar?.(p, n);
    setEditId(null);
  };

  // En panel estrecho (~350px) la rejilla es SIEMPRE de 2 columnas (masonry estilo Canva).
  const padX = compacto ? "px-3" : "px-4";
  const rejilla = compacto
    ? "grid grid-cols-2 gap-3"
    : "grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4";

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {/* Filtro de tipo (solo si no está fijo) */}
      {!tipoFijo && (
        <div className={`flex shrink-0 gap-1 border-b border-border py-2 ${padX}`}>
          {(["foto", "miniatura"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setFiltroTipo(t)}
              className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                filtroTipo === t
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
            >
              {t === "foto" ? (
                <><Image className="h-3 w-3" />Fotos</>
              ) : (
                <><Video className="h-3 w-3" />Miniaturas</>
              )}
            </button>
          ))}
        </div>
      )}

      {/* Búsqueda + chips de categoría: FIJOS arriba (fuera del área con scroll, estilo Canva). */}
      {plantillasTipo.length > 0 && (
        <div className={`shrink-0 space-y-2 border-b border-border bg-background py-2 ${padX}`}>
          <BuscadorPlantillas valor={q} onCambiar={setQ} />
          <ChipsCategoria categorias={presentes} activa={categoria} onCambiar={setCategoria} />
        </div>
      )}

      <div className={`min-h-0 flex-1 overflow-auto py-4 ${padX}`}>
        {plantillasTipo.length === 0 ? (
          <p className="py-8 text-center text-sm text-muted-foreground">
            {tipoEfectivo === "miniatura"
              ? "Aún no hay miniaturas para esta marca. Diseña una plantilla de tipo «Miniatura» y pulsa «Guardar plantilla»."
              : "Aún no hay plantillas para esta marca. Diseña una y pulsa «Guardar plantilla»."}
          </p>
        ) : filtradas.length === 0 ? (
          // VACÍO de búsqueda: además del mensaje, una salida de un clic (limpia búsqueda + chip).
          <div className="space-y-3 py-8 text-center">
            <p className="text-sm text-muted-foreground">Sin resultados para esa búsqueda.</p>
            <button
              onClick={() => { setQ(""); setCategoria(""); }}
              className="rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              Borrar búsqueda
            </button>
          </div>
        ) : (
          // Agrupación por CATEGORÍA (cabecera solo si hay más de un grupo).
          <div className="space-y-5">
            {grupos.map((grupo) => (
              <section key={grupo.slug}>
                {grupos.length > 1 && (
                  <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {grupo.etiqueta}
                  </h3>
                )}
                <div className={rejilla}>
                  {grupo.plantillas.map((p) => (
              <div key={p.id} className="group relative">
                <button
                  onClick={() => onCargar(p)}
                  title={`Cargar «${p.nombre}»`}
                  className="block w-full overflow-hidden rounded border border-border bg-muted/40 hover:ring-2 hover:ring-primary"
                >
                  <div className="aspect-[4/5] w-full">
                    {/* Miniatura guardada (la genera el estudio al guardar) o, si falta —p. ej.
                        plantillas creadas por API/agente—, el render on-demand del documento. */}
                    {imagenRota.has(p.id) ? (
                      <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
                        Sin vista previa
                      </div>
                    ) : (
                      <img
                        src={p.miniatura ? urlMedia(p.miniatura) : `/api/plantillas-diseno/${p.id}/preview`}
                        alt={p.nombre}
                        loading="lazy"
                        onError={() => setImagenRota((prev) => new Set([...prev, p.id]))}
                        className="h-full w-full object-contain"
                      />
                    )}
                  </div>
                </button>
                {/* Badges de tipo + categoría sobre la tarjeta */}
                <div className="absolute left-1.5 top-1.5 flex max-w-[calc(100%-3.75rem)] flex-wrap items-start gap-1">
                  <BadgeTipo tipo={p.tipo ?? "foto"} />
                  <BadgeCategoria
                    categoria={p.categoria}
                    onCambiar={onCategorizar ? (slug) => onCategorizar(p, slug) : undefined}
                  />
                </div>
                {/* Título: clic para renombrar inline (la miniatura de arriba abre la plantilla). */}
                {onRenombrar && editId === p.id ? (
                  <input
                    autoFocus
                    value={editVal}
                    onChange={(e) => setEditVal(e.target.value)}
                    onBlur={() => commit(p)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.stopPropagation();
                        commit(p);
                      } else if (e.key === "Escape") {
                        e.stopPropagation();
                        setEditId(null);
                        commitHecho.current = false;
                      }
                    }}
                    className="block w-full rounded border border-primary bg-background px-1.5 py-1 text-xs"
                  />
                ) : onRenombrar ? (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setEditId(p.id);
                      setEditVal(p.nombre || "");
                      commitHecho.current = false;
                    }}
                    title="Clic para renombrar"
                    className="block w-full truncate px-1.5 py-1 text-left text-xs text-muted-foreground hover:text-foreground"
                  >
                    {p.nombre || "(sin nombre)"}
                  </button>
                ) : (
                  <div className="truncate px-1.5 py-1 text-left text-xs">{p.nombre || "(sin nombre)"}</div>
                )}
                {/* Rotación: marca la plantilla para entrar en la ROTACIÓN automática de la marca
                    (cada post nuevo se lleva la siguiente del grupo; mismo color en todas las redes).
                    Necesita ≥2 plantillas marcadas para activarse. */}
                {onRotar && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onRotar(p, !p.rotar); }}
                    title={p.rotar ? "En rotación: clic para sacarla del grupo" : "Clic para incluirla en la rotación de la marca"}
                    className={`flex w-full items-center justify-center gap-1 px-1.5 py-1 text-[11px] font-medium transition-colors ${
                      p.rotar
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Repeat className="h-3 w-3" />
                    {p.rotar ? "En rotación" : "Rotación"}
                  </button>
                )}
                {onDuplicar && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDuplicar(p); }}
                    title="Duplicar plantilla"
                    className="absolute right-8 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-foreground group-hover:opacity-100"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                )}
                {onBorrar && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onBorrar(p); }}
                    title="Borrar plantilla"
                    className="absolute right-1 top-1 rounded bg-background/80 p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function GaleriaPlantillas({
  onCerrar,
  ...contenido
}: PropsContenido & { onCerrar: () => void }) {
  // Escape cierra la galería esté donde esté el foco (overlay casero, sin Radix).
  useCerrarConEscape(true, onCerrar);

  const handleDialogKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Tab") {
      const dialog = e.currentTarget;
      const focusables = dialog.querySelectorAll(
        "button, input, [tabindex]:not([tabindex='-1'])"
      ) as NodeListOf<HTMLElement>;
      if (focusables.length === 0) return;

      const focused = document.activeElement as HTMLElement;
      const focusedIndex = Array.from(focusables).indexOf(focused);

      if (e.shiftKey) {
        // Shift+Tab: ir atrás
        const prev = focusedIndex <= 0 ? focusables.length - 1 : focusedIndex - 1;
        e.preventDefault();
        focusables[prev]?.focus();
      } else {
        // Tab: ir adelante
        const next = focusedIndex < 0 || focusedIndex >= focusables.length - 1 ? 0 : focusedIndex + 1;
        e.preventDefault();
        focusables[next]?.focus();
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop accesible: clicable, focusable y cierra también con Escape (A11y). */}
      <Telon
        onCerrar={onCerrar}
        etiqueta="Cerrar galería de plantillas"
        className="absolute inset-0 bg-black/50"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Plantillas"
        onKeyDown={handleDialogKeyDown}
        className="relative flex max-h-[80vh] w-full max-w-3xl flex-col overflow-hidden rounded-lg border border-border bg-background shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">Plantillas</h2>
          <button
            onClick={onCerrar}
            aria-label="Cerrar"
            className="text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <ContenidoPlantillas {...contenido} />
      </div>
    </div>
  );
}
