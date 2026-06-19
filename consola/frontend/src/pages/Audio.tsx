/**
 * Gestor de Audio — audio→texto integral.
 *
 * Sube cualquier audio o vídeo, extrae la pista de voz y la transcribe EN LOCAL con whisper.cpp
 * (modelo v3 turbo) generando segmentos con timestamps. Sobre esa transcripción, el equipo trabaja
 * con AGENTES de Claude: «Limpiar» (quita silencios/loops/repeticiones/muletillas), «Resumir»,
 * «Aclarar» (pregunta por los fragmentos dudosos) y «Corregir» (aplica las respuestas del equipo).
 *
 * El humano decide qué se guarda: el resultado de un agente se PREVISUALIZA y solo al «Aceptar» se
 * persiste en la transcripción. Mismo principio que el resto del producto: poca IA de cara afuera,
 * mucha IA hacia adentro; nada se da por bueno sin criterio humano.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AudioLines,
  Check,
  Eraser,
  FileText,
  HelpCircle,
  Loader2,
  RefreshCw,
  SpellCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";

import { toast } from "sonner";

import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError, urlMedia } from "@/lib/api";
import type {
  EstadoTranscripcion,
  OperacionAgente,
  SegmentoAudio,
  TranscripcionAudio,
} from "@/lib/api/audio";

const EN_PROCESO: EstadoTranscripcion[] = ["pendiente", "transcribiendo"];

const ETIQUETA_ESTADO: Record<EstadoTranscripcion, string> = {
  pendiente: "En cola",
  transcribiendo: "Transcribiendo…",
  transcrito: "Transcrito",
  editado: "Editado",
  error: "Error",
};

const AGENTES: { op: OperacionAgente; etiqueta: string; Icono: typeof Eraser; ayuda: string }[] = [
  { op: "limpiar", etiqueta: "Limpiar", Icono: Eraser, ayuda: "Quita silencios, loops, frases repetidas y muletillas" },
  { op: "resumir", etiqueta: "Resumir", Icono: FileText, ayuda: "Idea central, puntos clave y citas" },
  { op: "aclarar", etiqueta: "Aclarar", Icono: HelpCircle, ayuda: "Pregunta por los fragmentos que no se entienden" },
  { op: "corregir", etiqueta: "Corregir", Icono: SpellCheck, ayuda: "Aplica las respuestas del equipo a la transcripción" },
];

function fmtTiempo(ms: number): string {
  const total = Math.max(0, Math.floor((ms || 0) / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function Audio() {
  const { marcaActiva, marcaPrimaria } = useMarcaActiva();
  const marca = marcaActiva ?? marcaPrimaria ?? "";
  const qc = useQueryClient();

  const [seleccionId, setSeleccionId] = React.useState<string | null>(null);

  // Lista de transcripciones de la marca activa. Se resondea mientras haya alguna en proceso.
  const lista = useQuery({
    queryKey: ["audio", "transcripciones", marca],
    queryFn: ({ signal }) => api.audio.transcripciones({ marca: marca || undefined }, signal),
    refetchInterval: (q) =>
      (q.state.data?.transcripciones ?? []).some((t) => EN_PROCESO.includes(t.estado)) ? 2500 : false,
  });
  const transcripciones = lista.data?.transcripciones ?? [];

  // Detalle de la transcripción seleccionada; se resondea mientras el ASR esté en curso.
  const detalle = useQuery({
    queryKey: ["audio", "transcripcion", seleccionId],
    queryFn: ({ signal }) => api.audio.transcripcion(seleccionId as string, signal),
    enabled: seleccionId !== null,
    refetchInterval: (q) => (EN_PROCESO.includes(q.state.data?.transcripcion.estado as EstadoTranscripcion) ? 2000 : false),
  });
  const actual = detalle.data?.transcripcion ?? null;

  const subir = useMutation({
    mutationFn: async (archivo: File) => {
      const form = new FormData();
      form.append("archivo", archivo);
      form.append("marca", marca);
      form.append("nombre", archivo.name);
      return api.audio.crear(form);
    },
    onSuccess: (r) => {
      setSeleccionId(r.transcripcion.id);
      qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
      toast.success("Audio subido. Transcribiendo…");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => api.audio.eliminar(id),
    onSuccess: (_d, id) => {
      if (seleccionId === id) setSeleccionId(null);
      qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const onArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    if (!marca) {
      toast.error("Selecciona una marca antes de subir audio.");
      return;
    }
    subir.mutate(f);
  };

  return (
    <div className="flex flex-col gap-4">
      <TituloPagina titulo="Audio" icono={AudioLines} />
      <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
        <aside className="flex flex-col gap-3">
          <label className="flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed border-border/70 bg-muted/30 p-5 text-center text-sm hover:bg-muted/50">
            <input
              type="file"
              accept="audio/*,video/*"
              className="sr-only"
              onChange={onArchivo}
              disabled={subir.isPending || !marca}
            />
            {subir.isPending ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <Upload className="h-5 w-5 text-muted-foreground" />
            )}
            <span className="font-medium">Subir audio o vídeo</span>
            <span className="text-xs text-muted-foreground">
              {marca ? "Se extrae la voz y se transcribe" : "Selecciona una marca primero"}
            </span>
          </label>

          <ListaTranscripciones
            transcripciones={transcripciones}
            cargando={lista.isLoading}
            seleccionId={seleccionId}
            onSeleccionar={setSeleccionId}
            onEliminar={(id) => eliminar.mutate(id)}
          />
        </aside>

        <section className="min-w-0">
          {seleccionId === null ? (
            <Vacio />
          ) : actual ? (
            <Editor
              transcripcion={actual}
              onCambio={() => {
                qc.invalidateQueries({ queryKey: ["audio", "transcripcion", seleccionId] });
                qc.invalidateQueries({ queryKey: ["audio", "transcripciones"] });
              }}
            />
          ) : (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando…
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Vacio() {
  return (
    <div className="flex h-64 flex-col items-center justify-center gap-2 rounded-xl border border-border/70 bg-muted/20 text-center text-sm text-muted-foreground">
      <AudioLines className="h-8 w-8 opacity-50" />
      <p>Sube un audio o vídeo, o elige una transcripción de la lista.</p>
    </div>
  );
}

function ListaTranscripciones({
  transcripciones,
  cargando,
  seleccionId,
  onSeleccionar,
  onEliminar,
}: {
  transcripciones: TranscripcionAudio[];
  cargando: boolean;
  seleccionId: string | null;
  onSeleccionar: (id: string) => void;
  onEliminar: (id: string) => void;
}) {
  if (cargando) {
    return (
      <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Cargando…
      </div>
    );
  }
  if (transcripciones.length === 0) {
    return <p className="px-1 text-xs text-muted-foreground">Aún no hay transcripciones.</p>;
  }
  return (
    <div className="flex flex-col gap-1.5">
      {transcripciones.map((t) => {
        const activa = t.id === seleccionId;
        return (
          <div
            key={t.id}
            className={`group flex items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-sm ${
              activa ? "border-primary/60 bg-primary/5" : "border-border/70 bg-card hover:bg-muted/40"
            }`}
          >
            <button
              type="button"
              onClick={() => onSeleccionar(t.id)}
              className="flex min-w-0 flex-1 flex-col items-start"
            >
              <span className="w-full truncate font-medium">{t.nombre || "Sin título"}</span>
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <EstadoBadge estado={t.estado} />
                {t.duracion_ms > 0 ? <span>{fmtTiempo(t.duracion_ms)}</span> : null}
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

function Editor({
  transcripcion,
  onCambio,
}: {
  transcripcion: TranscripcionAudio;
  onCambio: () => void;
}) {
  const t = transcripcion;
  const enProceso = EN_PROCESO.includes(t.estado);

  // Edición local de los segmentos (timestamps fijos; el texto es editable por el humano).
  const [segmentos, setSegmentos] = React.useState<SegmentoAudio[]>(t.segmentos);
  React.useEffect(() => setSegmentos(t.segmentos), [t.id, t.segmentos]);
  const sucio = React.useMemo(
    () => JSON.stringify(segmentos) !== JSON.stringify(t.segmentos),
    [segmentos, t.segmentos],
  );

  // Seguimiento EN VIVO del agente de Claude en curso (stream token a token).
  const agente = useGeneracion(`audio-agente:${t.id}`);
  const [opEnCurso, setOpEnCurso] = React.useState<OperacionAgente | null>(null);
  const [respuestas, setRespuestas] = React.useState("");

  const resultadoTexto =
    agente.generacion?.resultado?.documento ?? agente.generacion?.salida ?? "";

  const guardar = useMutation({
    mutationFn: (cambios: Parameters<typeof api.audio.guardar>[1]) => api.audio.guardar(t.id, cambios),
    onSuccess: () => onCambio(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const retranscribir = useMutation({
    mutationFn: () => api.audio.retranscribir(t.id),
    onSuccess: () => {
      toast.success("Reintentando la transcripción…");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const lanzarAgente = async (op: OperacionAgente) => {
    setOpEnCurso(op);
    agente.limpiar();
    try {
      const resp = op === "corregir" ? respuestas.split("\n").map((s) => s.trim()).filter(Boolean) : undefined;
      const { gen_id } = await api.audio.agente(t.id, op, resp);
      const r = await api.generacion(gen_id);
      agente.iniciar(r.generacion);
    } catch (e) {
      toast.error(mensajeError(e));
      setOpEnCurso(null);
    }
  };

  const aceptarResultado = async () => {
    if (opEnCurso === "resumir") {
      await guardar.mutateAsync({ resumen: resultadoTexto });
      toast.success("Resumen guardado.");
    } else if (opEnCurso === "limpiar" || opEnCurso === "corregir") {
      await guardar.mutateAsync({ texto: resultadoTexto, estado: "editado" });
      toast.success("Texto actualizado.");
    }
    descartarResultado();
  };

  const descartarResultado = () => {
    agente.limpiar();
    setOpEnCurso(null);
    setRespuestas("");
  };

  const agentesDeshabilitados = enProceso || agente.ejecutando || guardar.isPending;
  const hayResultado = !agente.ejecutando && opEnCurso !== null && resultadoTexto.trim() !== "";

  return (
    <div className="flex flex-col gap-4">
      {/* Cabecera */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span className="truncate text-lg font-semibold">{t.nombre || "Sin título"}</span>
          <EstadoBadge estado={t.estado} />
        </div>
        <div className="text-xs text-muted-foreground">
          {t.marca_nombre} · {t.idioma}
          {t.duracion_ms > 0 ? ` · ${fmtTiempo(t.duracion_ms)}` : ""}
        </div>
      </div>

      {/* Reproductor del original */}
      {t.media_url ? (
        <video controls src={urlMedia(t.media_url)} className="max-h-56 w-full rounded-lg bg-black" />
      ) : null}

      {/* Estado del ASR */}
      {enProceso ? (
        <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Extrayendo la voz y transcribiendo con whisper (v3 turbo)…
        </div>
      ) : null}
      {t.estado === "error" ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <span className="min-w-0">{t.error || "No se pudo transcribir."}</span>
          <Button size="sm" variant="outline" onClick={() => retranscribir.mutate()} disabled={retranscribir.isPending}>
            <RefreshCw className="mr-1.5 h-3.5 w-3.5" /> Reintentar
          </Button>
        </div>
      ) : null}

      {/* Barra de agentes */}
      {(t.estado === "transcrito" || t.estado === "editado") && segmentos.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {AGENTES.map(({ op, etiqueta, Icono, ayuda }) => (
            <Button
              key={op}
              size="sm"
              variant="outline"
              title={ayuda}
              disabled={agentesDeshabilitados}
              onClick={() => lanzarAgente(op)}
            >
              {agente.ejecutando && opEnCurso === op ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Icono className="mr-1.5 h-3.5 w-3.5" />
              )}
              {etiqueta}
            </Button>
          ))}
        </div>
      ) : null}

      {/* Panel del agente en curso / resultado */}
      {opEnCurso !== null ? (
        <PanelAgente
          operacion={opEnCurso}
          ejecutando={agente.ejecutando}
          texto={resultadoTexto}
          respuestas={respuestas}
          onRespuestas={setRespuestas}
          puedeAceptar={hayResultado && opEnCurso !== "aclarar"}
          guardando={guardar.isPending}
          onAceptar={aceptarResultado}
          onCorregirConRespuestas={() => lanzarAgente("corregir")}
          onCerrar={descartarResultado}
        />
      ) : null}

      {/* Resumen guardado */}
      {t.resumen && opEnCurso === null ? (
        <div className="rounded-lg border border-border/70 bg-muted/20 p-3">
          <h3 className="mb-1 text-sm font-semibold">Resumen</h3>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{t.resumen}</p>
        </div>
      ) : null}

      {/* Texto trabajado (resultado aceptado de limpiar/corregir) */}
      {t.texto && opEnCurso === null ? (
        <div className="rounded-lg border border-border/70 bg-muted/20 p-3">
          <h3 className="mb-1 text-sm font-semibold">Texto trabajado</h3>
          <p className="whitespace-pre-wrap text-sm">{t.texto}</p>
        </div>
      ) : null}

      {/* Editor de segmentos con timestamps */}
      {segmentos.length > 0 ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold">Transcripción ({segmentos.length} segmentos)</h3>
            {sucio ? (
              <div className="flex gap-2">
                <Button size="sm" variant="ghost" onClick={() => setSegmentos(t.segmentos)}>
                  Descartar
                </Button>
                <Button
                  size="sm"
                  disabled={guardar.isPending}
                  onClick={() =>
                    guardar.mutate({
                      segmentos,
                      texto: segmentos.map((s) => s.texto).join(" "),
                      estado: "editado",
                    })
                  }
                >
                  <Check className="mr-1.5 h-3.5 w-3.5" /> Guardar correcciones
                </Button>
              </div>
            ) : null}
          </div>
          <div className="flex flex-col divide-y divide-border/60 rounded-lg border border-border/70">
            {segmentos.map((s, i) => (
              <div key={i} className="flex gap-2 px-2.5 py-1.5">
                <span className="mt-1.5 shrink-0 font-mono text-xs text-muted-foreground">
                  {fmtTiempo(s.inicio_ms)}
                </span>
                <Textarea
                  value={s.texto}
                  rows={1}
                  onChange={(e) =>
                    setSegmentos((prev) => prev.map((x, j) => (j === i ? { ...x, texto: e.target.value } : x)))
                  }
                  className="min-h-0 resize-none border-0 bg-transparent px-1 py-1 text-sm focus-visible:ring-0"
                />
              </div>
            ))}
          </div>
        </div>
      ) : !enProceso && t.estado !== "error" ? (
        <p className="text-sm text-muted-foreground">La transcripción no tiene segmentos (audio sin voz).</p>
      ) : null}
    </div>
  );
}

function PanelAgente({
  operacion,
  ejecutando,
  texto,
  respuestas,
  onRespuestas,
  puedeAceptar,
  guardando,
  onAceptar,
  onCorregirConRespuestas,
  onCerrar,
}: {
  operacion: OperacionAgente;
  ejecutando: boolean;
  texto: string;
  respuestas: string;
  onRespuestas: (v: string) => void;
  puedeAceptar: boolean;
  guardando: boolean;
  onAceptar: () => void;
  onCorregirConRespuestas: () => void;
  onCerrar: () => void;
}) {
  const titulo = AGENTES.find((a) => a.op === operacion)?.etiqueta ?? operacion;
  return (
    <div className="rounded-lg border border-primary/40 bg-primary/5 p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold">
          {ejecutando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4 text-primary" />}
          {titulo}
        </h3>
        <button type="button" onClick={onCerrar} className="rounded p-1 text-muted-foreground hover:text-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>

      <p className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded bg-background/60 p-2 text-sm">
        {texto || (ejecutando ? "Pensando…" : "Sin resultado.")}
      </p>

      {/* «Aclarar» genera preguntas: el equipo responde y dispara «Corregir». */}
      {operacion === "aclarar" && !ejecutando && texto ? (
        <div className="mt-2 flex flex-col gap-2">
          <label className="text-xs font-medium text-muted-foreground">
            Responde a las dudas (una por línea) y aplícalas:
          </label>
          <Textarea
            value={respuestas}
            onChange={(e) => onRespuestas(e.target.value)}
            rows={3}
            placeholder="Ej.: El apellido correcto es Mbappé&#10;Ganó el América"
          />
          <div className="flex justify-end">
            <Button size="sm" disabled={!respuestas.trim()} onClick={onCorregirConRespuestas}>
              <SpellCheck className="mr-1.5 h-3.5 w-3.5" /> Corregir con estas respuestas
            </Button>
          </div>
        </div>
      ) : null}

      {puedeAceptar ? (
        <div className="mt-2 flex justify-end gap-2">
          <Button size="sm" variant="ghost" onClick={onCerrar}>
            Descartar
          </Button>
          <Button size="sm" disabled={guardando} onClick={onAceptar}>
            <Check className="mr-1.5 h-3.5 w-3.5" />
            {operacion === "resumir" ? "Guardar resumen" : "Aceptar y reemplazar texto"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
