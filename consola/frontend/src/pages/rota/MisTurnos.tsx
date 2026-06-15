// Pestaña MIS TURNOS de la rota. Partido mecánicamente de pages/Rota.tsx.
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarDays,
  Coffee,
  Sunrise,
  Sunset,
  User,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type {
  TurnoRota,
} from "@/types";

import { NavegadorSemana, formatearFechaCorta } from "./comun";


// --- Pestaña: Mis turnos ----------------------------------------------------

export function MisTurnos({
  lunes,
  setLunes,
  esAdmin = false,
  onVerCalendario,
}: {
  lunes: string;
  setLunes: (l: string) => void;
  /** El admin no suele estar en la rota; el vacío le ofrece saltar al Calendario. */
  esAdmin?: boolean;
  onVerCalendario?: () => void;
}) {
  const { marcaActiva } = useMarcaActiva();
  const q = useQuery({
    queryKey: ["rota", "mis-turnos", lunes, marcaActiva],
    queryFn: ({ signal }) =>
      api.misTurnos({ lunes, marca: marcaActiva ?? undefined }, signal),
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
          texto={
            esAdmin
              ? "Si gestionas el equipo, abre el Calendario para ver los turnos de todos."
              : undefined
          }
          accion={
            esAdmin && onVerCalendario ? (
              <Button variant="outline" size="sm" onClick={onVerCalendario}>
                Ver el calendario del equipo
                <ArrowRight className="ml-1.5 h-4 w-4" />
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          {!datos?.aprobada && (
            <p className="rounded-md border border-amber-300/60 bg-amber-50/50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
              Este horario es un borrador; puede cambiar antes de aprobarse
            </p>
          )}
          <ListaMisTurnos turnos={mios} />
        </>
      )}
    </div>
  );
}

// Icono por franja para escanear la lista de un vistazo (móvil-first). Mismo criterio que
// la rejilla del Calendario: amanecer = mañana, atardecer = tarde, café = descanso.
const ICONO_FRANJA: Record<string, typeof Sunrise> = {
  matutino: Sunrise,
  vespertino: Sunset,
  descanso: Coffee,
};

export function ListaMisTurnos({ turnos }: { turnos: TurnoRota[] }) {
  // Orden cronológico (fecha, franja).
  const ordenados = React.useMemo(
    () =>
      [...turnos].sort(
        (a, b) => a.fecha.localeCompare(b.fecha) || a.franja.localeCompare(b.franja),
      ),
    [turnos],
  );
  // Móvil-first: una tarjeta por turno, apilada en vertical. El dato primario (franja +
  // día) manda con tipografía grande y un icono de franja; los matices (sábado / override /
  // motivo / relevo) van debajo, legibles sin disparar el auto-zoom de iOS (nada < 16px en
  // los textos de acción; los matices son secundarios y deliberadamente pequeños).
  return (
    <ul className="space-y-3">
      {ordenados.map((t) => {
        // El icono se elige por si es descanso (café) o trabajo (sol). `TurnoRota` no trae
        // `es_descanso`, pero el backend mapea de forma fiable las franjas de descanso al
        // literal legacy `franja === "descanso"`; para el resto reusamos el literal cuando lo
        // hay (mañana/tarde) y caemos a Sunset para franjas custom (p. ej. "Cobertura nocturna").
        const esDescanso = t.franja === "descanso";
        const IconoFranja = esDescanso ? Coffee : ICONO_FRANJA[t.franja] ?? Sunset;
        return (
          <li key={t.id}>
            <Card>
              <CardContent className="space-y-2 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="flex items-center gap-1.5 text-base font-semibold">
                    <IconoFranja
                      className="h-4 w-4 text-muted-foreground"
                      aria-hidden="true"
                    />
                    {t.franja_nombre}
                  </span>
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
                <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <CalendarDays className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  <span className="capitalize">{formatearFechaCorta(t.fecha)}</span>
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
          </li>
        );
      })}
    </ul>
  );
}

