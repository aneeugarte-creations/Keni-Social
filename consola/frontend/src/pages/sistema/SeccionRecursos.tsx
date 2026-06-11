import { useQuery } from "@tanstack/react-query";
import { Cpu, HardDrive, MemoryStick } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { DiscoSistema } from "@/types";

import {
  INTERVALO_RECURSOS_MS,
  colorUso,
  formatoBytes,
  formatoPorcentaje,
} from "./lib";

/** Barra de progreso simple (sin dependencia de un componente shadcn nuevo). */
function BarraUso({ porcentaje }: { porcentaje: number | null | undefined }) {
  const ancho = porcentaje == null ? 0 : Math.min(100, Math.max(0, porcentaje));
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-muted"
      role="progressbar"
      aria-valuenow={porcentaje ?? undefined}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={cn("h-full rounded-full transition-all", colorUso(porcentaje))}
        style={{ width: `${ancho}%` }}
      />
    </div>
  );
}

/** Tarjeta de métrica con icono, valor grande, subtítulo y barra opcional. */
function TarjetaMetrica({
  icono: Icono,
  titulo,
  valor,
  subtitulo,
  porcentaje,
}: {
  icono: typeof Cpu;
  titulo: string;
  valor: React.ReactNode;
  subtitulo?: React.ReactNode;
  porcentaje?: number | null;
}) {
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Icono className="h-4 w-4" aria-hidden="true" />
          {titulo}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-4 pt-0">
        <div className="text-2xl font-semibold tabular-nums">{valor}</div>
        {subtitulo && <div className="text-xs text-muted-foreground">{subtitulo}</div>}
        {porcentaje !== undefined && <BarraUso porcentaje={porcentaje} />}
      </CardContent>
    </Card>
  );
}

function TarjetaDisco({ disco }: { disco: DiscoSistema }) {
  return (
    <TarjetaMetrica
      icono={HardDrive}
      titulo={`Disco · ${disco.etiqueta}`}
      valor={formatoPorcentaje(disco.porcentaje)}
      subtitulo={
        <>
          {formatoBytes(disco.usado)} de {formatoBytes(disco.total)}{" "}
          <span className="text-muted-foreground/70">({disco.ruta})</span>
        </>
      }
      porcentaje={disco.porcentaje}
    />
  );
}

/** Sección de recursos del servidor (CPU/RAM/disco) con auto-refresco. */
export function SeccionRecursos() {
  const query = useQuery({
    queryKey: ["sistema", "recursos"],
    queryFn: ({ signal }) => api.sistemaRecursos(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  if (query.isPending) {
    return (
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudieron leer los recursos del servidor"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { cpu, ram, discos, psutil } = query.data;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <TarjetaMetrica
          icono={Cpu}
          titulo="CPU"
          valor={formatoPorcentaje(cpu.porcentaje)}
          subtitulo={cpu.cores != null ? `${cpu.cores} núcleos` : undefined}
          porcentaje={cpu.porcentaje}
        />
        <TarjetaMetrica
          icono={MemoryStick}
          titulo="Memoria"
          valor={formatoPorcentaje(ram.porcentaje)}
          subtitulo={
            ram.total != null
              ? `${formatoBytes(ram.usado)} de ${formatoBytes(ram.total)}`
              : "psutil no disponible"
          }
          porcentaje={ram.porcentaje}
        />
        {discos.map((d) => (
          <TarjetaDisco key={d.ruta} disco={d} />
        ))}
      </div>
      {!psutil && (
        <p className="text-xs text-muted-foreground">
          CPU y memoria no disponibles (psutil no está instalado en este servidor). El
          disco se mide igualmente.
        </p>
      )}
    </div>
  );
}
