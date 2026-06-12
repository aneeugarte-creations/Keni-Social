/**
 * GESTOR de composiciones de video (= gestor de transcripciones).
 *
 * Lista las composiciones de la MARCA ACTIVA con: formato, última edición, enlace a la pieza
 * ligada (si tiene `contenido_id`), el ESTADO de subtítulos (pendiente/transcrito/editado/listo)
 * y si la pieza ya tiene su video adjunto o le falta. Reabrir una composición la carga en el
 * editor navegando a `?composicion=<id>`.
 *
 * Honestidad: el estado de subtítulos sale de `GET /api/video/subtitulos` por composición; el
 * estado de "video adjunto" sale de la pieza ligada (`falta_video`). No publica nada.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Captions, Check, ExternalLink, FilmIcon, PencilLine, Trash2, VideoOff, X } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora } from "@/lib/fecha";
import {
  ETIQUETA_ESTADO_COMPOSICION,
  type ComposicionResumen,
  type EstadoComposicion,
  type EstadoSubtitulos,
} from "@/lib/video";

const ETIQUETA_ESTADO_SUBS: Record<EstadoSubtitulos, string> = {
  pendiente: "Subtítulos pendientes",
  transcrito: "Transcrito",
  editado: "Subtítulos editados",
  listo: "Subtítulos listos",
};

/** Filtro por estado del borrador en el gestor. */
type FiltroEstado = "todos" | EstadoComposicion;

export interface GestorComposicionesProps {
  /** Marca activa: filtra el listado (multi-tenant). */
  marca: string;
  /** Reabrir una composición en el editor (navega a `?composicion=<id>`). */
  onAbrir: (id: string) => void;
}

export function GestorComposiciones({ marca, onAbrir }: GestorComposicionesProps) {
  const qc = useQueryClient();
  const [filtro, setFiltro] = React.useState<FiltroEstado>("todos");

  // Composiciones de la marca activa (el `documento` viene ya parseado).
  const compsQ = useQuery({
    queryKey: ["video-composiciones", marca],
    queryFn: ({ signal }) =>
      api.video.listarComposiciones({ marca }, signal).then((r) => r.composiciones),
    enabled: !!marca,
  });

  // Renombrar / eliminar un borrador. Tras éxito, refresca la lista de la marca.
  const renombrar = useMutation({
    mutationFn: ({ id, titulo }: { id: string; titulo: string }) =>
      api.video.renombrarComposicion(id, titulo),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video-composiciones", marca] }),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const eliminar = useMutation({
    mutationFn: (id: string) => api.video.eliminarComposicion(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["video-composiciones", marca] }),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Piezas de la marca, para mapear `contenido_id -> falta_video` (¿ya tiene su mp4?).
  const pubsQ = useQuery({
    queryKey: ["publicaciones-falta-video", marca],
    queryFn: ({ signal }) =>
      api.publicaciones({ marca }, signal).then((r) => r.publicaciones),
    enabled: !!marca,
  });

  // Map contenido_id -> { faltaVideo, tieneVideo } a partir de las piezas de esa pieza/contenido.
  const estadoPieza = React.useMemo(() => {
    const m = new Map<string, { faltaVideo: boolean }>();
    for (const p of pubsQ.data ?? []) {
      if (!p.contenido_id) continue;
      const prev = m.get(p.contenido_id);
      // Una pieza (contenido) tiene varias publicaciones (una por red); con que UNA tenga video,
      // el contenido tiene su render. "falta" sólo si NINGUNA lo tiene.
      const faltaVideo = (prev?.faltaVideo ?? true) && !p.video;
      m.set(p.contenido_id, { faltaVideo });
    }
    return m;
  }, [pubsQ.data]);

  if (!marca) {
    return (
      <p className="rounded-md border border-dashed border-border bg-muted/20 p-3 text-sm text-muted-foreground">
        Selecciona una marca para ver sus composiciones de video.
      </p>
    );
  }

  if (compsQ.isLoading) {
    return <p className="p-2 text-sm text-muted-foreground">Cargando composiciones…</p>;
  }

  if (compsQ.isError) {
    return (
      <p className="rounded-md border border-dashed border-border bg-muted/20 p-3 text-sm text-muted-foreground">
        No se pudieron cargar las composiciones.
      </p>
    );
  }

  const comps = compsQ.data ?? [];

  if (comps.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
        Aún no hay composiciones. Crea una nueva al subir un video.
      </p>
    );
  }

  const visibles = comps.filter((c) => filtro === "todos" || (c.estado ?? "borrador") === filtro);

  return (
    <div className="space-y-3">
      {/* Filtro Borradores / Listos. */}
      <div className="flex gap-1" role="tablist" aria-label="Filtrar por estado">
        {([
          ["todos", "Todos"],
          ["borrador", "Borradores"],
          ["listo", "Listos"],
        ] as [FiltroEstado, string][]).map(([clave, etiqueta]) => (
          <button
            key={clave}
            type="button"
            role="tab"
            aria-selected={filtro === clave}
            onClick={() => setFiltro(clave)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
              filtro === clave ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60"
            }`}
          >
            {etiqueta}
          </button>
        ))}
      </div>

      {visibles.length === 0 ? (
        <p className="rounded-md border border-dashed border-border bg-muted/20 p-4 text-sm text-muted-foreground">
          No hay composiciones.
        </p>
      ) : (
        <ul className="space-y-2" aria-label="Mis composiciones de video">
          {visibles.map((c) => (
            <FilaComposicion
              key={c.id}
              comp={c}
              faltaVideo={c.contenido_id ? estadoPieza.get(c.contenido_id)?.faltaVideo : undefined}
              onAbrir={() => onAbrir(c.id)}
              onRenombrar={(titulo) => renombrar.mutate({ id: c.id, titulo })}
              onEliminar={() => eliminar.mutate(c.id)}
              eliminando={eliminar.isPending && eliminar.variables === c.id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Una fila del gestor: una composición con su título, estado, formato, subtítulos y enlaces. */
function FilaComposicion({
  comp,
  faltaVideo,
  onAbrir,
  onRenombrar,
  onEliminar,
  eliminando,
}: {
  comp: ComposicionResumen;
  /** `undefined` si la composición no tiene pieza ligada; si la tiene, ¿le falta el video? */
  faltaVideo: boolean | undefined;
  onAbrir: () => void;
  onRenombrar: (titulo: string) => void;
  onEliminar: () => void;
  eliminando: boolean;
}) {
  // Estado de subtítulos: una query barata por composición (null si aún no se transcribió).
  const subQ = useQuery({
    queryKey: ["video-subtitulos-de", comp.id],
    queryFn: ({ signal }) =>
      api.video.subtitulosDe(comp.id, signal).then((r) => r.subtitulo),
  });
  const estadoSubs = (subQ.data?.estado as EstadoSubtitulos) ?? "pendiente";

  const preset = comp.documento?.formato?.preset ?? "9:16";
  const tieneBase = (comp.documento?.pistas ?? []).some(
    (p) => p.tipo === "video" && p.id === "base" && "clips" in p && p.clips.length > 0,
  );
  const estadoComp: EstadoComposicion = comp.estado ?? "borrador";
  const tituloMostrado = comp.titulo?.trim() || comp.id;

  // Renombrado inline: al confirmar, sólo dispara si cambió y no quedó vacío.
  const [editando, setEditando] = React.useState(false);
  const [borrador, setBorrador] = React.useState(comp.titulo ?? "");

  function confirmarRenombre() {
    const t = borrador.trim();
    setEditando(false);
    if (t && t !== (comp.titulo ?? "")) onRenombrar(t);
    else setBorrador(comp.titulo ?? "");
  }

  function pedirEliminar() {
    if (window.confirm(`¿Eliminar «${tituloMostrado}»? Esta acción no se puede deshacer.`)) {
      onEliminar();
    }
  }

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card p-3">
      <FilmIcon className="h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {editando ? (
            <input
              autoFocus
              type="text"
              value={borrador}
              onChange={(e) => setBorrador(e.target.value)}
              onBlur={confirmarRenombre}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirmarRenombre();
                if (e.key === "Escape") {
                  setBorrador(comp.titulo ?? "");
                  setEditando(false);
                }
              }}
              aria-label="Nuevo título"
              className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          ) : (
            <span className="truncate text-sm font-medium text-foreground" title={comp.id}>
              {tituloMostrado}
            </span>
          )}
          <span
            className={`rounded-full px-1.5 py-0.5 text-[11px] font-medium ${
              estadoComp === "listo"
                ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
                : "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
            }`}
          >
            {ETIQUETA_ESTADO_COMPOSICION[estadoComp] ?? estadoComp}
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {preset}
          </span>
          {!tieneBase && (
            <span className="rounded bg-amber-100 px-1.5 py-0.5 text-[11px] font-medium text-amber-800 dark:bg-amber-900/40 dark:text-amber-300">
              Sin clip base
            </span>
          )}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span title={comp.actualizado}>
            Última edición: {formatearFechaHora(comp.actualizado) || "—"}
          </span>
          <span className="inline-flex items-center gap-1">
            <Captions className="h-3 w-3" />
            {ETIQUETA_ESTADO_SUBS[estadoSubs] ?? estadoSubs}
          </span>
          {comp.contenido_id ? (
            faltaVideo === true ? (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                <VideoOff className="h-3 w-3" />
                Falta el video en la pieza
              </span>
            ) : faltaVideo === false ? (
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <FilmIcon className="h-3 w-3" />
                Video adjunto a la pieza
              </span>
            ) : null
          ) : (
            <span>Sin pieza ligada</span>
          )}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {comp.contenido_id && (
          <Button asChild size="sm" variant="ghost">
            <Link to="/operacion/feed/lista" title="Ir a la lista de contenido">
              <ExternalLink className="mr-1 h-4 w-4" />
              Pieza
            </Link>
          </Button>
        )}
        {editando ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={confirmarRenombre}
            aria-label="Confirmar nombre"
            title="Confirmar nombre"
          >
            <Check className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => {
              setBorrador(comp.titulo ?? "");
              setEditando(true);
            }}
            aria-label="Renombrar"
            title="Renombrar"
          >
            <PencilLine className="h-4 w-4" />
          </Button>
        )}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={pedirEliminar}
          disabled={eliminando}
          aria-label="Eliminar"
          title="Eliminar"
          className="text-destructive hover:text-destructive"
        >
          {eliminando ? <X className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onAbrir}>
          <PencilLine className="mr-1 h-4 w-4" />
          Abrir
        </Button>
      </div>
    </li>
  );
}

/** Fecha ISO → `dd/mm/aa hh:mm` (es-MX); vacío si no hay dato. */
