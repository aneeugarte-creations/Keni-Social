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
import { BarChart3, ChevronDown, Download, ExternalLink } from "lucide-react";
import * as React from "react";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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

/**
 * Componentes granulares del engagement de una pieza, en orden de lectura.
 * Solo se pintan los que la fuente expone (`!= null`): distinguimos "0" de "sin dato".
 */
const GRANULAR: Array<{ clave: keyof PiezaMetrica; etiqueta: string }> = [
  { clave: "likes", etiqueta: "♥" },
  { clave: "comentarios", etiqueta: "💬" },
  { clave: "compartidos", etiqueta: "↗" },
  { clave: "guardados", etiqueta: "⤓" },
];

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
    // Tabs por marca: al alternar tabs queremos datos razonablemente frescos sin re-pedir
    // en cada click. 2 min equilibra frescura y coste; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
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
      />

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Mejores y peores piezas</h4>
          <DescargarPiezas rango={rango} marca={marca} />
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <TablaPiezas titulo="Top 10" piezas={data.top} />
          <TablaPiezas titulo="Peores 10" piezas={data.peores} />
        </div>
      </div>

      <Distribucion buckets={data.distribucion} />
    </CardContent>
  );
}

const FORMATOS_PIEZAS: Array<{ formato: "csv" | "md" | "json"; etiqueta: string }> = [
  { formato: "csv", etiqueta: "CSV" },
  { formato: "md", etiqueta: "Markdown" },
  { formato: "json", etiqueta: "JSON" },
];

/** Descarga del Top 5 / Peores 5 del tab actual (csv|md|json), vía /piezas-export. */
function DescargarPiezas({ rango, marca }: { rango?: string; marca?: string }) {
  return (
    <MenuContextual
      disparador="click"
      etiqueta="Descargar top y peores piezas"
      items={FORMATOS_PIEZAS.map(({ formato, etiqueta }) => ({
        etiqueta,
        icono: Download,
        onClick: () => api.exportarPiezas(formato, { rango, marca }),
      }))}
    >
      <Button variant="outline" size="sm">
        <Download className="h-4 w-4" />
        Descargar
        <ChevronDown className="h-4 w-4 opacity-60" />
      </Button>
    </MenuContextual>
  );
}

function TiraEstadisticas({
  engagement,
  visualizaciones,
  total,
}: {
  engagement: EstadisticasNumericas;
  visualizaciones: EstadisticasNumericas;
  total: number;
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
              <TableHead className="w-10">
                <span className="sr-only">Acciones</span>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {piezas.map((p) => (
              <FilaAnalitica key={`${p.plataforma}-${p.id}`} pieza={p} />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function FilaAnalitica({ pieza }: { pieza: PiezaMetrica }) {
  // Acción primaria = abrir la pieza en la red (cuando hay url). "Abrir en la red"
  // queda también como acción secundaria en el menú (click derecho / kebab).
  const abrir = pieza.url
    ? () => window.open(pieza.url!, "_blank", "noopener,noreferrer")
    : undefined;
  const acciones: EntradaMenuContextual[] = pieza.url
    ? [{ etiqueta: "Abrir en la red", icono: ExternalLink, onClick: abrir! }]
    : [];

  // Marca de la pieza (`cuenta`) + red, para ubicarla cuando el tab agrega "Todas".
  const procedencia = [pieza.cuenta, pieza.plataforma].filter(Boolean).join(" · ");

  // Desglose granular: solo los componentes que la fuente expone (distingue 0 de null).
  const granular = GRANULAR.filter((g) => pieza[g.clave] != null);

  return (
    <FilaConAcciones
      como="tr"
      onPrimaria={abrir}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${pieza.titulo}"`}
      kebab="hover"
    >
      <TableCell className="max-w-[18rem]">
        <span className="block truncate" title={pieza.titulo}>
          {pieza.titulo}
        </span>
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <span>{procedencia}</span>
          {pieza.rendimiento_relativo != null && (
            <Badge
              variant={pieza.rendimiento_relativo >= 1 ? "ok" : "error"}
              title="Vistas de la pieza ÷ mediana de vistas de su red"
            >
              {pieza.rendimiento_relativo.toLocaleString("es-MX", {
                maximumFractionDigits: 1,
              })}
              × mediana de vistas de su red
            </Badge>
          )}
        </span>
        {granular.length > 0 && (
          <span className="mt-0.5 flex flex-wrap gap-x-2 text-xs text-muted-foreground tabular-nums">
            {granular.map((g) => (
              <span key={g.clave as string} title={g.clave as string}>
                {g.etiqueta} {numeroCompacto(pieza[g.clave] as number)}
              </span>
            ))}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {numeroCompacto(pieza.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {porcentaje(pieza.engagement_pct)}
      </TableCell>
    </FilaConAcciones>
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
