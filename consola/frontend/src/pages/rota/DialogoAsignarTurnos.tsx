import { useMutation } from "@tanstack/react-query";
import { CalendarPlus, Check, Loader2, Sparkles } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ImportarDocumentoParrilla } from "@/components/parrilla/ImportarDocumentoParrilla";
import { ApiError, api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { diaCorto } from "@/lib/rota-calendario";
import type { FranjaSemana, MiembroRota } from "@/types";

/**
 * Pastilla de un día (selección múltiple). El estado SELECCIONADO es inconfundible —
 * relleno sólido + check— frente al no-seleccionado —contorno y texto apagado—: con los
 * grises de plataforma (secondary ~95% vs background ~98%) un toggle sutil era invisible y
 * el usuario no veía qué días quedaban marcados.
 */
function ChipDia({
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
function aMinutos24(s: string): number | null {
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

/**
 * «Asignar turnos» del calendario de la rota: reparte la semana de un vistazo en vez de ir
 * celda por celda. Eliges PERSONA → HORARIO (de–a) → QUÉ DÍAS, y crea un turno por cada día
 * seleccionado. El usuario piensa en HORAS, no en franjas: la franja (fila del calendario) se
 * deriva sola del horario (`franjaParaHorario`). Repites el diálogo por persona. La cobertura
 * (quién cubre cada evento) sigue en Panorama; esto es CAPACIDAD.
 *
 * Va por día (no por el endpoint lote) a propósito: el lote es todo-o-nada y un solo choque
 * (sábado consecutivo o un día ya asignado) tumbaría el reparto entero. Por día es indulgente:
 * asigna lo que puede, cuenta los que ya estaban y avisa de los sábados que piden override.
 */
export function DialogoAsignarTurnos({
  abierto,
  onOpenChange,
  lunes,
  dias,
  franjas,
  cms,
  onCambio,
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
}) {
  const franjasLaborales = React.useMemo(
    () => franjas.filter((f) => !f.es_descanso),
    [franjas],
  );
  const [persona, setPersona] = React.useState("");
  // Horario del turno (de–a). El usuario teclea horas; la franja (fila) se deriva sola.
  const [inicio, setInicio] = React.useState("");
  const [fin, setFin] = React.useState("");
  const [diasSel, setDiasSel] = React.useState<Set<string>>(() => new Set());

  // Al abrir (o al cambiar de semana) arranca sin días: el usuario ELIGE los que quiere
  // (clic = añade). Los atajos «L–V» / «Toda la semana» cubren los casos masivos de un toque.
  React.useEffect(() => {
    if (abierto) setDiasSel(new Set());
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
      const f = franjaParaHorario(inicio, fin, franjasLaborales);
      const resumen = f
        ? await asignarDiasTurno(
            lunes,
            persona,
            f.id,
            fechas,
            horasAMedida ? inicio : "",
            horasAMedida ? fin : "",
          )
        : { creados: 0, yaEstaba: 0, sabados: 0, fallos: 0 };
      return {
        ...resumen,
        persona_nombre: cms.find((m) => m.id === persona)?.nombre ?? "",
        horario: `${inicio}–${fin}`,
      };
    },
    onSuccess: ({ creados, yaEstaba, sabados, fallos, persona_nombre, horario }) => {
      onCambio();
      const partes: string[] = [];
      if (creados)
        partes.push(
          `${creados} día${creados === 1 ? "" : "s"} a ${persona_nombre} (${horario})`,
        );
      if (yaEstaba) partes.push(`${yaEstaba} ya estaba${yaEstaba === 1 ? "" : "n"}`);
      if (sabados)
        partes.push(
          `${sabados} sábado${sabados === 1 ? "" : "s"} pide override (hazlo desde la celda)`,
        );
      if (fallos) partes.push(`${fallos} con error`);
      const msg = partes.join(" · ") || "Sin cambios.";
      if (creados > 0) toast.success(msg);
      else toast.error(msg);
      onOpenChange(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const incompleto =
    !persona || diasSel.size === 0 || !horasValidas || franjasLaborales.length === 0;

  return (
    <Dialog open={abierto} onOpenChange={onOpenChange}>
      <DialogContent className="gap-3">
        <DialogHeader>
          <DialogTitle>Asignar turnos</DialogTitle>
        </DialogHeader>

        {/* AUTOMÁTICO: subir un documento (parrilla/Excel/foto) → Keni propone los turnos
            (y eventos), se revisan y se aplican. Antes era un botón suelto en la cabecera del
            calendario; ahora vive aquí como la vía RÁPIDA de «Asignar turnos». */}
        <div className="space-y-2 rounded-lg border border-dashed border-border p-3">
          <div className="flex items-center gap-1.5 text-sm font-medium">
            <Sparkles className="h-4 w-4 text-primary" />
            Automático: de un documento
          </div>
          <p className="text-xs text-muted-foreground">
            Sube una parrilla, un Excel o una foto: Keni propone los turnos y los revisas antes de aplicar.
          </p>
          <ImportarDocumentoParrilla
            onAplicado={() => {
              onCambio();
              onOpenChange(false);
            }}
          />
        </div>

        <div className="relative py-0.5 text-center text-xs text-muted-foreground">
          — o a mano —
        </div>

        <p className="text-xs text-muted-foreground">
          Reparte la semana a mano: elige quién trabaja, su horario y qué días. Repítelo por
          persona. Esto es la CAPACIDAD; quién cubre cada evento se decide en Panorama.
        </p>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Persona</Label>
            <Select value={persona} onValueChange={setPersona}>
              <SelectTrigger>
                <SelectValue placeholder="Elige…" />
              </SelectTrigger>
              <SelectContent>
                {cms.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
              <ChipDia key={fecha} activo={diasSel.has(fecha)} onClick={() => toggleDia(fecha)}>
                <span className="capitalize">{diaCorto(fecha)}</span> {fecha.slice(8, 10)}
              </ChipDia>
            ))}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={asignar.isPending}>
            Cancelar
          </Button>
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
              : diasSel.size > 0
                ? `Asignar ${diasSel.size} día${diasSel.size === 1 ? "" : "s"}`
                : "Asignar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
