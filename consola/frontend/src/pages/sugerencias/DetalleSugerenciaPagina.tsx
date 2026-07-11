import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Coins,
  ExternalLink,
  Hammer,
  MessageSquareWarning,
  Pencil,
  RefreshCw,
  RotateCcw,
  Rocket,
  Search,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipEstado } from "@/components/comunes/ChipEstado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
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
import { useGeneracion } from "@/hooks/use-generacion";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { costeUsd } from "@/lib/formato";
import type { AccionCheckpoint, Sugerencia } from "@/types";

import {
  CATEGORIA_LABEL,
  CLAVE_SUGERENCIAS,
  COMPLEJIDAD_LABEL,
  COMPLEJIDAD_VARIANTE,
  ESTADO_LABEL,
  ESTADO_VARIANTE,
  etiqueta,
} from "./columnas";

/** Sigue EN VIVO la generación en curso de una sugerencia (SSE con fallback a sondeo). */
function StreamGeneracion({ genId }: { genId: string }) {
  const seg = useGeneracion();
  const { iniciar, limpiar } = seg;

  React.useEffect(() => {
    let vivo = true;
    if (!genId) {
      limpiar();
      return;
    }
    api
      .generacion(genId)
      .then((r) => {
        if (vivo) iniciar(r.generacion);
      })
      .catch(() => {
        /* El detalle converge igual cuando la fila se refresca. */
      });
    return () => {
      vivo = false;
    };
  }, [genId, iniciar, limpiar]);

  const gen = seg.generacion;
  if (!gen) return null;
  const salida = (gen.salida ?? "").trim();
  const razon = (gen.razonamiento ?? "").trim();

  return (
    <div className="space-y-2 rounded-xl border border-violet-500/20 bg-violet-500/5 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">Generación en vivo</span>
        <ChipEstado
          estado={seg.ejecutando ? "en_curso" : gen.estado === "error" ? "fallo" : "ok"}
        />
        {gen.metricas?.total_cost_usd != null && (
          <Badge variant="outline" className="gap-1 text-[10px] tabular-nums">
            <Coins className="h-2.5 w-2.5" aria-hidden="true" />
            {costeUsd(gen.metricas.total_cost_usd)}
          </Badge>
        )}
      </div>
      {razon && (
        <div className="max-h-48 overflow-y-auto rounded bg-background/60 p-2">
          <div className="mb-1 text-[11px] font-medium text-muted-foreground">Razonamiento</div>
          <Markdown className="text-xs text-foreground/70">{razon}</Markdown>
        </div>
      )}
      <div className="max-h-96 overflow-y-auto rounded bg-background/60 p-2">
        {salida ? (
          <Markdown className="text-xs text-foreground/90">{salida}</Markdown>
        ) : (
          <p className="text-xs italic text-muted-foreground">
            {seg.ejecutando ? "En curso…" : "Sin salida."}
          </p>
        )}
      </div>
    </div>
  );
}

/** Bloque de markdown (spec / plan) a tamaño de subpágina. Nada si vacío. */
function BloqueMarkdown({ titulo, texto }: { titulo: string; texto: string }) {
  if (!texto.trim()) return null;
  return (
    <div className="space-y-1.5">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {titulo}
      </div>
      <div className="rounded-xl border bg-card p-4">
        <Markdown className="text-sm text-foreground/90">{texto}</Markdown>
      </div>
    </div>
  );
}

/**
 * Área del preview: enlace «Ver preview» + (superadmin) detección de DESFASE respecto a main y
 * botón «Reconstruir preview». El bundle se compila de la rama; si main avanzó sin que el
 * preview se reconstruyera, queda viejo y puede no cargar. La comprobación la hace el worker
 * (compara la rama con origin/main); reconstruir rebasa sobre main y recompila el bundle.
 */
function BloquePreview({ sugerenciaId, esSuper }: { sugerenciaId: string; esSuper: boolean }) {
  const queryClient = useQueryClient();
  const estado = useQuery({
    queryKey: [...CLAVE_SUGERENCIAS, sugerenciaId, "preview-estado"],
    queryFn: ({ signal }) => api.previewEstado(sugerenciaId, signal),
    enabled: esSuper,
    staleTime: 30_000,
  });
  const reconstruir = useMutation({
    mutationFn: () => api.reconstruirPreview(sugerenciaId),
    onSuccess: (res) => {
      toast.success(res.detalle || "Preview reconstruido");
      void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const desfasado = estado.data?.desfasado === true;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" asChild>
          <a href={`/api/preview/${sugerenciaId}/`} target="_blank" rel="noopener">
            <ExternalLink className="h-4 w-4" />
            Ver preview
          </a>
        </Button>
        {esSuper && (
          <Button
            variant="outline"
            onClick={() => reconstruir.mutate()}
            disabled={reconstruir.isPending}
          >
            {reconstruir.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <RefreshCw className="h-4 w-4" />
            )}
            Reconstruir preview
          </Button>
        )}
      </div>
      {desfasado && (
        <p className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-500">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          El preview está desfasado respecto a main: reconstrúyelo para verlo actualizado.
        </p>
      )}
    </div>
  );
}

/** Una acción del flujo pendiente de confirmar: la dispara un botón que avanza de etapa. */
interface AccionFlujo {
  clave: string;
  titulo: string;
  descripcion: string;
  etiquetaConfirmar: string;
  /** `true` en acciones sin agente (promover): el pop-up es solo confirmación, sin nota. */
  sinNota?: boolean;
  ejecutar: (nota: string) => void;
}

/**
 * Pop-up de confirmación de una acción del flujo. Discovery/construir/pedir-cambios/aprobar
 * llevan una NOTA opcional EFÍMERA: se inyecta en el prompt de esa fase y no se persiste (lo
 * permanente va por «Editar idea»). Promover no corre agente: solo confirma (`sinNota`).
 */
function DialogoAccionFlujo({
  accion,
  ocupado,
  onCerrar,
}: {
  accion: AccionFlujo | null;
  ocupado: boolean;
  onCerrar: () => void;
}) {
  const [nota, setNota] = React.useState("");
  // Limpia la nota cada vez que cambia la acción abierta (no arrastrar texto entre etapas).
  React.useEffect(() => {
    setNota("");
  }, [accion?.clave]);

  return (
    <Dialog
      open={accion !== null}
      onOpenChange={(abierto) => {
        if (!abierto) onCerrar();
      }}
    >
      <DialogContent>
        {accion && (
          <>
            <DialogHeader>
              <DialogTitle>{accion.titulo}</DialogTitle>
              <DialogDescription>{accion.descripcion}</DialogDescription>
            </DialogHeader>
            {!accion.sinNota && (
              <div className="space-y-1.5">
                <Label htmlFor="nota-accion">Nota para el agente (opcional)</Label>
                <Textarea
                  id="nota-accion"
                  value={nota}
                  onChange={(e) => setNota(e.target.value)}
                  placeholder="Indica al agente qué tener en cuenta en esta etapa…"
                  rows={4}
                  maxLength={4000}
                  autoFocus
                />
                <p className="text-xs text-muted-foreground">
                  Solo para este lanzamiento; no se guarda. Para cambios permanentes, edita la idea.
                </p>
              </div>
            )}
            <DialogFooter>
              <Button variant="ghost" onClick={onCerrar} disabled={ocupado}>
                Cancelar
              </Button>
              <Button variant="default" onClick={() => accion.ejecutar(nota)} disabled={ocupado}>
                {ocupado ? <Spinner className="h-4 w-4" /> : null}
                {accion.etiquetaConfirmar}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Formulario inline para editar el texto de una idea (título / detalle / categoría). */
function EdicionTexto({
  sugerencia,
  onCancelar,
  onGuardado,
}: {
  sugerencia: Sugerencia;
  onCancelar: () => void;
  onGuardado: () => void;
}) {
  const [titulo, setTitulo] = React.useState(sugerencia.titulo);
  const [detalle, setDetalle] = React.useState(sugerencia.detalle);
  const [categoria, setCategoria] = React.useState(sugerencia.categoria || "idea");

  const guardar = useMutation({
    mutationFn: () =>
      api.actualizarSugerencia(sugerencia.id, {
        titulo: titulo.trim(),
        detalle: detalle.trim(),
        categoria,
      }),
    onSuccess: () => {
      toast.success("Idea actualizada");
      onGuardado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="space-y-4 rounded-xl border bg-card p-4">
      <div className="space-y-1.5">
        <Label htmlFor="edit-titulo">Título</Label>
        <Input
          id="edit-titulo"
          value={titulo}
          onChange={(e) => setTitulo(e.target.value)}
          maxLength={200}
          autoFocus
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="edit-detalle">Detalle</Label>
        <Textarea
          id="edit-detalle"
          value={detalle}
          onChange={(e) => setDetalle(e.target.value)}
          rows={5}
          maxLength={8000}
        />
      </div>
      <div className="space-y-1.5 sm:max-w-xs">
        <Label htmlFor="edit-categoria">Categoría</Label>
        <Select value={categoria} onValueChange={setCategoria}>
          <SelectTrigger id="edit-categoria">
            <SelectValue placeholder="Categoría" />
          </SelectTrigger>
          <SelectContent>
            {Object.keys(CATEGORIA_LABEL).map((c) => (
              <SelectItem key={c} value={c}>
                {etiqueta(CATEGORIA_LABEL, c)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancelar} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button
          onClick={() => guardar.mutate()}
          disabled={!titulo.trim() || guardar.isPending}
        >
          {guardar.isPending ? <Spinner className="h-4 w-4" /> : null}
          Guardar
        </Button>
      </div>
    </div>
  );
}

/**
 * Detalle/spec de una sugerencia como SUBPÁGINA (no popup): título, badges, detalle, stream
 * en vivo, spec/plan/diff y las acciones del flujo. Las acciones del tablero (discovery,
 * construir, checkpoint, promover, descartar, borrar, revivir) son del superadmin; el autor
 * de una idea puede verla y editar su texto.
 */
export default function DetalleSugerenciaPagina() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { usuario } = useSesion();
  const esSuper = usuario?.es_superadmin === true;

  const [pendiente, setPendiente] = React.useState<AccionFlujo | null>(null);
  const [editando, setEditando] = React.useState(false);

  const cerrarPendiente = () => setPendiente(null);

  const query = useQuery({
    queryKey: [...CLAVE_SUGERENCIAS, id],
    queryFn: ({ signal }) => api.sugerencia(id, signal),
    enabled: !!id,
  });

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_SUGERENCIAS });
  };

  const discovery = useMutation({
    mutationFn: (nota: string) => api.discoverySugerencia(id, nota.trim() || undefined),
    onSuccess: () => {
      invalidar();
      cerrarPendiente();
      toast.success("Discovery lanzado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const construir = useMutation({
    mutationFn: (nota: string) => api.construirSugerencia(id, nota.trim() || undefined),
    onSuccess: () => {
      invalidar();
      cerrarPendiente();
      toast.success("En cola para construir");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const checkpoint = useMutation({
    mutationFn: ({ accion, nota }: { accion: AccionCheckpoint; nota: string }) =>
      api.checkpointSugerencia(id, accion, nota.trim() || undefined),
    onSuccess: (_res, { accion }) => {
      invalidar();
      cerrarPendiente();
      toast.success(
        accion === "continuar"
          ? "Checkpoint aprobado"
          : accion === "cambios"
            ? "Cambios solicitados"
            : "Idea cancelada",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const promover = useMutation({
    mutationFn: () => api.promoverSugerencia(id),
    onSuccess: (res) => {
      invalidar();
      cerrarPendiente();
      toast.success(res.detalle || "Promovida a main");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cambiarEstado = useMutation({
    mutationFn: (estado: string) => api.actualizarSugerencia(id, { estado }),
    onSuccess: (_res, estado) => {
      invalidar();
      toast.success(estado === "descartada" ? "Descartada" : "Revivida");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarSugerencia(id),
    onSuccess: () => {
      invalidar();
      toast.success("Eliminada");
      navigate("/sugerencias");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const volver = (
    <Button variant="ghost" size="sm" asChild>
      <Link to="/sugerencias">
        <ArrowLeft className="h-4 w-4" />
        Volver
      </Link>
    </Button>
  );

  if (query.isPending) {
    return (
      <div className="space-y-4">
        {volver}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="space-y-4">
        {volver}
        <BloqueError
          titulo="No se pudo cargar la sugerencia"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      </div>
    );
  }

  const sugerencia = query.data.sugerencia;
  const estado = sugerencia.estado;
  const enRevision = estado === "revision";
  const esDescartada = estado === "descartada";
  // El stream EN VIVO solo mientras hay una generación corriendo (discovery/building). Si no,
  // su `gen_id` apunta a una generación TERMINADA cuyo output ya está guardado en spec/plan/diff:
  // mostrarlo duplicaría el spec. Acabada la generación, mandan los bloques guardados.
  const generando = estado === "discovery" || estado === "building";

  // En el checkpoint FINAL (sin fase siguiente) «Aprobar checkpoint» sería un no-op: solo queda
  // promover. Lo deriva el backend (no duplicamos la máquina de fases en el front).
  const checkpointIntermedio = enRevision && sugerencia.checkpoint_final !== true;

  const ocupado =
    discovery.isPending ||
    construir.isPending ||
    checkpoint.isPending ||
    promover.isPending ||
    cambiarEstado.isPending ||
    borrar.isPending;

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        {volver}
        {!editando && (
          <Button variant="outline" size="sm" onClick={() => setEditando(true)}>
            <Pencil className="h-4 w-4" />
            Editar idea
          </Button>
        )}
      </div>

      <div className="space-y-2">
        <h1 className="text-xl font-semibold leading-tight">{sugerencia.titulo}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="font-normal">
            {etiqueta(CATEGORIA_LABEL, sugerencia.categoria)}
          </Badge>
          <Badge variant={ESTADO_VARIANTE[estado] ?? "secondary"} className="font-normal">
            {etiqueta(ESTADO_LABEL, estado)}
          </Badge>
          {sugerencia.complejidad && (
            <Badge
              variant={COMPLEJIDAD_VARIANTE[sugerencia.complejidad] ?? "outline"}
              className="font-normal"
            >
              {etiqueta(COMPLEJIDAD_LABEL, sugerencia.complejidad)}
            </Badge>
          )}
          {sugerencia.fase && (
            <Badge variant="outline" className="font-normal">
              fase: {sugerencia.fase}
            </Badge>
          )}
          {sugerencia.autor && (
            <span className="text-xs text-muted-foreground">por {sugerencia.autor}</span>
          )}
        </div>
      </div>

      {editando ? (
        <EdicionTexto
          sugerencia={sugerencia}
          onCancelar={() => setEditando(false)}
          onGuardado={() => {
            setEditando(false);
            void query.refetch();
            invalidar();
          }}
        />
      ) : (
        <div className="space-y-5">
          {sugerencia.detalle && (
            <Markdown className="text-sm text-muted-foreground">{sugerencia.detalle}</Markdown>
          )}

          {sugerencia.coste_usd > 0 && (
            <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
              <span className="flex items-center gap-1 tabular-nums">
                <Coins className="h-3.5 w-3.5" aria-hidden="true" />
                {costeUsd(sugerencia.coste_usd)} acumulado
              </span>
            </div>
          )}

          {sugerencia.gen_id && generando && <StreamGeneracion genId={sugerencia.gen_id} />}

          <BloqueMarkdown titulo="Spec (discovery)" texto={sugerencia.spec} />
          <BloqueMarkdown titulo="Plan" texto={sugerencia.plan} />

          {sugerencia.preview_listo && (
            <BloquePreview sugerenciaId={sugerencia.id} esSuper={esSuper} />
          )}

          {/* Acciones del flujo: solo superadmin (control del tablero). Cada botón que AVANZA
              de etapa abre un pop-up de confirmación con nota opcional para el agente. */}
          {esSuper && (
            <div className="flex flex-wrap items-center justify-end gap-2 border-t pt-4">
              {esDescartada && (
                <Button
                  variant="outline"
                  onClick={() => cambiarEstado.mutate("nueva")}
                  disabled={ocupado}
                >
                  <RotateCcw className="h-4 w-4" />
                  Revivir
                </Button>
              )}
              {(estado === "nueva" || estado === "fallida") && (
                <Button
                  variant="outline"
                  disabled={ocupado}
                  onClick={() =>
                    setPendiente({
                      clave: "discovery",
                      titulo: "Lanzar discovery",
                      descripcion:
                        "El agente analizará la idea y producirá el SPEC. Puedes añadir una nota para orientar ese análisis.",
                      etiquetaConfirmar: "Lanzar discovery",
                      ejecutar: (nota) => discovery.mutate(nota),
                    })
                  }
                >
                  <Search className="h-4 w-4" />
                  Lanzar discovery
                </Button>
              )}
              {(estado === "nueva" ||
                estado === "discovery" ||
                estado === "en_cola" ||
                estado === "fallida") && (
                <Button
                  disabled={ocupado}
                  onClick={() =>
                    setPendiente({
                      clave: "construir",
                      titulo: "Construir",
                      descripcion:
                        "Arranca el pipeline de desarrollo (analyze→plan→build→review). Una nota viaja como contexto a los agentes que lo ejecutan.",
                      etiquetaConfirmar: "Construir",
                      ejecutar: (nota) => construir.mutate(nota),
                    })
                  }
                >
                  <Hammer className="h-4 w-4" />
                  Construir
                </Button>
              )}
              {enRevision && (
                <>
                  <Button
                    variant="outline"
                    disabled={ocupado}
                    onClick={() =>
                      setPendiente({
                        clave: "cambios",
                        titulo: "Pedir cambios",
                        descripcion:
                          "Re-ejecuta la construcción con tu nota como feedback. Explica qué cambiar.",
                        etiquetaConfirmar: "Pedir cambios",
                        ejecutar: (nota) => checkpoint.mutate({ accion: "cambios", nota }),
                      })
                    }
                  >
                    <MessageSquareWarning className="h-4 w-4" />
                    Pedir cambios
                  </Button>
                  {checkpointIntermedio && (
                    <Button
                      disabled={ocupado}
                      onClick={() =>
                        setPendiente({
                          clave: "continuar",
                          titulo: "Aprobar checkpoint",
                          descripcion:
                            "Aprueba esta fase y sigue el pipeline. Puedes añadir una nota para la siguiente fase.",
                          etiquetaConfirmar: "Aprobar checkpoint",
                          ejecutar: (nota) => checkpoint.mutate({ accion: "continuar", nota }),
                        })
                      }
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      Aprobar checkpoint
                    </Button>
                  )}
                </>
              )}
              {enRevision && (
                <Button
                  disabled={ocupado}
                  onClick={() =>
                    setPendiente({
                      clave: "promover",
                      titulo: "Promover a main",
                      descripcion:
                        "Rebasa la rama sobre lo último de main y hace el git push real, marcando la idea como hecha. Si el rebase tiene conflictos, un agente Opus los resuelve antes de empujar.",
                      etiquetaConfirmar: "Promover a main",
                      sinNota: true,
                      ejecutar: () => promover.mutate(),
                    })
                  }
                >
                  <Rocket className="h-4 w-4" />
                  Promover a main
                </Button>
              )}
              {!esDescartada && estado !== "hecha" && (
                <Button
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => cambiarEstado.mutate("descartada")}
                  disabled={ocupado}
                >
                  <X className="h-4 w-4" />
                  Descartar
                </Button>
              )}
              {esDescartada && (
                <Button
                  variant="ghost"
                  className="text-destructive hover:text-destructive"
                  onClick={() => borrar.mutate()}
                  disabled={ocupado}
                >
                  {borrar.isPending ? (
                    <Spinner className="h-4 w-4" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Borrar
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      <DialogoAccionFlujo accion={pendiente} ocupado={ocupado} onCerrar={cerrarPendiente} />
    </div>
  );
}
