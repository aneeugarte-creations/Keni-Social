// Constantes, helpers y componentes pequeños COMPARTIDOS por las vistas de la rota
// (calendario / mis turnos / cambios y ausencias).
import { useMutation } from "@tanstack/react-query";
import {
  BellRing,
  CalendarDays,
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
  Plane,
  ShieldCheck,
  User,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Tooltip } from "@/components/ui/tooltip";
import {
  MenuContextual,
  type EntradaMenuContextual,
} from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, mensajeError } from "@/lib/api";
import { ZONA_CDMX } from "@/lib/fecha";
import {
  COBERTURA,
  formatearRango,
  lunesSiguiente,
} from "@/lib/rota-calendario";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  FranjaTurno,
  MiembroRota,
  PrioridadEvento,
  SwapTurno,
  TipoAusencia,
  TipoCoberturaEvento,
} from "@/types";


/**
 * Nº de cambios de turno que requieren la ACCIÓN del usuario actual (alimenta el badge
 * de la pestaña «Cambios y ausencias»): los que espera responder como destinatario
 * (`propuesto` dirigido a mí) y, si es admin, los que esperan su aprobación (`aceptado`).
 * Las ausencias NO cuentan: no tienen estado de aprobación, son un registro directo.
 */
export function contarSwapsPendientes(
  swaps: SwapTurno[],
  miId: string,
  esAdmin: boolean,
): number {
  return swaps.filter(
    (s) =>
      (s.estado === "propuesto" && s.destinatario_id === miId) ||
      (esAdmin && s.estado === "aceptado"),
  ).length;
}


/**
 * Filtra el equipo devuelto por `/api/rota/equipo` a los miembros que cubren la marca
 * activa del workspace (el switch global de la barra superior). La rota de turnos es
 * multi-marca: cada marca ve sus eventos (`rota_eventos.marca`) y a los miembros que la
 * cubren; "Todas" (`marcaActiva === null`, admin) agrega todo el equipo. Si la respuesta
 * NO trae `marcas` (backend antiguo), no se filtra (degradación segura).
 */
export function filtrarEquipoPorMarca(
  equipo: MiembroRota[],
  marcaActiva: string | null,
): MiembroRota[] {
  if (marcaActiva === null) return equipo; // "Todas": agregado, sin filtrar por marca.
  const algunoTraeMarcas = equipo.some((m) => Array.isArray(m.marcas));
  if (!algunoTraeMarcas) return equipo;
  return equipo.filter((m) => (m.marcas ?? []).includes(marcaActiva));
}

// Etiquetas legibles de cada franja del turno de trabajo.
export const ETIQUETA_FRANJA: Record<FranjaTurno, string> = {
  matutino: "Mañana",
  vespertino: "Tarde",
  descanso: "Descanso",
};

// `COBERTURA` (presentación por tipo de cobertura) y `COLOR_PRIORIDAD` viven en
// `@/lib/rota-calendario` como única fuente de verdad (los reusa la previsualización
// de import para verse idéntica al calendario real).

export const TIPOS_COBERTURA: { valor: TipoCoberturaEvento; etiqueta: string }[] = [
  { valor: "transmision", etiqueta: "Transmisión en vivo" },
  { valor: "imagenes", etiqueta: "Solo imágenes" },
  { valor: "no_cubrir", etiqueta: "No cubrir" },
];

export const PRIORIDADES: { valor: PrioridadEvento; etiqueta: string }[] = [
  { valor: "alta", etiqueta: "Alta" },
  { valor: "media", etiqueta: "Media" },
  { valor: "baja", etiqueta: "Baja" },
];

export const TIPOS_AUSENCIA: { valor: TipoAusencia; etiqueta: string }[] = [
  { valor: "vacaciones", etiqueta: "Vacaciones" },
  { valor: "descanso", etiqueta: "Descanso" },
  { valor: "baja", etiqueta: "Baja" },
  { valor: "otro", etiqueta: "Otro" },
];

// Presentación de cada tipo de ausencia en la banda del calendario: icono + clases.
// Colores suaves consistentes con el chip-style usado por la cobertura (no robar atención).
export const PRESENTACION_AUSENCIA: Record<
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

export function formatearFechaCorta(s: string): string {
  if (!s) return "";
  // Convención de lib/fecha.ts: anclar el día a mediodía UTC y formatear en CDMX.
  const d = new Date(`${s}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("es-MX", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: ZONA_CDMX,
  });
}

// --- Navegador de semana ---------------------------------------------------

export function NavegadorSemana({
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
export function LeyendaCobertura() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      {(Object.keys(COBERTURA) as TipoCoberturaEvento[]).map((tc) => (
        <span key={tc} className="inline-flex items-center gap-1.5">
          <span className={`h-2.5 w-2.5 rounded-full ${COBERTURA[tc].punto}`} />
          {COBERTURA[tc].etiqueta}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <BellRing className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" /> Reprogramado
      </span>
      <span className="inline-flex items-center gap-1.5">
        <ShieldCheck className="h-3.5 w-3.5 text-sky-600 dark:text-sky-400" /> Coordinador
        por celda
      </span>
    </div>
  );
}

/**
 * Icono "?" con popover que muestra la leyenda completa bajo demanda.
 *
 * Popover autocontenido (mismo patron que IndicadorEstado): se cierra al pulsar fuera
 * o con Escape.
 */
export function AyudaLeyenda() {
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
export function MenuMasAcciones({
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
      etiqueta: copiarPendiente ? "Copiando…" : "Copiar anterior",
      icono: Copy,
      onClick: onCopiarAnterior,
      deshabilitado: copiarPendiente || semanaAprobada,
    });
    items.push({
      etiqueta: "Configurar franjas",
      icono: CalendarDays,
      onClick: onAbrirFranjasSemana,
    });
    items.push({
      etiqueta: "Plantilla de franjas",
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
 * (Borrador = no visible para el equipo; Publicada = el equipo ya la ve).
 */
export function BadgeEstadoSemana({ aprobada, hayTurnos }: { aprobada: boolean; hayTurnos: boolean }) {
  if (aprobada) {
    return (
      <Tooltip label="Visible para el equipo">
        <Badge variant="ok" className="font-normal">
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" /> Publicada
        </Badge>
      </Tooltip>
    );
  }
  if (!hayTurnos) return null;
  return (
    <Tooltip label="Por aprobar y publicar">
      <Badge variant="secondary" className="font-normal">
        Borrador
      </Badge>
    </Tooltip>
  );
}

/** Botón "marcar avisado": limpia el flag `cambiado` de un evento (PATCH cambiado:false). */
export function BotonMarcarAvisado({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const marcar = useMutation({
    mutationFn: () => api.actualizarEventoRota(evento.id, { cambiado: false }),
    onSuccess: () => {
      toast.success("Cambio marcado como avisado.");
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
export function ChipAusenciaDia({ ausencia }: { ausencia: AusenciaRota }) {
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
export function MasAusencias({ ausencias }: { ausencias: AusenciaRota[] }) {
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
export function ausenciaTocaDia(a: AusenciaRota, fecha: string): boolean {
  return a.desde <= fecha && fecha <= a.hasta;
}

/**
 * Convierte "HH:MM" a minutos desde 00:00. Devuelve `null` si no parsea.
 */
export function horaAMinutos(s: string): number | null {
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
export function horaEnRangoFranja(hora: string, inicio: string, fin: string): boolean {
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
 * ¿Dos franjas comparten algún minuto del día? Sirve para AVISAR de doble-asignación
 * (la misma persona en dos franjas que se solapan el mismo día). El modelo "franjas por
 * semana" permite solapes, así que esto es una posibilidad real, no un imposible.
 *
 * Soporta franjas que cruzan medianoche (`fin <= inicio`) descomponiéndolas en intervalos
 * sobre `[0, 1440)`. Una franja degenerada (`inicio === fin`, p. ej. Descanso "00:00"–
 * "00:00") no contiene minutos y no solapa con nada.
 */
export function franjasSolapan(
  a: { inicio: string; fin: string },
  b: { inicio: string; fin: string },
): boolean {
  const intervalos = (f: { inicio: string; fin: string }): [number, number][] => {
    const ini = horaAMinutos(f.inicio);
    const fin = horaAMinutos(f.fin);
    if (ini === null || fin === null || ini === fin) return [];
    if (ini < fin) return [[ini, fin]];
    return [
      [ini, 1440],
      [0, fin],
    ]; // cruza medianoche
  };
  const ia = intervalos(a);
  const ib = intervalos(b);
  return ia.some(([a1, a2]) => ib.some(([b1, b2]) => a1 < b2 && b1 < a2));
}

/**
 * Devuelve el `id` de la franja de `semana.franjas` que contiene la hora del evento.
 * Para eventos sin coverage (no podemos leer `cobertura[].franja_id`): probamos las
 * franjas NO descanso por `orden`; si ninguna contiene, caemos en la franja de descanso
 * (o la primera por orden si tampoco hay). `franjas` debe venir ya ordenada por orden.
 */
export function franjaIdParaHoraEvento(
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
export const BANDAS_FRANJA_LABORAL: { banda: string; fondo: string }[] = [
  { banda: "border-l-amber-400", fondo: "bg-amber-50/30 dark:bg-amber-950/10" },
  { banda: "border-l-sky-400", fondo: "bg-sky-50/30 dark:bg-sky-950/10" },
  { banda: "border-l-violet-400", fondo: "bg-violet-50/30 dark:bg-violet-950/10" },
  { banda: "border-l-teal-400", fondo: "bg-teal-50/30 dark:bg-teal-950/10" },
];

export function presentacionFranja(franja: FranjaSemana, indiceLaboral: number): {
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

/** Una persona que COGIÓ un evento (titularidad real). La misma noción que el Panorama:
 * sale de la tarea de cobertura (clase='tarea' con `evento_id`), no de quién está de turno. */
export interface CubridorEvento {
  /** `responsable_id` del claim (la persona que cogió el evento). */
  id: string;
  nombre: string;
}

export interface ItemEventoCalendario {
  evento: EventoRota;
  /** Quién COGIÓ el evento (titularidad real, coherente con el Panorama). Vacío = «Por cubrir». */
  cubridores: CubridorEvento[];
}

/**
 * Conflicto detectado al considerar asignar a una persona a una (fecha, franja). Es un
 * AVISO no bloqueante en el punto de decisión (el dropdown "+ Añadir persona"): el admin
 * puede forzar igualmente. Lo calcula el Calendario (tiene turnos + ausencias de la semana)
 * y lo consumen las celdas.
 */
export interface ConflictoCandidato {
  /** Ausencia que cubre ese día (vacaciones/baja/…), si la hay. */
  ausencia?: AusenciaRota;
  /** `true` si ya tiene OTRO turno ese día en una franja que solapa en horas. */
  solapa: boolean;
}

/**
 * Calendario fusionado (día × franja × persona): la única vista de la rota.
 * Las filas son las franjas vivas de la semana (modelo "franjas por semana", incluyendo
 * la franja de descanso), las columnas son los 7 días. Cada celda contiene un recuadro
 * por persona que trabaja esa franja ese día — con sus eventos cubiertos como chips
 * dentro — más, opcionalmente, un recuadro "Sin cubrir" con los eventos sin coverage.
 */
// --- Helper compartido: chip toggle ----------------------------------------
//
// `ChipToggle` lo reusan los filtros de la pestaña Cambios y ausencias.

/**
 * Botón toggle de chip (single/multi-select). Reutiliza `Button` con dos variantes.
 * Activo = gris de plataforma (`secondary`), inactivo = `outline`: la misma estetica
 * neutra del Calendario (sin negro), consistente con los badges "Borrador"/etc.
 */
export function ChipToggle({
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
      variant={activo ? "secondary" : "outline"}
      className="h-7 px-2.5 text-xs"
      onClick={onClick}
      aria-pressed={activo}
    >
      {children}
    </Button>
  );
}

