import { useMutation } from "@tanstack/react-query";
import { CalendarPlus, Check, Loader2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { diaCorto } from "@/lib/rota-calendario";
import type { FranjaSemana, MiembroRota } from "@/types";

/**
 * Pastilla de selección múltiple (un día o una persona). El estado SELECCIONADO es inconfundible
 * —relleno sólido + check— frente al no-seleccionado —contorno y texto apagado—: con los grises
 * de plataforma (secondary ~95% vs background ~98%) un toggle sutil era invisible y el usuario no
 * veía qué quedaba marcado. Personas y días usan la misma pastilla para que el diálogo sea
 * coherente: ambos son multi-selección por toque.
 */
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
    <button
      type="button"
      role="checkbox"
      aria-checked={activo}
      onClick={onClick}
      className={cn(
        "inline-flex h-8 items-center gap-1 rounded-md border px-2.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        activo
          ? "border-foreground bg-foreground font-medium text-background"
          : "border-border bg-background text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {activo && <Check className="h-3.5 w-3.5" />}
      {children}
    </button>
  );
}

/**
 * ¿`s` es una hora "HH:MM" válida? Acepta 00:00–23:59 y «24:00» (fin exclusivo), igual que
 * el backend (`_hhmm_valido`): una franja puede acabar en «24:00», así que el prefijado debe
 * darla por buena. Permite cruce de medianoche (no exige inicio<fin).
 */
function esHoraValida(s: string): boolean {
  return aMinutos24(s) !== null;
}

/** "HH:MM" → minutos desde 00:00 (00:00–23:59), con «24:00» = 1440. `null` si no parsea. */
export function aMinutos24(s: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return null;
  const h = Number(m[1]);
  const mm = Number(m[2]);
  if (h === 24) return mm === 0 ? 1440 : null;
  if (h < 0 || h > 23 || mm < 0 || mm > 59) return null;
  return h * 60 + mm;
}

/** Minutos en que dos rangos "HH:MM" se solapan (soporta cruce de medianoche). */
function solapeMinutos(aIni: string, aFin: string, bIni: string, bFin: string): number {
  const tramos = (ini: string, fin: string): [number, number][] => {
    const i = aMinutos24(ini);
    const f = aMinutos24(fin);
    if (i === null || f === null || i === f) return [];
    return i < f ? [[i, f]] : [[i, 1440], [0, f]];
  };
  let total = 0;
  for (const [a1, a2] of tramos(aIni, aFin))
    for (const [b1, b2] of tramos(bIni, bFin))
      total += Math.max(0, Math.min(a2, b2) - Math.max(a1, b1));
  return total;
}

/**
 * Franja (fila del calendario) donde cae un horario tecleado: la de mayor solape en horas; si
 * ninguna solapa, la de inicio más cercano; en último caso, la primera. Así el usuario NO
 * elige franja a mano —piensa en horas, no en franjas—: el turno se coloca solo por su hora.
 */
function franjaParaHorario(
  inicio: string,
  fin: string,
  franjas: FranjaSemana[],
): FranjaSemana | undefined {
  if (franjas.length === 0) return undefined;
  const ini = aMinutos24(inicio);
  let mejor = franjas[0]!;
  let mejorSolape = -1;
  let mejorDist = Number.POSITIVE_INFINITY;
  for (const f of franjas) {
    const solape = solapeMinutos(inicio, fin, f.inicio, f.fin);
    const fIni = aMinutos24(f.inicio);
    const dist =
      ini !== null && fIni !== null ? Math.abs(ini - fIni) : Number.POSITIVE_INFINITY;
    if (solape > mejorSolape || (solape === mejorSolape && dist < mejorDist)) {
      mejor = f;
      mejorSolape = solape;
      mejorDist = dist;
    }
  }
  return mejor;
}

export interface ResumenAsignacion {
  creados: number;
  /** 409 sin `requiere_override`: ya había un turno de esa persona en esa fecha/franja. */
  yaEstaba: number;
  /** 409 con `requiere_override`: regla de sábado consecutivo / ausencia (no se fuerza aquí). */
  sabados: number;
  fallos: number;
}

/**
 * Crea un turno por cada `fecha` (uno a uno, indulgente: un día que falla NO tumba el resto).
 * Cuenta el resultado. Separado del componente para testearlo SIN tocar los Select de Radix
 * (que dentro de un Dialog se cuelgan en jsdom).
 */
export async function asignarDiasTurno(
  lunes: string,
  miembroId: string,
  franjaId: string,
  fechas: string[],
  /** Horario a medida ("HH:MM"); vacío = el turno hereda las horas de la franja. */
  inicio = "",
  fin = "",
): Promise<ResumenAsignacion> {
  const r: ResumenAsignacion = { creados: 0, yaEstaba: 0, sabados: 0, fallos: 0 };
  const horas = inicio && fin ? { inicio, fin } : {};
  for (const fecha of fechas) {
    try {
      await api.crearTurno({ lunes, fecha, miembro_id: miembroId, franja_id: franjaId, ...horas });
      r.creados++;
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        if (e.cuerpo?.requiere_override) r.sabados++;
        else r.yaEstaba++;
      } else {
        r.fallos++;
      }
    }
  }
  return r;
}

export interface ResumenReparto extends ResumenAsignacion {
  /** Personas a las que se les creó al menos un turno (para el toast «… para N personas»). */
  personasConCreados: number;
}

/**
 * Aplica el MISMO horario+días a VARIAS personas, una por una, agregando el resultado. Mantiene
 * la indulgencia de `asignarDiasTurno` a dos niveles: ni un día que choca tumba a su persona, ni
 * una persona con todo ocupado tumba al resto. El reparto por lote (todo-o-nada) se descarta a
 * propósito: un solo choque perdería todo lo demás.
 */
export async function asignarPersonasDiasTurno(
  lunes: string,
  miembroIds: string[],
  franjaId: string,
  fechas: string[],
  inicio = "",
  fin = "",
): Promise<ResumenReparto> {
  const r: ResumenReparto = {
    creados: 0,
    yaEstaba: 0,
    sabados: 0,
    fallos: 0,
    personasConCreados: 0,
  };
  for (const miembroId of miembroIds) {
    const p = await asignarDiasTurno(lunes, miembroId, franjaId, fechas, inicio, fin);
    r.creados += p.creados;
    r.yaEstaba += p.yaEstaba;
    r.sabados += p.sabados;
    r.fallos += p.fallos;
    if (p.creados > 0) r.personasConCreados++;
  }
  return r;
}

/**
 * «Asignar turnos» del calendario de la rota: reparte la semana de un vistazo en vez de ir
 * celda por celda. Eliges PERSONAS → HORARIO (de–a) → QUÉ DÍAS, y crea un turno por cada par
 * persona×día. El usuario piensa en HORAS, no en franjas: la franja (fila del calendario) se
 * deriva sola del horario (`franjaParaHorario`). La cobertura (quién cubre cada evento) sigue
 * en Panorama; esto es CAPACIDAD.
 *
 * Va persona-a-persona y día-a-día (no por el endpoint lote) a propósito: el lote es todo-o-nada
 * y un solo choque (sábado consecutivo o un día ya asignado) tumbaría el reparto entero. Así es
 * indulgente: asigna lo que puede, cuenta los que ya estaban y avisa de los sábados que piden
 * override, sin que un choque arrastre al resto de personas ni de días.
 */
export function DialogoAsignarTurnos({
  abierto,
  onOpenChange,
  lunes,
  dias,
  franjas,
  cms,
  onCambio,
  incrustado = false,
}: {
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
  /** Lunes ISO de la semana en vista. */
  lunes: string;
  /** Las 7 fechas ISO (lun→dom) de la semana. */
  dias: string[];
  /** Franjas vivas de la semana (se ofrecen las NO-descanso: son turnos de trabajo). */
  franjas: FranjaSemana[];
  /** CMs asignables de la marca activa. */
  cms: MiembroRota[];
  /** Refresca la rejilla tras asignar. */
  onCambio: () => void;
  /** Incrustado: en vez de un modal centrado, se pinta como columna lateral junto a la rejilla
   *  (Gestión), para repartir mirando el calendario en vivo. Si está cerrado no renderiza nada. */
  incrustado?: boolean;
}) {
  const franjasLaborales = React.useMemo(
    () => franjas.filter((f) => !f.es_descanso),
    [franjas],
  );
  const [personasSel, setPersonasSel] = React.useState<Set<string>>(() => new Set());
  // Horario del turno (de–a). El usuario teclea horas; la franja (fila) se deriva sola.
  const [inicio, setInicio] = React.useState("");
  const [fin, setFin] = React.useState("");
  const [diasSel, setDiasSel] = React.useState<Set<string>>(() => new Set());

  // Al abrir (o al cambiar de semana) arranca sin personas ni días: el usuario ELIGE quién y
  // qué (clic = añade). Los atajos «L–V» / «Toda la semana» cubren los casos masivos de un toque.
  React.useEffect(() => {
    if (abierto) {
      setPersonasSel(new Set());
      setDiasSel(new Set());
    }
  }, [abierto, dias]);

  // Al abrir, prefija el horario con el de la primera franja laboral (p. ej. 08:00–16:00) sin
  // pisar lo que el usuario ya haya tecleado: un punto de partida cómodo, editable.
  React.useEffect(() => {
    if (!abierto) return;
    const f0 = franjasLaborales[0];
    if (!f0) return;
    setInicio((prev) => prev || f0.inicio);
    setFin((prev) => prev || f0.fin);
  }, [abierto, franjasLaborales]);

  const toggleDia = (fecha: string) =>
    setDiasSel((prev) => {
      const n = new Set(prev);
      if (n.has(fecha)) n.delete(fecha);
      else n.add(fecha);
      return n;
    });

  const togglePersona = (id: string) =>
    setPersonasSel((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);
  // La franja (fila del calendario) se deriva del horario; el turno lleva horas A MEDIDA solo
  // si difieren de las de esa franja (si coinciden, hereda, así editar la franja luego propaga).
  const franjaDestino = horasValidas
    ? franjaParaHorario(inicio, fin, franjasLaborales)
    : undefined;
  const horasAMedida =
    !!franjaDestino && (inicio !== franjaDestino.inicio || fin !== franjaDestino.fin);

  const asignar = useMutation({
    mutationFn: async () => {
      const fechas = dias.filter((d) => diasSel.has(d));
      const miembroIds = cms.filter((m) => personasSel.has(m.id)).map((m) => m.id);
      const f = franjaParaHorario(inicio, fin, franjasLaborales);
      const resumen = f
        ? await asignarPersonasDiasTurno(
            lunes,
            miembroIds,
            f.id,
            fechas,
            horasAMedida ? inicio : "",
            horasAMedida ? fin : "",
          )
        : { creados: 0, yaEstaba: 0, sabados: 0, fallos: 0, personasConCreados: 0 };
      return { ...resumen, horario: `${inicio}–${fin}` };
    },
    onSuccess: ({ creados, yaEstaba, sabados, fallos, personasConCreados, horario }) => {
      onCambio();
      const partes: string[] = [];
      if (creados) {
        const personasTxt =
          personasConCreados === 1 ? "1 persona" : `${personasConCreados} personas`;
        partes.push(
          `${creados} turno${creados === 1 ? "" : "s"} para ${personasTxt} (${horario})`,
        );
      }
      if (yaEstaba) partes.push(`${yaEstaba} ya estaba${yaEstaba === 1 ? "" : "n"}`);
      if (sabados)
        partes.push(
          `${sabados} sábado${sabados === 1 ? "" : "s"} pide override (hazlo desde la celda)`,
        );
      if (fallos) partes.push(`${fallos} con error`);
      const msg = partes.join(" · ") || "Sin cambios.";
      // Reparto EN LOTE: el panel NO se cierra al asignar, para encadenar tandas sin reabrir. Tras
      // una tanda con turnos creados deja la selección limpia (personas + días) y conserva el horario
      // —que suele repetirse— como punto de partida de la siguiente; si no se creó nada (todo ya
      // estaba o error), mantiene la selección para ajustarla y reintentar. Cerrar es manual (✕/Cancelar).
      if (creados > 0) {
        toast.success(msg);
        setPersonasSel(new Set());
        setDiasSel(new Set());
      } else {
        toast.error(msg);
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const incompleto =
    personasSel.size === 0 ||
    diasSel.size === 0 ||
    !horasValidas ||
    franjasLaborales.length === 0;
  // Turnos que se intentarán crear: el mismo horario+días aplicado a cada persona marcada.
  const totalTurnos = personasSel.size * diasSel.size;
  // Por qué el botón está deshabilitado: la PRIMERA pieza que falta. Un botón gris a secas no dice
  // qué hace falta y deja al usuario atascado («no me deja seguir»); esta pista lo desbloquea.
  const pistaIncompleta =
    franjasLaborales.length === 0
      ? "Esta semana no tiene franjas laborales."
      : personasSel.size === 0
        ? "Elige al menos una persona."
        : diasSel.size === 0
          ? "Elige al menos un día."
          : !horasValidas
            ? "Escribe un horario válido (HH:MM)."
            : null;

  // Cuerpo del formulario MANUAL (personas/horario/días), compartido por el modal y la columna
  // lateral (incrustado). El reparto automático «de un documento» vive aparte, al final del panel
  // (lo monta el contenedor de Gestión), por ser la última opción.
  const camposManual = (
    <>
        {/* Personas en pastillas multi-selección (mismo patrón que los Días): marca a quien
            trabaja ese horario y el reparto aplica el MISMO turno a todas. */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="flex items-baseline gap-1.5">
              Personas
              {personasSel.size > 0 && (
                <span className="text-xs font-normal text-muted-foreground">
                  {personasSel.size} elegida{personasSel.size === 1 ? "" : "s"}
                </span>
              )}
            </Label>
            <div className="flex items-center gap-1.5 text-xs">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setPersonasSel(new Set(cms.map((m) => m.id)))}
              >
                Todas
              </button>
              <span className="text-muted-foreground/40">·</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setPersonasSel(new Set())}
              >
                Ninguna
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {cms.map((m) => (
              <ChipToggle
                key={m.id}
                activo={personasSel.has(m.id)}
                onClick={() => togglePersona(m.id)}
              >
                {m.nombre}
              </ChipToggle>
            ))}
          </div>
        </div>

        {/* Horario en horas (de–a). Es lo único que define el turno; la franja —la fila del
            calendario— se deduce sola del horario, sin que el usuario la elija. */}
        <div className="space-y-1.5">
          <Label>Horario</Label>
          <div className="flex items-center gap-2">
            <Input
              value={inicio}
              onChange={(e) => setInicio(e.target.value)}
              placeholder="08:00"
              className="w-24 tabular-nums"
              aria-label="Hora de inicio"
            />
            <span className="text-muted-foreground">–</span>
            <Input
              value={fin}
              onChange={(e) => setFin(e.target.value)}
              placeholder="16:00"
              className="w-24 tabular-nums"
              aria-label="Hora de fin"
            />
          </div>
          {!horasValidas && (inicio || fin) && (
            <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label className="flex items-baseline gap-1.5">
              Días
              {diasSel.size > 0 && (
                <span className="text-xs font-normal text-muted-foreground">
                  {diasSel.size} elegido{diasSel.size === 1 ? "" : "s"}
                </span>
              )}
            </Label>
            <div className="flex items-center gap-1.5 text-xs">
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setDiasSel(new Set(dias.slice(0, 5)))}
              >
                L–V
              </button>
              <span className="text-muted-foreground/40">·</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setDiasSel(new Set(dias))}
              >
                Toda la semana
              </button>
              <span className="text-muted-foreground/40">·</span>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setDiasSel(new Set())}
              >
                Ninguno
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {dias.map((fecha) => (
              <ChipToggle key={fecha} activo={diasSel.has(fecha)} onClick={() => toggleDia(fecha)}>
                <span className="capitalize">{diaCorto(fecha)}</span> {fecha.slice(8, 10)}
              </ChipToggle>
            ))}
          </div>
        </div>

    </>
  );

  const botonAsignar = (
    <Button
      variant="secondary"
      onClick={() => asignar.mutate()}
      disabled={incompleto || asignar.isPending}
    >
      {asignar.isPending ? (
        <Loader2 className="mr-1 h-4 w-4 animate-spin" />
      ) : (
        <CalendarPlus className="mr-1 h-4 w-4" />
      )}
      {asignar.isPending
        ? "Asignando…"
        : totalTurnos > 0
          ? `Asignar ${totalTurnos} turno${totalTurnos === 1 ? "" : "s"}`
          : "Asignar"}
    </Button>
  );

  // Columna lateral (Gestión): tarjeta del reparto MANUAL. La compone el contenedor de Gestión
  // junto a «Cambios y ausencias» y, al final, el import automático. Cerrada no pinta nada; el ✕
  // de la cabecera oculta el panel.
  if (incrustado) {
    if (!abierto) return null;
    return (
      <div className="flex flex-col gap-3 rounded-lg border bg-card p-4 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Asignar turnos</h2>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => onOpenChange(false)}
            aria-label="Cerrar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {camposManual}
        <div className="flex items-center justify-between gap-2 pt-1">
          {pistaIncompleta ? (
            <span className="text-xs text-muted-foreground">{pistaIncompleta}</span>
          ) : (
            <span aria-hidden />
          )}
          {botonAsignar}
        </div>
      </div>
    );
  }

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent className="gap-3">
        <DialogHeader>
          <DialogTitle>Asignar turnos</DialogTitle>
        </DialogHeader>
        {camposManual}
        <DialogFooter>
          {pistaIncompleta && (
            <span className="mr-auto self-center text-xs text-muted-foreground">
              {pistaIncompleta}
            </span>
          )}
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={asignar.isPending}>
            Cancelar
          </Button>
          {botonAsignar}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
