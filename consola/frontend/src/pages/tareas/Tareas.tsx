import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Hand,
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
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido } from "@/types";

import { CLAVE_TAREAS } from "./claves";
import { DialogoCrearTarea } from "./DialogoCrearTarea";

// El tablero es COMPARTIDO: late al mismo pulso para que el claim/asignación de un compañero
// se vea sin recargar (igual que el reparto del feed que esto sustituye).
const REFRESCO = { refetchInterval: 45_000, refetchOnWindowFocus: true };

/** Lente sobre la MISMA lista: el pool, lo mío, o todo (la cabina de Elias). */
type Lente = "equipo" | "libres" | "mias";
const LENTES: { id: Lente; etiqueta: string }[] = [
  { id: "equipo", etiqueta: "Todo el equipo" },
  { id: "libres", etiqueta: "Por coger" },
  { id: "mias", etiqueta: "Mis tareas" },
];

/** Ciclo de vida de una tarea (estados de keni: pendiente → en_curso → hecha). */
const ESTADOS: { id: string; etiqueta: string }[] = [
  { id: "pendiente", etiqueta: "Pendientes" },
  { id: "en_curso", etiqueta: "En curso" },
  { id: "hecha", etiqueta: "Hechas" },
];
const SIGUIENTE: Record<string, { estado: string; etiqueta: string; icono: typeof Play }> = {
  pendiente: { estado: "en_curso", etiqueta: "Empezar", icono: Play },
  en_curso: { estado: "hecha", etiqueta: "Marcar hecha", icono: Check },
};

const PRIORIDAD_CLASE: Record<string, string> = {
  alta: "border-red-500/40 text-red-700 dark:text-red-300",
  media: "border-amber-500/40 text-amber-700 dark:text-amber-300",
  baja: "border-border text-muted-foreground",
};

/** Una tarjeta de tarea: estado, responsable, prioridad, fecha y evento, con sus acciones. */
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

  const evento = (catalogos?.eventos ?? []).find((e) => e.id === tarea.evento_id);
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

  return (
    <div className="rounded-lg border border-border bg-card p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
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
          </span>
        )}
        {evento && (
          <Badge
            variant="outline"
            className="gap-1 border-sky-500/40 font-normal text-sky-700 dark:text-sky-300"
            title={`Cobertura del evento: ${evento.titulo}`}
          >
            <Trophy className="h-3 w-3" />
            {evento.titulo}
          </Badge>
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
            size="sm"
            onClick={() => coger.mutate()}
            disabled={coger.isPending}
          >
            <Hand className="mr-1 h-3.5 w-3.5" />
            Coger
          </Button>
        )}
        {avance && (
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
          <Button
            variant="outline"
            size="sm"
            onClick={() => soltar.mutate()}
            disabled={soltar.isPending}
          >
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
        {esManager && (
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

      {/* Asignar a una persona (push del manager). Reusa el catálogo del tablero. */}
      <Dialog open={asignarAbierto} onOpenChange={setAsignarAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Asignar "{tarea.titulo}"</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Elige a quién se la encargas; se le avisa en la app.
          </p>
          <div className="max-h-72 space-y-1 overflow-y-auto py-1">
            {usuarios.length === 0 && (
              <p className="px-1 text-sm text-muted-foreground">
                No hay compañeros para asignar.
              </p>
            )}
            {usuarios.map((u) => {
              const yaEs = u.id === tarea.responsable_id;
              return (
                <button
                  key={u.id}
                  type="button"
                  disabled={asignar.isPending || yaEs}
                  onClick={() => asignar.mutate(u.id)}
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
            <Button variant="outline" onClick={() => setAsignarAbierto(false)}>
              Cancelar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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

/**
 * Página de TAREAS del equipo (ClaroSports): el tablero compartido que sustituye al WhatsApp.
 * Quién cubre qué — coberturas de partidos/eventos y encargos del equipo. Es un concepto
 * SEPARADO de las piezas de contenido (esto es `clase='tarea'`; el Feed sigue siendo piezas).
 *
 * Tres lentes sobre la misma lista (pool «Por coger» / «Mis tareas» / «Todo el equipo» para
 * Elias) y tres estados (pendiente → en curso → hecha). El reparto (coger/soltar/asignar) es
 * el mismo primitivo que ya existía, ahora en su sitio correcto: las tareas, no las piezas.
 */
export default function Tareas() {
  const { marcaActiva } = useMarcaActiva();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const [lente, setLente] = React.useState<Lente>("equipo");
  const [crearAbierto, setCrearAbierto] = React.useState(false);

  const marca =
    marcaActiva && marcaActiva !== MARCA_ACTIVA_TODAS ? marcaActiva : undefined;

  const query = useQuery({
    queryKey: [...CLAVE_TAREAS, marca ?? "todas"],
    queryFn: ({ signal }) => api.contenido({ clase: "tarea", marca }, signal),
    ...REFRESCO,
  });
  const tareas = query.data?.contenidos ?? [];
  const catalogos = query.data?.catalogos;

  const visibles = tareas.filter((t) => {
    if (lente === "libres") return !t.responsable_id;
    if (lente === "mias") return Boolean(usuario && t.responsable_id === usuario.id);
    return true;
  });
  const porEstado = (estado: string) => visibles.filter((t) => t.estado === estado);
  const conteoLibres = tareas.filter((t) => !t.responsable_id).length;

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Tareas del equipo</h1>
          <p className="text-sm text-muted-foreground">
            Quién cubre qué: coberturas de partidos y encargos. Cógelas del pool o que Elias
            las reparta.
          </p>
        </div>
        <Button onClick={() => setCrearAbierto(true)}>
          <Plus className="mr-1 h-4 w-4" />
          Nueva tarea
        </Button>
      </div>

      {/* Lentes (segmented). El pool muestra su contador para que «¿qué falta?» sea de un vistazo. */}
      <div className="flex flex-wrap gap-2">
        {LENTES.map((l) => (
          <Button
            key={l.id}
            variant={lente === l.id ? "default" : "outline"}
            size="sm"
            onClick={() => setLente(l.id)}
          >
            {l.etiqueta}
            {l.id === "libres" && conteoLibres > 0 && (
              <Badge variant="outline" className="ml-1.5 bg-background px-1.5 py-0 tabular-nums">
                {conteoLibres}
              </Badge>
            )}
          </Button>
        ))}
      </div>

      {query.isLoading && <p className="text-sm text-muted-foreground">Cargando tareas…</p>}

      {!query.isLoading && visibles.length === 0 && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center">
          <p className="text-sm text-muted-foreground">
            {lente === "mias"
              ? "No tienes tareas asignadas. Coge alguna de «Por coger»."
              : lente === "libres"
                ? "No hay tareas libres ahora mismo."
                : "Aún no hay tareas. Crea la primera con «Nueva tarea»."}
          </p>
        </div>
      )}

      {!query.isLoading &&
        visibles.length > 0 &&
        ESTADOS.map((est) => {
          const items = porEstado(est.id);
          if (items.length === 0) return null;
          return (
            <section key={est.id} className="space-y-2">
              <h2 className="text-sm font-medium text-muted-foreground">
                {est.etiqueta}
                <span className="ml-1.5 tabular-nums">({items.length})</span>
              </h2>
              <div className="space-y-2">
                {items.map((t) => (
                  <TarjetaTarea key={t.id} tarea={t} catalogos={catalogos} />
                ))}
              </div>
            </section>
          );
        })}

      <DialogoCrearTarea
        abierto={crearAbierto}
        onOpenChange={setCrearAbierto}
        catalogos={catalogos}
        marca={marca}
      />
    </div>
  );
}
