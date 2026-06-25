// Vista SEMANAL de Gestión con la MISMA anatomía y paleta que el calendario MENSUAL: la banda de
// días gris en mayúsculas arriba (idéntica a RejillaMensual) y, debajo, una columna por día con el
// número arriba a la derecha y sus franjas en texto («Mañana · 08:00–16:00» + los nombres). Se lee
// como una FILA del mes, más alta. El color del bloque de franja indica el PERIODO del turno
// (mañana ámbar · tarde naranja · noche rosa, vía `presentacionTurnoPorHora`); franja vacía =
// hueco discontinuo neutro; «hoy» = tinte `keni-50` + número naranja. Sigue siendo editable: cada
// persona lleva su × (al pasar el ratón) y cada franja su «+ Añadir»; el número del día abre el
// «Resumen del día».
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
  presentacionTurnoPorHora,
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
      {/* Banda de días: gris, mayúsculas, centrada — la MISMA cabecera del calendario mensual
          (RejillaMensual), para que la semana se lea como una fila del mes. Sticky al hacer scroll. */}
      <div className="sticky top-0 z-10 grid grid-cols-7 bg-muted/40 text-center text-[11px] font-medium uppercase tracking-wide text-muted-foreground dark:bg-muted/15">
        {dias.map((fecha) => (
          <div key={fecha} className="border-b border-r py-2">
            {diaCorto(fecha)}
          </div>
        ))}
      </div>

      {/* Cuerpo: una columna por día. Cada columna replica la celda del mes — número del día arriba
          a la derecha (clicable → «Resumen del día»), «hoy» con anillo + número naranja — y debajo
          las franjas apiladas en texto. */}
      <div className="grid grid-cols-7">
        {dias.map((fecha) => {
          const ausDia = ausenciasPorDia.get(fecha) ?? [];
          const finde = esFinDeSemana(fecha);
          const esHoy = fecha === hoy;
          return (
            <div
              key={fecha}
              className={cn(
                "min-h-[16rem] min-w-0 border-b border-r bg-background p-1.5",
                !esHoy && finde && "bg-muted/30 dark:bg-muted/10",
                esHoy && "bg-keni-50 dark:bg-keni-900/30",
              )}
            >
              {/* Número del día, arriba a la derecha y clicable (abre el resumen), como la celda
                  del mensual. «Hoy» en naranja seminegrita; el resto, apagado. */}
              <button
                type="button"
                onClick={() => onResumenDia(fecha)}
                aria-label={`Ver el resumen del ${formatearFechaCorta(fecha) || fecha}`}
                className="mb-1 flex w-full items-center justify-end rounded px-1 py-0.5 hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span
                  className={cn(
                    "text-xs tabular-nums",
                    esHoy
                      ? "font-semibold text-keni-700 dark:text-keni-300"
                      : "text-muted-foreground",
                  )}
                >
                  {Number(fecha.slice(8, 10))}
                </span>
              </button>
              {ausDia.length > 0 && (
                <div className="mb-1 flex flex-wrap gap-1" aria-label={`Ausencias del ${fecha}`}>
                  {ausDia.slice(0, 2).map((a) => (
                    <ChipAusenciaDia key={a.id} ausencia={a} />
                  ))}
                  {ausDia.length > 2 && <MasAusencias ausencias={ausDia.slice(2)} />}
                </div>
              )}
              <div className="space-y-1.5">
                {franjasLaborales.map((franja) => {
                  const personas = personasPorCelda.get(`${franja.id}|${fecha}`) ?? [];
                  const yaEnCelda = new Set(personas.map((t) => t.miembro_id));
                  const cmsDisponibles = cms.filter((m) => !yaEnCelda.has(m.id));
                  // Mismo lenguaje visual que el calendario mensual. Una franja CON gente es un
                  // bloque tintado por PERIODO del turno (mañana/tarde/noche, `presentacionTurnoPorHora`),
                  // como el chip de turno del mes; vacía, un hueco discontinuo neutro («añadir aquí»).
                  const tienePersonas = personas.length > 0;
                  const tono = presentacionTurnoPorHora(franja.inicio);
                  return (
                    <div
                      key={franja.id}
                      className={cn(
                        "rounded px-1.5 py-1",
                        tienePersonas
                          ? tono.fondo
                          : "border border-dashed border-border bg-muted/20 dark:bg-muted/10",
                      )}
                    >
                      <div className="mb-0.5 flex items-baseline justify-between gap-1">
                        <span
                          className={cn(
                            "truncate text-[11px] font-medium leading-tight",
                            tienePersonas ? tono.nombre : "text-muted-foreground",
                          )}
                        >
                          {franja.nombre}
                          <span
                            className={cn(
                              "ml-1 font-normal tabular-nums",
                              tienePersonas ? tono.horas : "text-muted-foreground/70",
                            )}
                          >
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
                      {tienePersonas && (
                        <div className={cn("space-y-px", tono.gente)}>
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
                        <div className={tienePersonas ? "mt-1" : "mt-0.5"}>
                          <DropdownAnadirPersona
                            lunes={lunes}
                            fecha={fecha}
                            franja={franja}
                            cmsDisponibles={cmsDisponibles}
                            conflictoCandidato={conflictoCandidato}
                            onCambio={onCambio}
                            placeholder={tienePersonas ? "Añadir" : "Añadir turno"}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
