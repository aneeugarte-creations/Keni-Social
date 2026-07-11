/**
 * Taller EVERGREEN: banco de ideas de contenido evergreen (evergreen) por marca.
 *
 * Dos bloques:
 *   1. "Proponer ideas": elige marca + contexto opcional y lanza la IA (`/evergreen/proponer`),
 *      que propone ideas en segundo plano. Se sigue con `useGeneracion` (igual que el resto
 *      de generaciones de la consola) y al terminar se refresca la lista.
 *   2. Lista de ideas con filtro por estado y acciones: Aprobar / Descartar. Aprobar una idea
 *      dispara su investigación y se sigue en vivo con `ProgresoGeneracion`; al completarse la
 *      idea pasa a `generada` y baja al histórico.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CheckCircle2,
  CircleSlash,
  Leaf,
  Lightbulb,
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
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  EstadoIdeaEvergreen,
  IdeaEvergreen,
  MarcaDisponible,
  RedPieza,
} from "@/types";

const CLAVE_IDEAS = ["evergreen", "ideas"] as const;

/** Centinela "todos los estados" del filtro. */
const ESTADO_TODOS = "__todos__";

const ESTADO_LABEL: Record<string, string> = {
  propuesta: "Propuesta",
  aprobada: "Aprobada",
  generada: "Generada",
  descartada: "Descartada",
};

/** ¿La idea ya está en su terminal feliz? (estado nuevo `generada`; las anteriores al estado
 *  solo llevan `publicacion_id`). Sin acciones: vive en el cajón Histórico. */
function esGenerada(idea: IdeaEvergreen): boolean {
  return idea.estado === "generada" || Boolean(idea.publicacion_id);
}

/** Etiqueta del origen de la idea (badge). `manual` no lleva badge (alta rápida sin matiz). */
const ORIGEN_LABEL: Record<string, string> = {
  ia: "IA",
  idea: "Idea del equipo",
  interna: "Interno AMX",
};

export function TallerEvergreen({
  marcas,
}: {
  marcas: MarcaDisponible[];
  redes: RedPieza[];
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

      {/* Lista del banco como SECCIÓN sobre el lienzo (no una Card que envuelva otra Card):
          así cada ficha de idea flota igual que en la Lista de contenido y en Feedback. La
          cabecera (título + conteo + filtro) va como fila, con el mismo formato que el resto. */}
      <div className="space-y-3">
        <div className="flex flex-row flex-wrap items-center justify-between gap-3">
          <h2 className="flex min-w-0 items-center gap-2 text-base font-medium">
            <Leaf className="h-4 w-4 shrink-0" />
            <span className="truncate">Banco de ideas evergreen</span>
            <Badge variant="secondary" className="ml-1 shrink-0">
              {ideas.length}
            </Badge>
          </h2>
          <Select value={estadoFiltro} onValueChange={setEstadoFiltro}>
            <SelectTrigger className="w-44 shrink-0" aria-label="Filtrar por estado">
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
        </div>
        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-24 w-full rounded-lg" />
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
            texto="No hay ideas para este filtro."
            className="py-4"
          />
        ) : (
          <ListaIdeas
            ideas={ideas}
            marcas={marcas}
            separarHistorico={estadoFiltro === ESTADO_TODOS}
          />
        )}
      </div>
    </div>
  );
}

/** Panel izquierdo: proponer ideas con IA (o crear una a mano). */
function ProponerIdeas({ marcas }: { marcas: MarcaDisponible[] }) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  // La idea/contenido nuevo SIGUE la marca activa global: con una marca concreta activa se
  // usa esa y NO se muestra selector (ya existe el switch global). Solo en "Todas" se elige.
  const marcaFija = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : null;
  const [marcaElegida, setMarcaElegida] = React.useState("");
  const marca = marcaFija ?? marcaElegida;
  const [contexto, setContexto] = React.useState("");

  // Aportación manual al MISMO banco: un tipo, un título y una nota/contenido. Entra como idea
  // en estado "propuesta" (se aprueba y se genera igual que una idea de la IA).
  const [tipoManual, setTipoManual] = React.useState<"idea" | "interna">("idea");
  const [tituloManual, setTituloManual] = React.useState("");
  const [descManual, setDescManual] = React.useState("");

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
      api.crearIdeaEvergreen({
        marca,
        titulo: tituloManual.trim(),
        descripcion: descManual.trim() || undefined,
        origen: tipoManual,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_IDEAS });
      setTituloManual("");
      setDescManual("");
      toast.success(
        tipoManual === "interna" ? "Publicacion interno añadido al banco." : "Idea añadida al banco.",
      );
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
          {/* Selector de marca SOLO en la vista "Todas" (sin marca concreta activa): con una
              marca activa, la idea va a esa marca y no se pregunta de nuevo. */}
          {marcaFija ? null : (
            <div className="space-y-1.5">
              <Label htmlFor="evergreen-marca">Marca</Label>
              <Select value={marcaElegida} onValueChange={setMarcaElegida}>
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
          )}

          <div className="space-y-1.5">
            <Label htmlFor="evergreen-contexto">Contexto</Label>
            <Textarea
              id="evergreen-contexto"
              value={contexto}
              onChange={(e) => setContexto(e.target.value)}
              placeholder="Opcional: temporada, programa, ángulo…"
              rows={4}
            />
          </div>

          <Button
            variant="outline"
            onClick={() => proponer.mutate()}
            disabled={!puedeProponer}
            className="w-full"
          >
            {proponiendo ? <Spinner className="h-4 w-4" /> : <MarcaIA />}
            {proponiendo ? "Proponiendo…" : "Proponer"}
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
          <CardTitle className="text-base">Aportar a mano</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {/* Tipo de aportación: una idea suelta del equipo, o contenido interno del cliente
              (briefs, material de programa). Ambos entran al MISMO banco. Control segmentado
              (Tabs) — el patrón canónico de la consola: segmento activo blanco sobre track
              gris, sin negro. */}
          <Tabs
            value={tipoManual}
            onValueChange={(v) => setTipoManual(v as "idea" | "interna")}
          >
            <TabsList className="w-full">
              <TabsTrigger value="idea" className="flex-1 justify-center gap-1.5">
                <Lightbulb className="h-4 w-4" />
                Idea
              </TabsTrigger>
              <TabsTrigger value="interna" className="flex-1 justify-center gap-1.5">
                <Building2 className="h-4 w-4" />
                Interno AMX
              </TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="space-y-1.5">
            <Label htmlFor="evergreen-titulo-manual">Título</Label>
            <Input
              id="evergreen-titulo-manual"
              value={tituloManual}
              onChange={(e) => setTituloManual(e.target.value)}
              placeholder={
                tipoManual === "interna"
                  ? "Ej. Brief del especial de fin de año"
                  : "Ej. 5 récords históricos de la liga"
              }
              maxLength={140}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="evergreen-desc-manual">
              {tipoManual === "interna" ? "Publicacion interno" : "Nota"}
            </Label>
            <Textarea
              id="evergreen-desc-manual"
              value={descManual}
              onChange={(e) => setDescManual(e.target.value)}
              placeholder={
                tipoManual === "interna"
                  ? "Opcional: brief, material, transcripción…"
                  : "Opcional: tema, enfoque…"
              }
              rows={3}
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
              <Spinner className="h-4 w-4" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Añadir al banco
          </Button>
          {marca === "" && (
            <p className="text-xs text-muted-foreground">
              Elige una marca arriba para aportar o proponer ideas.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Lista del banco: las ACTIVAS arriba y, plegado, el cajón HISTÓRICO (generadas y
 *  descartadas — ya no piden acción; quedan consultables sin estorbar). Con un filtro de
 *  estado concreto se pinta plano (el filtro ya dice qué quieres ver). */
function ListaIdeas({
  ideas,
  marcas,
  separarHistorico,
}: {
  ideas: IdeaEvergreen[];
  marcas: MarcaDisponible[];
  separarHistorico: boolean;
}) {
  const historico = separarHistorico
    ? ideas.filter((i) => esGenerada(i) || i.estado === "descartada")
    : [];
  const activas = separarHistorico ? ideas.filter((i) => !historico.includes(i)) : ideas;
  return (
    <div className="space-y-3">
      {activas.map((idea) => (
        <FilaIdea key={idea.id} idea={idea} marcas={marcas} />
      ))}
      {activas.length === 0 && historico.length > 0 && (
        <EstadoVacioTexto
          texto="No hay ideas activas."
          className="py-4"
        />
      )}
      {historico.length > 0 && (
        <details className="rounded-xl border bg-card">
          <summary className="cursor-pointer select-none px-3 py-2 text-sm text-muted-foreground">
            Histórico ({historico.length})
          </summary>
          <div className="space-y-3 p-3 pt-1">
            {historico.map((idea) => (
              <FilaIdea key={idea.id} idea={idea} marcas={marcas} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

/** Una idea con su estado y acciones (aprobar / descartar / borrar). */
function FilaIdea({
  idea,
  marcas,
}: {
  idea: IdeaEvergreen;
  marcas: MarcaDisponible[];
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const nombreMarca =
    marcas.find((m) => m.id === idea.marca)?.nombre || idea.marca || "Sin marca";

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_IDEAS });

  // Investigación de la idea aprobada: aprobar la lanza y la seguimos en vivo.
  const { generacion, ejecutando, iniciar, cancelar, cancelando } = useGeneracion();

  const cambiarEstado = useMutation({
    mutationFn: (estado: EstadoIdeaEvergreen) =>
      api.actualizarIdeaEvergreen(idea.id, { estado }),
    onSuccess: (data, estado) => {
      invalidar();
      // Aprobar dispara la investigación: el back devuelve la generación en curso y la
      // seguimos en vivo (ProgresoGeneracion), igual que el resto de generaciones.
      if (estado === "aprobada" && data.generacion) iniciar(data.generacion);
      toast.success(
        estado === "aprobada"
          ? data.generacion
            ? "Investigando la idea…"
            : "Idea aprobada."
          : estado === "descartada"
            ? "Idea descartada."
            : "Idea actualizada.",
      );
    },
    onError: (e) => {
      invalidar();
      toast.error(mensajeError(e));
    },
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarIdeaEvergreen(idea.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Idea borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const terminalRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      invalidar();
      void queryClient.invalidateQueries({ queryKey: ["piezas"] });
      toast.success("Pieza evergreen generada.", {
        action: {
          label: "Ver feed",
          onClick: () => navigate("/operacion/feed/lista"),
        },
      });
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      // La investigación falló: la idea sigue `aprobada` (reintentable). Refrescamos para
      // que la acción Aprobar reaparezca; el detalle del fallo va en el toast.
      invalidar();
      toast.error(generacion.error || "No se pudo generar la pieza.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generacion, navigate, queryClient]);

  const generada = esGenerada(idea);
  const aprobada = idea.estado === "aprobada" && !generada;
  const descartada = idea.estado === "descartada";
  // Aprobar dispara la investigación. Disponible mientras la idea no esté generada ni
  // descartada y no haya una investigación en curso: así reaparece para REINTENTAR si la
  // generación terminó en error (la idea sigue `aprobada`).
  const puedeAprobar = !descartada && !generada && !ejecutando;

  const acciones: EntradaMenuContextual[] = [
    ...(puedeAprobar
      ? [
          {
            etiqueta: "Aprobar",
            icono: CheckCircle2,
            deshabilitado: cambiarEstado.isPending,
            onClick: () => cambiarEstado.mutate("aprobada"),
          },
        ]
      : []),
    // Descartar: visible si aún no está descartada
    ...(!descartada
      ? [
          {
            etiqueta: "Descartar",
            icono: CircleSlash,
            deshabilitado: cambiarEstado.isPending,
            onClick: () => cambiarEstado.mutate("descartada"),
          },
        ]
      : []),
    // Reactivar: visible solo si descartada
    ...(descartada
      ? [
          {
            etiqueta: "Reactivar",
            icono: RotateCcw,
            deshabilitado: cambiarEstado.isPending,
            onClick: () => cambiarEstado.mutate("propuesta"),
          },
        ]
      : []),
    // Borrar: siempre visible
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
      kebab="nunca"
      realce
      acciones={acciones}
      className={cn(
        "space-y-2 rounded-xl border bg-card p-4 pr-10 text-card-foreground",
        descartada && "opacity-60",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="secondary" className="font-normal">
          {nombreMarca}
        </Badge>
        <Badge
          variant={aprobada ? "secondary" : "outline"}
          className="font-normal"
        >
          {ESTADO_LABEL[idea.estado] ?? idea.estado}
        </Badge>
        {ORIGEN_LABEL[idea.origen] && (
          <Badge variant="outline" className="font-normal">
            {ORIGEN_LABEL[idea.origen]}
          </Badge>
        )}
        {idea.publicacion_id && idea.estado !== "generada" && (
          <Badge variant="outline" className="font-normal">
            Generada
          </Badge>
        )}
      </div>

      <p className="font-medium leading-snug">{idea.titulo}</p>
      {idea.descripcion && (
        <p className="line-clamp-3 text-sm text-muted-foreground">{idea.descripcion}</p>
      )}

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
