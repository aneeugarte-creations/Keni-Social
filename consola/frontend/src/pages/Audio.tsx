/**
 * Gestor de Audio — audio→texto integral, por ARTEFACTOS.
 *
 * Subes un audio o vídeo y eliges qué crear: el SRT va siempre; además puedes pedir texto plano y
 * los tratamientos de Claude (limpio, resumen, preguntas, ideas). Cada uno es un ARTEFACTO
 * independiente que aparece en su lista y se genera en segundo plano.
 *
 * UI de 3 paneles: audios · artefactos del audio · contenido del artefacto. Los dos paneles
 * izquierdos se colapsan para leer a ancho completo (como el lector de contexto). El contenido es
 * editable (salvo el SRT crudo) y los artefactos markdown se renderizan.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  Eraser,
  FileText,
  HelpCircle,
  Lightbulb,
  Loader2,
  Plus,
  RefreshCw,
  SpellCheck,
  Trash2,
  Upload,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Markdown } from "@/components/ui/Markdown";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  ArtefactoAudio,
  EstadoTranscripcion,
  TipoArtefacto,
  TranscripcionAudio,
  TratamientoClaude,
} from "@/lib/api/audio";

const EN_PROCESO: EstadoTranscripcion[] = ["pendiente", "transcribiendo"];

const ETIQUETA_ESTADO: Record<EstadoTranscripcion, string> = {
  pendiente: "En cola",
  transcribiendo: "Transcribiendo…",
  transcrito: "Transcrito",
  editado: "Editado",
  error: "Error",
};

// Tratamientos elegibles al subir (además del SRT, que va siempre).
const TRATAMIENTOS_SUBIDA: { tipo: TipoArtefacto; etiqueta: string }[] = [
  { tipo: "texto", etiqueta: "Texto plano" },
  { tipo: "limpio", etiqueta: "Limpiar" },
  { tipo: "resumen", etiqueta: "Resumen" },
  { tipo: "preguntas", etiqueta: "Preguntas" },
  { tipo: "ideas", etiqueta: "Ideas" },
];

// Tratamientos de Claude que se pueden añadir a mano a un audio ya transcrito. `desc` explica qué
// hace cada uno (tooltip al pasar el ratón).
const TRATAMIENTOS_CLAUDE: {
  tipo: TratamientoClaude;
  etiqueta: string;
  Icono: typeof Eraser;
  desc: string;
}[] = [
  {
    tipo: "limpio",
    etiqueta: "Limpiar",
    Icono: Eraser,
    desc: "Quita muletillas, silencios y repeticiones sin cambiar el sentido.",
  },
  { tipo: "resumen", etiqueta: "Resumen", Icono: FileText, desc: "Resumen breve del contenido." },
  {
    tipo: "preguntas",
    etiqueta: "Preguntas",
    Icono: HelpCircle,
    desc: "Detecta frases que no se entienden y te pregunta para corregirlas.",
  },
  {
    tipo: "ideas",
    etiqueta: "Ideas",
    Icono: Lightbulb,
    desc: "Extrae las ideas clave para reutilizarlas como contenido.",
  },
];

// Icono por tipo de artefacto (lista y raíl colapsado).
const ICONO_ARTEFACTO: Record<TipoArtefacto, typeof Eraser> = {
  srt: FileText,
  texto: FileText,
  limpio: Eraser,
  resumen: FileText,
  preguntas: HelpCircle,
  ideas: Lightbulb,
  corregido: SpellCheck,
};

const EXT_ARTEFACTO: Record<string, string> = { srt: "srt", md: "md", txt: "txt" };

function fmtDur(ms: number): string {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export default function Audio() {
  const { marcaActiva, marcaPrimaria } = useMarcaActiva();
  const marca = marcaActiva ?? marcaPrimaria ?? "";
  const qc = useQueryClient();

  const [audioId, setAudioId] = React.useState<string | null>(null);
  const [artefactoId, setArtefactoId] = React.useState<string | null>(null);
  const [panelesAbiertos, setPanelesAbiertos] = React.useState(true);
  const [dialogo, setDialogo] = React.useState(false);

  // Lista de audios (todos: la herramienta no filtra por marca activa).
  const audios = useQuery({
    queryKey: ["audio", "transcripciones"],
    queryFn: ({ signal }) => api.audio.transcripciones({}, signal),
    refetchInterval: (q) =>
      (q.state.data?.transcripciones ?? []).some((t) => EN_PROCESO.includes(t.estado)) ? 2500 : false,
  });
  const lista = audios.data?.transcripciones ?? [];
  const audio = lista.find((t) => t.id === audioId) ?? null;

  // Artefactos del audio seleccionado; se resondea mientras el ASR corre o haya artefactos generándose.
  const arts = useQuery({
    queryKey: ["audio", "artefactos", audioId],
    queryFn: ({ signal }) => api.audio.artefactos(audioId as string, signal),
    enabled: audioId !== null,
    refetchInterval: (q) => {
      const generando = (q.state.data?.artefactos ?? []).some((a) => a.estado === "generando");
      const enAsr = audio ? EN_PROCESO.includes(audio.estado) : false;
      return generando || enAsr ? 2500 : false;
    },
  });
  const artefactos = arts.data?.artefactos ?? [];
  const artefacto = artefactos.find((a) => a.id === artefactoId) ?? null;

  // Al cambiar de audio, selecciona su primer artefacto (SRT) en cuanto carguen.
  React.useEffect(() => {
    if (audioId === null) return;
    if (artefactos.length && !artefactos.some((a) => a.id === artefactoId)) {
      setArtefactoId(artefactos[0].id);
    }
  }, [audioId, artefactos, artefactoId]);

  const subir = useMutation({
    mutationFn: async (v: { archivo: File; tratamientos: TipoArtefacto[] }) => {
      const form = new FormData();
      form.append("archivo", v.archivo);
      form.append("marca", marca);
      form.append("nombre", v.archivo.name);
      v.tratamientos.forEach((t) => form.append("tratamientos", t));
      return api.audio.crear(form);
    },
    onSuccess: (r) => {
      setDialogo(false);
      setAudioId(r.transcripcion.id);
      setArtefactoId(null);
      qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
      toast.success("Audio subido. Transcribiendo…");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminarAudio = useMutation({
    mutationFn: (id: string) => api.audio.eliminar(id),
    onSuccess: (_d, id) => {
      if (audioId === id) {
        setAudioId(null);
        setArtefactoId(null);
      }
      qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const refetchArtefactos = () =>
    qc.invalidateQueries({ queryKey: ["audio", "artefactos", audioId] });

  const vacioTotal = !audios.isLoading && lista.length === 0;

  return (
    <div className="flex min-h-[calc(100dvh-8rem)] flex-col gap-4">
      {/* El título se portaliza a la barra superior; «Subir» va a su lado (hueco de acciones). */}
      <TituloPagina titulo="Audio" icono={AudioLines} />
      {!vacioTotal ? (
        <AccionesPagina>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setDialogo(true)}
            disabled={!marca}
            className="gap-2"
          >
            <Upload className="h-4 w-4" /> Subir
          </Button>
        </AccionesPagina>
      ) : null}

      {vacioTotal ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3">
          <Button
            variant="outline"
            onClick={() => setDialogo(true)}
            disabled={!marca}
            className="gap-2"
          >
            <Upload className="h-4 w-4" />
            Subir audio o vídeo
          </Button>
          <p className="text-xs text-muted-foreground">
            {marca ? "Se extrae la voz y se transcribe con timestamps" : "Selecciona una marca primero"}
          </p>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 gap-3">
          {/* IZQUIERDA: doble panel (audios · artefactos), SIEMPRE presente. Expandido = listas;
              colapsado = raíl estrecho de iconos que SIGUE navegable (como el lector de contexto).
              El chevron al pie alterna; al colapsar el lector gana el ancho. */}
          <aside className={cn("flex shrink-0 flex-col", panelesAbiertos ? "w-[28rem]" : "w-auto")}>
            <div
              className={cn(
                "flex h-full min-h-0 flex-col rounded-md border border-border bg-card",
                panelesAbiertos ? "p-2" : "p-1",
              )}
            >
              {panelesAbiertos ? (
                <div className="flex min-h-0 flex-1 gap-2">
                  <PanelAudios
                    className="w-1/2"
                    lista={lista}
                    cargando={audios.isLoading}
                    audioId={audioId}
                    onSeleccionar={(id) => {
                      setAudioId(id);
                      setArtefactoId(null);
                    }}
                    onEliminar={(id) => eliminarAudio.mutate(id)}
                  />
                  <div className="w-px shrink-0 bg-border" />
                  <PanelArtefactos
                    className="flex-1"
                    audio={audio}
                    artefactos={artefactos}
                    cargando={arts.isLoading}
                    artefactoId={artefactoId}
                    onSeleccionar={setArtefactoId}
                  />
                </div>
              ) : (
                <RailColapsado
                  lista={lista}
                  audioId={audioId}
                  onSeleccionarAudio={(id) => {
                    setAudioId(id);
                    setArtefactoId(null);
                  }}
                  artefactos={artefactos}
                  artefactoId={artefactoId}
                  onSeleccionarArtefacto={setArtefactoId}
                />
              )}
              <Button
                size="icon"
                variant="ghost"
                className={cn("h-8 w-8 shrink-0 self-center", panelesAbiertos && "mt-2")}
                aria-label={panelesAbiertos ? "Colapsar paneles" : "Expandir paneles"}
                title={panelesAbiertos ? "Colapsar (leer a ancho completo)" : "Expandir paneles"}
                onClick={() => setPanelesAbiertos((v) => !v)}
              >
                {panelesAbiertos ? (
                  <ChevronLeft className="h-4 w-4" />
                ) : (
                  <ChevronRight className="h-4 w-4" />
                )}
              </Button>
            </div>
          </aside>

          {/* DERECHA: barra superior (tratamientos + acciones) sobre el lector del artefacto. */}
          <Lector
            audio={audio}
            artefacto={artefacto}
            onSeleccionarArtefacto={setArtefactoId}
            onCambio={refetchArtefactos}
          />
        </div>
      )}

      <DialogoSubida
        abierto={dialogo}
        onAbierto={setDialogo}
        subiendo={subir.isPending}
        onSubir={(archivo, tratamientos) => subir.mutate({ archivo, tratamientos })}
      />
    </div>
  );
}

function Vacio({ texto }: { texto: string }) {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
      <AudioLines className="h-8 w-8 opacity-40" />
      <p>{texto}</p>
    </div>
  );
}

function EstadoBadge({ estado }: { estado: EstadoTranscripcion }) {
  const variante =
    estado === "error" ? "destructive" : estado === "transcrito" || estado === "editado" ? "secondary" : "outline";
  return (
    <Badge variant={variante} className="px-1.5 py-0 text-[10px] font-normal">
      {ETIQUETA_ESTADO[estado]}
    </Badge>
  );
}

// Raíl estrecho del panel colapsado: iconos de audio (arriba) y, debajo, los artefactos del audio
// activo. Sigue navegable —clicar selecciona— igual que el raíl de versiones del lector de contexto.
function RailColapsado({
  lista,
  audioId,
  onSeleccionarAudio,
  artefactos,
  artefactoId,
  onSeleccionarArtefacto,
}: {
  lista: TranscripcionAudio[];
  audioId: string | null;
  onSeleccionarAudio: (id: string) => void;
  artefactos: ArtefactoAudio[];
  artefactoId: string | null;
  onSeleccionarArtefacto: (id: string) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto">
      {lista.map((t) => {
        const activo = t.id === audioId;
        return (
          <Tooltip key={t.id} label={t.nombre || "Sin título"} side="right">
            <button
              type="button"
              onClick={() => onSeleccionarAudio(t.id)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent",
                activo && "bg-accent text-primary",
              )}
            >
              <AudioLines className="h-4 w-4" />
            </button>
          </Tooltip>
        );
      })}
      {audioId && artefactos.length ? (
        <>
          <div className="my-1 h-px w-5 bg-border" />
          {artefactos.map((a) => {
            const activo = a.id === artefactoId;
            const Icono = ICONO_ARTEFACTO[a.tipo] ?? FileText;
            return (
              <Tooltip
                key={a.id}
                label={a.titulo || TITULO_ARTEFACTO[a.tipo] || a.tipo}
                side="right"
              >
                <button
                  type="button"
                  onClick={() => onSeleccionarArtefacto(a.id)}
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent",
                    activo && "bg-accent text-primary",
                  )}
                >
                  {a.estado === "generando" ? (
                    <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                  ) : (
                    <Icono className="h-4 w-4" />
                  )}
                </button>
              </Tooltip>
            );
          })}
        </>
      ) : null}
    </div>
  );
}

function PanelAudios({
  className,
  lista,
  cargando,
  audioId,
  onSeleccionar,
  onEliminar,
}: {
  className?: string;
  lista: TranscripcionAudio[];
  cargando: boolean;
  audioId: string | null;
  onSeleccionar: (id: string) => void;
  onEliminar: (id: string) => void;
}) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-2 overflow-hidden", className)}>
      <span className="px-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Audios
      </span>
      {cargando ? (
        <p className="px-1 text-xs text-muted-foreground">Cargando…</p>
      ) : (
        <div className="flex flex-col gap-1.5 overflow-y-auto">
          {lista.map((t) => {
            const activo = t.id === audioId;
            return (
              <div
                key={t.id}
                className={`group flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-sm ${
                  activo ? "border-primary/60 bg-primary/5" : "border-border/70 bg-card hover:bg-muted/40"
                }`}
              >
                <button type="button" onClick={() => onSeleccionar(t.id)} className="flex min-w-0 flex-1 flex-col items-start">
                  <span className="w-full truncate font-medium">{t.nombre || "Sin título"}</span>
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <EstadoBadge estado={t.estado} />
                    {t.duracion_ms > 0 ? <span>{fmtDur(t.duracion_ms)}</span> : null}
                    {t.marca_nombre ? <span className="truncate">· {t.marca_nombre}</span> : null}
                  </span>
                </button>
                <button
                  type="button"
                  title="Eliminar"
                  onClick={() => onEliminar(t.id)}
                  className="shrink-0 rounded p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const TITULO_ARTEFACTO: Record<TipoArtefacto, string> = {
  srt: "Subtítulos (SRT)",
  texto: "Texto plano",
  limpio: "Limpio",
  resumen: "Resumen",
  preguntas: "Preguntas",
  ideas: "Ideas",
  corregido: "Corregido",
};

function PanelArtefactos({
  className,
  audio,
  artefactos,
  cargando,
  artefactoId,
  onSeleccionar,
}: {
  className?: string;
  audio: TranscripcionAudio | null;
  artefactos: ArtefactoAudio[];
  cargando: boolean;
  artefactoId: string | null;
  onSeleccionar: (id: string) => void;
}) {
  const qc = useQueryClient();
  const reintentar = useMutation({
    mutationFn: () => api.audio.retranscribir(audio!.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
      toast.success("Reintentando…");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (!audio) {
    return (
      <div className={cn("flex min-w-0 flex-col gap-2", className)}>
        <span className="px-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
          Artefactos
        </span>
        <p className="px-1 text-xs text-muted-foreground">Elige un audio.</p>
      </div>
    );
  }
  return (
    <div className={cn("flex min-w-0 flex-col gap-2 overflow-hidden", className)}>
      <span className="px-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        Artefactos
      </span>
      {EN_PROCESO.includes(audio.estado) ? (
        <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/30 px-2.5 py-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" /> Transcribiendo…
        </div>
      ) : null}
      {audio.estado === "error" ? (
        <div className="flex flex-col gap-1.5 rounded-lg border border-destructive/40 bg-destructive/5 px-2.5 py-2 text-xs text-destructive">
          <span>{audio.error || "No se pudo transcribir."}</span>
          <Button size="sm" variant="outline" onClick={() => reintentar.mutate()} disabled={reintentar.isPending}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Reintentar
          </Button>
        </div>
      ) : null}

      {cargando ? (
        <p className="px-1 text-xs text-muted-foreground">Cargando…</p>
      ) : (
        <div className="flex flex-col gap-1.5 overflow-y-auto">
          {artefactos.map((a) => {
            const activo = a.id === artefactoId;
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => onSeleccionar(a.id)}
                className={`flex items-center justify-between gap-1.5 rounded-lg border px-2.5 py-2 text-left text-sm ${
                  activo ? "border-primary/60 bg-primary/5" : "border-border/70 bg-card hover:bg-muted/40"
                }`}
              >
                <span className="truncate font-medium">{a.titulo || TITULO_ARTEFACTO[a.tipo] || a.tipo}</span>
                {a.estado === "generando" ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                ) : a.estado === "error" ? (
                  <Badge variant="destructive" className="px-1.5 py-0 text-[10px] font-normal">Error</Badge>
                ) : (
                  <span className="shrink-0 text-[10px] uppercase text-muted-foreground">{a.formato}</span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Lector({
  audio,
  artefacto,
  onSeleccionarArtefacto,
  onCambio,
}: {
  audio: TranscripcionAudio | null;
  artefacto: ArtefactoAudio | null;
  onSeleccionarArtefacto: (id: string) => void;
  onCambio: () => void;
}) {
  const editable = !!artefacto && artefacto.tipo !== "srt";
  const esMd = artefacto?.formato === "md";
  const [editando, setEditando] = React.useState(false);
  const [texto, setTexto] = React.useState(artefacto?.contenido ?? "");
  React.useEffect(() => {
    setTexto(artefacto?.contenido ?? "");
    setEditando(false);
  }, [artefacto?.id, artefacto?.contenido]);

  const crear = useMutation({
    mutationFn: (tipo: TratamientoClaude) => api.audio.crearArtefacto(audio!.id, tipo),
    onSuccess: (r) => {
      onCambio();
      onSeleccionarArtefacto(r.artefacto.id);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardar = useMutation({
    mutationFn: () => api.audio.guardarArtefacto(artefacto!.id, { contenido: texto }),
    onSuccess: () => {
      setEditando(false);
      onCambio();
      toast.success("Guardado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descargar = () => {
    if (!artefacto) return;
    const ext = EXT_ARTEFACTO[artefacto.formato] || "txt";
    const blob = new Blob([artefacto.contenido], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(artefacto.titulo || artefacto.tipo).replace(/\s+/g, "-").toLowerCase()}.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const transcrito = !!audio && (audio.estado === "transcrito" || audio.estado === "editado");
  const acciones = !!artefacto && artefacto.estado === "listo";

  return (
    <section className="flex min-w-0 flex-1 flex-col gap-2">
      {/* Barra superior: tratamientos (con tooltip que explica cada uno) a la izquierda; acciones
          del artefacto a la derecha. */}
      <div className="flex min-h-9 flex-wrap items-center gap-2">
        {transcrito ? (
          <div className="flex flex-wrap items-center gap-1">
            {TRATAMIENTOS_CLAUDE.map(({ tipo, etiqueta, Icono, desc }) => (
              <Tooltip key={tipo} label={desc} side="bottom">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 px-2 text-xs"
                  disabled={crear.isPending}
                  onClick={() => crear.mutate(tipo)}
                >
                  {crear.isPending && crear.variables === tipo ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Icono className="h-3 w-3" />
                  )}
                  {etiqueta}
                </Button>
              </Tooltip>
            ))}
          </div>
        ) : null}
        {acciones ? (
          <div className="ml-auto flex items-center gap-2">
            {editable ? (
              <Button size="sm" variant="ghost" onClick={() => setEditando((v) => !v)}>
                {editando ? "Vista" : "Editar"}
              </Button>
            ) : null}
            <Button size="sm" variant="outline" onClick={descargar} className="gap-1.5">
              <Download className="h-3.5 w-3.5" /> Descargar
            </Button>
          </div>
        ) : null}
      </div>

      {/* Lector del artefacto seleccionado. */}
      <div className="flex min-h-0 flex-1 flex-col rounded-md border border-border bg-card p-4">
        {!audio ? (
          <Vacio texto="Elige un audio de la lista." />
        ) : EN_PROCESO.includes(audio.estado) ? (
          <Vacio texto="Transcribiendo… los artefactos aparecerán aquí." />
        ) : !artefacto ? (
          <Vacio texto="Elige un artefacto." />
        ) : artefacto.estado === "generando" ? (
          <div className="flex flex-1 items-center justify-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Generando «{artefacto.titulo}»…
          </div>
        ) : artefacto.estado === "error" ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {artefacto.error || "Este tratamiento falló."}
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            <h2 className="text-lg font-semibold">
              {artefacto.titulo || TITULO_ARTEFACTO[artefacto.tipo]}
            </h2>
            {editando && editable ? (
              <div className="flex min-h-0 flex-1 flex-col gap-2">
                <Textarea
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  className="min-h-[16rem] flex-1 font-mono text-sm"
                />
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setTexto(artefacto.contenido)}>
                    Descartar
                  </Button>
                  <Button
                    size="sm"
                    disabled={guardar.isPending || texto === artefacto.contenido}
                    onClick={() => guardar.mutate()}
                  >
                    <Check className="mr-1.5 h-3.5 w-3.5" /> Guardar
                  </Button>
                </div>
              </div>
            ) : esMd ? (
              <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-border/70 bg-background p-4">
                <Markdown>{artefacto.contenido || "_(vacío)_"}</Markdown>
              </div>
            ) : (
              <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-lg border border-border/70 bg-background p-4 font-mono text-sm">
                {artefacto.contenido || "(vacío)"}
              </pre>
            )}

            {artefacto.tipo === "preguntas" ? (
              <PanelCorregir artefacto={artefacto} onCambio={onCambio} />
            ) : null}
          </div>
        )}
      </div>
    </section>
  );
}

function PanelCorregir({ artefacto, onCambio }: { artefacto: ArtefactoAudio; onCambio: () => void }) {
  const [respuestas, setRespuestas] = React.useState("");
  const corregir = useMutation({
    mutationFn: () =>
      api.audio.corregir(
        artefacto.id,
        respuestas.split("\n").map((s) => s.trim()).filter(Boolean),
      ),
    onSuccess: () => {
      setRespuestas("");
      onCambio();
      toast.success("Aplicando correcciones… verás el artefacto «Corregido».");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  return (
    <div className="rounded-lg border border-border/70 bg-muted/20 p-3">
      <label className="text-xs font-medium text-muted-foreground">
        Responde a las dudas (una por línea) y genera el «Corregido»:
      </label>
      <Textarea
        value={respuestas}
        onChange={(e) => setRespuestas(e.target.value)}
        rows={3}
        className="mt-1.5"
        placeholder="Ej.: El apellido correcto es Mbappé&#10;Ganó el América"
      />
      <div className="mt-2 flex justify-end">
        <Button size="sm" disabled={!respuestas.trim() || corregir.isPending} onClick={() => corregir.mutate()}>
          <SpellCheck className="mr-1.5 h-3.5 w-3.5" /> Corregir con estas respuestas
        </Button>
      </div>
    </div>
  );
}

function DialogoSubida({
  abierto,
  onAbierto,
  subiendo,
  onSubir,
}: {
  abierto: boolean;
  onAbierto: (v: boolean) => void;
  subiendo: boolean;
  onSubir: (archivo: File, tratamientos: TipoArtefacto[]) => void;
}) {
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [sel, setSel] = React.useState<Record<string, boolean>>({});
  React.useEffect(() => {
    if (!abierto) {
      setArchivo(null);
      setSel({});
    }
  }, [abierto]);

  const tratamientos = TRATAMIENTOS_SUBIDA.filter((t) => sel[t.tipo]).map((t) => t.tipo);

  return (
    <Dialog open={abierto} onOpenChange={onAbierto}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Subir audio o vídeo</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div>
            <input
              type="file"
              accept="audio/*,video/*"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border file:border-border file:bg-muted file:px-3 file:py-1.5 file:text-sm"
            />
            <p className="mt-1 text-xs text-muted-foreground">Se extrae la voz y se transcribe con timestamps (SRT por defecto).</p>
          </div>
          <div>
            <p className="mb-2 text-sm font-medium">Crear además:</p>
            <div className="grid grid-cols-2 gap-2">
              {TRATAMIENTOS_SUBIDA.map((t) => (
                <label key={t.tipo} className="flex cursor-pointer items-center gap-2 text-sm">
                  <Checkbox
                    checked={!!sel[t.tipo]}
                    onCheckedChange={(c) => setSel((s) => ({ ...s, [t.tipo]: c }))}
                  />
                  {t.etiqueta}
                </label>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onAbierto(false)}>
            Cancelar
          </Button>
          <Button disabled={!archivo || subiendo} onClick={() => archivo && onSubir(archivo, tratamientos)} className="gap-2">
            {subiendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Transcribir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
