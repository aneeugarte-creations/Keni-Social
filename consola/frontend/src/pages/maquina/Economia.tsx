/**
 * Página ECONOMÍA (`/maquina/economia`): la CONTABILIDAD de la máquina de contenido, separada de
 * la operación de la cola (`/maquina/computo`). Reúne en un solo sitio el gasto: el presupuesto
 * diario editable + la parada de emergencia (globales) y la economía de tokens DESGLOSADA por
 * motor (Investigación | Producción): totales (trabajos IA · tokens · coste), la serie de 14 días
 * y los desgloses por tipo de trabajo y por día.
 *
 * Respeta el switch GLOBAL de marca (la economía se acota a la marca activa; el presupuesto es
 * global). `?proceso=investigacion|produccion` enfoca a un solo motor (columna a ancho completo).
 */
import { useQuery } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import * as React from "react";
import { Button } from "@/components/ui/button";
import { useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";
import { formatearDia } from "@/lib/fecha";
import { costeUsd, numeroCompacto, numeroCompleto } from "@/lib/formato";
import { etiquetaTipoGeneracion } from "@/lib/generaciones";
import { INTERVALO_SERIE_MS, INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { PanelPresupuesto } from "@/pages/maquina/cola-comun";
import { PROC_META, SerieProceso } from "@/pages/monitor/comun";
import type {
  ActividadProcesoBloque,
  ActividadPorDia,
  ActividadPorTipo,
  ColaSerie,
  Proceso,
} from "@/types";

/** Los dos motores de la máquina (ADR 0011), en orden de flujo. */
const MOTORES: Proceso[] = ["investigacion", "produccion"];

/** Mini-tabla de desglose por TIPO de trabajo (de un motor). */
function DesglosePorTipo({ filas }: { filas: ActividadPorTipo[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por tipo</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Tipo</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por tipo.
                </TableCell>
              </TableRow>
            ) : (
              filas.map((f) => (
                <TableRow key={f.tipo}>
                  <TableCell className="pl-6 font-medium">
                    {f.tipo ? etiquetaTipoGeneracion(f.tipo) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.tokens)}>
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Mini-tabla de desglose por DÍA, más reciente primero (incluye tokens). */
function DesglosePorDia({ filas }: { filas: ActividadPorDia[] }) {
  const ordenadas = React.useMemo(
    () => [...filas].sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Día</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por día.
                </TableCell>
              </TableRow>
            ) : (
              ordenadas.map((f) => (
                <TableRow key={f.dia}>
                  <TableCell className="pl-6 font-medium">{formatearDia(f.dia)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.tokens)}>
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Bloque «Economía (tokens)» de un motor: el DESGLOSE SEPARADO POR MOTOR (de
 *  `agregados.por_proceso[motor]`): totales + serie del proceso + por tipo + por día. */
function EconomiaMotor({
  motor,
  bloque,
  serie,
  cargando,
}: {
  motor: Proceso;
  bloque: ActividadProcesoBloque | undefined;
  serie: ColaSerie | undefined;
  cargando: boolean;
}) {
  const total = bloque?.total;
  const meta = PROC_META[motor];
  return (
    <section className="space-y-3">
      <h2 className={cn("flex items-center gap-2 text-lg font-semibold", meta.texto)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        {meta.etiqueta}
      </h2>
      {cargando ? (
        <Skeleton className="h-24 w-full rounded-xl" />
      ) : (
        <div className="grid grid-cols-3 gap-3">
          <TarjetaKpi
            variante="card"
            etiqueta="Trabajos IA"
            valor={numeroCompleto(total?.items ?? 0)}
          />
          <TarjetaKpi
            variante="card"
            etiqueta="Tokens"
            valor={numeroCompacto(total?.tokens ?? 0)}
            titulo={numeroCompleto(total?.tokens ?? 0)}
          />
          <TarjetaKpi variante="card" etiqueta="Coste" valor={costeUsd(total?.coste_usd ?? 0)} />
        </div>
      )}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <RotateCcw className="h-4 w-4 text-muted-foreground" />
            Últimos 14 días
          </CardTitle>
        </CardHeader>
        <CardContent className="p-4 pt-2">
          {serie ? (
            <SerieProceso serie={serie} soloProceso={motor} />
          ) : (
            <Skeleton className="h-32 w-full" />
          )}
        </CardContent>
      </Card>
      <DesglosePorTipo filas={bloque?.por_tipo ?? []} />
      <DesglosePorDia filas={bloque?.por_dia ?? []} />
    </section>
  );
}

export default function Economia() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const { marcaActiva } = useMarcaActiva();
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;

  // Presupuesto (global) + resultado de hoy: la cola trae el presupuesto; la serie, el gasto.
  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  const serie = useQuery({
    queryKey: ["actividad", "cola", "series"],
    queryFn: ({ signal }) => api.colaSeries(14, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });
  // Agregados de actividad IA (totales + por_proceso): la economía DESGLOSADA por motor.
  const agregados = useQuery({
    queryKey: ["actividad", "agregados", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.actividadAgregados({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });

  const quitarProceso = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("proceso");
    setSearchParams(params, { replace: true });
  };

  const motores: Proceso[] = proceso ? [proceso] : MOTORES;

  return (
    <>
      {/* Prefiltro de proceso (?proceso=): la página queda enfocada a ese motor. */}
      {proceso && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            Enfocado a{" "}
            <strong className={PROC_META[proceso].texto}>{PROC_META[proceso].etiqueta}</strong>.
          </span>
          <Button variant="ghost" size="sm" onClick={quitarProceso}>
            Ver ambos motores
          </Button>
        </div>
      )}

      {/* Presupuesto + parada de emergencia (GLOBALES). */}
      <div className="mb-6">
        {cola.isError ? (
          <BloqueError
            titulo="No se pudo leer el presupuesto"
            mensaje={mensajeError(cola.error)}
            onReintentar={() => void cola.refetch()}
            cargando={cola.isFetching}
          />
        ) : cola.isPending ? (
          <Skeleton className="h-28 w-full rounded-xl" />
        ) : (
          cola.data.presupuesto && (
            <PanelPresupuesto presupuesto={cola.data.presupuesto} esAdmin={esAdmin} />
          )
        )}
      </div>

      {/* Economía por motor (desglose separado). */}
      <div
        className={cn("grid grid-cols-1 gap-8", motores.length > 1 && "xl:grid-cols-2 xl:gap-6")}
      >
        {motores.map((m) => (
          <EconomiaMotor
            key={m}
            motor={m}
            bloque={agregados.data?.por_proceso?.[m]}
            serie={serie.data}
            cargando={agregados.isPending}
          />
        ))}
      </div>
    </>
  );
}
