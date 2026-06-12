import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
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
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido, EventoRota } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Lente sobre la MISMA lista: el pool, lo mío, o todo (la cabina de Elias). */
type Lente = "equipo" | "libres" | "mias";
const LENTES: { id: Lente; etiqueta: string }[] = [
  { id: "equipo", etiqueta: "Todo el equipo" },
  { id: "libres", etiqueta: "Por cubrir" },
  { id: "mias", etiqueta: "Lo mío" },
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

/**
 * Página de TAREAS del equipo (ClaroSports): la lista compartida que sustituye al WhatsApp.
 *
 * Se LLENA SOLA con los eventos/partidos a cubrir (los que entran por Fuentes o se añaden aquí)
 * y los muestra ordenados por fecha como «Por cubrir»; el equipo los coge o Elias los reparte.
 * Conviven los encargos sueltos (tareas sin evento). El dueño de una cobertura se registra como
 * una tarea (clase='tarea') enlazada al evento: el evento es la unidad canónica, sin duplicar.
 */
export default function Tareas() {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const [lente, setLente] = React.useState<Lente>("equipo");
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

  return (
    <>
      <TituloPagina titulo="Tareas del equipo" icono={ListChecks} />
      <AccionesPagina>
        <Button size="sm" onClick={() => setCrearAbierto(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Añadir
        </Button>
      </AccionesPagina>

      <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Los partidos y encargos a cubrir, por fecha. Cógelos o que Elias los reparta; lo que
        entra por Fuentes aparece aquí solo.
      </p>

      <div className="flex flex-wrap gap-2">
        {LENTES.map((l) => (
          <Button
            key={l.id}
            variant={lente === l.id ? "default" : "outline"}
            size="sm"
            onClick={() => setLente(l.id)}
          >
            {l.etiqueta}
            {l.id === "libres" && conteoPorCubrir > 0 && (
              <Badge variant="outline" className="ml-1.5 bg-background px-1.5 py-0 tabular-nums">
                {conteoPorCubrir}
              </Badge>
            )}
          </Button>
        ))}
      </div>

      {cargando && <p className="text-sm text-muted-foreground">Cargando…</p>}

      {!cargando && visibles.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {lente === "mias"
              ? "No tienes nada asignado. Coge algo de «Por cubrir»."
              : lente === "libres"
                ? "No hay nada por cubrir ahora mismo."
                : "Aún no hay partidos ni tareas. Súbelos en Fuentes o añádelos aquí."}
          </p>
        </div>
      )}

      {!cargando &&
        visibles.length > 0 &&
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
        )}

      <DialogoCrearTarea
        abierto={crearAbierto}
        onOpenChange={setCrearAbierto}
        catalogos={catalogos}
        marca={marca}
      />
      </div>
    </>
  );
}
