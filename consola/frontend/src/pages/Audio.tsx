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
  Pause,
  Play,
  Plus,
  RefreshCw,
  SpellCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
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
                    onCambio={refetchArtefactos}
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
            artefactos={artefactos}
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

// Orden canónico en que se pintan los documentos de un audio.
const ORDEN_ARTEFACTO: TipoArtefacto[] = [
  "srt",
  "texto",
  "limpio",
  "resumen",
  "preguntas",
  "ideas",
  "corregido",
];

const FASE_LEGIBLE: Record<string, string> = {
  "extrayendo audio": "Extrayendo la pista de voz…",
  transcribiendo: "Transcribiendo el audio…",
  "generando artefactos": "Creando los documentos…",
  razonando: "Razonando…",
  generando: "Escribiendo…",
};

// Vista VIVA y DESECHABLE de un job: confirma que está corriendo (no pillado). Para whisper muestra
// la fase del motor; para claude streamea el texto token a token. Enlaza a Actividad IA.
function ProgresoVivo({
  genId,
  modo,
  onCerrar,
}: {
  genId: string;
  modo: "whisper" | "claude";
  onCerrar?: () => void;
}) {
  const q = useQuery({
    queryKey: ["audio", "gen", genId],
    queryFn: ({ signal }) => api.generacion(genId, signal),
    enabled: !!genId,
    refetchInterval: (query) => {
      const est = query.state.data?.generacion?.estado;
      return est === "completado" || est === "error" ? false : 1200;
    },
  });
  const g = q.data?.generacion;
  const corriendo = !g || (g.estado !== "completado" && g.estado !== "error");
  const fase = g?.fase ? FASE_LEGIBLE[g.fase] ?? g.fase : "En cola…";
  const salida = g?.salida ?? "";

  return (
    <div className="flex min-h-0 flex-col gap-1.5 rounded-md border border-border/70 bg-muted/20 p-2.5">
      <div className="flex items-center gap-2">
        {corriendo ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
        ) : g?.estado === "error" ? (
          <X className="h-3.5 w-3.5 shrink-0 text-destructive" />
        ) : (
          <Check className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
          {g?.estado === "error" ? g.error || "Falló." : fase}
        </span>
        <Link
          to={`/maquina/actividad/generacion/${encodeURIComponent(genId)}`}
          className="shrink-0 text-xs text-muted-foreground underline-offset-2 hover:underline"
        >
          Ver en Actividad
        </Link>
        {onCerrar ? (
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Ocultar progreso"
            className="shrink-0 rounded p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
      {modo === "claude" && salida ? (
        <pre className="max-h-40 min-h-0 overflow-auto whitespace-pre-wrap rounded border border-border/60 bg-background p-2 font-mono text-xs text-muted-foreground">
          {salida}
        </pre>
      ) : null}
    </div>
  );
}

function EstadoBadge({ estado }: { estado: EstadoTranscripcion }) {
  const variante =
    estado === "error" ? "destructive" : estado === "transcrito" || estado === "editado" ? "secondary" : "outline";
  return (
    <Badge variant={variante} className="px-1.5 py-0 text-xs font-normal">
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
      <span className="px-1 text-label">Audios</span>
      {cargando ? (
        <p className="px-1 text-xs text-muted-foreground">Cargando…</p>
      ) : (
        <div className="flex flex-col gap-1 overflow-y-auto">
          {lista.map((t) => {
            const activo = t.id === audioId;
            return (
              <div
                key={t.id}
                className={`group flex items-center gap-1.5 rounded-md border px-2 py-1.5 text-xs ${
                  activo ? "border-primary/60 bg-primary/5" : "border-border/70 bg-card hover:bg-muted/40"
                }`}
              >
                <button type="button" onClick={() => onSeleccionar(t.id)} className="flex min-w-0 flex-1 flex-col items-start gap-0.5">
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
                  <Trash2 className="h-3.5 w-3.5" />
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
  onCambio,
}: {
  className?: string;
  audio: TranscripcionAudio | null;
  artefactos: ArtefactoAudio[];
  cargando: boolean;
  artefactoId: string | null;
  onSeleccionar: (id: string) => void;
  onCambio: () => void;
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
  const borrar = useMutation({
    mutationFn: (id: string) => api.audio.eliminarArtefacto(id),
    onSuccess: () => onCambio(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (!audio) {
    return (
      <div className={cn("flex min-w-0 flex-col gap-2", className)}>
        <span className="px-1 text-label">Artefactos</span>
        <p className="px-1 text-xs text-muted-foreground">Elige un audio.</p>
      </div>
    );
  }
  // Mientras corre el lote (transcribiendo o con algún artefacto generándose), PINTA también los
  // documentos que se van a crear (SRT + tratamientos elegidos) aunque aún no exista su fila.
  const enLote =
    EN_PROCESO.includes(audio.estado) || artefactos.some((a) => a.estado === "generando");
  const tiposReales = new Set(artefactos.map((a) => a.tipo));
  const planeados = enLote
    ? ORDEN_ARTEFACTO.filter(
        (t) => (t === "srt" || audio.tratamientos.includes(t)) && !tiposReales.has(t),
      )
    : [];

  return (
    <div className={cn("flex min-w-0 flex-col gap-2 overflow-hidden", className)}>
      <span className="px-1 text-label">Artefactos</span>
      {audio.estado === "error" ? (
        <div className="flex flex-col gap-1.5 rounded-md border border-destructive/40 bg-destructive/5 px-2 py-1.5 text-xs text-destructive">
          <span>{audio.error || "No se pudo transcribir."}</span>
          <Button size="sm" variant="outline" onClick={() => reintentar.mutate()} disabled={reintentar.isPending}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Reintentar
          </Button>
        </div>
      ) : null}

      {cargando && !artefactos.length && !planeados.length ? (
        <p className="px-1 text-xs text-muted-foreground">Cargando…</p>
      ) : (
        <div className="flex flex-col gap-1 overflow-y-auto">
          {artefactos.map((a) => {
            const activo = a.id === artefactoId;
            return (
              <div
                key={a.id}
                className={`group flex items-center gap-1 rounded-md border px-2 py-1.5 text-xs ${
                  activo ? "border-primary/60 bg-primary/5" : "border-border/70 bg-card hover:bg-muted/40"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onSeleccionar(a.id)}
                  className="flex min-w-0 flex-1 items-center justify-between gap-1.5 text-left"
                >
                  <span className="truncate font-medium">{a.titulo || TITULO_ARTEFACTO[a.tipo] || a.tipo}</span>
                  {a.estado === "generando" ? (
                    <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-muted-foreground" />
                  ) : a.estado === "error" ? (
                    <Badge variant="destructive" className="px-1.5 py-0 text-xs font-normal">Error</Badge>
                  ) : (
                    <span className="shrink-0 text-xs uppercase text-muted-foreground">{a.formato}</span>
                  )}
                </button>
                {a.tipo !== "srt" && a.estado !== "generando" ? (
                  <button
                    type="button"
                    title="Eliminar artefacto"
                    onClick={() => borrar.mutate(a.id)}
                    className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            );
          })}
          {/* Documentos planificados (aún sin fila): por crear cuando termine la transcripción. */}
          {planeados.map((t) => {
            const transcribiendo = t === "srt" && EN_PROCESO.includes(audio.estado);
            return (
              <div
                key={`plan:${t}`}
                className="flex items-center justify-between gap-1.5 rounded-md border border-dashed border-border/70 px-2 py-1.5 text-xs text-muted-foreground"
              >
                <span className="truncate">{TITULO_ARTEFACTO[t]}</span>
                {transcribiendo ? (
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                ) : (
                  <span className="shrink-0 text-xs">en cola</span>
                )}
              </div>
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
  artefactos,
  onSeleccionarArtefacto,
  onCambio,
}: {
  audio: TranscripcionAudio | null;
  artefacto: ArtefactoAudio | null;
  artefactos: ArtefactoAudio[];
  onSeleccionarArtefacto: (id: string) => void;
  onCambio: () => void;
}) {
  // El SRT y las 'preguntas' (cajón-formulario) no se editan como texto libre.
  const editable = !!artefacto && artefacto.tipo !== "srt" && artefacto.tipo !== "preguntas";
  const esMd = artefacto?.formato === "md";
  const [editando, setEditando] = React.useState(false);
  const [texto, setTexto] = React.useState(artefacto?.contenido ?? "");
  React.useEffect(() => {
    setTexto(artefacto?.contenido ?? "");
    setEditando(false);
  }, [artefacto?.id, artefacto?.contenido]);

  // Progreso vivo (desechable): se puede ocultar; reaparece al cambiar de audio.
  const [verProgreso, setVerProgreso] = React.useState(true);
  React.useEffect(() => setVerProgreso(true), [audio?.id]);

  // Fuente de un tratamiento NUEVO. Solo valen las bases de CONTENIDO; 'texto' (= SRT sin tiempos)
  // y 'preguntas' (cajón-formulario) NO son fuente: se parte del SRT (subtítulos, con timestamps).
  const srt = artefactos.find((a) => a.tipo === "srt") ?? null;
  const fuente = (artefacto && FUENTES_VALIDAS.has(artefacto.tipo) ? artefacto : srt) ?? null;
  const fuenteLista = !!fuente && fuente.estado === "listo";

  // El cajón de preguntas es ÚNICO por audio: si hay uno utilizable, el botón lo ABRE (no relanza).
  const preguntaAbrible =
    artefactos.find((a) => a.tipo === "preguntas" && a.estado === "listo") ??
    artefactos.find((a) => a.tipo === "preguntas" && a.estado === "generando") ??
    null;

  // ¿ya hay un artefacto de este tipo derivado de la fuente actual, en su versión actual?
  const yaDe = (tipo: TratamientoClaude) =>
    artefactos.find(
      (a) =>
        a.tipo === tipo &&
        a.origen_id === (fuente?.id ?? "") &&
        a.origen_version === (fuente?.actualizado ?? ""),
    ) ?? null;

  const crear = useMutation({
    // 'preguntas' SIEMPRE parte del SRT (necesita timestamps para el snippet de audio); el resto, de
    // la fuente activa.
    mutationFn: (tipo: TratamientoClaude) =>
      api.audio.crearArtefacto(audio!.id, tipo, (tipo === "preguntas" ? srt : fuente)?.id),
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
  // 'preguntas' es un cajón-formulario: sin barra de Editar/Descargar.
  const acciones =
    !!artefacto && artefacto.estado === "listo" && artefacto.tipo !== "preguntas";
  // Herencia del artefacto abierto (si es un tratamiento): de qué deriva.
  const origen =
    artefacto && artefacto.origen_id
      ? artefactos.find((a) => a.id === artefacto.origen_id) ?? null
      : null;
  const esTratamiento = !!artefacto && TIPOS_TRATAMIENTO.has(artefacto.tipo);

  return (
    <section className="flex min-w-0 flex-1 flex-col gap-2">
      {/* Barra superior: tratamientos (con tooltip que explica cada uno) a la izquierda; acciones
          del artefacto a la derecha. */}
      <div className="flex min-h-9 flex-wrap items-center gap-2">
        {transcrito ? (
          <div className="flex flex-wrap items-center gap-1">
            <span className="mr-1 text-xs text-muted-foreground">
              Desde «{fuente ? fuente.titulo || TITULO_ARTEFACTO[fuente.tipo] : "la transcripción"}»:
            </span>
            {TRATAMIENTOS_CLAUDE.map(({ tipo, etiqueta, Icono, desc }) => {
              // 'preguntas' NO se deshabilita ni relanza: si ya hay un cajón, su botón lo ABRE.
              const esPreguntas = tipo === "preguntas";
              const abrir = esPreguntas ? preguntaAbrible : null;
              const ya = esPreguntas ? null : yaDe(tipo);
              const deshab = !!ya;
              const label = deshab
                ? "Ya generado desde esta fuente. Edita la fuente para regenerar."
                : abrir
                  ? "Abre el cajón de preguntas"
                  : desc;
              const cargando = crear.isPending && crear.variables === tipo;
              return (
                <Tooltip key={tipo} label={label} side="bottom">
                  <Button
                    size="sm"
                    variant={abrir ? "secondary" : "ghost"}
                    className="h-7 gap-1 px-2 text-xs"
                    disabled={crear.isPending || deshab || (!abrir && !fuenteLista)}
                    onClick={() =>
                      abrir ? onSeleccionarArtefacto(abrir.id) : crear.mutate(tipo)
                    }
                  >
                    {cargando ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <Icono className="h-3 w-3" />
                    )}
                    {etiqueta}
                  </Button>
                </Tooltip>
              );
            })}
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
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            {audio.gen_id && verProgreso ? (
              <ProgresoVivo
                genId={audio.gen_id}
                modo="whisper"
                onCerrar={() => setVerProgreso(false)}
              />
            ) : null}
            <Vacio texto="Transcribiendo… los documentos aparecerán aquí." />
          </div>
        ) : !artefacto ? (
          <Vacio texto="Elige un artefacto." />
        ) : artefacto.estado === "generando" ? (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            {artefacto.gen_id && verProgreso ? (
              <ProgresoVivo
                genId={artefacto.gen_id}
                modo="claude"
                onCerrar={() => setVerProgreso(false)}
              />
            ) : (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Generando «{artefacto.titulo}»…
              </div>
            )}
          </div>
        ) : artefacto.estado === "error" ? (
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            {artefacto.error || "Este tratamiento falló."}
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col gap-3">
            <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <h2 className="text-sm font-semibold">
                {artefacto.titulo || TITULO_ARTEFACTO[artefacto.tipo]}
              </h2>
              {esTratamiento ? (
                <span className="text-xs text-muted-foreground">
                  Derivado de «{origen ? origen.titulo || TITULO_ARTEFACTO[origen.tipo] : "la transcripción"}»
                </span>
              ) : null}
            </div>
            {artefacto.tipo === "preguntas" ? (
              <FormularioPreguntas
                artefacto={artefacto}
                audio={audio}
                onCambio={onCambio}
                onSeleccionarArtefacto={onSeleccionarArtefacto}
              />
            ) : editando && editable ? (
              <div className="flex min-h-0 flex-1 flex-col gap-2">
                <Textarea
                  value={texto}
                  onChange={(e) => setTexto(e.target.value)}
                  className="min-h-[16rem] flex-1 font-mono text-base md:text-xs"
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
              <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border/70 bg-background p-3">
                <Markdown>{artefacto.contenido || "_(vacío)_"}</Markdown>
              </div>
            ) : (
              <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-md border border-border/70 bg-background p-3 font-mono text-xs">
                {artefacto.contenido || "(vacío)"}
              </pre>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

/** Tipos que son TRATAMIENTOS (derivan de otra fuente; muestran herencia). */
const TIPOS_TRATAMIENTO = new Set<TipoArtefacto>([
  "limpio",
  "resumen",
  "preguntas",
  "ideas",
  "corregido",
]);

/** Artefactos que valen como FUENTE de un tratamiento. 'texto' (SRT sin tiempos) y 'preguntas'
 *  (formulario) quedan fuera: deriva del SRT. */
const FUENTES_VALIDAS = new Set<TipoArtefacto>([
  "srt",
  "limpio",
  "resumen",
  "ideas",
  "corregido",
]);

// "mm:ss"/"hh:mm:ss" -> segundos. NaN/sin dígitos -> 0.
function ssToSec(t: string): number {
  const partes = t.split(":").map((n) => Number(n));
  if (!partes.length || partes.some((n) => Number.isNaN(n))) return 0;
  return partes.reduce((acc, n) => acc * 60 + n, 0);
}

interface PreguntaItem {
  t: string;
  frase: string;
  pregunta: string;
}

// Marca de tiempo que aporta información (la hay): «12:11» sí, «--:--» (sin timestamp, p. ej. al
// partir de texto plano) no.
function tieneTiempo(t: string): boolean {
  return /\d/.test(t);
}

// Parsea las líneas «[t] frase — pregunta» del prompt «Aclarar». Robusto: el corchete admite
// CUALQUIER marca (incl. «--:--» sin timestamp), tolera viñeta/numeración, una o varias «…» en la
// frase, y guion largo/medio. Las líneas que no encajan se descartan (p. ej. «(no hay dudas…)»).
function parsePreguntas(contenido: string): PreguntaItem[] {
  const out: PreguntaItem[] = [];
  for (const linea of contenido.split("\n")) {
    const l = linea.trim().replace(/^[-*]\s+/, "").replace(/^\d+[.)]\s+/, "");
    if (!l.startsWith("[")) continue;
    const cierre = l.indexOf("]");
    if (cierre < 1) continue;
    const t = l.slice(1, cierre).trim();
    // Frase y pregunta van separadas por « — » (espacio, raya, espacio); corta en la PRIMERA.
    const m = l.slice(cierre + 1).trim().match(/^(.*?)\s+[—–-]\s+(.+)$/);
    if (!m) continue;
    const frase = m[1].trim();
    const pregunta = m[2].trim();
    if (!pregunta) continue;
    out.push({ t, frase, pregunta });
  }
  return out;
}

// Cajón de PREGUNTAS: el artefacto intermedio del prompt «Aclarar» como formulario. Cada duda lleva
// su marca de tiempo, el fragmento escuchado, un PLAY del snippet de audio de esa franja y un campo
// de respuesta; al enviar genera el «Corregido». Las preguntas sin timestamp (derivadas de texto
// plano) no llevan play.
function FormularioPreguntas({
  artefacto,
  audio,
  onCambio,
  onSeleccionarArtefacto,
}: {
  artefacto: ArtefactoAudio;
  audio: TranscripcionAudio;
  onCambio: () => void;
  onSeleccionarArtefacto: (id: string) => void;
}) {
  const preguntas = React.useMemo(() => parsePreguntas(artefacto.contenido), [artefacto.contenido]);
  const [resp, setResp] = React.useState<Record<number, string>>({});
  React.useEffect(() => setResp({}), [artefacto.id]);

  // Reproductor de snippets: un solo <audio> del media; cada play salta a su franja y se detiene al
  // final de la ventana (~8 s desde un poco antes del timestamp).
  const audioRef = React.useRef<HTMLAudioElement>(null);
  const finRef = React.useRef(0);
  const [sonando, setSonando] = React.useState<number | null>(null);
  React.useEffect(() => setSonando(null), [artefacto.id]);

  const reproducir = (i: number, inicioSeg: number) => {
    const el = audioRef.current;
    if (!el) return;
    if (sonando === i) {
      el.pause();
      setSonando(null);
      return;
    }
    finRef.current = inicioSeg + 8;
    el.currentTime = Math.max(0, inicioSeg - 0.5);
    void el.play().then(() => setSonando(i)).catch(() => setSonando(null));
  };
  const alAvanzar = () => {
    const el = audioRef.current;
    if (el && el.currentTime >= finRef.current) {
      el.pause();
      setSonando(null);
    }
  };

  const corregir = useMutation({
    mutationFn: () => {
      const respuestas = preguntas
        .map((q, i) => {
          const a = (resp[i] ?? "").trim();
          if (!a) return null;
          const marca = tieneTiempo(q.t) ? `[${q.t}] ` : "";
          return `${marca}${q.frase} → ${a}`;
        })
        .filter((x): x is string => x !== null);
      return api.audio.corregir(artefacto.id, respuestas);
    },
    onSuccess: (r) => {
      onCambio();
      onSeleccionarArtefacto(r.artefacto.id);
      toast.success("Aplicando correcciones… verás el artefacto «Corregido».");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (!preguntas.length) {
    return (
      <div className="min-h-0 flex-1 overflow-y-auto whitespace-pre-wrap rounded-md border border-border/70 bg-background p-3 text-xs text-muted-foreground">
        {artefacto.contenido || "Sin preguntas."}
      </div>
    );
  }

  const algunaResp = Object.values(resp).some((v) => v.trim());
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-2">
      <audio
        ref={audioRef}
        src={audio.media_url || undefined}
        preload="none"
        onTimeUpdate={alAvanzar}
        onEnded={() => setSonando(null)}
        className="hidden"
      />
      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto">
        {preguntas.map((q, i) => {
          const conTiempo = tieneTiempo(q.t) && !!audio.media_url;
          return (
            <div key={i} className="rounded-md border border-border/70 bg-background p-3">
              <div className="flex items-baseline gap-2">
                {conTiempo ? (
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-6 shrink-0 gap-1 px-1.5 font-mono text-xs"
                    title="Escuchar este fragmento"
                    onClick={() => reproducir(i, ssToSec(q.t))}
                  >
                    {sonando === i ? <Pause className="h-3 w-3" /> : <Play className="h-3 w-3" />}
                    {q.t}
                  </Button>
                ) : (
                  <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
                    {q.t || "—"}
                  </span>
                )}
                <p className="text-xs">
                  <span className="text-muted-foreground">{q.frase}</span> — {q.pregunta}
                </p>
              </div>
              <Textarea
                value={resp[i] ?? ""}
                onChange={(e) => setResp((s) => ({ ...s, [i]: e.target.value }))}
                rows={1}
                className="mt-2 min-h-9"
                placeholder="Tu respuesta…"
              />
            </div>
          );
        })}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">
          {preguntas.length} {preguntas.length === 1 ? "pregunta" : "preguntas"}
        </span>
        <Button size="sm" disabled={!algunaResp || corregir.isPending} onClick={() => corregir.mutate()}>
          {corregir.isPending ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <SpellCheck className="mr-1.5 h-3.5 w-3.5" />
          )}
          Generar «Corregido»
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
