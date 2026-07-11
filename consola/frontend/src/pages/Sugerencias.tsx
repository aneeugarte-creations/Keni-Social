import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Hammer, Lightbulb, Plus, X } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
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
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { EstadoSugerencia, Sugerencia } from "@/types";

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
 * Panel de Sugerencias. El SUPERADMIN ve el KANBAN de auto-desarrollo completo
 * (Ideas → Discovery → En cola → Building → Revisión → Hecho + zona de archivadas) y lo
 * controla; el resto del equipo solo ve SUS ideas y su spec. El detalle/spec abre como
 * SUBPÁGINA (`/sugerencias/:id`), no como popup.
 */
export default function Sugerencias() {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: CLAVE_SUGERENCIAS,
    queryFn: ({ signal }) => api.sugerencias(signal),
  });

  const [nuevaAbierta, setNuevaAbierta] = React.useState(false);

  const sugerencias = query.data?.sugerencias ?? [];
  const categorias = query.data?.categorias ?? Object.keys(CATEGORIA_LABEL);
  const esSuper = query.data?.superadmin ?? false;
  const abrir = (s: Sugerencia) => navigate(`/sugerencias/${s.id}`);

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
        ) : esSuper ? (
          <Tablero sugerencias={sugerencias} onAbrir={abrir} />
        ) : (
          <MisIdeas
            sugerencias={sugerencias}
            onAbrir={abrir}
            onNueva={() => setNuevaAbierta(true)}
          />
        )}
      </div>

      <NuevaIdea
        abierta={nuevaAbierta}
        onCerrar={() => setNuevaAbierta(false)}
        categorias={categorias}
      />
    </>
  );
}

// --- Vista del equipo (no superadmin): solo MIS ideas ----------------------

function MisIdeas({
  sugerencias,
  onAbrir,
  onNueva,
}: {
  sugerencias: Sugerencia[];
  onAbrir: (s: Sugerencia) => void;
  onNueva: () => void;
}) {
  if (sugerencias.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed bg-muted/20 p-10 text-center">
        <Lightbulb className="h-8 w-8 text-muted-foreground" aria-hidden="true" />
        <p className="text-sm text-muted-foreground">
          Aún no has propuesto ninguna idea. Comparte una mejora, un bug o una idea para el
          equipo.
        </p>
        <Button onClick={onNueva}>
          <Plus className="h-4 w-4" />
          Nueva idea
        </Button>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        Tus ideas. Ábrelas para seguir su discovery y su spec.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sugerencias.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onAbrir(s)}
            className="space-y-2 rounded-xl border bg-card p-3 text-left text-card-foreground transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <p className="text-sm font-medium leading-snug">{s.titulo}</p>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge variant="outline" className="text-[10px] font-normal">
                {etiqueta(CATEGORIA_LABEL, s.categoria)}
              </Badge>
              <Badge
                variant={ESTADO_VARIANTE[s.estado] ?? "secondary"}
                className="text-[10px] font-normal"
              >
                {etiqueta(ESTADO_LABEL, s.estado)}
              </Badge>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

// --- Tablero kanban (superadmin) -------------------------------------------

function Tablero({
  sugerencias,
  onAbrir,
}: {
  sugerencias: Sugerencia[];
  onAbrir: (s: Sugerencia) => void;
}) {
  const queryClient = useQueryClient();
  const [sobreColumna, setSobreColumna] = React.useState<string | null>(null);

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });

  const mover = useMutation({
    mutationFn: async ({ s, destino }: { s: Sugerencia; destino: EstadoSugerencia }) => {
      // Cada columna dispara la acción adecuada del flujo; las demás transiciones
      // son un PATCH directo del estado (override manual). No se usa el valor de retorno.
      if (destino === "discovery") {
        await api.discoverySugerencia(s.id);
      } else if (destino === "building") {
        // Soltar en Building = construir: encola el pipeline (no un simple cambio de estado).
        await api.construirSugerencia(s.id);
      } else {
        await api.actualizarSugerencia(s.id, { estado: destino });
      }
    },
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Acciones RÁPIDAS desde la propia tarjeta (sin abrir el detalle).
  const accionRapida = useMutation({
    mutationFn: async ({ s, accion }: { s: Sugerencia; accion: "construir" | "descartar" }) => {
      if (accion === "construir") {
        await api.construirSugerencia(s.id);
      } else {
        await api.actualizarSugerencia(s.id, { estado: "descartada" });
      }
    },
    onSuccess: (_r, { accion }) => {
      invalidar();
      toast.success(accion === "construir" ? "En cola para construir" : "Descartada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const soltar = (col: (typeof COLUMNAS)[number], ev: React.DragEvent) => {
    ev.preventDefault();
    setSobreColumna(null);
    const id = ev.dataTransfer.getData(MIME_ARRASTRE);
    const s = sugerencias.find((x) => x.id === id);
    // Soltar dentro de la MISMA columna (su estado ya está incluido) no hace nada.
    if (!s || col.incluye.includes(s.estado as EstadoSugerencia)) return;
    mover.mutate({ s, destino: col.estado });
  };

  const archivadas = sugerencias.filter((s) =>
    ESTADOS_ARCHIVO.includes(s.estado as EstadoSugerencia),
  );

  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {COLUMNAS.map((col) => {
          const items = sugerencias.filter((s) =>
            col.incluye.includes(s.estado as EstadoSugerencia),
          );
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
              onDrop={(e) => soltar(col, e)}
            >
              {items.map((s) => (
                <Tarjeta
                  key={s.id}
                  sugerencia={s}
                  onAbrir={() => onAbrir(s)}
                  onAccion={(accion) => accionRapida.mutate({ s, accion })}
                  ocupada={accionRapida.isPending}
                />
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
                className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-1.5 text-left text-xs opacity-70 transition hover:bg-accent hover:opacity-100"
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
        "flex min-h-[16rem] flex-col gap-2 rounded-xl border border-dashed bg-muted/20 p-2 transition-colors",
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
  onAccion,
  ocupada,
}: {
  sugerencia: Sugerencia;
  onAbrir: () => void;
  onAccion: (accion: "construir" | "descartar") => void;
  ocupada: boolean;
}) {
  const estado = sugerencia.estado;
  const enVivo = !!sugerencia.gen_id && estado === "building";
  const enDiscovery = estado === "discovery";
  const specListo = estado === "en_cola"; // discovery terminado: spec listo para construir
  const puedeConstruir =
    estado === "nueva" || estado === "discovery" || estado === "en_cola" || estado === "fallida";
  const puedeDescartar = estado !== "descartada";
  // Las acciones rápidas no deben disparar el click de la tarjeta ni el arrastre.
  const sinPropagar = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation();
    fn();
  };

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
      className="group cursor-grab space-y-2 rounded-xl border bg-card p-3 text-card-foreground transition-colors hover:bg-accent focus:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing"
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
        {enDiscovery && (
          <span className="flex items-center gap-1 text-[10px] text-sky-600">
            <Spinner className="h-3 w-3" aria-hidden="true" />
            en curso
          </span>
        )}
        {specListo && (
          <span className="flex items-center gap-1 text-[10px] text-emerald-600">
            <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
            spec listo
          </span>
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
      {(puedeConstruir || puedeDescartar) && (
        <div className="flex items-center justify-end gap-1 pt-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          {puedeConstruir && (
            <Tooltip label="Construir" side="top">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                disabled={ocupada}
                onClick={sinPropagar(() => onAccion("construir"))}
                aria-label="Construir"
              >
                <Hammer className="h-3.5 w-3.5" />
              </Button>
            </Tooltip>
          )}
          {puedeDescartar && (
            <Tooltip label="Descartar" side="top">
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7 text-destructive hover:text-destructive"
                disabled={ocupada}
                onClick={sinPropagar(() => onAccion("descartar"))}
                aria-label="Descartar"
              >
                <X className="h-3.5 w-3.5" />
              </Button>
            </Tooltip>
          )}
        </div>
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

  const crear = useMutation({
    mutationFn: () =>
      api.crearSugerencia({
        titulo: titulo.trim(),
        detalle: detalle.trim() || undefined,
        categoria,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
      toast.success("Idea creada");
      setTitulo("");
      setDetalle("");
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
          <div className="space-y-1.5 sm:max-w-xs">
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
