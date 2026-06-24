/**
 * Dashboard de UNA campaña en un periodo: KPIs con comparativa (incluido el nº de
 * piezas), tendencia diaria, desglose por red y la tabla de piezas del periodo
 * —filtrable por red/formato y ordenable por cualquier columna—. Es la vista de
 * seguimiento de una campaña por hashtag para analizar su rendimiento.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, ExternalLink, Globe, Megaphone } from "lucide-react";

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
  FORMATOS_CANONICOS,
  formatoCanonico,
  nombreFormato,
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  porcentaje,
  REDES_CANONICAS,
  redCanonica,
  variacion,
} from "@/lib/formato";
import type {
  AnaliticaCampania,
  ComparativaKpi,
  DesgloseRedCampania,
  PiezaCampania,
  SeccionWebCampania,
} from "@/types";

import { Bloque } from "@/pages/metricas/Bloque";
import { CabeceraOrdenable } from "@/pages/metricas/CabeceraOrdenable";
import type { ColumnaMeta } from "@/pages/metricas/columnasMeta";
import { Seccion } from "@/pages/metricas/Seccion";
import { useOrdenTabla } from "@/pages/metricas/useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "@/pages/metricas/vistaConfig";
import { CLAVE_CAMPANIAS } from "./claves";
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
        </div>
      </CardContent>
    </Card>
  );
}

/** Tarjeta KPI simple, sin comparativa (para métricas que solo una red mide). */
function TarjetaKpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
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
      </CardContent>
    </Card>
  );
}

export function PanelCampania({
  campaniaId,
  rango,
  ocultarAds = false,
  datos: datosProp,
}: {
  campaniaId?: string;
  rango?: string;
  /** Modo cliente: oculta TODO lo de Ads y suma las visualizaciones pagadas a las orgánicas
   * (el cliente no debe ver que se usó pauta). */
  ocultarAds?: boolean;
  /** Analítica ya cargada (p. ej. la vista pública por token): si viene, no se vuelve a pedir
   * ni se monta la query; el panel solo la pinta. */
  datos?: AnaliticaCampania;
}) {
  const consulta = useQuery({
    queryKey: [...CLAVE_CAMPANIAS, "analitica", campaniaId, rango],
    queryFn: ({ signal }) => api.analiticaCampania(campaniaId ?? "", { rango }, signal),
    enabled: datosProp === undefined,
  });

  if (datosProp === undefined && consulta.isPending) {
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
  if (datosProp === undefined && consulta.isError) {
    return (
      <BloqueError
        titulo="No se pudo cargar la analítica de la campaña"
        mensaje={consulta.error instanceof Error ? consulta.error.message : undefined}
        onReintentar={() => void consulta.refetch()}
        cargando={consulta.isFetching}
      />
    );
  }

  const datos = datosProp ?? consulta.data;
  if (!datos) return null;
  const { kpis, comparativa, tendencia, desglose_red, inorganico, piezas, web } = datos;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <TarjetaKpiComparada
          etiqueta="Piezas"
          valor={numeroCompleto(kpis.piezas)}
          comp={comparativa.piezas}
        />
        <TarjetaKpiComparada
          etiqueta={ocultarAds ? "Vistas" : "Vistas (orgánicas)"}
          valor={numeroCompacto(kpis.visualizaciones + (ocultarAds ? inorganico.visualizaciones : 0))}
          titulo={numeroCompleto(kpis.visualizaciones + (ocultarAds ? inorganico.visualizaciones : 0))}
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
        <TarjetaKpi
          etiqueta="Alcance"
          valor={kpis.alcance == null ? "n/d" : numeroCompacto(kpis.alcance)}
          titulo={kpis.alcance == null ? "Ninguna red mide el alcance" : numeroCompleto(kpis.alcance)}
        />
      </div>

      {!ocultarAds && <BloqueInorganico inorganico={inorganico} />}

      {web && web.piezas > 0 && <BloqueWeb web={web} />}

      <Bloque id="campania-tendencia" titulo="Tendencia de la campaña">
        <Seccion id="campania-tendencia" titulo="Tendencia de la campaña">
          <GraficaTendencia puntos={tendencia.puntos} />
        </Seccion>
      </Bloque>

      <DesgloseRedTabla filas={desglose_red} />

      <TablaPiezas piezas={piezas} ocultarAds={ocultarAds} />
    </div>
  );
}

/** Resumen INORGÁNICO (Meta Ads): visualizaciones pagadas + gasto + nº de campañas.
 * Solo se muestra si hubo inversión; deja claro que es lo PAGADO, no lo orgánico. */
function BloqueInorganico({ inorganico }: { inorganico: AnaliticaCampania["inorganico"] }) {
  if (!inorganico || inorganico.visualizaciones <= 0) return null;
  const gasto = inorganico.gasto.toLocaleString("es-MX", { maximumFractionDigits: 0 });
  return (
    <Card className="border-amber-300/60 bg-amber-50/40 dark:border-amber-500/30 dark:bg-amber-500/5">
      <CardContent className="flex flex-wrap items-center gap-x-8 gap-y-2 p-5">
        <div className="flex items-center gap-2">
          <Megaphone className="h-4 w-4 text-amber-600 dark:text-amber-400" />
          <span className="text-sm font-medium">Inorgánico (Meta Ads)</span>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground">Vistas pagadas</p>
          <p className="text-xl font-semibold tabular-nums" title={numeroCompleto(inorganico.visualizaciones)}>
            {numeroCompacto(inorganico.visualizaciones)}
          </p>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground">Gasto</p>
          <p className="text-xl font-semibold tabular-nums">
            {gasto} {inorganico.moneda}
          </p>
        </div>
        <div className="space-y-0.5">
          <p className="text-xs text-muted-foreground">Campañas</p>
          <p className="text-xl font-semibold tabular-nums">{inorganico.campanias}</p>
        </div>
      </CardContent>
    </Card>
  );
}

/** Tráfico WEB (GA4) de la campaña: notas del sitio que cruzan con su etiqueta. Es tráfico de
 * la PÁGINA, no de redes: los pageviews van aparte y nunca se suman a las vistas sociales. */
function BloqueWeb({ web }: { web: SeccionWebCampania }) {
  const notas = [...web.notas].sort((a, b) => b.paginas_vistas - a.paginas_vistas);
  return (
    <Bloque id="campania-web" titulo="Tráfico web (GA4)">
      <Seccion
        id="campania-web"
        titulo="Tráfico web (GA4)"
        descripcion="Visitas a las notas del sitio por la etiqueta de la campaña. No son vistas de redes."
      >
        <Card className="border-sky-300/60 bg-sky-50/40 dark:border-sky-500/30 dark:bg-sky-500/5">
          <CardContent className="space-y-4 p-5">
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
              <div className="flex items-center gap-2">
                <Globe className="h-4 w-4 text-sky-600 dark:text-sky-400" />
                <span className="text-sm font-medium">Tráfico web</span>
                {web.etiqueta && (
                  <Badge variant="outline" className="font-normal">
                    {web.etiqueta}
                  </Badge>
                )}
              </div>
              <div className="space-y-0.5">
                <p className="text-xs text-muted-foreground">Notas</p>
                <p className="text-xl font-semibold tabular-nums">{numeroCompleto(web.piezas)}</p>
              </div>
              <div className="space-y-0.5">
                <p className="text-xs text-muted-foreground">Páginas vistas</p>
                <p className="text-xl font-semibold tabular-nums" title={numeroCompleto(web.paginas_vistas)}>
                  {numeroCompacto(web.paginas_vistas)}
                </p>
              </div>
              <div className="space-y-0.5">
                <p className="text-xs text-muted-foreground">Navegadores únicos</p>
                <p
                  className="text-xl font-semibold tabular-nums"
                  title={numeroCompleto(web.navegadores_unicos)}
                >
                  {numeroCompacto(web.navegadores_unicos)}
                </p>
              </div>
              <div className="space-y-0.5">
                <p className="text-xs text-muted-foreground">Visitas</p>
                <p className="text-xl font-semibold tabular-nums" title={numeroCompleto(web.visitas)}>
                  {numeroCompacto(web.visitas)}
                </p>
              </div>
              <div className="space-y-0.5">
                <p className="text-xs text-muted-foreground">Inicios de video</p>
                <p
                  className="text-xl font-semibold tabular-nums"
                  title={numeroCompleto(web.inicios_video)}
                >
                  {numeroCompacto(web.inicios_video)}
                </p>
              </div>
            </div>

            {notas.length > 0 && (
              <div className="overflow-hidden rounded-lg border border-border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="pl-4">Nota</TableHead>
                      <TableHead>Marca</TableHead>
                      <TableHead className="text-right">Páginas vistas</TableHead>
                      <TableHead className="text-right">Navegadores únicos</TableHead>
                      <TableHead className="pr-4 text-right">Visitas</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {notas.map((n) => (
                      <TableRow key={n.url || n.titulo}>
                        <TableCell className="pl-4">
                          <span className="flex max-w-[24rem] items-center gap-1.5">
                            <span className="truncate font-medium" title={n.titulo || n.url}>
                              {n.titulo || n.url || "Nota"}
                            </span>
                            {n.url && (
                              <a
                                href={n.url}
                                target="_blank"
                                rel="noreferrer"
                                className="shrink-0 text-muted-foreground hover:text-foreground"
                                aria-label="Abrir nota"
                              >
                                <ExternalLink className="h-3.5 w-3.5" />
                              </a>
                            )}
                          </span>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {n.marca || <span className="text-muted-foreground">—</span>}
                        </TableCell>
                        <TableCell
                          className="text-right tabular-nums"
                          title={numeroCompleto(n.paginas_vistas)}
                        >
                          {numeroCompacto(n.paginas_vistas)}
                        </TableCell>
                        <TableCell
                          className="text-right tabular-nums"
                          title={numeroCompleto(n.navegadores_unicos)}
                        >
                          {numeroCompacto(n.navegadores_unicos)}
                        </TableCell>
                        <TableCell
                          className="pr-4 text-right tabular-nums"
                          title={numeroCompleto(n.visitas)}
                        >
                          {numeroCompacto(n.visitas)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </Seccion>
    </Bloque>
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

// Identidad estable: es dependencia del `useMemo` de `useOrdenTabla` (un literal inline lo anularía).
const ACCESORES_RED: Record<ClaveOrdenRed, (f: DesgloseRedCampania) => number> = {
  piezas: (f) => f.piezas,
  visualizaciones: (f) => f.visualizaciones,
  interacciones: (f) => f.interacciones,
  likes: (f) => f.likes,
  comentarios: (f) => f.comentarios,
  compartidos: (f) => f.compartidos,
  guardados: (f) => f.guardados,
  engagement_pct: (f) => f.engagement_pct,
};

/** Columnas configurables del desglose por red (orden base). La primera, "red", es la dimensión. */
const COLS_RED: ColumnaMeta[] = [
  { id: "red", etiqueta: "Red" },
  { id: "piezas", etiqueta: "Piezas" },
  { id: "visualizaciones", etiqueta: "Vistas" },
  { id: "interacciones", etiqueta: "Interacciones" },
  { id: "likes", etiqueta: "Me gusta" },
  { id: "comentarios", etiqueta: "Comentarios" },
  { id: "compartidos", etiqueta: "Compartidos" },
  { id: "guardados", etiqueta: "Guardados" },
  { id: "engagement_pct", etiqueta: "Engagement" },
];
const IDS_RED = COLS_RED.map((c) => c.id);

/** Valor formateado de una celda numérica del desglose por red. */
function valorCeldaRed(f: DesgloseRedCampania, clave: ClaveOrdenRed): string {
  if (clave === "engagement_pct") return porcentaje(f.engagement_pct);
  if (clave === "piezas") return numeroCompleto(f.piezas);
  return numeroCompacto(f[clave]);
}

/** Tabla de agregados por red: dónde y cómo rinde la campaña (ordenable por columna). */
function DesgloseRedTabla({ filas }: { filas: DesgloseRedCampania[] }) {
  const cfg = useVistaConfig((s) => s.columnas["campania-red"]) ?? { orden: IDS_RED, ocultas: [] };
  const columnas = columnasVisibles(IDS_RED, cfg);

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<DesgloseRedCampania, ClaveOrdenRed>(
    filas,
    ACCESORES_RED,
    { clave: "visualizaciones", direccion: "desc" },
  );

  const etiquetaDe = (id: string) => COLS_RED.find((c) => c.id === id)?.etiqueta ?? id;

  const encabezado = (id: string, idx: number) => {
    const ultima = idx === columnas.length - 1;
    if (id === "red") {
      return (
        <TableHead key={id} className="pl-6">
          Red
        </TableHead>
      );
    }
    const clave = id as ClaveOrdenRed;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear="right"
        className={ultima ? "pr-6" : undefined}
      >
        {etiquetaDe(id)}
      </CabeceraOrdenable>
    );
  };

  const celda = (f: DesgloseRedCampania, id: string, idx: number) => {
    const ultima = idx === columnas.length - 1;
    if (id === "red") {
      return (
        <TableCell key={id} className="pl-6">
          <Badge variant="outline">{nombreRed(f.red)}</Badge>
        </TableCell>
      );
    }
    const clave = id as ClaveOrdenRed;
    const conTitulo = clave === "visualizaciones" || clave === "interacciones";
    return (
      <TableCell
        key={id}
        className={cn("text-right tabular-nums", ultima && "pr-6")}
        title={conTitulo ? numeroCompleto(f[clave]) : undefined}
      >
        {valorCeldaRed(f, clave)}
      </TableCell>
    );
  };

  return (
    <Bloque id="campania-red" titulo="Desglose por red">
      <Seccion
        id="campania-red"
        titulo="Desglose por red"
        tablaId="campania-red"
        columnas={COLS_RED}
      >
        <Card className="overflow-hidden py-2">
          <Table>
            <TableHeader>
              <TableRow>{columnas.map((id, idx) => encabezado(id, idx))}</TableRow>
            </TableHeader>
            <TableBody>
              {filas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columnas.length} className="py-8 text-center text-muted-foreground">
                    Sin datos por red en el periodo.
                  </TableCell>
                </TableRow>
              ) : (
                filasOrdenadas.map((f) => (
                  <TableRow key={f.red || "—"}>{columnas.map((id, idx) => celda(f, id, idx))}</TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>
      </Seccion>
    </Bloque>
  );
}

const TODAS = "__todas__";
type ClaveOrdenPieza =
  | "titulo"
  | "red"
  | "marca"
  | "formato"
  | "publicado"
  | "visualizaciones"
  | "visualizaciones_pagadas"
  | "interacciones"
  | "engagement_pct";

/** Columnas configurables de la tabla de piezas (orden base). "Ads" es exclusiva del modo
 * con Ads visibles: se excluye de la base cuando `ocultarAds`, así ni se ofrece ni se pinta. */
const COLS_PIEZAS: ColumnaMeta[] = [
  { id: "titulo", etiqueta: "Publicación" },
  { id: "red", etiqueta: "Red" },
  { id: "marca", etiqueta: "Marca" },
  { id: "formato", etiqueta: "Formato" },
  { id: "publicado", etiqueta: "Fecha" },
  { id: "visualizaciones", etiqueta: "Vistas" },
  { id: "visualizaciones_pagadas", etiqueta: "Ads" },
  { id: "interacciones", etiqueta: "Interacciones" },
  { id: "engagement_pct", etiqueta: "Engagement" },
];

/** Alineación de cada columna de la tabla de piezas (la dimensión textual va a la izquierda). */
const ALINEAR_PIEZA: Record<string, "left" | "right"> = {
  titulo: "left",
  red: "left",
  marca: "left",
  formato: "left",
  publicado: "right",
  visualizaciones: "right",
  visualizaciones_pagadas: "right",
  interacciones: "right",
  engagement_pct: "right",
};

/** Visualizaciones a MOSTRAR de una pieza: en modo cliente (ocultarAds) se suman las pagadas
 * a las orgánicas para que el inorgánico se vea como un post normal. */
function visEfectivas(p: PiezaCampania, ocultarAds: boolean): number {
  return p.visualizaciones + (ocultarAds ? p.visualizaciones_pagadas : 0);
}

/** Tabla de piezas del periodo: filtrable por red/formato y ordenable por columna. */
function TablaPiezas({ piezas, ocultarAds }: { piezas: PiezaCampania[]; ocultarAds: boolean }) {
  const [red, setRed] = React.useState<string>(TODAS);
  const [formato, setFormato] = React.useState<string>(TODAS);

  // Redes canónicas presentes en las piezas, en orden canónico (las desconocidas al final).
  const redes = React.useMemo(() => {
    const presentes = new Set(piezas.map((p) => redCanonica(p.red)).filter(Boolean));
    const conocidas = REDES_CANONICAS.filter((r) => presentes.has(r));
    const otras = [...presentes]
      .filter((r) => !(REDES_CANONICAS as readonly string[]).includes(r))
      .sort();
    return [...conocidas, ...otras];
  }, [piezas]);

  // Formatos canónicos presentes (colapsando feed_reel/reel… en uno), restringidos a la red
  // elegida: así el selector de formato depende de la red, como en métricas.
  const formatos = React.useMemo(() => {
    const relevantes = red === TODAS ? piezas : piezas.filter((p) => redCanonica(p.red) === red);
    const presentes = new Set(relevantes.map((p) => formatoCanonico(p.formato)).filter(Boolean));
    const conocidos = FORMATOS_CANONICOS.filter((f) => presentes.has(f));
    const otros = [...presentes]
      .filter((f) => !(FORMATOS_CANONICOS as readonly string[]).includes(f))
      .sort();
    return [...conocidos, ...otros];
  }, [piezas, red]);

  // Si el formato seleccionado deja de estar disponible al cambiar de red, vuelve a "todos".
  React.useEffect(() => {
    if (formato !== TODAS && !formatos.includes(formato)) setFormato(TODAS);
  }, [formatos, formato]);

  const filtradas = React.useMemo(
    () =>
      piezas.filter(
        (p) =>
          (red === TODAS || redCanonica(p.red) === red) &&
          (formato === TODAS || formatoCanonico(p.formato) === formato),
      ),
    [piezas, red, formato],
  );

  // Identidad estable (dependencia del `useMemo` de `useOrdenTabla`); solo cambia con `ocultarAds`,
  // del que depende el accesor de visualizaciones.
  const accesores = React.useMemo(
    () => ({
      titulo: (p: PiezaCampania) => p.titulo.toLowerCase(),
      red: (p: PiezaCampania) => nombreRed(p.red),
      marca: (p: PiezaCampania) => p.marca,
      formato: (p: PiezaCampania) => nombreFormato(p.formato),
      publicado: (p: PiezaCampania) => p.publicado,
      visualizaciones: (p: PiezaCampania) => visEfectivas(p, ocultarAds),
      visualizaciones_pagadas: (p: PiezaCampania) => p.visualizaciones_pagadas,
      interacciones: (p: PiezaCampania) => p.interacciones,
      engagement_pct: (p: PiezaCampania) => p.engagement_pct,
    }),
    [ocultarAds],
  );
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaCampania, ClaveOrdenPieza>(
    filtradas,
    accesores,
    { clave: "visualizaciones", direccion: "desc" },
  );

  const crossCount = React.useMemo(() => piezas.filter((p) => p.por_cross_post).length, [piezas]);

  // En modo cliente (ocultarAds) la columna "Ads" se excluye de la base ANTES de aplicar la
  // vista, así el editor de campos no la ofrece y la tabla no la pinta.
  const cols = ocultarAds ? COLS_PIEZAS.filter((c) => c.id !== "visualizaciones_pagadas") : COLS_PIEZAS;
  const idsBase = cols.map((c) => c.id);
  const cfg = useVistaConfig((s) => s.columnas["campania-piezas"]) ?? { orden: idsBase, ocultas: [] };
  const columnas = columnasVisibles(idsBase, cfg);

  const etiquetaDe = (id: string) => cols.find((c) => c.id === id)?.etiqueta ?? id;

  const encabezado = (id: string, idx: number) => {
    const clave = id as ClaveOrdenPieza;
    return (
      <CabeceraOrdenable
        key={id}
        activa={estado.clave === clave}
        direccion={estado.direccion}
        onClick={() => alClicar(clave)}
        alinear={ALINEAR_PIEZA[id] ?? "right"}
        className={cn(idx === 0 && "pl-6", idx === columnas.length - 1 && "pr-6")}
      >
        {etiquetaDe(id)}
      </CabeceraOrdenable>
    );
  };

  const celda = (p: PiezaCampania, id: string, idx: number) => {
    const primera = idx === 0;
    const ultima = idx === columnas.length - 1;
    switch (id) {
      case "titulo":
        return (
          <TableCell key={id} className={cn(primera && "pl-6", ultima && "pr-6")}>
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
                  title="Cross-post: mismo contenido en otra red"
                >
                  cross-post
                </Badge>
              )}
              {!ocultarAds && p.es_inorganico && (
                <Badge variant="aviso" className="shrink-0 text-[10px]" title="Incluida en Meta Ads">
                  Ads
                </Badge>
              )}
            </span>
          </TableCell>
        );
      case "red":
        return (
          <TableCell key={id} className={cn(primera && "pl-6", ultima && "pr-6")}>
            {p.red ? (
              <Badge variant="outline">{nombreRed(p.red)}</Badge>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </TableCell>
        );
      case "marca":
        return (
          <TableCell key={id} className={cn("text-muted-foreground", primera && "pl-6", ultima && "pr-6")}>
            {p.marca || <span className="text-muted-foreground">—</span>}
          </TableCell>
        );
      case "formato":
        return (
          <TableCell key={id} className={cn("text-muted-foreground", primera && "pl-6", ultima && "pr-6")}>
            {nombreFormato(p.formato)}
          </TableCell>
        );
      case "publicado":
        return (
          <TableCell
            key={id}
            className={cn("text-right text-muted-foreground tabular-nums", primera && "pl-6", ultima && "pr-6")}
          >
            {fechaCorta(p.publicado)}
          </TableCell>
        );
      case "visualizaciones":
        return (
          <TableCell
            key={id}
            className={cn("text-right tabular-nums", primera && "pl-6", ultima && "pr-6")}
            title={numeroCompleto(visEfectivas(p, ocultarAds))}
          >
            {numeroCompacto(visEfectivas(p, ocultarAds))}
          </TableCell>
        );
      case "visualizaciones_pagadas":
        return (
          <TableCell
            key={id}
            className={cn("text-right tabular-nums", primera && "pl-6", ultima && "pr-6")}
            title={p.visualizaciones_pagadas ? numeroCompleto(p.visualizaciones_pagadas) : "Sin inversión"}
          >
            {p.visualizaciones_pagadas ? (
              <span className="text-amber-600 dark:text-amber-400">
                {numeroCompacto(p.visualizaciones_pagadas)}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </TableCell>
        );
      case "interacciones":
        return (
          <TableCell
            key={id}
            className={cn("text-right tabular-nums", primera && "pl-6", ultima && "pr-6")}
            title={numeroCompleto(p.interacciones)}
          >
            {numeroCompacto(p.interacciones)}
          </TableCell>
        );
      case "engagement_pct":
        return (
          <TableCell key={id} className={cn("text-right tabular-nums", primera && "pl-6", ultima && "pr-6")}>
            {porcentaje(p.engagement_pct)}
          </TableCell>
        );
      default:
        return null;
    }
  };

  const filtros = (
    <>
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
    </>
  );

  return (
    <Bloque id="campania-piezas" titulo="Piezas del periodo">
      <Seccion
        id="campania-piezas"
        titulo="Piezas del periodo"
        descripcion={crossCount > 0 ? `Incluye ${crossCount} cross-posts.` : undefined}
        acciones={filtros}
        tablaId="campania-piezas"
        columnas={cols}
      >
        <Card className="overflow-hidden py-2">
          <Table>
            <TableHeader>
              <TableRow>{columnas.map((id, idx) => encabezado(id, idx))}</TableRow>
            </TableHeader>
            <TableBody>
              {filtradas.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={columnas.length} className="py-8 text-center text-muted-foreground">
                    {piezas.length === 0
                      ? "Sin piezas para estos hashtags."
                      : "Ninguna pieza coincide con los filtros."}
                  </TableCell>
                </TableRow>
              ) : (
                filasOrdenadas.map((p) => (
                  <TableRow key={p.id}>{columnas.map((id, idx) => celda(p, id, idx))}</TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>
      </Seccion>
    </Bloque>
  );
}
