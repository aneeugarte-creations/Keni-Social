import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  ClipboardList,
  Loader2,
  LayoutGrid,
  ListTodo,
  Plus,
  Rows3,
  Smartphone,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Textarea } from "@/components/ui/textarea";
import { Tooltip } from "@/components/ui/tooltip";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  CatalogosContenido,
  Contenido,
  ContenidoPlataforma,
  CuerpoCrearContenido,
  EstadoContenidoPlataforma,
  EtiquetaCatalogo,
} from "@/types";

const CLAVE = ["contenido"] as const;

const CABECERA = {
  titulo: "Tablero de contenido",
  descripcion:
    "La parrilla del día del equipo: lo importante del día, contenido evergreen y la cobertura de eventos previstos. Cada contenido lleva su estado y checklist por plataforma.",
};

const SIN_RESPONSABLE = "__sin_asignar__";
const TODOS = "__todos__";
/** Workspace "todas las marcas" (sin aislar). */
const WORKSPACE_TODAS = "__todas__";
/** localStorage: workspace (marca) activo + vista del tablero, para que sobrevivan al refresco. */
const CLAVE_WORKSPACE = "keni.tablero.workspace";
const CLAVE_VISTA = "keni.tablero.vista";

type Vista = "lista" | "grid" | "feed";

/** Secciones del tablero por flujo (el orden manda en pantalla). */
const SECCIONES: { flujo: Contenido["flujo"]; titulo: string }[] = [
  { flujo: "importante", titulo: "Importante del día" },
  { flujo: "evergreen", titulo: "Evergreen" },
  { flujo: "evento", titulo: "Eventos previstos" },
];

const PRIORIDAD_VARIANTE: Record<string, "error" | "aviso" | "secondary"> = {
  alta: "error",
  media: "aviso",
  baja: "secondary",
};

const ESTADO_PLAT_LABEL: Record<string, string> = {
  pendiente: "Pendiente",
  en_curso: "En curso",
  en_revision: "En revisión",
  aprobado: "Aprobado",
  programado: "Programado",
  publicado: "Publicado",
};

const ESTADO_PLAT_VARIANTE: Record<string, "secondary" | "aviso" | "ok"> = {
  pendiente: "aviso",
  en_curso: "aviso",
  en_revision: "secondary",
  aprobado: "secondary",
  programado: "secondary",
  publicado: "ok",
};

/** Etiqueta humana del eje de una etiqueta editorial (para agrupar el catálogo). */
const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  vertical: "Vertical",
  tipo: "Tipo",
};

/** Items del checklist por plataforma: campo (falta_X) ↔ etiqueta del check (hecho = !falta). */
const CHECKS: { campo: keyof ContenidoPlataforma; etiqueta: string }[] = [
  { campo: "falta_copy", etiqueta: "Copy" },
  { campo: "falta_imagen", etiqueta: "Imagen" },
  { campo: "falta_revision", etiqueta: "Revisión" },
  { campo: "falta_publicar", etiqueta: "Publicar" },
];

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFecha(iso: string): string {
  if (!iso) return "";
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short" });
}

function leerLS(clave: string, defecto: string): string {
  try {
    return localStorage.getItem(clave) ?? defecto;
  } catch {
    return defecto;
  }
}

export default function Tablero() {
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [gestionEtiquetas, setGestionEtiquetas] = React.useState(false);
  const [filtroResponsable, setFiltroResponsable] = React.useState(TODOS);
  const [filtroEtiqueta, setFiltroEtiqueta] = React.useState(TODOS);
  const [workspace, setWorkspace] = React.useState<string>(() =>
    leerLS(CLAVE_WORKSPACE, WORKSPACE_TODAS),
  );
  const [vista, setVista] = React.useState<Vista>(
    () => leerLS(CLAVE_VISTA, "lista") as Vista,
  );

  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_WORKSPACE, workspace);
    } catch {
      /* localStorage no disponible: no es crítico */
    }
  }, [workspace]);
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_VISTA, vista);
    } catch {
      /* idem */
    }
  }, [vista]);

  const contenidos = React.useMemo(() => query.data?.contenidos ?? [], [query.data]);
  const catalogos = query.data?.catalogos;
  const etiquetas = React.useMemo<EtiquetaCatalogo[]>(
    () => catalogos?.etiquetas ?? [],
    [catalogos],
  );
  const etiquetaPorId = React.useMemo(
    () => new Map(etiquetas.map((e) => [e.id, e])),
    [etiquetas],
  );

  // Etiquetas del selector de filtro: las del workspace activo + las globales (marca="").
  const etiquetasWorkspace = React.useMemo(
    () =>
      etiquetas.filter(
        (e) =>
          workspace === WORKSPACE_TODAS || e.marca === "" || e.marca === workspace,
      ),
    [etiquetas, workspace],
  );

  const visibles = React.useMemo(() => {
    let lista = contenidos;
    if (workspace !== WORKSPACE_TODAS) lista = lista.filter((c) => c.marca === workspace);
    if (filtroResponsable === SIN_RESPONSABLE)
      lista = lista.filter((c) => !c.responsable_id);
    else if (filtroResponsable !== TODOS)
      lista = lista.filter((c) => c.responsable_id === filtroResponsable);
    if (filtroEtiqueta !== TODOS)
      lista = lista.filter((c) => (c.etiquetas ?? []).includes(filtroEtiqueta));
    return lista;
  }, [contenidos, workspace, filtroResponsable, filtroEtiqueta]);

  const tareas = visibles.filter((c) => c.clase === "tarea");

  const renderItem = (c: Contenido) =>
    vista === "feed" ? (
      <TarjetaFeed key={c.id} contenido={c} etiquetaPorId={etiquetaPorId} />
    ) : (
      <TarjetaContenido
        key={c.id}
        contenido={c}
        catalogos={catalogos!}
        etiquetaPorId={etiquetaPorId}
        etiquetasWorkspace={etiquetasWorkspace}
        compacta={vista === "grid"}
      />
    );

  const contenedorClase =
    vista === "lista"
      ? "space-y-3"
      : "grid gap-3 sm:grid-cols-2 xl:grid-cols-3";

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => setGestionEtiquetas(true)}
              disabled={query.isPending}
            >
              <Tag className="h-4 w-4" />
              Etiquetas
            </Button>
            <Button onClick={() => setDialogoAbierto(true)} disabled={query.isPending}>
              <Plus className="h-4 w-4" />
              Nuevo contenido
            </Button>
          </div>
        }
      />

      {catalogos && (
        <BarraControles
          catalogos={catalogos}
          workspace={workspace}
          onWorkspace={setWorkspace}
          filtroResponsable={filtroResponsable}
          onResponsable={setFiltroResponsable}
          filtroEtiqueta={filtroEtiqueta}
          onEtiqueta={setFiltroEtiqueta}
          etiquetasWorkspace={etiquetasWorkspace}
          vista={vista}
          onVista={setVista}
        />
      )}

      {query.isPending ? (
        <div className="mt-4 space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-md" />
          ))}
        </div>
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el tablero"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : contenidos.length === 0 ? (
        <EstadoVacio
          icono={ListTodo}
          titulo="Tablero vacío"
          texto="Crea el primer contenido con el botón «Nuevo contenido»."
        />
      ) : visibles.length === 0 ? (
        <EstadoVacio
          icono={ListTodo}
          titulo="Nada que mostrar"
          texto="Ningún contenido coincide con el workspace o los filtros activos."
        />
      ) : (
        <div className="mt-4 space-y-8">
          {SECCIONES.map((s) => {
            const items = visibles.filter(
              (c) => c.clase === "contenido" && c.flujo === s.flujo,
            );
            return (
              <Seccion key={s.flujo} titulo={s.titulo} cantidad={items.length}>
                <div className={contenedorClase}>{items.map(renderItem)}</div>
              </Seccion>
            );
          })}
          {tareas.length > 0 && (
            <Seccion titulo="Tareas del equipo" cantidad={tareas.length}>
              <div className={contenedorClase}>{tareas.map(renderItem)}</div>
            </Seccion>
          )}
        </div>
      )}

      {catalogos && (
        <DialogoNuevo
          abierto={dialogoAbierto}
          onCerrar={() => setDialogoAbierto(false)}
          catalogos={catalogos}
          workspace={workspace}
          etiquetasWorkspace={etiquetasWorkspace}
        />
      )}
      <DialogoEtiquetas
        abierto={gestionEtiquetas}
        onCerrar={() => setGestionEtiquetas(false)}
        marcas={catalogos?.marcas ?? []}
      />
    </>
  );
}

function BarraControles({
  catalogos,
  workspace,
  onWorkspace,
  filtroResponsable,
  onResponsable,
  filtroEtiqueta,
  onEtiqueta,
  etiquetasWorkspace,
  vista,
  onVista,
}: {
  catalogos: CatalogosContenido;
  workspace: string;
  onWorkspace: (v: string) => void;
  filtroResponsable: string;
  onResponsable: (v: string) => void;
  filtroEtiqueta: string;
  onEtiqueta: (v: string) => void;
  etiquetasWorkspace: EtiquetaCatalogo[];
  vista: Vista;
  onVista: (v: Vista) => void;
}) {
  // Al cambiar de workspace, si la etiqueta del filtro deja de pertenecer, se resetea.
  React.useEffect(() => {
    if (
      filtroEtiqueta !== TODOS &&
      !etiquetasWorkspace.some((e) => e.id === filtroEtiqueta)
    ) {
      onEtiqueta(TODOS);
    }
  }, [etiquetasWorkspace, filtroEtiqueta, onEtiqueta]);

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-workspace" className="text-sm text-muted-foreground">
          Workspace
        </Label>
        <Select value={workspace} onValueChange={onWorkspace}>
          <SelectTrigger
            id="filtro-workspace"
            aria-label="Workspace (marca)"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={WORKSPACE_TODAS}>Todas las marcas</SelectItem>
            {catalogos.marcas.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {m.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-resp" className="text-sm text-muted-foreground">
          Responsable
        </Label>
        <Select value={filtroResponsable} onValueChange={onResponsable}>
          <SelectTrigger
            id="filtro-resp"
            aria-label="Filtrar por responsable"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos</SelectItem>
            <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
            {catalogos.usuarios.map((u) => (
              <SelectItem key={u.id} value={u.id}>
                {u.usuario}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <Label htmlFor="filtro-etiqueta" className="text-sm text-muted-foreground">
          Etiqueta
        </Label>
        <Select value={filtroEtiqueta} onValueChange={onEtiqueta}>
          <SelectTrigger
            id="filtro-etiqueta"
            aria-label="Filtrar por etiqueta"
            className="h-8 w-48"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todas</SelectItem>
            {etiquetasWorkspace.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {e.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Vista del tablero: lista / grid / feed-preview. */}
      <div
        className="ml-auto inline-flex items-center rounded-lg bg-muted p-0.5"
        role="group"
        aria-label="Vista del tablero"
      >
        {(
          [
            { v: "lista", icono: Rows3, etiqueta: "Lista" },
            { v: "grid", icono: LayoutGrid, etiqueta: "Cuadrícula" },
            { v: "feed", icono: Smartphone, etiqueta: "Feed" },
          ] as const
        ).map(({ v, icono: Icono, etiqueta }) => (
          <Tooltip key={v} label={etiqueta}>
            <button
              type="button"
              aria-label={etiqueta}
              aria-pressed={vista === v}
              onClick={() => onVista(v)}
              className={cn(
                "inline-flex h-7 w-9 items-center justify-center rounded-md transition-colors",
                vista === v
                  ? "bg-background text-foreground shadow"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Icono className="h-4 w-4" />
            </button>
          </Tooltip>
        ))}
      </div>
    </div>
  );
}

function Seccion({
  titulo,
  cantidad,
  children,
}: {
  titulo: string;
  cantidad: number;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h3 className="flex items-center gap-2 text-sm font-semibold tracking-tight text-muted-foreground">
        {titulo}
        <Badge variant="outline" className="font-normal">
          {cantidad}
        </Badge>
      </h3>
      {cantidad === 0 ? (
        <p className="text-sm text-muted-foreground/70">Nada por aquí todavía.</p>
      ) : (
        children
      )}
    </section>
  );
}

/** Chip de una etiqueta editorial (con color opcional). `onQuitar` lo vuelve removible. */
function ChipEtiqueta({
  etiqueta,
  onQuitar,
}: {
  etiqueta: EtiquetaCatalogo;
  onQuitar?: () => void;
}) {
  const estilo = etiqueta.color
    ? { borderColor: etiqueta.color, color: etiqueta.color }
    : undefined;
  return (
    <Badge variant="outline" className="gap-1 font-normal" style={estilo}>
      <Tag className="h-3 w-3" />
      {etiqueta.nombre}
      {onQuitar && (
        <button
          type="button"
          aria-label={`Quitar etiqueta ${etiqueta.nombre}`}
          onClick={onQuitar}
          className="-mr-0.5 ml-0.5 rounded-sm opacity-60 hover:opacity-100"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </Badge>
  );
}

function TarjetaContenido({
  contenido,
  catalogos,
  etiquetaPorId,
  etiquetasWorkspace,
  compacta = false,
}: {
  contenido: Contenido;
  catalogos: CatalogosContenido;
  etiquetaPorId: Map<string, EtiquetaCatalogo>;
  etiquetasWorkspace: EtiquetaCatalogo[];
  compacta?: boolean;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });

  const reasignar = useMutation({
    mutationFn: (responsable_id: string) =>
      api.actualizarContenido(contenido.id, { responsable_id }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const cambiarPrioridad = useMutation({
    mutationFn: (prioridad: Contenido["prioridad"]) =>
      api.actualizarContenido(contenido.id, { prioridad }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarContenido(contenido.id),
    onSuccess: () => {
      invalidar();
      toast.success("Contenido borrado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const agregarRed = useMutation({
    mutationFn: (red: string) => api.agregarPlataforma(contenido.id, red),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const asignarEtiqueta = useMutation({
    mutationFn: (etiquetaId: string) =>
      api.asignarEtiquetaContenido(contenido.id, etiquetaId),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const quitarEtiqueta = useMutation({
    mutationFn: (etiquetaId: string) =>
      api.quitarEtiquetaContenido(contenido.id, etiquetaId),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  const redesUsadas = new Set(contenido.plataformas.map((p) => p.red));
  const redesDisponibles = catalogos.redes.filter((r) => !redesUsadas.has(r.id));
  const asignadas = contenido.etiquetas ?? [];
  const etiquetasDisponibles = etiquetasWorkspace.filter((e) => !asignadas.includes(e.id));

  return (
    <Card>
      <CardContent className="space-y-3 p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 space-y-1.5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium leading-snug">{contenido.titulo}</span>
              {contenido.marca_nombre && (
                <Badge variant="outline" className="font-normal">
                  {contenido.marca_nombre}
                </Badge>
              )}
              {contenido.fecha_entrega && (
                <Badge
                  variant={contenido.vencido ? "error" : "outline"}
                  className="gap-1 font-normal"
                >
                  <CalendarClock className="h-3 w-3" />
                  {contenido.vencido ? "Venció " : "Entrega "}
                  {formatearFecha(contenido.fecha_entrega)}
                </Badge>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {contenido.autor_nombre && (
                <Autor nombre={contenido.autor_nombre} className="text-xs" />
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            <Select
              value={contenido.prioridad}
              onValueChange={(v) => cambiarPrioridad.mutate(v as Contenido["prioridad"])}
              disabled={cambiarPrioridad.isPending}
            >
              <SelectTrigger aria-label="Prioridad" className="h-7 w-24 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["alta", "media", "baja"] as const).map((p) => (
                  <SelectItem key={p} value={p}>
                    <Badge variant={PRIORIDAD_VARIANTE[p]} className="font-normal">
                      {p}
                    </Badge>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Tooltip label="Borrar">
              <Button
                variant="ghost"
                size="icon"
                aria-label="Borrar contenido"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => borrar.mutate()}
                disabled={borrar.isPending}
              >
                {borrar.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
              </Button>
            </Tooltip>
          </div>
        </div>

        {contenido.descripcion && (
          <p
            className={cn(
              "whitespace-pre-wrap text-sm text-muted-foreground",
              compacta && "line-clamp-2",
            )}
          >
            {contenido.descripcion}
          </p>
        )}

        {/* Etiquetas editoriales (chips removibles + selector para añadir). */}
        <div className="flex flex-wrap items-center gap-1.5">
          {asignadas.map((id) => {
            const et = etiquetaPorId.get(id);
            if (!et) return null;
            return (
              <ChipEtiqueta
                key={id}
                etiqueta={et}
                onQuitar={
                  quitarEtiqueta.isPending ? undefined : () => quitarEtiqueta.mutate(id)
                }
              />
            );
          })}
          {etiquetasDisponibles.length > 0 && (
            <Select value="" onValueChange={(id) => asignarEtiqueta.mutate(id)}>
              <SelectTrigger
                aria-label="Añadir etiqueta"
                className="h-6 w-auto gap-1 border-dashed px-2 text-xs text-muted-foreground"
              >
                <Tag className="h-3 w-3" />
                <SelectValue placeholder="Etiqueta" />
              </SelectTrigger>
              <SelectContent>
                {etiquetasDisponibles.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        {/* Filas por plataforma (clase=contenido). */}
        {contenido.clase === "contenido" && (
          <div className="space-y-2 rounded-md border border-border/60 p-2">
            {contenido.plataformas.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground/70">
                Sin plataformas. Añade una red abajo.
              </p>
            ) : (
              contenido.plataformas.map((p) => (
                <FilaPlataforma key={p.id} contenidoId={contenido.id} plataforma={p} />
              ))
            )}
            {redesDisponibles.length > 0 && (
              <Select value="" onValueChange={(red) => agregarRed.mutate(red)}>
                <SelectTrigger aria-label="Añadir plataforma" className="h-7 w-44 text-xs">
                  <SelectValue placeholder="+ Añadir plataforma" />
                </SelectTrigger>
                <SelectContent>
                  {redesDisponibles.map((r) => (
                    <SelectItem key={r.id} value={r.id}>
                      {r.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>
        )}

        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Responsable</span>
          <Select
            value={contenido.responsable_id || SIN_RESPONSABLE}
            onValueChange={(v) => reasignar.mutate(v === SIN_RESPONSABLE ? "" : v)}
            disabled={reasignar.isPending}
          >
            <SelectTrigger aria-label="Responsable del contenido" className="h-7 w-48 text-xs">
              <SelectValue placeholder="Sin asignar" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
              {catalogos.usuarios.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.usuario}
                </SelectItem>
              ))}
              {contenido.responsable_id &&
                !catalogos.usuarios.some((u) => u.id === contenido.responsable_id) && (
                  <SelectItem value={contenido.responsable_id}>
                    {contenido.responsable_nombre || "desconocido"}
                  </SelectItem>
                )}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}

/** Vista "feed-preview": cómo se verá la pieza en el perfil (mockup tipo tarjeta de red). */
function TarjetaFeed({
  contenido,
  etiquetaPorId,
}: {
  contenido: Contenido;
  etiquetaPorId: Map<string, EtiquetaCatalogo>;
}) {
  // El copy del feed: el de la primera plataforma con texto, si no la descripción/título.
  const copyPlat = contenido.plataformas.find((p) => p.copy)?.copy;
  const copy = copyPlat || contenido.descripcion || contenido.titulo;
  const asignadas = contenido.etiquetas ?? [];

  return (
    <Card className="overflow-hidden">
      <CardContent className="space-y-3 p-0">
        {/* Cabecera del "perfil" (marca + redes). */}
        <div className="flex items-center gap-2 px-4 pt-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground">
            {(contenido.marca_nombre || "?").slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium leading-tight">
              {contenido.marca_nombre || "Sin marca"}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {contenido.plataformas.map((p) => p.red_nombre).join(" · ") || "Sin plataformas"}
            </p>
          </div>
        </div>

        {/* Lienzo de la imagen (placeholder si no hay). */}
        <div className="aspect-square w-full bg-muted/50">
          {contenido.plataformas.find((p) => p.imagen)?.imagen ? (
            <img
              src={contenido.plataformas.find((p) => p.imagen)!.imagen}
              alt={contenido.titulo}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="flex h-full w-full items-center justify-center text-muted-foreground/50">
              <ClipboardList className="h-10 w-10" />
            </div>
          )}
        </div>

        {/* Copy + metadatos. */}
        <div className="space-y-2 px-4 pb-4">
          <p className="line-clamp-4 whitespace-pre-wrap text-sm">{copy}</p>
          <div className="flex flex-wrap items-center gap-1.5">
            {asignadas.map((id) => {
              const et = etiquetaPorId.get(id);
              return et ? <ChipEtiqueta key={id} etiqueta={et} /> : null;
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function FilaPlataforma({
  contenidoId,
  plataforma,
}: {
  contenidoId: string;
  plataforma: ContenidoPlataforma;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });

  const actualizar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.actualizarPlataforma>[2]) =>
      api.actualizarPlataforma(contenidoId, plataforma.id, cuerpo),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarPlataforma(contenidoId, plataforma.id),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-md bg-muted/30 px-2 py-1.5">
      <Badge variant="outline" className="w-20 justify-center font-normal">
        {plataforma.red_nombre}
      </Badge>
      <Select
        value={plataforma.estado}
        onValueChange={(estado) =>
          actualizar.mutate({ estado: estado as EstadoContenidoPlataforma })
        }
        disabled={actualizar.isPending}
      >
        <SelectTrigger
          aria-label={`Estado en ${plataforma.red_nombre}`}
          className="h-7 w-32 text-xs"
        >
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.keys(ESTADO_PLAT_LABEL).map((e) => (
            <SelectItem key={e} value={e}>
              {ESTADO_PLAT_LABEL[e]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Badge
        variant={ESTADO_PLAT_VARIANTE[plataforma.estado] ?? "secondary"}
        className="font-normal"
      >
        {ESTADO_PLAT_LABEL[plataforma.estado] ?? plataforma.estado}
      </Badge>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {CHECKS.map(({ campo, etiqueta }) => {
          const hecho = !plataforma[campo];
          return (
            <label
              key={campo}
              className="flex items-center gap-1.5 text-xs text-muted-foreground"
            >
              <Checkbox
                checked={hecho}
                onCheckedChange={(c) => actualizar.mutate({ [campo]: !c })}
                aria-label={etiqueta}
                disabled={actualizar.isPending}
              />
              <span className={cn(hecho && "line-through opacity-60")}>{etiqueta}</span>
            </label>
          );
        })}
      </div>
      <Tooltip label="Quitar plataforma">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Quitar ${plataforma.red_nombre}`}
          className="ml-auto h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </Tooltip>
    </div>
  );
}

function DialogoNuevo({
  abierto,
  onCerrar,
  catalogos,
  workspace,
  etiquetasWorkspace,
}: {
  abierto: boolean;
  onCerrar: () => void;
  catalogos: CatalogosContenido;
  workspace: string;
  etiquetasWorkspace: EtiquetaCatalogo[];
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [clase, setClase] = React.useState<"contenido" | "tarea">("contenido");
  const [flujo, setFlujo] = React.useState<Contenido["flujo"]>("importante");
  // Por defecto el workspace activo (si hay uno fijado), para que la pieza nazca en él.
  const [marca, setMarca] = React.useState(workspace === WORKSPACE_TODAS ? "" : workspace);
  const [prioridad, setPrioridad] = React.useState<Contenido["prioridad"]>("media");
  const [fechaEntrega, setFechaEntrega] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  const [descripcion, setDescripcion] = React.useState("");
  const [redes, setRedes] = React.useState<string[]>([]);
  const [etiquetas, setEtiquetas] = React.useState<string[]>([]);

  // Al abrir, preselecciona la marca del workspace activo.
  React.useEffect(() => {
    if (abierto) setMarca(workspace === WORKSPACE_TODAS ? "" : workspace);
  }, [abierto, workspace]);

  const reiniciar = () => {
    setTitulo("");
    setClase("contenido");
    setFlujo("importante");
    setMarca(workspace === WORKSPACE_TODAS ? "" : workspace);
    setPrioridad("media");
    setFechaEntrega("");
    setResponsable(SIN_RESPONSABLE);
    setDescripcion("");
    setRedes([]);
    setEtiquetas([]);
  };

  // Etiquetas elegibles: las globales + las de la marca seleccionada.
  const etiquetasElegibles = etiquetasWorkspace.filter(
    (e) => e.marca === "" || e.marca === marca,
  );

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearContenido = {
        titulo: titulo.trim(),
        clase,
        prioridad,
        fecha_entrega: fechaEntrega,
        descripcion: descripcion.trim(),
        responsable_id: responsable === SIN_RESPONSABLE ? "" : responsable,
      };
      if (clase === "contenido") {
        cuerpo.flujo = flujo;
        cuerpo.marca = marca;
        cuerpo.redes = redes;
        cuerpo.etiquetas = etiquetas;
      }
      return api.crearContenido(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE });
      toast.success("Contenido creado.");
      reiniciar();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const toggleRed = (id: string) =>
    setRedes((rs) => (rs.includes(id) ? rs.filter((r) => r !== id) : [...rs, id]));
  const toggleEtiqueta = (id: string) =>
    setEtiquetas((es) => (es.includes(id) ? es.filter((e) => e !== id) : [...es, id]));

  const puedeCrear = titulo.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ClipboardList className="h-4 w-4" />
            Nuevo contenido
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="nc-titulo">Título</Label>
            <Input
              id="nc-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Ej. Cobertura del partido de las 8"
              maxLength={300}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nc-clase">Tipo</Label>
              <Select value={clase} onValueChange={(v) => setClase(v as "contenido" | "tarea")}>
                <SelectTrigger id="nc-clase" aria-label="Tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="contenido">Contenido</SelectItem>
                  <SelectItem value="tarea">Tarea del equipo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-prioridad">Prioridad</Label>
              <Select
                value={prioridad}
                onValueChange={(v) => setPrioridad(v as Contenido["prioridad"])}
              >
                <SelectTrigger id="nc-prioridad" aria-label="Prioridad">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(["alta", "media", "baja"] as const).map((p) => (
                    <SelectItem key={p} value={p}>
                      {p}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {clase === "contenido" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="nc-flujo">Flujo</Label>
                <Select value={flujo} onValueChange={(v) => setFlujo(v as Contenido["flujo"])}>
                  <SelectTrigger id="nc-flujo" aria-label="Flujo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="importante">Importante del día</SelectItem>
                    <SelectItem value="evergreen">Evergreen</SelectItem>
                    <SelectItem value="evento">Evento previsto</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nc-marca">
                  Marca <span className="font-normal text-muted-foreground">(opcional)</span>
                </Label>
                <Select
                  value={marca || "__sin__"}
                  onValueChange={(v) => setMarca(v === "__sin__" ? "" : v)}
                >
                  <SelectTrigger id="nc-marca" aria-label="Marca">
                    <SelectValue placeholder="(sin marca)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__sin__">(sin marca)</SelectItem>
                    {catalogos.marcas.map((m) => (
                      <SelectItem key={m.id} value={m.id}>
                        {m.nombre}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="nc-entrega">
                Deadline <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Input
                id="nc-entrega"
                type="date"
                value={fechaEntrega}
                onChange={(e) => setFechaEntrega(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-resp">
                Responsable <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <Select value={responsable} onValueChange={setResponsable}>
                <SelectTrigger id="nc-resp" aria-label="Responsable">
                  <SelectValue placeholder="Sin asignar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
                  {catalogos.usuarios.map((u) => (
                    <SelectItem key={u.id} value={u.id}>
                      {u.usuario}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {clase === "contenido" && (
            <div className="space-y-1.5">
              <Label>
                Plataformas <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <div className="flex flex-wrap gap-2">
                {catalogos.redes.map((r) => (
                  <label key={r.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={redes.includes(r.id)}
                      onCheckedChange={() => toggleRed(r.id)}
                      aria-label={r.nombre}
                    />
                    {r.nombre}
                  </label>
                ))}
              </div>
            </div>
          )}

          {clase === "contenido" && etiquetasElegibles.length > 0 && (
            <div className="space-y-1.5">
              <Label>
                Etiquetas <span className="font-normal text-muted-foreground">(opcional)</span>
              </Label>
              <div className="flex flex-wrap gap-2">
                {etiquetasElegibles.map((e) => (
                  <label key={e.id} className="flex items-center gap-1.5 text-sm">
                    <Checkbox
                      checked={etiquetas.includes(e.id)}
                      onCheckedChange={() => toggleEtiqueta(e.id)}
                      aria-label={e.nombre}
                    />
                    {e.nombre}
                  </label>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="nc-desc">
              Notas / brief <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="nc-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              placeholder="Contexto, enlaces o qué hay que sacar."
              rows={4}
              maxLength={8000}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Gestión del CATÁLOGO de etiquetas (crear/editar/borrar). Lee de `/api/etiquetas`. */
function DialogoEtiquetas({
  abierto,
  onCerrar,
  marcas,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["etiquetas"],
    queryFn: ({ signal }) => api.etiquetas({}, signal),
    enabled: abierto,
  });
  const [nombre, setNombre] = React.useState("");
  const [clase, setClase] = React.useState("campania");
  const [marca, setMarca] = React.useState("");

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["etiquetas"] });
    // El catálogo de etiquetas del tablero viaja dentro de /api/contenido.
    void queryClient.invalidateQueries({ queryKey: CLAVE });
  };

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: clase as never, marca }),
    onSuccess: () => {
      invalidar();
      setNombre("");
      toast.success("Etiqueta creada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarEtiqueta(id),
    onSuccess: () => {
      invalidar();
      toast.success("Etiqueta borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetas = query.data?.etiquetas ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-4 w-4" />
            Etiquetas editoriales
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Alta de etiqueta. */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="et-nombre">Nombre</Label>
              <Input
                id="et-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Ej. Mundial 2026"
                maxLength={60}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-clase">Eje</Label>
              <Select value={clase} onValueChange={setClase}>
                <SelectTrigger id="et-clase" aria-label="Eje" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-marca">Marca</Label>
              <Select value={marca || "__global__"} onValueChange={(v) => setMarca(v === "__global__" ? "" : v)}>
                <SelectTrigger id="et-marca" aria-label="Marca" className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__global__">Global</SelectItem>
                  {marcas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={() => crear.mutate()}
              disabled={nombre.trim().length === 0 || crear.isPending}
            >
              {crear.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
          </div>

          {/* Listado del catálogo. */}
          {query.isPending ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : etiquetas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no hay etiquetas. Crea la primera arriba.
            </p>
          ) : (
            <div className="space-y-1.5">
              {etiquetas.map((e) => (
                <div
                  key={e.id}
                  className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 text-sm"
                >
                  <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="font-medium">{e.nombre}</span>
                  <Badge variant="secondary" className="font-normal">
                    {CLASE_ETIQUETA_LABEL[e.clase] ?? e.clase}
                  </Badge>
                  <Badge variant="outline" className="font-normal">
                    {e.marca_nombre || "Global"}
                  </Badge>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Borrar etiqueta ${e.nombre}`}
                    className="ml-auto h-7 w-7 text-muted-foreground hover:text-destructive"
                    onClick={() => borrar.mutate(e.id)}
                    disabled={borrar.isPending}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
