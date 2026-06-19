import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Lightbulb, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EstadoSugerencia, Sugerencia } from "@/types";

import { DetalleSugerencia } from "./sugerencias/DetalleSugerencia";
import {
  CATEGORIA_LABEL,
  CLAVE_SUGERENCIAS,
  COLUMNAS,
  COMPLEJIDAD_LABEL,
  COMPLEJIDAD_VARIANTE,
  ESTADO_LABEL,
  ESTADO_VARIANTE,
  ESTADOS_ARCHIVO,
  etiqueta,
} from "./sugerencias/columnas";

const MIME_ARRASTRE = "text/plain";

/**
 * Panel de Sugerencias como KANBAN de auto-desarrollo (estilo Nolan v2):
 * Ideas → Discovery → En cola → Building → Revisión → Hecho, con una zona aparte
 * para piezas Fallidas/Descartadas. Arrastre HTML5 nativo entre columnas; click en
 * una tarjeta abre el detalle (spec/plan, stream en vivo y acciones del flujo).
 */
export default function Sugerencias() {
  const query = useQuery({
    queryKey: CLAVE_SUGERENCIAS,
    queryFn: ({ signal }) => api.sugerencias(signal),
  });

  const [nuevaAbierta, setNuevaAbierta] = React.useState(false);
  const [seleccionId, setSeleccionId] = React.useState<string | null>(null);

  const sugerencias = query.data?.sugerencias ?? [];
  const categorias = query.data?.categorias ?? Object.keys(CATEGORIA_LABEL);
  const seleccion = sugerencias.find((s) => s.id === seleccionId) ?? null;

  return (
    <>
      <div className="flex items-center justify-between gap-3">
        <TituloPagina titulo="Sugerencias" icono={Lightbulb} />
        <Button onClick={() => setNuevaAbierta(true)}>
          <Plus className="h-4 w-4" />
          Nueva idea
        </Button>
      </div>

      <div className="mt-6">
        {query.isError ? (
          <BloqueError
            titulo="No se pudieron cargar las sugerencias"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : query.isPending ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-64 w-full rounded-lg" />
            ))}
          </div>
        ) : (
          <Tablero sugerencias={sugerencias} onAbrir={(s) => setSeleccionId(s.id)} />
        )}
      </div>

      <NuevaIdea
        abierta={nuevaAbierta}
        onCerrar={() => setNuevaAbierta(false)}
        categorias={categorias}
      />
      <DetalleSugerencia sugerencia={seleccion} onClose={() => setSeleccionId(null)} />
    </>
  );
}

// --- Tablero kanban --------------------------------------------------------

function Tablero({
  sugerencias,
  onAbrir,
}: {
  sugerencias: Sugerencia[];
  onAbrir: (s: Sugerencia) => void;
}) {
  const queryClient = useQueryClient();
  const [sobreColumna, setSobreColumna] = React.useState<string | null>(null);

  const mover = useMutation({
    mutationFn: async ({ s, destino }: { s: Sugerencia; destino: EstadoSugerencia }) => {
      // Cada columna dispara la acción adecuada del flujo; las demás transiciones
      // son un PATCH directo del estado (override manual). No se usa el valor de retorno.
      if (destino === "discovery") {
        await api.discoverySugerencia(s.id);
      } else if (destino === "en_cola") {
        await api.construirSugerencia(s.id);
      } else {
        await api.actualizarSugerencia(s.id, { estado: destino });
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const soltar = (destino: EstadoSugerencia, ev: React.DragEvent) => {
    ev.preventDefault();
    setSobreColumna(null);
    const id = ev.dataTransfer.getData(MIME_ARRASTRE);
    const s = sugerencias.find((x) => x.id === id);
    if (!s || s.estado === destino) return;
    mover.mutate({ s, destino });
  };

  const archivadas = sugerencias.filter((s) =>
    ESTADOS_ARCHIVO.includes(s.estado as EstadoSugerencia),
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        {COLUMNAS.map((col) => {
          const items = sugerencias.filter((s) => s.estado === col.estado);
          return (
            <Columna
              key={col.estado}
              titulo={col.titulo}
              total={items.length}
              activa={sobreColumna === col.estado}
              onDragOver={(e) => {
                e.preventDefault();
                setSobreColumna(col.estado);
              }}
              onDragLeave={() => setSobreColumna((c) => (c === col.estado ? null : c))}
              onDrop={(e) => soltar(col.estado, e)}
            >
              {items.map((s) => (
                <Tarjeta key={s.id} sugerencia={s} onAbrir={() => onAbrir(s)} />
              ))}
            </Columna>
          );
        })}
      </div>

      {archivadas.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm font-semibold text-muted-foreground">
            Fallidas y descartadas
          </h2>
          <div className="flex flex-wrap gap-2">
            {archivadas.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => onAbrir(s)}
                className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-left text-xs opacity-70 transition hover:opacity-100"
              >
                <Badge
                  variant={ESTADO_VARIANTE[s.estado] ?? "secondary"}
                  className="font-normal"
                >
                  {etiqueta(ESTADO_LABEL, s.estado)}
                </Badge>
                <span className="max-w-[16rem] truncate font-medium">{s.titulo}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Columna({
  titulo,
  total,
  activa,
  children,
  onDragOver,
  onDragLeave,
  onDrop,
}: {
  titulo: string;
  total: number;
  activa: boolean;
  children: React.ReactNode;
  onDragOver: React.DragEventHandler;
  onDragLeave: React.DragEventHandler;
  onDrop: React.DragEventHandler;
}) {
  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className={cn(
        "flex min-h-[16rem] flex-col gap-2 rounded-lg border border-dashed bg-muted/20 p-2 transition-colors",
        activa && "border-keni-300 bg-keni-50/40 ring-1 ring-keni-300",
      )}
    >
      <div className="flex items-center justify-between px-1">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {titulo}
        </span>
        <Badge variant="outline" className="text-[10px] tabular-nums">
          {total}
        </Badge>
      </div>
      <div className="flex flex-1 flex-col gap-2">{children}</div>
    </div>
  );
}

function Tarjeta({
  sugerencia,
  onAbrir,
}: {
  sugerencia: Sugerencia;
  onAbrir: () => void;
}) {
  const enVivo = !!sugerencia.gen_id && sugerencia.estado === "building";
  return (
    <div
      draggable
      onDragStart={(e) => e.dataTransfer.setData(MIME_ARRASTRE, sugerencia.id)}
      role="button"
      tabIndex={0}
      onClick={onAbrir}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir();
        }
      }}
      className="cursor-grab space-y-2 rounded-md border border-border bg-card p-3 text-card-foreground shadow-sm transition-colors hover:border-keni-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
    >
      <p className="text-sm font-medium leading-snug">{sugerencia.titulo}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="outline" className="text-[10px] font-normal">
          {etiqueta(CATEGORIA_LABEL, sugerencia.categoria)}
        </Badge>
        {sugerencia.complejidad && (
          <Badge
            variant={COMPLEJIDAD_VARIANTE[sugerencia.complejidad] ?? "outline"}
            className="text-[10px] font-normal"
          >
            {etiqueta(COMPLEJIDAD_LABEL, sugerencia.complejidad)}
          </Badge>
        )}
        {enVivo && (
          <span className="flex items-center gap-1 text-[10px] text-sky-600">
            <Spinner className="h-3 w-3" aria-hidden="true" />
            en vivo
          </span>
        )}
      </div>
      {(sugerencia.autor || sugerencia.fase) && (
        <p className="truncate text-[11px] text-muted-foreground">
          {[sugerencia.autor, sugerencia.fase && `fase: ${sugerencia.fase}`]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}
    </div>
  );
}

// --- Alta de idea ----------------------------------------------------------

function NuevaIdea({
  abierta,
  onCerrar,
  categorias,
}: {
  abierta: boolean;
  onCerrar: () => void;
  categorias: string[];
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [detalle, setDetalle] = React.useState("");
  const [categoria, setCategoria] = React.useState(categorias[0] ?? "idea");
  const [autor, setAutor] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearSugerencia({
        titulo: titulo.trim(),
        detalle: detalle.trim() || undefined,
        categoria,
        autor: autor.trim() || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
      toast.success("Idea creada");
      setTitulo("");
      setDetalle("");
      setAutor("");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeEnviar = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierta} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva idea</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="idea-titulo">Título</Label>
            <Input
              id="idea-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ej. Exportar métricas a Slack"
              maxLength={200}
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="idea-detalle">Detalle</Label>
            <Textarea
              id="idea-detalle"
              value={detalle}
              onChange={(e) => setDetalle(e.target.value)}
              placeholder="Describe el problema, tu idea…"
              rows={5}
              maxLength={8000}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="idea-categoria">Categoría</Label>
              <Select value={categoria} onValueChange={setCategoria}>
                <SelectTrigger id="idea-categoria">
                  <SelectValue placeholder="Categoría" />
                </SelectTrigger>
                <SelectContent>
                  {categorias.map((c) => (
                    <SelectItem key={c} value={c}>
                      {etiqueta(CATEGORIA_LABEL, c)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="idea-autor">Tu nombre</Label>
              <Input
                id="idea-autor"
                value={autor}
                onChange={(e) => setAutor(e.target.value)}
                placeholder="Opcional"
                maxLength={120}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeEnviar}>
            {crear.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear idea
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
