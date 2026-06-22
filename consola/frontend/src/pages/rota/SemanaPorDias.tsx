// Vista SEMANAL de Gestión con el diseño del calendario MENSUAL: una columna por día (lun→dom)
// y, dentro de cada día, sus franjas en texto («Mañana · 08:00–16:00» + los nombres debajo) en
// vez de la matriz franja×día con avatares. Sigue siendo editable: cada persona lleva su × (al
// pasar el ratón) y cada franja su «+ Añadir»; la cabecera del día abre el «Resumen del día».
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { diaCorto, esFinDeSemana } from "@/lib/rota-calendario";
import type { AusenciaRota, FranjaSemana, MiembroRota, TurnoRota } from "@/types";

import { ChipTurnoCM, DropdownAnadirPersona } from "./CalendarioPiezas";
import {
  ChipAusenciaDia,
  formatearFechaCorta,
  MasAusencias,
  presentacionFranja,
  type ConflictoCandidato,
} from "./comun";

export function SemanaPorDias({
  dias,
  franjasSemana,
  personasPorCelda,
  ausenciasPorDia,
  lunes,
  equipo,
  cms,
  editable,
  marcaActiva,
  hoy,
  ausenciaDe,
  conflictoCandidato,
  onResumenDia,
  onCambio,
}: {
  /** Las 7 fechas de la semana (lun→dom). */
  dias: string[];
  /** Franjas vivas de la semana; el render usa solo las LABORALES (descanso = no se trabaja). */
  franjasSemana: FranjaSemana[];
  /** Turnos por celda, clave `${franja_id}|${fecha}`. */
  personasPorCelda: Map<string, TurnoRota[]>;
  ausenciasPorDia: Map<string, AusenciaRota[]>;
  lunes: string;
  equipo: MiembroRota[];
  /** CMs de la marca (candidatos para «Añadir turno»). */
  cms: MiembroRota[];
  editable: boolean;
  /** `null` = vista «Todas»: etiqueta cada franja con su marca. */
  marcaActiva: string | null;
  hoy: string;
  ausenciaDe: (miembroId: string, fecha: string) => AusenciaRota | undefined;
  conflictoCandidato: (
    miembroId: string,
    fecha: string,
    franja: FranjaSemana,
  ) => ConflictoCandidato;
  onResumenDia: (fecha: string) => void;
  onCambio: () => void;
}) {
  const franjasLaborales = React.useMemo(
    () => franjasSemana.filter((f) => !f.es_descanso),
    [franjasSemana],
  );

  return (
    <div className="min-h-0 flex-1 overflow-auto rounded-lg border-l border-t">
      {/* Cabecera de días (sticky para no perderla al hacer scroll). */}
      <div className="sticky top-0 z-10 grid grid-cols-7 bg-background">
        {dias.map((fecha) => {
          const ausDia = ausenciasPorDia.get(fecha) ?? [];
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          return (
            <div
              key={fecha}
              className={cn(
                "flex flex-col gap-1 border-b border-r px-2 py-2",
                esHoy
                  ? "bg-keni-50/70 ring-1 ring-inset ring-keni-500/40 dark:bg-keni-900/20"
                  : finde
                    ? "bg-muted/50 dark:bg-muted/20"
                    : "",
              )}
            >
              <button
                type="button"
                onClick={() => onResumenDia(fecha)}
                aria-label={`Ver el resumen del ${formatearFechaCorta(fecha) || fecha}`}
                className="-mx-1 flex items-baseline justify-between rounded px-1 py-0.5 text-left hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span
                  className={cn(
                    "text-xs font-semibold capitalize",
                    esHoy && "text-keni-700 dark:text-keni-300",
                  )}
                >
                  {diaCorto(fecha)}
                  {esHoy && (
                    <span className="ml-1 font-normal normal-case text-keni-600 dark:text-keni-300">
                      · Hoy
                    </span>
                  )}
                </span>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {fecha.slice(8, 10)}
                </span>
              </button>
              {ausDia.length > 0 && (
                <div className="flex flex-wrap gap-1" aria-label={`Ausencias del ${fecha}`}>
                  {ausDia.slice(0, 2).map((a) => (
                    <ChipAusenciaDia key={a.id} ausencia={a} />
                  ))}
                  {ausDia.length > 2 && <MasAusencias ausencias={ausDia.slice(2)} />}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Cuerpo: una columna por día, con sus franjas apiladas en texto. */}
      <div className="grid grid-cols-7">
        {dias.map((fecha) => {
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          return (
            <div
              key={fecha}
              className={cn(
                "min-h-[16rem] min-w-0 space-y-1.5 border-b border-r p-1.5",
                !esHoy && finde && "bg-muted/30 dark:bg-muted/10",
                esHoy && "bg-keni-50/30 dark:bg-keni-900/10",
              )}
            >
              {franjasLaborales.map((franja, idx) => {
                const meta = presentacionFranja(franja, idx);
                const personas = personasPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                const yaEnCelda = new Set(personas.map((t) => t.miembro_id));
                const cmsDisponibles = cms.filter((m) => !yaEnCelda.has(m.id));
                return (
                  <div
                    key={franja.id}
                    className={cn(
                      "rounded-md border border-l-[3px] px-1.5 py-1",
                      meta.banda,
                      meta.fondo,
                    )}
                  >
                    <div className="mb-0.5 flex items-baseline justify-between gap-1">
                      <span className="truncate text-[11px] font-semibold leading-tight text-foreground/90">
                        {franja.nombre}
                        <span className="ml-1 font-normal tabular-nums text-muted-foreground">
                          · {franja.inicio}–{franja.fin}
                        </span>
                      </span>
                      {marcaActiva === null && franja.marca_nombre ? (
                        <Badge
                          variant="outline"
                          className="shrink-0 px-1 py-0 text-[9px] font-normal"
                        >
                          {franja.marca_nombre}
                        </Badge>
                      ) : null}
                    </div>
                    {personas.length > 0 && (
                      <div className="space-y-px text-foreground/80">
                        {personas.map((t) => (
                          <ChipTurnoCM
                            key={t.id}
                            turno={t}
                            equipo={equipo}
                            franjas={franjasSemana}
                            ausencia={ausenciaDe(t.miembro_id, fecha)}
                            editable={editable}
                            onCambio={onCambio}
                            variante="texto"
                          />
                        ))}
                      </div>
                    )}
                    {editable && (
                      <div className="mt-1">
                        <DropdownAnadirPersona
                          lunes={lunes}
                          fecha={fecha}
                          franja={franja}
                          cmsDisponibles={cmsDisponibles}
                          conflictoCandidato={conflictoCandidato}
                          onCambio={onCambio}
                          placeholder={personas.length === 0 ? "Añadir turno" : "Añadir"}
                        />
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
    </div>
  );
}
