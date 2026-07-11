// Diálogos del calendario de la rota: edición de evento, edición de turno y popup de
// carga del equipo.
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  Trash2,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { BloqueError } from "@/components/comunes/BloqueError";
import { Campo } from "@/components/comunes/Campo";
import { confirmar, elegir } from "@/components/comunes/confirmar";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
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
import {
  SelectorRecurrencia,
  type ValorRecurrencia,
} from "@/pages/rota/SelectorRecurrencia";
import type {
  AlcanceSerie,
  Publicacion,
  EventoRota,
  FranjaSemana,
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
  tareasVinculadas?: Publicacion[];
}) {
  const [titulo, setTitulo] = React.useState(evento.titulo);
  const [fecha, setFecha] = React.useState(evento.fecha);
  const [hora, setHora] = React.useState(evento.hora);
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>(
    evento.tipo_cobertura,
  );
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>(evento.prioridad);
  const [contenido, setPublicacion] = React.useState(evento.contenido);
  // Recurrencia para CONVERTIR un evento suelto en serie (solo si aún no pertenece a una).
  const [recurrencia, setRecurrencia] = React.useState<ValorRecurrencia | null>(null);
  // Bloquea reentradas mientras se espera el diálogo de alcance/confirmación, antes de que
  // `isPending` de la mutación tome el relevo.
  const [enviando, setEnviando] = React.useState(false);

  const vinculadas = tareasVinculadas ?? [];
  const esSerie = Boolean(evento.serie_id);
  // «Personalizado» sin días no es una recurrencia válida: no dejes guardar en ese estado.
  const recurrenciaIncompleta =
    !esSerie && recurrencia !== null && recurrencia.dias_semana.length === 0;
  const guardar = useMutation({
    mutationFn: async (alcance?: AlcanceSerie) => {
      const campos = {
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
        contenido: contenido.trim(),
      };
      // Sin alcance (evento suelto) la llamada es la de siempre; con alcance propaga a la serie.
      if (alcance) await api.actualizarEventoRota(evento.id, campos, alcance);
      else await api.actualizarEventoRota(evento.id, campos);
      // Convertir en serie: si el evento NO era recurrente y el usuario configuró «Repetir»,
      // genera las ocurrencias (clona los campos YA guardados de este evento como ancla).
      const serie =
        !esSerie && recurrencia ? await api.repetirEventoRota(evento.id, recurrencia) : null;
      // Propaga el cambio a las tareas de cobertura: su título/fecha/hora son una foto del
      // evento al cubrir, así que sin esto la agenda mostraría los datos viejos del partido.
      if (vinculadas.length > 0) {
        await Promise.all(
          vinculadas.map((t) =>
            api.actualizarPublicacion(t.id, {
              titulo: titulo.trim(),
              fecha_objetivo: fecha,
              hora_objetivo: hora.trim(),
              prioridad,
            }),
          ),
        );
      }
      return serie;
    },
    onSuccess: (serie) => {
      toast.success(
        serie && serie.total > 1
          ? `Serie creada: ${serie.total} eventos.`
          : "Evento guardado.",
      );
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: async (alcance?: AlcanceSerie) => {
      if (alcance) await api.eliminarEventoRota(evento.id, alcance);
      else await api.eliminarEventoRota(evento.id);
      // Cascada: la fila de cobertura se deriva de estas tareas, no del evento; sin borrarlas
      // el partido seguiría apareciendo (ahora sin dueño claro). Borrar el evento = cancelarlo.
      if (vinculadas.length > 0) {
        await Promise.all(vinculadas.map((t) => api.eliminarPublicacion(t.id)));
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

  // En una serie, editar/borrar pregunta el ALCANCE (este / siguientes / toda la serie). Devuelve
  // el alcance elegido, o null si se cancela. Un evento suelto no pregunta y devuelve undefined.
  async function elegirAlcance(verbo: "Editar" | "Borrar"): Promise<AlcanceSerie | null | undefined> {
    if (!esSerie) return undefined;
    return (await elegir({
      titulo: `${verbo} evento recurrente`,
      mensaje: `"${evento.titulo}" se repite. ¿A qué eventos aplicar?`,
      opciones: [
        { valor: "este", etiqueta: "Solo este" },
        { valor: "siguientes", etiqueta: "Este y los siguientes" },
        { valor: "serie", etiqueta: "Toda la serie", destructivo: verbo === "Borrar" },
      ],
    })) as AlcanceSerie | null;
  }

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar evento</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {esSerie && (
            <p className="text-sm text-muted-foreground">
              Forma parte de una serie recurrente: al guardar o borrar podrás elegir el alcance.
            </p>
          )}
          <Campo etiqueta="Evento / transmisión" htmlFor="ce-titulo">
            <Input
              id="ce-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              maxLength={200}
            />
          </Campo>
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Fecha" htmlFor="ce-fecha">
              <Input
                id="ce-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </Campo>
            <Campo etiqueta="Hora (CDMX)" htmlFor="ce-hora">
              <Input
                id="ce-hora"
                value={hora}
                onChange={(e) => setHora(e.target.value)}
                placeholder="16:00"
                maxLength={40}
              />
            </Campo>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Cobertura">
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
            </Campo>
            <Campo etiqueta="Prioridad">
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
            </Campo>
          </div>
          <Campo etiqueta="Qué sacar" htmlFor="ce-contenido">
            <Textarea
              id="ce-contenido"
              value={contenido}
              onChange={(e) => setPublicacion(e.target.value)}
              rows={3}
              maxLength={2000}
            />
          </Campo>
          {/* Convertir un evento suelto en recurrente: configurar «Repetir» aquí lo vuelve serie
              al guardar. Un evento que YA es serie no lo muestra (se gestiona por alcance). */}
          {!esSerie && <SelectorRecurrencia fechaBase={fecha} onChange={setRecurrencia} />}
        </div>
        <DialogFooter className="flex-row justify-between gap-2 sm:justify-between">
          <Button
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={async () => {
              setEnviando(true);
              try {
                if (esSerie) {
                  const alcance = await elegirAlcance("Borrar");
                  if (alcance) borrar.mutate(alcance);
                  return;
                }
                if (
                  await confirmar({
                    mensaje: mensajeBorrar,
                    destructivo: true,
                    textoConfirmar: "Borrar",
                  })
                )
                  borrar.mutate(undefined);
              } finally {
                setEnviando(false);
              }
            }}
            disabled={enviando || borrar.isPending}
          >
            {borrar.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Borrar
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onCerrar}>
              Cancelar
            </Button>
            <Button
              variant="default"
              onClick={async () => {
                setEnviando(true);
                try {
                  const alcance = await elegirAlcance("Editar");
                  if (alcance === null) return; // canceló el diálogo de alcance
                  guardar.mutate(alcance);
                } finally {
                  setEnviando(false);
                }
              }}
              disabled={enviando || guardar.isPending || recurrenciaIncompleta}
            >
              {guardar.isPending && <Spinner className="h-4 w-4" />}
              Guardar
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo para editar detalles de un turno (persona, motivo, nota de relevo). */
/** Valores editables del diálogo de turno (estado del formulario). */
export type EdicionTurno = {
  fecha: string;
  miembroId: string;
  franjaId: string;
  inicio: string;
  fin: string;
  motivo: string;
  notaRelevo: string;
};

/** Cuerpo del PATCH de un turno: SOLO los campos que cambiaron respecto al turno actual. La
 * franja viaja como `franja_id` (la franja viva real), no como literal legacy: así editar un
 * turno en franja a medida no lo saca de su franja. Extraída para testear sin el Select de Radix
 * (que dentro de un Dialog se cuelga en jsdom). */
export function construirCuerpoEdicion(
  turno: TurnoRota,
  edicion: EdicionTurno,
  override: boolean,
) {
  const cuerpo: {
    fecha?: string;
    miembro_id?: string;
    franja_id?: string;
    inicio?: string;
    fin?: string;
    motivo?: string;
    nota_relevo?: string;
    override?: boolean;
  } = {};
  if (edicion.fecha !== turno.fecha) cuerpo.fecha = edicion.fecha;
  if (edicion.miembroId !== turno.miembro_id) cuerpo.miembro_id = edicion.miembroId;
  if (edicion.franjaId !== turno.franja_id) cuerpo.franja_id = edicion.franjaId;
  if (edicion.inicio !== turno.inicio) cuerpo.inicio = edicion.inicio.trim();
  if (edicion.fin !== turno.fin) cuerpo.fin = edicion.fin.trim();
  if (edicion.motivo !== turno.motivo) cuerpo.motivo = edicion.motivo;
  if (edicion.notaRelevo !== turno.nota_relevo) cuerpo.nota_relevo = edicion.notaRelevo;
  if (override) cuerpo.override = true;
  return cuerpo;
}

export function DialogEditarTurno({
  turno,
  equipo,
  franjas,
  onCerrar,
  onGuardado,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  /** Franjas VIVAS de la semana del turno: el desplegable ofrece estas (por `franja_id`),
   * no las tres legacy — así un turno en franja a medida («Nocturna») no salta a otra al editar. */
  franjas: FranjaSemana[];
  onCerrar: () => void;
  onGuardado: () => void;
}) {
  const [fecha, setFecha] = React.useState(turno.fecha);
  const [miembroId, setMiembroId] = React.useState(turno.miembro_id);
  const [franjaId, setFranjaId] = React.useState(turno.franja_id);
  // Horario efectivo del turno (sus horas a medida o las de su franja). Editable: cambiarlo
  // pone horas a medida; dejarlo igual no toca nada (sigue heredando si así estaba).
  const [inicio, setInicio] = React.useState(turno.inicio);
  const [fin, setFin] = React.useState(turno.fin);
  const [motivo, setMotivo] = React.useState(turno.motivo);
  const [notaRelevo, setNotaRelevo] = React.useState(turno.nota_relevo);
  // Si el backend devuelve 409 requiere_override, mostramos botón "forzar".
  const [pendienteOverride, setPendienteOverride] = React.useState<{ mensaje: string } | null>(
    null,
  );

  const guardar = useMutation({
    mutationFn: (override: boolean) =>
      api.actualizarTurno(
        turno.id,
        construirCuerpoEdicion(
          turno,
          { fecha, miembroId, franjaId, inicio, fin, motivo, notaRelevo },
          override,
        ),
      ),
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
    franjaId === turno.franja_id &&
    inicio === turno.inicio &&
    fin === turno.fin &&
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
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Campo etiqueta="Fecha" htmlFor="et-fecha">
              <Input
                id="et-fecha"
                type="date"
                value={fecha}
                onChange={(e) => setFecha(e.target.value)}
              />
            </Campo>
            <Campo etiqueta="Franja">
              <Select value={franjaId} onValueChange={setFranjaId}>
                <SelectTrigger aria-label="Franja">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[...franjas]
                    .sort((a, b) => a.orden - b.orden)
                    .map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.nombre}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            </Campo>
          </div>
          <Campo etiqueta="Horario">
            <div className="flex items-center gap-2">
              <Input
                value={inicio}
                onChange={(e) => setInicio(e.target.value)}
                placeholder="08:00"
                className="w-28 tabular-nums"
                aria-label="Hora de inicio"
              />
              <span className="text-muted-foreground">–</span>
              <Input
                value={fin}
                onChange={(e) => setFin(e.target.value)}
                placeholder="16:00"
                className="w-28 tabular-nums"
                aria-label="Hora de fin"
              />
              <span className="text-xs text-muted-foreground">
                {turno.horario_propio ? "a medida" : "de la franja"}
              </span>
            </div>
          </Campo>
          <Campo etiqueta="Persona">
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
          </Campo>
          <Campo etiqueta="Motivo" htmlFor="et-motivo">
            <Input
              id="et-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Opcional: cobertura forzada por evento crítico"
              maxLength={200}
            />
          </Campo>
          <Campo etiqueta="Nota de relevo" htmlFor="et-nota">
            <Textarea
              id="et-nota"
              value={notaRelevo}
              onChange={(e) => setNotaRelevo(e.target.value)}
              placeholder="Opcional: qué queda pendiente para el siguiente turno"
              rows={3}
              maxLength={1000}
            />
          </Campo>
          {pendienteOverride && (
            <Aviso>
              <p className="font-medium">{pendienteOverride.mensaje}</p>
              <p className="mt-1">Confirma solo si es una cobertura estratégica intencional.</p>
            </Aviso>
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
              {guardar.isPending && <Spinner className="h-4 w-4" />}
              <AlertTriangle className="h-4 w-4" /> Forzar override
            </Button>
          ) : (
            <Button variant="default" onClick={() => guardar.mutate(false)} disabled={sinCambios || guardar.isPending}>
              {guardar.isPending && <Spinner className="h-4 w-4" />}
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
