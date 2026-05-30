/**
 * Panel de COLABORACIÓN de una pieza del tablero (inspirado en Planable):
 *
 *   - Comentarios internos: hilo de discusión de redacción por item (con opción de atar
 *     un comentario a una red concreta y marcar hilos como resueltos).
 *   - Historial de versiones del copy: ver snapshots por plataforma y revertir a uno.
 *   - Aprobación multinivel: cadena de niveles (Edición → Coordinación → Dirección) con
 *     decisión por orden, trazabilidad (quién/cuándo) y bloqueo "otro par de ojos".
 *
 * Se monta sobre el modelo `contenido`/`contenido_plataforma`: los comentarios cuelgan del
 * contenido padre; versiones y aprobación, de cada `contenido_plataforma`. Todo vía la API
 * de `lib/api` (familia `comentarios`/`copy`/`aprobacion`). El estado del tablero se
 * invalida al cambiar el copy (revert/guardar) para que la tarjeta refleje el copy nuevo.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  History,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  Trash2,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  Contenido,
  ContenidoPlataforma,
  DecisionAprobacion,
  EstadoCadenaAprobacion,
} from "@/types";

const CLAVE_TABLERO = ["contenido"] as const;

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "No se pudo completar la acción.";
}

function fecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString("es-MX", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

const ESTADO_CADENA_LABEL: Record<EstadoCadenaAprobacion, string> = {
  sin_cadena: "Sin cadena",
  pendiente: "En aprobación",
  aprobado: "Aprobada",
  rechazado: "Rechazada",
};

const ESTADO_CADENA_VARIANTE: Record<EstadoCadenaAprobacion, "secondary" | "aviso" | "ok" | "error"> = {
  sin_cadena: "secondary",
  pendiente: "aviso",
  aprobado: "ok",
  rechazado: "error",
};

export function PanelColaboracion({
  contenido,
  abierto,
  onCerrar,
}: {
  contenido: Contenido;
  abierto: boolean;
  onCerrar: () => void;
}) {
  const plataformas = contenido.plataformas;
  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4" />
            Colaboración · {contenido.titulo}
          </DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="comentarios">
          <TabsList className="w-full">
            <TabsTrigger value="comentarios" className="flex-1">
              <MessageSquare className="mr-1.5 h-3.5 w-3.5" /> Comentarios
            </TabsTrigger>
            <TabsTrigger value="versiones" className="flex-1" disabled={plataformas.length === 0}>
              <History className="mr-1.5 h-3.5 w-3.5" /> Versiones
            </TabsTrigger>
            <TabsTrigger value="aprobacion" className="flex-1" disabled={plataformas.length === 0}>
              <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> Aprobación
            </TabsTrigger>
          </TabsList>
          <TabsContent value="comentarios" className="pt-3">
            <Comentarios contenido={contenido} />
          </TabsContent>
          <TabsContent value="versiones" className="pt-3">
            <PorPlataforma plataformas={plataformas} render={(p) => <Versiones plataforma={p} />} />
          </TabsContent>
          <TabsContent value="aprobacion" className="pt-3">
            <PorPlataforma plataformas={plataformas} render={(p) => <Aprobacion plataforma={p} />} />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

/** Selector de plataforma compartido por las pestañas que operan por red. */
function PorPlataforma({
  plataformas,
  render,
}: {
  plataformas: ContenidoPlataforma[];
  render: (plataforma: ContenidoPlataforma) => React.ReactNode;
}) {
  const [sel, setSel] = React.useState(plataformas[0]?.id ?? "");
  const actual = plataformas.find((p) => p.id === sel) ?? plataformas[0];
  if (!actual) {
    return <EstadoVacio titulo="Sin plataformas" texto="Añade una red a este contenido primero." />;
  }
  return (
    <div className="space-y-3">
      {plataformas.length > 1 && (
        <Select value={actual.id} onValueChange={setSel}>
          <SelectTrigger className="h-8 w-48 text-xs" aria-label="Plataforma">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {plataformas.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.red_nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {render(actual)}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Comentarios internos                                                         //
// --------------------------------------------------------------------------- //

function Comentarios({ contenido }: { contenido: Contenido }) {
  const queryClient = useQueryClient();
  const clave = ["comentarios", contenido.id] as const;
  const [texto, setTexto] = React.useState("");

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.comentarios(contenido.id, undefined, signal),
  });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  const crear = useMutation({
    mutationFn: () => api.crearComentario(contenido.id, texto.trim()),
    onSuccess: () => {
      setTexto("");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const resolver = useMutation({
    mutationFn: ({ id, resuelto }: { id: string; resuelto: boolean }) =>
      api.actualizarComentario(id, { resuelto }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarComentario(id),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  const comentarios = query.data?.comentarios ?? [];

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border p-2">
        <Textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          placeholder="Escribe un comentario para el equipo…"
          rows={2}
          className="text-sm"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={!texto.trim() || crear.isPending}
            onClick={() => crear.mutate()}
          >
            Comentar
          </Button>
        </div>
      </div>

      {comentarios.length === 0 ? (
        <EstadoVacio titulo="Sin comentarios" texto="Arranca la conversación del equipo." />
      ) : (
        <ul className="space-y-2">
          {comentarios.map((c) => (
            <li
              key={c.id}
              className={cn(
                "rounded-md border p-2 text-sm",
                c.resuelto && "bg-muted/40 opacity-70",
              )}
            >
              <div className="mb-1 flex items-center justify-between gap-2">
                <Autor nombre={c.autor_nombre} className="text-xs" />
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  {fecha(c.creado)}
                  {c.resuelto && (
                    <Badge variant="ok" className="font-normal">
                      Resuelto
                    </Badge>
                  )}
                </span>
              </div>
              <p className="whitespace-pre-wrap break-words">{c.texto}</p>
              <div className="mt-1.5 flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => resolver.mutate({ id: c.id, resuelto: !c.resuelto })}
                  disabled={resolver.isPending}
                >
                  {c.resuelto ? "Reabrir" : "Marcar resuelto"}
                </Button>
                <Tooltip label="Borrar comentario">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Borrar comentario"
                    className="ml-auto h-6 w-6 text-muted-foreground hover:text-destructive"
                    onClick={() => borrar.mutate(c.id)}
                    disabled={borrar.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </Tooltip>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Historial de versiones del copy                                             //
// --------------------------------------------------------------------------- //

function Versiones({ plataforma }: { plataforma: ContenidoPlataforma }) {
  const queryClient = useQueryClient();
  const clave = ["copy-versiones", plataforma.id] as const;
  const [borrador, setBorrador] = React.useState(plataforma.copy);

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.copyVersiones(plataforma.id, signal),
  });
  const tras = () => {
    void queryClient.invalidateQueries({ queryKey: clave });
    void queryClient.invalidateQueries({ queryKey: CLAVE_TABLERO });
  };

  const guardar = useMutation({
    mutationFn: () => api.guardarCopy(plataforma.id, borrador),
    onSuccess: () => {
      toast.success("Copy guardado (versión registrada).");
      tras();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const revertir = useMutation({
    mutationFn: (versionId: string) => api.revertirCopy(plataforma.id, versionId),
    onSuccess: (r) => {
      setBorrador(r.plataforma.copy);
      toast.success("Copy revertido.");
      tras();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const versiones = query.data?.versiones ?? [];

  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-md border p-2">
        <p className="text-xs font-medium text-muted-foreground">Copy actual ({plataforma.red_nombre})</p>
        <Textarea
          value={borrador}
          onChange={(e) => setBorrador(e.target.value)}
          rows={3}
          className="text-sm"
          placeholder="Escribe el copy…"
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={guardar.isPending || borrador === plataforma.copy}
            onClick={() => guardar.mutate()}
          >
            Guardar versión
          </Button>
        </div>
      </div>

      {versiones.length === 0 ? (
        <EstadoVacio titulo="Sin versiones previas" texto="Cada cambio de copy queda aquí." />
      ) : (
        <ul className="space-y-2">
          {versiones.map((v) => (
            <li key={v.id} className="rounded-md border p-2 text-sm">
              <div className="mb-1 flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <Badge variant="secondary" className="font-normal">
                    v{v.version}
                  </Badge>
                  <Autor nombre={v.autor_nombre} className="text-xs" />
                </span>
                <span className="text-xs text-muted-foreground">{fecha(v.creado)}</span>
              </div>
              {v.nota && <p className="mb-1 text-xs italic text-muted-foreground">{v.nota}</p>}
              <p className="whitespace-pre-wrap break-words text-muted-foreground">
                {v.copy || <span className="italic">(copy vacío)</span>}
              </p>
              <div className="mt-1.5 flex justify-end">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-xs"
                  onClick={() => revertir.mutate(v.id)}
                  disabled={revertir.isPending}
                >
                  <RotateCcw className="mr-1 h-3 w-3" /> Revertir a esta
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Aprobación multinivel                                                        //
// --------------------------------------------------------------------------- //

function Aprobacion({ plataforma }: { plataforma: ContenidoPlataforma }) {
  const queryClient = useQueryClient();
  const clave = ["aprobacion", plataforma.id] as const;

  const query = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.cadenaAprobacion(plataforma.id, signal),
  });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  const crear = useMutation({
    mutationFn: () => api.crearCadenaAprobacion(plataforma.id),
    onSuccess: () => {
      toast.success("Cadena de aprobación creada.");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const decidir = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: DecisionAprobacion }) =>
      api.decidirNivelAprobacion(id, decision as "aprobado" | "rechazado"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TABLERO });
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cadena = query.data;
  const niveles = cadena?.niveles ?? [];

  if (query.isLoading) {
    return <p className="text-sm text-muted-foreground">Cargando…</p>;
  }

  if (niveles.length === 0) {
    return (
      <div className="space-y-3">
        <EstadoVacio
          titulo="Sin cadena de aprobación"
          texto="Crea la cadena Edición → Coordinación → Dirección para esta pieza."
        />
        <div className="flex justify-center">
          <Button size="sm" onClick={() => crear.mutate()} disabled={crear.isPending}>
            <ShieldCheck className="mr-1.5 h-3.5 w-3.5" /> Crear cadena de aprobación
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <Badge
          variant={ESTADO_CADENA_VARIANTE[cadena!.estado]}
          className="font-normal"
        >
          {ESTADO_CADENA_LABEL[cadena!.estado]}
        </Badge>
        <Button
          variant="ghost"
          size="sm"
          className="h-6 px-2 text-xs"
          onClick={() => crear.mutate()}
          disabled={crear.isPending}
        >
          <RotateCcw className="mr-1 h-3 w-3" /> Reiniciar cadena
        </Button>
      </div>
      <ol className="space-y-2">
        {niveles.map((n) => {
          const esActual = cadena!.nivel_actual === n.id;
          return (
            <li
              key={n.id}
              className={cn(
                "rounded-md border p-2 text-sm",
                esActual && "border-primary",
                n.decision === "aprobado" && "bg-muted/40",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-medium">
                  {n.decision === "aprobado" ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                  ) : n.decision === "rechazado" ? (
                    <XCircle className="h-4 w-4 text-destructive" />
                  ) : (
                    <span className="flex h-4 w-4 items-center justify-center text-xs text-muted-foreground">
                      {n.nivel}
                    </span>
                  )}
                  {n.etiqueta}
                </span>
                {n.decision !== "pendiente" && (
                  <span className="text-xs text-muted-foreground">
                    {n.decisor_nombre || "—"} · {fecha(n.decidido_en)}
                  </span>
                )}
              </div>
              {esActual && n.decision === "pendiente" && (
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => decidir.mutate({ id: n.id, decision: "aprobado" })}
                    disabled={decidir.isPending}
                  >
                    <Check className="mr-1 h-3.5 w-3.5" /> Aprobar
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs"
                    onClick={() => decidir.mutate({ id: n.id, decision: "rechazado" })}
                    disabled={decidir.isPending}
                  >
                    <XCircle className="mr-1 h-3.5 w-3.5" /> Rechazar
                  </Button>
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
