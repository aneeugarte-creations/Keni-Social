import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeftRight,
  BellRing,
  CalendarDays,
  CalendarOff,
  CalendarPlus,
  Camera,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  Coffee,
  Copy,
  Download,
  HeartPulse,
  ImageIcon,
  Loader2,
  MessageSquare,
  Pencil,
  Plane,
  Plus,
  Radio,
  Search,
  Send,
  Shield,
  ShieldCheck,
  Trash2,
  User,
  UserMinus,
  Users,
  Wand2,
  X,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type {
  AusenciaRota,
  CuerpoActualizarPiezaRota,
  CuerpoActualizarProgramaRota,
  CuerpoCrearPiezaRota,
  CuerpoCrearProgramaRota,
  EstadoPieza,
  EstadoSwap,
  EventoRota,
  FiltrosSwaps,
  FranjaCobertura,
  FranjaTurno,
  HorarioSemana,
  MiembroRota,
  PiezaRota,
  PrioridadEvento,
  ProgramaRota,
  SwapTurno,
  TipoAusencia,
  TipoCoberturaEvento,
  TurnoRota,
  TurnoTrabajoRota,
} from "@/types";

const CABECERA = {
  titulo: "Parrilla y rota",
  descripcion:
    "Calendario de eventos (con su tipo de cobertura: transmisión, solo imágenes o no cubrir) y reprogramaciones marcadas, rota de cobertura y horarios/turnos del equipo. Tú decides qué cubre cada quien; la consola te muestra huecos, repite sábados y carga por persona, y tú apruebas antes de publicar al equipo.",
};

// Etiquetas legibles de cada franja del turno de trabajo.
const ETIQUETA_FRANJA: Record<FranjaTurno, string> = {
  matutino: "Mañana",
  vespertino: "Tarde",
  descanso: "Descanso",
};

// Presentación de cada tipo de cobertura: etiqueta, icono y clases de color (chips/leyenda).
// Tropicalización MX y consistente con la voz del producto (Elías decide qué se cubre).
const COBERTURA: Record<
  TipoCoberturaEvento,
  { etiqueta: string; icono: typeof Radio; chip: string; punto: string }
> = {
  transmision: {
    etiqueta: "Transmisión",
    icono: Radio,
    chip: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300",
    punto: "bg-sky-500",
  },
  imagenes: {
    etiqueta: "Solo imágenes",
    icono: Camera,
    chip: "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-800 dark:bg-violet-950/40 dark:text-violet-300",
    punto: "bg-violet-500",
  },
  no_cubrir: {
    etiqueta: "No cubrir",
    icono: CalendarOff,
    chip: "border-zinc-300 bg-zinc-100 text-zinc-600 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-400",
    punto: "bg-zinc-400",
  },
};

const TIPOS_COBERTURA: { valor: TipoCoberturaEvento; etiqueta: string }[] = [
  { valor: "transmision", etiqueta: "Transmisión (con señal)" },
  { valor: "imagenes", etiqueta: "Solo imágenes / fotografías" },
  { valor: "no_cubrir", etiqueta: "No cubrir" },
];

const PRIORIDADES: { valor: PrioridadEvento; etiqueta: string }[] = [
  { valor: "alta", etiqueta: "Alta" },
  { valor: "media", etiqueta: "Media" },
  { valor: "baja", etiqueta: "Baja" },
];

// Color del texto de la prioridad (sutil; la alta resalta).
const COLOR_PRIORIDAD: Record<PrioridadEvento, string> = {
  alta: "text-red-600 dark:text-red-400",
  media: "text-muted-foreground",
  baja: "text-muted-foreground",
};

const TIPOS_AUSENCIA: { valor: TipoAusencia; etiqueta: string }[] = [
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "descanso", etiqueta: "Descanso" },
  { valor: "baja", etiqueta: "Baja" },
  { valor: "otro", etiqueta: "Otro" },
];

// Estados del workflow de produccion de UNA pieza (#150 PARRILLA 2026.xlsx). Mismo orden
// que el ciclo de vida: pendiente -> en_curso -> listo -> publicado.
const ESTADOS_PIEZA: { valor: EstadoPieza; etiqueta: string }[] = [
  { valor: "pendiente", etiqueta: "Pendiente" },
  { valor: "en_curso", etiqueta: "En curso" },
  { valor: "listo", etiqueta: "Listo" },
  { valor: "publicado", etiqueta: "Publicado" },
];

// Presentación de cada tipo de ausencia en la banda del calendario: icono + clases.
// Colores suaves consistentes con el chip-style usado por la cobertura (no robar atención).
const PRESENTACION_AUSENCIA: Record<
  TipoAusencia,
  { etiqueta: string; icono: typeof Plane; chip: string }
> = {
  vacaciones: {
    etiqueta: "Vacaciones",
    icono: Plane,
    chip: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300",
  },
  descanso: {
    etiqueta: "Descanso",
    icono: Coffee,
    chip: "border-zinc-300 bg-zinc-100 text-zinc-700 dark:border-zinc-700 dark:bg-zinc-900/60 dark:text-zinc-300",
  },
  baja: {
    etiqueta: "Baja",
    icono: HeartPulse,
    chip: "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-300",
  },
  otro: {
    etiqueta: "Otro",
    icono: User,
    chip: "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-800 dark:bg-blue-950/40 dark:text-blue-300",
  },
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
  // Pestaña activa (controlada) para que el catálogo de programas sea linkable
  // desde otras pestañas (PiezasSueltas → "Gestionar programas →").
  const [pestania, setPestania] = React.useState("calendario");

  return (
    <>
      <PageHeader {...CABECERA} />
      <Tabs value={pestania} onValueChange={setPestania} className="space-y-4">
        <TabsList>
          <TabsTrigger value="calendario">Calendario</TabsTrigger>
          <TabsTrigger value="parrilla">Parrilla del equipo</TabsTrigger>
          <TabsTrigger value="horario">Horario del equipo</TabsTrigger>
          <TabsTrigger value="mi-semana">Mi próxima semana</TabsTrigger>
          <TabsTrigger value="swaps">Cambios de turno</TabsTrigger>
          <TabsTrigger value="ausencias">Ausencias</TabsTrigger>
          <TabsTrigger value="eventos">Eventos</TabsTrigger>
          <TabsTrigger value="programas">Programas</TabsTrigger>
        </TabsList>

        <TabsContent value="calendario">
          <Calendario lunes={lunes} setLunes={setLunes} />
        </TabsContent>
        <TabsContent value="parrilla">
          <Parrilla lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="horario">
          <Horario lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="mi-semana">
          <MiSemana lunes={lunes} setLunes={setLunes} />
        </TabsContent>
        <TabsContent value="swaps">
          <Swaps esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="ausencias">
          <Ausencias />
        </TabsContent>
        <TabsContent value="eventos">
          <Eventos onIrAProgramas={() => setPestania("programas")} />
        </TabsContent>
        <TabsContent value="programas">
          <Programas />
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

// --- Pestaña: calendario de eventos (semana, color por cobertura) ----------

/** Leyenda de colores por tipo de cobertura (consistente con los chips del calendario). */
function LeyendaCobertura() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      {(Object.keys(COBERTURA) as TipoCoberturaEvento[]).map((tc) => (
        <span key={tc} className="inline-flex items-center gap-1.5">
          <span className={`h-2.5 w-2.5 rounded-full ${COBERTURA[tc].punto}`} />
          {COBERTURA[tc].etiqueta}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <BellRing className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" /> Cambió
        (reprogramado, falta avisar)
      </span>
    </div>
  );
}

/** Botón "marcar avisado": limpia el flag `cambiado` de un evento (PATCH cambiado:false). */
function BotonMarcarAvisado({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const marcar = useMutation({
    mutationFn: () => api.actualizarEventoRota(evento.id, { cambiado: false }),
    onSuccess: () => {
      toast.success("Marcado como avisado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-6 gap-1 px-1.5 text-[11px] text-amber-700 dark:text-amber-400"
      onClick={() => marcar.mutate()}
      disabled={marcar.isPending}
    >
      {marcar.isPending ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <CheckCircle2 className="h-3 w-3" />
      )}
      Marcar avisado
    </Button>
  );
}

/** Un chip de evento dentro de una celda del calendario, color por tipo de cobertura. */
function ChipEvento({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const cob = COBERTURA[evento.tipo_cobertura] ?? COBERTURA.transmision;
  const Icono = cob.icono;
  return (
    <div className={`space-y-1 rounded-md border px-2 py-1.5 text-xs ${cob.chip}`}>
      <div className="flex items-start gap-1.5">
        <Icono className="mt-0.5 h-3 w-3 shrink-0" />
        <span className="min-w-0 break-words font-medium leading-tight">{evento.titulo}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 opacity-90">
        {evento.hora && <span>{evento.hora}</span>}
        <span className={COLOR_PRIORIDAD[evento.prioridad]}>· {evento.prioridad}</span>
      </div>
      {evento.cambiado && (
        <div className="flex flex-wrap items-center gap-1">
          <Badge variant="aviso" className="gap-1 font-normal">
            <BellRing className="h-3 w-3" /> Cambió
          </Badge>
          <BotonMarcarAvisado evento={evento} onCambio={onCambio} />
        </div>
      )}
    </div>
  );
}

/** Chip compacto de una ausencia dentro de la banda superior del día. */
function ChipAusenciaDia({ ausencia }: { ausencia: AusenciaRota }) {
  const pres = PRESENTACION_AUSENCIA[ausencia.tipo] ?? PRESENTACION_AUSENCIA.otro;
  const Icono = pres.icono;
  const tooltip = ausencia.motivo
    ? `${pres.etiqueta}: ${ausencia.motivo}`
    : pres.etiqueta;
  // `title` nativo: tooltip honesto sin sumar otra librería. El chip es mínimo (icono + nombre).
  return (
    <span
      title={tooltip}
      className={`inline-flex max-w-full items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] leading-tight ${pres.chip}`}
    >
      <Icono className="h-2.5 w-2.5 shrink-0" />
      <span className="truncate">{ausencia.miembro_nombre || "—"}</span>
    </span>
  );
}

/** Popover (CSS puro) con el resto de ausencias del día cuando hay > MAX_VISIBLE. */
function MasAusencias({ ausencias }: { ausencias: AusenciaRota[] }) {
  const [abierto, setAbierto] = React.useState(false);
  return (
    <div className="relative inline-block">
      <button
        type="button"
        className="rounded border border-border bg-muted/40 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted"
        onClick={() => setAbierto((v) => !v)}
        aria-label={`Ver ${ausencias.length} ausencias más`}
        aria-expanded={abierto}
      >
        +{ausencias.length}
      </button>
      {abierto && (
        <div
          className="absolute left-0 top-full z-20 mt-1 flex w-max max-w-[14rem] flex-col gap-1 rounded-md border border-border bg-popover p-2 shadow-md"
          role="dialog"
        >
          {ausencias.map((a) => (
            <ChipAusenciaDia key={a.id} ausencia={a} />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * ¿La ausencia toca el día `fecha` (rango inclusivo)?
 * Comparación lexicográfica sobre ISO AAAA-MM-DD: segura sin parseo.
 */
function ausenciaTocaDia(a: AusenciaRota, fecha: string): boolean {
  return a.desde <= fecha && fecha <= a.hasta;
}

// Las dos franjas reales que el equipo trabaja, en orden de aparición vertical en
// el calendario. `descanso` aparece como una banda inferior con marca clara: aunque
// nadie "cubre" en descanso, mostrarla deja explícito quién está OFF ese día y dónde
// caen los eventos nocturnos (>=23h) que no se cubren.
const FRANJAS_CALENDARIO: FranjaTurno[] = ["matutino", "vespertino", "descanso"];

/**
 * Mapea la hora de un evento a la franja de trabajo. Sin hora -> matutino (la mayoría
 * de los eventos "TBD" son notas tempraneras). El equipo trabaja matutino 06-13:59,
 * vespertino 14-22:59 y "descanso" 23-05:59 (turno de madrugada que NADIE cubre, pero
 * que aparece en la rejilla para no esconder eventos nocturnos).
 */
function franjaDeHora(hora: string): FranjaTurno {
  const m = hora.match(/(\d{1,2}):?(\d{2})?/);
  if (!m) return "matutino";
  const h = Number(m[1]);
  if (!Number.isFinite(h)) return "matutino";
  if (h >= 6 && h <= 13) return "matutino";
  if (h >= 14 && h <= 22) return "vespertino";
  return "descanso";
}

/** Presentación visual de cada franja en el calendario (color de banda izquierda). */
const COLOR_FRANJA_CALENDARIO: Record<FranjaTurno, { label: string; banda: string; fondo: string }> = {
  matutino: {
    label: "Mañana",
    banda: "border-l-amber-400",
    fondo: "bg-amber-50/30 dark:bg-amber-950/10",
  },
  vespertino: {
    label: "Tarde",
    banda: "border-l-sky-400",
    fondo: "bg-sky-50/30 dark:bg-sky-950/10",
  },
  descanso: {
    label: "Descanso / madrugada",
    banda: "border-l-zinc-300 dark:border-l-zinc-700",
    fondo: "bg-muted/30",
  },
};

interface ItemEventoCalendario {
  evento: EventoRota;
  /** Turno que asigna al evento (null si nadie lo cubre). */
  turno: TurnoRota | null;
  /** `true` si el evento está asignado a alguien que no trabaja esa franja-día. */
  fueraDeTurno: boolean;
}

interface RecuadroPersona {
  miembro_id: string;
  miembro_nombre: string;
  /** `true` si el recuadro es "Sin asignar" (eventos sin turno o asignados fuera). */
  sinAsignar: boolean;
  eventos: ItemEventoCalendario[];
}

/**
 * Calendario nuevo (día × franja × persona): la frontera real con la que trabaja el
 * equipo. Las filas son franjas (mañana → tarde → descanso), las columnas son los 7
 * días de la semana. Cada celda contiene un recuadro por persona que TRABAJA esa
 * franja ese día con sus eventos asignados; si un evento está asignado a alguien
 * fuera de su franja, sale en "Sin asignar" con badge "Fuera de turno". El relleno
 * ocupa el alto disponible para minimizar scroll lateral.
 */
function Calendario({ lunes, setLunes }: { lunes: string; setLunes: (l: string) => void }) {
  const queryClient = useQueryClient();
  // El rango (lun→dom) de la semana en vista para acotar las consultas.
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1); // exclusivo
  const eventosQ = useQuery({
    queryKey: ["rota", "calendario", "eventos", desde] as const,
    queryFn: ({ signal }) => api.rotaEventos({ desde, hasta }, signal),
  });
  const semanaQ = useQuery({
    queryKey: ["rota", "semana", lunes] as const,
    queryFn: ({ signal }) => api.rotaSemana({ lunes }, signal),
  });
  const horarioQ = useQuery({
    queryKey: ["rota", "horario", lunes] as const,
    queryFn: ({ signal }) => api.rotaHorario({ lunes }, signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });

  // Las 7 fechas de la semana (lun → dom). Memo para estabilidad referencial.
  const dias = React.useMemo(() => {
    const base = new Date(`${lunes}T00:00:00`);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base);
      d.setDate(d.getDate() + i);
      return iso(d);
    });
  }, [lunes]);

  // Modal de edición rápida (chip click → edita el evento sin salir del calendario).
  const [eventoSeleccionado, setEventoSeleccionado] = React.useState<EventoRota | null>(null);

  // Filtra al rango exacto.
  const eventos = (eventosQ.data?.eventos ?? []).filter(
    (e) => e.fecha >= desde && e.fecha < hasta,
  );
  // Mapa eventoId → turno (cobertura): nos dice quién cubre cada evento.
  const turnosPorEvento = React.useMemo(() => {
    const m = new Map<string, TurnoRota>();
    for (const t of semanaQ.data?.turnos ?? []) m.set(t.evento_id, t);
    return m;
  }, [semanaQ.data?.turnos]);

  // Mapa (miembro_id|fecha) → franja del horario de trabajo. Indica quién trabaja qué.
  const franjaPorPersona = React.useMemo(() => {
    const m = new Map<string, FranjaTurno>();
    for (const t of horarioQ.data?.turnos ?? []) {
      m.set(`${t.miembro_id}|${t.fecha}`, t.franja);
    }
    return m;
  }, [horarioQ.data?.turnos]);

  // Personas que trabajan cada (franja, fecha) según el horario publicado.
  const personasPorCelda = React.useMemo(() => {
    const m = new Map<string, { miembro_id: string; miembro_nombre: string }[]>();
    for (const t of horarioQ.data?.turnos ?? []) {
      const k = `${t.franja}|${t.fecha}`;
      const lista = m.get(k) ?? [];
      lista.push({ miembro_id: t.miembro_id, miembro_nombre: t.miembro_nombre });
      m.set(k, lista);
    }
    // Orden estable por nombre para que los recuadros no salten entre renders.
    for (const lista of m.values()) {
      lista.sort((a, b) => a.miembro_nombre.localeCompare(b.miembro_nombre));
    }
    return m;
  }, [horarioQ.data?.turnos]);

  // Ausencias que solapan con la semana.
  const finSemana = dias[6] ?? desde;
  const ausenciasSemana = (ausenciasQ.data?.ausencias ?? []).filter(
    (a) => a.desde <= finSemana && a.hasta >= desde,
  );
  const ausenciasPorDia = new Map<string, AusenciaRota[]>();
  for (const fecha of dias) {
    const lista = ausenciasSemana.filter((a) => ausenciaTocaDia(a, fecha));
    if (lista.length > 0) {
      lista.sort((x, y) => {
        if (x.tipo !== y.tipo) return x.tipo.localeCompare(y.tipo);
        return (x.miembro_nombre || "").localeCompare(y.miembro_nombre || "");
      });
      ausenciasPorDia.set(fecha, lista);
    }
  }

  // Itera los eventos y los reparte en su (franja, fecha) → persona/sin-asignar.
  const recuadrosPorCelda = React.useMemo(() => {
    const m = new Map<string, RecuadroPersona[]>(); // clave: `${franja}|${fecha}`
    // Para cada celda primero metemos el recuadro de cada persona que trabaja allí
    // (aunque no tenga eventos): es lo que pidió el usuario, "ver quién cubre el turno".
    for (const franja of FRANJAS_CALENDARIO) {
      for (const fecha of dias) {
        const personas = personasPorCelda.get(`${franja}|${fecha}`) ?? [];
        const lista: RecuadroPersona[] = personas.map((p) => ({
          miembro_id: p.miembro_id,
          miembro_nombre: p.miembro_nombre,
          sinAsignar: false,
          eventos: [],
        }));
        m.set(`${franja}|${fecha}`, lista);
      }
    }
    // Ahora coloca cada evento en su recuadro: turno.miembro -> recuadro de esa persona
    // EN LA FRANJA del evento; si la persona no trabaja esa franja (o no hay turno),
    // cae en "Sin asignar" con badge fueraDeTurno cuando había asignación.
    for (const evento of eventos) {
      const franja = franjaDeHora(evento.hora);
      const clave = `${franja}|${evento.fecha}`;
      const turno = turnosPorEvento.get(evento.id) ?? null;
      const persona = turno?.miembro_id ?? "";
      const lista = m.get(clave) ?? [];

      if (persona && franjaPorPersona.get(`${persona}|${evento.fecha}`) === franja) {
        // La persona trabaja esa franja ese día: lo metemos en su recuadro.
        const recuadro = lista.find((r) => !r.sinAsignar && r.miembro_id === persona);
        if (recuadro) {
          recuadro.eventos.push({ evento, turno, fueraDeTurno: false });
          continue;
        }
      }
      // O no hay turno, o el asignado no trabaja esa franja: "Sin asignar" con badge.
      let recuadroSin = lista.find((r) => r.sinAsignar);
      if (!recuadroSin) {
        recuadroSin = {
          miembro_id: "",
          miembro_nombre: "Sin asignar",
          sinAsignar: true,
          eventos: [],
        };
        // El recuadro Sin asignar se muestra al final.
        lista.push(recuadroSin);
      }
      recuadroSin.eventos.push({
        evento,
        turno,
        fueraDeTurno: Boolean(persona),
      });
      m.set(clave, lista);
    }
    return m;
  }, [eventos, dias, personasPorCelda, turnosPorEvento, franjaPorPersona]);

  const inicio = dias[0] ?? "";
  const fin = dias[6] ?? "";
  const nCambiados = eventos.filter((e) => e.cambiado).length;
  const cargando =
    eventosQ.isPending || semanaQ.isPending || horarioQ.isPending || ausenciasQ.isPending;
  const error = eventosQ.error || semanaQ.error || horarioQ.error || ausenciasQ.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
        {nCambiados > 0 && (
          <Badge variant="aviso" className="gap-1 font-normal">
            <BellRing className="h-3.5 w-3.5" /> {nCambiados} reprogramado
            {nCambiados === 1 ? "" : "s"} sin avisar
          </Badge>
        )}
      </div>

      <LeyendaCobertura />

      {cargando ? (
        <Skeleton className="h-[60vh] w-full rounded-md" />
      ) : error ? (
        <BloqueError
          titulo="No se pudo cargar el calendario"
          mensaje={mensajeError(error)}
          onReintentar={() => {
            void eventosQ.refetch();
            void semanaQ.refetch();
            void horarioQ.refetch();
            void ausenciasQ.refetch();
          }}
          cargando={eventosQ.isFetching}
        />
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {/* Rejilla principal: 1 cabecera con días + 1 fila por franja.
                `max-h-[calc(100vh-18rem)]` aprovecha el alto disponible con scroll interno
                si la semana se sale de pantalla; `min-w-[56rem]` mantiene legibilidad. */}
            <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 18rem)" }}>
              <div className="min-w-[56rem]">
                {/* Cabecera de días (sticky para que no se pierda al hacer scroll). */}
                <div className="sticky top-0 z-10 grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px border-b bg-background">
                  <div className="bg-background px-3 py-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    Franja
                  </div>
                  {dias.map((fecha) => {
                    const ausDia = ausenciasPorDia.get(fecha) ?? [];
                    const finde = esFinDeSemana(fecha);
                    return (
                      <div
                        key={fecha}
                        className={`flex flex-col gap-1 px-2 py-2 ${
                          finde ? "bg-amber-50/40 dark:bg-amber-950/10" : "bg-background"
                        }`}
                      >
                        <div className="flex items-baseline justify-between">
                          <span className="text-xs font-semibold capitalize">
                            {diaCorto(fecha)}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {fecha.slice(8, 10)}
                          </span>
                        </div>
                        {ausDia.length > 0 && (
                          <div
                            className="flex flex-wrap gap-1"
                            aria-label={`Ausencias del ${fecha}`}
                          >
                            {ausDia.slice(0, 2).map((a) => (
                              <ChipAusenciaDia key={a.id} ausencia={a} />
                            ))}
                            {ausDia.length > 2 && (
                              <MasAusencias ausencias={ausDia.slice(2)} />
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Filas: una por franja. Borde superior grueso para marcar el cambio. */}
                {FRANJAS_CALENDARIO.map((franja, idx) => {
                  const meta = COLOR_FRANJA_CALENDARIO[franja];
                  return (
                    <div
                      key={franja}
                      className={`grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px ${
                        idx > 0 ? "border-t-4 border-t-border" : ""
                      }`}
                    >
                      {/* Etiqueta de franja (sticky a la izquierda para scroll horizontal). */}
                      <div
                        className={`sticky left-0 z-[1] flex items-center border-l-4 px-3 py-3 text-sm font-semibold ${meta.banda} ${meta.fondo}`}
                      >
                        {meta.label}
                      </div>
                      {dias.map((fecha) => {
                        const finde = esFinDeSemana(fecha);
                        const recuadros = recuadrosPorCelda.get(`${franja}|${fecha}`) ?? [];
                        return (
                          <div
                            key={`${franja}-${fecha}`}
                            className={`flex min-h-[8rem] flex-col gap-2 border-l p-2 ${
                              finde ? "bg-amber-50/20 dark:bg-amber-950/5" : ""
                            }`}
                          >
                            {recuadros.length === 0 ? (
                              <div className="rounded-md border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-muted-foreground/60">
                                {franja === "descanso" ? "—" : "Sin turno asignado"}
                              </div>
                            ) : (
                              recuadros.map((rec) => (
                                <RecuadroPersonaCalendario
                                  key={`${rec.miembro_id}-${rec.sinAsignar ? "sin" : "ok"}`}
                                  recuadro={rec}
                                  franja={franja}
                                  onEditarEvento={(e) => setEventoSeleccionado(e)}
                                  onCambio={invalidar}
                                />
                              ))
                            )}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {eventoSeleccionado && (
        <DialogEditarEvento
          evento={eventoSeleccionado}
          onCerrar={() => setEventoSeleccionado(null)}
          onCambio={invalidar}
        />
      )}
    </div>
  );
}

/** Un recuadro por persona dentro de una celda día-franja del calendario. */
function RecuadroPersonaCalendario({
  recuadro,
  franja,
  onEditarEvento,
  onCambio,
}: {
  recuadro: RecuadroPersona;
  franja: FranjaTurno;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
}) {
  const esDescanso = franja === "descanso";
  const estilo = recuadro.sinAsignar
    ? "border-dashed border-amber-300/70 bg-amber-50/30 dark:bg-amber-950/10"
    : esDescanso
      ? "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/40"
      : "border-border bg-background";
  return (
    <div className={`flex flex-col gap-1 rounded-md border p-1.5 text-xs ${estilo}`}>
      <div className="flex items-center justify-between gap-1">
        <span
          className={`truncate font-medium ${
            recuadro.sinAsignar ? "text-amber-700 dark:text-amber-400" : ""
          }`}
        >
          {recuadro.sinAsignar ? "Sin asignar" : recuadro.miembro_nombre}
        </span>
        {recuadro.eventos.length > 0 && (
          <Badge variant="outline" className="h-4 px-1 text-[10px] font-normal">
            {recuadro.eventos.length}
          </Badge>
        )}
      </div>
      {recuadro.eventos.length === 0 ? (
        <span className="px-0.5 text-[10px] text-muted-foreground/70">
          {esDescanso ? "Descanso" : "Sin eventos"}
        </span>
      ) : (
        <div className="flex flex-col gap-1">
          {recuadro.eventos.map((item) => (
            <ChipEventoCalendario
              key={item.evento.id}
              item={item}
              onClick={() => onEditarEvento(item.evento)}
              onCambio={onCambio}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** Chip de evento dentro de un recuadro de persona (clicable: abre edición). */
function ChipEventoCalendario({
  item,
  onClick,
  onCambio,
}: {
  item: ItemEventoCalendario;
  onClick: () => void;
  onCambio: () => void;
}) {
  const cob = COBERTURA[item.evento.tipo_cobertura] ?? COBERTURA.transmision;
  const Icono = cob.icono;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group/chip flex flex-col gap-0.5 rounded-sm border px-1.5 py-1 text-left text-[11px] leading-tight transition hover:ring-1 hover:ring-primary/40 ${cob.chip}`}
      aria-label={`Editar ${item.evento.titulo}`}
    >
      <span className="flex items-start gap-1">
        <Icono className="mt-0.5 h-2.5 w-2.5 shrink-0" />
        <span className="min-w-0 break-words font-medium">{item.evento.titulo}</span>
      </span>
      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 opacity-90">
        {item.evento.hora && <span>{item.evento.hora}</span>}
        <span className={COLOR_PRIORIDAD[item.evento.prioridad]}>· {item.evento.prioridad}</span>
        {item.evento.cambiado && (
          <Badge variant="aviso" className="h-3.5 gap-0.5 px-1 text-[9px] font-normal">
            <BellRing className="h-2.5 w-2.5" /> cambió
          </Badge>
        )}
      </span>
      {item.fueraDeTurno && item.turno?.miembro_nombre && (
        <span className="mt-0.5 inline-flex items-center gap-1 rounded border border-amber-400/60 bg-amber-100/60 px-1 py-0.5 text-[10px] text-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
          <AlertTriangle className="h-2.5 w-2.5" />
          Asignado a {item.turno.miembro_nombre} fuera de turno
        </span>
      )}
      {item.evento.cambiado && (
        <span
          // Stop propagation: marcar avisado no debe abrir el modal de edición.
          onClick={(e) => e.stopPropagation()}
          className="mt-0.5"
        >
          <BotonMarcarAvisado evento={item.evento} onCambio={onCambio} />
        </span>
      )}
    </button>
  );
}

/** Diálogo de edición rápida de evento: lo que más se cambia desde el calendario. */
function DialogEditarEvento({
  evento,
  onCerrar,
  onCambio,
}: {
  evento: EventoRota;
  onCerrar: () => void;
  onCambio: () => void;
}) {
  const [titulo, setTitulo] = React.useState(evento.titulo);
  const [fecha, setFecha] = React.useState(evento.fecha);
  const [hora, setHora] = React.useState(evento.hora);
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>(
    evento.tipo_cobertura,
  );
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>(evento.prioridad);
  const [contenido, setContenido] = React.useState(evento.contenido);

  const guardar = useMutation({
    mutationFn: () =>
      api.actualizarEventoRota(evento.id, {
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
        contenido: contenido.trim(),
      }),
    onSuccess: () => {
      toast.success("Evento guardado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar evento</DialogTitle>
          <DialogDescription>
            Los cambios de fecha/hora/cobertura marcan el evento como reprogramado para que
            avisen al equipo.
          </DialogDescription>
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
            onClick={() => {
              if (window.confirm("¿Borrar este evento? Sus turnos también se perderán."))
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
  // Memoizamos `turnos` para que el `useMemo` de filtros tenga una referencia estable
  // entre renders cuando los datos no cambian (evita recomputos innecesarios y avisos
  // del linter).
  const turnos = React.useMemo(() => semana?.turnos ?? [], [semana?.turnos]);

  const invalidarTodo = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota"] });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: claveSemana });

  const aprobar = useMutation({
    mutationFn: () => api.aprobarRota({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveSemana, res);
      toast.success(res.mensaje ?? "Rota publicada al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const copiarAnterior = useMutation({
    mutationFn: () =>
      api.copiarSemana({
        de_lunes: lunesSiguiente(lunes, -1),
        a_lunes: lunes,
        alcance: "cobertura",
        reemplazar: false,
      }),
    onSuccess: (res) => {
      if (res.mensaje) toast.warning(res.mensaje);
      else toast.success(`Copiados ${res.copiados ?? 0} turnos de cobertura.`);
      invalidarTodo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Filtros por miembro (multi-toggle); "sin-asignar" es un id reservado.
  const [filtros, setFiltros] = React.useState<Set<string>>(new Set());
  // Filtro por estado del turno (toggle exclusivo): null = todos.
  const [filtroEstado, setFiltroEstado] = React.useState<
    "todos" | "sin_asignar" | "asignados" | "aprobados"
  >("todos");
  const turnosFiltrados = React.useMemo(() => {
    let xs = turnos;
    if (filtros.size > 0) {
      xs = xs.filter((t) => {
        if (!t.miembro_id) return filtros.has("sin-asignar");
        return filtros.has(t.miembro_id);
      });
    }
    if (filtroEstado === "sin_asignar") xs = xs.filter((t) => !t.miembro_id);
    else if (filtroEstado === "asignados") xs = xs.filter((t) => Boolean(t.miembro_id));
    else if (filtroEstado === "aprobados") xs = xs.filter((t) => t.estado === "aprobado");
    return xs;
  }, [turnos, filtros, filtroEstado]);

  // Selección múltiple (estado del check por fila).
  const [seleccionados, setSeleccionados] = React.useState<Set<string>>(new Set());
  // Cada vez que cambia la semana o se invalida, limpia la selección (ids viejos).
  React.useEffect(() => {
    setSeleccionados(new Set());
  }, [lunes, semana?.total]);

  const toggleSeleccionado = (id: string) =>
    setSeleccionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
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
            <Badge variant="secondary" className="font-normal">
              Borrador
            </Badge>
          ) : null}
          {!semana?.aprobada && (
            <BotonNuevoTurno
              lunes={lunes}
              equipo={equipo}
              onCreado={invalidarTodo}
            />
          )}
          <Button
            variant="outline"
            onClick={() => copiarAnterior.mutate()}
            disabled={copiarAnterior.isPending || semana?.aprobada}
            title="Copiar la cobertura de la semana anterior (los eventos cambian: avisa si no aplica)"
          >
            {copiarAnterior.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            Copiar semana anterior
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

      {!semana?.aprobada && (
        <AsignarDeGolpe lunes={lunes} equipo={equipo} onAplicado={invalidarTodo} />
      )}

      <FiltrosMiembro equipo={equipo} filtros={filtros} setFiltros={setFiltros} />

      {/* Filtros por estado del turno (exclusivos: todos / sin asignar / asignados / aprobados). */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-muted-foreground">Estado:</span>
        {(
          [
            { v: "todos", l: "Todos" },
            { v: "sin_asignar", l: "Sin asignar" },
            { v: "asignados", l: "Asignados" },
            { v: "aprobados", l: "Aprobados" },
          ] as { v: typeof filtroEstado; l: string }[]
        ).map((opt) => (
          <Button
            key={opt.v}
            size="sm"
            variant={filtroEstado === opt.v ? "default" : "outline"}
            className="h-7 px-2"
            onClick={() => setFiltroEstado(opt.v)}
          >
            {opt.l}
          </Button>
        ))}
      </div>

      {seleccionados.size > 0 && (
        <BarraSeleccion
          seleccionados={seleccionados}
          equipo={equipo}
          onLimpiar={() => setSeleccionados(new Set())}
          onAplicado={() => {
            setSeleccionados(new Set());
            invalidarTodo();
          }}
        />
      )}

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
          texto="Da de alta los eventos de la semana en la pestaña 'Eventos' y asigna cada uno a un miembro de tu equipo."
        />
      ) : (
        <TablaTurnos
          turnos={turnosFiltrados}
          equipo={equipo}
          editable={!semana?.aprobada}
          onCambio={invalidar}
          seleccionados={seleccionados}
          onToggleSeleccionado={!semana?.aprobada ? toggleSeleccionado : undefined}
        />
      )}

      <PanelCarga lunes={lunes} />
    </div>
  );
}

// --- Asignar de golpe (POR FRANJA) -----------------------------------------

function AsignarDeGolpe({
  lunes,
  equipo,
  onAplicado,
}: {
  lunes: string;
  equipo: MiembroRota[];
  onAplicado: () => void;
}) {
  const dias = React.useMemo(() => {
    const base = new Date(`${lunes}T00:00:00`);
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(base);
      d.setDate(d.getDate() + i);
      return iso(d);
    });
  }, [lunes]);

  const [fecha, setFecha] = React.useState(dias[0] ?? "");
  const [franja, setFranja] = React.useState<FranjaCobertura>("vespertino");
  const [miembroId, setMiembroId] = React.useState("");
  const [sobreescribir, setSobreescribir] = React.useState(false);

  React.useEffect(() => {
    // Si cambia la semana, ancla la fecha al primer día válido.
    if (dias.length > 0 && !dias.includes(fecha)) setFecha(dias[0]);
  }, [dias, fecha]);

  const aplicar = useMutation({
    mutationFn: (override: boolean) =>
      api.asignarFranja({
        lunes,
        fecha,
        franja,
        miembro_id: miembroId,
        sobreescribir,
        override,
      }),
    onSuccess: (res) => {
      const partes: string[] = [];
      if (res.actualizados > 0) partes.push(`asignados ${res.actualizados}`);
      if (res.saltados > 0) partes.push(`saltados ${res.saltados}`);
      if (res.conflictos.length > 0)
        partes.push(`${res.conflictos.length} requieren override`);
      toast.success(partes.length > 0 ? partes.join(" · ") : "Sin cambios que aplicar.");
      onAplicado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puede = fecha !== "" && miembroId !== "" && !aplicar.isPending;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wand2 className="h-4 w-4" /> Asignar de golpe
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1.5">
          <Label>Día</Label>
          <Select value={fecha} onValueChange={setFecha}>
            <SelectTrigger aria-label="Día de la semana">
              <SelectValue placeholder="—" />
            </SelectTrigger>
            <SelectContent>
              {dias.map((d) => (
                <SelectItem key={d} value={d}>
                  {formatearFechaCorta(d)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>Franja</Label>
          <Select value={franja} onValueChange={(v) => setFranja(v as FranjaCobertura)}>
            <SelectTrigger aria-label="Franja">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="matutino">Mañana (06–13:59)</SelectItem>
              <SelectItem value="vespertino">Tarde (14–22:59)</SelectItem>
            </SelectContent>
          </Select>
        </div>
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
        <div className="flex items-center gap-2 self-end pb-2">
          <Checkbox
            id="sobreescribir"
            checked={sobreescribir}
            onCheckedChange={(v) => setSobreescribir(v === true)}
          />
          <Label htmlFor="sobreescribir" className="cursor-pointer text-sm font-normal">
            Sobrescribir
          </Label>
        </div>
        <div className="flex items-end">
          <Button
            onClick={() => aplicar.mutate(false)}
            disabled={!puede}
            className="w-full"
          >
            {aplicar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Wand2 className="h-4 w-4" />
            )}
            Asignar
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// --- Botón "Nuevo turno": dos modos (evento existente / evento nuevo + turno) ---

/**
 * Crear un turno de cobertura directamente desde la parrilla. Dos caminos:
 *  - "Para evento existente": elige uno de los eventos de la semana y la persona.
 *  - "Crear evento + turno": atajo cuando el evento aún no existe (alta express).
 */
function BotonNuevoTurno({
  lunes,
  equipo,
  onCreado,
}: {
  lunes: string;
  equipo: MiembroRota[];
  onCreado: () => void;
}) {
  const [abierto, setAbierto] = React.useState(false);
  return (
    <>
      <Button variant="default" size="sm" onClick={() => setAbierto(true)}>
        <Plus className="h-4 w-4" /> Nuevo turno
      </Button>
      {abierto && (
        <DialogNuevoTurno
          lunes={lunes}
          equipo={equipo}
          onCerrar={() => setAbierto(false)}
          onCreado={() => {
            onCreado();
            setAbierto(false);
          }}
        />
      )}
    </>
  );
}

function DialogNuevoTurno({
  lunes,
  equipo,
  onCerrar,
  onCreado,
}: {
  lunes: string;
  equipo: MiembroRota[];
  onCerrar: () => void;
  onCreado: () => void;
}) {
  const [modo, setModo] = React.useState<"existente" | "nuevo">("existente");
  // Eventos de la semana en vista (lo más común: el turno encaja en algún evento real).
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1);
  const eventosQ = useQuery({
    queryKey: ["rota", "eventos-semana-picker", desde] as const,
    queryFn: ({ signal }) => api.rotaEventos({ desde, hasta }, signal),
  });
  const eventos = (eventosQ.data?.eventos ?? []).filter(
    (e) => e.fecha >= desde && e.fecha < hasta,
  );

  // --- Modo "existente" ---
  const [eventoId, setEventoId] = React.useState("");
  const [miembroId, setMiembroId] = React.useState("");
  const crearExistente = useMutation({
    mutationFn: (override: boolean) =>
      api.crearTurnoRota({
        evento_id: eventoId,
        miembro_id: miembroId || undefined,
        override,
      }),
    onSuccess: () => {
      toast.success("Turno creado.");
      onCreado();
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        if (
          window.confirm(
            `${e.message}\n\n¿Forzar la cobertura aun así (override)?`,
          )
        ) {
          crearExistente.mutate(true);
          return;
        }
      }
      toast.error(mensajeError(e));
    },
  });

  // --- Modo "nuevo" (alta express): evento + turno ---
  const [titulo, setTitulo] = React.useState("");
  const [fecha, setFecha] = React.useState(desde);
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>("transmision");
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>("media");

  const crearNuevo = useMutation({
    mutationFn: async (override: boolean) => {
      const ev = await api.crearEventoRota({
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        contenido: contenido.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
      });
      return api.crearTurnoRota({
        evento_id: ev.evento.id,
        miembro_id: miembroId || undefined,
        override,
      });
    },
    onSuccess: () => {
      toast.success("Evento creado y turno asignado.");
      onCreado();
    },
    onError: (e) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        // No reintentamos automáticamente: si el evento ya se creó (caso muy poco probable
        // aquí), el override solo aplica al turno; lo dejamos en la mano del usuario.
        toast.warning(`${e.message} Llama de nuevo desde el listado con override.`);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const puedeExistente = eventoId !== "" && !crearExistente.isPending;
  const puedeNuevo =
    titulo.trim().length > 0 && fecha !== "" && !crearNuevo.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Nuevo turno de cobertura</DialogTitle>
          <DialogDescription>
            Asigna una persona a un evento de esta semana, o crea el evento al vuelo.
          </DialogDescription>
        </DialogHeader>

        {/* Toggle entre los dos modos. Tabs simulados con botones para no anidar */}
        {/* <Tabs> dentro de <Dialog> (sería molesto con el foco). */}
        <div className="flex gap-2">
          <Button
            size="sm"
            variant={modo === "existente" ? "default" : "outline"}
            onClick={() => setModo("existente")}
          >
            Para un evento existente
          </Button>
          <Button
            size="sm"
            variant={modo === "nuevo" ? "default" : "outline"}
            onClick={() => setModo("nuevo")}
          >
            Crear evento + turno
          </Button>
        </div>

        {modo === "existente" ? (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>Evento</Label>
              {eventosQ.isPending ? (
                <Skeleton className="h-9 w-full rounded-md" />
              ) : eventos.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No hay eventos en esta semana. Crea uno arriba o usa el modo
                  "Crear evento + turno".
                </p>
              ) : (
                <Select value={eventoId} onValueChange={setEventoId}>
                  <SelectTrigger>
                    <SelectValue placeholder="Elige un evento" />
                  </SelectTrigger>
                  <SelectContent>
                    {eventos
                      .slice()
                      .sort((a, b) =>
                        (a.fecha + a.hora).localeCompare(b.fecha + b.hora),
                      )
                      .map((e) => (
                        <SelectItem key={e.id} value={e.id}>
                          {formatearFechaCorta(e.fecha)}
                          {e.hora ? ` · ${e.hora}` : ""} — {e.titulo}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="space-y-1.5">
              <Label>Persona</Label>
              <Select value={miembroId} onValueChange={setMiembroId}>
                <SelectTrigger>
                  <SelectValue placeholder="Sin asignar (puedes elegir luego)" />
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
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="nt-titulo">Evento / transmisión</Label>
              <Input
                id="nt-titulo"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                placeholder="Ej. Cruz Azul vs América"
                maxLength={200}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="nt-fecha">Fecha</Label>
                <Input
                  id="nt-fecha"
                  type="date"
                  value={fecha}
                  onChange={(e) => setFecha(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nt-hora">Hora</Label>
                <Input
                  id="nt-hora"
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
                <Select
                  value={prioridad}
                  onValueChange={(v) => setPrioridad(v as PrioridadEvento)}
                >
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
              <Label htmlFor="nt-contenido">Qué sacar</Label>
              <Textarea
                id="nt-contenido"
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                rows={2}
                maxLength={2000}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Persona (turno)</Label>
              <Select value={miembroId} onValueChange={setMiembroId}>
                <SelectTrigger>
                  <SelectValue placeholder="Sin asignar (puedes elegir luego)" />
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
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          {modo === "existente" ? (
            <Button
              onClick={() => crearExistente.mutate(false)}
              disabled={!puedeExistente}
            >
              {crearExistente.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear turno
            </Button>
          ) : (
            <Button onClick={() => crearNuevo.mutate(false)} disabled={!puedeNuevo}>
              {crearNuevo.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear evento y turno
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Filtros por miembro ---------------------------------------------------

function FiltrosMiembro({
  equipo,
  filtros,
  setFiltros,
}: {
  equipo: MiembroRota[];
  filtros: Set<string>;
  setFiltros: React.Dispatch<React.SetStateAction<Set<string>>>;
}) {
  const toggle = (id: string) =>
    setFiltros((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  if (equipo.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">Filtra por persona:</span>
      {equipo.map((m) => {
        const activo = filtros.has(m.id);
        return (
          <Button
            key={m.id}
            size="sm"
            variant={activo ? "default" : "outline"}
            className="h-7 px-2"
            onClick={() => toggle(m.id)}
          >
            {m.nombre}
          </Button>
        );
      })}
      <Button
        size="sm"
        variant={filtros.has("sin-asignar") ? "default" : "outline"}
        className="h-7 px-2"
        onClick={() => toggle("sin-asignar")}
      >
        Sin asignar
      </Button>
      {filtros.size > 0 && (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 px-2 text-muted-foreground"
          onClick={() => setFiltros(new Set())}
        >
          <X className="h-3.5 w-3.5" /> Limpiar
        </Button>
      )}
    </div>
  );
}

// --- Barra de acción para la selección múltiple ----------------------------

function BarraSeleccion({
  seleccionados,
  equipo,
  onLimpiar,
  onAplicado,
}: {
  seleccionados: Set<string>;
  equipo: MiembroRota[];
  onLimpiar: () => void;
  onAplicado: () => void;
}) {
  const [miembroId, setMiembroId] = React.useState("");
  // Si el backend pide override (409), guardamos los datos y abrimos el diálogo.
  const [override, setOverride] = React.useState<{
    miembroId: string;
    mensaje: string;
    ids: string[];
  } | null>(null);

  const aplicar = useMutation({
    mutationFn: (vars: { miembroId: string; override: boolean }) =>
      api.actualizarLoteTurnos({
        ids: [...seleccionados],
        miembro_id: vars.miembroId,
        override: vars.override,
      }),
    onSuccess: (res) => {
      toast.success(`Asignados ${res.actualizados} turnos.`);
      setOverride(null);
      setMiembroId("");
      onAplicado();
    },
    onError: (e, vars) => {
      if (e instanceof ApiError && e.status === 409) {
        const ids = (e.cuerpo?.ids_que_requieren_override as string[] | undefined) ?? [];
        setOverride({ miembroId: vars.miembroId, mensaje: e.message, ids });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  // `miembro_id=""` SÍ está aceptado por el backend (alineado con el PATCH 1:1):
  // quita la asignación de todos los turnos del lote.
  const quitar = useMutation({
    mutationFn: () =>
      api.actualizarLoteTurnos({ ids: [...seleccionados], miembro_id: "" }),
    onSuccess: (res) => {
      toast.success(`Quitada asignación a ${res.actualizados} turnos.`);
      onAplicado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrarSeleccion = useMutation({
    mutationFn: () => api.borrarTurnosLote({ ids: [...seleccionados] }),
    onSuccess: (res) => {
      const ne = res.no_encontrados?.length ?? 0;
      toast.success(
        ne > 0
          ? `Borrados ${res.borrados} turnos (${ne} ya no existían).`
          : `Borrados ${res.borrados} turnos.`,
      );
      onAplicado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Card className="border-primary/40 bg-primary/5">
      <CardContent className="flex flex-wrap items-center gap-3 p-3">
        <span className="text-sm font-medium">
          Seleccionados {seleccionados.size}
        </span>
        <span className="text-sm text-muted-foreground">· Asignar a</span>
        <div className="min-w-[12rem]">
          <Select value={miembroId} onValueChange={setMiembroId}>
            <SelectTrigger aria-label="Persona para el lote" className="h-8">
              <SelectValue placeholder="Elige persona" />
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
        <Button
          size="sm"
          onClick={() => aplicar.mutate({ miembroId, override: false })}
          disabled={!miembroId || aplicar.isPending}
        >
          {aplicar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Users className="h-4 w-4" />
          )}
          Aplicar
        </Button>
        <Button
          size="sm"
          variant="outline"
          onClick={() => quitar.mutate()}
          disabled={quitar.isPending}
        >
          {quitar.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Quitar asignación
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="text-destructive hover:text-destructive"
          onClick={() => {
            if (
              window.confirm(
                `¿Borrar ${seleccionados.size} turno${
                  seleccionados.size === 1 ? "" : "s"
                }? Los eventos siguen, pero perderán su cobertura.`,
              )
            )
              borrarSeleccion.mutate();
          }}
          disabled={borrarSeleccion.isPending}
        >
          {borrarSeleccion.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Trash2 className="h-3.5 w-3.5" />
          )}
          Borrar
        </Button>
        <Button size="sm" variant="ghost" onClick={onLimpiar}>
          <X className="h-4 w-4" /> Cancelar
        </Button>
      </CardContent>
      {override && (
        <Dialog open onOpenChange={(o) => !o && setOverride(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>¿Forzar la cobertura?</DialogTitle>
              <DialogDescription>{override.mensaje}</DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              {override.ids.length} {override.ids.length === 1 ? "turno repite" : "turnos repiten"}
              {" "}el sábado anterior. Confirma solo si es una cobertura estratégica
              intencional.
            </p>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setOverride(null)}>
                Cancelar
              </Button>
              <Button
                onClick={() => aplicar.mutate({ miembroId: override.miembroId, override: true })}
                disabled={aplicar.isPending}
              >
                <AlertTriangle className="h-4 w-4" /> Forzar cobertura
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </Card>
  );
}

// --- Panel "Carga del equipo" ----------------------------------------------

function PanelCarga({ lunes }: { lunes: string }) {
  const [abierto, setAbierto] = React.useState(false);
  const q = useQuery({
    queryKey: ["rota", "carga", lunes],
    queryFn: ({ signal }) => api.cargaRota({ lunes }, signal),
    enabled: abierto && !!lunes,
  });
  const miembros = q.data?.miembros ?? [];
  return (
    <Card>
      <CardHeader
        className="cursor-pointer pb-3"
        onClick={() => setAbierto((v) => !v)}
      >
        <CardTitle className="flex items-center justify-between text-base">
          <span className="flex items-center gap-2">
            <Users className="h-4 w-4" /> Carga del equipo
          </span>
          {abierto ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </CardTitle>
      </CardHeader>
      {abierto && (
        <CardContent className="p-0">
          {q.isPending ? (
            <Skeleton className="h-24 w-full rounded-none" />
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
        </CardContent>
      )}
    </Card>
  );
}

function TablaTurnos({
  turnos,
  equipo,
  editable,
  onCambio,
  seleccionados,
  onToggleSeleccionado,
}: {
  turnos: TurnoRota[];
  equipo: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
  seleccionados?: Set<string>;
  onToggleSeleccionado?: (id: string) => void;
}) {
  const muestraCheck = !!onToggleSeleccionado;
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              {muestraCheck && <TableHead className="w-10" />}
              <TableHead>Día / hora</TableHead>
              <TableHead>Evento / transmisión</TableHead>
              <TableHead>Qué sacar</TableHead>
              <TableHead className="w-[14rem]">Persona</TableHead>
              <TableHead className="w-10" aria-label="Acciones" />
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
                seleccionado={seleccionados?.has(t.id) ?? false}
                onToggleSeleccionado={onToggleSeleccionado}
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
  seleccionado,
  onToggleSeleccionado,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
  seleccionado: boolean;
  onToggleSeleccionado?: (id: string) => void;
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

  const borrar = useMutation({
    mutationFn: () => api.eliminarTurnoRota(turno.id),
    onSuccess: () => {
      toast.success("Turno eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <TableRow className={turno.es_sabado ? "bg-amber-50/40 dark:bg-amber-950/10" : undefined}>
      {onToggleSeleccionado && (
        <TableCell className="align-top">
          <Checkbox
            aria-label={`Seleccionar turno de ${turno.evento_titulo}`}
            checked={seleccionado}
            onCheckedChange={() => onToggleSeleccionado(turno.id)}
          />
        </TableCell>
      )}
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
            <div className="flex items-center gap-1">
              <div className="flex-1">
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
              </div>
              {turno.miembro_id && (
                <Tooltip label="Quitar asignación">
                  <Button
                    size="icon"
                    variant="ghost"
                    className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                    onClick={() => actualizar.mutate({ miembro_id: "" })}
                    disabled={actualizar.isPending}
                  >
                    <UserMinus className="h-3.5 w-3.5" />
                  </Button>
                </Tooltip>
              )}
            </div>
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
      <TableCell className="w-10 align-top">
        {editable && (
          <Tooltip label="Borrar turno">
            <Button
              size="icon"
              variant="ghost"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              aria-label="Borrar turno"
              onClick={() => {
                if (
                  window.confirm(
                    `¿Borrar el turno de "${turno.evento_titulo}"? El evento sigue, pero pierde la cobertura.`,
                  )
                )
                  borrar.mutate();
              }}
              disabled={borrar.isPending}
            >
              {borrar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </Tooltip>
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
                Este horario es un borrador sin publicar; puede cambiar antes de que
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
                Esta rota es un borrador sin publicar; puede cambiar antes de que Elías
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

  const aprobar = useMutation({
    mutationFn: () => api.aprobarHorario({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveHorario, res);
      toast.success(res.mensaje ?? "Horario publicado al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const copiarAnterior = useMutation({
    mutationFn: () =>
      api.copiarSemana({
        de_lunes: lunesSiguiente(lunes, -1),
        a_lunes: lunes,
        alcance: "horario",
        reemplazar: false,
      }),
    onSuccess: (res) => {
      toast.success(`Copiados ${res.copiados ?? 0} turnos del horario.`);
      void queryClient.invalidateQueries({ queryKey: ["rota"] });
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
            <Badge variant="secondary" className="font-normal">
              Borrador
            </Badge>
          ) : null}
          <Button
            variant="outline"
            onClick={() => copiarAnterior.mutate()}
            disabled={copiarAnterior.isPending || horario?.aprobada}
            title="Copia las franjas (mañana/tarde/descanso) de la semana anterior con offset +7 días"
          >
            {copiarAnterior.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            Copiar semana anterior
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
          texto="No has armado el horario de esta semana. Asigna mañana/tarde/descanso a cada miembro, o copia de la semana anterior."
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

// --- Filtros de la pestaña Eventos -----------------------------------------

/** Primer día del MES en curso, en ISO AAAA-MM-DD (default del rango). */
function primerDiaMes(d: Date): string {
  return iso(new Date(d.getFullYear(), d.getMonth(), 1));
}

/** Último día del MES en curso, en ISO AAAA-MM-DD. */
function ultimoDiaMes(d: Date): string {
  return iso(new Date(d.getFullYear(), d.getMonth() + 1, 0));
}

/** Estado tri-estado del filtro "Cambiado" representado como string en la URL. */
type FiltroCambiado = "todos" | "si" | "no";

/** Lee y normaliza los filtros desde la URL (search params). Defaults = mes en curso. */
function leerFiltrosDesdeUrl(sp: URLSearchParams): {
  desde: string;
  hasta: string;
  tiposCobertura: TipoCoberturaEvento[];
  prioridades: PrioridadEvento[];
  cambiado: FiltroCambiado;
  q: string;
} {
  const hoy = new Date();
  const desde = sp.get("desde") ?? primerDiaMes(hoy);
  const hasta = sp.get("hasta") ?? ultimoDiaMes(hoy);
  const tiposCobertura = sp
    .getAll("tipo_cobertura")
    .filter((v): v is TipoCoberturaEvento => v === "transmision" || v === "imagenes" || v === "no_cubrir");
  const prioridades = sp
    .getAll("prioridad")
    .filter((v): v is PrioridadEvento => v === "alta" || v === "media" || v === "baja");
  const cambiadoCrudo = (sp.get("cambiado") ?? "").toLowerCase();
  const cambiado: FiltroCambiado =
    cambiadoCrudo === "true" || cambiadoCrudo === "si"
      ? "si"
      : cambiadoCrudo === "false" || cambiadoCrudo === "no"
        ? "no"
        : "todos";
  const q = sp.get("q") ?? "";
  return { desde, hasta, tiposCobertura, prioridades, cambiado, q };
}

/** Convierte los filtros a `URLSearchParams` (omite defaults para una URL limpia). */
function filtrosAUrl(args: {
  desde: string;
  hasta: string;
  tiposCobertura: TipoCoberturaEvento[];
  prioridades: PrioridadEvento[];
  cambiado: FiltroCambiado;
  q: string;
}): URLSearchParams {
  const sp = new URLSearchParams();
  const hoy = new Date();
  if (args.desde && args.desde !== primerDiaMes(hoy)) sp.set("desde", args.desde);
  if (args.hasta && args.hasta !== ultimoDiaMes(hoy)) sp.set("hasta", args.hasta);
  for (const t of args.tiposCobertura) sp.append("tipo_cobertura", t);
  for (const p of args.prioridades) sp.append("prioridad", p);
  if (args.cambiado === "si") sp.set("cambiado", "true");
  else if (args.cambiado === "no") sp.set("cambiado", "false");
  if (args.q.trim()) sp.set("q", args.q.trim());
  return sp;
}

/** Botón toggle de chip (multi-select). Reutiliza `Button` con dos variantes. */
function ChipToggle({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={activo ? "default" : "outline"}
      className="h-7 px-2.5 text-xs"
      onClick={onClick}
      aria-pressed={activo}
    >
      {children}
    </Button>
  );
}

function FiltrosEventos({
  estado,
  setEstado,
  onLimpiar,
  total,
}: {
  estado: ReturnType<typeof leerFiltrosDesdeUrl>;
  setEstado: (next: ReturnType<typeof leerFiltrosDesdeUrl>) => void;
  onLimpiar: () => void;
  total: number;
}) {
  const togglearCobertura = (t: TipoCoberturaEvento) => {
    const dentro = estado.tiposCobertura.includes(t);
    setEstado({
      ...estado,
      tiposCobertura: dentro
        ? estado.tiposCobertura.filter((x) => x !== t)
        : [...estado.tiposCobertura, t],
    });
  };
  const togglearPrioridad = (p: PrioridadEvento) => {
    const dentro = estado.prioridades.includes(p);
    setEstado({
      ...estado,
      prioridades: dentro
        ? estado.prioridades.filter((x) => x !== p)
        : [...estado.prioridades, p],
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
        <CardTitle className="text-base">Filtros</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {total} evento{total === 1 ? "" : "s"}
          </span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2 text-xs"
            onClick={onLimpiar}
          >
            <X className="h-3.5 w-3.5" /> Limpiar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="filtro-desde">Desde</Label>
            <Input
              id="filtro-desde"
              type="date"
              value={estado.desde}
              onChange={(e) => setEstado({ ...estado, desde: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filtro-hasta">Hasta</Label>
            <Input
              id="filtro-hasta"
              type="date"
              value={estado.hasta}
              onChange={(e) => setEstado({ ...estado, hasta: e.target.value })}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Cobertura</Label>
          <div className="flex flex-wrap gap-1.5">
            {TIPOS_COBERTURA.map((t) => (
              <ChipToggle
                key={t.valor}
                activo={estado.tiposCobertura.includes(t.valor)}
                onClick={() => togglearCobertura(t.valor)}
              >
                {COBERTURA[t.valor].etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Prioridad</Label>
          <div className="flex flex-wrap gap-1.5">
            {PRIORIDADES.map((p) => (
              <ChipToggle
                key={p.valor}
                activo={estado.prioridades.includes(p.valor)}
                onClick={() => togglearPrioridad(p.valor)}
              >
                {p.etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Cambiado</Label>
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                { valor: "todos", etiqueta: "Todos" },
                { valor: "si", etiqueta: "Sí" },
                { valor: "no", etiqueta: "No" },
              ] as { valor: FiltroCambiado; etiqueta: string }[]
            ).map((opt) => (
              <ChipToggle
                key={opt.valor}
                activo={estado.cambiado === opt.valor}
                onClick={() => setEstado({ ...estado, cambiado: opt.valor })}
              >
                {opt.etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="filtro-q">Buscar</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="filtro-q"
              value={estado.q}
              onChange={(e) => setEstado({ ...estado, q: e.target.value })}
              placeholder="Buscar en título y qué sacar…"
              className="pl-8"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Eventos() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const estado = React.useMemo(() => leerFiltrosDesdeUrl(searchParams), [searchParams]);
  // Persistencia en URL: cada cambio refleja la URL (un refresh respeta el filtro).
  const setEstado = (next: ReturnType<typeof leerFiltrosDesdeUrl>) => {
    setSearchParams(filtrosAUrl(next), { replace: true });
  };
  const limpiar = () => setSearchParams(new URLSearchParams(), { replace: true });

  // La query depende de los filtros: se reejecuta cuando cambian (clave incluye el SP).
  const clave = [
    "rota",
    "eventos",
    estado.desde,
    estado.hasta,
    estado.tiposCobertura.join(","),
    estado.prioridades.join(","),
    estado.cambiado,
    estado.q,
  ] as const;
  const filtrosApi: Parameters<typeof api.rotaEventos>[0] = {
    desde: estado.desde || undefined,
    hasta: estado.hasta || undefined,
    tipo_cobertura: estado.tiposCobertura,
    prioridad: estado.prioridades,
    cambiado: estado.cambiado === "si" ? true : estado.cambiado === "no" ? false : undefined,
    q: estado.q || undefined,
  };
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.rotaEventos(filtrosApi, signal),
  });
  const eventos = q.data?.eventos ?? [];
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota", "eventos"] });

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevoEvento onCreado={invalidar} />
        <div className="space-y-3">
          <FiltrosEventos
            estado={estado}
            setEstado={setEstado}
            onLimpiar={limpiar}
            total={eventos.length}
          />
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
              texto="Ajusta los filtros o da de alta nuevos eventos con el formulario."
            />
          ) : (
            eventos.map((e) => <TarjetaEvento key={e.id} evento={e} onCambio={invalidar} />)
          )}
        </div>
      </div>
      {/* Piezas sueltas (#150): campanas evergreen sin evento, agrupadas por programa. */}
      <PiezasSueltas />
    </div>
  );
}

function NuevoEvento({ onCreado }: { onCreado: () => void }) {
  const [titulo, setTitulo] = React.useState("");
  const [fecha, setFecha] = React.useState("");
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>("transmision");
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>("media");

  const crear = useMutation({
    mutationFn: () =>
      api.crearEventoRota({
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        contenido: contenido.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
      }),
    onSuccess: () => {
      toast.success("Evento creado.");
      setTitulo("");
      setHora("");
      setContenido("");
      setTipoCobertura("transmision");
      setPrioridad("media");
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
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Cobertura</Label>
            <Select
              value={tipoCobertura}
              onValueChange={(v) => setTipoCobertura(v as TipoCoberturaEvento)}
            >
              <SelectTrigger aria-label="Tipo de cobertura">
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
              <SelectTrigger aria-label="Prioridad">
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
  const [panelAbierto, setPanelAbierto] = React.useState(false);
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Edición inline de cobertura/prioridad (cambiar cobertura reprograma -> "Cambió").
  const editar = useMutation({
    mutationFn: (cuerpo: { tipo_cobertura?: TipoCoberturaEvento; prioridad?: PrioridadEvento }) =>
      api.actualizarEventoRota(evento.id, cuerpo),
    onSuccess: () => onCambio(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cob = COBERTURA[evento.tipo_cobertura] ?? COBERTURA.transmision;
  const IconoCob = cob.icono;

  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{evento.titulo}</span>
            <Badge variant="outline" className={`gap-1 font-normal ${cob.chip}`}>
              <IconoCob className="h-3 w-3" /> {cob.etiqueta}
            </Badge>
            {evento.es_sabado && (
              <Badge variant="outline" className="font-normal">
                Sábado
              </Badge>
            )}
            {evento.cambiado && (
              <Badge variant="aviso" className="gap-1 font-normal">
                <BellRing className="h-3 w-3" /> Cambió
              </Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatearFechaCorta(evento.fecha)}
            {evento.hora ? ` · ${evento.hora}` : ""}
            {" · "}
            <span className={COLOR_PRIORIDAD[evento.prioridad]}>prioridad {evento.prioridad}</span>
          </div>
          {evento.contenido && (
            <div className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Qué sacar: </span>
              {evento.contenido}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Select
              value={evento.tipo_cobertura}
              onValueChange={(v) => editar.mutate({ tipo_cobertura: v as TipoCoberturaEvento })}
              disabled={editar.isPending}
            >
              <SelectTrigger aria-label="Cambiar cobertura" className="h-8 w-[11rem] text-xs">
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
            <Select
              value={evento.prioridad}
              onValueChange={(v) => editar.mutate({ prioridad: v as PrioridadEvento })}
              disabled={editar.isPending}
            >
              <SelectTrigger aria-label="Cambiar prioridad" className="h-8 w-[7rem] text-xs">
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
            {evento.cambiado && <BotonMarcarAvisado evento={evento} onCambio={onCambio} />}
            {/* Panel inferior expandible (NO modal): muestra las piezas asociadas al evento. */}
            <Button
              size="sm"
              variant="outline"
              className="h-8 gap-1.5 text-xs"
              onClick={() => setPanelAbierto((v) => !v)}
              aria-expanded={panelAbierto}
              aria-label={panelAbierto ? "Cerrar piezas" : "Abrir piezas"}
            >
              <ImageIcon className="h-3.5 w-3.5" />
              Piezas
              {panelAbierto ? (
                <ChevronUp className="h-3.5 w-3.5" />
              ) : (
                <ChevronDown className="h-3.5 w-3.5" />
              )}
            </Button>
          </div>
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
      {panelAbierto && (
        <div className="border-t bg-muted/30">
          <PanelPiezasEvento evento={evento} />
        </div>
      )}
    </Card>
  );
}

// --- Piezas de la parrilla (#150 PARRILLA 2026.xlsx) -----------------------
//
// Una pieza = un POST individual. Vive dentro de la pestana "Eventos": (a) panel inferior
// expandible por evento; (b) seccion colapsable al final para piezas sueltas (campanas
// evergreen sin evento). Reutiliza shadcn (Table, Input, Select, Checkbox, Button, Card).

function fechaInputAValor(fecha: string): string {
  // Input type="date" usa AAAA-MM-DD. Nuestro backend envia el mismo formato o "".
  return fecha;
}

function PanelPiezasEvento({ evento }: { evento: EventoRota }) {
  const queryClient = useQueryClient();
  const clave = ["rota", "piezas", "evento", evento.id] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.listarPiezasRota({ evento_id: evento.id }, signal),
  });
  const piezas = q.data?.piezas ?? [];
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });
  // Catálogo de programas (texto libre con autocomplete): consulta liviana, cacheable.
  const programasQ = useQuery({
    queryKey: ["rota", "programas"] as const,
    queryFn: ({ signal }) => api.listarProgramasRota({}, signal),
  });
  const programas = programasQ.data?.programas ?? [];

  return (
    <div className="space-y-3 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-muted-foreground">
          Piezas del evento ({piezas.length}). Una pieza = un post individual (pre-evento,
          reel, historia, post-evento…).
        </div>
        <FormularioNuevaPieza
          eventoIdInicial={evento.id}
          programas={programas}
          onCreada={invalidar}
          textoBoton="Nueva pieza"
        />
      </div>
      <TablaPiezas
        piezas={piezas}
        cargando={q.isPending}
        onCambio={invalidar}
        programas={programas}
      />
    </div>
  );
}

function TablaPiezas({
  piezas,
  cargando,
  onCambio,
  mostrarPrograma = false,
  seleccionados,
  onToggleSeleccionado,
  onToggleTodos,
  programas,
}: {
  piezas: PiezaRota[];
  cargando: boolean;
  onCambio: () => void;
  mostrarPrograma?: boolean;
  /** Si se pasa, la tabla muestra una columna de checkboxes para selección múltiple. */
  seleccionados?: Set<string>;
  onToggleSeleccionado?: (id: string) => void;
  onToggleTodos?: (todos: boolean) => void;
  /** Catálogo de programas para el autocomplete (opcional, solo en pestañas con CRUD). */
  programas?: { nombre: string }[];
}) {
  const muestraCheck = !!onToggleSeleccionado;
  const todosMarcados =
    muestraCheck && piezas.length > 0 && piezas.every((p) => seleccionados?.has(p.id));
  if (cargando) {
    return <Skeleton className="h-24 w-full rounded-md" />;
  }
  if (piezas.length === 0) {
    return (
      <div className="rounded-md border border-dashed bg-background p-4 text-center text-xs text-muted-foreground">
        Aún no hay piezas. Crea la primera con el botón de arriba.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-md border bg-background">
      <Table>
        <TableHeader>
          <TableRow>
            {muestraCheck && (
              <TableHead className="w-10">
                <Checkbox
                  aria-label="Seleccionar todas"
                  checked={todosMarcados}
                  onCheckedChange={(v) => onToggleTodos?.(v === true)}
                />
              </TableHead>
            )}
            {mostrarPrograma && <TableHead className="min-w-[10rem]">Programa</TableHead>}
            <TableHead className="min-w-[8rem]">Salida</TableHead>
            <TableHead className="min-w-[10rem]">Red</TableHead>
            <TableHead className="min-w-[8rem]">Tipo</TableHead>
            <TableHead className="min-w-[8rem]">Día</TableHead>
            <TableHead className="min-w-[6rem]">Hora</TableHead>
            <TableHead className="min-w-[8rem]">Estado</TableHead>
            <TableHead className="min-w-[5rem] text-center">Material</TableHead>
            <TableHead className="min-w-[6rem] text-center">Contenido</TableHead>
            <TableHead className="min-w-[6rem] text-center">Publicado</TableHead>
            <TableHead className="min-w-[16rem]">Contenido sugerido / Enlace</TableHead>
            <TableHead className="w-20" />
          </TableRow>
        </TableHeader>
        <TableBody>
          {piezas.map((p) => (
            <FilaPieza
              key={p.id}
              pieza={p}
              mostrarPrograma={mostrarPrograma}
              onCambio={onCambio}
              seleccionado={seleccionados?.has(p.id) ?? false}
              onToggleSeleccionado={onToggleSeleccionado}
              programas={programas}
            />
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function FilaPieza({
  pieza,
  mostrarPrograma,
  onCambio,
  seleccionado,
  onToggleSeleccionado,
  programas,
}: {
  pieza: PiezaRota;
  mostrarPrograma: boolean;
  onCambio: () => void;
  seleccionado: boolean;
  onToggleSeleccionado?: (id: string) => void;
  programas?: { nombre: string }[];
}) {
  const editar = useMutation({
    mutationFn: (cuerpo: CuerpoActualizarPiezaRota) => api.actualizarPiezaRota(pieza.id, cuerpo),
    onSuccess: () => onCambio(),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: () => api.eliminarPiezaRota(pieza.id),
    onSuccess: () => {
      toast.success("Pieza eliminada.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const duplicar = useMutation({
    mutationFn: () => api.duplicarPiezaRota(pieza.id),
    onSuccess: () => {
      toast.success("Pieza duplicada (workflow reseteado).");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardarTexto = (campo: keyof CuerpoActualizarPiezaRota, valor: string) => {
    if (valor === (pieza[campo as keyof PiezaRota] as string)) return;
    editar.mutate({ [campo]: valor } as CuerpoActualizarPiezaRota);
  };

  // Si la pieza es "always_on", `dia` y `hora_post` pierden sentido (sin fecha fija):
  // los deshabilitamos y avisamos con `title` para que la pista sea obvia.
  const tituloAlwaysOn = pieza.always_on
    ? "Pieza perenne (always-on): no se programa con fecha/hora fija."
    : "";

  return (
    <TableRow className={pieza.always_on ? "bg-emerald-50/30 dark:bg-emerald-950/10" : undefined}>
      {onToggleSeleccionado && (
        <TableCell className="align-top">
          <Checkbox
            aria-label={`Seleccionar pieza ${pieza.id}`}
            checked={seleccionado}
            onCheckedChange={() => onToggleSeleccionado(pieza.id)}
          />
        </TableCell>
      )}
      {mostrarPrograma && (
        <TableCell>
          <InputProgramaPieza
            valor={pieza.programa}
            programas={programas ?? []}
            onGuardar={(v) => guardarTexto("programa", v)}
          />
        </TableCell>
      )}
      <TableCell>
        <Input
          defaultValue={pieza.salida}
          placeholder="REDES / WEB / TV"
          onBlur={(e) => guardarTexto("salida", e.target.value.trim())}
          className="h-8 text-xs"
          maxLength={60}
        />
      </TableCell>
      <TableCell>
        <Input
          defaultValue={pieza.red_social}
          placeholder="FB, IG, X…"
          onBlur={(e) => guardarTexto("red_social", e.target.value.trim())}
          className="h-8 text-xs"
          maxLength={80}
        />
      </TableCell>
      <TableCell>
        <Input
          defaultValue={pieza.tipo_pieza}
          placeholder="IMAGEN / VIDEO…"
          onBlur={(e) => guardarTexto("tipo_pieza", e.target.value.trim())}
          className="h-8 text-xs"
          maxLength={60}
        />
      </TableCell>
      <TableCell>
        <Input
          type="date"
          defaultValue={fechaInputAValor(pieza.dia)}
          onBlur={(e) => guardarTexto("dia", e.target.value)}
          className="h-8 text-xs"
          disabled={pieza.always_on}
          title={tituloAlwaysOn}
        />
        {pieza.always_on && (
          <span className="text-[10px] text-emerald-700 dark:text-emerald-400">always-on</span>
        )}
      </TableCell>
      <TableCell>
        <Input
          defaultValue={pieza.hora_post}
          placeholder="17:30 / LINK VIVO"
          onBlur={(e) => guardarTexto("hora_post", e.target.value.trim())}
          className="h-8 text-xs"
          maxLength={40}
          disabled={pieza.always_on}
          title={tituloAlwaysOn}
        />
      </TableCell>
      <TableCell>
        <Select
          value={pieza.estado}
          onValueChange={(v) => editar.mutate({ estado: v as EstadoPieza })}
          disabled={editar.isPending}
        >
          <SelectTrigger aria-label="Estado" className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ESTADOS_PIEZA.map((e) => (
              <SelectItem key={e.valor} value={e.valor}>
                {e.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="text-center">
        <Checkbox
          checked={pieza.material_entregado}
          onCheckedChange={(v) => editar.mutate({ material_entregado: v })}
          aria-label="Material entregado"
        />
      </TableCell>
      <TableCell className="text-center">
        <Checkbox
          checked={pieza.contenido_entregado}
          onCheckedChange={(v) => editar.mutate({ contenido_entregado: v })}
          aria-label="Contenido entregado"
        />
      </TableCell>
      <TableCell className="text-center">
        <Checkbox
          checked={pieza.publicado}
          onCheckedChange={(v) => editar.mutate({ publicado: v })}
          aria-label="Publicado"
        />
      </TableCell>
      <TableCell>
        <div className="space-y-1">
          <Input
            defaultValue={pieza.contenido_sugerido}
            placeholder="Contenido sugerido"
            onBlur={(e) => guardarTexto("contenido_sugerido", e.target.value.trim())}
            className="h-8 text-xs"
            maxLength={500}
          />
          <Input
            defaultValue={pieza.enlace}
            placeholder="https://…"
            onBlur={(e) => guardarTexto("enlace", e.target.value.trim())}
            className="h-8 text-xs"
            maxLength={2000}
          />
          {pieza.comentarios && (
            <div className="rounded bg-muted/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
              <span className="font-semibold">Comentarios: </span>
              {pieza.comentarios}
            </div>
          )}
        </div>
      </TableCell>
      <TableCell>
        <div className="flex items-center gap-0.5">
          <Tooltip label="Duplicar (workflow reseteado)">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Duplicar pieza"
              className="h-8 w-8 text-muted-foreground hover:text-foreground"
              onClick={() => duplicar.mutate()}
              disabled={duplicar.isPending}
            >
              {duplicar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </Tooltip>
          <Tooltip label="Borrar pieza">
            <Button
              variant="ghost"
              size="icon"
              aria-label="Borrar pieza"
              className="h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={() => {
                if (window.confirm("¿Borrar esta pieza?")) borrar.mutate();
              }}
              disabled={borrar.isPending}
            >
              {borrar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </Button>
          </Tooltip>
        </div>
      </TableCell>
    </TableRow>
  );
}

/**
 * Input de `programa` con datalist de autocomplete contra el catálogo. Permite
 * escribir un nombre nuevo (texto libre): si no existe en el catálogo, la pieza
 * conserva ese texto, pero al pasar el blur damos un atajo "crear programa" si
 * el nombre no está. Para mantener el componente compacto, el botón "crear" lo
 * surfa el panel padre (`Programas`). Aquí solo persistimos el texto.
 */
function InputProgramaPieza({
  valor,
  programas,
  onGuardar,
}: {
  valor: string;
  programas: { nombre: string }[];
  onGuardar: (v: string) => void;
}) {
  const listId = React.useId();
  return (
    <>
      <Input
        defaultValue={valor}
        placeholder="Campaña / programa"
        onBlur={(e) => onGuardar(e.target.value.trim())}
        className="h-8 text-xs"
        maxLength={200}
        list={listId}
      />
      <datalist id={listId}>
        {programas.map((p) => (
          <option key={p.nombre} value={p.nombre} />
        ))}
      </datalist>
    </>
  );
}

/**
 * Selector con autocomplete del campo `programa` para alta de pieza.
 *
 * - Si hay catálogo, muestra las opciones que matchean lo escrito; el usuario
 *   puede escribir cualquier texto (queda libre).
 * - Si el texto no coincide con ningún programa del catálogo, ofrecemos crearlo
 *   al vuelo (`POST /api/rota/programas`) y lo seleccionamos.
 * - Degradación: si la lista llega vacía o falla, el input se comporta como
 *   campo de texto libre como antes.
 */
function SelectorProgramaPieza({
  valor,
  programas,
  onCambio,
  onCreado,
}: {
  valor: string;
  programas: ProgramaRota[] | { nombre: string }[];
  onCambio: (v: string) => void;
  onCreado: (nuevo: string) => void;
}) {
  const listId = React.useId();
  // Filtramos los inactivos si el catálogo viene con `activo` (modo `ProgramaRota[]`).
  // En modo legado `{nombre}[]` (no debería pasar aquí, pero por defensa) los mostramos
  // todos.
  const opciones = React.useMemo(() => {
    const todos = programas as Array<{ nombre: string; activo?: boolean }>;
    return todos.filter((p) => (p.activo === undefined ? true : p.activo));
  }, [programas]);
  const limpio = valor.trim();
  const existeExacto = opciones.some(
    (p) => p.nombre.localeCompare(limpio, undefined, { sensitivity: "accent" }) === 0,
  );
  const puedeCrear = limpio.length > 0 && !existeExacto;

  const queryClient = useQueryClient();
  const crear = useMutation({
    mutationFn: () => api.crearProgramaRota({ nombre: limpio }),
    onSuccess: (res) => {
      // Invalida TODAS las queries del catálogo (con/sin filtro `activo`) para que
      // el nuevo programa aparezca en otros sitios que ya estén renderizados.
      void queryClient.invalidateQueries({ queryKey: ["rota", "programas"] });
      toast.success(`Programa «${res.programa.nombre}» creado.`);
      onCreado(res.programa.nombre);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="space-y-1.5">
      <Input
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
        placeholder="Álvaro Fidalgo, MUNDIAL…"
        maxLength={200}
        className="h-8 text-xs"
        list={listId}
        autoComplete="off"
      />
      <datalist id={listId}>
        {opciones.map((p) => (
          <option key={p.nombre} value={p.nombre} />
        ))}
      </datalist>
      {puedeCrear && (
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 w-full justify-start px-2 text-xs text-muted-foreground hover:text-foreground"
          onClick={() => crear.mutate()}
          disabled={crear.isPending}
        >
          {crear.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Plus className="h-3 w-3" />
          )}
          Crear programa «{limpio}»
        </Button>
      )}
    </div>
  );
}

function FormularioNuevaPieza({
  eventoIdInicial = "",
  programaInicial = "",
  programas = [],
  onCreada,
  textoBoton,
  conPrograma = false,
}: {
  eventoIdInicial?: string;
  programaInicial?: string;
  /** Catálogo para el selector + autocomplete del campo `programa`. Si se pasa
   * `ProgramaRota[]`, se filtran los inactivos; si solo se pasa `{nombre}[]`, se
   * muestran todos (modo legado: filas inline de la tabla). */
  programas?: ProgramaRota[] | { nombre: string }[];
  onCreada: () => void;
  textoBoton: string;
  conPrograma?: boolean;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const [programa, setPrograma] = React.useState(programaInicial);
  const [redSocial, setRedSocial] = React.useState("");
  const [tipoPieza, setTipoPieza] = React.useState("");
  const [salida, setSalida] = React.useState("");
  const [dia, setDia] = React.useState("");
  const [horaPost, setHoraPost] = React.useState("");
  const [contenidoSugerido, setContenidoSugerido] = React.useState("");
  const [comentarios, setComentarios] = React.useState("");
  const [fechaEntregaMaterial, setFechaEntregaMaterial] = React.useState("");
  const [alwaysOn, setAlwaysOn] = React.useState(false);
  const alwaysOnId = React.useId();

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearPiezaRota = {
        evento_id: eventoIdInicial || undefined,
        programa: programa.trim() || undefined,
        red_social: redSocial.trim() || undefined,
        tipo_pieza: tipoPieza.trim() || undefined,
        salida: salida.trim() || undefined,
        dia: alwaysOn ? "" : dia || undefined,
        hora_post: alwaysOn ? "" : horaPost.trim() || undefined,
        contenido_sugerido: contenidoSugerido.trim() || undefined,
        comentarios: comentarios.trim() || undefined,
        fecha_entrega_material: fechaEntregaMaterial || undefined,
        always_on: alwaysOn || undefined,
      };
      return api.crearPiezaRota(cuerpo);
    },
    onSuccess: () => {
      toast.success("Pieza creada.");
      // Limpiamos los campos editables (mantenemos `eventoIdInicial` que viene del evento).
      setPrograma(programaInicial);
      setRedSocial("");
      setTipoPieza("");
      setSalida("");
      setDia("");
      setHoraPost("");
      setContenidoSugerido("");
      setComentarios("");
      setFechaEntregaMaterial("");
      setAlwaysOn(false);
      setAbierto(false);
      onCreada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Al menos uno entre evento, programa o contenido_sugerido (el back lo valida; aqui
  // pre-validamos para que el boton se vea claro).
  const puedeCrear =
    Boolean(eventoIdInicial) ||
    programa.trim().length > 0 ||
    contenidoSugerido.trim().length > 0;

  if (!abierto) {
    return (
      <Button size="sm" variant="outline" onClick={() => setAbierto(true)}>
        <Plus className="h-3.5 w-3.5" /> {textoBoton}
      </Button>
    );
  }

  return (
    <div className="w-full rounded-md border bg-background p-3 space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {conPrograma && (
          <div className="space-y-1.5">
            <Label className="text-xs">Programa / campaña</Label>
            <SelectorProgramaPieza
              valor={programa}
              programas={programas}
              onCambio={setPrograma}
              onCreado={(nuevo) => {
                onCreada();
                setPrograma(nuevo);
              }}
            />
          </div>
        )}
        <div className="space-y-1.5">
          <Label className="text-xs">Salida (canal amplio)</Label>
          <Input
            value={salida}
            onChange={(e) => setSalida(e.target.value)}
            placeholder="REDES / WEB / TV / OTROS"
            maxLength={60}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Red social</Label>
          <Input
            value={redSocial}
            onChange={(e) => setRedSocial(e.target.value)}
            placeholder="FB, IG, X / HISTORIA / IG, TK (REEL)"
            maxLength={80}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Tipo</Label>
          <Input
            value={tipoPieza}
            onChange={(e) => setTipoPieza(e.target.value)}
            placeholder="IMAGEN / VIDEO / REEL"
            maxLength={60}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Día</Label>
          <Input
            type="date"
            value={dia}
            onChange={(e) => setDia(e.target.value)}
            className="h-8 text-xs"
            disabled={alwaysOn}
            title={alwaysOn ? "Las piezas perennes no tienen fecha fija." : ""}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Hora</Label>
          <Input
            value={horaPost}
            onChange={(e) => setHoraPost(e.target.value)}
            placeholder="17:30 o LINK VIVO"
            maxLength={40}
            className="h-8 text-xs"
            disabled={alwaysOn}
            title={alwaysOn ? "Las piezas perennes no tienen hora fija." : ""}
          />
        </div>
        <div className="space-y-1.5">
          <Label className="text-xs">Entrega del material</Label>
          <Input
            type="date"
            value={fechaEntregaMaterial}
            onChange={(e) => setFechaEntregaMaterial(e.target.value)}
            className="h-8 text-xs"
            title="Deadline interno para entregar el material a producción"
          />
        </div>
        <div className="flex items-center gap-2 self-end pb-1">
          <Checkbox
            id={`pieza-alwayson-${alwaysOnId}`}
            checked={alwaysOn}
            onCheckedChange={(v) => setAlwaysOn(v === true)}
          />
          <Label
            htmlFor={`pieza-alwayson-${alwaysOnId}`}
            className="cursor-pointer text-xs font-normal"
          >
            Always-on (perenne, sin fecha fija)
          </Label>
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="text-xs">Contenido sugerido</Label>
          <Textarea
            value={contenidoSugerido}
            onChange={(e) => setContenidoSugerido(e.target.value)}
            placeholder="Pre-evento, reel del gol, 5:15 LINK VIVO…"
            rows={2}
            maxLength={500}
            className="text-xs"
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label className="text-xs">Comentarios de coordinación</Label>
          <Textarea
            value={comentarios}
            onChange={(e) => setComentarios(e.target.value)}
            placeholder="Notas internas: avisar a producción, formato, dependencias…"
            rows={2}
            maxLength={1000}
            className="text-xs"
          />
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setAbierto(false)}>
          Cancelar
        </Button>
        <Button
          size="sm"
          onClick={() => crear.mutate()}
          disabled={!puedeCrear || crear.isPending}
        >
          {crear.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          Crear pieza
        </Button>
      </div>
    </div>
  );
}

function PiezasSueltas() {
  const [abierto, setAbierto] = React.useState(false);
  const queryClient = useQueryClient();
  const clave = ["rota", "piezas", "sueltas"] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.listarPiezasRota({ evento_id: "" }, signal),
    enabled: abierto,
  });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: clave });
  const programasQ = useQuery({
    queryKey: ["rota", "programas"] as const,
    queryFn: ({ signal }) => api.listarProgramasRota({}, signal),
    enabled: abierto,
  });
  const programas = programasQ.data?.programas ?? [];

  // --- Filtros (client-side: el backend no acepta always_on / salida) ---
  const [filtroAlwaysOn, setFiltroAlwaysOn] = React.useState<"todas" | "solo" | "excluir">(
    "todas",
  );
  const [filtroSalida, setFiltroSalida] = React.useState("");
  const [filtroPrograma, setFiltroPrograma] = React.useState("");

  // Selección múltiple para borrado en lote.
  const [seleccionados, setSeleccionados] = React.useState<Set<string>>(new Set());
  const limpiarSeleccion = () => setSeleccionados(new Set());

  const todasPiezas = q.data?.piezas ?? [];
  const piezasFiltradas = React.useMemo(() => {
    const salidaQ = filtroSalida.trim().toLowerCase();
    const programaQ = filtroPrograma.trim().toLowerCase();
    return todasPiezas.filter((p) => {
      if (filtroAlwaysOn === "solo" && !p.always_on) return false;
      if (filtroAlwaysOn === "excluir" && p.always_on) return false;
      if (salidaQ && !(p.salida || "").toLowerCase().includes(salidaQ)) return false;
      if (programaQ && !(p.programa || "").toLowerCase().includes(programaQ)) return false;
      return true;
    });
  }, [todasPiezas, filtroAlwaysOn, filtroSalida, filtroPrograma]);

  // Agrupamos por programa (las piezas sueltas son campañas evergreen).
  const grupos = React.useMemo(() => {
    const m = new Map<string, PiezaRota[]>();
    for (const p of piezasFiltradas) {
      const k = p.programa || "(sin programa)";
      const lista = m.get(k) ?? [];
      lista.push(p);
      m.set(k, lista);
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [piezasFiltradas]);

  const toggleSeleccionado = (id: string) =>
    setSeleccionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleTodosGrupo = (ids: string[], marcarTodos: boolean) =>
    setSeleccionados((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (marcarTodos) next.add(id);
        else next.delete(id);
      }
      return next;
    });

  const borrarLote = useMutation({
    mutationFn: () => api.borrarPiezasLote({ ids: [...seleccionados] }),
    onSuccess: (res) => {
      const ne = res.no_encontrados?.length ?? 0;
      toast.success(
        ne > 0
          ? `Borradas ${res.borrados} piezas (${ne} ya no existían).`
          : `Borradas ${res.borrados} piezas.`,
      );
      limpiarSeleccion();
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Card>
      <CardHeader className="cursor-pointer pb-3" onClick={() => setAbierto((v) => !v)}>
        <CardTitle className="flex items-center gap-2 text-base">
          {abierto ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          Piezas sueltas / programas
          <span className="ml-auto text-xs font-normal text-muted-foreground">
            Campañas evergreen sin evento (Álvaro Fidalgo, MUNDIAL, Paty Cantú…)
          </span>
        </CardTitle>
      </CardHeader>
      {abierto && (
        <CardContent className="space-y-4">
          {/* Filtros + alta. */}
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label className="text-xs">Always-on</Label>
              <div className="flex gap-1">
                {(
                  [
                    { v: "todas", l: "Todas" },
                    { v: "solo", l: "Solo perennes" },
                    { v: "excluir", l: "Sin perennes" },
                  ] as { v: typeof filtroAlwaysOn; l: string }[]
                ).map((opt) => (
                  <Button
                    key={opt.v}
                    size="sm"
                    variant={filtroAlwaysOn === opt.v ? "default" : "outline"}
                    className="h-7 px-2 text-xs"
                    onClick={() => setFiltroAlwaysOn(opt.v)}
                  >
                    {opt.l}
                  </Button>
                ))}
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="filt-salida">Salida (substring)</Label>
              <Input
                id="filt-salida"
                value={filtroSalida}
                onChange={(e) => setFiltroSalida(e.target.value)}
                placeholder="REDES, WEB…"
                className="h-7 w-40 text-xs"
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs" htmlFor="filt-programa">Programa (substring)</Label>
              <Input
                id="filt-programa"
                value={filtroPrograma}
                onChange={(e) => setFiltroPrograma(e.target.value)}
                placeholder="MUNDIAL…"
                className="h-7 w-40 text-xs"
                list="filt-programa-options"
              />
              <datalist id="filt-programa-options">
                {programas.map((p) => (
                  <option key={p.id} value={p.nombre} />
                ))}
              </datalist>
            </div>
            <div className="ml-auto">
              <FormularioNuevaPieza
                onCreada={invalidar}
                programas={programas}
                textoBoton="Pieza suelta"
                conPrograma
              />
            </div>
          </div>

          {/* Barra de selección múltiple. */}
          {seleccionados.size > 0 && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-2 text-sm">
              <span className="font-medium">Seleccionadas {seleccionados.size}</span>
              <Button
                size="sm"
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => {
                  if (
                    window.confirm(
                      `¿Borrar ${seleccionados.size} pieza${
                        seleccionados.size === 1 ? "" : "s"
                      }?`,
                    )
                  )
                    borrarLote.mutate();
                }}
                disabled={borrarLote.isPending}
              >
                {borrarLote.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
                Borrar selección
              </Button>
              <Button size="sm" variant="ghost" onClick={limpiarSeleccion}>
                <X className="h-3.5 w-3.5" /> Limpiar
              </Button>
            </div>
          )}

          {q.isPending ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : grupos.length === 0 ? (
            <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
              Sin coincidencias. Ajusta filtros o crea piezas sueltas con el botón.
            </div>
          ) : (
            grupos.map(([programa, lista]) => (
              <div key={programa} className="space-y-2">
                <div className="text-sm font-medium">{programa}</div>
                <TablaPiezas
                  piezas={lista}
                  cargando={false}
                  onCambio={invalidar}
                  mostrarPrograma
                  seleccionados={seleccionados}
                  onToggleSeleccionado={toggleSeleccionado}
                  onToggleTodos={(todos) =>
                    toggleTodosGrupo(
                      lista.map((p) => p.id),
                      todos,
                    )
                  }
                  programas={programas}
                />
              </div>
            ))
          )}
        </CardContent>
      )}
    </Card>
  );
}

// --- Pestaña: cambios de turno entre compañeros (#175) --------------------
//
// Flujo (todo lo orquesta el backend; el cliente solo informa):
//   A (solicitante) crea -> B (destinatario) acepta/rechaza -> admin aprueba
//   (ejecuta el swap sobre `rota_turnos_trabajo`) o rechaza. A puede cancelar
//   mientras el estado no sea terminal (terminales: aplicado, rechazado,
//   rechazado_admin, cancelado).

/** Etiqueta legible para cada estado del swap (es-MX, voz del producto). */
const ETIQUETA_ESTADO_SWAP: Record<EstadoSwap, string> = {
  propuesto: "Pendiente de su respuesta",
  aceptado: "Aceptado · espera a Elías",
  aprobado: "Aprobado por Elías",
  aplicado: "Aplicado al horario",
  rechazado: "Rechazado por el compañero",
  rechazado_admin: "Rechazado por Elías",
  cancelado: "Cancelado",
};

/** Variante visual del Badge para cada estado del swap. */
const VARIANTE_ESTADO_SWAP: Record<
  EstadoSwap,
  "aviso" | "secondary" | "ok" | "error"
> = {
  propuesto: "aviso",
  aceptado: "secondary",
  aprobado: "ok",
  aplicado: "ok",
  rechazado: "error",
  rechazado_admin: "error",
  cancelado: "error",
};

/** Estados terminales: el swap ya no admite más acciones (solo historial). */
const ESTADOS_TERMINALES_SWAP: ReadonlySet<EstadoSwap> = new Set([
  "aplicado",
  "rechazado",
  "rechazado_admin",
  "cancelado",
]);

const FRANJAS_SWAP: { valor: FranjaTurno; etiqueta: string }[] = [
  { valor: "matutino", etiqueta: "Mañana" },
  { valor: "vespertino", etiqueta: "Tarde" },
  { valor: "descanso", etiqueta: "Descanso" },
];

/** Formatea un timestamp ISO ("2026-05-25T18:42:11") como fecha-hora corta es-MX. */
function formatearMomentoCorto(s: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleString("es-MX", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Swaps({ esAdmin }: { esAdmin: boolean }) {
  const { usuario } = useSesion();
  // Sin sesión (token de mantenimiento) no hay "yo": el backend devuelve [] para
  // las consultas con `mio=true`. Lo decimos honestamente y no listamos nada.
  if (!usuario) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">
          Inicia sesión para gestionar tus cambios de turno con el equipo.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <FormularioNuevoSwap miId={usuario.id} />
      <SeccionSwaps
        titulo="Por responder"
        descripcion="Compañeros que te piden un cambio. Acepta o rechaza."
        icono={ArrowLeftRight}
        filtros={{ destinatario_id: usuario.id, estado: "propuesto" }}
        miId={usuario.id}
        esAdmin={esAdmin}
        vacio="No tienes solicitudes esperando tu respuesta."
      />
      <SeccionSwaps
        titulo="Solicité"
        descripcion="Cambios que pediste tú. Puedes cancelar mientras no sean terminales."
        icono={Send}
        filtros={{ solicitante_id: usuario.id }}
        soloEstados="no_terminales"
        miId={usuario.id}
        esAdmin={esAdmin}
        vacio="No tienes solicitudes activas. Pide un cambio con el formulario de arriba."
      />
      {esAdmin && (
        <SeccionSwaps
          titulo="Para aprobar"
          descripcion="Cambios que ya aceptaron entre compañeros: tú decides si se aplican al horario."
          icono={ShieldCheck}
          filtros={{ estado: "aceptado" }}
          miId={usuario.id}
          esAdmin={esAdmin}
          vacio="No hay cambios pendientes de tu aprobación."
        />
      )}
      <SeccionSwaps
        titulo="Historial"
        descripcion="Tus cambios ya cerrados (aplicados, rechazados o cancelados)."
        icono={Clock}
        filtros={{ mio: true }}
        soloEstados="terminales"
        miId={usuario.id}
        esAdmin={esAdmin}
        vacio="Aún no tienes cambios cerrados."
      />
    </div>
  );
}

function FormularioNuevoSwap({ miId }: { miId: string }) {
  const queryClient = useQueryClient();
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const equipo = (equipoQ.data?.equipo ?? []).filter((m) => m.id !== miId);

  const [destinatarioId, setDestinatarioId] = React.useState("");
  const [fechaA, setFechaA] = React.useState("");
  const [franjaA, setFranjaA] = React.useState<FranjaTurno>("matutino");
  const [fechaB, setFechaB] = React.useState("");
  const [franjaB, setFranjaB] = React.useState<FranjaTurno>("matutino");
  const [motivo, setMotivo] = React.useState("");

  const destinatario = equipo.find((m) => m.id === destinatarioId);

  const crear = useMutation({
    mutationFn: () =>
      api.crearSwap({
        destinatario_id: destinatarioId,
        fecha_a: fechaA,
        franja_a: franjaA,
        fecha_b: fechaB,
        franja_b: franjaB,
        motivo: motivo.trim(),
      }),
    onSuccess: () => {
      toast.success("Solicitud enviada. Tu compañero la verá en su lista de 'Por responder'.");
      setDestinatarioId("");
      setFechaA("");
      setFranjaA("matutino");
      setFechaB("");
      setFranjaB("matutino");
      setMotivo("");
      void queryClient.invalidateQueries({ queryKey: ["rota", "swaps"] });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear =
    destinatarioId !== "" &&
    fechaA !== "" &&
    fechaB !== "" &&
    !crear.isPending;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <ArrowLeftRight className="h-4 w-4" /> Pedir cambio de turno
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label>Compañero/a</Label>
          <Select value={destinatarioId} onValueChange={setDestinatarioId}>
            <SelectTrigger aria-label="Compañero al que pides el cambio">
              <SelectValue placeholder="Elige a un compañero/a" />
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
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-3 rounded-md border bg-muted/30 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Mi turno
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="swap-fecha-a">Día</Label>
              <Input
                id="swap-fecha-a"
                type="date"
                value={fechaA}
                onChange={(e) => setFechaA(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Franja</Label>
              <Select value={franjaA} onValueChange={(v) => setFranjaA(v as FranjaTurno)}>
                <SelectTrigger aria-label="Franja de mi turno">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FRANJAS_SWAP.map((f) => (
                    <SelectItem key={f.valor} value={f.valor}>
                      {f.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-3 rounded-md border bg-muted/30 p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Turno de {destinatario?.nombre || "tu compañero/a"}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="swap-fecha-b">Día</Label>
              <Input
                id="swap-fecha-b"
                type="date"
                value={fechaB}
                onChange={(e) => setFechaB(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Franja</Label>
              <Select value={franjaB} onValueChange={(v) => setFranjaB(v as FranjaTurno)}>
                <SelectTrigger aria-label="Franja del turno del compañero">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FRANJAS_SWAP.map((f) => (
                    <SelectItem key={f.valor} value={f.valor}>
                      {f.etiqueta}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="swap-motivo">
            Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="swap-motivo"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej. Cita médica, evento familiar, examen…"
            rows={2}
            maxLength={500}
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Solicitar cambio
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Una sección de la pestaña de Swaps: lista filtrada de tarjetas, con un filtro
 * adicional cliente (`soloEstados`) para dividir "Solicité" entre activos y los
 * "Historial" (terminales), reaprovechando la misma consulta backend.
 */
function SeccionSwaps({
  titulo,
  descripcion,
  icono: Icono,
  filtros,
  soloEstados,
  miId,
  esAdmin,
  vacio,
}: {
  titulo: string;
  descripcion: string;
  icono: typeof ArrowLeftRight;
  filtros: FiltrosSwaps;
  /** Filtro extra cliente: deja solo (no_)terminales. Sin valor = sin filtro. */
  soloEstados?: "terminales" | "no_terminales";
  miId: string;
  esAdmin: boolean;
  vacio: string;
}) {
  const clave = ["rota", "swaps", filtros] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.listarSwaps(filtros, signal),
  });

  const swaps = React.useMemo(() => {
    const todos = q.data?.swaps ?? [];
    if (!soloEstados) return todos;
    const esTerminal = (s: SwapTurno) => ESTADOS_TERMINALES_SWAP.has(s.estado);
    return soloEstados === "terminales" ? todos.filter(esTerminal) : todos.filter((s) => !esTerminal(s));
  }, [q.data, soloEstados]);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icono className="h-4 w-4" /> {titulo}
          <span className="ml-2 text-xs font-normal text-muted-foreground">
            {descripcion}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {q.isPending ? (
          <Skeleton className="h-24 w-full rounded-md" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudieron cargar los cambios de turno"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : swaps.length === 0 ? (
          <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
            {vacio}
          </div>
        ) : (
          swaps.map((s) => (
            <TarjetaSwap key={s.id} swap={s} miId={miId} esAdmin={esAdmin} />
          ))
        )}
      </CardContent>
    </Card>
  );
}

/** Una tarjeta con los datos de un swap y los botones de acción según contexto. */
function TarjetaSwap({
  swap,
  miId,
  esAdmin,
}: {
  swap: SwapTurno;
  miId: string;
  esAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "swaps"] });

  const soyDestinatario = swap.destinatario_id === miId;
  const soySolicitante = swap.solicitante_id === miId;
  const esTerminal = ESTADOS_TERMINALES_SWAP.has(swap.estado);

  // Qué acciones puede ejecutar el usuario en este swap, en este estado.
  // El backend revalida; aquí solo decidimos qué BOTONES enseñar.
  const puedeAceptarRechazarDestinatario =
    soyDestinatario && swap.estado === "propuesto";
  const puedeAprobarAdmin = esAdmin && swap.estado === "aceptado";
  const puedeCancelar = soySolicitante && !esTerminal;

  const cancelar = useMutation({
    mutationFn: () => api.cancelarSwap(swap.id),
    onSuccess: () => {
      toast.success("Solicitud cancelada.");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <div className="rounded-md border bg-card p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="font-medium">{swap.solicitante_nombre}</span>
            <ArrowLeftRight className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="font-medium">{swap.destinatario_nombre}</span>
          </div>
          <div className="text-xs text-muted-foreground">
            <span>
              {formatearFechaCorta(swap.fecha_a)} · {ETIQUETA_FRANJA[swap.franja_a]}
            </span>
            <span className="mx-1.5">↔</span>
            <span>
              {formatearFechaCorta(swap.fecha_b)} · {ETIQUETA_FRANJA[swap.franja_b]}
            </span>
          </div>
        </div>
        <Badge variant={VARIANTE_ESTADO_SWAP[swap.estado]}>
          {ETIQUETA_ESTADO_SWAP[swap.estado]}
        </Badge>
      </div>

      {swap.motivo && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Motivo ·{" "}
          </span>
          <span className="text-muted-foreground">{swap.motivo}</span>
        </div>
      )}
      {swap.respuesta_destinatario && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Respuesta de {swap.destinatario_nombre} ·{" "}
          </span>
          <span className="text-muted-foreground">{swap.respuesta_destinatario}</span>
        </div>
      )}
      {swap.respuesta_admin && (
        <div className="text-sm">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Nota de Elías ·{" "}
          </span>
          <span className="text-muted-foreground">{swap.respuesta_admin}</span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>Creado: {formatearMomentoCorto(swap.creado)}</span>
        {swap.decidido_destinatario && (
          <span>· Respondió el compañero: {formatearMomentoCorto(swap.decidido_destinatario)}</span>
        )}
        {swap.decidido_admin && (
          <span>· Decisión admin: {formatearMomentoCorto(swap.decidido_admin)}</span>
        )}
        {swap.aplicado && (
          <span>· Aplicado: {formatearMomentoCorto(swap.aplicado)}</span>
        )}
      </div>

      {(puedeAceptarRechazarDestinatario || puedeAprobarAdmin || puedeCancelar) && (
        <div className="flex flex-wrap justify-end gap-2 pt-1">
          {puedeAceptarRechazarDestinatario && (
            <>
              <DialogAccionSwap
                swapId={swap.id}
                accion="aceptar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm">
                    <Check className="h-4 w-4" /> Aceptar
                  </Button>
                }
              />
              <DialogAccionSwap
                swapId={swap.id}
                accion="rechazar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="outline">
                    <X className="h-4 w-4" /> Rechazar
                  </Button>
                }
              />
            </>
          )}
          {puedeAprobarAdmin && (
            <>
              <DialogAccionSwap
                swapId={swap.id}
                accion="aprobar"
                onCambio={invalidar}
                trigger={
                  <Button size="sm">
                    <ShieldCheck className="h-4 w-4" /> Aprobar y aplicar
                  </Button>
                }
              />
              <DialogAccionSwap
                swapId={swap.id}
                accion="rechazar_admin"
                onCambio={invalidar}
                trigger={
                  <Button size="sm" variant="outline">
                    <Shield className="h-4 w-4" /> Rechazar
                  </Button>
                }
              />
            </>
          )}
          {puedeCancelar && (
            <Button
              size="sm"
              variant="ghost"
              className="text-muted-foreground hover:text-destructive"
              onClick={() => cancelar.mutate()}
              disabled={cancelar.isPending}
            >
              {cancelar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
              Cancelar solicitud
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Diálogo de confirmación para aceptar/rechazar/aprobar/rechazar-admin un swap.
 * Pide una nota opcional ("respuesta") antes de mandar la mutación. El backend
 * valida estado, identidad y rol; aquí solo informamos.
 */
function DialogAccionSwap({
  swapId,
  accion,
  onCambio,
  trigger,
}: {
  swapId: string;
  accion: "aceptar" | "rechazar" | "aprobar" | "rechazar_admin";
  onCambio: () => void;
  trigger: React.ReactNode;
}) {
  const [abierto, setAbierto] = React.useState(false);
  const [respuesta, setRespuesta] = React.useState("");

  // Cada acción tiene su título, llamada API y texto del botón confirmar.
  const META: Record<
    typeof accion,
    {
      titulo: string;
      descripcion: string;
      botonConfirmar: string;
      llamar: (cuerpo: { respuesta?: string }) => Promise<unknown>;
      toastOk: string;
      placeholder: string;
    }
  > = {
    aceptar: {
      titulo: "Aceptar el cambio",
      descripcion:
        "Confirmas que puedes cubrir el turno de tu compañero. Aún falta que Elías lo apruebe.",
      botonConfirmar: "Aceptar",
      llamar: (cuerpo) => api.aceptarSwap(swapId, cuerpo),
      toastOk: "Cambio aceptado. Espera la aprobación de Elías.",
      placeholder: "Sin problema, yo te cubro…",
    },
    rechazar: {
      titulo: "Rechazar el cambio",
      descripcion: "Rechazas el cambio que te pidió tu compañero. Puedes dejarle el motivo.",
      botonConfirmar: "Rechazar",
      llamar: (cuerpo) => api.rechazarSwap(swapId, cuerpo),
      toastOk: "Cambio rechazado.",
      placeholder: "No puedo ese día porque…",
    },
    aprobar: {
      titulo: "Aprobar y aplicar el cambio",
      descripcion:
        "Vas a intercambiar los turnos en el horario del equipo. Si los turnos han cambiado a mano desde la solicitud, la consola lo avisará y no aplicará nada.",
      botonConfirmar: "Aprobar y aplicar",
      llamar: (cuerpo) => api.aprobarSwap(swapId, cuerpo),
      toastOk: "Cambio aprobado y aplicado al horario.",
      placeholder: "Ojo con el relevo / nota interna…",
    },
    rechazar_admin: {
      titulo: "Rechazar el cambio (admin)",
      descripcion: "Vas a rechazar el cambio aunque tus compañeros ya lo hubieran acordado.",
      botonConfirmar: "Rechazar",
      llamar: (cuerpo) => api.rechazarSwapAdmin(swapId, cuerpo),
      toastOk: "Cambio rechazado.",
      placeholder: "Ese día necesitamos a… en transmisión.",
    },
  };
  const meta = META[accion];

  const mutar = useMutation({
    mutationFn: () => meta.llamar({ respuesta: respuesta.trim() }),
    onSuccess: () => {
      toast.success(meta.toastOk);
      setRespuesta("");
      setAbierto(false);
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <>
      <span onClick={() => setAbierto(true)}>{trigger}</span>
      <Dialog open={abierto} onOpenChange={setAbierto}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{meta.titulo}</DialogTitle>
            <DialogDescription>{meta.descripcion}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor={`resp-${swapId}-${accion}`}>
              Respuesta <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id={`resp-${swapId}-${accion}`}
              value={respuesta}
              onChange={(e) => setRespuesta(e.target.value)}
              placeholder={meta.placeholder}
              rows={3}
              maxLength={500}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
            <Button onClick={() => mutar.mutate()} disabled={mutar.isPending}>
              {mutar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              {meta.botonConfirmar}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// --- Pestaña: catálogo de programas (#150, PARRILLA 2026.xlsx) -------------
//
// Cada hoja EVERGREEN del Excel ("Álvaro Fidalgo", "MUNDIAL", "Paty Cantú"…) es un
// PROGRAMA. Las piezas referencian programas POR NOMBRE: renombrar dispara cascada
// transparente en `rota_piezas.programa`. Borrar un programa en uso pide forzar
// (las piezas huérfanas siguen mostrando el nombre textual). Activo/inactivo solo
// filtra el autocomplete en `FormularioNuevaPieza` (las piezas existentes no se
// tocan).

function Programas() {
  const queryClient = useQueryClient();
  const [soloActivos, setSoloActivos] = React.useState(false);
  const clave = ["rota", "programas", soloActivos ? "activos" : "todos"] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.listarProgramasRota(soloActivos ? { activo: true } : {}, signal),
  });
  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["rota", "programas"] });
  };
  const programas = q.data?.programas ?? [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="flex flex-row items-start justify-between gap-2">
          <div>
            <CardTitle className="text-base">Catálogo de programas</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              Campañas evergreen del Excel «PARRILLA 2026» (Álvaro Fidalgo, MUNDIAL,
              Paty Cantú…). Las piezas las referencian por nombre: al renombrar, la
              consola actualiza todas las piezas en una sola transacción.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Checkbox
              id="prog-solo-activos"
              checked={soloActivos}
              onCheckedChange={(v) => setSoloActivos(v === true)}
            />
            <Label htmlFor="prog-solo-activos" className="cursor-pointer font-normal">
              Solo activos
            </Label>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <NuevoPrograma onCreado={invalidar} />
          {q.isPending ? (
            <Skeleton className="h-32 w-full rounded-md" />
          ) : q.isError ? (
            <BloqueError
              titulo="No se pudo cargar el catálogo"
              mensaje={mensajeError(q.error)}
              onReintentar={() => void q.refetch()}
              cargando={q.isFetching}
            />
          ) : programas.length === 0 ? (
            <EstadoVacio
              icono={CalendarPlus}
              titulo="Sin programas"
              texto="Da de alta un programa con el formulario de arriba para que aparezca en el autocomplete de piezas."
            />
          ) : (
            <div className="overflow-x-auto rounded-md border bg-background">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="min-w-[14rem]">Nombre</TableHead>
                    <TableHead className="min-w-[18rem]">Descripción</TableHead>
                    <TableHead className="min-w-[8rem]">Inicio</TableHead>
                    <TableHead className="min-w-[8rem]">Fin</TableHead>
                    <TableHead className="min-w-[5rem] text-center">Activo</TableHead>
                    <TableHead className="w-12" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {programas.map((p) => (
                    <FilaPrograma key={p.id} programa={p} onCambio={invalidar} />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NuevoPrograma({ onCreado }: { onCreado: () => void }) {
  const [abierto, setAbierto] = React.useState(false);
  const [nombre, setNombre] = React.useState("");
  const [descripcion, setDescripcion] = React.useState("");
  const [color, setColor] = React.useState("#7c7c7c");
  const [inicio, setInicio] = React.useState("");
  const [fin, setFin] = React.useState("");

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearProgramaRota = {
        nombre: nombre.trim(),
        descripcion: descripcion.trim() || undefined,
        color: color || undefined,
        inicio: inicio || undefined,
        fin: fin || undefined,
      };
      return api.crearProgramaRota(cuerpo);
    },
    onSuccess: () => {
      toast.success("Programa creado.");
      setNombre("");
      setDescripcion("");
      setColor("#7c7c7c");
      setInicio("");
      setFin("");
      setAbierto(false);
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (!abierto) {
    return (
      <Button size="sm" variant="outline" onClick={() => setAbierto(true)}>
        <Plus className="h-3.5 w-3.5" /> Nuevo programa
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-md border bg-background p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="prog-nombre" className="text-xs">
            Nombre
          </Label>
          <Input
            id="prog-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="Álvaro Fidalgo, MUNDIAL, Paty Cantú…"
            maxLength={200}
            className="h-8 text-xs"
            autoFocus
          />
        </div>
        <div className="space-y-1.5 sm:col-span-2">
          <Label htmlFor="prog-desc" className="text-xs">
            Descripción
          </Label>
          <Textarea
            id="prog-desc"
            value={descripcion}
            onChange={(e) => setDescripcion(e.target.value)}
            placeholder="Notas internas, qué cubre el programa…"
            rows={2}
            maxLength={1000}
            className="text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-inicio" className="text-xs">
            Inicio
          </Label>
          <Input
            id="prog-inicio"
            type="date"
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-fin" className="text-xs">
            Fin
          </Label>
          <Input
            id="prog-fin"
            type="date"
            value={fin}
            onChange={(e) => setFin(e.target.value)}
            className="h-8 text-xs"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-color" className="text-xs">
            Color
          </Label>
          <div className="flex items-center gap-2">
            <Input
              id="prog-color"
              type="color"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 w-14 cursor-pointer p-1"
            />
            <Input
              value={color}
              onChange={(e) => setColor(e.target.value)}
              className="h-8 flex-1 font-mono text-xs"
              maxLength={20}
              placeholder="#RRGGBB"
            />
          </div>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setAbierto(false)}>
          Cancelar
        </Button>
        <Button
          size="sm"
          onClick={() => crear.mutate()}
          disabled={!nombre.trim() || crear.isPending}
        >
          {crear.isPending ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Plus className="h-3.5 w-3.5" />
          )}
          Crear programa
        </Button>
      </div>
    </div>
  );
}

function FilaPrograma({
  programa,
  onCambio,
}: {
  programa: ProgramaRota;
  onCambio: () => void;
}) {
  const [editando, setEditando] = React.useState(false);
  // Estado pendiente del 409 al borrar: el backend dice cuántas piezas hay; el
  // usuario decide forzar.
  const [confirmarBorradoForzado, setConfirmarBorradoForzado] = React.useState<{
    piezasAfectadas: number;
  } | null>(null);

  const activar = useMutation({
    mutationFn: (activo: boolean) => api.actualizarProgramaRota(programa.id, { activo }),
    onSuccess: () => {
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: (forzar: boolean) => api.eliminarProgramaRota(programa.id, { forzar }),
    onSuccess: (res) => {
      const afectadas = res.piezas_afectadas ?? 0;
      toast.success(
        afectadas > 0
          ? `Programa eliminado (${afectadas} pieza${afectadas === 1 ? "" : "s"} huérfana${
              afectadas === 1 ? "" : "s"
            } conservan el nombre).`
          : "Programa eliminado.",
      );
      setConfirmarBorradoForzado(null);
      onCambio();
    },
    onError: (e, forzar) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        !forzar &&
        e.cuerpo &&
        (e.cuerpo as { en_uso?: boolean }).en_uso
      ) {
        const piezas = Number((e.cuerpo as { piezas_afectadas?: number }).piezas_afectadas ?? 0);
        setConfirmarBorradoForzado({ piezasAfectadas: piezas });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  if (editando) {
    return (
      <DialogEditarPrograma
        programa={programa}
        onCerrar={() => setEditando(false)}
        onCambio={onCambio}
      />
    );
  }

  return (
    <>
      <TableRow>
        <TableCell className="align-top">
          <div className="flex items-center gap-2">
            {programa.color && (
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-sm border"
                style={{ backgroundColor: programa.color }}
              />
            )}
            <span className="font-medium">{programa.nombre}</span>
          </div>
        </TableCell>
        <TableCell className="align-top text-sm text-muted-foreground">
          {programa.descripcion || <span className="opacity-50">—</span>}
        </TableCell>
        <TableCell className="align-top text-sm">
          {programa.inicio || <span className="text-muted-foreground opacity-50">—</span>}
        </TableCell>
        <TableCell className="align-top text-sm">
          {programa.fin || <span className="text-muted-foreground opacity-50">—</span>}
        </TableCell>
        <TableCell className="text-center align-top">
          <Checkbox
            checked={programa.activo}
            onCheckedChange={(v) => activar.mutate(v === true)}
            disabled={activar.isPending}
            aria-label={`Activar / desactivar ${programa.nombre}`}
          />
        </TableCell>
        <TableCell className="align-top">
          <div className="flex items-center gap-0.5">
            <Tooltip label="Editar">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-muted-foreground hover:text-foreground"
                aria-label={`Editar ${programa.nombre}`}
                onClick={() => setEditando(true)}
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            </Tooltip>
            <Tooltip label="Borrar">
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 text-muted-foreground hover:text-destructive"
                aria-label={`Borrar ${programa.nombre}`}
                onClick={() => {
                  if (window.confirm(`¿Borrar el programa «${programa.nombre}»?`))
                    borrar.mutate(false);
                }}
                disabled={borrar.isPending}
              >
                {borrar.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Trash2 className="h-3.5 w-3.5" />
                )}
              </Button>
            </Tooltip>
          </div>
        </TableCell>
      </TableRow>
      {confirmarBorradoForzado && (
        <Dialog open onOpenChange={(o) => !o && setConfirmarBorradoForzado(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Este programa tiene piezas</DialogTitle>
              <DialogDescription>
                «{programa.nombre}» está en uso por {confirmarBorradoForzado.piezasAfectadas}{" "}
                pieza
                {confirmarBorradoForzado.piezasAfectadas === 1 ? "" : "s"}. Si lo borras, las
                piezas conservarán el nombre textual pero ya no tendrás el catálogo.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setConfirmarBorradoForzado(null)}>
                Cancelar
              </Button>
              <Button
                variant="outline"
                className="text-destructive hover:text-destructive"
                onClick={() => borrar.mutate(true)}
                disabled={borrar.isPending}
              >
                {borrar.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Borrar igualmente
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

function DialogEditarPrograma({
  programa,
  onCerrar,
  onCambio,
}: {
  programa: ProgramaRota;
  onCerrar: () => void;
  onCambio: () => void;
}) {
  const [nombre, setNombre] = React.useState(programa.nombre);
  const [descripcion, setDescripcion] = React.useState(programa.descripcion);
  const [color, setColor] = React.useState(programa.color || "#7c7c7c");
  const [inicio, setInicio] = React.useState(programa.inicio);
  const [fin, setFin] = React.useState(programa.fin);
  const [activo, setActivo] = React.useState(programa.activo);

  const guardar = useMutation({
    mutationFn: () => {
      // Solo enviamos los campos que han cambiado: el backend acepta PATCH parcial
      // y la cascada del rename SOLO se dispara si `nombre` viaja en el cuerpo.
      const cuerpo: CuerpoActualizarProgramaRota = {};
      if (nombre.trim() !== programa.nombre) cuerpo.nombre = nombre.trim();
      if (descripcion !== programa.descripcion) cuerpo.descripcion = descripcion;
      if (color !== (programa.color || "#7c7c7c")) cuerpo.color = color;
      if (inicio !== programa.inicio) cuerpo.inicio = inicio;
      if (fin !== programa.fin) cuerpo.fin = fin;
      if (activo !== programa.activo) cuerpo.activo = activo;
      return api.actualizarProgramaRota(programa.id, cuerpo);
    },
    onSuccess: () => {
      // La cascada en piezas es transparente (el backend la hace en la misma
      // transacción). No emite contador: avisamos si el nombre cambió.
      if (nombre.trim() !== programa.nombre) {
        toast.success(
          `Programa renombrado. Las piezas con «${programa.nombre}» se actualizaron a «${nombre.trim()}».`,
        );
      } else {
        toast.success("Programa actualizado.");
      }
      onCambio();
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const sinCambios =
    nombre.trim() === programa.nombre &&
    descripcion === programa.descripcion &&
    color === (programa.color || "#7c7c7c") &&
    inicio === programa.inicio &&
    fin === programa.fin &&
    activo === programa.activo;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Editar programa</DialogTitle>
          <DialogDescription>
            Al renombrar, las piezas que usaban «{programa.nombre}» se renombran automáticamente
            en la misma transacción.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="ep-nombre">Nombre</Label>
            <Input
              id="ep-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ep-desc">Descripción</Label>
            <Textarea
              id="ep-desc"
              value={descripcion}
              onChange={(e) => setDescripcion(e.target.value)}
              rows={3}
              maxLength={1000}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ep-inicio">Inicio</Label>
              <Input
                id="ep-inicio"
                type="date"
                value={inicio}
                onChange={(e) => setInicio(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ep-fin">Fin</Label>
              <Input
                id="ep-fin"
                type="date"
                value={fin}
                onChange={(e) => setFin(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ep-color">Color</Label>
              <div className="flex items-center gap-2">
                <Input
                  id="ep-color"
                  type="color"
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="h-9 w-14 cursor-pointer p-1"
                />
                <Input
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                  className="h-9 flex-1 font-mono text-xs"
                  maxLength={20}
                  placeholder="#RRGGBB"
                />
              </div>
            </div>
            <div className="flex items-end gap-2 pb-1">
              <Checkbox
                id="ep-activo"
                checked={activo}
                onCheckedChange={(v) => setActivo(v === true)}
              />
              <Label htmlFor="ep-activo" className="cursor-pointer font-normal">
                Activo (aparece en el autocomplete de piezas)
              </Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button
            onClick={() => guardar.mutate()}
            disabled={sinCambios || !nombre.trim() || guardar.isPending}
          >
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
