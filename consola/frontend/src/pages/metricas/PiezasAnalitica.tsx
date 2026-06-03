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
import {
  BarChart3,
  Bookmark,
  ChevronDown,
  Clock,
  Download,
  Heart,
  Link2,
  MessageCircle,
  Share2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { MenuContextual } from "@/components/comunes/MenuContextual";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { nombreMarca, nombreRed, numeroCompacto, porcentaje, tiempoVis } from "@/lib/formato";
import type {
  EstadisticasNumericas,
  MarcaDisponible,
  OpcionesMetricas,
  PiezaMetrica,
} from "@/types";

const TAB_TODAS = "todas";
const RED_TODAS = "todas";
// Redes auditables para el filtro (mismas que la cobertura). El backend valida estos ids.
const REDES_FILTRO = ["facebook", "instagram", "x", "tiktok", "youtube"] as const;

/** Porcentaje tolerante a null ("—" si no hay dato). */
function pct(v: number | null): string {
  return v == null ? "—" : porcentaje(v);
}

/**
 * Componentes granulares del engagement de una pieza, en orden de lectura.
 * Solo se pintan los que la fuente expone (`!= null`): distinguimos "0" de "sin dato".
 * Cada uno usa un icono con su nombre como tooltip (más legible que glifos sueltos).
 */
const GRANULAR: Array<{ clave: keyof PiezaMetrica; nombre: string; icono: LucideIcon }> = [
  { clave: "likes", nombre: "Likes", icono: Heart },
  { clave: "comentarios", nombre: "Comentarios", icono: MessageCircle },
  { clave: "compartidos", nombre: "Compartidos", icono: Share2 },
  { clave: "guardados", nombre: "Guardados", icono: Bookmark },
];

/** Chip icono + número con tooltip de nombre (desglose granular legible de una pieza). */
function ChipMetrica({
  icono: Icono,
  nombre,
  valor,
}: {
  icono: LucideIcon;
  nombre: string;
  valor: string;
}) {
  return (
    <span
      className="inline-flex items-center gap-1 rounded bg-muted/60 px-1.5 py-0.5"
      title={nombre}
    >
      <Icono className="h-3 w-3 shrink-0 opacity-70" aria-hidden="true" />
      <span className="sr-only">{nombre}: </span>
      {valor}
    </span>
  );
}

export function PiezasAnalitica({
  opciones,
  rangoActual,
  tab: tabControlado,
  onTabChange,
}: {
  opciones: OpcionesMetricas;
  rangoActual?: string;
  /** Tab de marca controlado externamente (drill-down desde las tablas). */
  tab?: string;
  onTabChange?: (tab: string) => void;
}) {
  const [tabInterno, setTabInterno] = React.useState(TAB_TODAS);
  // Controlado si el padre pasa `tab`; si no, gestiona su propio estado.
  const tab = tabControlado ?? tabInterno;
  const setTab = (v: string) => {
    setTabInterno(v);
    onTabChange?.(v);
  };
  // Filtro por red, aplicado a la marca activa (el top/peores/estadísticas se recalculan
  // SOLO sobre esa red en el backend). "todas" = sin filtro.
  const [red, setRed] = React.useState<string>(RED_TODAS);
  const redParam = red === RED_TODAS ? undefined : red;

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

          {/* Filtro por red, debajo del filtro por marca. Aplica al tab activo. */}
          <div className="mt-3">
            <Select value={red} onValueChange={setRed}>
              <SelectTrigger className="w-full sm:w-48" aria-label="Filtrar por red">
                <SelectValue placeholder="Red" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={RED_TODAS}>Todas las redes</SelectItem>
                {REDES_FILTRO.map((r) => (
                  <SelectItem key={r} value={r}>
                    {nombreRed(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <TabsContent value={TAB_TODAS}>
            <ContenidoPiezas
              marca={undefined}
              red={redParam}
              rango={rangoActual}
              marcas={opciones.marcas}
            />
          </TabsContent>
          {opciones.marcas.map((m) => (
            <TabsContent key={m.id} value={m.id}>
              <ContenidoPiezas
                marca={m.id}
                red={redParam}
                rango={rangoActual}
                marcas={opciones.marcas}
              />
            </TabsContent>
          ))}
        </Tabs>
      </CardHeader>
    </Card>
  );
}

function ContenidoPiezas({
  marca,
  red,
  rango,
  marcas,
}: {
  marca?: string;
  /** Red seleccionada (id de plataforma) o undefined = todas. */
  red?: string;
  rango?: string;
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada pieza. */
  marcas: MarcaDisponible[];
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas", rango ?? "", marca ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasPiezas({ rango, marca, red }, signal),
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
          <TablaPiezas titulo="Top 10" piezas={data.top} marcas={marcas} />
          <TablaPiezas titulo="Peores 10" piezas={data.peores} marcas={marcas} />
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

function TablaPiezas({
  titulo,
  piezas,
  marcas,
}: {
  titulo: string;
  piezas: PiezaMetrica[];
  marcas: MarcaDisponible[];
}) {
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
              <FilaAnalitica key={`${p.plataforma}-${p.id}`} pieza={p} marcas={marcas} />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function FilaAnalitica({ pieza, marcas }: { pieza: PiezaMetrica; marcas: MarcaDisponible[] }) {
  // Clic en CUALQUIER parte de la fila abre la pieza en la red (cuando hay url). Sin
  // icono de enlace ni columna de acciones: el área completa es el disparador.
  const abrir = pieza.url
    ? () => window.open(pieza.url!, "_blank", "noopener,noreferrer")
    : undefined;

  // Marca de la pieza (`cuenta`, id crudo) + red, para ubicarla cuando el tab agrega
  // "Todas". Resolvemos ambos a su nombre legible (id desconocido se degrada honesto).
  const procedencia = [
    pieza.cuenta ? nombreMarca(pieza.cuenta, marcas) : "",
    pieza.plataforma ? nombreRed(pieza.plataforma) : "",
  ]
    .filter(Boolean)
    .join(" · ");

  // Desglose granular: solo los componentes que la fuente expone (distingue 0 de null).
  const granular = GRANULAR.filter((g) => pieza[g.clave] != null);
  // Clics a enlace alto: ~señal de que el copy llevó tráfico fuera de la red.
  const clicsAltos = pieza.clics_enlace != null && pieza.clics_enlace >= 1000;

  return (
    <TableRow
      onClick={abrir}
      tabIndex={abrir ? 0 : undefined}
      role={abrir ? "button" : undefined}
      aria-label={abrir ? `Abrir "${pieza.titulo}" en la red` : undefined}
      onKeyDown={
        abrir
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                abrir();
              }
            }
          : undefined
      }
      className={abrir ? "cursor-pointer" : undefined}
    >
      <TableCell className="max-w-[18rem]">
        <span className="block truncate font-medium text-foreground" title={pieza.titulo}>
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
        {(granular.length > 0 ||
          pieza.clics_enlace != null ||
          pieza.tiempo_medio_vis_s != null) && (
          <span className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground tabular-nums">
            {granular.map((g) => (
              <ChipMetrica
                key={g.clave as string}
                icono={g.icono}
                nombre={g.nombre}
                valor={numeroCompacto(pieza[g.clave] as number)}
              />
            ))}
            {/* Clics a enlace: solo si la fuente lo expone (distingue 0 de sin dato). */}
            {pieza.clics_enlace != null && (
              <ChipMetrica
                icono={Link2}
                nombre="Clics al enlace"
                valor={numeroCompacto(pieza.clics_enlace)}
              />
            )}
            {/* Tiempo medio de visualización (vídeo): "Xs" / "Xm Ys". */}
            {pieza.tiempo_medio_vis_s != null && (
              <ChipMetrica
                icono={Clock}
                nombre="Tiempo medio de visualización"
                valor={tiempoVis(pieza.tiempo_medio_vis_s)}
              />
            )}
            {clicsAltos && (
              <Badge variant="ok" title="Muchos clics al enlace en este periodo">
                clics altos
              </Badge>
            )}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {numeroCompacto(pieza.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {porcentaje(pieza.engagement_pct)}
      </TableCell>
    </TableRow>
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
