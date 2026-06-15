// Diálogos del calendario de la rota: edición de evento, edición de turno y popup de
// carga del equipo.
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Loader2,
  Trash2,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import type {
  Contenido,
  EventoRota,
  FranjaTurno,
  MiembroRota,
  PrioridadEvento,
  TipoCoberturaEvento,
  TurnoRota,
} from "@/types";

import { PRIORIDADES, TIPOS_COBERTURA } from "../comun";


/**
 * Diálogo de edición rápida de evento: lo que más se cambia desde el calendario.
 *
 * `tareasVinculadas` (opcional) son las TAREAS de cobertura enlazadas al evento (cubridores +
 * roles soltados). El calendario NO las pasa (su cobertura es por turnos); la AGENDA de Tareas
 * SÍ, porque allí la fila de cobertura se DERIVA de esas tareas (su título/fecha son una foto
 * del evento tomada al cubrir). Con ellas: al guardar se propaga el cambio a cada tarea (si no,
 * editar el partido no se vería en la agenda) y al borrar se borran en cascada (si no, la fila
 * de cobertura seguiría viva). Sin ellas, el diálogo se comporta como siempre (solo el evento).
 */
export function DialogEditarEvento({
  evento,
  onCerrar,
  onCambio,
  tareasVinculadas,
}: {
  evento: EventoRota;
  onCerrar: () => void;
  onCambio: () => void;
  tareasVinculadas?: Contenido[];
}) {
  const [titulo, setTitulo] = React.useState(evento.titulo);
  const [fecha, setFecha] = React.useState(evento.fecha);
  const [hora, setHora] = React.useState(evento.hora);
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>(
    evento.tipo_cobertura,
  );
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>(evento.prioridad);
  const [contenido, setContenido] = React.useState(evento.contenido);

  const vinculadas = tareasVinculadas ?? [];
  const guardar = useMutation({
    mutationFn: async () => {
      await api.actualizarEventoRota(evento.id, {
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
        contenido: contenido.trim(),
      });
      // Propaga el cambio a las tareas de cobertura: su título/fecha/hora son una foto del
      // evento al cubrir, así que sin esto la agenda mostraría los datos viejos del partido.
      if (vinculadas.length > 0) {
        await Promise.all(
          vinculadas.map((t) =>
            api.actualizarContenido(t.id, {
              titulo: titulo.trim(),
              fecha_objetivo: fecha,
              hora_objetivo: hora.trim(),
              prioridad,
            }),
          ),
        );
      }
    },
    onSuccess: () => {
      toast.success("Evento guardado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: async () => {
      await api.eliminarEventoRota(evento.id);
      // Cascada: la fila de cobertura se deriva de estas tareas, no del evento; sin borrarlas
      // el partido seguiría apareciendo (ahora sin dueño claro). Borrar el evento = cancelarlo.
      if (vinculadas.length > 0) {
        await Promise.all(vinculadas.map((t) => api.eliminarContenido(t.id)));
      }
    },
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  // Aviso de borrado adaptado: si hay gente cubriendo, deja claro que se cancela su cobertura.
  const nCubren = vinculadas.filter((t) => t.responsable_id).length;
  const mensajeBorrar =
    nCubren > 0
      ? `¿Borrar este evento? Cancelará la cobertura de ${nCubren} ${nCubren === 1 ? "persona" : "personas"}.`
      : "¿Borrar este evento? Sus turnos también se perderán.";

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar evento</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ce-titulo">Evento / transmisión</Label>
            <Input
              id="ce-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ce-fecha">Fecha</Label>
              <Input
                id="ce-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ce-hora">Hora</Label>
              <Input
                id="ce-hora"
                value={hora}
                onChange={(e) => setHora(e.target.value)}
                placeholder="16:00"
                maxLength={40}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>Cobertura</Label>
              <Select
                value={tipoCobertura}
                onValueChange={(v) => setTipoCobertura(v as TipoCoberturaEvento)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS_COBERTURA.map((t) => (
                    <SelectItem key={t.valor} value={t.valor}>
                      {t.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Prioridad</Label>
              <Select value={prioridad} onValueChange={(v) => setPrioridad(v as PrioridadEvento)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORIDADES.map((p) => (
                    <SelectItem key={p.valor} value={p.valor}>
                      {p.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ce-contenido">Qué sacar</Label>
            <Textarea
              id="ce-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </div>
        </div>
        <DialogFooter className="flex-row justify-between gap-2 sm:justify-between">
          <Button
            variant="outline"
            className="text-destructive hover:text-destructive"
            onClick={async () => {
              if (
                await confirmar({
                  mensaje: mensajeBorrar,
                  destructivo: true,
                  textoConfirmar: "Borrar",
                })
              )
                borrar.mutate();
            }}
            disabled={borrar.isPending}
          >
            {borrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Borrar
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button onClick={() => guardar.mutate()} disabled={guardar.isPending}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo para editar detalles de un turno (persona, motivo, nota de relevo). */
export function DialogEditarTurno({
  turno,
  equipo,
  onCerrar,
  onGuardado,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  onCerrar: () => void;
  onGuardado: () => void;
}) {
  const [fecha, setFecha] = React.useState(turno.fecha);
  const [miembroId, setMiembroId] = React.useState(turno.miembro_id);
  const [franja, setFranja] = React.useState<FranjaTurno>(turno.franja);
  const [motivo, setMotivo] = React.useState(turno.motivo);
  const [notaRelevo, setNotaRelevo] = React.useState(turno.nota_relevo);
  // Si el backend devuelve 409 requiere_override, mostramos botón "forzar".
  const [pendienteOverride, setPendienteOverride] = React.useState<{ mensaje: string } | null>(
    null,
  );

  const guardar = useMutation({
    mutationFn: (override: boolean) => {
      const cuerpo: {
        fecha?: string;
        miembro_id?: string;
        franja?: FranjaTurno;
        motivo?: string;
        nota_relevo?: string;
        override?: boolean;
      } = {};
      if (fecha !== turno.fecha) cuerpo.fecha = fecha;
      if (miembroId !== turno.miembro_id) cuerpo.miembro_id = miembroId;
      if (franja !== turno.franja) cuerpo.franja = franja;
      if (motivo !== turno.motivo) cuerpo.motivo = motivo;
      if (notaRelevo !== turno.nota_relevo) cuerpo.nota_relevo = notaRelevo;
      if (override) cuerpo.override = true;
      return api.actualizarTurno(turno.id, cuerpo);
    },
    onSuccess: () => {
      toast.success("Turno actualizado.");
      onGuardado();
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        setPendienteOverride({ mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const sinCambios =
    fecha === turno.fecha &&
    miembroId === turno.miembro_id &&
    franja === turno.franja &&
    motivo === turno.motivo &&
    notaRelevo === turno.nota_relevo;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar turno</DialogTitle>
          <DialogDescription>
            Edita los detalles del turno. Las reglas se validan al guardar.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="et-fecha">Fecha</Label>
              <Input
                id="et-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Franja</Label>
              <Select value={franja} onValueChange={(v) => setFranja(v as FranjaTurno)}>
                <SelectTrigger aria-label="Franja">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="matutino">Mañana</SelectItem>
                  <SelectItem value="vespertino">Tarde</SelectItem>
                  <SelectItem value="descanso">Descanso</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label>Persona</Label>
            <Select value={miembroId} onValueChange={setMiembroId}>
              <SelectTrigger aria-label="Persona del turno">
                <SelectValue placeholder="Sin asignar" />
              </SelectTrigger>
              <SelectContent>
                {equipo.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-motivo">Motivo</Label>
            <Input
              id="et-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Opcional: cobertura forzada por evento crítico"
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-nota">Nota de relevo</Label>
            <Textarea
              id="et-nota"
              value={notaRelevo}
              onChange={(e) => setNotaRelevo(e.target.value)}
              placeholder="Opcional: qué queda pendiente para el siguiente turno"
              rows={3}
              maxLength={1000}
            />
          </div>
          {pendienteOverride && (
            <div className="rounded-md border border-amber-300/60 bg-amber-50/40 p-3 text-sm text-amber-900 dark:bg-amber-950/20 dark:text-amber-300">
              <p className="font-medium">{pendienteOverride.mensaje}</p>
              <p className="mt-1 text-xs">
                Confirma solo si es una cobertura estratégica intencional.
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          {pendienteOverride ? (
            <Button
              variant="outline"
              className="text-amber-700 hover:text-amber-700 dark:text-amber-400"
              onClick={() => guardar.mutate(true)}
              disabled={guardar.isPending}
            >
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              <AlertTriangle className="h-4 w-4" /> Forzar override
            </Button>
          ) : (
            <Button onClick={() => guardar.mutate(false)} disabled={sinCambios || guardar.isPending}>
              {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Guardar
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Popup "Carga del equipo" -----------------------------------------------

/**
 * Resumen de carga del equipo de la semana, en un diálogo. Se invoca bajo demanda
 * desde el menú "Más". El componente sólo se monta cuando el popup está abierto,
 * así que la query arranca al abrir.
 */
export function DialogCargaEquipo({ lunes, onCerrar }: { lunes: string; onCerrar: () => void }) {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "carga", lunes, marcaActiva],
    queryFn: ({ signal }) =>
      api.cargaRota({ lunes, marca: marcaActiva ?? undefined }, signal),
    enabled: !!lunes,
  });
  const miembros = q.data?.miembros ?? [];
  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-4 w-4" /> Carga del equipo
          </DialogTitle>
          <DialogDescription>
            Cuánto trabajo lleva cada persona esta semana.
          </DialogDescription>
        </DialogHeader>
        {q.isPending ? (
          <Skeleton className="h-24 w-full" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudo cargar el resumen"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : miembros.length === 0 ? (
          <EstadoVacio
            icono={Users}
            titulo="Sin datos"
            texto="No hay miembros del equipo todavía."
          />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Persona</TableHead>
                <TableHead className="text-right">Eventos</TableHead>
                <TableHead className="text-right">Días trabajados</TableHead>
                <TableHead>Sábado</TableHead>
                <TableHead className="text-right">Descansos</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {miembros.map((m) => (
                <TableRow key={m.miembro_id}>
                  <TableCell className="font-medium">{m.nombre}</TableCell>
                  <TableCell
                    className={
                      m.eventos >= 7
                        ? "text-right font-medium text-red-600 dark:text-red-400"
                        : "text-right"
                    }
                  >
                    {m.eventos}
                  </TableCell>
                  <TableCell className="text-right">{m.dias_trabajados}</TableCell>
                  <TableCell>
                    {m.sabado ? (
                      <Badge variant="outline" className="font-normal">
                        Sábado
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">{m.descansos}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
    </Dialog>
  );
}
