import { CalendarOff, ChevronLeft, ChevronRight } from "lucide-react";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { Publicacion } from "@/types";

import { formatearHora, iconoRed, nombreRed } from "./meta";

/** Nombres de los días (lunes a domingo), abreviados es-MX. */
const DIAS_SEMANA = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];

/** Clave YYYY-MM-DD en hora local para agrupar por día. */
function claveDia(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Índice día -> publicaciones programadas ese día (ordenadas por hora). */
function indexarPorDia(publicaciones: Publicacion[]): Map<string, Publicacion[]> {
  const mapa = new Map<string, Publicacion[]>();
  for (const p of publicaciones) {
    if (!p.fecha_programada) continue;
    const d = new Date(p.fecha_programada);
    if (Number.isNaN(d.getTime())) continue;
    const clave = claveDia(d);
    const lista = mapa.get(clave) ?? [];
    lista.push(p);
    mapa.set(clave, lista);
  }
  for (const lista of mapa.values()) {
    lista.sort((a, b) => {
      const ta = a.fecha_programada ? new Date(a.fecha_programada).getTime() : 0;
      const tb = b.fecha_programada ? new Date(b.fecha_programada).getTime() : 0;
      return ta - tb;
    });
  }
  return mapa;
}

/** Devuelve las celdas (42, 6 semanas) que componen la rejilla del mes. */
function celdasDelMes(ancla: Date): Date[] {
  const primero = new Date(ancla.getFullYear(), ancla.getMonth(), 1);
  // getDay(): 0=domingo..6=sábado. Queremos que la semana empiece en lunes.
  const offset = (primero.getDay() + 6) % 7;
  const inicio = new Date(primero);
  inicio.setDate(primero.getDate() - offset);
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(inicio);
    d.setDate(inicio.getDate() + i);
    return d;
  });
}

/** Una píldora compacta de publicación dentro de una celda del calendario. */
function PildoraPub({
  publicacion,
  onAbrir,
}: {
  publicacion: Publicacion;
  onAbrir: (p: Publicacion) => void;
}) {
  const Icono = iconoRed(publicacion.red);
  return (
    <button
      type="button"
      onClick={() => onAbrir(publicacion)}
      title={`${formatearHora(publicacion.fecha_programada)} · ${nombreRed(publicacion.red)} · ${publicacion.titulo}`}
      className="flex w-full items-center gap-1 truncate rounded bg-amber-500/15 px-1.5 py-0.5 text-left text-xs text-amber-800 transition-colors hover:bg-amber-500/25 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring dark:text-amber-200"
    >
      <Icono className="h-3 w-3 shrink-0" />
      <span className="shrink-0 tabular-nums">{formatearHora(publicacion.fecha_programada)}</span>
      <span className="truncate">{publicacion.titulo}</span>
    </button>
  );
}

/**
 * Vista calendario: rejilla mensual navegable que muestra las publicaciones
 * programadas en su día. Construida solo con `Date`/`Intl` (sin librerías).
 */
export function VistaCalendario({
  publicaciones,
  onEditar,
}: {
  publicaciones: Publicacion[];
  onEditar: (p: Publicacion) => void;
}) {
  const [ancla, setAncla] = React.useState(() => new Date());

  const programadas = React.useMemo(
    () => publicaciones.filter((p) => !!p.fecha_programada),
    [publicaciones],
  );
  const porDia = React.useMemo(() => indexarPorDia(programadas), [programadas]);
  const celdas = React.useMemo(() => celdasDelMes(ancla), [ancla]);

  const hoy = claveDia(new Date());
  const mesActual = ancla.getMonth();
  const etiquetaMes = new Intl.DateTimeFormat("es-MX", {
    month: "long",
    year: "numeric",
  }).format(ancla);

  function cambiarMes(delta: number) {
    setAncla((prev) => new Date(prev.getFullYear(), prev.getMonth() + delta, 1));
  }

  if (programadas.length === 0) {
    return (
      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
            <CalendarOff className="h-6 w-6" />
          </div>
          <div className="space-y-1">
            <p className="font-medium">No hay publicaciones programadas</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Pon una publicación en estado “Programado” con su fecha y hora para verla aquí.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium capitalize">{etiquetaMes}</p>
          <div className="flex items-center gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAncla(new Date())}
              title="Ir al mes actual"
            >
              Hoy
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Mes anterior"
              onClick={() => cambiarMes(-1)}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label="Mes siguiente"
              onClick={() => cambiarMes(1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-7 gap-px overflow-hidden rounded-md border border-border bg-border">
          {DIAS_SEMANA.map((d) => (
            <div
              key={d}
              className="bg-muted/60 px-2 py-1.5 text-center text-xs font-medium text-muted-foreground"
            >
              {d}
            </div>
          ))}
          {celdas.map((dia) => {
            const clave = claveDia(dia);
            const delMes = dia.getMonth() === mesActual;
            const esHoy = clave === hoy;
            const items = porDia.get(clave) ?? [];
            return (
              <div
                key={clave}
                className={cn(
                  "min-h-[6rem] space-y-1 bg-card p-1.5",
                  !delMes && "bg-muted/30 text-muted-foreground",
                )}
              >
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center text-xs",
                    esHoy && "rounded-full bg-primary font-medium text-primary-foreground",
                  )}
                >
                  {dia.getDate()}
                </div>
                <div className="space-y-1">
                  {items.map((p) => (
                    <PildoraPub key={p.id} publicacion={p} onAbrir={onEditar} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
