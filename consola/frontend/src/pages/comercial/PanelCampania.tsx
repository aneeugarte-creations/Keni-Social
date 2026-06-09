/**
 * Dashboard de UNA campaña en un periodo: KPIs con comparativa, tendencia diaria y la
 * tabla de piezas del periodo. Es la vista de seguimiento de una campaña por hashtag,
 * un símil simplificado del dashboard de Métricas acotado a 5-10 piezas/mes.
 */
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ExternalLink } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { numeroCompacto, numeroCompleto, porcentaje, variacion } from "@/lib/formato";
import type { ComparativaKpi, PiezaCampania } from "@/types";

import { CLAVE_COMERCIAL } from "./claves";
import { GraficaTendencia } from "./GraficaTendencia";
import { fechaCorta } from "./formato";

/** Tarjeta KPI con su variación vs. el periodo anterior (flecha + color). */
function TarjetaKpiComparada({
  etiqueta,
  valor,
  titulo,
  comp,
}: {
  etiqueta: string;
  valor: string;
  titulo?: string;
  comp: ComparativaKpi;
}) {
  const v = comp.variacion_pct;
  const sube = v != null && v > 0;
  const baja = v != null && v < 0;
  const Icono = sube ? ArrowUpRight : baja ? ArrowDownRight : ArrowRight;
  return (
    <Card>
      <CardContent className="space-y-1.5 p-5">
        <p className="text-sm text-muted-foreground">{etiqueta}</p>
        <p
          className="truncate text-2xl font-semibold tracking-tight tabular-nums"
          title={titulo ?? valor}
        >
          {valor}
        </p>
        <div
          className={cn(
            "flex items-center gap-1 text-xs tabular-nums",
            sube && "text-emerald-600 dark:text-emerald-400",
            baja && "text-rose-600 dark:text-rose-400",
            !sube && !baja && "text-muted-foreground",
          )}
        >
          <Icono className="h-3.5 w-3.5 shrink-0" />
          <span>{v == null ? "—" : variacion(v)}</span>
          <span className="text-muted-foreground">vs. periodo anterior</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function PanelCampania({ campaniaId, rango }: { campaniaId: string; rango: string }) {
  const consulta = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "analitica", campaniaId, rango],
    queryFn: ({ signal }) => api.analiticaCampania(campaniaId, { rango }, signal),
  });

  if (consulta.isPending) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    );
  }
  if (consulta.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la analítica de la campaña"
        mensaje={consulta.error instanceof Error ? consulta.error.message : undefined}
        onReintentar={() => void consulta.refetch()}
        cargando={consulta.isFetching}
      />
    );
  }

  const { kpis, comparativa, tendencia, piezas } = consulta.data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <TarjetaKpiComparada
          etiqueta="Visualizaciones"
          valor={numeroCompacto(kpis.visualizaciones)}
          titulo={numeroCompleto(kpis.visualizaciones)}
          comp={comparativa.visualizaciones}
        />
        <TarjetaKpiComparada
          etiqueta="Interacciones"
          valor={numeroCompacto(kpis.interacciones)}
          titulo={numeroCompleto(kpis.interacciones)}
          comp={comparativa.interacciones}
        />
        <TarjetaKpiComparada
          etiqueta="Engagement"
          valor={porcentaje(kpis.engagement_pct)}
          comp={comparativa.engagement_pct}
        />
      </div>

      <GraficaTendencia puntos={tendencia.puntos} />

      <TablaPiezas piezas={piezas} />
    </div>
  );
}

function TablaPiezas({ piezas }: { piezas: PiezaCampania[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-6 py-4">
          <h3 className="text-sm font-medium">Piezas del periodo</h3>
          <span className="text-xs text-muted-foreground tabular-nums">
            {piezas.length} {piezas.length === 1 ? "pieza" : "piezas"}
          </span>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Publicación</TableHead>
              <TableHead>Red</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead className="text-right">Visualizaciones</TableHead>
              <TableHead className="text-right">Interacciones</TableHead>
              <TableHead className="pr-6 text-right">Engagement</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {piezas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  No hay piezas con estos hashtags en el periodo.
                </TableCell>
              </TableRow>
            ) : (
              piezas.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="pl-6">
                    <span className="flex max-w-[22rem] items-center gap-1.5">
                      <span className="truncate font-medium" title={p.titulo || "Publicación"}>
                        {p.titulo || "Publicación"}
                      </span>
                      {p.url && (
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 text-muted-foreground hover:text-foreground"
                          aria-label="Abrir publicación"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      )}
                    </span>
                  </TableCell>
                  <TableCell>
                    {p.red ? (
                      <Badge variant="outline" className="capitalize">
                        {p.red}
                      </Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{fechaCorta(p.publicado)}</TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(p.visualizaciones)}>
                    {numeroCompacto(p.visualizaciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(p.interacciones)}>
                    {numeroCompacto(p.interacciones)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {porcentaje(p.engagement_pct)}
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
