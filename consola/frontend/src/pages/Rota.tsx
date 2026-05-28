import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CalendarDays,
  CalendarOff,
  CalendarPlus,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  Plane,
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
import type {
  AusenciaRota,
  EventoRota,
  FranjaTurno,
  HorarioSemana,
  MiembroRota,
  TipoAusencia,
  TurnoRota,
  TurnoTrabajoRota,
} from "@/types";

const CABECERA = {
  titulo: "Parrilla y rota",
  descripcion:
    "Eventos de la semana, rota de cobertura y horarios/turnos del equipo (mañana/tarde/descanso, con vacaciones y ausencias). Keni propone (rota los sábados sin repetir a la misma persona dos seguidos); tú ajustas y apruebas antes de publicar al equipo.",
};

// Etiquetas legibles de cada franja del turno de trabajo.
const ETIQUETA_FRANJA: Record<FranjaTurno, string> = {
  matutino: "Mañana",
  vespertino: "Tarde",
  descanso: "Descanso",
};

const TIPOS_AUSENCIA: { valor: TipoAusencia; etiqueta: string }[] = [
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "descanso", etiqueta: "Descanso" },
  { valor: "baja", etiqueta: "Baja" },
  { valor: "otro", etiqueta: "Otro" },
];

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
          <TabsTrigger value="horario">Horario del equipo</TabsTrigger>
          <TabsTrigger value="mi-semana">Mi próxima semana</TabsTrigger>
          <TabsTrigger value="ausencias">Ausencias</TabsTrigger>
          <TabsTrigger value="eventos">Eventos</TabsTrigger>
        </TabsList>

        <TabsContent value="parrilla">
          <Parrilla lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="horario">
          <Horario lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="mi-semana">
          <MiSemana lunes={lunes} setLunes={setLunes} />
        </TabsContent>
        <TabsContent value="ausencias">
          <Ausencias />
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
  const hq = useQuery({
    queryKey: ["rota", "mi-horario", lunes],
    queryFn: ({ signal }) => api.miHorarioRota({ lunes }, signal),
  });
  const datos = q.data;
  const mios = datos?.mis_turnos ?? [];
  const horario = hq.data;
  const misTurnosTrabajo = horario?.mis_turnos ?? [];

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

      {/* Mi horario de trabajo (turnos mañana/tarde/descanso) */}
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Mi horario de trabajo</h3>
        {hq.isPending ? (
          <Skeleton className="h-24 w-full rounded-md" />
        ) : hq.isError ? (
          <BloqueError
            titulo="No se pudo cargar tu horario"
            mensaje={mensajeError(hq.error)}
            onReintentar={() => void hq.refetch()}
            cargando={hq.isFetching}
          />
        ) : horario?.aviso ? (
          <EstadoVacio icono={User} titulo="Inicia sesión" texto={horario.aviso} />
        ) : misTurnosTrabajo.length === 0 ? (
          <EstadoVacio
            icono={CalendarDays}
            titulo="Sin horario esta semana"
            texto="No tienes turnos de trabajo asignados esta semana."
          />
        ) : (
          <>
            {!horario?.aprobada && (
              <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
                Este horario aún es una propuesta sin publicar; puede cambiar antes de que
                Elías lo apruebe.
              </p>
            )}
            <ListaMisTurnosTrabajo turnos={misTurnosTrabajo} />
          </>
        )}
      </section>

      {/* Mi cobertura de eventos */}
      <section className="space-y-2">
        <h3 className="text-sm font-semibold text-muted-foreground">Mi cobertura de eventos</h3>
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
        ) : mios.length === 0 ? (
          <EstadoVacio
            icono={CalendarDays}
            titulo="Sin eventos esta semana"
            texto="No tienes eventos asignados en la rota de cobertura."
          />
        ) : (
          <>
            {!datos?.aprobada && (
              <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
                Esta rota aún es una propuesta sin publicar; puede cambiar antes de que Elías
                la apruebe.
              </p>
            )}
            <ListaMisTurnos turnos={mios} />
          </>
        )}
      </section>
    </div>
  );
}

function ListaMisTurnosTrabajo({ turnos }: { turnos: TurnoTrabajoRota[] }) {
  return (
    <div className="space-y-3">
      {turnos.map((t) => (
        <Card key={t.id}>
          <CardContent className="space-y-1.5 p-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium">{ETIQUETA_FRANJA[t.franja]}</span>
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
            <div className="text-sm text-muted-foreground">{formatearFechaCorta(t.fecha)}</div>
            {t.nota_relevo && (
              <div className="rounded-md bg-muted/50 px-2.5 py-1.5 text-sm">
                <span className="font-medium">Relevo: </span>
                {t.nota_relevo}
              </div>
            )}
          </CardContent>
        </Card>
      ))}
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

// --- Pestaña: horario del equipo (turnos de trabajo) -----------------------

/** Nombre corto del día (Lun..Dom) de una fecha ISO. */
function diaCorto(fechaIso: string): string {
  const d = new Date(`${fechaIso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { weekday: "short" });
}

/** ¿La fecha ISO cae en sábado o domingo? (para resaltar el fin de semana). */
function esFinDeSemana(fechaIso: string): boolean {
  const d = new Date(`${fechaIso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return false;
  const dia = d.getDay();
  return dia === 0 || dia === 6;
}

function Horario({
  lunes,
  setLunes,
  esAdmin,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const claveHorario = ["rota", "horario", lunes] as const;

  const horarioQ = useQuery({
    queryKey: claveHorario,
    queryFn: ({ signal }) => api.rotaHorario({ lunes }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });

  const equipo = equipoQ.data?.equipo ?? [];
  const ausencias = ausenciasQ.data?.ausencias ?? [];
  const horario = horarioQ.data;
  const turnos = horario?.turnos ?? [];

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: claveHorario });

  const proponer = useMutation({
    mutationFn: () => api.proponerHorario({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveHorario, res);
      const avisos = res.avisos ?? [];
      if (avisos.length > 0) avisos.forEach((a) => toast.warning(a));
      else toast.success("Horario propuesto. Revísalo y apruébalo antes de publicarlo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aprobar = useMutation({
    mutationFn: () => api.aprobarHorario({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveHorario, res);
      toast.success(res.mensaje ?? "Horario publicado al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana
          lunes={lunes}
          setLunes={setLunes}
          inicio={horario?.inicio ?? ""}
          fin={horario?.fin ?? ""}
        />
        <div className="flex flex-wrap items-center gap-2">
          {horario?.aprobada ? (
            <Badge variant="ok" className="font-normal">
              <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Publicado
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
            Proponer horario
          </Button>
          {esAdmin && (
            <Button
              variant="secondary"
              onClick={() => aprobar.mutate()}
              disabled={aprobar.isPending || turnos.length === 0 || horario?.aprobada}
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
        </div>
      </div>

      {horarioQ.isPending ? (
        <Skeleton className="h-48 w-full rounded-md" />
      ) : horarioQ.isError ? (
        <BloqueError
          titulo="No se pudo cargar el horario"
          mensaje={mensajeError(horarioQ.error)}
          onReintentar={() => void horarioQ.refetch()}
          cargando={horarioQ.isFetching}
        />
      ) : turnos.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin horario para esta semana"
          texto='Pulsa "Proponer horario": Keni reparte mañana/tarde/descanso respetando vacaciones y rotando los sábados.'
        />
      ) : (
        <RejillaHorario
          horario={horario as HorarioSemana}
          equipo={equipo}
          ausencias={ausencias}
          editable={!horario?.aprobada}
          onCambio={invalidar}
        />
      )}
    </div>
  );
}

function RejillaHorario({
  horario,
  equipo,
  ausencias,
  editable,
  onCambio,
}: {
  horario: HorarioSemana;
  equipo: MiembroRota[];
  ausencias: AusenciaRota[];
  editable: boolean;
  onCambio: () => void;
}) {
  const dias = horario.dias;
  // Indexa el turno por (miembro, fecha) para llenar la rejilla.
  const porCelda = new Map<string, TurnoTrabajoRota>();
  for (const t of horario.turnos) porCelda.set(`${t.miembro_id}|${t.fecha}`, t);

  // ¿Tiene el miembro una ausencia que cubra esa fecha?
  const estaAusente = (miembroId: string, fecha: string): AusenciaRota | undefined =>
    ausencias.find((a) => a.miembro_id === miembroId && a.desde <= fecha && fecha <= a.hasta);

  const filas = [...equipo].sort((a, b) => a.nombre.localeCompare(b.nombre));

  return (
    <Card>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="sticky left-0 bg-background">Persona</TableHead>
              {dias.map((fecha) => (
                <TableHead
                  key={fecha}
                  className={esFinDeSemana(fecha) ? "bg-amber-50/40 dark:bg-amber-950/10" : undefined}
                >
                  <div className="capitalize">{diaCorto(fecha)}</div>
                  <div className="text-xs font-normal text-muted-foreground">
                    {fecha.slice(8, 10)}
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="sticky left-0 whitespace-nowrap bg-background font-medium">
                  {m.nombre}
                </TableCell>
                {dias.map((fecha) => {
                  const ausencia = estaAusente(m.id, fecha);
                  const turno = porCelda.get(`${m.id}|${fecha}`);
                  return (
                    <TableCell
                      key={fecha}
                      className={esFinDeSemana(fecha) ? "bg-amber-50/30 dark:bg-amber-950/10" : undefined}
                    >
                      {ausencia ? (
                        <Badge variant="secondary" className="font-normal">
                          <Plane className="mr-1 h-3 w-3" />
                          {TIPOS_AUSENCIA.find((t) => t.valor === ausencia.tipo)?.etiqueta ??
                            "Ausente"}
                        </Badge>
                      ) : turno ? (
                        <CeldaTurno turno={turno} editable={editable} onCambio={onCambio} />
                      ) : (
                        <span className="text-sm text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CeldaTurno({
  turno,
  editable,
  onCambio,
}: {
  turno: TurnoTrabajoRota;
  editable: boolean;
  onCambio: () => void;
}) {
  // Confirmación de override pendiente: si el backend pide override, lo reintenta.
  const [pendienteOverride, setPendienteOverride] = React.useState<FranjaTurno | null>(null);

  const actualizar = useMutation({
    mutationFn: (cuerpo: { franja?: FranjaTurno; override?: boolean }) =>
      api.actualizarTurnoTrabajoRota(turno.id, cuerpo),
    onSuccess: () => {
      setPendienteOverride(null);
      onCambio();
    },
    onError: (e, variables) => {
      if (e instanceof ApiError && e.status === 409 && variables.franja) {
        // Repite el sábado de trabajo anterior: ofrecemos forzar la cobertura (override).
        setPendienteOverride(variables.franja);
        toast.warning(mensajeError(e));
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  if (!editable) {
    return (
      <div className="flex items-center gap-1.5">
        <span className="text-sm">{ETIQUETA_FRANJA[turno.franja]}</span>
        {turno.override && <AlertTriangle className="h-3 w-3 text-amber-600" />}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <Select
        value={turno.franja}
        onValueChange={(v) => actualizar.mutate({ franja: v as FranjaTurno })}
        disabled={actualizar.isPending}
      >
        <SelectTrigger aria-label={`Franja de ${turno.miembro_nombre}`} className="min-w-[7.5rem]">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="matutino">Mañana</SelectItem>
          <SelectItem value="vespertino">Tarde</SelectItem>
          <SelectItem value="descanso">Descanso</SelectItem>
        </SelectContent>
      </Select>
      {turno.override && (
        <Badge variant="aviso" className="font-normal">
          <AlertTriangle className="mr-1 h-3 w-3" /> Override
        </Badge>
      )}
      {pendienteOverride && (
        <Button
          size="sm"
          variant="outline"
          className="w-full text-amber-700 dark:text-amber-400"
          onClick={() => actualizar.mutate({ franja: pendienteOverride, override: true })}
          disabled={actualizar.isPending}
        >
          <AlertTriangle className="h-3.5 w-3.5" /> Forzar cobertura (override)
        </Button>
      )}
    </div>
  );
}

// --- Pestaña: ausencias / vacaciones ---------------------------------------

function Ausencias() {
  const queryClient = useQueryClient();
  const clave = ["rota", "ausencias"] as const;
  const q = useQuery({ queryKey: clave, queryFn: ({ signal }) => api.rotaAusencias({}, signal) });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const ausencias = q.data?.ausencias ?? [];
  const equipo = equipoQ.data?.equipo ?? [];
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });

  return (
    <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
      <NuevaAusencia equipo={equipo} onCreada={invalidar} />
      <div className="space-y-3">
        {q.isPending ? (
          <Skeleton className="h-40 w-full rounded-md" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudieron cargar las ausencias"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : ausencias.length === 0 ? (
          <EstadoVacio
            icono={CalendarOff}
            titulo="Sin ausencias"
            texto="Registra vacaciones, descansos o bajas para que el horario propuesto las respete."
          />
        ) : (
          ausencias.map((a) => <TarjetaAusencia key={a.id} ausencia={a} onCambio={invalidar} />)
        )}
      </div>
    </div>
  );
}

function NuevaAusencia({
  equipo,
  onCreada,
}: {
  equipo: MiembroRota[];
  onCreada: () => void;
}) {
  const [miembroId, setMiembroId] = React.useState("");
  const [tipo, setTipo] = React.useState<TipoAusencia>("vacaciones");
  const [desde, setDesde] = React.useState("");
  const [hasta, setHasta] = React.useState("");
  const [motivo, setMotivo] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearAusenciaRota({ miembro_id: miembroId, tipo, desde, hasta, motivo: motivo.trim() }),
    onSuccess: () => {
      toast.success("Ausencia registrada.");
      setDesde("");
      setHasta("");
      setMotivo("");
      onCreada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = miembroId !== "" && desde !== "" && hasta !== "" && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarOff className="h-4 w-4" /> Nueva ausencia
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label>Persona</Label>
          <Select value={miembroId} onValueChange={setMiembroId}>
            <SelectTrigger aria-label="Persona">
              <SelectValue placeholder="Elige a un miembro" />
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
          <Label>Tipo</Label>
          <Select value={tipo} onValueChange={(v) => setTipo(v as TipoAusencia)}>
            <SelectTrigger aria-label="Tipo de ausencia">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TIPOS_AUSENCIA.map((t) => (
                <SelectItem key={t.valor} value={t.valor}>
                  {t.etiqueta}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="au-desde">Desde</Label>
            <Input id="au-desde" type="date" value={desde} onChange={(e) => setDesde(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="au-hasta">Hasta</Label>
            <Input id="au-hasta" type="date" value={hasta} onChange={(e) => setHasta(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="au-motivo">
            Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="au-motivo"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej. Vacaciones de verano"
            maxLength={200}
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Registrar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TarjetaAusencia({
  ausencia,
  onCambio,
}: {
  ausencia: AusenciaRota;
  onCambio: () => void;
}) {
  const borrar = useMutation({
    mutationFn: () => api.eliminarAusenciaRota(ausencia.id),
    onSuccess: () => {
      toast.success("Ausencia eliminada.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetaTipo =
    TIPOS_AUSENCIA.find((t) => t.valor === ausencia.tipo)?.etiqueta ?? ausencia.tipo;

  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{ausencia.miembro_nombre || "—"}</span>
            <Badge variant="secondary" className="font-normal">
              {etiquetaTipo}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground">
            {formatearRango(ausencia.desde, ausencia.hasta)}
          </div>
          {ausencia.motivo && (
            <div className="text-sm text-muted-foreground">{ausencia.motivo}</div>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar ausencia"
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
