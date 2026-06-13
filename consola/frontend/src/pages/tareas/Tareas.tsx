import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  ChevronDown,
  ChevronRight,
  Hand,
  ListChecks,
  Play,
  Plus,
  RotateCcw,
  Trash2,
  Trophy,
  UserCheck,
  UserPlus,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearDia, formatearFecha, hoyCDMX, tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido, EventoRota } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Lente sobre la MISMA lista: el panorama (agenda de equipo), el pool a coger, o lo mío. */
type Lente = "panorama" | "libres" | "mias";
const LENTES: { id: Lente; etiqueta: string }[] = [
  { id: "panorama", etiqueta: "Panorama" },
  { id: "libres", etiqueta: "Por cubrir" },
  { id: "mias", etiqueta: "Mis tareas" },
];

/** Avance de estado de una tarea ya cogida (pendiente → en_curso → hecha). */
const SIGUIENTE: Record<string, { estado: string; etiqueta: string; icono: typeof Play }> = {
  pendiente: { estado: "en_curso", etiqueta: "Empezar", icono: Play },
  en_curso: { estado: "hecha", etiqueta: "Marcar hecha", icono: Check },
};

const PRIORIDAD_CLASE: Record<string, string> = {
  alta: "border-red-500/40 text-red-700 dark:text-red-300",
  media: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  baja: "border-border text-muted-foreground",
};

/** Diálogo "Asignar a…" compartido (manager elige a quién encarga). */
function DialogoAsignar({
  titulo,
  abierto,
  onOpenChange,
  usuarios,
  responsableActual,
  onElegir,
  enviando,
}: {
  titulo: string;
  abierto: boolean;
  onOpenChange: (v: boolean) => void;
  usuarios: { id: string; usuario: string }[];
  responsableActual: string;
  onElegir: (personaId: string) => void;
  enviando: boolean;
}) {
  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Asignar "{titulo}"</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Elige a quién se la encargas; se le avisa en la app.
        </p>
        <div className="max-h-72 space-y-1 overflow-y-auto py-1">
          {usuarios.length === 0 && (
            <p className="px-1 text-sm text-muted-foreground">No hay compañeros para asignar.</p>
          )}
          {usuarios.map((u) => {
            const yaEs = u.id === responsableActual;
            return (
              <button
                key={u.id}
                type="button"
                disabled={enviando || yaEs}
                onClick={() => onElegir(u.id)}
                className={cn(
                  "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm disabled:opacity-100",
                  yaEs
                    ? "border-primary/50 bg-primary/5 text-primary"
                    : "border-border hover:border-foreground/30 hover:bg-accent",
                )}
              >
                <span className="truncate">{u.usuario}</span>
                {yaEs && <span className="ml-2 shrink-0 text-xs">la lleva ahora</span>}
              </button>
            );
          })}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Un EVENTO «Por cubrir»: un partido/transmisión que nadie ha cogido todavía. No tiene tarea
 * aún; al coger (o que Elias asigne) se crea su registro de cobertura vía `cubrirEvento`.
 */
function TarjetaEventoLibre({
  evento,
  catalogos,
}: {
  evento: EventoRota;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const usuarios = catalogos?.usuarios ?? [];

  const cubrir = useMutation({
    mutationFn: (responsableId?: string) => api.cubrirEvento(evento.id, responsableId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre = res?.contenido?.responsable_nombre || "ti";
      toast.success(`"${evento.titulo}" la cubre ${nombre}.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  return (
    <div className="rounded-lg border border-dashed border-border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <Trophy className="h-4 w-4 shrink-0 text-muted-foreground" />
        <span className="font-medium">{evento.titulo}</span>
        <Badge variant="outline" className="border-dashed text-muted-foreground">
          Por cubrir
        </Badge>
        {evento.cambiado && (
          <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-300">
            Cambió de hora
          </Badge>
        )}
        {evento.prioridad && (
          <Badge variant="outline" className={cn("font-normal", PRIORIDAD_CLASE[evento.prioridad])}>
            {evento.prioridad}
          </Badge>
        )}
        {evento.fecha && (
          <span className="inline-flex items-center gap-1 text-sm text-muted-foreground">
            <CalendarClock className="h-3.5 w-3.5" />
            {formatearFecha(evento.fecha)}
            {evento.hora ? ` · ${evento.hora}` : ""}
          </span>
        )}
      </div>
      {evento.contenido && (
        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{evento.contenido}</p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8"
          onClick={() => cubrir.mutate(undefined)}
          disabled={cubrir.isPending}
          title="La cubro yo"
          aria-label="La cubro yo"
        >
          <Hand className="h-3.5 w-3.5" />
        </Button>
        {esManager && (
          <Button variant="outline" size="sm" onClick={() => setAsignarAbierto(true)}>
            <UserPlus className="mr-1 h-3.5 w-3.5" />
            Asignar
          </Button>
        )}
      </div>

      <DialogoAsignar
        titulo={evento.titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual=""
        onElegir={(id) => cubrir.mutate(id)}
        enviando={cubrir.isPending}
      />
    </div>
  );
}

/** Una TAREA ya con dueño (cobertura cogida o encargo del equipo): estado, responsable, acciones. */
function TarjetaTarea({
  tarea,
  catalogos,
}: {
  tarea: Contenido;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const libre = !tarea.responsable_id;
  const esMia = Boolean(usuario && tarea.responsable_id === usuario.id);
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const usuarios = catalogos?.usuarios ?? [];

  const invalidar = () => queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
  const conError = (e: unknown) => {
    void invalidar();
    toast.error(mensajeError(e));
  };

  const coger = useMutation({
    mutationFn: () => api.cogerContenido(tarea.id),
    onSuccess: () => {
      void invalidar();
      toast.success(`"${tarea.titulo}" es tuya: el equipo ya lo ve.`);
    },
    onError: conError,
  });
  const soltar = useMutation({
    mutationFn: () => api.soltarContenido(tarea.id),
    onSuccess: () => {
      void invalidar();
      toast.success(`"${tarea.titulo}" vuelve a estar libre.`);
    },
    onError: conError,
  });
  const asignar = useMutation({
    mutationFn: (personaId: string) => api.asignarContenido(tarea.id, personaId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void invalidar();
      const nombre = res?.contenido?.responsable_nombre || "esa persona";
      toast.success(`"${tarea.titulo}" asignada a ${nombre}: se le avisa en la app.`);
    },
    onError: conError,
  });
  const cambiarEstado = useMutation({
    mutationFn: (estado: string) => api.actualizarContenido(tarea.id, { estado }),
    onSuccess: () => void invalidar(),
    onError: conError,
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarContenido(tarea.id),
    onSuccess: () => {
      setConfirmarBorrado(false);
      void invalidar();
      toast.success("Tarea borrada.");
    },
    onError: conError,
  });

  const avance = SIGUIENTE[tarea.estado];
  const esCobertura = Boolean(tarea.evento_id);

  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        {esCobertura && <Trophy className="h-4 w-4 shrink-0 text-muted-foreground" />}
        <span className="font-medium">{tarea.titulo}</span>
        {libre ? (
          <Badge variant="outline" className="border-dashed text-muted-foreground">
            Libre
          </Badge>
        ) : (
          <Badge
            variant="outline"
            className={cn(
              "gap-1 font-normal",
              esMia
                ? "border-primary/50 text-primary"
                : "border-violet-500/40 text-violet-700 dark:text-violet-300",
            )}
          >
            <UserCheck className="h-3 w-3" />
            {esMia ? "Tuya" : tarea.responsable_nombre}
          </Badge>
        )}
        {tarea.estado === "en_curso" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            En curso
          </Badge>
        )}
        {tarea.estado === "hecha" && (
          <Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300">
            Hecha
          </Badge>
        )}
        {tarea.prioridad && (
          <Badge variant="outline" className={cn("font-normal", PRIORIDAD_CLASE[tarea.prioridad])}>
            {tarea.prioridad}
          </Badge>
        )}
        {tarea.fecha_objetivo && (
          <span
            className={cn(
              "inline-flex items-center gap-1 text-sm",
              tarea.vencido ? "text-red-700 dark:text-red-300" : "text-muted-foreground",
            )}
          >
            <CalendarClock className="h-3.5 w-3.5" />
            {formatearFecha(tarea.fecha_objetivo)}
            {tarea.hora_objetivo ? ` · ${tarea.hora_objetivo}` : ""}
          </span>
        )}
      </div>

      {tarea.descripcion && (
        <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">
          {tarea.descripcion}
        </p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {libre && (
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            onClick={() => coger.mutate()}
            disabled={coger.isPending}
            title={esCobertura ? "La cubro yo" : "Coger"}
            aria-label={esCobertura ? "La cubro yo" : "Coger"}
          >
            <Hand className="h-3.5 w-3.5" />
          </Button>
        )}
        {avance && !libre && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate(avance.estado)}
            disabled={cambiarEstado.isPending}
          >
            <avance.icono className="mr-1 h-3.5 w-3.5" />
            {avance.etiqueta}
          </Button>
        )}
        {tarea.estado === "hecha" && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => cambiarEstado.mutate("pendiente")}
            disabled={cambiarEstado.isPending}
          >
            <RotateCcw className="mr-1 h-3.5 w-3.5" />
            Reabrir
          </Button>
        )}
        {!libre && (esMia || esManager) && (
          <Button variant="outline" size="sm" onClick={() => soltar.mutate()} disabled={soltar.isPending}>
            <Hand className="mr-1 h-3.5 w-3.5" />
            Soltar
          </Button>
        )}
        {esManager && (
          <Button variant="outline" size="sm" onClick={() => setAsignarAbierto(true)}>
            <UserPlus className="mr-1 h-3.5 w-3.5" />
            {libre ? "Asignar" : "Reasignar"}
          </Button>
        )}
        {esManager && !esCobertura && (
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            onClick={() => setConfirmarBorrado(true)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      <DialogoAsignar
        titulo={tarea.titulo}
        abierto={asignarAbierto}
        onOpenChange={setAsignarAbierto}
        usuarios={usuarios}
        responsableActual={tarea.responsable_id}
        onElegir={(id) => asignar.mutate(id)}
        enviando={asignar.isPending}
      />

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar "{tarea.titulo}"</DialogTitle>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmarBorrado(false)} disabled={borrar.isPending}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={() => borrar.mutate()} disabled={borrar.isPending}>
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Un ítem de la lista unificada: o un evento aún por cubrir, o una tarea (cobertura o encargo). */
type Item =
  | { kind: "evento"; clave: string; orden: string; evento: EventoRota }
  | { kind: "tarea"; clave: string; orden: string; tarea: Contenido };

// Colores fijos por persona: con 5 personas el color se vuelve reconocible de un vistazo
// (patrón de los calendarios editoriales: identidad por color, no solo por nombre).
const PALETA_PERSONA = [
  "bg-sky-500",
  "bg-violet-500",
  "bg-amber-500",
  "bg-emerald-500",
  "bg-rose-500",
  "bg-cyan-500",
] as const;

/** Color estable de una persona por hash de su id (mismo id → mismo color siempre). */
function colorPersona(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return PALETA_PERSONA[h % PALETA_PERSONA.length];
}

/** Avatar redondo con la inicial y el color propio de la persona. */
function AvatarPersona({
  id,
  nombre,
  size = "md",
}: {
  id: string;
  nombre: string;
  size?: "sm" | "md";
}) {
  return (
    <span
      title={nombre}
      className={cn(
        "inline-flex shrink-0 items-center justify-center rounded-full font-medium text-white",
        colorPersona(id),
        size === "sm" ? "h-5 w-5 text-[10px]" : "h-6 w-6 text-xs",
      )}
    >
      {(nombre || "?").slice(0, 1).toUpperCase()}
    </span>
  );
}

/** Etiqueta del encabezado de día: «Hoy» / «Mañana» / día legible / «Sin fecha». */
function sumarDias(iso: string, n: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}
function etiquetaDia(dia: string, hoy: string): string {
  if (!dia || dia === "9999-99-99") return "Sin fecha";
  if (dia === hoy) return "Hoy";
  if (dia === sumarDias(hoy, 1)) return "Mañana";
  return formatearDia(dia);
}

/** Banda superior: lo ÚLTIMO que ha cogido el equipo (por momento de asignación), para ver el pulso. */
function BandaReciente({ tareas }: { tareas: Contenido[] }) {
  const recientes = tareas
    .filter((t) => t.responsable_id)
    .slice()
    .sort((a, b) => (b.actualizado || "").localeCompare(a.actualizado || ""))
    .slice(0, 5);
  if (recientes.length === 0) return null;
  return (
    <section className="space-y-1.5">
      <h2 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        Lo último que ha cogido el equipo
      </h2>
      <div className="flex flex-wrap gap-2">
        {recientes.map((t) => {
          const rel = t.actualizado ? tiempoRelativo(t.actualizado) : "";
          return (
            <div
              key={t.id}
              className="flex items-center gap-1.5 rounded-full border border-border bg-card px-2 py-1 text-xs shadow-sm"
            >
              <AvatarPersona id={t.responsable_id} nombre={t.responsable_nombre} size="sm" />
              <span className="font-medium">{t.responsable_nombre}</span>
              <span className="max-w-[12rem] truncate text-muted-foreground">{t.titulo}</span>
              {rel && <span className="shrink-0 text-muted-foreground">· {rel}</span>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/**
 * Una FILA del agenda: compacta (hora · título · estado · dueño-o-«por cubrir»). Al desplegar
 * muestra la tarjeta real para coger/reasignar/avanzar sin salir del panorama.
 */
function FilaAgenda({
  item,
  abierta,
  onToggle,
  catalogos,
}: {
  item: Item;
  abierta: boolean;
  onToggle: () => void;
  catalogos: CatalogosContenido | undefined;
}) {
  const tarea = item.kind === "tarea" ? item.tarea : null;
  const evento = item.kind === "evento" ? item.evento : null;
  const titulo = tarea ? tarea.titulo : evento!.titulo;
  const hora = tarea ? tarea.hora_objetivo : evento!.hora;
  const sinDueno = !tarea || !tarea.responsable_id;
  const esCobertura = Boolean(tarea?.evento_id) || item.kind === "evento";

  return (
    <div
      className={cn(
        "rounded-md border",
        sinDueno
          ? "border-dashed border-amber-500/40 bg-amber-50/40 dark:bg-amber-950/10"
          : "border-border bg-card",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left"
      >
        {abierta ? (
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
        )}
        <span className="w-11 shrink-0 text-xs tabular-nums text-muted-foreground">
          {hora || "—"}
        </span>
        {esCobertura && <Trophy className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />}
        <span className="flex-1 truncate text-sm font-medium">{titulo}</span>
        {tarea?.estado === "en_curso" && (
          <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-300">
            En curso
          </Badge>
        )}
        {tarea?.estado === "hecha" && (
          <Badge
            variant="outline"
            className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300"
          >
            Hecha
          </Badge>
        )}
        {sinDueno ? (
          <Badge
            variant="outline"
            className="shrink-0 border-amber-500/50 text-amber-700 dark:text-amber-300"
          >
            Por cubrir
          </Badge>
        ) : (
          <span className="flex shrink-0 items-center gap-1">
            <AvatarPersona id={tarea!.responsable_id} nombre={tarea!.responsable_nombre} size="sm" />
            <span className="hidden text-xs text-muted-foreground sm:inline">
              {tarea!.responsable_nombre}
            </span>
          </span>
        )}
      </button>
      {abierta && (
        <div className="border-t border-border/60 bg-muted/20 p-2">
          {tarea ? (
            <TarjetaTarea tarea={tarea} catalogos={catalogos} />
          ) : (
            <TarjetaEventoLibre evento={evento!} catalogos={catalogos} />
          )}
        </div>
      )}
    </div>
  );
}

/**
 * PANORAMA (la cabina de Elias): una AGENDA por día —como un calendario— de quién cubre qué.
 *
 * Arriba, la carga por persona (avatar + conteo) que además FILTRA la agenda, y una banda con
 * lo último que ha cogido el equipo. Debajo, los partidos/encargos agrupados por día (Hoy /
 * Mañana / fecha) y ordenados por hora; lo «por cubrir» resalta en ámbar (es lo que pide
 * decisión). Cada fila se despliega para coger/reasignar. «Cargar más» trae más días.
 */
function PanoramaAgenda({
  tareas,
  eventosLibres,
  catalogos,
}: {
  tareas: Contenido[];
  eventosLibres: EventoRota[];
  catalogos: CatalogosContenido | undefined;
}) {
  const [abiertas, setAbiertas] = React.useState<Set<string>>(() => new Set());
  const [filtro, setFiltro] = React.useState<string | null>(null); // id de persona, "__pool__", o null
  const [diasVisibles, setDiasVisibles] = React.useState(5);
  const alternar = (clave: string) =>
    setAbiertas((prev) => {
      const next = new Set(prev);
      if (next.has(clave)) next.delete(clave);
      else next.add(clave);
      return next;
    });

  const usuarios = catalogos?.usuarios ?? [];
  const conResponsable = tareas.filter((t) => t.responsable_id);

  // Nombre por id: lo del catálogo manda; si falta, lo sellado en la tarea.
  const nombrePorId = new Map<string, string>();
  for (const u of usuarios) nombrePorId.set(u.id, u.usuario);
  for (const t of conResponsable) {
    if (!nombrePorId.has(t.responsable_id) && t.responsable_nombre)
      nombrePorId.set(t.responsable_id, t.responsable_nombre);
  }

  // Carga por persona = nº de tareas activas (no hechas). Más cargados primero (cuello de botella).
  const idsPersona = new Set<string>(usuarios.map((u) => u.id));
  for (const t of conResponsable) idsPersona.add(t.responsable_id);
  const cargas = [...idsPersona]
    .map((id) => ({
      id,
      nombre: nombrePorId.get(id) || "Sin nombre",
      n: conResponsable.filter((t) => t.responsable_id === id && t.estado !== "hecha").length,
    }))
    .sort((a, b) => b.n - a.n || a.nombre.localeCompare(b.nombre));
  const nPorCubrir = tareas.filter((t) => !t.responsable_id).length + eventosLibres.length;

  // Agenda, aplicando el filtro de persona/pool si lo hay.
  const pasaFiltro = (responsable: string | null) => {
    if (!filtro) return true;
    if (filtro === "__pool__") return responsable === null;
    return responsable === filtro;
  };
  const verEventos = !filtro || filtro === "__pool__"; // los eventos libres no tienen dueño
  const items: Item[] = [
    ...tareas
      .filter((t) => pasaFiltro(t.responsable_id || null))
      .map((t) => ({
        kind: "tarea" as const,
        clave: `t-${t.id}`,
        orden: t.fecha_objetivo || "9999-99-99",
        tarea: t,
      })),
    ...(verEventos
      ? eventosLibres.map((e) => ({
          kind: "evento" as const,
          clave: `e-${e.id}`,
          orden: e.fecha || "9999-99-99",
          evento: e,
        }))
      : []),
  ];

  // Agrupar por día y ordenar cada día por hora (estilo rundown).
  const horaDe = (i: Item) =>
    i.kind === "tarea" ? i.tarea.hora_objetivo || "99:99" : i.evento.hora || "99:99";
  const porDia = new Map<string, Item[]>();
  for (const it of items) {
    const lista = porDia.get(it.orden) ?? [];
    lista.push(it);
    porDia.set(it.orden, lista);
  }
  const diasOrdenados = [...porDia.keys()].sort();
  for (const d of diasOrdenados) porDia.get(d)!.sort((a, b) => horaDe(a).localeCompare(horaDe(b)));
  const diasMostrados = diasOrdenados.slice(0, diasVisibles);
  const hayMas = diasOrdenados.length > diasVisibles;
  const hoy = hoyCDMX();

  return (
    <div className="space-y-4">
      {/* Carga por persona (avatar + conteo) que además filtra la agenda. */}
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          aria-label="Ver solo lo por cubrir"
          onClick={() => setFiltro(filtro === "__pool__" ? null : "__pool__")}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
            filtro === "__pool__"
              ? "border-amber-500 bg-amber-100/60 dark:bg-amber-950/30"
              : "border-amber-500/40 hover:bg-accent",
          )}
        >
          <Hand className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
          Por cubrir
          <Badge variant="outline" className="px-1.5 py-0 tabular-nums">
            {nPorCubrir}
          </Badge>
        </button>
        {cargas.map((c) => (
          <button
            key={c.id}
            type="button"
            aria-label={`Ver solo lo de ${c.nombre}`}
            onClick={() => setFiltro(filtro === c.id ? null : c.id)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2 py-1 text-xs",
              filtro === c.id ? "border-foreground/40 bg-accent" : "border-border hover:bg-accent",
            )}
          >
            <AvatarPersona id={c.id} nombre={c.nombre} size="sm" />
            <span className="font-medium">{c.nombre}</span>
            <Badge
              variant="outline"
              className={cn("px-1.5 py-0 tabular-nums", c.n === 0 && "text-muted-foreground")}
            >
              {c.n}
            </Badge>
          </button>
        ))}
        {filtro && (
          <Button
            variant="ghost"
            size="sm"
            className="h-7 text-xs text-muted-foreground"
            onClick={() => setFiltro(null)}
          >
            Ver todo
          </Button>
        )}
      </div>

      {!filtro && <BandaReciente tareas={tareas} />}

      {diasMostrados.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {filtro
              ? "Nada por aquí con este filtro."
              : "Aún no hay partidos ni tareas. Súbelos en Fuentes o añádelos aquí."}
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {diasMostrados.map((dia) => (
            <section key={dia} className="space-y-1.5">
              <h2 className="sticky top-0 z-10 bg-background/95 py-1 text-sm font-semibold backdrop-blur">
                {etiquetaDia(dia, hoy)}
                <span className="ml-1.5 font-normal tabular-nums text-muted-foreground">
                  ({porDia.get(dia)!.length})
                </span>
              </h2>
              <div className="space-y-1.5">
                {porDia.get(dia)!.map((it) => (
                  <FilaAgenda
                    key={it.clave}
                    item={it}
                    abierta={abiertas.has(it.clave)}
                    onToggle={() => alternar(it.clave)}
                    catalogos={catalogos}
                  />
                ))}
              </div>
            </section>
          ))}
          {hayMas && (
            <div className="flex justify-center">
              <Button variant="outline" size="sm" onClick={() => setDiasVisibles((d) => d + 5)}>
                Cargar más días
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * TABLERO de Tareas del equipo (ClaroSports): la lista compartida que sustituye al WhatsApp.
 * Es el CUERPO reutilizable —SIN título de página— para montarlo tanto en su página suelta
 * (`/operacion/tareas`) como dentro de Turnos (pestaña «Cobertura»).
 *
 * Se LLENA SOLA con los eventos/partidos a cubrir (los que entran por Fuentes o se añaden aquí)
 * y los muestra ordenados por fecha como «Por cubrir»; el equipo los coge o Elias los reparte.
 * Conviven los encargos sueltos (tareas sin evento). El dueño de una cobertura se registra como
 * una tarea (clase='tarea') enlazada al evento: el evento es la unidad canónica, sin duplicar.
 *
 * `acciones`: dónde va el botón «Añadir». "barra" (default, página suelta) lo portaliza a la
 * barra superior vía AccionesPagina; "inline" (dentro de Turnos) lo pinta junto a las pestañas.
 */
export function TareasBoard({ acciones = "barra" }: { acciones?: "barra" | "inline" }) {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const [lente, setLente] = React.useState<Lente>("panorama");
  const [crearAbierto, setCrearAbierto] = React.useState(false);

  const marca = marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;
  const hoy = new Date().toISOString().slice(0, 10);

  const tareasQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "tareas", marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  const eventosQuery = useQuery({
    queryKey: [...CLAVE_TAREAS, "eventos", marca ?? "todas"],
    queryFn: ({ signal }) => api.rotaEventos({ desde: hoy, marca }, signal),
    ...REFRESCO,
  });

  const tareas = tareasQuery.data?.contenidos ?? [];
  const catalogos = tareasQuery.data?.catalogos;
  const cargando = tareasQuery.isLoading || eventosQuery.isLoading;

  // Eventos a cubrir = los coverables (no "no_cubrir") que aún NO tienen tarea de cobertura.
  const eventosConTarea = new Set(tareas.map((t) => t.evento_id).filter(Boolean));
  const eventosLibres = (eventosQuery.data?.eventos ?? []).filter(
    (e) => e.tipo_cobertura !== "no_cubrir" && !eventosConTarea.has(e.id),
  );

  // Lista unificada, ordenada por fecha (las sin fecha, al final).
  const conOrden = (f: string) => f || "9999-99-99";
  const items: Item[] = [
    ...tareas.map((t) => ({
      kind: "tarea" as const,
      clave: `t-${t.id}`,
      orden: conOrden(t.fecha_objetivo),
      tarea: t,
    })),
    ...eventosLibres.map((e) => ({
      kind: "evento" as const,
      clave: `e-${e.id}`,
      orden: conOrden(e.fecha),
      evento: e,
    })),
  ].sort((a, b) => a.orden.localeCompare(b.orden));

  const cumpleLente = (i: Item) => {
    if (lente === "libres") return i.kind === "evento" || !i.tarea.responsable_id;
    if (lente === "mias")
      return i.kind === "tarea" && Boolean(usuario && i.tarea.responsable_id === usuario.id);
    return true;
  };
  const visibles = items.filter(cumpleLente);

  // Tres grupos para que «se organice»: lo que falta por cubrir, lo que está en marcha, lo hecho.
  const grupos: { etiqueta: string; items: Item[] }[] = [
    {
      etiqueta: "Por cubrir",
      items: visibles.filter((i) => i.kind === "evento" || !i.tarea.responsable_id),
    },
    {
      etiqueta: "En marcha",
      items: visibles.filter(
        (i) => i.kind === "tarea" && i.tarea.responsable_id && i.tarea.estado !== "hecha",
      ),
    },
    {
      etiqueta: "Hechas",
      items: visibles.filter((i) => i.kind === "tarea" && i.tarea.estado === "hecha"),
    },
  ];
  const conteoPorCubrir = items.filter(
    (i) => i.kind === "evento" || !i.tarea.responsable_id,
  ).length;

  const pintar = (i: Item) =>
    i.kind === "evento" ? (
      <TarjetaEventoLibre key={i.clave} evento={i.evento} catalogos={catalogos} />
    ) : (
      <TarjetaTarea key={i.clave} tarea={i.tarea} catalogos={catalogos} />
    );

  // Lista agrupada (Por cubrir / En marcha / Hechas) que comparten «Por cubrir» y «Mis tareas».
  const listaAgrupada =
    visibles.length === 0 ? (
      <div className="rounded-lg border border-dashed border-border p-8 text-center">
        <p className="text-sm text-muted-foreground">
          {lente === "mias"
            ? "No tienes nada asignado. Coge algo de «Por cubrir»."
            : "No hay nada por cubrir ahora mismo."}
        </p>
      </div>
    ) : (
      grupos.map((g) =>
        g.items.length === 0 ? null : (
          <section key={g.etiqueta} className="space-y-2">
            <h2 className="text-sm font-medium text-muted-foreground">
              {g.etiqueta}
              <span className="ml-1.5 tabular-nums">({g.items.length})</span>
            </h2>
            <div className="space-y-2">{g.items.map(pintar)}</div>
          </section>
        ),
      )
    );

  const botonAnadir = (
    <Button size="sm" onClick={() => setCrearAbierto(true)}>
      <Plus className="mr-1 h-4 w-4" />
      Añadir
    </Button>
  );

  return (
    <>
      {acciones === "barra" && <AccionesPagina>{botonAnadir}</AccionesPagina>}

      <Tabs value={lente} onValueChange={(v) => setLente(v as Lente)} className="space-y-4">
        <div className="flex items-center justify-between gap-2">
          <TabsList>
            {LENTES.map((l) => (
              <TabsTrigger key={l.id} value={l.id}>
                {l.etiqueta}
                {l.id === "libres" && conteoPorCubrir > 0 && (
                  <Badge
                    variant="outline"
                    className="ml-1.5 bg-background px-1.5 py-0 tabular-nums"
                  >
                    {conteoPorCubrir}
                  </Badge>
                )}
              </TabsTrigger>
            ))}
          </TabsList>
          {acciones === "inline" && botonAnadir}
        </div>

        {cargando ? (
          <p className="text-sm text-muted-foreground">Cargando…</p>
        ) : (
          <>
            <TabsContent value="panorama">
              <PanoramaAgenda tareas={tareas} eventosLibres={eventosLibres} catalogos={catalogos} />
            </TabsContent>
            <TabsContent value="libres" className="space-y-4">
              {listaAgrupada}
            </TabsContent>
            <TabsContent value="mias" className="space-y-4">
              {listaAgrupada}
            </TabsContent>
          </>
        )}
      </Tabs>

      <DialogoCrearTarea
        abierto={crearAbierto}
        onOpenChange={setCrearAbierto}
        catalogos={catalogos}
        marca={marca}
      />
    </>
  );
}

/** Página suelta `/operacion/tareas`: el tablero con su título en la barra superior. */
export default function Tareas() {
  return (
    <>
      <TituloPagina titulo="Tareas del equipo" icono={ListChecks} />
      <TareasBoard />
    </>
  );
}
