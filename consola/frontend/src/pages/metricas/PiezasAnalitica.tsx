/**
 * Analítica de piezas/videos del periodo, con un tab por marca (+ "Todas").
 *
 * Cada tab muestra, en una sola tarjeta y sin saturar:
 *   1. Tira de estadísticas de engagement: media, mediana, rango p25–p75 y pico.
 *   2. Top 5 y Peores 5 piezas (tabla compacta: título·plataforma·vistas·engagement).
 *   3. Distribución de engagement (mini-histograma): detecta si pocas piezas concentran
 *      el resultado.
 *
 * Coste 0 de API: el backend lo arma sobre las piezas que ya descarga del periodo. Los
 * tabs son perezosos (Radix desmonta el inactivo), así que solo el tab visible consulta.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { BarChart3, ExternalLink } from "lucide-react";
import * as React from "react";

import { BadgeFuente } from "@/components/comunes/BadgeFuente";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type { EstadisticasNumericas, OpcionesMetricas, PiezaMetrica } from "@/types";

const TAB_TODAS = "todas";

/** Porcentaje tolerante a null ("—" si no hay dato). */
function pct(v: number | null): string {
  return v == null ? "—" : porcentaje(v);
}

export function PiezasAnalitica({
  opciones,
  rangoActual,
}: {
  opciones: OpcionesMetricas;
  rangoActual?: string;
}) {
  const [tab, setTab] = React.useState(TAB_TODAS);

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Piezas del periodo</CardTitle>
        </div>
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value={TAB_TODAS}>Todas</TabsTrigger>
            {opciones.marcas.map((m) => (
              <TabsTrigger key={m.id} value={m.id}>
                {m.nombre}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value={TAB_TODAS}>
            <ContenidoPiezas marca={undefined} rango={rangoActual} />
          </TabsContent>
          {opciones.marcas.map((m) => (
            <TabsContent key={m.id} value={m.id}>
              <ContenidoPiezas marca={m.id} rango={rangoActual} />
            </TabsContent>
          ))}
        </Tabs>
      </CardHeader>
    </Card>
  );
}

function ContenidoPiezas({ marca, rango }: { marca?: string; rango?: string }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas", rango ?? "", marca ?? "todas"],
    queryFn: ({ signal }) => api.metricasPiezas({ rango, marca }, signal),
    enabled: Boolean(rango),
    staleTime: 5 * 60_000,
  });

  if (isPending) return <Skeleton className="mt-2 h-72 w-full rounded-lg" />;
  if (isError) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        No se pudo cargar la analítica de piezas.
      </p>
    );
  }
  if (data.total === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Sin piezas en este periodo.
      </p>
    );
  }

  return (
    <CardContent className="space-y-6 px-0 pb-0">
      <TiraEstadisticas
        engagement={data.engagement}
        visualizaciones={data.visualizaciones}
        total={data.total}
        fuente={data.fuente}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TablaPiezas titulo="Top 5" piezas={data.top} />
        <TablaPiezas titulo="Peores 5" piezas={data.peores} />
      </div>

      <Distribucion buckets={data.distribucion} />
    </CardContent>
  );
}

function TiraEstadisticas({
  engagement,
  visualizaciones,
  total,
  fuente,
}: {
  engagement: EstadisticasNumericas;
  visualizaciones: EstadisticasNumericas;
  total: number;
  fuente: string;
}) {
  return (
    <div className="space-y-3">
      <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>
          <span className="font-medium text-foreground tabular-nums">{total}</span> piezas
        </span>
        <span>·</span>
        <span>
          vistas media{" "}
          <span className="font-medium text-foreground tabular-nums">
            {visualizaciones.media == null ? "—" : numeroCompacto(visualizaciones.media)}
          </span>
        </span>
        <BadgeFuente fuente={fuente} className="ml-1" />
      </p>
      {/* Estadísticas de engagement: el indicador comparable entre piezas (#138). */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <TarjetaKpi etiqueta="Engagement medio" valor={pct(engagement.media)} />
        <TarjetaKpi etiqueta="Mediana" valor={pct(engagement.mediana)} />
        <TarjetaKpi etiqueta="Rango p25–p75" valor={`${pct(engagement.p25)} – ${pct(engagement.p75)}`} />
        <TarjetaKpi etiqueta="Pico" valor={pct(engagement.maximo)} />
      </div>
    </div>
  );
}

function TablaPiezas({ titulo, piezas }: { titulo: string; piezas: PiezaMetrica[] }) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">{titulo}</h4>
      {piezas.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
          No hay suficientes piezas para destacar peores.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pieza</TableHead>
              <TableHead className="text-right">Vistas</TableHead>
              <TableHead className="text-right">Eng.</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {piezas.map((p) => (
              <TableRow key={`${p.plataforma}-${p.id}`}>
                <TableCell className="max-w-[16rem]">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate" title={p.titulo}>
                      {p.titulo}
                    </span>
                    {p.url && (
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        aria-label="Abrir pieza"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                      </a>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">{p.plataforma}</span>
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {numeroCompacto(p.visualizaciones)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{porcentaje(p.engagement_pct)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function Distribucion({ buckets }: { buckets: { etiqueta: string; n: number }[] }) {
  const datos = buckets.map((b) => ({ tramo: b.etiqueta, Piezas: b.n }));
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-semibold">Distribución de engagement</h4>
      <BarChart
        data={datos}
        index="tramo"
        categories={["Piezas"]}
        colors={["sky"]}
        valueFormatter={(v) => String(v)}
        showLegend={false}
        showAnimation
        className="h-40"
      />
    </div>
  );
}
