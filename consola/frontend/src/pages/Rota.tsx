import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  CalendarPlus,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Plus,
  Sparkles,
  Trash2,
  User,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type { EventoRota, MiembroRota, TurnoRota } from "@/types";

const CABECERA = {
  titulo: "Parrilla y rota",
  descripcion:
    "Eventos y transmisiones de la semana + la rota del equipo. Keni propone (rota los sábados sin repetir a la misma persona dos seguidos); tú ajustas y apruebas antes de publicarla al equipo.",
};

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

// --- Utilidades de fechas (semana lunes->domingo) --------------------------

/** Lunes (ISO AAAA-MM-DD) de la semana que contiene `d`. */
function lunesDeSemana(d: Date): string {
  const copia = new Date(d);
  const dia = (copia.getDay() + 6) % 7; // lunes=0 ... domingo=6
  copia.setDate(copia.getDate() - dia);
  return iso(copia);
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

function lunesSiguiente(lunesIso: string, semanas: number): string {
  const d = new Date(`${lunesIso}T00:00:00`);
  d.setDate(d.getDate() + semanas * 7);
  return lunesDeSemana(d);
}

function formatearRango(inicio: string, fin: string): string {
  if (!inicio || !fin) return "";
  const fmt = (s: string) =>
    new Date(`${s}T00:00:00`).toLocaleDateString("es-MX", { day: "numeric", month: "short" });
  return `${fmt(inicio)} – ${fmt(fin)}`;
}

function formatearFechaCorta(s: string): string {
  if (!s) return "";
  const d = new Date(`${s}T00:00:00`);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("es-MX", { weekday: "short", day: "numeric", month: "short" });
}

// ===========================================================================

export default function Rota() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  // Por defecto: la próxima semana (la que más le importa al equipo, B4).
  const [lunes, setLunes] = React.useState(() => lunesSiguiente(lunesDeSemana(new Date()), 1));

  return (
    <>
      <PageHeader {...CABECERA} />
      <Tabs defaultValue="parrilla" className="space-y-4">
        <TabsList>
          <TabsTrigger value="parrilla">Parrilla del equipo</TabsTrigger>
          <TabsTrigger value="mi-semana">Mi próxima semana</TabsTrigger>
          <TabsTrigger value="eventos">Eventos</TabsTrigger>
        </TabsList>

        <TabsContent value="parrilla">
          <Parrilla lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="mi-semana">
          <MiSemana lunes={lunes} setLunes={setLunes} />
        </TabsContent>
        <TabsContent value="eventos">
          <Eventos />
        </TabsContent>
      </Tabs>
    </>
  );
}

// --- Navegador de semana ---------------------------------------------------

function NavegadorSemana({
  lunes,
  setLunes,
  inicio,
  fin,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  inicio: string;
  fin: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <Button
        variant="outline"
        size="icon"
        aria-label="Semana anterior"
        onClick={() => setLunes(lunesSiguiente(lunes, -1))}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      <div className="min-w-[12rem] text-center text-sm font-medium">
        <CalendarDays className="mr-1.5 inline h-4 w-4 text-muted-foreground" />
        {formatearRango(inicio, fin) || "Semana"}
      </div>
      <Button
        variant="outline"
        size="icon"
        aria-label="Semana siguiente"
        onClick={() => setLunes(lunesSiguiente(lunes, 1))}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

// --- Pestaña: parrilla del equipo ------------------------------------------

function Parrilla({
  lunes,
  setLunes,
  esAdmin,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const claveSemana = ["rota", "semana", lunes] as const;

  const semanaQ = useQuery({
    queryKey: claveSemana,
    queryFn: ({ signal }) => api.rotaSemana({ lunes }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });

  const equipo = equipoQ.data?.equipo ?? [];
  const semana = semanaQ.data;
  const turnos = semana?.turnos ?? [];

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: claveSemana });

  const proponer = useMutation({
    mutationFn: () => api.proponerRota({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveSemana, res);
      const avisos = res.avisos ?? [];
      if (avisos.length > 0) avisos.forEach((a) => toast.warning(a));
      else toast.success("Rota propuesta. Revísala y apruébala antes de publicarla.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aprobar = useMutation({
    mutationFn: () => api.aprobarRota({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveSemana, res);
      toast.success(res.mensaje ?? "Rota publicada al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana
          lunes={lunes}
          setLunes={setLunes}
          inicio={semana?.inicio ?? ""}
          fin={semana?.fin ?? ""}
        />
        <div className="flex flex-wrap items-center gap-2">
          {semana?.aprobada ? (
            <Badge variant="ok" className="font-normal">
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Publicada
            </Badge>
          ) : turnos.length > 0 ? (
            <Badge variant="aviso" className="font-normal">
              Propuesta (sin publicar)
            </Badge>
          ) : null}
          <Button onClick={() => proponer.mutate()} disabled={proponer.isPending}>
            {proponer.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            Proponer rota
          </Button>
          {esAdmin && (
            <Button
              variant="secondary"
              onClick={() => aprobar.mutate()}
              disabled={aprobar.isPending || turnos.length === 0 || semana?.aprobada}
            >
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              Aprobar y publicar
            </Button>
          )}
          <Button variant="outline" onClick={() => api.exportarRota("xlsx", { lunes })}>
            <Download className="h-4 w-4" /> Excel
          </Button>
          <Button variant="outline" onClick={() => api.exportarRota("csv", { lunes })}>
            <Download className="h-4 w-4" /> CSV
          </Button>
        </div>
      </div>

      {semanaQ.isPending ? (
        <Skeleton className="h-48 w-full rounded-md" />
      ) : semanaQ.isError ? (
        <BloqueError
          titulo="No se pudo cargar la rota"
          mensaje={mensajeError(semanaQ.error)}
          onReintentar={() => void semanaQ.refetch()}
          cargando={semanaQ.isFetching}
        />
      ) : turnos.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin rota para esta semana"
          texto='Da de alta los eventos de la semana en la pestaña "Eventos" y pulsa "Proponer rota".'
        />
      ) : (
        <TablaTurnos
          turnos={turnos}
          equipo={equipo}
          editable={!semana?.aprobada}
          onCambio={invalidar}
        />
      )}
    </div>
  );
}

function TablaTurnos({
  turnos,
  equipo,
  editable,
  onCambio,
}: {
  turnos: TurnoRota[];
  equipo: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
}) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Día / hora</TableHead>
              <TableHead>Evento / transmisión</TableHead>
              <TableHead>Qué sacar</TableHead>
              <TableHead className="w-[14rem]">Persona</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {turnos.map((t) => (
              <FilaTurno
                key={t.id}
                turno={t}
                equipo={equipo}
                editable={editable}
                onCambio={onCambio}
              />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function FilaTurno({
  turno,
  equipo,
  editable,
  onCambio,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
}) {
  // Confirmación de override pendiente: si el backend pide override, lo reintenta.
  const [pendienteOverride, setPendienteOverride] = React.useState<string | null>(null);

  const actualizar = useMutation({
    mutationFn: (cuerpo: { miembro_id?: string; override?: boolean }) =>
      api.actualizarTurnoRota(turno.id, cuerpo),
    onSuccess: () => {
      setPendienteOverride(null);
      onCambio();
    },
    onError: (e, variables) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        typeof variables.miembro_id === "string"
      ) {
        // Repite el sábado anterior: ofrecemos forzar la cobertura (override).
        setPendienteOverride(variables.miembro_id);
        toast.warning(mensajeError(e));
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  return (
    <TableRow className={turno.es_sabado ? "bg-amber-50/40 dark:bg-amber-950/10" : undefined}>
      <TableCell className="whitespace-nowrap align-top">
        <div className="font-medium">{formatearFechaCorta(turno.evento_fecha)}</div>
        <div className="text-xs text-muted-foreground">{turno.evento_hora}</div>
        {turno.es_sabado && (
          <Badge variant="outline" className="mt-1 font-normal">
            Sábado
          </Badge>
        )}
      </TableCell>
      <TableCell className="align-top">
        <div className="font-medium">{turno.evento_titulo}</div>
        {turno.override && (
          <Badge variant="aviso" className="mt-1 font-normal">
            <AlertTriangle className="mr-1 h-3 w-3" /> Override
          </Badge>
        )}
        {turno.motivo && (
          <div className="mt-0.5 text-xs text-muted-foreground">{turno.motivo}</div>
        )}
      </TableCell>
      <TableCell className="align-top text-sm text-muted-foreground">
        {turno.contenido || "—"}
      </TableCell>
      <TableCell className="align-top">
        {editable ? (
          <div className="space-y-1.5">
            <Select
              value={turno.miembro_id || ""}
              onValueChange={(v) => actualizar.mutate({ miembro_id: v })}
              disabled={actualizar.isPending}
            >
              <SelectTrigger aria-label="Asignar persona">
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
            {pendienteOverride && (
              <Button
                size="sm"
                variant="outline"
                className="w-full text-amber-700 dark:text-amber-400"
                onClick={() =>
                  actualizar.mutate({ miembro_id: pendienteOverride, override: true })
                }
                disabled={actualizar.isPending}
              >
                <AlertTriangle className="h-3.5 w-3.5" /> Forzar cobertura (override)
              </Button>
            )}
          </div>
        ) : (
          <span className="text-sm">{turno.miembro_nombre || "Sin asignar"}</span>
        )}
      </TableCell>
    </TableRow>
  );
}

// --- Pestaña: mi próxima semana --------------------------------------------

function MiSemana({ lunes, setLunes }: { lunes: string; setLunes: (l: string) => void }) {
  const q = useQuery({
    queryKey: ["rota", "mi-semana", lunes],
    queryFn: ({ signal }) => api.miSemanaRota({ lunes }, signal),
  });
  const datos = q.data;
  const mios = datos?.mis_turnos ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana
          lunes={lunes}
          setLunes={setLunes}
          inicio={datos?.inicio ?? ""}
          fin={datos?.fin ?? ""}
        />
        {datos?.miembro_nombre && (
          <Badge variant="secondary" className="font-normal">
            <User className="mr-1 h-3.5 w-3.5" /> {datos.miembro_nombre}
          </Badge>
        )}
      </div>

      {q.isPending ? (
        <Skeleton className="h-40 w-full rounded-md" />
      ) : q.isError ? (
        <BloqueError
          titulo="No se pudo cargar tu semana"
          mensaje={mensajeError(q.error)}
          onReintentar={() => void q.refetch()}
          cargando={q.isFetching}
        />
      ) : datos?.aviso ? (
        <EstadoVacio icono={User} titulo="Inicia sesión" texto={datos.aviso} />
      ) : !datos?.aprobada && mios.length > 0 ? (
        <>
          <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
            Esta rota aún es una propuesta sin publicar; puede cambiar antes de que Elías la
            apruebe.
          </p>
          <ListaMisTurnos turnos={mios} />
        </>
      ) : mios.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin turnos esta semana"
          texto="No tienes asignaciones en la rota de esta semana."
        />
      ) : (
        <ListaMisTurnos turnos={mios} />
      )}
    </div>
  );
}

function ListaMisTurnos({ turnos }: { turnos: TurnoRota[] }) {
  return (
    <div className="space-y-3">
      {turnos.map((t) => (
        <Card key={t.id}>
          <CardContent className="space-y-1.5 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{t.evento_titulo}</span>
              {t.es_sabado && (
                <Badge variant="outline" className="font-normal">
                  Sábado
                </Badge>
              )}
              {t.override && (
                <Badge variant="aviso" className="font-normal">
                  Override
                </Badge>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              {formatearFechaCorta(t.evento_fecha)} · {t.evento_hora}
            </div>
            {t.contenido && (
              <div className="text-sm">
                <span className="text-muted-foreground">Qué sacar: </span>
                {t.contenido}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// --- Pestaña: eventos / transmisiones --------------------------------------

function Eventos() {
  const queryClient = useQueryClient();
  const clave = ["rota", "eventos"] as const;
  const q = useQuery({ queryKey: clave, queryFn: ({ signal }) => api.rotaEventos({}, signal) });
  const eventos = q.data?.eventos ?? [];
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  return (
    <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
      <NuevoEvento onCreado={invalidar} />
      <div className="space-y-3">
        {q.isPending ? (
          <Skeleton className="h-40 w-full rounded-md" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudieron cargar los eventos"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : eventos.length === 0 ? (
          <EstadoVacio
            icono={CalendarPlus}
            titulo="Sin eventos"
            texto="Da de alta los partidos y transmisiones de la semana con el formulario."
          />
        ) : (
          eventos.map((e) => <TarjetaEvento key={e.id} evento={e} onCambio={invalidar} />)
        )}
      </div>
    </div>
  );
}

function NuevoEvento({ onCreado }: { onCreado: () => void }) {
  const [titulo, setTitulo] = React.useState("");
  const [fecha, setFecha] = React.useState("");
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearEventoRota({
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        contenido: contenido.trim(),
      }),
    onSuccess: () => {
      toast.success("Evento creado.");
      setTitulo("");
      setHora("");
      setContenido("");
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = titulo.trim().length > 0 && fecha !== "" && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarPlus className="h-4 w-4" /> Nuevo evento
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="ev-titulo">Evento / transmisión</Label>
          <Input
            id="ev-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ej. Cruz Azul vs América"
            maxLength={200}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="ev-fecha">Fecha</Label>
            <Input id="ev-fecha" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-hora">Hora</Label>
            <Input
              id="ev-hora"
              value={hora}
              onChange={(e) => setHora(e.target.value)}
              placeholder="16:00"
              maxLength={40}
            />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="ev-contenido">
            Qué sacar <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="ev-contenido"
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            placeholder="Clip del gol, resumen 1 min, frase del DT…"
            rows={3}
            maxLength={2000}
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear evento
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TarjetaEvento({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{evento.titulo}</span>
            {evento.es_sabado && (
              <Badge variant="outline" className="font-normal">
                Sábado
              </Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatearFechaCorta(evento.fecha)}
            {evento.hora ? ` · ${evento.hora}` : ""}
          </div>
          {evento.contenido && (
            <div className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Qué sacar: </span>
              {evento.contenido}
            </div>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar evento"
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
      </CardContent>
    </Card>
  );
}
