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
  const m = /^(\d{1,2}):(\d{2})$/.exec(s.trim());
  if (!m) return false;
  const h = Number(m[1]);
  const mm = Number(m[2]);
  if (h === 24) return mm === 0;
  return h >= 0 && h <= 23 && mm >= 0 && mm <= 59;
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
 * celda por celda. Eliges PERSONA → FRANJA (Mañana/Tarde…) → QUÉ DÍAS, y crea un turno por
 * cada día seleccionado. Es el «uno trabaja de mañanas, otro de tardes»: repites el diálogo
 * por persona. La cobertura (quién cubre cada evento) sigue en Panorama; esto es CAPACIDAD.
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
  const [franjaId, setFranjaId] = React.useState("");
  // Horario del turno: arranca con el de la franja (fijo) y es editable (a medida).
  const [inicio, setInicio] = React.useState("");
  const [fin, setFin] = React.useState("");
  const [diasSel, setDiasSel] = React.useState<Set<string>>(() => new Set());

  // Al abrir (o al cambiar de semana) arranca sin días: el usuario ELIGE los que quiere
  // (clic = añade). Los atajos «L–V» / «Toda la semana» cubren los casos masivos de un toque.
  React.useEffect(() => {
    if (abierto) setDiasSel(new Set());
  }, [abierto, dias]);

  const toggleDia = (fecha: string) =>
    setDiasSel((prev) => {
      const n = new Set(prev);
      if (n.has(fecha)) n.delete(fecha);
      else n.add(fecha);
      return n;
    });

  const franjaSel = franjasLaborales.find((f) => f.id === franjaId);

  // Al elegir franja, el horario se prefija con el SUYO (fijo); el usuario lo edita si esa
  // persona trabaja otras horas (a medida). Así «fijo o no» es un solo control, sin jerga.
  const elegirFranja = (id: string) => {
    setFranjaId(id);
    const f = franjasLaborales.find((x) => x.id === id);
    if (f) {
      setInicio(f.inicio);
      setFin(f.fin);
    }
  };

  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);
  // Hay override si el horario difiere del de la franja; si coincide, el turno hereda (no se
  // congela, así editar la franja luego propaga). Sin franja elegida no aplica.
  const horasAMedida =
    !!franjaSel && horasValidas && (inicio !== franjaSel.inicio || fin !== franjaSel.fin);

  const asignar = useMutation({
    mutationFn: async () => {
      const fechas = dias.filter((d) => diasSel.has(d));
      const resumen = await asignarDiasTurno(
        lunes,
        persona,
        franjaId,
        fechas,
        horasAMedida ? inicio : "",
        horasAMedida ? fin : "",
      );
      return {
        ...resumen,
        persona_nombre: cms.find((m) => m.id === persona)?.nombre ?? "",
        franja_nombre: franjasLaborales.find((f) => f.id === franjaId)?.nombre ?? "",
      };
    },
    onSuccess: ({ creados, yaEstaba, sabados, fallos, persona_nombre, franja_nombre }) => {
      onCambio();
      const partes: string[] = [];
      if (creados)
        partes.push(
          `${creados} día${creados === 1 ? "" : "s"} a ${persona_nombre} en ${franja_nombre}`,
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

  const incompleto = !persona || !franjaId || diasSel.size === 0 || !horasValidas;

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
          Reparte la semana a mano: elige quién trabaja, en qué franja y qué días. Repítelo por
          persona (p. ej. uno a Mañana, otro a Tarde). Esto es la CAPACIDAD; quién cubre cada
          evento se decide en Panorama.
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
          <div className="space-y-1.5">
            <Label>Franja</Label>
            <Select value={franjaId} onValueChange={elegirFranja}>
              <SelectTrigger>
                <SelectValue placeholder="Elige…" />
              </SelectTrigger>
              <SelectContent>
                {franjasLaborales.map((f) => (
                  <SelectItem key={f.id} value={f.id}>
                    {f.nombre} ({f.inicio}–{f.fin})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Horario del turno: prefijado con el de la franja (FIJO) y editable (A MEDIDA).
            Si lo cambias, esos días llevan tus horas; si lo dejas, heredan las de la franja. */}
        {franjaId && (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>Horario</Label>
              {horasAMedida && franjaSel && (
                <button
                  type="button"
                  className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                  onClick={() => {
                    setInicio(franjaSel.inicio);
                    setFin(franjaSel.fin);
                  }}
                >
                  Volver al de la franja
                </button>
              )}
            </div>
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
              <span className="text-xs text-muted-foreground">
                {horasAMedida ? "a medida" : "fijo (de la franja)"}
              </span>
            </div>
            {!horasValidas && (
              <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
            )}
          </div>
        )}

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
