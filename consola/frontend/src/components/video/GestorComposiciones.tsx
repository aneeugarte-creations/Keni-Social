/**
 * GESTOR de composiciones de video (= gestor de transcripciones).
 *
 * Rejilla de TARJETAS a ancho completo de las composiciones de la MARCA ACTIVA. Cada tarjeta
 * muestra formato, última edición, el ESTADO de subtítulos (pendiente/transcrito/editado/listo)
 * y si la pieza ligada (`publicacion_id`) ya tiene su video adjunto o le falta. El modelo de
 * interacción es item-first: clic en la tarjeta = abrir en el editor (`?composicion=<id>`); clic
 * en el título = renombrar inline; las acciones secundarias viven en el menú contextual + kebab.
 *
 * Honestidad: el estado de subtítulos sale de `GET /api/video/subtitulos` por composición; el
 * estado de "video adjunto" sale de la pieza ligada (`falta_video`). No publica nada.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Captions, Copy, ExternalLink, FilmIcon, PencilLine, Trash2, VideoOff } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
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
  const duplicar = useMutation({
    mutationFn: (c: ComposicionResumen) =>
      api.video.crearComposicion({
        marca,
        documento: c.documento,
        titulo: `${c.titulo?.trim() || c.id} (copia)`,
        estado: "borrador",
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["video-composiciones", marca] });
      toast.success("Composición duplicada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Piezas de la marca, para mapear `publicacion_id -> falta_video` (¿ya tiene su mp4?).
  const pubsQ = useQuery({
    queryKey: ["piezas-falta-video", marca],
    queryFn: ({ signal }) =>
      api.piezas({ marca }, signal).then((r) => r.piezas),
    enabled: !!marca,
  });

  // Map publicacion_id -> { faltaVideo } a partir de las piezas de esa pieza/contenido.
  const estadoPieza = React.useMemo(() => {
    const m = new Map<string, { faltaVideo: boolean }>();
    for (const p of pubsQ.data ?? []) {
      if (!p.publicacion_id) continue;
      const prev = m.get(p.publicacion_id);
      // Una pieza (contenido) tiene varias piezas (una por red); con que UNA tenga video,
      // el contenido tiene su render. "falta" sólo si NINGUNA lo tiene.
      const faltaVideo = (prev?.faltaVideo ?? true) && !p.video;
      m.set(p.publicacion_id, { faltaVideo });
    }
    return m;
  }, [pubsQ.data]);

  if (!marca) {
    return (
      <p className="rounded-xl border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">
        Selecciona una marca para ver sus composiciones de video.
      </p>
    );
  }

  if (compsQ.isLoading) {
    return <p className="p-2 text-sm text-muted-foreground">Cargando composiciones…</p>;
  }

  if (compsQ.isError) {
    return (
      <p className="rounded-xl border border-dashed bg-muted/20 p-3 text-sm text-muted-foreground">
        No se pudieron cargar las composiciones.
      </p>
    );
  }

  const comps = compsQ.data ?? [];

  if (comps.length === 0) {
    return (
      <p className="rounded-xl border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
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
        <p className="rounded-xl border border-dashed bg-muted/20 p-4 text-sm text-muted-foreground">
          No hay composiciones.
        </p>
      ) : (
        <ul
          className="grid list-none grid-cols-1 gap-3 p-0 sm:grid-cols-2 xl:grid-cols-3"
          aria-label="Mis composiciones de video"
        >
          {visibles.map((c) => (
            <TarjetaComposicion
              key={c.id}
              comp={c}
              faltaVideo={c.publicacion_id ? estadoPieza.get(c.publicacion_id)?.faltaVideo : undefined}
              onAbrir={() => onAbrir(c.id)}
              onRenombrar={(titulo) => renombrar.mutate({ id: c.id, titulo })}
              onDuplicar={() => duplicar.mutate(c)}
              onEliminar={() => eliminar.mutate(c.id)}
              eliminando={eliminar.isPending && eliminar.variables === c.id}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

/** Una tarjeta del gestor: una composición con su título, estado, formato, subtítulos y enlaces. */
function TarjetaComposicion({
  comp,
  faltaVideo,
  onAbrir,
  onRenombrar,
  onDuplicar,
  onEliminar,
  eliminando,
}: {
  comp: ComposicionResumen;
  /** `undefined` si la composición no tiene pieza ligada; si la tiene, ¿le falta el video? */
  faltaVideo: boolean | undefined;
  onAbrir: () => void;
  onRenombrar: (titulo: string) => void;
  onDuplicar: () => void;
  onEliminar: () => void;
  eliminando: boolean;
}) {
  const navigate = useNavigate();

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

  // Renombrado inline: el título es un botón; al hacer clic entra en edición. Enter/blur
  // confirman, Escape cancela. `commitHecho` evita el doble commit Enter→blur.
  const [editando, setEditando] = React.useState(false);
  const [borrador, setBorrador] = React.useState(comp.titulo ?? "");
  const commitHecho = React.useRef(false);

  function iniciarEdicion() {
    setBorrador(comp.titulo ?? "");
    commitHecho.current = false;
    setEditando(true);
  }

  function confirmarRenombre() {
    if (commitHecho.current) return;
    commitHecho.current = true;
    setEditando(false);
    const t = borrador.trim();
    if (t && t !== (comp.titulo ?? "")) onRenombrar(t);
  }

  async function pedirEliminar() {
    if (
      await confirmar({
        titulo: "Eliminar composición",
        mensaje: `¿Eliminar «${tituloMostrado}»? Esta acción no se puede deshacer.`,
        destructivo: true,
        textoConfirmar: "Eliminar",
      })
    ) {
      onEliminar();
    }
  }

  const acciones: EntradaMenuContextual[] = [
    { etiqueta: "Abrir", icono: FilmIcon, onClick: onAbrir },
    { etiqueta: "Renombrar", icono: PencilLine, onClick: iniciarEdicion },
    { etiqueta: "Duplicar", icono: Copy, onClick: onDuplicar },
    ...(comp.publicacion_id
      ? [
          {
            etiqueta: "Ir a la pieza",
            icono: ExternalLink,
            onClick: () => navigate("/operacion/feed/lista"),
          } as EntradaMenuContextual,
        ]
      : []),
    { separador: true },
    {
      etiqueta: "Eliminar",
      icono: Trash2,
      destructivo: true,
      deshabilitado: eliminando,
      onClick: () => void pedirEliminar(),
    },
  ];

  return (
    <FilaConAcciones
      como="li"
      realce
      kebab="hover"
      onPrimaria={onAbrir}
      acciones={acciones}
      etiquetaAcciones={`Acciones de ${tituloMostrado}`}
      className="flex gap-3 rounded-xl border bg-card p-3"
    >
      <FilmIcon className="h-5 w-5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2 pr-7">
          {editando ? (
            <input
              autoFocus
              type="text"
              value={borrador}
              onChange={(e) => setBorrador(e.target.value)}
              onBlur={confirmarRenombre}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.stopPropagation();
                  confirmarRenombre();
                } else if (e.key === "Escape") {
                  e.stopPropagation();
                  commitHecho.current = true;
                  setEditando(false);
                }
              }}
              aria-label="Nuevo título"
              className="min-w-0 flex-1 rounded border border-border bg-background px-1.5 py-0.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          ) : (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                iniciarEdicion();
              }}
              title="Clic para renombrar"
              className="min-w-0 truncate text-left text-sm font-medium text-foreground hover:text-keni-600"
            >
              {tituloMostrado}
            </button>
          )}
          <Badge variant={estadoComp === "listo" ? "ok" : "aviso"}>
            {ETIQUETA_ESTADO_COMPOSICION[estadoComp] ?? estadoComp}
          </Badge>
          <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            {preset}
          </span>
          {!tieneBase && <Badge variant="aviso">Sin clip base</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
          <span title={comp.actualizado}>
            Última edición: {formatearFechaHora(comp.actualizado) || "—"}
          </span>
          <span className="inline-flex items-center gap-1">
            <Captions className="h-3 w-3" />
            {ETIQUETA_ESTADO_SUBS[estadoSubs] ?? estadoSubs}
          </span>
          {comp.publicacion_id ? (
            faltaVideo === true ? (
              <Badge variant="aviso" className="gap-1">
                <VideoOff className="h-3 w-3" />
                Falta el video en la pieza
              </Badge>
            ) : faltaVideo === false ? (
              <Badge variant="ok" className="gap-1">
                <FilmIcon className="h-3 w-3" />
                Video adjunto a la pieza
              </Badge>
            ) : null
          ) : (
            <span>Sin pieza ligada</span>
          )}
        </div>
      </div>
    </FilaConAcciones>
  );
}
