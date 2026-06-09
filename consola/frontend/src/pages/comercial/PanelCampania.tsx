/**
 * Dashboard de UNA campaña en un periodo: KPIs con comparativa (incluido el nº de
 * publicaciones), tendencia diaria, desglose por red y la tabla de piezas del periodo
 * —filtrable por red/formato y ordenable por cualquier columna—. Es la vista de
 * seguimiento de una campaña por hashtag para analizar su rendimiento comercial.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ExternalLink } from "lucide-react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import {
  nombreFormato,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  variacion,
} from "@/lib/formato";
import type { ComparativaKpi, DesgloseRedCampania, PiezaCampania } from "@/types";

import { CabeceraOrdenable } from "@/pages/metricas/CabeceraOrdenable";
import { useOrdenTabla } from "@/pages/metricas/useOrdenTabla";
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
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

  const { kpis, comparativa, tendencia, desglose_red, piezas } = consulta.data;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <TarjetaKpiComparada
          etiqueta="Publicaciones"
          valor={numeroCompleto(kpis.piezas)}
          comp={comparativa.piezas}
        />
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

      <DesgloseRedTabla filas={desglose_red} />

      <TablaPiezas piezas={piezas} />
    </div>
  );
}

type ClaveOrdenRed =
  | "piezas"
  | "visualizaciones"
  | "interacciones"
  | "likes"
  | "comentarios"
  | "compartidos"
  | "guardados"
  | "engagement_pct";

/** Tabla de agregados por red: dónde y cómo rinde la campaña (ordenable por columna). */
function DesgloseRedTabla({ filas }: { filas: DesgloseRedCampania[] }) {
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<DesgloseRedCampania, ClaveOrdenRed>(
    filas,
    {
      piezas: (f) => f.piezas,
      visualizaciones: (f) => f.visualizaciones,
      interacciones: (f) => f.interacciones,
      likes: (f) => f.likes,
      comentarios: (f) => f.comentarios,
      compartidos: (f) => f.compartidos,
      guardados: (f) => f.guardados,
      engagement_pct: (f) => f.engagement_pct,
    },
    { clave: "visualizaciones", direccion: "desc" },
  );

  const col = (clave: ClaveOrdenRed, etiqueta: string, className?: string) => (
    <CabeceraOrdenable
      activa={estado.clave === clave}
      direccion={estado.direccion}
      onClick={() => alClicar(clave)}
      alinear="right"
      className={className}
    >
      {etiqueta}
    </CabeceraOrdenable>
  );

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-6 py-4">
          <h3 className="text-sm font-medium">Desglose por red</h3>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Red</TableHead>
              {col("piezas", "Publicaciones")}
              {col("visualizaciones", "Visualizaciones")}
              {col("interacciones", "Interacciones")}
              {col("likes", "Likes")}
              {col("comentarios", "Comentarios")}
              {col("compartidos", "Compartidos")}
              {col("guardados", "Guardados")}
              {col("engagement_pct", "Engagement", "pr-6")}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                  Sin datos por red en el periodo.
                </TableCell>
              </TableRow>
            ) : (
              filasOrdenadas.map((f) => (
                <TableRow key={f.red || "—"}>
                  <TableCell className="pl-6">
                    <Badge variant="outline">{nombreRed(f.red)}</Badge>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{numeroCompleto(f.piezas)}</TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.visualizaciones)}>
                    {numeroCompacto(f.visualizaciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" title={numeroCompleto(f.interacciones)}>
                    {numeroCompacto(f.interacciones)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{numeroCompacto(f.likes)}</TableCell>
                  <TableCell className="text-right tabular-nums">{numeroCompacto(f.comentarios)}</TableCell>
                  <TableCell className="text-right tabular-nums">{numeroCompacto(f.compartidos)}</TableCell>
                  <TableCell className="text-right tabular-nums">{numeroCompacto(f.guardados)}</TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">{porcentaje(f.engagement_pct)}</TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

const TODAS = "__todas__";
type ClaveOrdenPieza = "publicado" | "visualizaciones" | "interacciones" | "engagement_pct";

/** Tabla de piezas del periodo: filtrable por red/formato y ordenable por columna. */
function TablaPiezas({ piezas }: { piezas: PiezaCampania[] }) {
  const [red, setRed] = React.useState<string>(TODAS);
  const [formato, setFormato] = React.useState<string>(TODAS);

  // Opciones de filtro derivadas de las piezas presentes (ordenadas, sin vacíos).
  const redes = React.useMemo(
    () => [...new Set(piezas.map((p) => p.red).filter(Boolean))].sort(),
    [piezas],
  );
  const formatos = React.useMemo(
    () => [...new Set(piezas.map((p) => p.formato).filter(Boolean))].sort(),
    [piezas],
  );

  const filtradas = React.useMemo(
    () =>
      piezas.filter(
        (p) => (red === TODAS || p.red === red) && (formato === TODAS || p.formato === formato),
      ),
    [piezas, red, formato],
  );

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaCampania, ClaveOrdenPieza>(
    filtradas,
    {
      publicado: (p) => p.publicado,
      visualizaciones: (p) => p.visualizaciones,
      interacciones: (p) => p.interacciones,
      engagement_pct: (p) => p.engagement_pct,
    },
    { clave: "visualizaciones", direccion: "desc" },
  );

  const crossCount = React.useMemo(() => piezas.filter((p) => p.por_cross_post).length, [piezas]);

  const col = (clave: ClaveOrdenPieza, etiqueta: string, className?: string) => (
    <CabeceraOrdenable
      activa={estado.clave === clave}
      direccion={estado.direccion}
      onClick={() => alClicar(clave)}
      alinear="right"
      className={className}
    >
      {etiqueta}
    </CabeceraOrdenable>
  );

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div className="space-y-0.5">
            <h3 className="text-sm font-medium">Piezas del periodo</h3>
            {crossCount > 0 && (
              <p className="text-xs text-muted-foreground">
                Incluye {crossCount} por cross-post (mismo contenido en otra red, sin el hashtag).
              </p>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={red} onValueChange={setRed}>
              <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Filtrar por red">
                <SelectValue placeholder="Red" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todas las redes</SelectItem>
                {redes.map((r) => (
                  <SelectItem key={r} value={r}>
                    {nombreRed(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={formato} onValueChange={setFormato}>
              <SelectTrigger className="h-8 w-[150px] text-xs" aria-label="Filtrar por formato">
                <SelectValue placeholder="Formato" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={TODAS}>Todos los formatos</SelectItem>
                {formatos.map((f) => (
                  <SelectItem key={f} value={f}>
                    {nombreFormato(f)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground tabular-nums">
              {filtradas.length} de {piezas.length}
            </span>
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Publicación</TableHead>
              <TableHead>Red</TableHead>
              <TableHead>Formato</TableHead>
              {col("publicado", "Fecha")}
              {col("visualizaciones", "Visualizaciones")}
              {col("interacciones", "Interacciones")}
              {col("engagement_pct", "Engagement", "pr-6")}
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtradas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                  {piezas.length === 0
                    ? "No hay piezas con estos hashtags en el periodo."
                    : "Ninguna pieza coincide con los filtros."}
                </TableCell>
              </TableRow>
            ) : (
              filasOrdenadas.map((p) => (
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
                      {p.por_cross_post && (
                        <Badge
                          variant="secondary"
                          className="shrink-0 text-[10px]"
                          title="Incluida por cross-post: mismo contenido en otra red, sin el hashtag propio"
                        >
                          cross-post
                        </Badge>
                      )}
                    </span>
                  </TableCell>
                  <TableCell>
                    {p.red ? (
                      <Badge variant="outline">{nombreRed(p.red)}</Badge>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{nombreFormato(p.formato)}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {fechaCorta(p.publicado)}
                  </TableCell>
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
