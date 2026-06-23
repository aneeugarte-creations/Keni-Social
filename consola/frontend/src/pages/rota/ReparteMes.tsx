import { useMutation } from "@tanstack/react-query";
import { Loader2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { mensajeError } from "@/lib/api";
import { asignarMatriz } from "@/lib/rota-reparto";
import { cn } from "@/lib/utils";
import type { FranjaSemana, MiembroRota } from "@/types";

import { aMinutos24 } from "./DialogoAsignarTurnos";

/** getDay(): 0=domingo … 6=sábado → letra del día (lunes=L). */
const LETRAS_SEM = ["D", "L", "M", "X", "J", "V", "S"];
function letraDeFecha(iso: string): string {
  return LETRAS_SEM[new Date(`${iso}T12:00:00`).getDay()] ?? "";
}

function esHoraValida(s: string): boolean {
  return aMinutos24(s) !== null;
}

/** Token de persona (mismo lenguaje que el calendario: elegido = naranja suave). */
function Token({
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
        "rounded-full px-2.5 py-1 text-[13px] leading-tight transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        activo
          ? "bg-keni-50 font-medium text-keni-700 dark:bg-keni-900/30 dark:text-keni-300"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/**
 * Panel «Asignar turnos» de Gestión = Mes único (variante SELECCIÓN-EN-MES).
 *
 * Los DÍAS los marca el usuario en el calendario mensual (`diasSel`, puede cruzar semanas). Aquí
 * elige PERSONAS y HORARIO, y AFINA por persona en una matriz editable persona×día: por defecto
 * cada persona elegida trabaja todos los días marcados, y se puede apagar cualquier celda (cada
 * quien su patrón, sin plantillas obligatorias). Al asignar, el motor `asignarMatriz` agrupa las
 * fechas de cada persona por su semana y resuelve la franja con las franjas de ESA semana.
 */
export function ReparteMes({
  diasSel,
  cms,
  franjasPorSemana,
  onCambio,
  onCerrar,
  onLimpiarDias,
}: {
  /** Días ISO marcados en el calendario (columnas de la matriz). Controlado por Gestión. */
  diasSel: Set<string>;
  /** CMs asignables de la marca activa (filas candidatas). */
  cms: MiembroRota[];
  /** lunes ISO → franjas LABORALES vivas de esa semana (las de las semanas tocadas por `diasSel`). */
  franjasPorSemana: Map<string, FranjaSemana[]>;
  /** Refresca el calendario tras asignar. */
  onCambio: () => void;
  /** Oculta el panel (✕). */
  onCerrar: () => void;
  /** Limpia la selección de días del calendario (tras una tanda con turnos creados). */
  onLimpiarDias: () => void;
}) {
  const dias = React.useMemo(() => Array.from(diasSel).sort(), [diasSel]);
  const [personasSel, setPersonasSel] = React.useState<Set<string>>(() => new Set());
  const [inicio, setInicio] = React.useState("08:00");
  const [fin, setFin] = React.useState("16:00");
  // `excluidas[persona]` = días que ESA persona NO trabaja (opt-out). Por defecto todas las celdas
  // están encendidas; apagar una celda añade su fecha aquí. Así la matriz se deriva de `diasSel` +
  // las exclusiones, sin reconciliar estado cuando cambian la selección o las personas.
  const [excluidas, setExcluidas] = React.useState<Map<string, Set<string>>>(() => new Map());

  const togglePersona = (id: string) =>
    setPersonasSel((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const celdaEncendida = (id: string, fecha: string) => !excluidas.get(id)?.has(fecha);
  const toggleCelda = (id: string, fecha: string) =>
    setExcluidas((prev) => {
      const n = new Map(prev);
      const s = new Set(n.get(id) ?? []);
      if (s.has(fecha)) s.delete(fecha);
      else s.add(fecha);
      n.set(id, s);
      return n;
    });

  const personasElegidas = cms.filter((m) => personasSel.has(m.id));
  const diasDePersona = (id: string) => dias.filter((f) => celdaEncendida(id, f));
  const totalTurnos = personasElegidas.reduce((acc, m) => acc + diasDePersona(m.id).length, 0);
  const horasValidas = esHoraValida(inicio) && esHoraValida(fin);

  const incompleto =
    personasElegidas.length === 0 || diasSel.size === 0 || !horasValidas || totalTurnos === 0;
  const pista =
    diasSel.size === 0
      ? "Marca días en el calendario para repartir."
      : personasElegidas.length === 0
        ? "Elige al menos una persona."
        : !horasValidas
          ? "Escribe un horario válido (HH:MM)."
          : totalTurnos === 0
            ? "Enciende al menos una celda."
            : null;

  const asignar = useMutation({
    mutationFn: async () => {
      const porPersona = new Map<string, string[]>();
      for (const m of personasElegidas) porPersona.set(m.id, diasDePersona(m.id));
      return asignarMatriz(porPersona, franjasPorSemana, inicio, fin);
    },
    onSuccess: (r) => {
      onCambio();
      const partes: string[] = [];
      if (r.creados) {
        const p = r.personasConCreados === 1 ? "1 persona" : `${r.personasConCreados} personas`;
        partes.push(`${r.creados} turno${r.creados === 1 ? "" : "s"} para ${p}`);
      }
      if (r.yaEstaba) partes.push(`${r.yaEstaba} ya estaba${r.yaEstaba === 1 ? "" : "n"}`);
      if (r.requierenOverride)
        partes.push(
          `${r.requierenOverride} por ausencia ${r.requierenOverride === 1 ? "pide" : "piden"} override (hazlo desde la celda)`,
        );
      if (r.sinFranja)
        partes.push(`${r.sinFranja} sin franja laboral esa semana`);
      if (r.fallos) partes.push(`${r.fallos} con error`);
      const msg = partes.join(" · ") || "Sin cambios.";
      // Tras una tanda con turnos creados, limpia personas + exclusiones y la selección de días
      // (para encadenar otra). Si no se creó nada, mantiene todo para ajustar y reintentar.
      if (r.creados > 0) {
        toast.success(msg);
        setPersonasSel(new Set());
        setExcluidas(new Map());
        onLimpiarDias();
      } else {
        toast.error(msg);
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eyebrow = "text-[11px] font-semibold uppercase tracking-wide text-muted-foreground/70";

  return (
    <div className="flex shrink-0 flex-col gap-3 rounded-xl border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Asignar turnos</h2>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onCerrar}
          aria-label="Cerrar"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Personas */}
      <div className="space-y-2">
        <div className="flex items-baseline justify-between">
          <Label className={eyebrow}>Personas</Label>
          <div className="flex items-center gap-1.5 text-[11px]">
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
        <div className="flex flex-wrap gap-0.5">
          {cms.map((m) => (
            <Token key={m.id} activo={personasSel.has(m.id)} onClick={() => togglePersona(m.id)}>
              {m.nombre}
            </Token>
          ))}
        </div>
      </div>

      {/* Horario */}
      <div className="space-y-2">
        <Label className={eyebrow}>Horario</Label>
        <div className="flex items-center gap-3">
          <Input
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            placeholder="08:00"
            className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
            aria-label="Hora de inicio"
          />
          <span className="text-muted-foreground">–</span>
          <Input
            value={fin}
            onChange={(e) => setFin(e.target.value)}
            placeholder="16:00"
            className="h-8 w-[68px] rounded-none border-0 border-b border-input bg-transparent px-1 tabular-nums focus-visible:border-keni-400 focus-visible:ring-0"
            aria-label="Hora de fin"
          />
        </div>
        {!horasValidas && (inicio || fin) && (
          <p className="text-xs text-destructive">Usa HH:MM (24h), p. ej. 08:00.</p>
        )}
      </div>

      {/* Matriz editable: filas = personas elegidas, columnas = días marcados en el calendario. */}
      <div className="space-y-2">
        <div>
          <Label className={eyebrow}>El patrón de cada persona</Label>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Toca una celda para ajustar los días de cada persona. Cada quien puede tener el suyo.
          </p>
        </div>
        {diasSel.size === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Marca días en el calendario para repartir.
          </p>
        ) : personasElegidas.length === 0 ? (
          <p className="rounded-lg border border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Elige personas para ver la matriz.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border p-2">
            <table className="border-separate border-spacing-[3px] tabular-nums">
              <thead>
                <tr>
                  <th />
                  {dias.map((f) => (
                    <th key={f} className="px-0 text-center align-bottom font-normal leading-none">
                      <span className="block text-[10px] font-semibold uppercase text-muted-foreground/70">
                        {letraDeFecha(f)}
                      </span>
                      <span className="block text-[9px] text-muted-foreground/50">
                        {f.slice(8, 10)}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {personasElegidas.map((m) => (
                  <tr key={m.id}>
                    <td className="max-w-[5rem] truncate pr-2 text-[11.5px] text-foreground/80">
                      {m.nombre}
                    </td>
                    {dias.map((f) => {
                      const on = celdaEncendida(m.id, f);
                      return (
                        <td key={f}>
                          <button
                            type="button"
                            role="checkbox"
                            aria-checked={on}
                            aria-label={`${m.nombre} ${f.slice(8, 10)}`}
                            onClick={() => toggleCelda(m.id, f)}
                            className={cn(
                              "h-[18px] w-[22px] rounded-[4px] border transition-colors",
                              on
                                ? "border-keni-400/40 bg-keni-50 dark:bg-keni-900/30"
                                : "border-border/60 hover:bg-accent",
                            )}
                          />
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pie: pista de qué falta, o el total real con el desglose por persona. */}
      <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
        <span className="text-xs text-muted-foreground">
          {pista ?? (
            <>
              <b className="font-semibold text-keni-700 dark:text-keni-300">
                {totalTurnos} turno{totalTurnos === 1 ? "" : "s"}
              </b>
              {personasElegidas.length > 0 && (
                <>
                  {" · "}
                  {personasElegidas
                    .map((m) => `${m.nombre} ${diasDePersona(m.id).length}`)
                    .join(" · ")}
                </>
              )}
            </>
          )}
        </span>
        <Button
          variant="secondary"
          onClick={() => asignar.mutate()}
          disabled={incompleto || asignar.isPending}
        >
          {asignar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
          {asignar.isPending
            ? "Asignando…"
            : totalTurnos > 0
              ? `Asignar ${totalTurnos} turno${totalTurnos === 1 ? "" : "s"}`
              : "Asignar"}
        </Button>
      </div>
    </div>
  );
}
