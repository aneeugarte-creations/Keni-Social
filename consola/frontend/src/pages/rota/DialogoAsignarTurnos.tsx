import { useMutation } from "@tanstack/react-query";
import { CalendarPlus, Loader2, Sparkles } from "lucide-react";
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
import { diaCorto } from "@/lib/rota-calendario";
import type { FranjaSemana, MiembroRota } from "@/types";

import { ChipToggle } from "./comun";

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
): Promise<ResumenAsignacion> {
  const r: ResumenAsignacion = { creados: 0, yaEstaba: 0, sabados: 0, fallos: 0 };
  for (const fecha of fechas) {
    try {
      await api.crearTurno({ lunes, fecha, miembro_id: miembroId, franja_id: franjaId });
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
  const [diasSel, setDiasSel] = React.useState<Set<string>>(() => new Set(dias));

  // Al abrir (o al cambiar de semana) parte de «toda la semana» seleccionada.
  React.useEffect(() => {
    if (abierto) setDiasSel(new Set(dias));
  }, [abierto, dias]);

  const toggleDia = (fecha: string) =>
    setDiasSel((prev) => {
      const n = new Set(prev);
      if (n.has(fecha)) n.delete(fecha);
      else n.add(fecha);
      return n;
    });

  const asignar = useMutation({
    mutationFn: async () => {
      const fechas = dias.filter((d) => diasSel.has(d));
      const resumen = await asignarDiasTurno(lunes, persona, franjaId, fechas);
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

  const incompleto = !persona || !franjaId || diasSel.size === 0;

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
            <Select value={franjaId} onValueChange={setFranjaId}>
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

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label>Días</Label>
            <div className="flex items-center gap-1.5 text-xs">
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
                onClick={() => setDiasSel(new Set(dias.slice(0, 5)))}
              >
                L–V
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
            {asignar.isPending ? "Asignando…" : "Asignar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
