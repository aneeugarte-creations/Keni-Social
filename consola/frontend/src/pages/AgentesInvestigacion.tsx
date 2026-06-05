/**
 * Agentes de investigación (Ola 6).
 *
 * Los agentes investigan por marca/línea/tema y dejan candidatos fechados.
 * Proponen; el humano filtra: aceptar → tablero, descartar → fuera.
 *
 * Contrato: docs/maquina-contenido/06-agentes-investigacion.md
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Calendar,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { InvBrief, InvCandidato } from "@/types";

// ── Constantes ─────────────────────────────────────────────────────────────────

const CLAVES_BRIEFS = ["investigacion", "briefs"] as const;
const CLAVES_CANDIDATOS = (fecha: string, marca?: string, estado?: string) =>
  ["investigacion", "candidatos", fecha, marca ?? "", estado ?? ""] as const;
const PREFIJO_CANDIDATOS = ["investigacion", "candidatos"] as const;

// ── Utilidades ─────────────────────────────────────────────────────────────────

function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function etiquetaFecha(fecha: string): string {
  if (!fecha) return "";
  try {
    return new Intl.DateTimeFormat("es-MX", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(new Date(`${fecha}T00:00:00`));
  } catch {
    return fecha;
  }
}

// ── Diálogo: crear / editar brief ──────────────────────────────────────────────

interface PropsBriefDialogo {
  brief: InvBrief | null;
  abierto: boolean;
  onCerrar: () => void;
  /** Marca activa global: se usa como valor por defecto al crear un brief nuevo. */
  marcaActivaDefault?: string | null;
}

function DialogoBrief({ brief, abierto, onCerrar, marcaActivaDefault }: PropsBriefDialogo) {
  const queryClient = useQueryClient();

  const [nombre, setNombre] = React.useState(brief?.nombre ?? "");
  const [marca, setMarca] = React.useState(brief?.marca ?? (marcaActivaDefault ?? ""));
  const [linea, setLinea] = React.useState(brief?.linea ?? "");
  const [instrucciones, setInstrucciones] = React.useState(brief?.instrucciones ?? "");
  const [idiomas, setIdiomas] = React.useState(brief?.idiomas ?? "");

  React.useEffect(() => {
    if (abierto) {
      setNombre(brief?.nombre ?? "");
      // Al crear nuevo brief: pre-rellena con la marca activa (editable). Al editar: respeta la guardada.
      setMarca(brief?.marca ?? (marcaActivaDefault ?? ""));
      setLinea(brief?.linea ?? "");
      setInstrucciones(brief?.instrucciones ?? "");
      setIdiomas(brief?.idiomas ?? "");
    }
  }, [abierto, brief, marcaActivaDefault]);

  const guardar = useMutation({
    mutationFn: () => {
      if (brief) {
        return api.investigacion.editarBrief(brief.id, {
          nombre: nombre.trim(),
          marca: marca.trim(),
          linea: linea.trim(),
          instrucciones: instrucciones.trim(),
          idiomas: idiomas.trim(),
        });
      }
      return api.investigacion.crearBrief({
        nombre: nombre.trim(),
        marca: marca.trim(),
        linea: linea.trim() || undefined,
        instrucciones: instrucciones.trim(),
        idiomas: idiomas.trim() || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVES_BRIEFS });
      toast.success(brief ? "Brief actualizado." : "Brief creado.");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    nombre.trim().length > 0 &&
    marca.trim().length > 0 &&
    instrucciones.trim().length > 0 &&
    !guardar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bot className="h-5 w-5" />
            {brief ? "Editar brief" : "Nuevo brief"}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="brief-nombre">Nombre del brief</Label>
            <Input
              id="brief-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej. Noticias deportivas UnoTV"
              className="mt-1"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="brief-marca">Marca (id)</Label>
              <Input
                id="brief-marca"
                value={marca}
                onChange={(e) => setMarca(e.target.value)}
                placeholder="Ej. unotv"
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="brief-linea">
                Línea / tema{" "}
                <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Input
                id="brief-linea"
                value={linea}
                onChange={(e) => setLinea(e.target.value)}
                placeholder="Ej. Deportes"
                className="mt-1"
              />
            </div>
          </div>
          <div>
            <Label htmlFor="brief-instrucciones">Instrucciones</Label>
            <Textarea
              id="brief-instrucciones"
              value={instrucciones}
              onChange={(e) => setInstrucciones(e.target.value)}
              placeholder="¿Qué buscar? ¿Qué fuentes preferir? ¿Qué evitar?"
              rows={4}
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="brief-idiomas">
              Idiomas (CSV){" "}
              <span className="font-normal text-muted-foreground">(opcional, vacío = cualquiera)</span>
            </Label>
            <Input
              id="brief-idiomas"
              value={idiomas}
              onChange={(e) => setIdiomas(e.target.value)}
              placeholder="Ej. es, en"
              className="mt-1"
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {brief ? "Guardar cambios" : "Crear brief"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Tarjeta de brief ───────────────────────────────────────────────────────────

interface PropsTarjetaBrief {
  brief: InvBrief;
  onEditar: () => void;
}

function TarjetaBrief({ brief, onEditar }: PropsTarjetaBrief) {
  const queryClient = useQueryClient();

  const alternarActivo = useMutation({
    mutationFn: () =>
      api.investigacion.editarBrief(brief.id, { activo: brief.activo ? 0 : 1 }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVES_BRIEFS });
      toast.success(brief.activo ? "Brief desactivado." : "Brief activado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.investigacion.borrarBrief(brief.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVES_BRIEFS });
      toast.success("Brief eliminado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // La investigación corre ASÍNCRONA en el worker (el back no tiene `claude`). El POST
  // devuelve una `generacion` en curso; la sondeamos con `useGeneracion` y, al completar,
  // refrescamos los candidatos. El parseo inserta los `inv_candidato` en el worker.
  const seguimiento = useGeneracion();
  const correr = useMutation({
    mutationFn: () => api.investigacion.correr({ brief_id: brief.id }),
    onSuccess: (data) => {
      if (data.generacion) seguimiento.iniciar(data.generacion);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  React.useEffect(() => {
    const g = seguimiento.generacion;
    if (!g || seguimiento.ejecutando) return;
    if (g.estado === "completado") {
      void queryClient.invalidateQueries({ queryKey: PREFIJO_CANDIDATOS });
      const n = (g.resultado as { candidatos?: number } | null)?.candidatos ?? 0;
      toast.success(
        n > 0
          ? `${n} candidato${n !== 1 ? "s" : ""} encontrado${n !== 1 ? "s" : ""}.`
          : "Investigación completada, sin candidatos nuevos.",
      );
      seguimiento.limpiar();
    } else if (g.estado === "error") {
      toast.error(g.error || "No se pudo completar la investigación.");
      seguimiento.limpiar();
    }
  }, [seguimiento.generacion, seguimiento.ejecutando, seguimiento, queryClient]);

  const investigando = correr.isPending || seguimiento.ejecutando;
  const esActivo = brief.activo === 1;

  return (
    <div
      className={`rounded-md border p-3 text-sm ${!esActivo ? "opacity-60 bg-muted/30" : "bg-card"}`}
      data-testid="brief-card"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <p className="font-medium">{brief.nombre || "(sin nombre)"}</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {brief.marca && (
              <Badge variant="secondary" className="text-xs">{brief.marca}</Badge>
            )}
            {brief.linea && (
              <Badge variant="outline" className="text-xs">{brief.linea}</Badge>
            )}
            {brief.idiomas && (
              <Badge variant="outline" className="text-xs uppercase">{brief.idiomas}</Badge>
            )}
            {!esActivo && (
              <Badge variant="secondary" className="text-xs">Inactivo</Badge>
            )}
          </div>
          {brief.instrucciones && (
            <p className="mt-1.5 line-clamp-2 text-xs text-muted-foreground">
              {brief.instrucciones}
            </p>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs"
              onClick={onEditar}
              aria-label={`Editar brief "${brief.nombre}"`}
            >
              Editar
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 px-2 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => borrar.mutate()}
              disabled={borrar.isPending}
              aria-label={`Borrar brief "${brief.nombre}"`}
            >
              {borrar.isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Trash2 className="h-3 w-3" />
              )}
            </Button>
          </div>
          <div className="flex items-center gap-1.5">
            <Switch
              checked={esActivo}
              onCheckedChange={() => alternarActivo.mutate()}
              disabled={alternarActivo.isPending}
              aria-label={esActivo ? "Desactivar brief" : "Activar brief"}
            />
            <Button
              size="sm"
              className="h-7 gap-1 px-2 text-xs"
              onClick={() => correr.mutate()}
              disabled={investigando}
              aria-label={`Investigar ahora con brief "${brief.nombre}"`}
              data-testid="btn-investigar"
            >
              {investigando ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Bot className="h-3 w-3" />
              )}
              {investigando ? "Investigando…" : "Investigar ahora"}
            </Button>
          </div>
        </div>
      </div>

      {/* Visor en vivo del stream de investigación mientras corre */}
      {seguimiento.generacion && seguimiento.ejecutando && (
        <div className="mt-3 border-t pt-3" data-testid="investigacion-progreso">
          <ProgresoGeneracion
            generacion={seguimiento.generacion}
            onCancelar={seguimiento.cancelar}
            cancelando={seguimiento.cancelando}
          />
        </div>
      )}
    </div>
  );
}

// ── Sección de gestión de briefs ───────────────────────────────────────────────

function SeccionBriefs() {
  const { marcaActiva } = useMarcaActiva();
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [briefEditando, setBriefEditando] = React.useState<InvBrief | null>(null);
  const [expandido, setExpandido] = React.useState(true);

  const query = useQuery({
    queryKey: CLAVES_BRIEFS,
    queryFn: ({ signal }) => api.investigacion.briefs(signal),
    staleTime: 60 * 1000,
  });

  const briefs = query.data?.briefs ?? [];

  function abrirNuevo() {
    setBriefEditando(null);
    setDialogoAbierto(true);
  }

  function abrirEditar(brief: InvBrief) {
    setBriefEditando(brief);
    setDialogoAbierto(true);
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" />
            Briefs de investigación
            {briefs.length > 0 && (
              <Badge variant="secondary">{briefs.length}</Badge>
            )}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" onClick={abrirNuevo}>
              <Plus className="h-4 w-4" />
              Nuevo
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setExpandido((v) => !v)}
              aria-label={expandido ? "Colapsar briefs" : "Expandir briefs"}
            >
              {expandido ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          Configura lo que deben investigar los agentes: marca, tema e instrucciones. Luego corre
          cada brief con "Investigar ahora" para generar candidatos del día.
        </p>
      </CardHeader>
      {expandido && (
        <CardContent className="space-y-2">
          {query.isPending ? (
            <div className="space-y-2">
              {[0, 1].map((i) => (
                <Skeleton key={i} className="h-20 w-full rounded-md" />
              ))}
            </div>
          ) : query.isError ? (
            <BloqueError
              titulo="No se pudieron cargar los briefs"
              mensaje={mensajeError(query.error)}
              onReintentar={() => void query.refetch()}
              cargando={query.isFetching}
            />
          ) : briefs.length === 0 ? (
            <EstadoVacioTexto
              texto="Aún no hay briefs. Crea el primero con el botón de arriba."
              className="py-4"
            />
          ) : (
            briefs.map((brief) => (
              <TarjetaBrief
                key={brief.id}
                brief={brief}
                onEditar={() => abrirEditar(brief)}
              />
            ))
          )}
        </CardContent>
      )}

      <DialogoBrief
        brief={briefEditando}
        abierto={dialogoAbierto}
        onCerrar={() => setDialogoAbierto(false)}
        marcaActivaDefault={marcaActiva}
      />
    </Card>
  );
}

// ── Tarjeta de candidato ───────────────────────────────────────────────────────

interface PropsCandidatoCard {
  candidato: InvCandidato;
  fecha: string;
}

function CandidatoCard({ candidato, fecha }: PropsCandidatoCard) {
  const queryClient = useQueryClient();

  const aceptar = useMutation({
    mutationFn: () => api.investigacion.aceptar(candidato.id, { generar: false }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["investigacion", "candidatos", fecha],
      });
      toast.success("Copy en marcha — aparecerá en el Feed para imagen y aprobación.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartar = useMutation({
    mutationFn: () => api.investigacion.descartar(candidato.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["investigacion", "candidatos", fecha],
      });
      toast.success("Candidato descartado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const esAceptado = candidato.estado === "aceptado";
  const esDescartado = candidato.estado === "descartado";
  const esNuevo = candidato.estado === "nuevo";

  return (
    <div
      className={`rounded-md border p-3 text-sm ${esDescartado ? "opacity-50 bg-muted/30" : esAceptado ? "bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800" : "bg-card"}`}
      data-testid="candidato-card"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-medium leading-snug">{candidato.titulo || "(sin título)"}</p>
        <div className="flex shrink-0 items-center gap-1">
          {esNuevo && (
            <>
              <Badge variant="secondary" className="text-xs">En el pool</Badge>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                onClick={() => aceptar.mutate()}
                disabled={aceptar.isPending || descartar.isPending}
                aria-label={`Empujar ya "${candidato.titulo}"`}
                title="Forzar esta nota al feed ahora. Normalmente el auto-feed lleva solas las historias relevantes."
                data-testid="btn-aceptar"
              >
                {aceptar.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Send className="h-3 w-3" />
                )}
                Empujar ya
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
                onClick={() => descartar.mutate()}
                disabled={aceptar.isPending || descartar.isPending}
                aria-label={`Descartar "${candidato.titulo}"`}
                data-testid="btn-descartar"
              >
                {descartar.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <X className="h-3 w-3" />
                )}
                Descartar
              </Button>
            </>
          )}
          {esAceptado && (
            <Badge variant="ok" className="gap-1 text-xs">
              <CheckCircle2 className="h-3 w-3" />
              En el feed
            </Badge>
          )}
          {esDescartado && (
            <Badge variant="secondary" className="gap-1 text-xs">
              Descartado
            </Badge>
          )}
        </div>
      </div>

      {candidato.resumen && (
        <p className="mt-1 text-muted-foreground">{candidato.resumen}</p>
      )}

      {candidato.por_que && (
        <p className="mt-1 text-xs italic text-muted-foreground">
          {candidato.por_que}
        </p>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {(candidato.marca_nombre ?? candidato.marca) && (
          <Badge variant="secondary" className="text-xs">
            {candidato.marca_nombre ?? candidato.marca}
          </Badge>
        )}
        {candidato.linea && (
          <Badge variant="outline" className="text-xs">{candidato.linea}</Badge>
        )}
        {candidato.fuente && (
          <Badge variant="outline" className="text-xs">{candidato.fuente}</Badge>
        )}
        {candidato.idioma && candidato.idioma !== "es" && (
          <Badge variant="outline" className="text-xs uppercase">
            {candidato.idioma}
          </Badge>
        )}
        {candidato.enlace && (
          <a
            href={candidato.enlace}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
            aria-label={`Abrir fuente de "${candidato.titulo}"`}
          >
            <ExternalLink className="h-3 w-3" />
            Fuente
          </a>
        )}
      </div>
    </div>
  );
}

// ── Sección de candidatos del día ──────────────────────────────────────────────

function SeccionCandidatos() {
  const { marcaActiva } = useMarcaActiva();
  const [fecha, setFecha] = React.useState<string>(hoyIso);
  const [filtroEstado, setFiltroEstado] = React.useState<"" | "nuevo" | "aceptado" | "descartado">("");

  const query = useQuery({
    queryKey: CLAVES_CANDIDATOS(fecha, marcaActiva ?? undefined, filtroEstado || undefined),
    queryFn: ({ signal }) =>
      api.investigacion.candidatos(
        { fecha, marca: marcaActiva ?? undefined, estado: filtroEstado || undefined },
        signal,
      ),
    staleTime: 30 * 1000,
  });

  const candidatos = query.data?.candidatos ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Calendar className="h-4 w-4" />
            Candidatos del día
            {candidatos.length > 0 && (
              <Badge variant="secondary">{candidatos.length}</Badge>
            )}
          </CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            {/* Selector de fecha */}
            <div className="flex items-center gap-1.5">
              <Label htmlFor="cand-fecha" className="text-xs text-muted-foreground whitespace-nowrap">
                Día editorial
              </Label>
              <Input
                id="cand-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value || hoyIso())}
                className="w-36 text-xs"
                aria-label="Seleccionar fecha de candidatos"
              />
            </div>

            {/* Filtro de estado */}
            <div className="flex items-center gap-1">
              {(["", "nuevo", "aceptado", "descartado"] as const).map((est) => (
                <Button
                  key={est || "todos"}
                  size="sm"
                  variant={filtroEstado === est ? "default" : "outline"}
                  className="h-7 px-2 text-xs"
                  onClick={() => setFiltroEstado(est)}
                >
                  {est === "" ? "Todos" : est.charAt(0).toUpperCase() + est.slice(1)}
                </Button>
              ))}
            </div>

            {/* Refrescar */}
            <Button
              size="sm"
              variant="outline"
              className="h-7 w-7 p-0"
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              aria-label="Refrescar candidatos"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${query.isFetching ? "animate-spin" : ""}`} />
            </Button>
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {etiquetaFecha(fecha)} — Los agentes proponen; tú decides qué va al feed.
        </p>
      </CardHeader>
      <CardContent className="space-y-2">
        {query.isPending ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <BloqueError
            titulo="No se pudieron cargar los candidatos"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : candidatos.length === 0 ? (
          <EstadoVacioTexto
            texto={
              filtroEstado
                ? `No hay candidatos con estado "${filtroEstado}" para esta fecha.`
                : 'No hay candidatos para esta fecha. Corre un brief con "Investigar ahora".'
            }
            className="py-6"
          />
        ) : (
          candidatos.map((c) => (
            <CandidatoCard key={c.id} candidato={c} fecha={fecha} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

// ── Página principal ───────────────────────────────────────────────────────────

export default function AgentesInvestigacion() {
  return (
    <>
      <PageHeader
        titulo="Agentes de investigación"
        descripcion="Los agentes investigan por marca y tema, y dejan candidatos fechados. Tú decides qué entra al feed."
      />

      <div className="space-y-6">
        <SeccionBriefs />
        <SeccionCandidatos />
      </div>
    </>
  );
}
