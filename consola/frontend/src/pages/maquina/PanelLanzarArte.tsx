/**
 * Lanzador manual de ARTE (gemelo «rico» de «Generar copy»): genera N imágenes a mano para
 * una marca a partir del prompt de la etapa Ilustrar de la Prompts (`prompt/ilustrar`, editable) con un
 * modelo de imagen y un nº de alternativas elegidos. DEJA CLARO QUE TIENE COSTE: estima el
 * gasto con el coste medio por imagen del modelo («~$X por imagen × N»). Lanza con
 * `POST /api/artes/generar`, sondea cada generación devuelta (`GET /api/generaciones/{id}`)
 * y pinta las N imágenes resultantes (servidas en `/api/media/{id}`), cada una con su modelo
 * y su coste real.
 *
 * La marca llega del switch GLOBAL salvo que el cockpit imponga una `marcaForzada` (su
 * selector LOCAL).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Coins, ImageOff, Loader2, Pencil, Sparkles } from "lucide-react";
import * as React from "react";

import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { MENSAJE_MARCA_REQUERIDA, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError, urlMedia } from "@/lib/api";
import type { Generacion } from "@/types";

/** Doc de la Prompts con el prompt de Ilustrar (mismo id que la directiva del generador). */
const PROMPT_ILUSTRAR_ID = "prompt/ilustrar";
/** Tope de alternativas por lanzamiento (espejo de `_MAX_ALTERNATIVAS` en el backend). */
const MAX_ALTERNATIVAS = 4;
/** Cada cuánto sondeamos las generaciones en curso (mientras alguna sigue viva). */
const INTERVALO_SONDEO_MS = 1500;

/** Formatea un coste en USD con la precisión justa (céntimos o milésimas para importes chicos). */
function formatoUsd(valor: number): string {
  const decimales = valor < 0.1 ? 3 : 2;
  return `$${valor.toFixed(decimales)}`;
}

export function PanelLanzarArte({
  marcas,
  open,
  onOpenChange,
  marcaForzada,
  onEditarPrompt,
}: {
  marcas: { id: string; nombre: string }[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Marca LOCAL que prevalece sobre el switch global (selector propio del cockpit). */
  marcaForzada?: string;
  /** Si se pasa, el popup muestra un botón "Editar prompt" en la cabecera (edición in-place). */
  onEditarPrompt?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const marcaBase = marcaForzada ?? marcaActiva;
  const marca = marcaBase && marcas.some((m) => m.id === marcaBase) ? marcaBase : "";

  // ── Prompt de arte de la Prompts: precargado y EDITABLE (el usuario puede escribir el suyo). ──
  const promptQuery = useQuery({
    queryKey: ["prompts-doc", PROMPT_ILUSTRAR_ID],
    queryFn: ({ signal }) => api.documento(PROMPT_ILUSTRAR_ID, signal),
    enabled: open,
  });
  const [prompt, setPrompt] = React.useState("");
  const [promptTocado, setPromptTocado] = React.useState(false);
  React.useEffect(() => {
    // Precarga el cuerpo una sola vez, mientras el usuario no lo haya editado.
    if (!promptTocado && promptQuery.data) setPrompt(promptQuery.data.documento.cuerpo ?? "");
  }, [promptQuery.data, promptTocado]);

  // ── Conexión de imagen: modelos disponibles + modelo por defecto. ──
  const conexionQuery = useQuery({
    queryKey: ["conexion-imagen"],
    queryFn: ({ signal }) => api.conexionImagen(signal),
    enabled: open,
  });
  const modelos = conexionQuery.data?.modelos ?? [];
  const configurado = conexionQuery.data?.configurado ?? true;
  const [modelo, setModelo] = React.useState("");
  React.useEffect(() => {
    if (!modelo && conexionQuery.data?.modelo) setModelo(conexionQuery.data.modelo);
  }, [conexionQuery.data, modelo]);

  // ── Nº de alternativas (1..4). ──
  const [n, setN] = React.useState(1);

  // ── Coste medio por imagen del modelo elegido (para estimar «~$X × N»). ──
  const costeQuery = useQuery({
    queryKey: ["arte-coste", modelo],
    queryFn: ({ signal }) => api.costeMedioArte(modelo || undefined, signal),
    enabled: open,
  });
  const porImagen = costeQuery.data?.por_imagen ?? null;
  const costeGlobal = costeQuery.data?.global ?? false;

  // ── Generaciones lanzadas: se inicializan del POST y se refrescan sondeando el listado. ──
  const [lanzadas, setLanzadas] = React.useState<Generacion[]>([]);
  const ids = React.useMemo(() => lanzadas.map((g) => g.id), [lanzadas]);
  const seguimiento = useQuery({
    queryKey: ["arte-generaciones", ids],
    queryFn: ({ signal }) => api.generaciones(signal),
    enabled: ids.length > 0,
    refetchInterval: (q) => {
      if (ids.length === 0) return false;
      const lista = q.state.data?.generaciones ?? [];
      const pendiente = ids.some((id) => {
        const g = lista.find((x) => x.id === id);
        return !g || g.estado === "ejecutando";
      });
      return pendiente ? INTERVALO_SONDEO_MS : false;
    },
  });
  // Cada id: su instantánea del sondeo si llegó, si no el valor inicial del POST (estado «ejecutando»).
  const generaciones = React.useMemo(() => {
    const lista = seguimiento.data?.generaciones ?? [];
    return lanzadas.map((seed) => lista.find((g) => g.id === seed.id) ?? seed);
  }, [lanzadas, seguimiento.data]);

  const lanzar = useMutation({
    mutationFn: () =>
      api.generarArte({
        marca,
        prompt: prompt.trim() || undefined,
        modelo: modelo || undefined,
        n,
      }),
    onSuccess: (r) => setLanzadas(r.generaciones),
  });

  // Al cerrar el diálogo limpiamos el seguimiento y el estado de la mutación (los trabajos
  // siguen vivos en el servidor; esto solo resetea la vista para el próximo lanzamiento).
  const cerrar = (v: boolean) => {
    if (!v) {
      setLanzadas([]);
      lanzar.reset();
    }
    onOpenChange(v);
  };

  const estimado = porImagen != null ? porImagen * n : null;
  const puedeArrancar = !!marca && configurado && !lanzar.isPending && prompt.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={cerrar}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col gap-3 overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between gap-2 pr-6">
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" /> Generar arte
            </DialogTitle>
            {onEditarPrompt ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 text-xs text-muted-foreground"
                onClick={onEditarPrompt}
              >
                <Pencil className="h-3.5 w-3.5" /> Editar prompt
              </Button>
            ) : null}
          </div>
        </DialogHeader>

        {!configurado ? (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              La generación de imagen no está configurada. Añade una clave de proveedor de
              imagen (Ajustes → Conexiones · Imagen con IA) para activarla.
            </span>
          </div>
        ) : null}

        {/* Prompt de arte (Prompts), precargado y editable. */}
        <div className="space-y-1">
          <Label>Prompt de arte (editable)</Label>
          <AutoTextarea
            value={prompt}
            onChange={(e) => {
              setPromptTocado(true);
              setPrompt(e.target.value);
            }}
            maxHeight={260}
            placeholder={
              promptQuery.isPending ? "Cargando el prompt de la Prompts…" : "Describe el arte a generar…"
            }
            className="min-h-[120px] w-full text-sm"
          />
          <p className="text-xs text-muted-foreground">
            Parte del prompt de la Prompts (<code>prompt/ilustrar</code>); escríbelo a tu gusto.
          </p>
        </div>

        {/* Modelo + Nº de alternativas. */}
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1">
            <Label>Modelo de imagen</Label>
            <Select value={modelo} onValueChange={setModelo} disabled={modelos.length === 0}>
              <SelectTrigger>
                <SelectValue placeholder="Modelo por defecto" />
              </SelectTrigger>
              <SelectContent>
                {modelos.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Alternativas</Label>
            <Select value={String(n)} onValueChange={(v) => setN(Number(v))}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Array.from({ length: MAX_ALTERNATIVAS }, (_, i) => i + 1).map((v) => (
                  <SelectItem key={v} value={String(v)}>
                    {v} {v === 1 ? "imagen" : "imágenes"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Coste: dejamos CLARO que se paga, con la estimación por imagen × N. */}
        <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
          <Coins className="mt-0.5 h-4 w-4 shrink-0" />
          {estimado != null && porImagen != null ? (
            <span>
              Esta acción <strong>tiene coste</strong>: ~{formatoUsd(porImagen)} por imagen × {n} ≈{" "}
              <strong>{formatoUsd(estimado)}</strong>
              {costeGlobal ? " (media global; sin histórico de este modelo)" : ""}. Se paga al
              generar.
            </span>
          ) : (
            <span>
              Esta acción <strong>tiene coste</strong> (cada imagen es una llamada al proveedor).
              Aún no hay histórico para estimar el importe.
            </span>
          )}
        </div>

        <Tooltip
          label={!marca ? MENSAJE_MARCA_REQUERIDA : ""}
          className="w-full"
        >
          <Button
            variant="outline"
            className="w-full"
            onClick={() => lanzar.mutate()}
            disabled={!puedeArrancar}
          >
            {lanzar.isPending ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="mr-1 h-4 w-4" />
            )}
            Generar {n} {n === 1 ? "imagen" : "imágenes"}
          </Button>
        </Tooltip>
        {lanzar.isError ? (
          <p className="text-xs text-destructive">{mensajeError(lanzar.error)}</p>
        ) : null}

        {/* Resultados: las N imágenes (o su estado en curso/error). */}
        {generaciones.length > 0 ? (
          <div className="min-h-0 flex-1 space-y-2 border-t border-border pt-2">
            <span className="text-xs font-medium">Resultado</span>
            <div className="grid grid-cols-2 gap-2">
              {generaciones.map((g) => (
                <ResultadoArte key={g.id} gen={g} />
              ))}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/** Una celda del grid de resultados: imagen lista, «Generando…» o el error. */
function ResultadoArte({ gen }: { gen: Generacion }) {
  const res = gen.resultado;
  if (gen.estado === "error") {
    return (
      <div className="flex flex-col items-center justify-center gap-1 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-center text-xs text-destructive">
        <ImageOff className="h-5 w-5" />
        <span>{gen.error || "No se pudo generar."}</span>
      </div>
    );
  }
  if (gen.estado === "ejecutando" || !res?.url) {
    return (
      <div className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-md border border-border bg-muted/40 text-xs text-muted-foreground">
        <Loader2 className="h-5 w-5 animate-spin" />
        <span>Generando…</span>
      </div>
    );
  }
  return (
    <figure className="overflow-hidden rounded-md border border-border">
      <a href={urlMedia(res.url)} target="_blank" rel="noopener noreferrer">
        <img
          src={urlMedia(res.url)}
          alt="Arte generado"
          className="aspect-square w-full object-cover"
          loading="lazy"
        />
      </a>
      <figcaption className="flex items-center justify-between gap-1 px-2 py-1 text-[11px] text-muted-foreground">
        <span className="truncate">{res.modelo || "—"}</span>
        {res.coste_usd ? <span>{formatoUsd(res.coste_usd)}</span> : null}
      </figcaption>
    </figure>
  );
}
