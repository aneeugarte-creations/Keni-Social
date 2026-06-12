// Galería visual de plantillas de diseño: rejilla de miniaturas para elegir una de un vistazo
// (mucho mejor que un desplegable). Filtra por la marca de la pestaña activa (el llamante).
// Pestaña de tipo: "Fotos" (default) / "Miniaturas" (portadas de video).
// Organización estilo Canva: búsqueda + chips de categoría + rejilla agrupada por categoría.
//
// Envoltorios sobre el MISMO contenido (`ContenidoPlantillas`), una sola fuente de verdad:
//  - `GaleriaPlantillas`: diálogo modal (overlay) — flujos que interrumpen (DialogoEditar, vídeo).
//  - `ContenidoPlantillas` directo: panel «Diseño» del rail del editor (columna ~350px), estilo
//    Canva: búsqueda y chips quedan FIJOS arriba (fuera del área con scroll).
//  - `ContenidoPlantillas` a página completa: estado vacío del editor (pages/Imagen) con
//    `agruparPorMarca` (vista «Todas») y tarjeta «Lienzo en blanco» al final (`onLienzoBlanco`).

import { Copy, Image, Plus, Repeat, Trash2, Video, X } from "lucide-react";
import { Fragment, useRef, useState } from "react";

import {
  BadgeCategoria,
  BuscadorPlantillas,
  ChipsCategoria,
  MasonryPlantillas,
  ratioPlantilla,
  useColumnasGaleria,
  useFiltroPlantillas,
  useLotes,
} from "@/components/plantillas/FiltroPlantillas";
import { urlMedia, type PlantillaDiseno } from "@/lib/api";
import { agruparPorCategoria, normalizarCategoria } from "@/lib/categoriasPlantilla";

import { Telon, useCerrarConEscape } from "./Telon";

type FiltroTipo = "foto" | "miniatura";

/** Clase Tailwind (estática) de columnas para la rejilla uniforme de reordenación. */
function claseColumnas(columnas: number): string {
  return columnas >= 6
    ? "grid-cols-6"
    : columnas === 5
      ? "grid-cols-5"
      : columnas >= 4
        ? "grid-cols-4"
        : columnas === 3
          ? "grid-cols-3"
          : "grid-cols-2";
}

// Agrupa plantillas por marca (orden alfabético por nombre de marca). Para la vista «Todas»,
// donde conviven varias marcas: amontonarlas en una sola rejilla no aporta nada, así que se
// dividen en secciones por marca.
function agruparPlantillasPorMarca(plantillas: PlantillaDiseno[]): PlantillaDiseno[][] {
  const porMarca = new Map<string, PlantillaDiseno[]>();
  for (const p of plantillas) {
    const arr = porMarca.get(p.marca);
    if (arr) arr.push(p);
    else porMarca.set(p.marca, [p]);
  }
  return [...porMarca.values()].sort((a, b) =>
    (a[0].marca_nombre || a[0].marca).localeCompare(b[0].marca_nombre || b[0].marca),
  );
}

/** Badge de tipo: pequeña etiqueta en el pie de la tarjeta, junto al nombre. */
function BadgeTipo({ tipo }: { tipo: "foto" | "miniatura" }) {
  return tipo === "miniatura" ? (
    <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-violet-100 px-1 py-0.5 text-[10px] font-medium text-violet-700 dark:bg-violet-900/40 dark:text-violet-300">
      <Video className="h-2.5 w-2.5" />
      Miniatura
    </span>
  ) : (
    <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-sky-100 px-1 py-0.5 text-[10px] font-medium text-sky-700 dark:bg-sky-900/40 dark:text-sky-300">
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
  /**
   * Si se pasa (modo GESTIÓN), las tarjetas se pueden REORDENAR arrastrándolas dentro de su sección
   * (misma marca + categoría), en una rejilla uniforme. Recibe la lista COMPLETA de ids en el nuevo
   * orden (el llamante la persiste). Se desactiva mientras hay una búsqueda activa (subconjunto
   * arbitrario sin posición clara).
   */
  onReordenar?: (ids: string[]) => void;
  /** Si se pasa, el selector de tipo queda fijo y no se puede cambiar (ej: DialogoEditar). */
  tipoFijo?: "foto" | "miniatura";
  /** Modo PANEL estrecho (columna del rail ~350px): rejilla fija de 2 columnas y padding menor. */
  compacto?: boolean;
  /** Tope de columnas (la modal, de ancho fijo, lo capa para no amontonar en pantallas grandes). */
  maxColumnas?: number;
  /** Divide la rejilla en secciones por MARCA (vista «Todas»: marca → categoría). */
  agruparPorMarca?: boolean;
  /** Si se pasa, añade la tarjeta «Lienzo en blanco» al FINAL de la galería (CTA para empezar). */
  onLienzoBlanco?: () => void;
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
  onReordenar,
  maxColumnas,
  tipoFijo,
  compacto,
  agruparPorMarca,
  onLienzoBlanco,
}: PropsContenido) {
  const [editId, setEditId] = useState<string | null>(null);
  const [editVal, setEditVal] = useState("");
  const [filtroTipo, setFiltroTipo] = useState<FiltroTipo>(tipoFijo ?? "foto");
  const [imagenRota, setImagenRota] = useState<Set<string>>(new Set());
  // Drag-and-drop de reordenación: id que se arrastra y id sobre el que se soltaría (para el realce).
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);

  // Ref para rastrear si el commit ya se ejecutó (evita doble PATCH en blur después de Enter).
  const commitHecho = useRef(false);

  const tipoEfectivo = tipoFijo ?? filtroTipo;
  const plantillasTipo = plantillas.filter((p) => (p.tipo ?? "foto") === tipoEfectivo);
  // Búsqueda + chip de categoría (client-side) SOBRE las del tipo activo.
  const { q, setQ, categoria, setCategoria, presentes, filtradas } =
    useFiltroPlantillas(plantillasTipo);

  // Carga perezosa por lotes (los datos YA están en memoria; esto solo limita el DOM). El corte
  // sigue el ORDEN DE PINTADO (sección a sección, grupo a grupo), así cada lote nuevo solo AÑADE
  // al final y el scroll no salta. Cambiar búsqueda/chip/tipo reinicia el contador.
  const { visibles, hayMas, refSentinela } = useLotes(
    filtradas.length,
    `${tipoEfectivo}|${categoria}|${q}`,
  );
  // SECCIONES de la rejilla: con `agruparPorMarca` (vista «Todas») se divide por marca (orden
  // alfabético) y dentro por categoría; sin él, una única sección (solo categorías). La cabecera
  // de categoría de cada sección se decide sobre sus grupos COMPLETOS (no sobre el lote), para
  // que no aparezcan cabeceras de golpe al soltar un lote.
  const listas = agruparPorMarca ? agruparPlantillasPorMarca(filtradas) : [filtradas];
  let resto = visibles;
  const secciones = listas
    .map((lista) => {
      const grupos = agruparPorCategoria(lista);
      const corte: typeof grupos = [];
      for (const g of grupos) {
        if (resto <= 0) break;
        const visiblesGrupo = g.plantillas.slice(0, resto);
        resto -= visiblesGrupo.length;
        corte.push({ ...g, plantillas: visiblesGrupo });
      }
      return { marca: lista[0], conCabeceras: grupos.length > 1, grupos: corte };
    })
    .filter((s) => s.grupos.length > 0);

  // En panel estrecho (~350px) el masonry es SIEMPRE de 2 columnas (estilo Canva); en el diálogo
  // ancho acompaña al viewport (2/3/4).
  const columnasGaleria = useColumnasGaleria();
  const columnas = compacto ? 2 : Math.min(columnasGaleria, maxColumnas ?? columnasGaleria);

  // ── REORDENAR (drag-and-drop) ─────────────────────────────────────────────────────────────────
  // Activo solo en modo gestión (`onReordenar`) y SIN búsqueda (un subconjunto buscado no tiene
  // posición clara). En rejilla uniforme: se arrastra una tarjeta y se suelta sobre otra de la
  // MISMA sección (misma marca + categoría); la arrastrada se inserta ANTES de la destino. El
  // llamante recibe la lista COMPLETA de ids en el nuevo orden y la persiste.
  const dndActivo = !!onReordenar && !q;
  const claveSeccion = (p: PlantillaDiseno) => `${p.marca}|${normalizarCategoria(p.categoria)}`;
  const soltarSobre = (destinoId: string) => {
    const origenId = arrastrando;
    setArrastrando(null);
    setSobre(null);
    if (!origenId || origenId === destinoId || !onReordenar) return;
    const origen = plantillas.find((p) => p.id === origenId);
    const destino = plantillas.find((p) => p.id === destinoId);
    // Solo dentro de la misma sección: arrastrar entre marcas/categorías no recoloca ni recategoriza.
    if (!origen || !destino || claveSeccion(origen) !== claveSeccion(destino)) return;
    const ids = plantillas.filter((p) => p.id !== origenId).map((p) => p.id);
    const idx = ids.indexOf(destinoId);
    if (idx < 0) return;
    ids.splice(idx, 0, origenId);
    onReordenar(ids);
  };

  const commit = (p: PlantillaDiseno) => {
    // Si el commit ya se hizo, noop. Así evitamos doble PATCH: Enter ejecuta commit,
    // luego onBlur sería un noop.
    if (commitHecho.current) return;
    commitHecho.current = true;

    const n = editVal.trim();
    if (n && n !== p.nombre) onRenombrar?.(p, n);
    setEditId(null);
  };

  const padX = compacto ? "px-3" : "px-4";

  // Tarjeta de plantilla: miniatura con la relación de aspecto REAL del documento (la caja
  // reserva el alto exacto antes de cargar la imagen: placeholder sin layout shift y altura
  // variable del masonry) + título/acciones debajo. Hover: elevación + scale sutil (~150ms).
  const tarjeta = (p: PlantillaDiseno) => (
    <div
      key={p.id}
      data-plantilla-id={p.id}
      draggable={dndActivo || undefined}
      onDragStart={
        dndActivo
          ? (e) => {
              setArrastrando(p.id);
              e.dataTransfer.effectAllowed = "move";
            }
          : undefined
      }
      onDragEnter={
        dndActivo
          ? () => {
              if (!arrastrando || arrastrando === p.id) return;
              const o = plantillas.find((x) => x.id === arrastrando);
              if (o && claveSeccion(o) === claveSeccion(p)) setSobre(p.id);
            }
          : undefined
      }
      onDragOver={
        dndActivo
          ? (e) => {
              e.preventDefault();
              e.dataTransfer.dropEffect = "move";
            }
          : undefined
      }
      onDragLeave={dndActivo ? () => setSobre((s) => (s === p.id ? null : s)) : undefined}
      onDrop={dndActivo ? (e) => { e.preventDefault(); soltarSobre(p.id); } : undefined}
      onDragEnd={dndActivo ? () => { setArrastrando(null); setSobre(null); } : undefined}
      className={`group relative rounded transition-[outline] ${dndActivo ? "cursor-move" : ""} ${
        arrastrando === p.id ? "opacity-50" : ""
      } ${
        sobre === p.id && arrastrando && arrastrando !== p.id
          ? "outline-dashed outline-2 outline-offset-2 outline-primary"
          : "outline-none"
      }`}
    >
      <button
        onClick={() => onCargar(p)}
        title={`Cargar «${p.nombre}»`}
        className="block w-full overflow-hidden rounded border border-border bg-muted/40 transition-[transform,box-shadow] duration-150 hover:shadow-lg hover:ring-2 hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary motion-safe:hover:scale-[1.02]"
      >
        <div className="w-full" style={{ aspectRatio: String(ratioPlantilla(p)) }}>
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
              draggable={false}
              onError={() => setImagenRota((prev) => new Set([...prev, p.id]))}
              className="h-full w-full object-contain"
            />
          )}
        </div>
      </button>
      {/* Badge de categoría sobre la tarjeta (el de tipo va abajo, junto al nombre) */}
      <div className="absolute left-1.5 top-1.5 flex max-w-[calc(100%-3.75rem)] flex-wrap items-start gap-1">
        <BadgeCategoria
          categoria={p.categoria}
          onCambiar={onCategorizar ? (slug) => onCategorizar(p, slug) : undefined}
        />
      </div>
      {/* Pie: etiqueta de tipo + título, fuera de la miniatura. Clic en el título
          renombra inline (la miniatura de arriba abre la plantilla). */}
      <div className="flex items-center gap-1 px-1.5 py-1">
        <BadgeTipo tipo={p.tipo ?? "foto"} />
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
            className="block min-w-0 flex-1 rounded border border-primary bg-background px-1 py-0.5 text-xs"
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
            className="min-w-0 flex-1 truncate text-left text-xs text-muted-foreground hover:text-foreground"
          >
            {p.nombre || "(sin nombre)"}
          </button>
        ) : (
          <div className="min-w-0 flex-1 truncate text-left text-xs">{p.nombre || "(sin nombre)"}</div>
        )}
      </div>
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
  );

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {/* Filtro de tipo (solo si no está fijo): segmented control estilo «Turnos» (Apple/Canva) —
          track gris con la pestaña activa como píldora BLANCA con sombra (sin la antigua píldora
          negra `bg-primary`). */}
      {!tipoFijo && (
        <div className={`flex shrink-0 border-b border-border py-2 ${padX}`}>
          <div className="inline-flex items-center rounded-lg bg-muted p-1">
            {(["foto", "miniatura"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setFiltroTipo(t)}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-sm font-medium transition-all ${
                  filtroTipo === t
                    ? "bg-background text-foreground shadow"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {t === "foto" ? (
                  <><Image className="h-3.5 w-3.5" />Fotos</>
                ) : (
                  <><Video className="h-3.5 w-3.5" />Miniaturas</>
                )}
              </button>
            ))}
          </div>
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
          // VACÍO de galería (tono único en todas las galerías): qué falta + qué hacer. La CTA es
          // la tarjeta «Lienzo en blanco» de abajo cuando existe (`onLienzoBlanco`).
          <p className="py-8 text-center text-sm text-muted-foreground">
            Aún no hay {tipoEfectivo === "miniatura" ? "miniaturas" : "plantillas"} para esta
            marca. Diseña una en el lienzo y pulsa «Guardar plantilla».
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
          // Secciones (marca → categoría o solo categoría) con cabeceras según el modo.
          <>
            <div className={agruparPorMarca ? "space-y-8" : undefined}>
              {secciones.map((s, i) => {
                const cuerpo = (
                  <div className="space-y-5">
                    {s.grupos.map((grupo) => {
                      // Dentro de una sección de marca, la categoría baja un nivel (h4).
                      const Cabecera = agruparPorMarca ? "h4" : "h3";
                      return (
                        <section key={grupo.slug}>
                          {s.conCabeceras && (
                            <Cabecera className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                              {grupo.etiqueta}
                            </Cabecera>
                          )}
                          {dndActivo ? (
                            // Rejilla UNIFORME (filas/columnas regulares) para que arrastrar a una
                            // posición exacta sea predecible (el masonry por columnas no lo es).
                            <div className={`grid gap-3 ${claseColumnas(columnas)}`}>
                              {grupo.plantillas.map((p) => tarjeta(p))}
                            </div>
                          ) : (
                            <MasonryPlantillas
                              plantillas={grupo.plantillas}
                              columnas={columnas}
                              render={tarjeta}
                            />
                          )}
                        </section>
                      );
                    })}
                  </div>
                );
                return agruparPorMarca && s.marca ? (
                  <section key={s.marca.marca}>
                    <h3 className="mb-2 border-b border-border pb-1 text-sm font-medium text-foreground">
                      {s.marca.marca_nombre || s.marca.marca}
                    </h3>
                    {cuerpo}
                  </section>
                ) : (
                  <Fragment key={i}>{cuerpo}</Fragment>
                );
              })}
            </div>
            {/* Sentinel de scroll infinito: al acercarse, suelta el siguiente lote. */}
            {hayMas && <div ref={refSentinela} data-sentinela aria-hidden className="h-px" />}
          </>
        )}
        {/* «Lienzo en blanco» va al FINAL de la galería (no el primero), en todos los estados. */}
        {onLienzoBlanco && (
          <div className={`mt-6 grid gap-3 ${claseColumnas(columnas)}`}>
            <button
              onClick={onLienzoBlanco}
              className="flex aspect-[4/5] flex-col items-center justify-center gap-1 rounded border border-dashed border-border text-xs text-muted-foreground hover:border-primary hover:text-foreground"
            >
              <Plus className="h-6 w-6" />
              Lienzo en blanco
            </button>
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
        {/* La modal es de ancho fijo (max-w-3xl): capa las columnas a 4 para no amontonar. */}
        <ContenidoPlantillas maxColumnas={4} {...contenido} />
      </div>
    </div>
  );
}
