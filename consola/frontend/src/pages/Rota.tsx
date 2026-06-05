import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeftRight,
  BellRing,
  CalendarDays,
  CalendarOff,
  CalendarPlus,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  Coffee,
  Copy,
  Download,
  HeartPulse,
  HelpCircle,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plane,
  Plus,
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
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
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
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import {
  COBERTURA,
  COLOR_PRIORIDAD,
  diaCorto,
  esFinDeSemana,
  formatearRango,
  iso,
  lunesDeSemana,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import { ImportarDocumentoParrilla } from "@/components/parrilla/ImportarDocumentoParrilla";
import { cn } from "@/lib/utils";
import type {
  AusenciaRota,
  CoordinacionTurno,
  CuerpoActualizarProgramaRota,
  CuerpoCrearFranjaSemana,
  CuerpoCrearProgramaRota,
  CuerpoCrearTurnoRota,
  EstadoSwap,
  EventoRota,
  FiltrosSwaps,
  FranjaSemana,
  FranjaTurno,
  MiembroRota,
  PrioridadEvento,
  ProgramaRota,
  SwapTurno,
  TipoAusencia,
  TipoCoberturaEvento,
  TurnoCobertura,
  TurnoRota,
} from "@/types";

const CABECERA = {
  titulo: "Turnos",
  // Descripcion corta. La explicacion larga vivia aqui antes y comia mucho espacio
  // visual; ahora se ofrece bajo demanda con el icono "?" del calendario.
  descripcion: "Turnos y cobertura, semana a semana. (Los eventos a cubrir viven en Fuentes › Eventos.)",
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

// `COBERTURA` (presentación por tipo de cobertura) y `COLOR_PRIORIDAD` viven en
// `@/lib/rota-calendario` como única fuente de verdad (los reusa la previsualización
// de import para verse idéntica al calendario real).

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

const TIPOS_AUSENCIA: { valor: TipoAusencia; etiqueta: string }[] = [
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "descanso", etiqueta: "Descanso" },
  { valor: "baja", etiqueta: "Baja" },
  { valor: "otro", etiqueta: "Otro" },
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

// --- Utilidades de fechas (semana lunes->domingo) --------------------------
//
// `lunesDeSemana`, `iso`, `lunesSiguiente`, `formatearRango`, `diaCorto` y
// `esFinDeSemana` viven en `@/lib/rota-calendario` (única fuente de verdad, reusada
// por la previsualización de import). Aquí solo queda lo específico de esta página.

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
  // Pestaña activa (controlada). La gestión de EVENTOS se mudó al hub de Fuentes
  // (ola "Calendario = turnos / Fuentes = eventos"); aquí el Calendario es solo turnos
  // + su cobertura derivada.
  const [pestania, setPestania] = React.useState("calendario");

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          // Hoy la rota es solo de ClaroSports. Multi-marca pendiente. El badge
          // se redujo (texto compacto, sin "Marca:" prefijo) para no comer la
          // fila de acciones del calendario; el tooltip da el contexto completo.
          <Tooltip label={`Esta rota cubre solo ${ETIQUETA_MARCA_ROTA}. Multi-marca pendiente.`}>
            <Badge
              variant="outline"
              className="px-1.5 py-0 text-[10px] font-normal text-muted-foreground"
              data-testid="banner-marca-rota"
            >
              {ETIQUETA_MARCA_ROTA}
            </Badge>
          </Tooltip>
        }
      />
      <Tabs value={pestania} onValueChange={setPestania} className="space-y-4">
        <TabsList>
          <TabsTrigger value="calendario">Calendario</TabsTrigger>
          <TabsTrigger value="mis-turnos">Mis turnos</TabsTrigger>
          <TabsTrigger value="cambios-ausencias">Cambios y ausencias</TabsTrigger>
          <TabsTrigger value="programas">Programas</TabsTrigger>
        </TabsList>

        <TabsContent value="calendario">
          <Calendario lunes={lunes} setLunes={setLunes} esAdmin={esAdmin} />
        </TabsContent>
        <TabsContent value="mis-turnos">
          <MisTurnos lunes={lunes} setLunes={setLunes} />
        </TabsContent>
        <TabsContent value="cambios-ausencias">
          {/* Ola "fusion real": una sola vista que mezcla cambios de turno y
              ausencias en una lista cronologica unica, con filtros por tipo y
              estado. Sin sub-tabs. */}
          <CambiosYAusencias esAdmin={esAdmin} />
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
      <span className="inline-flex items-center gap-1.5">
        <ShieldCheck className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" /> Coordinador
        por celda
      </span>
    </div>
  );
}

/**
 * Icono "?" con popover que muestra la leyenda completa bajo demanda. Sustituye a la
 * `LeyendaCobertura` que vivia siempre visible bajo la cabecera del calendario y la
 * llenaba de ruido visual; ahora la leyenda solo aparece cuando el usuario la pide.
 *
 * Popover autocontenido (mismo patron que IndicadorEstado): se cierra al pulsar fuera
 * o con Escape.
 */
function AyudaLeyenda() {
  const [abierto, setAbierto] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!abierto) return;
    function alPulsarFuera(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setAbierto(false);
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  return (
    <div ref={ref} className="relative inline-flex">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground"
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="dialog"
        aria-expanded={abierto}
        aria-label="Leyenda del calendario"
        title="Leyenda del calendario"
      >
        <HelpCircle className="h-4 w-4" />
      </Button>
      {abierto && (
        <div
          role="dialog"
          aria-label="Leyenda del calendario"
          className="absolute right-0 top-full z-50 mt-2 w-[20rem] max-w-[90vw] rounded-lg border border-border bg-popover p-3 text-popover-foreground shadow-md"
        >
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Leyenda
          </p>
          <LeyendaCobertura />
        </div>
      )}
    </div>
  );
}

/**
 * Botón "Más" (overflow `⋯`) que abre un menú con las acciones secundarias del
 * calendario: copia de semana anterior, configuración de franjas, exportes. Mantiene
 * la primera fila reservada a las acciones primarias (Aprobar/Despublicar) y al
 * estado de la semana, sin perder ninguna funcionalidad.
 *
 * Implementacion: reusa `MenuContextual` con `disparador="click"` y un trigger
 * explicito (no hay `DropdownMenu` de shadcn instalado en el repo).
 */
function MenuMasAcciones({
  esAdmin,
  semanaAprobada,
  onCopiarAnterior,
  onAbrirFranjasSemana,
  onAbrirPlantillaFranjas,
  onAbrirCarga,
  onExportExcel,
  onExportCsv,
  copiarPendiente,
}: {
  esAdmin: boolean;
  semanaAprobada: boolean;
  onCopiarAnterior: () => void;
  onAbrirFranjasSemana: () => void;
  onAbrirPlantillaFranjas: () => void;
  onAbrirCarga: () => void;
  onExportExcel: () => void;
  onExportCsv: () => void;
  copiarPendiente: boolean;
}) {
  const items: EntradaMenuContextual[] = [];

  if (esAdmin) {
    items.push({
      etiqueta: copiarPendiente ? "Copiando…" : "Copiar semana anterior",
      icono: Copy,
      onClick: onCopiarAnterior,
      deshabilitado: copiarPendiente || semanaAprobada,
    });
    items.push({
      etiqueta: "Configurar franjas de esta semana",
      icono: CalendarDays,
      onClick: onAbrirFranjasSemana,
    });
    items.push({
      etiqueta: "Plantilla por defecto de franjas",
      icono: Clock,
      onClick: onAbrirPlantillaFranjas,
    });
    items.push({ separador: true });
  }
  items.push({
    etiqueta: "Carga del equipo",
    icono: Users,
    onClick: onAbrirCarga,
  });
  items.push({ separador: true });
  items.push({
    etiqueta: "Descargar Excel",
    icono: Download,
    onClick: onExportExcel,
  });
  items.push({
    etiqueta: "Descargar CSV",
    icono: Download,
    onClick: onExportCsv,
  });

  return (
    <MenuContextual items={items} disparador="click">
      <Button
        type="button"
        variant="outline"
        size="icon"
        aria-label="Más acciones"
        title="Más acciones"
        data-testid="rota-mas-acciones"
      >
        <MoreHorizontal className="h-4 w-4" />
      </Button>
    </MenuContextual>
  );
}

/**
 * Badge de estado de la semana con tooltip que explica al usuario el significado
 * (Borrador = no visible para el equipo; Publicada = el equipo ya la ve). Reemplaza
 * los badges desnudos sin contexto que dejaba la cabecera anterior.
 */
function BadgeEstadoSemana({ aprobada, hayTurnos }: { aprobada: boolean; hayTurnos: boolean }) {
  if (aprobada) {
    return (
      <Tooltip label="Visible para el equipo (publicada).">
        <Badge variant="ok" className="font-normal">
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Publicada
        </Badge>
      </Tooltip>
    );
  }
  if (!hayTurnos) return null;
  return (
    <Tooltip label="Los CMs aún no la ven; queda por aprobar y publicar.">
      <Badge variant="secondary" className="font-normal">
        Borrador
      </Badge>
    </Tooltip>
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
          className="absolute right-0 top-full z-20 mt-1 flex w-max max-w-[14rem] flex-col gap-1 rounded-md border border-border bg-popover p-2 shadow-md"
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

/**
 * Convierte "HH:MM" a minutos desde 00:00. Devuelve `null` si no parsea.
 */
function horaAMinutos(s: string): number | null {
  const m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (!Number.isFinite(h) || !Number.isFinite(mi)) return null;
  if (h < 0 || h > 23 || mi < 0 || mi > 59) return null;
  return h * 60 + mi;
}

/**
 * ¿`hora` (HH:MM) cae dentro del rango `[inicio, fin)` de una franja? Soporta franjas
 * que cruzan medianoche (`fin <= inicio`). Si la hora no parsea, devuelve `false`.
 */
function horaEnRangoFranja(hora: string, inicio: string, fin: string): boolean {
  const h = horaAMinutos(hora);
  const ini = horaAMinutos(inicio);
  const f = horaAMinutos(fin);
  if (h === null || ini === null || f === null) return false;
  if (ini === f) return false; // franja degenerada: no contiene nada
  if (ini < f) return h >= ini && h < f;
  // Cruza medianoche: [ini, 24:00) ∪ [00:00, f)
  return h >= ini || h < f;
}

/**
 * Devuelve el `id` de la franja de `semana.franjas` que contiene la hora del evento.
 * Para eventos sin coverage (no podemos leer `cobertura[].franja_id`): probamos las
 * franjas NO descanso por `orden`; si ninguna contiene, caemos en la franja de descanso
 * (o la primera por orden si tampoco hay). `franjas` debe venir ya ordenada por orden.
 */
function franjaIdParaHoraEvento(
  hora: string,
  franjas: FranjaSemana[],
): string | null {
  if (franjas.length === 0) return null;
  const noDescanso = franjas.filter((f) => !f.es_descanso);
  for (const f of noDescanso) {
    if (horaEnRangoFranja(hora, f.inicio, f.fin)) return f.id;
  }
  const descanso = franjas.find((f) => f.es_descanso);
  if (descanso) return descanso.id;
  return franjas[0]?.id ?? null;
}

/**
 * Color/banda visual de una franja en la rejilla del calendario. La franja de descanso
 * es muted; las franjas laborables alternan amber/sky/violet/teal por `orden` para no
 * depender del nombre literal (soportamos franjas custom).
 */
const BANDAS_FRANJA_LABORAL: { banda: string; fondo: string }[] = [
  { banda: "border-l-amber-400", fondo: "bg-amber-50/30 dark:bg-amber-950/10" },
  { banda: "border-l-sky-400", fondo: "bg-sky-50/30 dark:bg-sky-950/10" },
  { banda: "border-l-violet-400", fondo: "bg-violet-50/30 dark:bg-violet-950/10" },
  { banda: "border-l-teal-400", fondo: "bg-teal-50/30 dark:bg-teal-950/10" },
];

function presentacionFranja(franja: FranjaSemana, indiceLaboral: number): {
  banda: string;
  fondo: string;
} {
  if (franja.es_descanso) {
    return {
      banda: "border-l-zinc-300 dark:border-l-zinc-700",
      fondo: "bg-muted/30",
    };
  }
  return (
    BANDAS_FRANJA_LABORAL[indiceLaboral % BANDAS_FRANJA_LABORAL.length] ??
    BANDAS_FRANJA_LABORAL[0]!
  );
}

interface ItemEventoCalendario {
  evento: EventoRota;
  /** Turnos (cobertura derivada) que cubren el evento por (fecha, franja). */
  cobertura: TurnoCobertura[];
}

interface RecuadroPersona {
  miembro_id: string;
  miembro_nombre: string;
  /** El turno concreto de esta persona en esta celda (para CRUD: editar/duplicar/borrar). */
  turno: TurnoRota | null;
  /** `true` si el recuadro es "Sin cubrir" (eventos sin cobertura derivada). */
  sinCubrir: boolean;
  eventos: ItemEventoCalendario[];
}

/**
 * Calendario fusionado (día × franja × persona): la única vista de la rota.
 * Las filas son las franjas vivas de la semana (modelo "franjas por semana", incluyendo
 * la franja de descanso), las columnas son los 7 días. Cada celda contiene un recuadro
 * por persona que trabaja esa franja ese día — con sus eventos cubiertos como chips
 * dentro — más, opcionalmente, un recuadro "Sin cubrir" con los eventos sin coverage.
 *
 * Antes existían dos pestañas hermanas, "Calendario" (read-only) y "Turnos" (CRUD por
 * dropdown). La fusión las unifica: el dropdown "+ Añadir persona" aparece al pie de
 * cada celda cuando la semana es editable (no aprobada), y cada recuadro persona
 * expone el menú contextual (editar/duplicar/borrar) heredado de la rejilla anterior.
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
  const claveTurnos = ["rota", "turnos", lunes] as const;
  // El rango (lun→dom) de la semana en vista para acotar las consultas.
  const desde = lunes;
  const hasta = lunesSiguiente(lunes, 1); // exclusivo
  const coberturaQ = useQuery({
    queryKey: ["rota", "cobertura", lunes] as const,
    queryFn: ({ signal }) => api.cobertura({ lunes }, signal),
  });
  const turnosQ = useQuery({
    queryKey: claveTurnos,
    queryFn: ({ signal }) => api.listarTurnos({ lunes }, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  // Equipo completo (incluye sin cobertura): necesario para resolver candidatos a
  // coordinador (ola "coord") como Mariana o Ale, que tienen `cobertura=false`.
  const equipoTodosQ = useQuery({
    queryKey: ["rota", "equipo", "todos"],
    queryFn: ({ signal }) => api.rotaEquipoTodos(signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });
  // Coordinador por celda (ola "coord"): un PUT por celda, lista por semana.
  const coordinacionQ = useQuery({
    queryKey: ["rota", "coordinacion", lunes] as const,
    queryFn: ({ signal }) => api.listarCoordinacionSemana(lunes, signal),
  });

  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota"] });

  // `equipo` para la edición avanzada del chip (DialogEditarTurno admite reasignar a
  // cualquier miembro de la rota), y `cms` para el dropdown "+ Añadir persona" (sólo
  // CMs activos de ClaroSports). Mismo desglose que la rejilla Turnos anterior.
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? []);
  const cms = cmsClaroSports(equipoQ.data?.equipo ?? []);
  // Candidatos a coordinador (ola "coord"): usuarios con `puede_coordinar=true`. Se
  // sacan del equipo COMPLETO (no solo cobertura) porque hoy son Elias (cubre), Ale
  // y Mariana (NO cubren). El admin gestiona el flag desde /usuarios.
  const candidatosCoordinador = React.useMemo(
    () => (equipoTodosQ.data?.equipo ?? []).filter((m) => m.puede_coordinar),
    [equipoTodosQ.data?.equipo],
  );
  // Index de coordinaciones por (fecha|franja_id) -> CoordinacionTurno.
  const coordinacionPorCelda = React.useMemo(() => {
    const m = new Map<string, CoordinacionTurno>();
    for (const c of coordinacionQ.data?.coordinacion ?? []) {
      m.set(`${c.fecha}|${c.franja_id}`, c);
    }
    return m;
  }, [coordinacionQ.data?.coordinacion]);
  const semana = turnosQ.data;
  const turnos = React.useMemo(() => semana?.turnos ?? [], [semana?.turnos]);
  // Franjas vivas de la semana, ordenadas por `orden` (la franja Descanso suele ir al
  // final con orden=999). Memo para evitar re-cálculos.
  const franjasSemana = React.useMemo(
    () => (semana?.franjas ?? []).slice().sort((a, b) => a.orden - b.orden),
    [semana?.franjas],
  );

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
  // Diálogos de franjas: antes los abrían sus propios botones (BotonConfigFranjas /
  // BotonFranjasDeSemana). Tras la slimificación de la cabecera ahora se invocan desde
  // el menú "Más", así que la apertura se gobierna desde aquí.
  const [abrirFranjasSemana, setAbrirFranjasSemana] = React.useState(false);
  const [abrirPlantillaFranjas, setAbrirPlantillaFranjas] = React.useState(false);
  // Resumen "Carga del equipo": antes vivía como panel colapsable bajo el calendario;
  // ahora se abre bajo demanda desde el menú "Más" (popup), para no alargar la vista.
  const [abrirCarga, setAbrirCarga] = React.useState(false);

  // Mutaciones de cabecera (de la antigua pestaña Turnos): aprobar / despublicar /
  // copiar semana anterior. Sin cambios funcionales — sólo migradas aquí.
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
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Eventos con su cobertura derivada (el backend ya excluyó los `no_cubrir`).
  const eventosCobertura = React.useMemo(
    () => (coberturaQ.data?.eventos ?? []).filter((e) => e.fecha >= desde && e.fecha < hasta),
    [coberturaQ.data?.eventos, desde, hasta],
  );

  // Turnos indexados por (franja_id, fecha, miembro_id) → TurnoRota. Sirve para que el
  // recuadro persona conserve el id del turno (para borrar/duplicar) sin volver a
  // buscar. También lo usamos para construir la lista de personas por celda.
  const turnoPorCelda = React.useMemo(() => {
    const m = new Map<string, TurnoRota>();
    for (const t of turnos) m.set(`${t.franja_id}|${t.fecha}|${t.miembro_id}`, t);
    return m;
  }, [turnos]);

  // Personas que trabajan cada (franja_id, fecha) según los turnos publicados.
  const personasPorCelda = React.useMemo(() => {
    const m = new Map<string, TurnoRota[]>();
    for (const t of turnos) {
      const k = `${t.franja_id}|${t.fecha}`;
      const lista = m.get(k) ?? [];
      lista.push(t);
      m.set(k, lista);
    }
    // Orden estable por nombre para que los recuadros no salten entre renders.
    for (const lista of m.values()) {
      lista.sort((a, b) => a.miembro_nombre.localeCompare(b.miembro_nombre));
    }
    return m;
  }, [turnos]);

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

  // Índice por miembro para resolver rápido "¿esta persona tiene ausencia este día?".
  const ausenciasPorMiembro = React.useMemo(() => {
    const m = new Map<string, AusenciaRota[]>();
    for (const a of ausenciasQ.data?.ausencias ?? []) {
      const lista = m.get(a.miembro_id) ?? [];
      lista.push(a);
      m.set(a.miembro_id, lista);
    }
    return m;
  }, [ausenciasQ.data?.ausencias]);
  const ausenciaDe = React.useCallback(
    (miembroId: string, fecha: string): AusenciaRota | undefined =>
      (ausenciasPorMiembro.get(miembroId) ?? []).find(
        (a) => a.desde <= fecha && fecha <= a.hasta,
      ),
    [ausenciasPorMiembro],
  );

  // Itera los eventos y los reparte en su (franja_id, fecha) → persona/sin-cubrir.
  // - Con cobertura: cada cubridor entra en el recuadro de su persona (su `franja_id`
  //   ya viene resuelto por el backend, así que la asignación es directa).
  // - Sin cobertura: el evento cae en un recuadro "Sin cubrir" en la franja que su
  //   hora resuelve contra las franjas vivas de la semana. Si la semana aún no tiene
  //   franjas (race), el evento se pierde de la rejilla — caso raro, sin franjas no
  //   hay rejilla que pintar.
  const recuadrosPorCelda = React.useMemo(() => {
    const m = new Map<string, RecuadroPersona[]>(); // clave: `${franja_id}|${fecha}`
    // Primero las personas que trabajan cada celda (aunque no tengan eventos).
    for (const franja of franjasSemana) {
      for (const fecha of dias) {
        const personas = personasPorCelda.get(`${franja.id}|${fecha}`) ?? [];
        const lista: RecuadroPersona[] = personas.map((t) => ({
          miembro_id: t.miembro_id,
          miembro_nombre: t.miembro_nombre,
          turno: t,
          sinCubrir: false,
          eventos: [],
        }));
        m.set(`${franja.id}|${fecha}`, lista);
      }
    }
    // Coloca cada evento en su recuadro.
    for (const evento of eventosCobertura) {
      if (evento.cobertura.length === 0) {
        const franjaId = franjaIdParaHoraEvento(evento.hora, franjasSemana);
        if (!franjaId) continue;
        const clave = `${franjaId}|${evento.fecha}`;
        const lista = m.get(clave) ?? [];
        let recuadroSin = lista.find((r) => r.sinCubrir);
        if (!recuadroSin) {
          recuadroSin = {
            miembro_id: "",
            miembro_nombre: "Sin cubrir",
            turno: null,
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
        const clave = `${cob.franja_id}|${evento.fecha}`;
        const lista = m.get(clave) ?? [];
        const recuadro = lista.find(
          (r) => !r.sinCubrir && r.miembro_id === cob.miembro_id,
        );
        if (recuadro) {
          recuadro.eventos.push({ evento, cobertura: evento.cobertura });
        } else {
          // El backend devolvió una cobertura cuyo miembro no aparece en `turnosQ`
          // para esa (franja_id, fecha). Caso raro (carrera de invalidaciones); lo
          // metemos como persona del cubridor para no perder el dato. `turno` queda
          // null porque no tenemos el TurnoRota local; el menú de CRUD del recuadro
          // se desactiva (sólo se ven los chips de evento).
          const turnoLocal =
            turnoPorCelda.get(`${cob.franja_id}|${evento.fecha}|${cob.miembro_id}`) ??
            null;
          lista.push({
            miembro_id: cob.miembro_id,
            miembro_nombre: cob.miembro_nombre,
            turno: turnoLocal,
            sinCubrir: false,
            eventos: [{ evento, cobertura: evento.cobertura }],
          });
        }
        m.set(clave, lista);
      }
    }
    return m;
  }, [eventosCobertura, dias, personasPorCelda, franjasSemana, turnoPorCelda]);

  const inicio = semana?.inicio ?? coberturaQ.data?.inicio ?? dias[0] ?? "";
  const fin = semana?.fin ?? coberturaQ.data?.fin ?? dias[6] ?? "";
  const nCambiados = eventosCobertura.filter((e) => e.cambiado).length;
  // `editable` requiere admin + semana no aprobada. Los CMs no admin siempre ven la vista
  // en solo-lectura. La edición es inline: click en el chip abre el menú (Editar/Duplicar/
  // Eliminar); click en "Sin turno asignado" o "Sin cubrir" abre el dropdown.
  const editable = esAdmin && !semana?.aprobada;
  const cargando =
    coberturaQ.isPending ||
    turnosQ.isPending ||
    ausenciasQ.isPending ||
    equipoQ.isPending ||
    coordinacionQ.isPending;
  const error =
    coberturaQ.error || turnosQ.error || ausenciasQ.error || equipoQ.error ||
    coordinacionQ.error;

  return (
    <div className="space-y-4">
      {/* Cabecera SLIM (ola "cabecera-slim"): NavegadorSemana + ayuda a la izquierda; a la
          derecha el estado de la semana, el aviso de reprogramaciones, la accion primaria
          (Aprobar/Despublicar) y un menu "Mas" con el resto. La leyenda dejo de vivir
          siempre visible bajo la cabecera; se ofrece bajo demanda con el icono "?". */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <NavegadorSemana lunes={lunes} setLunes={setLunes} inicio={inicio} fin={fin} />
          <AyudaLeyenda />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <BadgeEstadoSemana
            aprobada={Boolean(semana?.aprobada)}
            hayTurnos={turnos.length > 0}
          />
          {nCambiados > 0 && (
            <Tooltip
              label={`${nCambiados} evento${nCambiados === 1 ? "" : "s"} reprogramado${
                nCambiados === 1 ? "" : "s"
              } sin avisar al equipo.`}
            >
              <Badge variant="aviso" className="gap-1 font-normal">
                <BellRing className="h-3.5 w-3.5" /> {nCambiados}
              </Badge>
            </Tooltip>
          )}
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
              onClick={async () => {
                if (
                  await confirmar({
                    mensaje:
                      "La semana volverá a ser editable. ¿Despublicar los turnos?",
                    destructivo: true,
                    textoConfirmar: "Despublicar",
                  })
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
          {esAdmin && (
            <ImportarDocumentoParrilla onAplicado={invalidar} />
          )}
          <MenuMasAcciones
            esAdmin={esAdmin}
            semanaAprobada={Boolean(semana?.aprobada)}
            copiarPendiente={copiarAnterior.isPending}
            onCopiarAnterior={() => copiarAnterior.mutate()}
            onAbrirFranjasSemana={() => setAbrirFranjasSemana(true)}
            onAbrirPlantillaFranjas={() => setAbrirPlantillaFranjas(true)}
            onAbrirCarga={() => setAbrirCarga(true)}
            onExportExcel={() => api.exportarRota("xlsx", { lunes })}
            onExportCsv={() => api.exportarRota("csv", { lunes })}
          />
        </div>
      </div>

      {abrirFranjasSemana && (
        <DialogFranjasDeSemana
          lunes={lunes}
          onCerrar={() => setAbrirFranjasSemana(false)}
        />
      )}
      {abrirPlantillaFranjas && (
        <DialogConfigFranjas onCerrar={() => setAbrirPlantillaFranjas(false)} />
      )}

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
            void equipoQ.refetch();
          }}
          cargando={coberturaQ.isFetching}
        />
      ) : (
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            {/* Rejilla principal: 1 cabecera con días + 1 fila por franja viva.
                `max-h-[calc(100vh-18rem)]` aprovecha el alto disponible con scroll interno
                si la semana se sale de pantalla; `min-w-[56rem]` mantiene legibilidad. */}
            <div className="overflow-auto" style={{ maxHeight: "calc(100dvh - 18rem)" }}>
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

                {/* Filas: una por franja viva. Borde superior grueso para marcar el cambio. */}
                {(() => {
                  let indiceLaboral = 0;
                  return franjasSemana.map((franja, idx) => {
                    const idxLab = franja.es_descanso ? -1 : indiceLaboral++;
                    const meta = presentacionFranja(franja, idxLab);
                    return (
                      <div
                        key={franja.id}
                        className={`grid grid-cols-[8rem_repeat(7,minmax(0,1fr))] gap-px ${
                          idx > 0 ? "border-t-4 border-t-border" : ""
                        }`}
                      >
                        {/* Etiqueta de franja (sticky a la izquierda para scroll horizontal). */}
                        <div
                          className={`sticky left-0 z-[1] flex flex-col justify-center border-l-4 px-3 py-3 text-sm font-semibold ${meta.banda} ${meta.fondo}`}
                        >
                          <span className="flex items-center gap-1.5">
                            {franja.es_descanso ? (
                              <Sunset className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : idxLab === 0 ? (
                              <Sunrise className="h-3.5 w-3.5 text-muted-foreground" />
                            ) : (
                              <Sunset className="h-3.5 w-3.5 text-muted-foreground" />
                            )}
                            {franja.nombre}
                          </span>
                          <span className="text-xs font-normal text-muted-foreground">
                            {franja.es_descanso
                              ? "(descanso)"
                              : `${franja.inicio}–${franja.fin}`}
                          </span>
                        </div>
                        {dias.map((fecha) => {
                          const recuadros =
                            recuadrosPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                          // CMs disponibles para añadir aquí: los de ClaroSports que no
                          // estén ya asignados a esta celda. La franja Descanso también
                          // admite asignaciones (turno de no-laboral explícito).
                          const yaEnCelda = new Set(
                            recuadros
                              .filter((r) => !r.sinCubrir && r.miembro_id)
                              .map((r) => r.miembro_id),
                          );
                          const cmsDisponibles = cms.filter(
                            (m) => !yaEnCelda.has(m.id),
                          );
                          const coordinacionCelda = coordinacionPorCelda.get(
                            `${fecha}|${franja.id}`,
                          );
                          return (
                            <CeldaDeRejilla
                              key={`${franja.id}-${fecha}`}
                              lunes={lunes}
                              fecha={fecha}
                              franja={franja}
                              recuadros={recuadros}
                              equipo={equipo}
                              cmsDisponibles={cmsDisponibles}
                              editable={editable}
                              finde={esFinDeSemana(fecha)}
                              ausenciaDe={ausenciaDe}
                              coordinacion={coordinacionCelda}
                              candidatosCoordinador={candidatosCoordinador}
                              coordinacionEditable={esAdmin && !semana?.aprobada}
                              onEditarEvento={(e) => setEventoSeleccionado(e)}
                              onCambio={invalidar}
                            />
                          );
                        })}
                      </div>
                    );
                  });
                })()}
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

      {abrirCarga && (
        <DialogCargaEquipo lunes={lunes} onCerrar={() => setAbrirCarga(false)} />
      )}
    </div>
  );
}

/**
 * Badge de COORDINADOR por celda (ola "coord"): muestra "Coord: <nombre>" o "Sin coord".
 * Click (si editable) abre un Select con los candidatos (`puede_coordinar=true`); la X
 * inline (solo si hay coordinador y editable) borra la asignación. Si la semana está
 * aprobada o el usuario no es admin, queda en modo solo-lectura (sin Select ni X).
 */
function BadgeCoordinador({
  lunes,
  fecha,
  franja,
  coordinacion,
  candidatos,
  editable,
  onCambio,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  coordinacion?: CoordinacionTurno;
  candidatos: MiembroRota[];
  editable: boolean;
  onCambio: () => void;
}) {
  const [open, setOpen] = React.useState(false);

  const asignar = useMutation({
    mutationFn: (coordinador_id: string) =>
      api.setCoordinador({
        lunes,
        fecha,
        franja_id: franja.id,
        coordinador_id,
      }),
    onSuccess: () => {
      toast.success("Coordinador asignado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const quitar = useMutation({
    mutationFn: () =>
      api.quitarCoordinador({ fecha, franja_id: franja.id }),
    onSuccess: () => {
      toast.success("Coordinador quitado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cargando = asignar.isPending || quitar.isPending;

  if (!editable) {
    // Solo lectura: si hay coordinador, lo mostramos; si no, badge muted "Sin coord".
    return coordinacion ? (
      <span
        className="inline-flex max-w-full items-center gap-1 rounded border border-sky-300/70 bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-800 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-300"
        title={`Coordina: ${coordinacion.coordinador_nombre}`}
      >
        <ShieldCheck className="h-3 w-3 shrink-0" />
        <span className="truncate">
          Coord: {coordinacion.coordinador_nombre || "—"}
        </span>
      </span>
    ) : (
      <span className="inline-flex max-w-full items-center gap-1 rounded border border-dashed border-border/60 bg-background px-1.5 py-0.5 text-[10px] text-muted-foreground/60">
        Sin coord
      </span>
    );
  }

  // Editable: Select para asignar/cambiar + X para borrar (si hay).
  return (
    <div className="flex items-center gap-1">
      <Select
        value={coordinacion?.coordinador_id ?? ""}
        open={open}
        onOpenChange={setOpen}
        onValueChange={(id) => {
          if (!id) return;
          asignar.mutate(id);
        }}
        disabled={cargando || candidatos.length === 0}
      >
        <SelectTrigger
          aria-label={`Coordinador de ${franja.nombre} del ${fecha}`}
          className={cn(
            "h-6 flex-1 gap-1 px-1.5 text-[10px]",
            coordinacion
              ? "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-300"
              : "border-dashed border-border bg-background text-muted-foreground",
          )}
        >
          <ShieldCheck className="h-3 w-3 shrink-0" />
          <span className="truncate">
            {coordinacion
              ? `Coord: ${coordinacion.coordinador_nombre || "—"}`
              : candidatos.length === 0
                ? "Sin candidatos"
                : "Sin coord"}
          </span>
        </SelectTrigger>
        <SelectContent>
          {candidatos.map((c) => (
            <SelectItem key={c.id} value={c.id}>
              {c.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {coordinacion && (
        <Button
          size="icon"
          variant="ghost"
          className="h-6 w-6 text-muted-foreground hover:text-destructive"
          aria-label="Quitar coordinador"
          title="Quitar coordinador"
          onClick={() => quitar.mutate()}
          disabled={cargando}
        >
          {quitar.isPending ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <X className="h-3 w-3" />
          )}
        </Button>
      )}
    </div>
  );
}

/**
 * Una celda (franja × día) de la rejilla. Mantiene estado local para abrir el dropdown
 * desde dos puntos de entrada: el propio trigger del dropdown al pie de la celda y el
 * recuadro "Sin cubrir" cuando hay eventos sin coverage. La separación a componente es
 * lo que permite tener `useState` por celda sin polucionar el padre con un Map.
 */
function CeldaDeRejilla({
  lunes,
  fecha,
  franja,
  recuadros,
  equipo,
  cmsDisponibles,
  editable,
  finde,
  ausenciaDe,
  coordinacion,
  candidatosCoordinador,
  coordinacionEditable,
  onEditarEvento,
  onCambio,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  recuadros: RecuadroPersona[];
  equipo: MiembroRota[];
  cmsDisponibles: MiembroRota[];
  editable: boolean;
  finde: boolean;
  ausenciaDe: (miembroId: string, fecha: string) => AusenciaRota | undefined;
  /** Coordinador asignado a esta celda (si lo hay). Ola "coord". */
  coordinacion?: CoordinacionTurno;
  /** Candidatos a coordinador (usuarios con `puede_coordinar=true`). */
  candidatosCoordinador: MiembroRota[];
  /** True si el admin puede editar la coordinación (semana NO aprobada). */
  coordinacionEditable: boolean;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
}) {
  // Cada vez que sube, el dropdown del pie se abre. Se usa para que un click en el header
  // del recuadro "Sin cubrir" abra el dropdown sin necesitar pasar refs.
  const [pedidoAbrir, setPedidoAbrir] = React.useState(0);
  const placeholderDropdown =
    recuadros.length === 0
      ? franja.es_descanso
        ? "—"
        : "Sin turno asignado"
      : "Añadir persona";
  return (
    <div
      className={cn(
        "flex min-h-[8rem] flex-col gap-2 border-l p-2",
        finde && "bg-amber-50/20 dark:bg-amber-950/5",
      )}
    >
      {/* Badge de coordinador (ola "coord"): siempre visible si hay coordinador o si
          la celda es editable; en franja Descanso lo ocultamos porque no aplica. */}
      {!franja.es_descanso && (
        <BadgeCoordinador
          lunes={lunes}
          fecha={fecha}
          franja={franja}
          coordinacion={coordinacion}
          candidatos={candidatosCoordinador}
          editable={coordinacionEditable}
          onCambio={onCambio}
        />
      )}
      {recuadros.length === 0 && !editable && (
        <div className="rounded-md border border-dashed border-border/60 px-2 py-3 text-center text-[11px] text-muted-foreground/60">
          {franja.es_descanso ? "—" : "Sin turno asignado"}
        </div>
      )}
      {recuadros.map((rec) => (
        <RecuadroPersonaCalendario
          key={`${rec.miembro_id}-${rec.sinCubrir ? "sin" : "ok"}`}
          recuadro={rec}
          franja={franja}
          equipo={equipo}
          ausencia={
            rec.sinCubrir ? undefined : ausenciaDe(rec.miembro_id, fecha)
          }
          editable={editable}
          onEditarEvento={onEditarEvento}
          onCambio={onCambio}
          onClickHeaderSinCubrir={
            editable ? () => setPedidoAbrir((n) => n + 1) : undefined
          }
        />
      ))}
      {editable && (
        <DropdownAnadirPersona
          lunes={lunes}
          fecha={fecha}
          franja={franja}
          cmsDisponibles={cmsDisponibles}
          onCambio={onCambio}
          placeholder={placeholderDropdown}
          pedidoAbrir={pedidoAbrir}
        />
      )}
    </div>
  );
}

/**
 * Un recuadro por persona dentro de una celda día-franja del calendario fusionado. La
 * cabecera del recuadro reutiliza `ChipTurnoCM`: cuando `editable=true` y el recuadro
 * representa a una persona real (no "Sin cubrir"), expone el menú contextual de CRUD
 * (editar detalles / duplicar / borrar) y el botón × inline para quitar el turno. Los
 * eventos cubiertos por esa persona aparecen como chips clicables debajo.
 */
function RecuadroPersonaCalendario({
  recuadro,
  franja,
  equipo,
  ausencia,
  editable,
  onEditarEvento,
  onCambio,
  onClickHeaderSinCubrir,
}: {
  recuadro: RecuadroPersona;
  franja: FranjaSemana;
  /** Equipo de la rota (para que `DialogEditarTurno` pueda reasignar). */
  equipo: MiembroRota[];
  ausencia?: AusenciaRota;
  /** `true` si la semana es borrador (no aprobada): habilita CRUD de turnos. */
  editable: boolean;
  onEditarEvento: (evento: EventoRota) => void;
  onCambio: () => void;
  /**
   * Cuando el recuadro es "Sin cubrir" y el padre quiere abrir el dropdown al hacer
   * click en su header, pasa este callback. Solo lo recibe el header sinCubrir.
   */
  onClickHeaderSinCubrir?: () => void;
}) {
  const esDescanso = franja.es_descanso;
  const estilo = recuadro.sinCubrir
    ? "border-dashed border-amber-300/70 bg-amber-50/30 dark:bg-amber-950/10"
    : esDescanso
      ? "border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900/40"
      : "border-border bg-background";
  return (
    <div className={`flex flex-col gap-1 rounded-md border p-1.5 text-xs ${estilo}`}>
      <div className="flex items-center justify-between gap-1">
        {recuadro.sinCubrir ? (
          onClickHeaderSinCubrir ? (
            <button
              type="button"
              onClick={onClickHeaderSinCubrir}
              className="truncate text-left font-medium text-amber-700 hover:underline dark:text-amber-400"
              title="Asignar una persona a esta franja"
            >
              Sin cubrir
            </button>
          ) : (
            <span className="truncate font-medium text-amber-700 dark:text-amber-400">
              Sin cubrir
            </span>
          )
        ) : recuadro.turno ? (
          // `ChipTurnoCM` ya envuelve el nombre en un menú contextual (editar /
          // duplicar / borrar) + botón × para quitar el turno. Reusamos el mismo
          // componente que la rejilla CRUD anterior — una única fuente de verdad.
          <ChipTurnoCM
            turno={recuadro.turno}
            equipo={equipo}
            ausencia={ausencia}
            editable={editable}
            onCambio={onCambio}
          />
        ) : (
          // Coverage huérfana: el backend devolvió un cubridor cuyo TurnoRota local no
          // tenemos (carrera de invalidación). Mostramos el nombre sin menú; la acción
          // CRUD vuelve disponible al siguiente refetch.
          <span className="inline-flex max-w-full items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-xs">
            <User className="h-3 w-3 shrink-0 text-muted-foreground" />
            <span className="truncate">{recuadro.miembro_nombre}</span>
          </span>
        )}
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

/**
 * Dropdown "+ Añadir persona" al pie de cada celda del calendario. Asigna un CM de
 * ClaroSports a la (fecha, franja_id) creando un turno; maneja 409 `requiere_override`
 * (regla de sábado consecutivo) abriendo un dialog de confirmación. Extraído de la
 * antigua `CeldaFranjaDia` para reutilizarlo dentro de la rejilla fusionada.
 */
function DropdownAnadirPersona({
  lunes,
  fecha,
  franja,
  cmsDisponibles,
  onCambio,
  placeholder = "Añadir persona",
  pedidoAbrir = 0,
}: {
  lunes: string;
  fecha: string;
  franja: FranjaSemana;
  cmsDisponibles: MiembroRota[];
  onCambio: () => void;
  /** Texto del trigger cuando no hay persona seleccionada. Por defecto "Añadir persona". */
  placeholder?: string;
  /**
   * Contador "trigger numérico": cada incremento abre el Select programáticamente. Sirve
   * para que el padre (la celda) abra el dropdown cuando el usuario hace click en otro
   * elemento (p. ej. el header del recuadro "Sin cubrir") sin necesitar refs.
   */
  pedidoAbrir?: number;
}) {
  const [pendienteOverride, setPendienteOverride] = React.useState<{
    miembroId: string;
    mensaje: string;
  } | null>(null);
  const [open, setOpen] = React.useState(false);
  // El primer render (pedidoAbrir=0) no debe abrir el dropdown; sólo los incrementos
  // posteriores cuentan como "el padre pide abrir". Mantengo el valor anterior con un ref.
  const ultimoPedido = React.useRef(pedidoAbrir);
  React.useEffect(() => {
    if (pedidoAbrir > ultimoPedido.current) setOpen(true);
    ultimoPedido.current = pedidoAbrir;
  }, [pedidoAbrir]);

  const crear = useMutation({
    mutationFn: ({ miembroId, override }: { miembroId: string; override: boolean }) => {
      const cuerpo: CuerpoCrearTurnoRota = {
        lunes,
        fecha,
        miembro_id: miembroId,
        franja_id: franja.id,
      };
      if (override) cuerpo.override = true;
      return api.crearTurno(cuerpo);
    },
    onSuccess: () => {
      setPendienteOverride(null);
      toast.success("Turno creado.");
      onCambio();
    },
    onError: (e, variables) => {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        (e.cuerpo?.requiere_override as boolean | undefined)
      ) {
        setPendienteOverride({ miembroId: variables.miembroId, mensaje: e.message });
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  return (
    <>
      <Select
        value=""
        open={open}
        onOpenChange={setOpen}
        onValueChange={(miembroId) => {
          if (!miembroId) return;
          crear.mutate({ miembroId, override: false });
        }}
        disabled={crear.isPending || cmsDisponibles.length === 0}
      >
        <SelectTrigger
          aria-label={`Añadir persona a ${franja.nombre} del ${fecha}`}
          className="h-7 w-full justify-start gap-1 border-dashed px-1.5 text-xs text-muted-foreground hover:text-foreground"
        >
          <Plus className="h-3 w-3" />
          <span className="truncate">
            {cmsDisponibles.length === 0 ? "Todos asignados" : placeholder}
          </span>
        </SelectTrigger>
        <SelectContent>
          {cmsDisponibles.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {pendienteOverride && (
        <Dialog open onOpenChange={(o) => !o && setPendienteOverride(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>¿Forzar la cobertura?</DialogTitle>
              <DialogDescription>{pendienteOverride.mensaje}</DialogDescription>
            </DialogHeader>
            <p className="text-sm text-muted-foreground">
              Esta persona ya cubrió el sábado anterior. Confirma solo si es una
              cobertura estratégica intencional.
            </p>
            <DialogFooter>
              <Button variant="ghost" onClick={() => setPendienteOverride(null)}>
                Cancelar
              </Button>
              <Button
                variant="outline"
                className="text-amber-700 hover:text-amber-700 dark:text-amber-400"
                onClick={() =>
                  crear.mutate({
                    miembroId: pendienteOverride.miembroId,
                    override: true,
                  })
                }
                disabled={crear.isPending}
              >
                {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
                <AlertTriangle className="h-4 w-4" /> Forzar override
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </>
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
            onClick={async () => {
              if (
                await confirmar({
                  mensaje: "¿Borrar este evento? Sus turnos también se perderán.",
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

// --- Helpers de la rejilla CRUD (consumidos por el Calendario fusionado) --
//
// Modelo: un turno NO está ligado a un evento. Es el horario que cada persona tiene
// en (fecha, franja_id). La cobertura es derivada. El CRUD vive ahora dentro del
// Calendario fusionado (la antigua pestaña "Turnos" se absorbió aquí); estas
// utilidades se conservan porque siguen siendo la fuente de la lista de CMs y de
// los chips de persona con menú.

/**
 * Restringe el equipo a los community managers cubriendo ClaroSports activos.
 *
 * Aplica los tres filtros pedidos por Bernardo:
 *  - `marcas.includes("claro-sports")` (vertical correcta).
 *  - `cobertura === true` (la persona está disponible para cubrir hoy).
 *  - `cargo === "community_manager"` (los coordinadores quedan fuera; Elías
 *    coordina pero no se asigna a una franja).
 *
 * Si los tres filtros dejan la lista vacía (puede ocurrir en entornos donde el
 * seed de cargos del organigrama AMX aún no se ha aplicado a la BD), degrada al
 * filtro por marca+cobertura para no romper la rejilla.
 */
function cmsClaroSports(equipo: MiembroRota[]): MiembroRota[] {
  const porMarca = filtrarEquipoPorMarca(equipo).filter((m) => m.cobertura !== false);
  const estrictos = porMarca.filter((m) => m.cargo === "community_manager");
  if (estrictos.length > 0) return estrictos;
  return porMarca;
}

// La antigua pestaña `Turnos` (rejilla CRUD por dropdown) se fusionó con el Calendario:
// su cabecera de acciones (badges/copia/aprobar/despublicar/franjas/exportar) y la
// rejilla con dropdown + `ChipTurnoCM` ahora viven dentro de `Calendario` arriba.
// `ChipTurnoCM` y `DialogEditarTurno` (debajo) siguen siendo reutilizables.

function ChipTurnoCM({
  turno,
  equipo,
  ausencia,
  editable,
  onCambio,
}: {
  turno: TurnoRota;
  /** Equipo de la rota (para que `DialogEditarTurno` pueda reasignar). */
  equipo: MiembroRota[];
  ausencia?: AusenciaRota;
  editable: boolean;
  onCambio: () => void;
}) {
  const [editandoDetalles, setEditandoDetalles] = React.useState(false);

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
      if (e instanceof ApiError && e.status === 409) {
        toast.info(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  // Tooltip con motivo + ausencia + nota relevo, para no cargar la celda.
  const tooltipPartes: string[] = [];
  if (turno.motivo) tooltipPartes.push(`Motivo: ${turno.motivo}`);
  if (turno.nota_relevo) tooltipPartes.push(`Relevo: ${turno.nota_relevo}`);
  if (ausencia)
    tooltipPartes.push(
      `Ausente (${ausencia.tipo})${ausencia.motivo ? `: ${ausencia.motivo}` : ""}`,
    );
  const tieneTooltip = tooltipPartes.length > 0;
  const etiquetaTooltip = tooltipPartes.join(" · ");

  if (!editable) {
    const chip = (
      <span className="inline-flex max-w-full items-center gap-1 rounded border bg-muted/40 px-1.5 py-0.5 text-xs">
        <User className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate">{turno.miembro_nombre}</span>
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
      </span>
    );
    return tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip;
  }

  const itemsMenu: EntradaMenuContextual[] = [
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
      etiqueta: "Eliminar",
      icono: Trash2,
      destructivo: true,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Eliminar el turno de ${turno.miembro_nombre}?`,
            destructivo: true,
            textoConfirmar: "Eliminar",
          })
        )
          borrar.mutate();
      },
      deshabilitado: borrar.isPending,
    },
  ];

  const chip = (
    <MenuContextual items={itemsMenu} disparador="ambos">
      <span className="inline-flex max-w-full cursor-pointer items-center gap-1 rounded border bg-background px-1.5 py-0.5 text-xs hover:bg-accent">
        <User className="h-3 w-3 shrink-0 text-muted-foreground" />
        <span className="truncate">{turno.miembro_nombre}</span>
        {turno.override && (
          <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" aria-label="override" />
        )}
        {ausencia && !turno.override && (
          <Plane className="h-3 w-3 shrink-0 text-orange-600" aria-label="ausente" />
        )}
        <button
          type="button"
          aria-label={`Borrar turno de ${turno.miembro_nombre}`}
          onClick={async (e) => {
            e.stopPropagation();
            if (borrar.isPending) return;
            if (
              await confirmar({
                mensaje: `¿Borrar el turno de ${turno.miembro_nombre}?`,
                destructivo: true,
                textoConfirmar: "Borrar",
              })
            )
              borrar.mutate();
          }}
          disabled={borrar.isPending}
          className="ml-0.5 rounded text-muted-foreground hover:text-destructive disabled:opacity-50"
        >
          {borrar.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <X className="h-3 w-3" />}
        </button>
      </span>
    </MenuContextual>
  );

  return (
    <>
      {tieneTooltip ? <Tooltip label={etiquetaTooltip}>{chip}</Tooltip> : chip}
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
    </>
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

// --- Popup "Carga del equipo" -----------------------------------------------

/**
 * Resumen de carga del equipo de la semana, en un diálogo. Antes era un panel
 * colapsable bajo el calendario; ahora se invoca bajo demanda desde el menú "Más"
 * para no alargar la vista. El componente sólo se monta cuando el popup está abierto,
 * así que la query arranca al abrir.
 */
function DialogCargaEquipo({ lunes, onCerrar }: { lunes: string; onCerrar: () => void }) {
  const q = useQuery({
    queryKey: ["rota", "carga", lunes],
    queryFn: ({ signal }) => api.cargaRota({ lunes }, signal),
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

// `diaCorto` y `esFinDeSemana` se movieron a `@/lib/rota-calendario`.

// --- Dialog "Configurar franjas" (solo admin) -------------------------------
//
// Los wrappers `BotonConfigFranjas` / `BotonFranjasDeSemana` se eliminaron al fusionar
// sus acciones dentro del menu "Mas" del calendario (ola "cabecera-slim"): la apertura
// la gobierna `Calendario` con estado propio (`abrirFranjasSemana` / `abrirPlantillaFranjas`)
// y aqui solo viven los dialogs.

function DialogFranjasDeSemana({
  lunes,
  onCerrar,
}: {
  lunes: string;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const claveLista = ["rota", "franjas", lunes] as const;
  const q = useQuery({
    queryKey: claveLista,
    queryFn: ({ signal }) => api.listarFranjasSemana(lunes, signal),
  });
  const franjas = (q.data?.franjas ?? []).slice().sort((a, b) => a.orden - b.orden);

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: claveLista });
    void queryClient.invalidateQueries({ queryKey: ["rota", "turnos"] });
  };

  const crear = useMutation({
    mutationFn: (cuerpo: CuerpoCrearFranjaSemana) => api.crearFranjaSemana(lunes, cuerpo),
    onSuccess: () => {
      invalidar();
      toast.success("Franja añadida.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Franjas de esta semana ({lunes})</DialogTitle>
          <DialogDescription>
            Cada semana tiene sus franjas (nombre libre, rangos HH:MM, solapes
            permitidos). La franja Descanso marca turnos de no-laboral: la persona NO
            cubre eventos ese día pero tiene turno explícito.
          </DialogDescription>
        </DialogHeader>
        {q.isPending ? (
          <Skeleton className="h-32 w-full rounded-md" />
        ) : (
          <div className="space-y-2">
            {franjas.map((f) => (
              <FilaFranjaSemana key={f.id} franja={f} onCambio={invalidar} />
            ))}
            <FormCrearFranjaSemana
              cargando={crear.isPending}
              onCrear={(cuerpo) => crear.mutate(cuerpo)}
            />
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FilaFranjaSemana({
  franja,
  onCambio,
}: {
  franja: FranjaSemana;
  onCambio: () => void;
}) {
  const [nombre, setNombre] = React.useState(franja.nombre);
  const [inicio, setInicio] = React.useState(franja.inicio);
  const [fin, setFin] = React.useState(franja.fin);
  const [orden, setOrden] = React.useState(String(franja.orden));

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarFranjaSemana(franja.id, {
        nombre: nombre !== franja.nombre ? nombre : undefined,
        inicio: inicio !== franja.inicio ? inicio : undefined,
        fin: fin !== franja.fin ? fin : undefined,
        orden:
          Number.parseInt(orden, 10) !== franja.orden
            ? Number.parseInt(orden, 10)
            : undefined,
      }),
    onSuccess: () => {
      toast.success("Franja actualizada.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: (forzar: boolean) => api.borrarFranjaSemana(franja.id, { forzar }),
    onSuccess: (res) => {
      const sufijo =
        res.turnos_borrados && res.turnos_borrados > 0
          ? ` (${res.turnos_borrados} turnos también)`
          : "";
      toast.success(`Franja borrada${sufijo}.`);
      onCambio();
    },
    onError: async (e) => {
      if (e instanceof ApiError && e.status === 409) {
        const asociados = (e.cuerpo?.turnos_asociados as number | undefined) ?? 0;
        if (
          await confirmar({
            mensaje: `Tiene ${asociados} turnos asociados. ¿Borrar también esos turnos?`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        ) {
          borrar.mutate(true);
        }
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  const cambiada =
    nombre !== franja.nombre ||
    inicio !== franja.inicio ||
    fin !== franja.fin ||
    Number.parseInt(orden, 10) !== franja.orden;

  return (
    <div
      className={cn(
        "flex flex-wrap items-end gap-2 rounded border px-2 py-2",
        franja.es_descanso && "bg-muted/40",
      )}
    >
      <div className="flex-1 min-w-32">
        <Label className="text-xs text-muted-foreground">Nombre</Label>
        <Input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          className="h-8"
          disabled={franja.es_descanso}
          title={
            franja.es_descanso
              ? "La franja de descanso no se renombra (borra y crea otra)"
              : ""
          }
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Inicio</Label>
        <Input
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          placeholder="HH:MM"
          className="h-8"
          disabled={franja.es_descanso}
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Fin</Label>
        <Input
          value={fin}
          onChange={(e) => setFin(e.target.value)}
          placeholder="HH:MM"
          className="h-8"
          disabled={franja.es_descanso}
        />
      </div>
      <div className="w-20">
        <Label className="text-xs text-muted-foreground">Orden</Label>
        <Input
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
          className="h-8"
        />
      </div>
      <Button
        size="sm"
        variant="outline"
        onClick={() => actualizar.mutate()}
        disabled={!cambiada || actualizar.isPending}
      >
        Guardar
      </Button>
      <Button
        size="sm"
        variant="ghost"
        className="text-destructive"
        onClick={() => borrar.mutate(false)}
        disabled={borrar.isPending}
      >
        Borrar
      </Button>
    </div>
  );
}

function FormCrearFranjaSemana({
  cargando,
  onCrear,
}: {
  cargando: boolean;
  onCrear: (cuerpo: CuerpoCrearFranjaSemana) => void;
}) {
  const [nombre, setNombre] = React.useState("");
  const [inicio, setInicio] = React.useState("17:00");
  const [fin, setFin] = React.useState("01:00");
  const [orden, setOrden] = React.useState("2");
  const [esDescanso, setEsDescanso] = React.useState(false);

  const submit = () => {
    if (!nombre.trim()) {
      toast.error("Indica un nombre.");
      return;
    }
    onCrear({
      nombre: nombre.trim(),
      inicio,
      fin,
      orden: Number.parseInt(orden, 10) || 0,
      es_descanso: esDescanso,
    });
    setNombre("");
  };

  return (
    <div className="flex flex-wrap items-end gap-2 rounded border border-dashed px-2 py-2">
      <div className="flex-1 min-w-32">
        <Label className="text-xs text-muted-foreground">Añadir franja</Label>
        <Input
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Cobertura nocturna"
          className="h-8"
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Inicio</Label>
        <Input
          value={inicio}
          onChange={(e) => setInicio(e.target.value)}
          className="h-8"
        />
      </div>
      <div className="w-24">
        <Label className="text-xs text-muted-foreground">Fin</Label>
        <Input value={fin} onChange={(e) => setFin(e.target.value)} className="h-8" />
      </div>
      <div className="w-20">
        <Label className="text-xs text-muted-foreground">Orden</Label>
        <Input
          value={orden}
          onChange={(e) => setOrden(e.target.value)}
          className="h-8"
        />
      </div>
      <label className="flex items-center gap-1 text-xs">
        <input
          type="checkbox"
          checked={esDescanso}
          onChange={(e) => setEsDescanso(e.target.checked)}
        />
        Descanso
      </label>
      <Button size="sm" onClick={submit} disabled={cargando || !nombre.trim()}>
        <Plus className="h-4 w-4" /> Añadir
      </Button>
    </div>
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

// --- Formulario de nueva ausencia (reutilizado por CambiosYAusencias) -------

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

  // Sin wrapper Card: lo aporta el caller (CambiosYAusencias monta el formulario
  // colapsable dentro de su propio recuadro y elige el titulo segun el tipo).
  return (
    <div className="space-y-4">
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
          Registrar ausencia
        </Button>
      </div>
    </div>
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

  const [editando, setEditando] = React.useState(false);

  const etiquetaTipo =
    TIPOS_AUSENCIA.find((t) => t.valor === ausencia.tipo)?.etiqueta ?? ausencia.tipo;

  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-normal">
              <CalendarOff className="mr-1 h-3 w-3" /> Ausencia
            </Badge>
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
        <div className="flex shrink-0 items-center">
          <Button
            variant="ghost"
            size="icon"
            aria-label="Editar ausencia"
            className="text-muted-foreground hover:text-foreground"
            onClick={() => setEditando(true)}
            disabled={borrar.isPending}
          >
            <Pencil className="h-4 w-4" />
          </Button>
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
        </div>
      </CardContent>
      <DialogoEditarAusencia
        ausencia={ausencia}
        abierto={editando}
        onCerrar={() => setEditando(false)}
        onGuardada={() => {
          setEditando(false);
          onCambio();
        }}
      />
    </Card>
  );
}

/**
 * Diálogo para EDITAR una ausencia existente (PATCH /api/rota/ausencias/{id}).
 * Reutiliza los mismos campos que `NuevaAusencia` salvo la PERSONA: el backend
 * (`CuerpoActualizarAusenciaRota`) solo permite cambiar tipo / fechas / motivo.
 */
function DialogoEditarAusencia({
  ausencia,
  abierto,
  onCerrar,
  onGuardada,
}: {
  ausencia: AusenciaRota;
  abierto: boolean;
  onCerrar: () => void;
  onGuardada: () => void;
}) {
  const [tipo, setTipo] = React.useState<TipoAusencia>(ausencia.tipo);
  const [desde, setDesde] = React.useState(ausencia.desde);
  const [hasta, setHasta] = React.useState(ausencia.hasta);
  const [motivo, setMotivo] = React.useState(ausencia.motivo);

  // Al (re)abrir, repuebla los campos con los valores vigentes de la ausencia.
  React.useEffect(() => {
    if (abierto) {
      setTipo(ausencia.tipo);
      setDesde(ausencia.desde);
      setHasta(ausencia.hasta);
      setMotivo(ausencia.motivo);
    }
  }, [abierto, ausencia]);

  const guardar = useMutation({
    mutationFn: () =>
      api.actualizarAusenciaRota(ausencia.id, { tipo, desde, hasta, motivo: motivo.trim() }),
    onSuccess: () => {
      toast.success("Ausencia actualizada.");
      onGuardada();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar = desde !== "" && hasta !== "" && !guardar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Editar ausencia</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Persona</Label>
            <Input value={ausencia.miembro_nombre || "—"} disabled readOnly />
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
              <Label htmlFor="au-edit-desde">Desde</Label>
              <Input
                id="au-edit-desde"
                type="date"
                value={desde}
                onChange={(e) => setDesde(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="au-edit-hasta">Hasta</Label>
              <Input
                id="au-edit-hasta"
                type="date"
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="au-edit-motivo">
              Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <Input
              id="au-edit-motivo"
              value={motivo}
              onChange={(e) => setMotivo(e.target.value)}
              maxLength={200}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Helper compartido: chip toggle ----------------------------------------
//
// La gestión de EVENTOS se mudó al hub de Fuentes (ola "Calendario = turnos / Fuentes =
// eventos"): su panel completo vive en `components/eventos/PanelEventos.tsx`. Aquí solo
// sobrevive `ChipToggle`, que reusan los filtros de la pestaña Cambios y ausencias.

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

/** Timestamp ISO ("2026-05-25T18:42:11", UTC) como fecha-hora corta en CDMX. */
const formatearMomentoCorto = (s: string): string => formatearFechaHoraCorta(s);

/**
 * Vista FUSIONADA de Cambios de turno + Ausencias en una sola lista cronologica.
 *
 * La iteracion previa intento fusionar con sub-tabs (Cambios / Ausencias hermanas);
 * el usuario lo rechazo: aqui no hay sub-tabs. Una unica cabecera, un boton "Nueva
 * solicitud" que abre un formulario colapsable con selector de tipo, una banda de
 * chips para filtrar (tipo + estado) y una lista mezclada de tarjetas (cada una
 * con su badge de tipo: "Cambio" o "Ausencia").
 *
 * Sigue habiendo dos consultas backend (swaps y ausencias) porque cada recurso es
 * independiente; la fusion ocurre en cliente. Conserva el contrato actual de los
 * endpoints REST.
 */
function CambiosYAusencias({ esAdmin }: { esAdmin: boolean }) {
  const { usuario } = useSesion();
  const queryClient = useQueryClient();

  // Filtros locales (sin URL, solo estado): tipo y estado.
  const [filtroTipo, setFiltroTipo] = React.useState<"todo" | "cambios" | "ausencias">("todo");
  const [filtroEstado, setFiltroEstado] = React.useState<"activos" | "historial">("activos");
  const [formAbierto, setFormAbierto] = React.useState(false);
  const [tipoSolicitud, setTipoSolicitud] = React.useState<"cambio" | "ausencia">("cambio");

  // El usuario admin ve todos los swaps (incluyendo "Para aprobar" donde no es
  // parte). El resto solo ve los swaps en los que participa (`mio=true`).
  const filtrosSwaps: FiltrosSwaps = esAdmin ? {} : { mio: true };
  const swapsQ = useQuery({
    enabled: usuario !== null,
    queryKey: ["rota", "swaps", filtrosSwaps] as const,
    queryFn: ({ signal }) => api.listarSwaps(filtrosSwaps, signal),
  });
  const ausenciasQ = useQuery({
    queryKey: ["rota", "ausencias"] as const,
    queryFn: ({ signal }) => api.rotaAusencias({}, signal),
  });
  const equipoQ = useQuery({
    queryKey: ["rota", "equipo"],
    queryFn: ({ signal }) => api.rotaEquipo(signal),
  });
  const equipo = filtrarEquipoPorMarca(equipoQ.data?.equipo ?? []);

  const invalidarSwaps = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "swaps"] });
  const invalidarAusencias = () =>
    void queryClient.invalidateQueries({ queryKey: ["rota", "ausencias"] });

  // Cargando: si AMBOS estan pendientes (mostramos skeleton); de lo contrario
  // mezclamos lo que tengamos (evitamos parpadeos al cambiar de filtro).
  const cargandoTodo =
    (usuario !== null && swapsQ.isPending) || ausenciasQ.isPending;
  const errorSwaps = swapsQ.isError;
  const errorAusencias = ausenciasQ.isError;

  // Lista cronologica unificada: cada item es discriminado por `tipo` para que
  // el render decida que tarjeta usar. Orden DESC: el mas reciente primero.
  // - Swaps tienen `creado` (timestamp ISO).
  // - Ausencias NO tienen timestamp de creacion en el backend; usamos `desde`
  //   como proxy de "cuando entra en juego" (tradeoff conocido: si en futuro el
  //   backend persiste `creado_en`, se reemplaza por ese campo).
  type ItemSwap = { tipo: "cambio"; orden: string; swap: SwapTurno };
  type ItemAusencia = { tipo: "ausencia"; orden: string; ausencia: AusenciaRota };
  type ItemSolicitud = ItemSwap | ItemAusencia;

  const items: ItemSolicitud[] = React.useMemo(() => {
    const lista: ItemSolicitud[] = [];
    const swaps = swapsQ.data?.swaps ?? [];
    const ausencias = ausenciasQ.data?.ausencias ?? [];

    const esSwapActivo = (s: SwapTurno) => !ESTADOS_TERMINALES_SWAP.has(s.estado);
    // Heuristica para ausencias: "activa" = aun no ha terminado (hasta >= hoy).
    const hoy = iso(new Date());
    const esAusenciaActiva = (a: AusenciaRota) => (a.hasta || "") >= hoy;

    if (filtroTipo !== "ausencias") {
      for (const s of swaps) {
        const activo = esSwapActivo(s);
        if (filtroEstado === "activos" && !activo) continue;
        if (filtroEstado === "historial" && activo) continue;
        lista.push({ tipo: "cambio", orden: s.creado || s.actualizado || "", swap: s });
      }
    }
    if (filtroTipo !== "cambios") {
      for (const a of ausencias) {
        const activa = esAusenciaActiva(a);
        if (filtroEstado === "activos" && !activa) continue;
        if (filtroEstado === "historial" && activa) continue;
        lista.push({ tipo: "ausencia", orden: a.desde || "", ausencia: a });
      }
    }
    lista.sort((x, y) => (y.orden || "").localeCompare(x.orden || ""));
    return lista;
  }, [swapsQ.data, ausenciasQ.data, filtroTipo, filtroEstado]);

  // Sin sesion no hay "yo": el backend devuelve [] para `mio=true` y la creacion
  // de swap requiere usuario logueado. Avisamos honestamente.
  const sinSesion = usuario === null;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <ArrowLeftRight className="h-4 w-4" /> Cambios y ausencias
              </CardTitle>
              <p className="mt-1 text-xs text-muted-foreground">
                Pide un cambio de turno con un compañero o registra una ausencia
                (vacaciones, descanso, baja). Aparece todo en una lista, mas reciente
                arriba.
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant={formAbierto ? "outline" : "default"}
              onClick={() => setFormAbierto((v) => !v)}
              disabled={sinSesion && !equipo.length}
            >
              {formAbierto ? (
                <>
                  <X className="h-4 w-4" /> Cerrar
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4" /> Nueva solicitud
                </>
              )}
            </Button>
          </div>
        </CardHeader>
        {formAbierto && (
          <CardContent className="space-y-4 border-t pt-4">
            <div className="space-y-1.5">
              <Label className="text-xs uppercase tracking-wide text-muted-foreground">
                Tipo
              </Label>
              <div className="flex flex-wrap gap-2">
                <ChipToggle
                  activo={tipoSolicitud === "cambio"}
                  onClick={() => setTipoSolicitud("cambio")}
                >
                  <ArrowLeftRight className="mr-1 h-3.5 w-3.5" /> Cambio de turno
                </ChipToggle>
                <ChipToggle
                  activo={tipoSolicitud === "ausencia"}
                  onClick={() => setTipoSolicitud("ausencia")}
                >
                  <CalendarOff className="mr-1 h-3.5 w-3.5" /> Ausencia
                </ChipToggle>
              </div>
            </div>
            {tipoSolicitud === "cambio" ? (
              sinSesion ? (
                <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
                  Inicia sesion para pedir un cambio de turno con tus compañeros.
                </div>
              ) : (
                <FormularioNuevoSwap
                  miId={usuario.id}
                  onCreado={() => {
                    invalidarSwaps();
                    setFormAbierto(false);
                  }}
                />
              )
            ) : (
              <NuevaAusencia
                equipo={equipo}
                onCreada={() => {
                  invalidarAusencias();
                  setFormAbierto(false);
                }}
              />
            )}
          </CardContent>
        )}
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Tipo
        </span>
        <ChipToggle activo={filtroTipo === "todo"} onClick={() => setFiltroTipo("todo")}>
          Todo
        </ChipToggle>
        <ChipToggle activo={filtroTipo === "cambios"} onClick={() => setFiltroTipo("cambios")}>
          Cambios
        </ChipToggle>
        <ChipToggle
          activo={filtroTipo === "ausencias"}
          onClick={() => setFiltroTipo("ausencias")}
        >
          Ausencias
        </ChipToggle>
        <span className="ml-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Estado
        </span>
        <ChipToggle
          activo={filtroEstado === "activos"}
          onClick={() => setFiltroEstado("activos")}
        >
          Activos
        </ChipToggle>
        <ChipToggle
          activo={filtroEstado === "historial"}
          onClick={() => setFiltroEstado("historial")}
        >
          Historial
        </ChipToggle>
      </div>

      {errorSwaps && (
        <BloqueError
          titulo="No se pudieron cargar los cambios de turno"
          mensaje={mensajeError(swapsQ.error)}
          onReintentar={() => void swapsQ.refetch()}
          cargando={swapsQ.isFetching}
        />
      )}
      {errorAusencias && (
        <BloqueError
          titulo="No se pudieron cargar las ausencias"
          mensaje={mensajeError(ausenciasQ.error)}
          onReintentar={() => void ausenciasQ.refetch()}
          cargando={ausenciasQ.isFetching}
        />
      )}

      {cargandoTodo ? (
        <Skeleton className="h-40 w-full rounded-md" />
      ) : items.length === 0 ? (
        <EstadoVacio
          icono={ArrowLeftRight}
          titulo={
            filtroEstado === "historial"
              ? "Sin historial"
              : "Sin solicitudes activas"
          }
          texto={
            filtroEstado === "historial"
              ? "Aqui apareceran los cambios cerrados y las ausencias ya pasadas."
              : "Crea una con el boton 'Nueva solicitud'."
          }
        />
      ) : (
        <div className="space-y-3">
          {items.map((it) =>
            it.tipo === "cambio" ? (
              <TarjetaSwap
                key={`swap-${it.swap.id}`}
                swap={it.swap}
                miId={usuario?.id ?? ""}
                esAdmin={esAdmin}
              />
            ) : (
              <TarjetaAusencia
                key={`au-${it.ausencia.id}`}
                ausencia={it.ausencia}
                onCambio={invalidarAusencias}
              />
            ),
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Formulario SIMPLIFICADO para pedir un cambio de turno.
 *
 * Antes pedia 6 campos (compañero + fecha A + franja A + fecha B + franja B + motivo).
 * Ahora son 3: "Mi turno" (Select sobre los turnos REALES del solicitante en la
 * semana actual y la siguiente), "Turno deseado" (Select sobre los turnos de los
 * demas CMs en el mismo rango) y motivo opcional. De cada Select derivamos
 * `fecha`/`franja_id` (y `destinatario_id` del segundo). El backend sigue
 * recibiendo el mismo cuerpo `crearSwap`.
 *
 * Rango: hardcoded a "semana actual + siguiente" (14 dias). Si la lista queda
 * vacia avisamos al usuario en lugar de saltar a otra ventana.
 */
function FormularioNuevoSwap({
  miId,
  onCreado,
}: {
  miId: string;
  onCreado?: () => void;
}) {
  // Semana actual y la siguiente: dos consultas, una por semana, para reusar el
  // cache compartido con la pestaña Calendario.
  const lunesActual = React.useMemo(() => lunesDeSemana(new Date()), []);
  const lunesProxima = React.useMemo(() => lunesSiguiente(lunesActual, 1), [lunesActual]);

  const semana1Q = useQuery({
    queryKey: ["rota", "turnos", lunesActual] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes: lunesActual }, signal),
  });
  const semana2Q = useQuery({
    queryKey: ["rota", "turnos", lunesProxima] as const,
    queryFn: ({ signal }) => api.listarTurnos({ lunes: lunesProxima }, signal),
  });

  const turnos: TurnoRota[] = React.useMemo(
    () => [...(semana1Q.data?.turnos ?? []), ...(semana2Q.data?.turnos ?? [])],
    [semana1Q.data, semana2Q.data],
  );

  // Hoy en ISO: filtramos turnos pasados (no tiene sentido pedir cambio sobre
  // un dia que ya paso). La franja descanso si la permitimos: el backend valida.
  const hoyIso = React.useMemo(() => iso(new Date()), []);
  const turnosFuturos = React.useMemo(
    () => turnos.filter((t) => t.fecha >= hoyIso),
    [turnos, hoyIso],
  );

  const turnosMios = React.useMemo(
    () =>
      turnosFuturos
        .filter((t) => t.miembro_id === miId)
        .slice()
        .sort((a, b) => a.fecha.localeCompare(b.fecha) || a.franja_nombre.localeCompare(b.franja_nombre)),
    [turnosFuturos, miId],
  );
  const turnosOtros = React.useMemo(
    () =>
      turnosFuturos
        .filter((t) => t.miembro_id !== miId)
        .slice()
        .sort(
          (a, b) =>
            a.fecha.localeCompare(b.fecha) ||
            a.franja_nombre.localeCompare(b.franja_nombre) ||
            a.miembro_nombre.localeCompare(b.miembro_nombre),
        ),
    [turnosFuturos, miId],
  );

  // Las opciones del Select 1 codifican `${id}` y leemos el TurnoRota completo
  // por busqueda en la lista. Idem el Select 2.
  const [miTurnoId, setMiTurnoId] = React.useState("");
  const [turnoDeseadoId, setTurnoDeseadoId] = React.useState("");
  const [motivo, setMotivo] = React.useState("");

  const miTurno = turnosMios.find((t) => t.id === miTurnoId);
  const turnoDeseado = turnosOtros.find((t) => t.id === turnoDeseadoId);

  const crear = useMutation({
    mutationFn: () => {
      if (!miTurno || !turnoDeseado) throw new Error("Falta seleccionar los turnos.");
      return api.crearSwap({
        destinatario_id: turnoDeseado.miembro_id,
        fecha_a: miTurno.fecha,
        franja_a: miTurno.franja_id,
        fecha_b: turnoDeseado.fecha,
        franja_b: turnoDeseado.franja_id,
        motivo: motivo.trim(),
      });
    },
    onSuccess: () => {
      toast.success("Solicitud enviada. Tu compañero la vera en la lista.");
      setMiTurnoId("");
      setTurnoDeseadoId("");
      setMotivo("");
      onCreado?.();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cargando = semana1Q.isPending || semana2Q.isPending;
  const motivoExcedido = motivo.length > 500;
  const puedeCrear =
    miTurnoId !== "" &&
    turnoDeseadoId !== "" &&
    !motivoExcedido &&
    !crear.isPending;

  // Etiqueta de cada opcion: "Lun 8 jun · Mañana" o "Lun 8 jun · Mañana · Tezcu"
  // segun si es opcion propia o de un compañero.
  const etiquetaTurnoPropio = (t: TurnoRota) =>
    `${formatearFechaCorta(t.fecha)} · ${t.franja_nombre}`;
  const etiquetaTurnoOtros = (t: TurnoRota) =>
    `${formatearFechaCorta(t.fecha)} · ${t.franja_nombre} · ${t.miembro_nombre}`;

  if (cargando) {
    return <Skeleton className="h-40 w-full rounded-md" />;
  }
  if (turnosMios.length === 0) {
    return (
      <div className="rounded-md border border-dashed p-4 text-center text-xs text-muted-foreground">
        No tienes turnos para cambiar en este rango (semana actual + siguiente).
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Mi turno</Label>
        <Select value={miTurnoId} onValueChange={setMiTurnoId}>
          <SelectTrigger aria-label="Mi turno (el que cedo)">
            <SelectValue placeholder="Elige uno de tus turnos" />
          </SelectTrigger>
          <SelectContent>
            {turnosMios.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {etiquetaTurnoPropio(t)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label>Turno deseado</Label>
        <Select value={turnoDeseadoId} onValueChange={setTurnoDeseadoId}>
          <SelectTrigger aria-label="Turno deseado (el que quieres recibir)">
            <SelectValue placeholder="Elige el turno con el que quieres cambiar" />
          </SelectTrigger>
          <SelectContent>
            {turnosOtros.length === 0 ? (
              <div className="p-2 text-xs text-muted-foreground">
                No hay turnos de otros compañeros en este rango.
              </div>
            ) : (
              turnosOtros.map((t) => (
                <SelectItem key={t.id} value={t.id}>
                  {etiquetaTurnoOtros(t)}
                </SelectItem>
              ))
            )}
          </SelectContent>
        </Select>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="swap-motivo">
          Motivo <span className="font-normal text-muted-foreground">(opcional)</span>
        </Label>
        <Textarea
          id="swap-motivo"
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
          placeholder="Ej. Cita medica, evento familiar, examen…"
          rows={2}
          maxLength={500}
        />
        {motivoExcedido && (
          <div className="text-xs text-destructive">
            El motivo no puede pasar de 500 caracteres.
          </div>
        )}
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
    </div>
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
            <Badge variant="outline" className="font-normal">
              <ArrowLeftRight className="mr-1 h-3 w-3" /> Cambio
            </Badge>
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
// filtra el autocomplete del tablero de piezas (las piezas existentes no se
// tocan).

function Programas() {
  const queryClient = useQueryClient();
  const [soloActivos, setSoloActivos] = React.useState(false);
  // Ola "simplificar": filtro de búsqueda (case-insensitive) sobre nombre/descripción.
  const [busqueda, setBusqueda] = React.useState("");
  const clave = ["rota", "programas", soloActivos ? "activos" : "todos"] as const;
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) =>
      api.listarProgramasRota(soloActivos ? { activo: true } : {}, signal),
  });
  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["rota", "programas"] });
  };
  const programas = React.useMemo(() => q.data?.programas ?? [], [q.data?.programas]);
  // Filtro local (no toca la API: el backend no expone búsqueda y la lista es corta).
  const programasFiltrados = React.useMemo(() => {
    const term = busqueda.trim().toLowerCase();
    if (!term) return programas;
    return programas.filter(
      (p) =>
        p.nombre.toLowerCase().includes(term) ||
        (p.descripcion ?? "").toLowerCase().includes(term),
    );
  }, [programas, busqueda]);

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
          {/* Búsqueda inline (ola "simplificar"): filtra por nombre/descripción. */}
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por nombre o descripción…"
              className="h-9 pl-8"
              aria-label="Buscar programas"
            />
          </div>
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
          ) : programasFiltrados.length === 0 ? (
            <EstadoVacio
              icono={Search}
              titulo="Sin resultados"
              texto={`No hay programas que coincidan con «${busqueda}». Borra el filtro para verlos todos.`}
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
                  {programasFiltrados.map((p) => (
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
  // Validación inline: fin >= inicio (ola "simplificar"). Si ambos están y el orden
  // está mal, bloqueamos el submit y mostramos el mensaje pegado al campo.
  const [errorFechas, setErrorFechas] = React.useState<string | null>(null);

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
      setErrorFechas(null);
      setAbierto(false);
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function intentarCrear() {
    if (inicio && fin && fin < inicio) {
      setErrorFechas("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    setErrorFechas(null);
    crear.mutate();
  }

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
            onChange={(e) => {
              setInicio(e.target.value);
              if (errorFechas) setErrorFechas(null);
            }}
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
            onChange={(e) => {
              setFin(e.target.value);
              if (errorFechas) setErrorFechas(null);
            }}
            className="h-8 text-xs"
            aria-invalid={errorFechas ? true : undefined}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="prog-color" className="text-xs">
            Color
          </Label>
          {/* Ola "simplificar": eliminamos el input hex de texto; con el picker basta. */}
          <Input
            id="prog-color"
            type="color"
            value={color}
            onChange={(e) => setColor(e.target.value)}
            className="h-8 w-14 cursor-pointer p-1"
          />
        </div>
        {errorFechas && (
          <p className="text-xs text-destructive sm:col-span-2">{errorFechas}</p>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setAbierto(false)}>
          Cancelar
        </Button>
        <Button
          size="sm"
          onClick={intentarCrear}
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
                onClick={async () => {
                  if (
                    await confirmar({
                      mensaje: `¿Borrar el programa «${programa.nombre}»?`,
                      destructivo: true,
                      textoConfirmar: "Borrar",
                    })
                  )
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
  // Ola "simplificar": validación inline `fin >= inicio` antes de PATCH.
  const [errorFechas, setErrorFechas] = React.useState<string | null>(null);

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

  function intentarGuardar() {
    if (inicio && fin && fin < inicio) {
      setErrorFechas("La fecha de fin no puede ser anterior al inicio.");
      return;
    }
    setErrorFechas(null);
    guardar.mutate();
  }

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
                onChange={(e) => {
                  setInicio(e.target.value);
                  if (errorFechas) setErrorFechas(null);
                }}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="ep-fin">Fin</Label>
              <Input
                id="ep-fin"
                type="date"
                value={fin}
                onChange={(e) => {
                  setFin(e.target.value);
                  if (errorFechas) setErrorFechas(null);
                }}
                aria-invalid={errorFechas ? true : undefined}
              />
            </div>
          </div>
          {errorFechas && (
            <p className="text-xs text-destructive">{errorFechas}</p>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="ep-color">Color</Label>
              {/* Ola "simplificar": eliminamos el input hex de texto. */}
              <Input
                id="ep-color"
                type="color"
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="h-9 w-14 cursor-pointer p-1"
              />
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
            onClick={intentarGuardar}
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
