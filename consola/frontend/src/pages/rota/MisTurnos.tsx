// Pestaña MIS TURNOS de la rota. Partido mecánicamente de pages/Rota.tsx.
import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  User,
} from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type {
  TurnoRota,
} from "@/types";

import { ETIQUETA_FRANJA, NavegadorSemana, formatearFechaCorta } from "./comun";


// --- Pestaña: Mis turnos ----------------------------------------------------

export function MisTurnos({
  lunes,
  setLunes,
}: {
  lunes: string;
  setLunes: (l: string) => void;
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

export function ListaMisTurnos({ turnos }: { turnos: TurnoRota[] }) {
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

