import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  Hand,
  Play,
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
import { SesionContexto } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, Contenido, EventoRota } from "@/types";

import { AvatarPersona } from "./AvatarPersona";
import { CLAVE_TAREAS } from "./claves";
import { DialogoAsignar } from "./dialogos";
import type { Cobertura } from "./tipos";

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

/**
 * Un EVENTO «Por cubrir»: un partido/transmisión que nadie ha cogido todavía. No tiene tarea
 * aún; al coger (o que Elias asigne) se crea su registro de cobertura vía `cubrirEvento`.
 */
export function TarjetaEventoLibre({
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
export function TarjetaTarea({
  tarea,
  catalogos,
  enCobertura = false,
}: {
  tarea: Contenido;
  catalogos: CatalogosContenido | undefined;
  /** Dentro de una cobertura: oculta «Soltar»/«Reasignar» (se gestionan a nivel de evento). */
  enCobertura?: boolean;
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
        {!enCobertura && !libre && (esMia || esManager) && (
          <Button variant="outline" size="sm" onClick={() => soltar.mutate()} disabled={soltar.isPending}>
            <Hand className="mr-1 h-3.5 w-3.5" />
            Soltar
          </Button>
        )}
        {!enCobertura && esManager && (
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

/**
 * COBERTURA de un evento con uno o VARIOS cubridores. Cabecera con quién lo cubre + acciones
 * («Apuntarme» yo, «Añadir a alguien» el manager) y, debajo, la tarjeta de cada cubridor para
 * que cada quien avance o suelte LA SUYA (soltar = dejar de cubrir; los demás siguen).
 */
export function TarjetaCobertura({
  cobertura,
  catalogos,
}: {
  cobertura: Cobertura;
  catalogos: CatalogosContenido | undefined;
}) {
  const queryClient = useQueryClient();
  const usuario = React.useContext(SesionContexto)?.usuario ?? null;
  const esManager = usuario?.rol === "admin";
  const [asignarAbierto, setAsignarAbierto] = React.useState(false);
  const usuarios = catalogos?.usuarios ?? [];
  const yaApuntado = Boolean(
    usuario && cobertura.cubridores.some((t) => t.responsable_id === usuario.id),
  );

  const cubrir = useMutation({
    mutationFn: (responsableId?: string) => api.cubrirEvento(cobertura.eventoId, responsableId),
    onSuccess: (res) => {
      setAsignarAbierto(false);
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const nombre = res?.contenido?.responsable_nombre || "ti";
      toast.success(`"${cobertura.titulo}" la cubre ${nombre}.`);
    },
    onError: (e) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.error(mensajeError(e));
    },
  });

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Cubren:</span>
        {cobertura.cubridores.map((t) => (
          <span key={t.id} className="inline-flex items-center gap-1 text-sm">
            <AvatarPersona id={t.responsable_id} nombre={t.responsable_nombre} size="sm" />
            {t.responsable_nombre}
          </span>
        ))}
      </div>
      <div className="space-y-2">
        {cobertura.cubridores.map((t) => (
          <TarjetaTarea key={t.id} tarea={t} catalogos={catalogos} enCobertura />
        ))}
      </div>
      {/* Acciones a nivel de evento, junto al avance de cada cubridor (Empezar/Marcar hecha). */}
      {(!yaApuntado || esManager) && (
        <div className="flex flex-wrap items-center gap-2">
          {!yaApuntado && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => cubrir.mutate(undefined)}
              disabled={cubrir.isPending}
            >
              <UserPlus className="mr-1 h-3.5 w-3.5" />
              Apuntarme
            </Button>
          )}
          {esManager && (
            <Button variant="outline" size="sm" onClick={() => setAsignarAbierto(true)}>
              <UserPlus className="mr-1 h-3.5 w-3.5" />
              Añadir a alguien
            </Button>
          )}
        </div>
      )}

      <DialogoAsignar
        titulo={cobertura.titulo}
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
