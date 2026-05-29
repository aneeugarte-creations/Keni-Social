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
  Moon,
  Pencil,
  Plane,
  Plus,
  Radio,
  Search,
  Send,
  Shield,
  ShieldCheck,
  Sunrise,
  Sunset,
  Trash2,
  User,
  Users,
  X,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
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
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  CoberturaEvento,
  CuerpoActualizarPiezaRota,
  CuerpoActualizarProgramaRota,
  CuerpoCrearPiezaRota,
  CuerpoCrearProgramaRota,
  CuerpoCrearTurnoRota,
  EstadoPieza,
  EstadoSwap,
  EventoRota,
  FiltrosSwaps,
  FranjaTurno,
  MiembroRota,
  PiezaRota,
  PrioridadEvento,
  ProgramaRota,
  RotaSemana,
  SwapTurno,
  TipoAusencia,
  TipoCoberturaEvento,
  TurnoCobertura,
  TurnoRota,
} from "@/types";

const CABECERA = {
  titulo: "Parrilla y rota",
  descripcion:
    "Calendario de eventos (con su tipo de cobertura: transmisión, solo imágenes o no cubrir) y reprogramaciones marcadas, rota de cobertura y horarios/turnos del equipo. Tú decides qué cubre cada quien; la consola te muestra huecos, repite sábados y carga por persona, y tú apruebas antes de publicar al equipo.",
};

// Marca a la que pertenece esta rota.
// Hoy la rota es solo de ClaroSports. Multi-marca pendiente (refactor de `rota_eventos`
// para segregar por marca). De momento, filtramos en el front a los miembros que tienen
// `claro-sports` en sus marcas; el banner avisa explícitamente del alcance.
const MARCA_ROTA = "claro-sports" as const;
const ETIQUETA_MARCA_ROTA = "ClaroSports";

/**
 * Filtra el equipo devuelto por `/api/rota/equipo` a los miembros que cubren la marca
 * de esta rota. Si la respuesta NO trae `marcas` (backend antiguo), no se filtra
 * (degradación segura: vuelve al comportamiento anterior, todos los `cobertura=True`).
 */
function filtrarEquipoPorMarca(equipo: MiembroRota[]): MiembroRota[] {
  const algunoTraeMarcas = equipo.some((m) => Array.isArray(m.marcas));
  if (!algunoTraeMarcas) return equipo;
  return equipo.filter((m) => (m.marcas ?? []).includes(MARCA_ROTA));
}

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

/**
 * Args para abrir el dialog "Nuevo turno" desde otras pestañas (p. ej. Cobertura:
 * "Crear turno para esa franja+fecha"). El usuario salta a la pestaña Turnos y la
 * apertura del dialog se hace con estos campos prellenados.
 */
type PrelleneNuevoTurno = {
  fecha?: string;
  franja?: FranjaTurno;
  miembro_id?: string;
};

export default function Rota() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  // Por defecto: la próxima semana (la que más le importa al equipo, B4).
  const [lunes, setLunes] = React.useState(() => lunesSiguiente(lunesDeSemana(new Date()), 1));
  // Pestaña activa (controlada) para que pestañas hermanas puedan saltar entre sí
  // (PiezasSueltas → Programas; Cobertura → Turnos con dialog prellenado).
  const [pestania, setPestania] = React.useState("calendario");
  // Prellenado pendiente para el dialog "Nuevo turno" de la pestaña Turnos. Lo
  // consumimos al cambiar a `turnos` (one-shot) para evitar reabrir en re-renders.
  const [prellenoTurno, setPrellenoTurno] = React.useState<PrelleneNuevoTurno | null>(null);

  const abrirNuevoTurnoDesdeCobertura = (args: PrelleneNuevoTurno) => {
    setPrellenoTurno(args);
    setPestania("turnos");
  };

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          // Hoy la rota es solo de ClaroSports. Multi-marca pendiente.
          <Badge variant="outline" className="font-normal" data-testid="banner-marca-rota">
            Marca: {ETIQUETA_MARCA_ROTA}
          </Badge>
        }
      />
      <Tabs value={pestania} onValueChange={setPestania} className="space-y-4">
        <TabsList>
          <TabsTrigger value="calendario">Calendario</TabsTrigger>
          <TabsTrigger value="turnos">Turnos</TabsTrigger>
          <TabsTrigger value="cobertura">Cobertura</TabsTrigger>
          <TabsTrigger value="mis-turnos">Mis turnos</TabsTrigger>
          <TabsTrigger value="swaps">Cambios de turno</TabsTrigger>
          <TabsTrigger value="ausencias">Ausencias</TabsTrigger>
          <TabsTrigger value="eventos">Eventos</TabsTrigger>
          <TabsTrigger value="programas">Programas</TabsTrigger>
        </TabsList>

        <TabsContent value="calendario">
          <Calendario lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="turnos">
          <Turnos
            lunes={lunes}
            setLunes={setLunes}
            esAdmin={esAdmin}
            prelleno={prellenoTurno}
            limpiarPrelleno={() => setPrellenoTurno(null)}
          />
        </TabsContent>
        <TabsContent value="cobertura">
          <Cobertura
            lunes={lunes}
            setLunes={setLunes}
            onCrearTurno={abrirNuevoTurnoDesdeCobertura}
          />
        </TabsContent>
        <TabsContent value="mis-turnos">
          <MisTurnos lunes={lunes} setLunes={setLunes} />
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
  /** Turnos (cobertura derivada) que cubren el evento por (fecha, franja). */
  cobertura: TurnoCobertura[];
}

interface RecuadroPersona {
  miembro_id: string;
  miembro_nombre: string;
  /** `true` si el recuadro es "Sin cubrir" (eventos sin cobertura derivada). */
  sinCubrir: boolean;
  eventos: ItemEventoCalendario[];
}

/**
 * Calendario nuevo (día × franja × persona): la frontera real con la que trabaja el
 * equipo. Las filas son franjas (mañana → tarde → descanso), las columnas son los 7
 * días de la semana. Cada celda contiene un recuadro por persona que TRABAJA esa
 * franja ese día con sus eventos cubiertos (cobertura DERIVADA del backend); los
 * eventos sin cobertura caen en un recuadro "Sin cubrir". Pestaña sólo de lectura
 * editorial (el CRUD vive en la pestaña Turnos).
 */
function Calendario({
  lunes,
  setLunes,
  esAdmin,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  // El rango (lun→dom) de la semana en vista para acotar las consultas.
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1); // exclusivo
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes] as const,
    queryFn: ({ signal }) => api.cobertura({ lunes }, signal),
  });
  const turnosQ = useQuery({
    queryKey: ["rota", "turnos", lunes] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes }, signal),
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

  // Eventos con su cobertura derivada (el backend ya excluyó los `no_cubrir`).
  const eventosCobertura = React.useMemo(
    () => (coberturaQ.data?.eventos ?? []).filter((e) => e.fecha >= desde && e.fecha < hasta),
    [coberturaQ.data?.eventos, desde, hasta],
  );

  // Personas que trabajan cada (franja, fecha) según los turnos publicados.
  const personasPorCelda = React.useMemo(() => {
    const m = new Map<string, { miembro_id: string; miembro_nombre: string }[]>();
    for (const t of turnosQ.data?.turnos ?? []) {
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
  }, [turnosQ.data?.turnos]);

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

  // Itera los eventos y los reparte en su (franja, fecha) → persona/sin-cubrir.
  const recuadrosPorCelda = React.useMemo(() => {
    const m = new Map<string, RecuadroPersona[]>(); // clave: `${franja}|${fecha}`
    // Para cada celda primero metemos el recuadro de cada persona que trabaja allí
    // (aunque no tenga eventos): el usuario quiere ver "quién entra a esta franja".
    for (const franja of FRANJAS_CALENDARIO) {
      for (const fecha of dias) {
        const personas = personasPorCelda.get(`${franja}|${fecha}`) ?? [];
        const lista: RecuadroPersona[] = personas.map((p) => ({
          miembro_id: p.miembro_id,
          miembro_nombre: p.miembro_nombre,
          sinCubrir: false,
          eventos: [],
        }));
        m.set(`${franja}|${fecha}`, lista);
      }
    }
    // Ahora coloca cada evento en su recuadro: por cada cubridor en la cobertura
    // derivada, lo metemos en el recuadro de esa persona EN LA FRANJA del evento.
    // Si el evento no tiene cobertura, cae en un recuadro "Sin cubrir".
    for (const evento of eventosCobertura) {
      const franja = franjaDeHora(evento.hora);
      const clave = `${franja}|${evento.fecha}`;
      const lista = m.get(clave) ?? [];

      if (evento.cobertura.length === 0) {
        let recuadroSin = lista.find((r) => r.sinCubrir);
        if (!recuadroSin) {
          recuadroSin = {
            miembro_id: "",
            miembro_nombre: "Sin cubrir",
            sinCubrir: true,
            eventos: [],
          };
          lista.push(recuadroSin);
        }
        recuadroSin.eventos.push({ evento, cobertura: [] });
        m.set(clave, lista);
        continue;
      }

      for (const cob of evento.cobertura) {
        const recuadro = lista.find((r) => !r.sinCubrir && r.miembro_id === cob.miembro_id);
        if (recuadro) {
          recuadro.eventos.push({ evento, cobertura: evento.cobertura });
        } else {
          // El backend devolvió una cobertura cuyo miembro no aparece en `turnosQ`
          // para esa (franja, fecha). Caso raro (carrera de invalidaciones); lo
          // metemos como persona del cubridor para no perder el dato.
          lista.push({
            miembro_id: cob.miembro_id,
            miembro_nombre: cob.miembro_nombre,
            sinCubrir: false,
            eventos: [{ evento, cobertura: evento.cobertura }],
          });
        }
      }
      m.set(clave, lista);
    }
    return m;
  }, [eventosCobertura, dias, personasPorCelda]);

  const inicio = coberturaQ.data?.inicio ?? dias[0] ?? "";
  const fin = coberturaQ.data?.fin ?? dias[6] ?? "";
  const nCambiados = eventosCobertura.filter((e) => e.cambiado).length;
  const cargando = coberturaQ.isPending || turnosQ.isPending || ausenciasQ.isPending;
  const error = coberturaQ.error || turnosQ.error || ausenciasQ.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
        <div className="flex flex-wrap items-center gap-2">
          {nCambiados > 0 && (
            <Badge variant="aviso" className="gap-1 font-normal">
              <BellRing className="h-3.5 w-3.5" /> {nCambiados} reprogramado
              {nCambiados === 1 ? "" : "s"} sin avisar
            </Badge>
          )}
          {esAdmin && <BotonConfigFranjas />}
        </div>
      </div>

      <LeyendaCobertura />

      {cargando ? (
        <Skeleton className="h-[60vh] w-full rounded-md" />
      ) : error ? (
        <BloqueError
          titulo="No se pudo cargar el calendario"
          mensaje={mensajeError(error)}
          onReintentar={() => {
            void coberturaQ.refetch();
            void turnosQ.refetch();
            void ausenciasQ.refetch();
          }}
          cargando={coberturaQ.isFetching}
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
                                  key={`${rec.miembro_id}-${rec.sinCubrir ? "sin" : "ok"}`}
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
  const estilo = recuadro.sinCubrir
    ? "border-dashed border-amber-300/70 bg-amber-50/30 dark:bg-amber-950/10"
    : esDescanso
      ? "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/40"
      : "border-border bg-background";
  return (
    <div className={`flex flex-col gap-1 rounded-md border p-1.5 text-xs ${estilo}`}>
      <div className="flex items-center justify-between gap-1">
        <span
          className={`truncate font-medium ${
            recuadro.sinCubrir ? "text-amber-700 dark:text-amber-400" : ""
          }`}
        >
          {recuadro.sinCubrir ? "Sin cubrir" : recuadro.miembro_nombre}
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
  const tieneOverride = item.cobertura.some((c) => c.override);
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
        {tieneOverride && (
          <span className="inline-flex items-center gap-0.5 text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-2.5 w-2.5" /> override
          </span>
        )}
      </span>
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

// --- Pestaña: Turnos (CRUD primario sobre persona × día × franja) ----------
//
// Modelo nuevo (ola back3): un turno NO está ligado a un evento. Es el horario
// que cada persona tiene en (fecha, franja). La cobertura es derivada (otra
// pestaña). Aquí está el CRUD completo: crear (formulario / dialog), editar
// inline en la rejilla, multi-select para acciones en lote, borrar, duplicar,
// copiar semana, aprobar la semana.

/** Args para abrir el dialog "Nuevo turno" desde otras pestañas. */
type PrellenoNuevoTurno = {
  fecha?: string;
  franja?: FranjaTurno;
  miembro_id?: string;
};

function Turnos({
  lunes,
  setLunes,
  esAdmin,
  prelleno,
  limpiarPrelleno,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  esAdmin: boolean;
  /** Si llega un prelleno (atajo desde Cobertura), abrimos el dialog auto-rellenado. */
  prelleno: PrellenoNuevoTurno | null;
  limpiarPrelleno: () => void;
}) {
  const queryClient = useQueryClient();
  const claveTurnos = ["rota", "turnos", lunes] as const;

  const turnosQ = useQuery({
    queryKey: claveTurnos,
    queryFn: ({ signal }) => api.listarTurnos({ lunes }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"],
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });

  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? []);
  const ausencias = ausenciasQ.data?.ausencias ?? [];
  const semana = turnosQ.data;
  const turnos = React.useMemo(() => semana?.turnos ?? [], [semana?.turnos]);

  const invalidarTodo = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: claveTurnos });

  // Estado del dialog "Nuevo turno" (con o sin prelleno).
  const [dialogNuevo, setDialogNuevo] = React.useState<PrellenoNuevoTurno | null>(null);
  // Si llega un prelleno desde otra pestaña, ábrelo una vez y consúmelo.
  React.useEffect(() => {
    if (prelleno) {
      setDialogNuevo(prelleno);
      limpiarPrelleno();
    }
  }, [prelleno, limpiarPrelleno]);

  const aprobar = useMutation({
    mutationFn: () => api.aprobarTurnos({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveTurnos, res);
      toast.success(res.mensaje ?? "Turnos publicados al equipo.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const despublicar = useMutation({
    mutationFn: () => api.despublicarTurnos({ lunes }),
    onSuccess: (res) => {
      queryClient.setQueryData(claveTurnos, res);
      toast.success(res.mensaje ?? "Semana despublicada: vuelve a borrador.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const copiarAnterior = useMutation({
    mutationFn: () =>
      api.copiarSemana({
        de_lunes: lunesSiguiente(lunes, -1),
        a_lunes: lunes,
        reemplazar: false,
      }),
    onSuccess: (res) => {
      toast.success(`Copiados ${res.copiados ?? 0} turnos de la semana anterior.`);
      invalidarTodo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Filtros por miembro (multi-toggle).
  const [filtros, setFiltros] = React.useState<Set<string>>(new Set());
  const turnosFiltrados = React.useMemo(() => {
    if (filtros.size === 0) return turnos;
    return turnos.filter((t) => filtros.has(t.miembro_id));
  }, [turnos, filtros]);

  // Selección múltiple sobre la rejilla.
  const [seleccionados, setSeleccionados] = React.useState<Set<string>>(new Set());
  React.useEffect(() => {
    setSeleccionados(new Set());
  }, [lunes]);
  const toggleSeleccionado = (id: string) =>
    setSeleccionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Popover de acciones de lote: se abre con click izquierdo sobre una celda ya
  // seleccionada, en la posición (x,y) del cursor. Reemplaza al antiguo panel
  // superior. Si la selección queda vacía, ciérralo automáticamente.
  const [posPopoverLote, setPosPopoverLote] = React.useState<{ x: number; y: number } | null>(
    null,
  );
  React.useEffect(() => {
    if (seleccionados.size === 0 && posPopoverLote) setPosPopoverLote(null);
  }, [seleccionados, posPopoverLote]);

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
          <Button
            size="sm"
            onClick={() => setDialogNuevo({})}
            disabled={semana?.aprobada}
          >
            <Plus className="h-4 w-4" /> Nuevo turno
          </Button>
          <Button
            variant="outline"
            onClick={() => copiarAnterior.mutate()}
            disabled={copiarAnterior.isPending || semana?.aprobada}
            title="Copia los turnos de la semana anterior con offset +7 días"
          >
            {copiarAnterior.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
            Copiar semana anterior
          </Button>
          {esAdmin && !semana?.aprobada && (
            <Button
              variant="secondary"
              onClick={() => aprobar.mutate()}
              disabled={aprobar.isPending || turnos.length === 0}
            >
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              Aprobar y publicar
            </Button>
          )}
          {esAdmin && semana?.aprobada && (
            <Button
              variant="outline"
              onClick={() => {
                if (
                  window.confirm(
                    "La semana volverá a ser editable. ¿Despublicar los turnos?",
                  )
                )
                  despublicar.mutate();
              }}
              disabled={despublicar.isPending}
              title="Volver a borrador para editar"
            >
              {despublicar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CalendarOff className="h-4 w-4" />
              )}
              Despublicar
            </Button>
          )}
          {esAdmin && <BotonConfigFranjas />}
          <Button variant="outline" onClick={() => api.exportarRota("xlsx", { lunes })}>
            <Download className="h-4 w-4" /> Excel
          </Button>
          <Button variant="outline" onClick={() => api.exportarRota("csv", { lunes })}>
            <Download className="h-4 w-4" /> CSV
          </Button>
        </div>
      </div>

      <FiltrosMiembro equipo={equipo} filtros={filtros} setFiltros={setFiltros} />

      {turnosQ.isPending ? (
        <Skeleton className="h-48 w-full rounded-md" />
      ) : turnosQ.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los turnos"
          mensaje={mensajeError(turnosQ.error)}
          onReintentar={() => void turnosQ.refetch()}
          cargando={turnosQ.isFetching}
        />
      ) : turnos.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin turnos para esta semana"
          texto="Crea el primero con «Nuevo turno» o copia la semana anterior."
        />
      ) : (
        <RejillaTurnos
          semana={(semana as RotaSemana) ?? null}
          turnos={turnosFiltrados}
          equipo={equipo}
          ausencias={ausencias}
          editable={!semana?.aprobada}
          onCambio={invalidar}
          seleccionados={seleccionados}
          onToggleSeleccionado={toggleSeleccionado}
          onPedirNuevoTurno={(args) => setDialogNuevo(args)}
          onAbrirPopoverLote={(x, y) => setPosPopoverLote({ x, y })}
        />
      )}

      {posPopoverLote && seleccionados.size > 0 && (
        <PopoverSeleccionLote
          pos={posPopoverLote}
          seleccionados={seleccionados}
          equipo={equipo}
          onCerrar={() => setPosPopoverLote(null)}
          onAplicado={() => {
            setPosPopoverLote(null);
            setSeleccionados(new Set());
            invalidarTodo();
          }}
          onLimpiar={() => {
            setPosPopoverLote(null);
            setSeleccionados(new Set());
          }}
        />
      )}

      <PanelCarga lunes={lunes} />

      {dialogNuevo && (
        <DialogNuevoTurno
          lunes={lunes}
          equipo={equipo}
          inicial={dialogNuevo}
          onCerrar={() => setDialogNuevo(null)}
          onCreado={() => {
            setDialogNuevo(null);
            invalidarTodo();
          }}
        />
      )}
    </div>
  );
}

// --- Rejilla persona × día con celdas editables ---------------------------

function RejillaTurnos({
  semana,
  turnos,
  equipo,
  ausencias,
  editable,
  onCambio,
  seleccionados,
  onToggleSeleccionado,
  onPedirNuevoTurno,
  onAbrirPopoverLote,
}: {
  semana: RotaSemana | null;
  turnos: TurnoRota[];
  equipo: MiembroRota[];
  ausencias: AusenciaRota[];
  editable: boolean;
  onCambio: () => void;
  seleccionados: Set<string>;
  onToggleSeleccionado: (id: string) => void;
  onPedirNuevoTurno: (args: PrellenoNuevoTurno) => void;
  /** Click izquierdo sobre una celda ya seleccionada: abrir popover de lote en (x,y). */
  onAbrirPopoverLote?: (x: number, y: number) => void;
}) {
  const dias = semana?.dias ?? [];
  // Indexa los turnos por (miembro, fecha). El backend garantiza unicidad por
  // (miembro, fecha, franja), pero una persona puede tener varios turnos en el
  // mismo día (raro). Mostramos todos en pila por celda.
  const porCelda = React.useMemo(() => {
    const m = new Map<string, TurnoRota[]>();
    for (const t of turnos) {
      const k = `${t.miembro_id}|${t.fecha}`;
      const lista = m.get(k) ?? [];
      lista.push(t);
      m.set(k, lista);
    }
    return m;
  }, [turnos]);

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
                  const turnosCelda = porCelda.get(`${m.id}|${fecha}`) ?? [];
                  const finde = esFinDeSemana(fecha);
                  return (
                    <TableCell
                      key={fecha}
                      className={
                        finde ? "align-top bg-amber-50/30 dark:bg-amber-950/10" : "align-top"
                      }
                    >
                      <div className="space-y-1.5">
                        {ausencia && (
                          <Tooltip
                            label={
                              ausencia.motivo
                                ? `${ausencia.tipo}: ${ausencia.motivo}`
                                : `${ausencia.tipo} del ${ausencia.desde} al ${ausencia.hasta}`
                            }
                          >
                            <Badge variant="secondary" className="font-normal">
                              <Plane className="mr-1 h-3 w-3" />
                              {TIPOS_AUSENCIA.find((t) => t.valor === ausencia.tipo)?.etiqueta ??
                                "Ausente"}
                            </Badge>
                          </Tooltip>
                        )}
                        {turnosCelda.length === 0 ? (
                          editable ? (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-full justify-start gap-1 px-1.5 text-xs text-muted-foreground hover:text-foreground"
                              onClick={() =>
                                onPedirNuevoTurno({ fecha, miembro_id: m.id })
                              }
                            >
                              <Plus className="h-3 w-3" /> Añadir
                            </Button>
                          ) : (
                            <span className="text-sm text-muted-foreground">—</span>
                          )
                        ) : (
                          turnosCelda.map((t) => (
                            <CeldaTurno
                              key={t.id}
                              turno={t}
                              equipo={equipo}
                              editable={editable}
                              ausencia={ausencia}
                              onCambio={onCambio}
                              seleccionado={seleccionados.has(t.id)}
                              onToggleSeleccionado={onToggleSeleccionado}
                              onAbrirPopoverLote={onAbrirPopoverLote}
                            />
                          ))
                        )}
                      </div>
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
  equipo,
  editable,
  ausencia,
  onCambio,
  seleccionado,
  onToggleSeleccionado,
  onAbrirPopoverLote,
}: {
  turno: TurnoRota;
  equipo: MiembroRota[];
  editable: boolean;
  /** Si la persona tiene una ausencia que cubre el día de este turno. */
  ausencia?: AusenciaRota;
  onCambio: () => void;
  seleccionado: boolean;
  onToggleSeleccionado: (id: string) => void;
  /** Si el turno ya está seleccionado, un click izquierdo en la celda (no en el checkbox) abre el popover de acciones de lote. */
  onAbrirPopoverLote?: (x: number, y: number) => void;
}) {
  // Override pendiente por regla de sábado (la persona repite el sábado anterior).
  const [pendienteSabado, setPendienteSabado] = React.useState<FranjaTurno | null>(null);
  // Override pendiente por AUSENCIA (la persona está ausente ese día).
  const [pendienteAusencia, setPendienteAusencia] = React.useState<{
    franja: FranjaTurno;
    ausencia: AusenciaRota;
  } | null>(null);
  const [editandoDetalles, setEditandoDetalles] = React.useState(false);

  const actualizar = useMutation({
    mutationFn: (cuerpo: {
      franja?: FranjaTurno;
      miembro_id?: string;
      override?: boolean;
      motivo?: string;
      nota_relevo?: string;
    }) => api.actualizarTurno(turno.id, cuerpo),
    onSuccess: () => {
      setPendienteSabado(null);
      setPendienteAusencia(null);
      onCambio();
    },
    onError: (e, variables) => {
      if (e instanceof ApiError && e.status === 409 && variables.franja) {
        const cuerpo = (e.cuerpo ?? {}) as {
          requiere_override?: boolean;
          ausencia?: AusenciaRota;
        };
        if (cuerpo.requiere_override && cuerpo.ausencia) {
          setPendienteAusencia({ franja: variables.franja, ausencia: cuerpo.ausencia });
          return;
        }
        setPendienteSabado(variables.franja);
        toast.warning(mensajeError(e));
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const borrar = useMutation({
    mutationFn: () => api.borrarTurno(turno.id),
    onSuccess: () => {
      toast.success("Turno eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const duplicar = useMutation({
    mutationFn: () => api.duplicarTurno(turno.id, {}),
    onSuccess: () => {
      toast.success("Turno duplicado.");
      onCambio();
    },
    onError: (e) => {
      // Choque con turno existente (común al duplicar sin cambiar nada).
      if (e instanceof ApiError && e.status === 409) {
        toast.info(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  if (!editable) {
    return (
      <div className="space-y-1">
        <div className="flex items-center gap-1.5">
          <span className="text-sm">{ETIQUETA_FRANJA[turno.franja]}</span>
          {turno.override && <AlertTriangle className="h-3 w-3 text-amber-600" />}
        </div>
        {turno.nota_relevo && <NotaRelevo nota={turno.nota_relevo} />}
        {turno.motivo && (
          <div className="text-[10px] text-muted-foreground">{turno.motivo}</div>
        )}
      </div>
    );
  }

  // Items del menú contextual (right-click): TODA la edición vive aquí.
  // Reduce ruido visual en la celda: ni botones, ni selector inline. La celda solo
  // muestra franja + override/ausente + nota/motivo; el resto se descubre con
  // botón derecho.
  const itemsMenu: EntradaMenuContextual[] = [
    {
      etiqueta: "Mañana",
      icono: Sunrise,
      activo: turno.franja === "matutino",
      onClick: () => actualizar.mutate({ franja: "matutino" }),
    },
    {
      etiqueta: "Tarde",
      icono: Sunset,
      activo: turno.franja === "vespertino",
      onClick: () => actualizar.mutate({ franja: "vespertino" }),
    },
    {
      etiqueta: "Descanso",
      icono: Moon,
      activo: turno.franja === "descanso",
      onClick: () => actualizar.mutate({ franja: "descanso" }),
    },
    { separador: true },
    {
      etiqueta: "Editar detalles…",
      icono: Pencil,
      onClick: () => setEditandoDetalles(true),
    },
    {
      etiqueta: "Duplicar",
      icono: Copy,
      onClick: () => duplicar.mutate(),
      deshabilitado: duplicar.isPending,
    },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      destructivo: true,
      onClick: () => {
        if (window.confirm(`¿Borrar el turno de ${turno.miembro_nombre}?`))
          borrar.mutate();
      },
      deshabilitado: borrar.isPending,
    },
  ];

  return (
    <MenuContextual items={itemsMenu}>
      <div
        className={cn(
          "space-y-1.5 rounded-md border bg-background p-1.5",
          seleccionado && onAbrirPopoverLote && "cursor-pointer",
        )}
        onClick={(e) => {
          // Click izquierdo en celda ya seleccionada abre el popover de acciones
          // de lote. Ignora clicks que vienen de elementos interactivos internos
          // (checkbox, botón "Forzar cobertura") para no interceptarlos: el
          // checkbox detiene la propagación con stopPropagation, pero por
          // robustez también filtramos cualquier <button>/<input>/<a> aquí.
          if (!seleccionado || !onAbrirPopoverLote) return;
          const objetivo = e.target as HTMLElement;
          if (objetivo.closest("button, input, a, [role='checkbox']")) return;
          onAbrirPopoverLote(e.clientX, e.clientY);
        }}
      >
        <div className="flex items-start gap-1.5">
          {/* Envuelve el Checkbox en un span para parar la propagación: así un
              click en el checkbox solo togglea, sin disparar el click izquierdo
              de la celda que abre el popover de acciones de lote. */}
          <span onClick={(e) => e.stopPropagation()} className="mt-1.5">
            <Checkbox
              aria-label={`Seleccionar turno de ${turno.miembro_nombre} el ${turno.fecha}`}
              checked={seleccionado}
              onCheckedChange={() => onToggleSeleccionado(turno.id)}
            />
          </span>
          <div className="min-w-0 flex-1 space-y-1">
            <div className="text-xs font-medium">{ETIQUETA_FRANJA[turno.franja]}</div>
            <div className="flex flex-wrap items-center gap-1">
              {turno.override && (
                <Badge variant="aviso" className="h-4 gap-0.5 px-1 text-[10px] font-normal">
                  <AlertTriangle className="h-2.5 w-2.5" /> override
                </Badge>
              )}
              {ausencia && !turno.override && (
                <Badge variant="aviso" className="h-4 gap-0.5 px-1 text-[10px] font-normal">
                  <Plane className="h-2.5 w-2.5" /> ausente
                </Badge>
              )}
            </div>
            {turno.nota_relevo && <NotaRelevo nota={turno.nota_relevo} />}
            {turno.motivo && (
              <div className="text-[10px] text-muted-foreground">{turno.motivo}</div>
            )}
          </div>
        </div>
      {pendienteSabado && (
        <Button
          size="sm"
          variant="outline"
          className="w-full text-amber-700 dark:text-amber-400"
          onClick={() => actualizar.mutate({ franja: pendienteSabado, override: true })}
          disabled={actualizar.isPending}
        >
          <AlertTriangle className="h-3.5 w-3.5" /> Forzar cobertura (override)
        </Button>
      )}
      {pendienteAusencia && (
        <Dialog open onOpenChange={(o) => !o && setPendienteAusencia(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Esa persona está ausente</DialogTitle>
              <DialogDescription>
                {pendienteAusencia.ausencia.miembro_nombre} está{" "}
                {pendienteAusencia.ausencia.tipo} del {pendienteAusencia.ausencia.desde} al{" "}
                {pendienteAusencia.ausencia.hasta}.
                {pendienteAusencia.ausencia.motivo
                  ? ` Motivo: ${pendienteAusencia.ausencia.motivo}.`
                  : ""}{" "}
                ¿Forzar override de todas formas?
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPendienteAusencia(null)}>
                Cancelar
              </Button>
              <Button
                variant="outline"
                className="text-amber-700 hover:text-amber-700 dark:text-amber-400"
                onClick={() =>
                  actualizar.mutate({ franja: pendienteAusencia.franja, override: true })
                }
                disabled={actualizar.isPending}
              >
                {actualizar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                <AlertTriangle className="h-4 w-4" /> Forzar override
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
        {editandoDetalles && (
          <DialogEditarTurno
            turno={turno}
            equipo={equipo}
            onCerrar={() => setEditandoDetalles(false)}
            onGuardado={() => {
              setEditandoDetalles(false);
              onCambio();
            }}
          />
        )}
      </div>
    </MenuContextual>
  );
}

/** Diálogo para editar detalles de un turno (persona, motivo, nota de relevo). */
function DialogEditarTurno({
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
            Cambia persona, fecha, franja, motivo o nota de relevo. Se valida el sábado
            consecutivo y las ausencias; si chocan, te ofrecemos forzar override.
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
            <Label htmlFor="et-motivo">
              Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="et-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              placeholder="Cobertura forzada por evento crítico…"
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-nota">
              Nota de relevo{" "}
              <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="et-nota"
              value={notaRelevo}
              onChange={(e) => setNotaRelevo(e.target.value)}
              placeholder="Qué queda pendiente para el siguiente turno…"
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

/** Dialog "Nuevo turno": crea un turno (persona × fecha × franja). */
function DialogNuevoTurno({
  lunes,
  equipo,
  inicial,
  onCerrar,
  onCreado,
}: {
  lunes: string;
  equipo: MiembroRota[];
  inicial: PrellenoNuevoTurno;
  onCerrar: () => void;
  onCreado: () => void;
}) {
  const desde = lunes;
  const [fecha, setFecha] = React.useState(inicial.fecha ?? desde);
  const [miembroId, setMiembroId] = React.useState(inicial.miembro_id ?? "");
  const [franja, setFranja] = React.useState<FranjaTurno>(inicial.franja ?? "matutino");
  const [motivo, setMotivo] = React.useState("");
  const [notaRelevo, setNotaRelevo] = React.useState("");
  const [pendienteOverride, setPendienteOverride] = React.useState<{ mensaje: string } | null>(
    null,
  );

  const crear = useMutation({
    mutationFn: (override: boolean) => {
      const cuerpo: CuerpoCrearTurnoRota = {
        lunes,
        fecha,
        miembro_id: miembroId,
        franja,
        motivo: motivo.trim() || undefined,
        nota_relevo: notaRelevo.trim() || undefined,
      };
      if (override) cuerpo.override = true;
      return api.crearTurno(cuerpo);
    },
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
        setPendienteOverride({ mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const puedeCrear = fecha !== "" && miembroId !== "" && !crear.isPending;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Nuevo turno</DialogTitle>
          <DialogDescription>
            Un turno es una persona en una fecha y franja. NO se asocia a ningún evento:
            la cobertura se calcula a partir de los turnos y los eventos de la semana.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
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
              <Label>Franja</Label>
              <Select value={franja} onValueChange={(v) => setFranja(v as FranjaTurno)}>
                <SelectTrigger aria-label="Franja del turno">
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
            <Label htmlFor="nt-motivo">
              Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="nt-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nt-nota">
              Nota de relevo <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Textarea
              id="nt-nota"
              value={notaRelevo}
              onChange={(e) => setNotaRelevo(e.target.value)}
              rows={2}
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
              onClick={() => crear.mutate(true)}
              disabled={crear.isPending}
            >
              {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              <AlertTriangle className="h-4 w-4" /> Forzar override
            </Button>
          ) : (
            <Button onClick={() => crear.mutate(false)} disabled={!puedeCrear}>
              {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
              Crear turno
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Filtros por miembro (chip toggles) ------------------------------------

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

// --- Popover de acciones de lote (click izquierdo en celda seleccionada) ---
//
// Antes era una "barra superior" (Card flotante) que aparecía al seleccionar 1+
// celdas. Ahora es un popover en `position: fixed`, abierto en la posición del
// cursor cuando el usuario hace click izquierdo sobre una celda ya seleccionada
// (mismo patrón visual que `MenuContextual`, pero disparado con click izquierdo
// y mostrando acciones de lote). Se cierra con click fuera o tecla Escape.

function PopoverSeleccionLote({
  pos,
  seleccionados,
  equipo,
  onCerrar,
  onAplicado,
  onLimpiar,
}: {
  pos: { x: number; y: number };
  seleccionados: Set<string>;
  equipo: MiembroRota[];
  /** Cerrar sin tocar la selección (click fuera / Escape). */
  onCerrar: () => void;
  /** Hubo una mutación con éxito: limpia selección + invalida queries. */
  onAplicado: () => void;
  /** Cancelar selección: limpia selección + cierra. */
  onLimpiar: () => void;
}) {
  const popoverRef = React.useRef<HTMLDivElement>(null);
  const [miembroId, setMiembroId] = React.useState("");
  const [override, setOverride] = React.useState<{
    miembroId: string;
    franja: FranjaTurno | "";
    mensaje: string;
    ids: string[];
  } | null>(null);

  // Click fuera / Escape cierran el popover (igual que MenuContextual). Si el
  // diálogo de override está abierto, lo dejamos manejar sus propios cierres.
  React.useEffect(() => {
    function alPulsarFuera(e: MouseEvent) {
      if (override) return;
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onCerrar();
      }
    }
    function alTeclear(e: KeyboardEvent) {
      if (override) return;
      if (e.key === "Escape") onCerrar();
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [onCerrar, override]);

  const aplicar = useMutation({
    mutationFn: (vars: {
      miembroId: string;
      franja: FranjaTurno | "";
      override: boolean;
    }) => {
      const cuerpo: {
        ids: string[];
        miembro_id?: string;
        franja?: FranjaTurno;
        override?: boolean;
      } = {
        ids: [...seleccionados],
      };
      if (vars.miembroId !== "") cuerpo.miembro_id = vars.miembroId;
      if (vars.franja !== "") cuerpo.franja = vars.franja;
      if (vars.override) cuerpo.override = true;
      return api.actualizarTurnosLote(cuerpo);
    },
    onSuccess: (res) => {
      toast.success(`Actualizados ${res.actualizados} turnos.`);
      setOverride(null);
      setMiembroId("");
      onAplicado();
    },
    onError: (e, vars) => {
      if (e instanceof ApiError && e.status === 409) {
        const ids = (e.cuerpo?.ids_que_requieren_override as string[] | undefined) ?? [];
        setOverride({
          miembroId: vars.miembroId,
          franja: vars.franja,
          mensaje: e.message,
          ids,
        });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  // `miembro_id=""` desasigna en el backend (alineado con el PATCH 1:1).
  const quitarMiembro = useMutation({
    mutationFn: () =>
      api.actualizarTurnosLote({ ids: [...seleccionados], miembro_id: "" }),
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

  const ocupado =
    aplicar.isPending || quitarMiembro.isPending || borrarSeleccion.isPending;
  const n = seleccionados.size;
  const etiquetaTurnos = `${n} ${n === 1 ? "turno" : "turnos"}`;

  return (
    <>
      <div
        ref={popoverRef}
        role="menu"
        aria-label="Acciones de lote sobre la selección"
        className="fixed z-50 w-64 rounded-md border border-border bg-popover p-3 text-popover-foreground shadow-md"
        style={{ left: pos.x, top: pos.y }}
      >
        <div className="mb-2 text-xs font-medium text-muted-foreground">
          {etiquetaTurnos} seleccionado{n === 1 ? "" : "s"}
        </div>

        <div className="space-y-1">
          <Label className="text-[10px] text-muted-foreground">Asignar a</Label>
          <div className="flex gap-1.5">
            <Select value={miembroId} onValueChange={setMiembroId}>
              <SelectTrigger
                aria-label="Persona para el lote"
                className="h-8 flex-1 text-xs"
              >
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
            <Button
              size="sm"
              className="h-8 px-2"
              onClick={() =>
                aplicar.mutate({ miembroId, franja: "", override: false })
              }
              disabled={miembroId === "" || ocupado}
            >
              {aplicar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                "Aplicar"
              )}
            </Button>
          </div>
        </div>

        <div className="mt-3 space-y-1">
          <Label className="text-[10px] text-muted-foreground">Cambiar franja</Label>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant="outline"
              className="h-8 flex-1 px-1.5"
              onClick={() =>
                aplicar.mutate({ miembroId: "", franja: "matutino", override: false })
              }
              disabled={ocupado}
            >
              <Sunrise className="h-3.5 w-3.5" /> Mañana
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8 flex-1 px-1.5"
              onClick={() =>
                aplicar.mutate({ miembroId: "", franja: "vespertino", override: false })
              }
              disabled={ocupado}
            >
              <Sunset className="h-3.5 w-3.5" /> Tarde
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-8 flex-1 px-1.5"
              onClick={() =>
                aplicar.mutate({ miembroId: "", franja: "descanso", override: false })
              }
              disabled={ocupado}
            >
              <Moon className="h-3.5 w-3.5" /> Descanso
            </Button>
          </div>
        </div>

        <div className="my-2 border-t border-border" aria-hidden="true" />

        <button
          type="button"
          role="menuitem"
          disabled={ocupado}
          onClick={() => quitarMiembro.mutate()}
          className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {quitarMiembro.isPending ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <Users className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <span className="flex-1">Quitar asignación</span>
        </button>

        <button
          type="button"
          role="menuitem"
          disabled={ocupado}
          onClick={() => {
            if (
              window.confirm(
                `¿Borrar ${n} turno${n === 1 ? "" : "s"}?`,
              )
            )
              borrarSeleccion.mutate();
          }}
          className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left text-sm text-destructive transition-colors hover:bg-destructive/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {borrarSeleccion.isPending ? (
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4 shrink-0 text-destructive" />
          )}
          <span className="flex-1">Borrar {etiquetaTurnos}</span>
        </button>

        <div className="my-2 border-t border-border" aria-hidden="true" />

        <button
          type="button"
          role="menuitem"
          onClick={onLimpiar}
          className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-accent"
        >
          <X className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="flex-1">Cancelar selección</span>
        </button>
      </div>

      {override && (
        <Dialog open onOpenChange={(o) => !o && setOverride(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>¿Forzar la cobertura?</DialogTitle>
              <DialogDescription>{override.mensaje}</DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              {override.ids.length}{" "}
              {override.ids.length === 1 ? "turno repite" : "turnos repiten"} el sábado
              anterior. Confirma solo si es una cobertura estratégica intencional.
            </p>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setOverride(null)}>
                Cancelar
              </Button>
              <Button
                onClick={() =>
                  aplicar.mutate({
                    miembroId: override.miembroId,
                    franja: override.franja,
                    override: true,
                  })
                }
                disabled={aplicar.isPending}
              >
                <AlertTriangle className="h-4 w-4" /> Forzar cobertura
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}

// --- Panel "Carga del equipo" (colapsable) ---------------------------------

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
      <CardHeader className="cursor-pointer pb-3" onClick={() => setAbierto((v) => !v)}>
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

// --- Pestaña: Cobertura (vista DERIVADA, solo lectura) ----------------------
//
// Para cada evento de la semana, muestra los turnos cuya (fecha, franja) lo
// cubren. NO es CRUD: el CRUD vive en la pestaña Turnos. Sí ofrecemos un atajo
// "Crear turno para esa franja+fecha" cuando el evento no tiene cobertura, que
// salta a la pestaña Turnos abriendo el dialog prellenado.

function Cobertura({
  lunes,
  setLunes,
  onCrearTurno,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  onCrearTurno: (args: PrellenoNuevoTurno) => void;
}) {
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes] as const,
    queryFn: ({ signal }) => api.cobertura({ lunes }, signal),
  });
  const datos = coberturaQ.data;
  // Memo para que la referencia sea estable entre renders sin datos nuevos.
  const eventos = React.useMemo(() => datos?.eventos ?? [], [datos?.eventos]);
  const inicio = datos?.inicio ?? "";
  const fin = datos?.fin ?? "";

  // Agrupamos por día para una lectura natural.
  const porDia = React.useMemo(() => {
    const m = new Map<string, CoberturaEvento[]>();
    for (const e of eventos) {
      const lista = m.get(e.fecha) ?? [];
      lista.push(e);
      m.set(e.fecha, lista);
    }
    // Orden interno por hora.
    for (const lista of m.values()) {
      lista.sort((a, b) => (a.hora || "").localeCompare(b.hora || ""));
    }
    return Array.from(m.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [eventos]);

  // Resumen para la barra superior.
  const sinCubrir = eventos.filter((e) => e.cobertura.length === 0).length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
        <div className="flex flex-wrap items-center gap-2">
          {datos && (
            <Badge variant="secondary" className="font-normal">
              {eventos.length} evento{eventos.length === 1 ? "" : "s"} ·{" "}
              {sinCubrir === 0
                ? "todo cubierto"
                : `${sinCubrir} sin cubrir`}
            </Badge>
          )}
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Esta vista se calcula a partir de los turnos y los eventos: para cada evento, qué
        persona lo cubre por su (fecha, franja). No se asigna aquí — usa la pestaña{" "}
        <strong>Turnos</strong> para crear o editar turnos.
      </p>

      {coberturaQ.isPending ? (
        <Skeleton className="h-48 w-full rounded-md" />
      ) : coberturaQ.isError ? (
        <BloqueError
          titulo="No se pudo cargar la cobertura"
          mensaje={mensajeError(coberturaQ.error)}
          onReintentar={() => void coberturaQ.refetch()}
          cargando={coberturaQ.isFetching}
        />
      ) : porDia.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin eventos esta semana"
          texto="Da de alta eventos en la pestaña «Eventos»."
        />
      ) : (
        porDia.map(([fecha, eventosDia]) => (
          <Card key={fecha}>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center justify-between text-base">
                <span className="capitalize">{formatearFechaCorta(fecha)}</span>
                {esFinDeSemana(fecha) && (
                  <Badge variant="outline" className="font-normal">
                    Fin de semana
                  </Badge>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {eventosDia.map((evento) => (
                <FilaCoberturaEvento
                  key={evento.id}
                  evento={evento}
                  onCrearTurno={onCrearTurno}
                />
              ))}
            </CardContent>
          </Card>
        ))
      )}
    </div>
  );
}

function FilaCoberturaEvento({
  evento,
  onCrearTurno,
}: {
  evento: CoberturaEvento;
  onCrearTurno: (args: PrellenoNuevoTurno) => void;
}) {
  const cob = COBERTURA[evento.tipo_cobertura] ?? COBERTURA.transmision;
  const IconoCob = cob.icono;
  const franjaPropuesta = franjaDeHora(evento.hora);
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 rounded-md border bg-background p-3">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{evento.titulo}</span>
          <Badge variant="outline" className={`gap-1 font-normal ${cob.chip}`}>
            <IconoCob className="h-3 w-3" /> {cob.etiqueta}
          </Badge>
          {evento.cambiado && (
            <Badge variant="aviso" className="gap-1 font-normal">
              <BellRing className="h-3 w-3" /> Cambió
            </Badge>
          )}
        </div>
        <div className="text-xs text-muted-foreground">
          {evento.hora ? `${evento.hora} · ` : ""}
          <span className={COLOR_PRIORIDAD[evento.prioridad]}>
            prioridad {evento.prioridad}
          </span>
        </div>
        {evento.contenido && (
          <div className="text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Qué sacar: </span>
            {evento.contenido}
          </div>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1.5">
        {evento.cobertura.length === 0 ? (
          <div className="flex flex-col items-end gap-1">
            <Badge variant="aviso" className="gap-1 font-normal">
              <AlertTriangle className="h-3 w-3" /> Sin cubrir
            </Badge>
            <Button
              size="sm"
              variant="outline"
              className="h-7 gap-1 text-xs"
              onClick={() =>
                onCrearTurno({
                  fecha: evento.fecha,
                  franja: franjaPropuesta,
                })
              }
            >
              <Plus className="h-3 w-3" /> Crear turno
            </Button>
          </div>
        ) : (
          <div className="flex flex-col items-end gap-1">
            {evento.cobertura.map((c) => (
              <span
                key={c.turno_id}
                className="inline-flex items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-xs"
              >
                <User className="h-3 w-3 text-muted-foreground" />
                {c.miembro_nombre}
                <span className="text-muted-foreground">· {ETIQUETA_FRANJA[c.franja]}</span>
                {c.override && (
                  <AlertTriangle
                    className="h-3 w-3 text-amber-600"
                    aria-label="override"
                  />
                )}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Pestaña: Mis turnos ----------------------------------------------------

function MisTurnos({
  lunes,
  setLunes,
}: {
  lunes: string;
  setLunes: (l: string) => void;
}) {
  const q = useQuery({
    queryKey: ["rota", "mis-turnos", lunes],
    queryFn: ({ signal }) => api.misTurnos({ lunes }, signal),
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
          titulo="No se pudieron cargar tus turnos"
          mensaje={mensajeError(q.error)}
          onReintentar={() => void q.refetch()}
          cargando={q.isFetching}
        />
      ) : datos?.aviso ? (
        <EstadoVacio icono={User} titulo="Inicia sesión" texto={datos.aviso} />
      ) : mios.length === 0 ? (
        <EstadoVacio
          icono={CalendarDays}
          titulo="Sin turnos esta semana"
          texto="No tienes turnos asignados esta semana."
        />
      ) : (
        <>
          {!datos?.aprobada && (
            <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
              Este horario es un borrador sin publicar; puede cambiar antes de que Elías
              lo apruebe.
            </p>
          )}
          <ListaMisTurnos turnos={mios} />
        </>
      )}
    </div>
  );
}

function ListaMisTurnos({ turnos }: { turnos: TurnoRota[] }) {
  // Orden cronológico (fecha, franja).
  const ordenados = React.useMemo(
    () =>
      [...turnos].sort(
        (a, b) => a.fecha.localeCompare(b.fecha) || a.franja.localeCompare(b.franja),
      ),
    [turnos],
  );
  return (
    <div className="space-y-3">
      {ordenados.map((t) => (
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
            <div className="text-sm text-muted-foreground">
              {formatearFechaCorta(t.fecha)}
            </div>
            {t.motivo && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">Motivo: </span>
                {t.motivo}
              </div>
            )}
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

// --- Día de la semana + utilidades de fecha ---------------------------------

function diaCorto(fechaIso: string): string {
  const d = new Date(`${fechaIso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("es-MX", { weekday: "short" });
}

function esFinDeSemana(fechaIso: string): boolean {
  const d = new Date(`${fechaIso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return false;
  const dia = d.getDay();
  return dia === 0 || dia === 6;
}

// --- Dialog "Configurar franjas" (solo admin) -------------------------------

function BotonConfigFranjas() {
  const [abierto, setAbierto] = React.useState(false);
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setAbierto(true)}
        title="Editar los rangos horarios de las franjas (mañana / tarde)"
      >
        <Clock className="h-4 w-4" /> Franjas
      </Button>
      {abierto && <DialogConfigFranjas onCerrar={() => setAbierto(false)} />}
    </>
  );
}

function DialogConfigFranjas({ onCerrar }: { onCerrar: () => void }) {
  const queryClient = useQueryClient();
  const q = useQuery({
    queryKey: ["rota", "config", "franjas"] as const,
    queryFn: ({ signal }) => api.obtenerConfigFranjas(signal),
  });
  const inicial = q.data?.franjas;
  const [matIni, setMatIni] = React.useState("");
  const [matFin, setMatFin] = React.useState("");
  const [vesIni, setVesIni] = React.useState("");
  const [vesFin, setVesFin] = React.useState("");

  React.useEffect(() => {
    if (inicial) {
      setMatIni(inicial.matutino_inicio);
      setMatFin(inicial.matutino_fin);
      setVesIni(inicial.vespertino_inicio);
      setVesFin(inicial.vespertino_fin);
    }
  }, [inicial]);

  const guardar = useMutation({
    mutationFn: () =>
      api.guardarConfigFranjas({
        matutino_inicio: matIni,
        matutino_fin: matFin,
        vespertino_inicio: vesIni,
        vespertino_fin: vesFin,
      }),
    onSuccess: () => {
      toast.success("Franjas guardadas.");
      void queryClient.invalidateQueries({ queryKey: ["rota"] });
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const sinCambios =
    !!inicial &&
    matIni === inicial.matutino_inicio &&
    matFin === inicial.matutino_fin &&
    vesIni === inicial.vespertino_inicio &&
    vesFin === inicial.vespertino_fin;
  const puedeGuardar =
    matIni !== "" && matFin !== "" && vesIni !== "" && vesFin !== "" && !sinCambios;

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Configurar franjas</DialogTitle>
          <DialogDescription>
            Los rangos horarios determinan qué eventos caen en cada franja al calcular
            la cobertura. Usa formato HH:MM (24h).
          </DialogDescription>
        </DialogHeader>
        {q.isPending ? (
          <Skeleton className="h-32 w-full rounded-md" />
        ) : q.isError ? (
          <BloqueError
            titulo="No se pudo cargar la configuración"
            mensaje={mensajeError(q.error)}
            onReintentar={() => void q.refetch()}
            cargando={q.isFetching}
          />
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 rounded-md border bg-muted/30 p-3">
              <div className="col-span-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Mañana
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cf-mat-ini">Inicio</Label>
                <Input
                  id="cf-mat-ini"
                  type="time"
                  value={matIni}
                  onChange={(e) => setMatIni(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cf-mat-fin">Fin</Label>
                <Input
                  id="cf-mat-fin"
                  type="time"
                  value={matFin}
                  onChange={(e) => setMatFin(e.target.value)}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 rounded-md border bg-muted/30 p-3">
              <div className="col-span-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Tarde
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cf-ves-ini">Inicio</Label>
                <Input
                  id="cf-ves-ini"
                  type="time"
                  value={vesIni}
                  onChange={(e) => setVesIni(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="cf-ves-fin">Fin</Label>
                <Input
                  id="cf-ves-fin"
                  type="time"
                  value={vesFin}
                  onChange={(e) => setVesFin(e.target.value)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Lo que cae fuera de ambos rangos (madrugada típica) se asigna a «descanso»:
              no se cubre, pero los eventos aparecen para que sepas que están ahí.
            </p>
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar || guardar.isPending}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function NotaRelevo({ nota }: { nota: string }) {
  const limpia = nota.trim();
  if (!limpia) return null;
  const RESUMEN_MAX = 30;
  const resumen = limpia.length > RESUMEN_MAX ? `${limpia.slice(0, RESUMEN_MAX)}…` : limpia;
  return (
    <div
      className="flex items-start gap-1 text-[11px] text-muted-foreground"
      title={limpia}
    >
      <MessageSquare className="mt-0.5 h-3 w-3 shrink-0" aria-hidden />
      <span className="truncate">{resumen}</span>
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
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? []);
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

function Eventos({ onIrAProgramas }: { onIrAProgramas?: () => void }) {
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
      <PiezasSueltas onIrAProgramas={onIrAProgramas} />
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

function PiezasSueltas({ onIrAProgramas }: { onIrAProgramas?: () => void }) {
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

  const piezasData = q.data?.piezas;
  const piezasFiltradas = React.useMemo(() => {
    const todasPiezas = piezasData ?? [];
    const salidaQ = filtroSalida.trim().toLowerCase();
    const programaQ = filtroPrograma.trim().toLowerCase();
    return todasPiezas.filter((p) => {
      if (filtroAlwaysOn === "solo" && !p.always_on) return false;
      if (filtroAlwaysOn === "excluir" && p.always_on) return false;
      if (salidaQ && !(p.salida || "").toLowerCase().includes(salidaQ)) return false;
      if (programaQ && !(p.programa || "").toLowerCase().includes(programaQ)) return false;
      return true;
    });
  }, [piezasData, filtroAlwaysOn, filtroSalida, filtroPrograma]);

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
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {onIrAProgramas && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                  onClick={onIrAProgramas}
                >
                  Gestionar programas →
                </Button>
              )}
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
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? []).filter(
    (m) => m.id !== miId,
  );

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
