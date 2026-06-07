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
import { useQuery } from "@tanstack/react-query";
import { Captions, ExternalLink, FilmIcon, PencilLine, VideoOff } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import {
  type ComposicionResumen,
  type EstadoSubtitulos,
} from "@/lib/video";

const ETIQUETA_ESTADO_SUBS: Record<EstadoSubtitulos, string> = {
  pendiente: "Subtítulos pendientes",
  transcrito: "Transcrito (sin revisar)",
  editado: "Subtítulos editados",
  listo: "Subtítulos listos",
};

export interface GestorComposicionesProps {
  /** Marca activa: filtra el listado (multi-tenant). */
  marca: string;
  /** Reabrir una composición en el editor (navega a `?composicion=<id>`). */
  onAbrir: (id: string) => void;
}

export function GestorComposiciones({ marca, onAbrir }: GestorComposicionesProps) {
  // Composiciones de la marca activa (el `documento` viene ya parseado).
  const compsQ = useQuery({
    queryKey: ["video-composiciones", marca],
    queryFn: ({ signal }) =>
      api.video.listarComposiciones({ marca }, signal).then((r) => r.composiciones),
    enabled: !!marca,
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
        Aún no hay composiciones para esta marca. Empieza una nueva en la sección «Base» (al subir
        un clip base se crea la composición), o edita una pieza de video desde la lista de contenido.
      </p>
    );
  }

  return (
    <ul className="space-y-2" aria-label="Mis composiciones de video">
      {comps.map((c) => (
        <FilaComposicion
          key={c.id}
          comp={c}
          faltaVideo={c.contenido_id ? estadoPieza.get(c.contenido_id)?.faltaVideo : undefined}
          onAbrir={() => onAbrir(c.id)}
        />
      ))}
    </ul>
  );
}

/** Una fila del gestor: una composición con su formato, estado de subtítulos y enlaces. */
function FilaComposicion({
  comp,
  faltaVideo,
  onAbrir,
}: {
  comp: ComposicionResumen;
  /** `undefined` si la composición no tiene pieza ligada; si la tiene, ¿le falta el video? */
  faltaVideo: boolean | undefined;
  onAbrir: () => void;
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

  return (
    <li className="flex flex-wrap items-center gap-3 rounded-md border border-border bg-card p-3">
      <FilmIcon className="h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-mono text-xs text-foreground">{comp.id}</span>
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
            Última edición: {formatearFecha(comp.actualizado)}
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
            <Link to="/operacion/feed/lista" title="Ir a la lista de contenido (pieza ligada)">
              <ExternalLink className="mr-1 h-4 w-4" />
              Pieza
            </Link>
          </Button>
        )}
        <Button type="button" size="sm" variant="outline" onClick={onAbrir}>
          <PencilLine className="mr-1 h-4 w-4" />
          Abrir
        </Button>
      </div>
    </li>
  );
}

/** Fecha ISO → `dd/mm/aa hh:mm` (es-MX); vacío si no hay dato. */
function formatearFecha(iso: string | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-MX", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
