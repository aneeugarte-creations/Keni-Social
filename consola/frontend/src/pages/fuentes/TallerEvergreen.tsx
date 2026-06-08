/**
 * Taller EVERGREEN: banco de ideas de contenido evergreen (evergreen) por marca.
 *
 * Dos bloques:
 *   1. "Proponer ideas": elige marca + contexto opcional y lanza la IA (`/evergreen/proponer`),
 *      que propone ideas en segundo plano. Se sigue con `useGeneracion` (igual que el resto
 *      de generaciones de la consola) y al terminar se refresca la lista.
 *   2. Lista de ideas con filtro por estado y acciones: Aprobar / Descartar y, cuando una
 *      idea está aprobada, Generar la pieza evergreen (`/evergreen/ideas/{id}/generar`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleSlash,
  Leaf,
  Loader2,
  Plus,
  RotateCcw,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  EstadoIdeaEvergreen,
  IdeaEvergreen,
  MarcaDisponible,
  RedPublicacion,
} from "@/types";

const CLAVE_IDEAS = ["evergreen", "ideas"] as const;

/** Centinela "todos los estados" del filtro. */
const ESTADO_TODOS = "__todos__";

const ESTADO_LABEL: Record<string, string> = {
  propuesta: "Propuesta",
  aprobada: "Aprobada",
  descartada: "Descartada",
};

export function TallerEvergreen({
  marcas,
  redes,
}: {
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const [estadoFiltro, setEstadoFiltro] = React.useState(ESTADO_TODOS);

  const query = useQuery({
    queryKey: [...CLAVE_IDEAS, estadoFiltro],
    queryFn: ({ signal }) =>
      api.ideasEvergreen(
        { estado: estadoFiltro === ESTADO_TODOS ? undefined : estadoFiltro },
        signal,
      ),
  });

  const ideas = React.useMemo(() => query.data?.ideas ?? [], [query.data]);
  const estados = query.data?.estados ?? ["propuesta", "aprobada", "descartada"];

  return (
    <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
      <ProponerIdeas marcas={marcas} />

      <Card className="h-fit">
        <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Leaf className="h-4 w-4" />
            Banco de ideas evergreen
            <Badge variant="secondary" className="ml-1">
              {ideas.length}
            </Badge>
          </CardTitle>
          <Select value={estadoFiltro} onValueChange={setEstadoFiltro}>
            <SelectTrigger className="w-44" aria-label="Filtrar por estado">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ESTADO_TODOS}>Todos los estados</SelectItem>
              {estados.map((e) => (
                <SelectItem key={e} value={e}>
                  {ESTADO_LABEL[e] ?? e}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardHeader>
        <CardContent className="space-y-3">
          {query.isPending ? (
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-md" />
              ))}
            </div>
          ) : query.isError ? (
            <BloqueError
              titulo="No se pudieron cargar las ideas"
              mensaje={mensajeError(query.error)}
              onReintentar={() => void query.refetch()}
              cargando={query.isFetching}
            />
          ) : ideas.length === 0 ? (
            <EstadoVacioTexto
              texto="No hay ideas para este filtro. Propón algunas con la IA o crea la primera a mano."
              className="py-4"
            />
          ) : (
            <div className="space-y-3">
              {ideas.map((idea) => (
                <FilaIdea key={idea.id} idea={idea} marcas={marcas} redes={redes} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Panel izquierdo: proponer ideas con IA (o crear una a mano). */
function ProponerIdeas({ marcas }: { marcas: MarcaDisponible[] }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const [marca, setMarca] = React.useState(
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : "",
  );
  const [contexto, setContexto] = React.useState("");

  // Alta manual de una idea.
  const [tituloManual, setTituloManual] = React.useState("");

  const { generacion, ejecutando, iniciar, cancelar, cancelando } = useGeneracion(
    "evergreen-proponer",
  );

  const proponer = useMutation({
    mutationFn: () =>
      api.proponerEvergreen({ marca, contexto: contexto.trim() || undefined }),
    onSuccess: (data) => iniciar(data.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const crearManual = useMutation({
    mutationFn: () =>
      api.crearIdeaEvergreen({ marca, titulo: tituloManual.trim() }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_IDEAS });
      setTituloManual("");
      toast.success("Idea añadida al banco.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Al completar la propuesta IA: refrescar la lista.
  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      void queryClient.invalidateQueries({ queryKey: CLAVE_IDEAS });
      toast.success("Ideas propuestas. Revísalas en el banco.");
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudieron proponer ideas.");
    }
  }, [generacion, queryClient]);

  const proponiendo = proponer.isPending || ejecutando;
  const puedeProponer = marca !== "" && !proponiendo;

  return (
    <div className="space-y-6">
      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <MarcaIA />
            Proponer ideas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            La IA propone ideas de contenido evergreen (evergreen) para la marca. Añade un
            contexto opcional para enfocarla (temporada, programa, ángulo…).
          </p>

          <div className="space-y-1.5">
            <Label htmlFor="evergreen-marca">Marca</Label>
            <Select value={marca} onValueChange={setMarca}>
              <SelectTrigger id="evergreen-marca">
                <SelectValue placeholder="Elige una marca" />
              </SelectTrigger>
              <SelectContent>
                {marcas.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="evergreen-contexto">
              Contexto <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="evergreen-contexto"
              value={contexto}
              onChange={(e) => setContexto(e.target.value)}
              placeholder="Ej. enfoque en efemérides deportivas y datos curiosos para llenar huecos de parrilla…"
              rows={4}
            />
          </div>

          <Button onClick={() => proponer.mutate()} disabled={!puedeProponer} className="w-full">
            {proponiendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA />}
            {proponiendo ? "Proponiendo…" : "Proponer con IA"}
          </Button>

          {generacion && (ejecutando || generacion.estado === "error") && (
            <ProgresoGeneracion
              generacion={generacion}
              onCancelar={cancelar}
              cancelando={cancelando}
            />
          )}
        </CardContent>
      </Card>

      <Card className="h-fit">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Añadir idea a mano</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="evergreen-titulo-manual">Título de la idea</Label>
            <Input
              id="evergreen-titulo-manual"
              value={tituloManual}
              onChange={(e) => setTituloManual(e.target.value)}
              placeholder="Ej. 5 récords históricos de la liga"
              maxLength={140}
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => crearManual.mutate()}
            disabled={marca === "" || tituloManual.trim().length === 0 || crearManual.isPending}
          >
            {crearManual.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Añadir idea
          </Button>
          {marca === "" && (
            <p className="text-xs text-muted-foreground">
              Elige una marca arriba para añadir o proponer ideas.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Una idea con su estado y acciones (aprobar / descartar / generar / borrar). */
function FilaIdea({
  idea,
  marcas,
  redes,
}: {
  idea: IdeaEvergreen;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const nombreMarca =
    marcas.find((m) => m.id === idea.marca)?.nombre || idea.marca || "Sin marca";

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_IDEAS });

  const cambiarEstado = useMutation({
    mutationFn: (estado: EstadoIdeaEvergreen) =>
      api.actualizarIdeaEvergreen(idea.id, { estado }),
    onSuccess: (_d, estado) => {
      invalidar();
      toast.success(
        estado === "aprobada"
          ? "Idea aprobada."
          : estado === "descartada"
            ? "Idea descartada."
            : "Idea actualizada.",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarIdeaEvergreen(idea.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Idea borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Generación de la pieza evergreen (solo si la idea está aprobada).
  const { generacion, ejecutando, iniciar, cancelar, cancelando } = useGeneracion();

  const generar = useMutation({
    mutationFn: () =>
      api.generarIdeaEvergreen(idea.id, {
        redes: redes.length > 0 ? redes.map((r) => r.id) : undefined,
      }),
    onSuccess: (data) => iniciar(data.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      invalidar();
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
      toast.success("Pieza evergreen generada.", {
        action: {
          label: "Ver feed",
          onClick: () => navigate("/operacion/feed/lista"),
        },
      });
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudo generar la pieza.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generacion, navigate, queryClient]);

  const generando = generar.isPending || ejecutando;
  const aprobada = idea.estado === "aprobada";
  const descartada = idea.estado === "descartada";

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Borrar",
      icono: Trash2,
      destructivo: true,
      deshabilitado: borrar.isPending,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar la idea "${idea.titulo}"? Esta acción no se puede deshacer.`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          borrar.mutate();
      },
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      etiquetaAcciones={`Acciones de la idea "${idea.titulo}"`}
      kebab="hover"
      acciones={acciones}
      className={cn(
        "space-y-2 rounded-md border border-border p-3 pr-10",
        descartada && "opacity-60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-normal">
          {nombreMarca}
        </Badge>
        <Badge
          variant={aprobada ? "default" : "outline"}
          className="font-normal"
        >
          {ESTADO_LABEL[idea.estado] ?? idea.estado}
        </Badge>
        {idea.origen === "ia" && (
          <Badge variant="outline" className="font-normal">
            IA
          </Badge>
        )}
        {idea.contenido_id && (
          <Badge variant="outline" className="font-normal">
            Generada
          </Badge>
        )}
      </div>

      <p className="font-medium leading-snug">{idea.titulo}</p>
      {idea.descripcion && (
        <p className="line-clamp-3 text-sm text-muted-foreground">{idea.descripcion}</p>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1">
        {!aprobada && !descartada && (
          <Button
            size="sm"
            onClick={() => cambiarEstado.mutate("aprobada")}
            disabled={cambiarEstado.isPending}
          >
            <CheckCircle2 className="h-4 w-4" />
            Aprobar
          </Button>
        )}
        {!descartada && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate("descartada")}
            disabled={cambiarEstado.isPending}
          >
            <CircleSlash className="h-4 w-4" />
            Descartar
          </Button>
        )}
        {descartada && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate("propuesta")}
            disabled={cambiarEstado.isPending}
          >
            <RotateCcw className="h-4 w-4" />
            Reactivar
          </Button>
        )}
        {aprobada && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => generar.mutate()}
            disabled={generando}
          >
            {generando ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA />}
            {generando ? "Generando…" : "Generar contenido"}
          </Button>
        )}
      </div>

      {generacion && (ejecutando || generacion.estado === "error") && (
        <ProgresoGeneracion
          generacion={generacion}
          onCancelar={cancelar}
          cancelando={cancelando}
        />
      )}
    </FilaConAcciones>
  );
}
