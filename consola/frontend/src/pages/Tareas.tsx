import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  ChevronDown,
  ClipboardList,
  Eye,
  Loader2,
  ListTodo,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Autor } from "@/components/comunes/Autor";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { PageHeader } from "@/components/layout/PageHeader";
import { AutoTextarea } from "@/components/ui/auto-textarea";
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
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError } from "@/lib/api";
import { limiteRed } from "@/pages/publicaciones/meta";
import { cn } from "@/lib/utils";
import type {
  CatalogosContenido,
  Contenido,
  ContenidoPlataforma,
  CuerpoCrearContenido,
  EstadoContenidoPlataforma,
  ModoAsistenteContenido,
  PiezaGenerada,
  VariableCopy,
} from "@/types";

const CLAVE = ["contenido"] as const;

const CABECERA = {
  titulo: "Tablero de contenido",
  descripcion:
    "La parrilla del día del equipo: lo importante del día, contenido evergreen y la cobertura de eventos previstos. Cada contenido lleva su estado y checklist por plataforma.",
};

const SIN_RESPONSABLE = "__sin_asignar__";
const TODOS = "__todos__";

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

export default function Tablero() {
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [filtroResponsable, setFiltroResponsable] = React.useState(TODOS);

  const contenidos = React.useMemo(() => query.data?.contenidos ?? [], [query.data]);
  const catalogos = query.data?.catalogos;

  const visibles = React.useMemo(() => {
    if (filtroResponsable === TODOS) return contenidos;
    if (filtroResponsable === SIN_RESPONSABLE)
      return contenidos.filter((c) => !c.responsable_id);
    return contenidos.filter((c) => c.responsable_id === filtroResponsable);
  }, [contenidos, filtroResponsable]);

  const tareas = visibles.filter((c) => c.clase === "tarea");

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <Button onClick={() => setDialogoAbierto(true)} disabled={query.isPending}>
            <Plus className="h-4 w-4" />
            Nuevo contenido
          </Button>
        }
      />

      {catalogos && (
        <FiltroResponsable
          usuarios={catalogos.usuarios}
          valor={filtroResponsable}
          onCambio={setFiltroResponsable}
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
      ) : (
        <div className="mt-4 space-y-8">
          {SECCIONES.map((s) => {
            const items = visibles.filter(
              (c) => c.clase === "contenido" && c.flujo === s.flujo,
            );
            return (
              <Seccion key={s.flujo} titulo={s.titulo} cantidad={items.length}>
                {items.map((c) => (
                  <TarjetaContenido key={c.id} contenido={c} catalogos={catalogos!} />
                ))}
              </Seccion>
            );
          })}
          {tareas.length > 0 && (
            <Seccion titulo="Tareas del equipo" cantidad={tareas.length}>
              {tareas.map((c) => (
                <TarjetaContenido key={c.id} contenido={c} catalogos={catalogos!} />
              ))}
            </Seccion>
          )}
        </div>
      )}

      {catalogos && (
        <DialogoNuevo
          abierto={dialogoAbierto}
          onCerrar={() => setDialogoAbierto(false)}
          catalogos={catalogos}
        />
      )}
    </>
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
        <div className="space-y-3">{children}</div>
      )}
    </section>
  );
}

function FiltroResponsable({
  usuarios,
  valor,
  onCambio,
}: {
  usuarios: CatalogosContenido["usuarios"];
  valor: string;
  onCambio: (v: string) => void;
}) {
  return (
    <div className="mt-2 flex items-center gap-2">
      <Label htmlFor="filtro-resp" className="text-sm text-muted-foreground">
        Responsable
      </Label>
      <Select value={valor} onValueChange={onCambio}>
        <SelectTrigger id="filtro-resp" aria-label="Filtrar por responsable" className="h-8 w-56">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={TODOS}>Todos</SelectItem>
          <SelectItem value={SIN_RESPONSABLE}>Sin asignar</SelectItem>
          {usuarios.map((u) => (
            <SelectItem key={u.id} value={u.id}>
              {u.usuario}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function TarjetaContenido({
  contenido,
  catalogos,
}: {
  contenido: Contenido;
  catalogos: CatalogosContenido;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });
  const [asistenteAbierto, setAsistenteAbierto] = React.useState(false);

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

  const redesUsadas = new Set(contenido.plataformas.map((p) => p.red));
  const redesDisponibles = catalogos.redes.filter((r) => !redesUsadas.has(r.id));

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
            {contenido.clase === "contenido" && (
              <Tooltip label="Asistente IA">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Asistente IA"
                  className="text-muted-foreground hover:text-primary"
                  onClick={() => setAsistenteAbierto(true)}
                >
                  <Sparkles className="h-4 w-4" />
                </Button>
              </Tooltip>
            )}
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
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">
            {contenido.descripcion}
          </p>
        )}

        {/* Filas por plataforma (clase=contenido). */}
        {contenido.clase === "contenido" && (
          <div className="space-y-2 rounded-md border border-border/60 p-2">
            {contenido.plataformas.length === 0 ? (
              <p className="px-1 text-xs text-muted-foreground/70">
                Sin plataformas. Añade una red abajo.
              </p>
            ) : (
              contenido.plataformas.map((p) => (
                <FilaPlataforma
                  key={p.id}
                  contenidoId={contenido.id}
                  plataforma={p}
                  variables={catalogos.variables}
                />
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
      {contenido.clase === "contenido" && (
        <DialogoAsistente
          abierto={asistenteAbierto}
          onCerrar={() => setAsistenteAbierto(false)}
          contenido={contenido}
          onAplicado={invalidar}
        />
      )}
    </Card>
  );
}

function FilaPlataforma({
  contenidoId,
  plataforma,
  variables,
}: {
  contenidoId: string;
  plataforma: ContenidoPlataforma;
  variables: VariableCopy[];
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });
  const [editorAbierto, setEditorAbierto] = React.useState(false);

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
    <div className="space-y-1.5 rounded-md bg-muted/30 px-2 py-1.5">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
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
      <Button
        variant="ghost"
        size="sm"
        className="ml-auto h-7 gap-1 px-2 text-xs text-muted-foreground"
        onClick={() => setEditorAbierto((v) => !v)}
        aria-expanded={editorAbierto}
      >
        <ChevronDown
          className={cn("h-3.5 w-3.5 transition-transform", editorAbierto && "rotate-180")}
        />
        Copy
        {plataforma.copy ? (
          <Badge variant="ok" className="h-4 px-1 font-normal">
            <Check className="h-3 w-3" />
          </Badge>
        ) : null}
      </Button>
      <Tooltip label="Quitar plataforma">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Quitar ${plataforma.red_nombre}`}
          className="h-7 w-7 text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </Tooltip>
    </div>
      {editorAbierto && (
        <EditorCopy
          contenidoId={contenidoId}
          plataforma={plataforma}
          variables={variables}
          guardando={actualizar.isPending}
          onGuardar={(copy) => actualizar.mutate({ copy })}
        />
      )}
    </div>
  );
}

/**
 * Editor del copy de UNA fila por plataforma: variantes por red con contador/límite de
 * caracteres, inserción de variables `{...}` y previa con las variables ya sustituidas
 * (vía `POST /api/contenido/{id}/preview`). Guarda en `contenido_plataforma.copy`.
 */
function EditorCopy({
  contenidoId,
  plataforma,
  variables,
  guardando,
  onGuardar,
}: {
  contenidoId: string;
  plataforma: ContenidoPlataforma;
  variables: VariableCopy[];
  guardando: boolean;
  onGuardar: (copy: string) => void;
}) {
  const [texto, setTexto] = React.useState(plataforma.copy);
  const [verPrevia, setVerPrevia] = React.useState(false);
  const areaRef = React.useRef<HTMLTextAreaElement>(null);
  const limite = limiteRed(plataforma.red);
  const sucio = texto !== plataforma.copy;

  // El copy del servidor cambió (p.ej. lo rellenó el asistente IA): si NO hay edición
  // local sin guardar respecto al valor anterior del servidor, adoptamos el nuevo. Así no
  // pisamos lo que el usuario está escribiendo, pero sí reflejamos un relleno externo.
  const servidorRef = React.useRef(plataforma.copy);
  React.useEffect(() => {
    if (plataforma.copy !== servidorRef.current) {
      setTexto((prev) => (prev === servidorRef.current ? plataforma.copy : prev));
      servidorRef.current = plataforma.copy;
    }
  }, [plataforma.copy]);

  // Previa: expande las variables del texto contra el contexto del contenido. Debounced.
  const previa = useQuery({
    queryKey: ["contenido-preview", contenidoId, texto],
    queryFn: ({ signal }) => api.previewContenido(contenidoId, texto, signal),
    enabled: verPrevia && texto.includes("{"),
    staleTime: 30_000,
  });

  const insertarVariable = (ejemplo: string) => {
    const area = areaRef.current;
    if (!area) {
      setTexto((t) => t + ejemplo);
      return;
    }
    const inicio = area.selectionStart ?? texto.length;
    const fin = area.selectionEnd ?? texto.length;
    setTexto(texto.slice(0, inicio) + ejemplo + texto.slice(fin));
    requestAnimationFrame(() => {
      area.focus();
      const pos = inicio + ejemplo.length;
      area.setSelectionRange(pos, pos);
    });
  };

  const previaTexto = previa.data?.preview ?? texto;

  return (
    <div className="space-y-2 rounded-md border border-border/60 bg-background/60 p-2">
      <div className="flex items-center justify-between">
        <Label htmlFor={`copy-${plataforma.id}`} className="text-xs text-muted-foreground">
          Copy para {plataforma.red_nombre}
        </Label>
        <ContadorCaracteres caracteres={texto.length} limite={limite} />
      </div>
      <AutoTextarea
        ref={areaRef}
        id={`copy-${plataforma.id}`}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        placeholder={`Escribe el copy para ${plataforma.red_nombre}. Usa {marca}, {fecha}…`}
        maxHeight={320}
        className="min-h-[5rem] font-mono text-sm"
      />
      {variables.length > 0 && (
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-xs text-muted-foreground">Insertar:</span>
          {variables.map((v) => (
            <Tooltip key={v.clave} label={v.etiqueta}>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 px-1.5 font-mono text-[11px]"
                onClick={() => insertarVariable(v.ejemplo)}
              >
                {v.ejemplo}
              </Button>
            </Tooltip>
          ))}
        </div>
      )}
      {verPrevia && (
        <div className="rounded-md bg-muted/50 p-2">
          <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Previa (variables sustituidas)
          </p>
          <p className="whitespace-pre-wrap text-sm">
            {previaTexto || <span className="text-muted-foreground/60">Sin copy.</span>}
          </p>
        </div>
      )}
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          className="h-7"
          onClick={() => onGuardar(texto)}
          disabled={!sucio || guardando}
        >
          {guardando ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
          Guardar copy
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1"
          onClick={() => setVerPrevia((v) => !v)}
        >
          <Eye className="h-3.5 w-3.5" />
          {verPrevia ? "Ocultar previa" : "Previa"}
        </Button>
      </div>
    </div>
  );
}

function DialogoNuevo({
  abierto,
  onCerrar,
  catalogos,
}: {
  abierto: boolean;
  onCerrar: () => void;
  catalogos: CatalogosContenido;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [clase, setClase] = React.useState<"contenido" | "tarea">("contenido");
  const [flujo, setFlujo] = React.useState<Contenido["flujo"]>("importante");
  const [marca, setMarca] = React.useState("");
  const [prioridad, setPrioridad] = React.useState<Contenido["prioridad"]>("media");
  const [fechaEntrega, setFechaEntrega] = React.useState("");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  const [descripcion, setDescripcion] = React.useState("");
  const [redes, setRedes] = React.useState<string[]>([]);

  const reiniciar = () => {
    setTitulo("");
    setClase("contenido");
    setFlujo("importante");
    setMarca("");
    setPrioridad("media");
    setFechaEntrega("");
    setResponsable(SIN_RESPONSABLE);
    setDescripcion("");
    setRedes([]);
  };

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

/** Modos del asistente IA con su etiqueta y descripción para la UI. */
const MODOS_ASISTENTE: { modo: ModoAsistenteContenido; etiqueta: string; ayuda: string }[] = [
  { modo: "generar", etiqueta: "Generar copy", ayuda: "Una variante por red, lista para revisar." },
  { modo: "variantes", etiqueta: "3 variantes", ayuda: "Tres enfoques alternativos para elegir." },
  { modo: "resumir", etiqueta: "Resumir", ayuda: "Condensa el brief a lo esencial por red." },
];

/**
 * Asistente IA del tablero sobre un `contenido`: genera / resume / 3 variantes
 * reutilizando las skills de copy (voz de marca + tropicalización MX + verificación).
 * Lanza un trabajo en segundo plano, lo sigue token a token y, al completarse, ofrece
 * APLICAR cada pieza generada al `copy` de su fila `contenido_plataforma`.
 */
function DialogoAsistente({
  abierto,
  onCerrar,
  contenido,
  onAplicado,
}: {
  abierto: boolean;
  onCerrar: () => void;
  contenido: Contenido;
  onAplicado: () => void;
}) {
  const [modo, setModo] = React.useState<ModoAsistenteContenido>("generar");
  const seguimiento = useGeneracion();
  const { generacion, ejecutando, iniciar, limpiar } = seguimiento;

  const lanzar = useMutation({
    mutationFn: () => api.asistenteContenido(contenido.id, { modo }),
    onSuccess: (r) => iniciar(r.generacion),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Filas por red del contenido: mapa red -> fila, para aplicar la pieza correcta.
  const filaPorRed = React.useMemo(() => {
    const m = new Map<string, ContenidoPlataforma>();
    for (const p of contenido.plataformas) m.set(p.red, p);
    return m;
  }, [contenido.plataformas]);

  const aplicar = useMutation({
    mutationFn: ({ plataformaId, copy }: { plataformaId: string; copy: string }) =>
      api.actualizarPlataforma(contenido.id, plataformaId, { copy }),
    onSuccess: () => {
      onAplicado();
      toast.success("Copy aplicado a la plataforma.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const piezas: PiezaGenerada[] = generacion?.resultado?.piezas ?? [];
  const errorGen = generacion?.estado === "error";

  const cerrar = () => {
    limpiar();
    onCerrar();
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && cerrar()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Asistente IA · {contenido.titulo}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            {MODOS_ASISTENTE.map((m) => (
              <button
                key={m.modo}
                type="button"
                onClick={() => setModo(m.modo)}
                disabled={ejecutando || lanzar.isPending}
                className={cn(
                  "rounded-md border p-2 text-left text-xs transition",
                  modo === m.modo ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
                )}
              >
                <span className="block font-medium">{m.etiqueta}</span>
                <span className="text-muted-foreground">{m.ayuda}</span>
              </button>
            ))}
          </div>

          <Button
            onClick={() => lanzar.mutate()}
            disabled={ejecutando || lanzar.isPending}
            className="w-full"
          >
            {ejecutando || lanzar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {ejecutando ? "Generando…" : "Generar con IA"}
          </Button>

          {errorGen && (
            <p className="text-sm text-red-600 dark:text-red-400">
              {generacion?.error || "No se pudo generar. Inténtalo de nuevo."}
            </p>
          )}

          {ejecutando && generacion?.salida && (
            <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap rounded-md bg-muted/50 p-2 text-xs">
              {generacion.salida}
            </pre>
          )}

          {generacion?.resultado?.verdicto && (
            <p className="text-xs text-muted-foreground">
              Auto-verificación: {generacion.resultado.verdicto}
            </p>
          )}

          {piezas.length > 0 && (
            <div className="space-y-3">
              <p className="text-sm font-medium">Copy generado por red</p>
              {piezas.map((pieza) => {
                const fila = filaPorRed.get(pieza.red);
                const limite = limiteRed(pieza.red);
                return (
                  <div key={pieza.red} className="space-y-1.5 rounded-md border p-2">
                    <div className="flex items-center justify-between">
                      <Badge variant="outline" className="font-normal">
                        {fila?.red_nombre ?? pieza.red}
                      </Badge>
                      <ContadorCaracteres caracteres={pieza.contenido.length} limite={limite} />
                    </div>
                    <p className="whitespace-pre-wrap text-sm">{pieza.contenido}</p>
                    {fila ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-7"
                        onClick={() =>
                          aplicar.mutate({ plataformaId: fila.id, copy: pieza.contenido })
                        }
                        disabled={aplicar.isPending}
                      >
                        <Check className="h-3.5 w-3.5" />
                        Aplicar a {fila.red_nombre}
                      </Button>
                    ) : (
                      <p className="text-xs text-muted-foreground/70">
                        Añade {pieza.red} al contenido para aplicar este copy.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={cerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
