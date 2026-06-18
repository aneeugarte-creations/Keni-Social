/**
 * Página ECONOMÍA (`/maquina/economia`): la CONTABILIDAD de la máquina de contenido, separada de
 * la operación de la cola (`/maquina/computo`). Reúne en un solo sitio el gasto: el presupuesto
 * diario editable + la parada de emergencia (globales) y la economía de tokens DESGLOSADA por
 * motor (Investigación | Producción): totales (trabajos IA · tokens · coste), la serie de los
 * últimos 7 días y los desgloses por tipo de trabajo y por día.
 *
 * La economía sale de `/api/actividad/economia` (ledger `gasto_ia`): es la MISMA fuente para los
 * totales, la serie y los desgloses, así que todo cuadra. Respeta el switch de marca: una marca
 * activa acota el desglose a sus filas; "todas" muestra el AGREGADO global. El presupuesto y la
 * parada de emergencia se gestionan aparte (globales). `?proceso=investigacion|produccion` enfoca
 * a un solo motor (columna a ancho completo).
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
import { PROC_META } from "@/pages/monitor/comun";
import type {
  EconomiaDia,
  EconomiaProcesoBloque,
  EconomiaTipo,
  Proceso,
} from "@/types";

/** Los dos motores de la máquina (ADR 0011), en orden de flujo. */
const MOTORES: Proceso[] = ["investigacion", "produccion"];

/** Días de la ventana de economía (la serie y los desgloses). */
const DIAS = 7;

/** Línea discreta de "sin datos": una sola fila, no una tarjeta enorme con hueco. */
function LineaVacia({ texto }: { texto: string }) {
  return <p className="px-6 py-3 text-sm text-muted-foreground">{texto}</p>;
}

/** Mini-tabla de desglose por TIPO de trabajo (de un motor). */
function DesglosePorTipo({ filas }: { filas: EconomiaTipo[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por tipo</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {filas.length === 0 ? (
          <LineaVacia texto="Sin actividad por tipo" />
        ) : (
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
              {filas.map((f) => (
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
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** Mini-tabla de desglose por DÍA con actividad, más reciente primero. */
function DesglosePorDia({ filas }: { filas: EconomiaDia[] }) {
  const conActividad = React.useMemo(
    () => filas.filter((f) => f.items > 0).sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        {conActividad.length === 0 ? (
          <LineaVacia texto="Sin actividad por día" />
        ) : (
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
              {conActividad.map((f) => (
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
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

/** Mini-gráfico de los últimos `DIAS` días: una barra por día escalada por TOKENS. Cada fila es
 *  clicable: togglea el día seleccionado (clic en el activo lo deselecciona) y eso reenfoca los
 *  KPIs superiores a ese día. */
function SerieEconomia({
  motor,
  filas,
  diaSel,
  onToggle,
}: {
  motor: Proceso;
  filas: EconomiaDia[];
  diaSel: string | null;
  onToggle: (dia: string) => void;
}) {
  const maximo = Math.max(1, ...filas.map((f) => f.tokens));
  const meta = PROC_META[motor];
  return (
    <div className="space-y-1.5">
      {filas.map((f) => {
        const activo = f.dia === diaSel;
        return (
          <button
            key={f.dia}
            type="button"
            onClick={() => onToggle(f.dia)}
            aria-pressed={activo}
            className={cn(
              "flex w-full items-center gap-3 rounded px-2 py-1 text-left text-xs transition-colors",
              activo ? "bg-muted" : "hover:bg-muted/50",
            )}
          >
            <span className="w-16 shrink-0 tabular-nums text-muted-foreground">
              {formatearDia(f.dia)}
            </span>
            <div className="flex h-4 flex-1 overflow-hidden rounded bg-muted">
              <div
                className={cn(meta.barra, activo && "brightness-110")}
                style={{ width: `${(f.tokens / maximo) * 100}%` }}
                title={`${numeroCompleto(f.tokens)} tokens`}
              />
            </div>
            <span className="w-28 shrink-0 text-right tabular-nums text-muted-foreground">
              {numeroCompacto(f.tokens)} · {costeUsd(f.coste_usd)}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Economía de UN motor (desglose separado): totales + serie de 7 días + por tipo + por día.
 *  GLOBAL (ledger `gasto_ia`): la misma fuente para todo, así cuadra. Mismo layout y alturas
 *  mínimas para ambos motores, de modo que las dos columnas alinean aunque uno tenga menos datos. */
function EconomiaMotor({
  motor,
  bloque,
  cargando,
}: {
  motor: Proceso;
  bloque: EconomiaProcesoBloque | undefined;
  cargando: boolean;
}) {
  const meta = PROC_META[motor];
  const porDia = bloque?.por_dia ?? [];
  // Día seleccionado en la serie: reenfoca los KPIs a ese día (null = total del periodo).
  const [diaSel, setDiaSel] = React.useState<string | null>(null);
  const toggleDia = (dia: string) => setDiaSel((prev) => (prev === dia ? null : dia));

  // KPIs: el día elegido (de la serie) o el total del periodo.
  const delDia = diaSel ? porDia.find((f) => f.dia === diaSel) : undefined;
  const items = delDia?.items ?? bloque?.total.items ?? 0;
  const tokens = delDia?.tokens ?? bloque?.total.tokens ?? 0;
  const coste = delDia?.coste_usd ?? bloque?.total.coste_usd ?? 0;
  const ambito = diaSel ? formatearDia(diaSel) : `últimos ${DIAS} días`;

  return (
    <section className="space-y-3">
      <h2 className={cn("flex items-center gap-2 text-lg font-semibold", meta.texto)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        {meta.etiqueta}
      </h2>
      {cargando ? (
        <Skeleton className="h-24 w-full rounded-xl" />
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            Mostrando: <span className="font-medium text-foreground">{ambito}</span>
          </p>
          <div className="grid grid-cols-3 gap-3">
            <TarjetaKpi variante="card" etiqueta="Trabajos IA" valor={numeroCompleto(items)} />
            <TarjetaKpi
              variante="card"
              etiqueta="Tokens"
              valor={numeroCompacto(tokens)}
              titulo={numeroCompleto(tokens)}
            />
            <TarjetaKpi variante="card" etiqueta="Coste" valor={costeUsd(coste)} />
          </div>
        </>
      )}
      <Card>
        <CardHeader className="p-4 pb-2">
          <CardTitle className="flex items-center gap-2 text-sm">
            <RotateCcw className="h-4 w-4 text-muted-foreground" />
            Últimos {DIAS} días
          </CardTitle>
        </CardHeader>
        <CardContent className="min-h-[15rem] p-4 pt-2">
          {cargando ? (
            <Skeleton className="h-32 w-full" />
          ) : porDia.length === 0 ? (
            <LineaVacia texto="Sin actividad en la ventana" />
          ) : (
            <SerieEconomia
              motor={motor}
              filas={porDia}
              diaSel={diaSel}
              onToggle={toggleDia}
            />
          )}
        </CardContent>
      </Card>
      <DesglosePorTipo filas={bloque?.por_tipo ?? []} />
      <DesglosePorDia filas={porDia} />
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

  // Presupuesto (global) + parada de emergencia: la cola trae el presupuesto.
  const cola = useQuery({
    queryKey: ["actividad", "cola", marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.cola({ marca: marcaActiva ?? undefined }, signal),
    refetchInterval: INTERVALO_VIVO_MS,
  });
  // Economía por motor (ledger gasto_ia): totales + serie + desgloses que cuadran. Respeta el
  // switch de marca: marca activa acota el desglose; "todas" muestra el AGREGADO global.
  const economia = useQuery({
    queryKey: ["actividad", "economia", DIAS, marcaActiva ?? "todas"],
    queryFn: ({ signal }) => api.economia({ dias: DIAS, marca: marcaActiva ?? undefined }, signal),
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

      {/* Economía por motor (desglose separado, GLOBAL). */}
      <div
        className={cn("grid grid-cols-1 gap-8", motores.length > 1 && "xl:grid-cols-2 xl:gap-6")}
      >
        {motores.map((m) => (
          <EconomiaMotor
            key={m}
            motor={m}
            bloque={economia.data?.por_proceso?.[m]}
            cargando={economia.isPending}
          />
        ))}
      </div>
    </>
  );
}
