/**
 * Crecimiento de seguidores del periodo (estrategia digital).
 *
 * Pinta la GANANCIA ACUMULADA de seguidores día a día: la línea arranca en 0 al inicio
 * del periodo y termina en el neto (`neto` / `neto_por_red`), de modo que la pendiente
 * cuenta exactamente lo que el título promete y el eje es legible (0 → +5.2 k) aunque el
 * stock sea de millones. En el desglose por red todas las series parten de 0 y son
 * comparables entre sí. Mismo criterio que la lámina de seguidores del informe. El stock
 * ABSOLUTO no se pierde: arriba, un KPI por red con el total ACTUAL de seguidores (el
 * dato protagonista, como en Metricool) y el neto del periodo como insignia de
 * variación; debajo, la tabla con las cifras exactas. Si la fuente activa no expone
 * seguidores (`puntos=[]`) lo dice con honestidad en vez de inventar una serie; una red
 * sin datos en el periodo no se pinta como serie (su ausencia queda explicada con "—").
 */
import { useQuery } from "@tanstack/react-query";
import { BadgeDelta, type DeltaType, LineChart } from "@tremor/react";
import { Users } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import {
  nombreRed,
  numeroCompacto,
  numeroCompleto,
  REDES_CANONICAS,
  variacion,
} from "@/lib/formato";
import type { PuntoSeguidores } from "@/types";

import { colorDe } from "./coloresRed";
import { MARCA_TODAS } from "./Controles";
import { useVistaConfig } from "./vistaConfig";
import { Seccion } from "./Seccion";

/** Neto de seguidores con signo: es un CONTEO (`+1.2K` / `−5K`), NO un porcentaje. */
function netoSeguidores(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompacto(Math.abs(n))}`;
}

/** "12 may" a partir de una fecha ISO (AAAA-MM-DD), en es-MX. */
function fechaCorta(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", { day: "2-digit", month: "short" }).format(d);
}

/**
 * Filas del chart: ganancia ACUMULADA por día (valor del día − primer valor CONOCIDO de
 * su serie), con las claves de `por_red` re-mapeadas al nombre legible de cada red para
 * que la leyenda no enseñe el id crudo. En el modo global la serie es "Total" (arranca
 * en 0 y termina en el neto del periodo); en el desglose cada red resta SU primer valor,
 * así todas parten de 0 y son comparables aunque sus stocks difieran en órdenes de
 * magnitud. Un día sin dato para una red es `null` (hueco honesto en la línea), NUNCA un
 * 0 inventado (parecería que la red volvió a su nivel inicial). Exportada para tests.
 */
export function filasAcumuladas(
  puntos: PuntoSeguidores[],
  porRed: boolean,
  redes: string[],
): Array<Record<string, string | number | null>> {
  const inicioTotal = puntos[0]?.total ?? 0;
  const inicioRed = new Map<string, number>();
  for (const p of puntos)
    for (const red of redes)
      if (!inicioRed.has(red) && p.por_red[red] != null) inicioRed.set(red, p.por_red[red]);
  return puntos.map((p) => {
    if (!porRed) return { fecha: fechaCorta(p.fecha), Total: p.total - inicioTotal };
    const fila: Record<string, string | number | null> = { fecha: fechaCorta(p.fecha) };
    for (const red of redes) {
      const v = p.por_red[red];
      fila[nombreRed(red)] = v == null ? null : v - (inicioRed.get(red) ?? v);
    }
    return fila;
  });
}

export function CrecimientoSeguidores({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const [porRed, setPorRed] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "seguidores", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasSeguidores({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Redes canónicas CON al menos un punto en el periodo (orden canónico fijo). Las
  // ausentes no se pintan como serie: su ausencia ya queda explicada con "—" en los KPIs.
  const redesConDatos = React.useMemo(() => {
    const puntos = data?.puntos ?? [];
    return REDES_CANONICAS.filter((red) => puntos.some((p) => p.por_red[red] != null));
  }, [data]);

  const datos = React.useMemo(
    () => filasAcumuladas(data?.puntos ?? [], porRed, redesConDatos),
    [data, porRed, redesConDatos],
  );

  const categorias = porRed ? redesConDatos.map(nombreRed) : ["Total"];
  // Color por red SIEMPRE desde la fuente única (coloresRed.ts); los hex están en la
  // safelist de tailwind.config.js para que el JIT no los purgue.
  const colores = porRed ? redesConDatos.map(colorDe) : ["blue"];

  return (
    <Seccion
      id="seguidores"
      titulo="Crecimiento de seguidores"
      descripcion="Seguidores ganados desde el inicio del periodo, acumulados día a día."
      icono={Users}
      acciones={
        <Label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch
            checked={porRed}
            onCheckedChange={setPorRed}
            aria-label="Desglosar por red"
            disabled={redesConDatos.length === 0}
          />
          Por red
        </Label>
      }
    >
      <div className="space-y-4">
        <Card className="space-y-4 p-4 sm:p-6">
          {isPending ? (
            <Skeleton className="h-56 w-full rounded-lg" />
          ) : isError ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No se pudo cargar la serie de seguidores.
            </p>
          ) : (data.puntos ?? []).length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              Aún no hay datos de seguidores para este periodo
            </p>
          ) : (
            <>
              <KpisSeguidores
                puntos={data.puntos}
                neto={data.neto}
                netoPorRed={data.neto_por_red}
              />
              {/* Alternativa textual del chart para lectores de pantalla. */}
              <div
                role="img"
                aria-label={`Seguidores ganados en el periodo: ${netoSeguidores(data.neto)}`}
              >
                {/* Eje y tooltip con signo (netoSeguidores): los valores son ganancia, no
                    stock. `autoMinValue` deja bajar el eje de 0 si el neto se vuelve
                    negativo (pérdida de seguidores). */}
                <LineChart
                  data={datos}
                  index="fecha"
                  categories={categorias}
                  colors={colores}
                  valueFormatter={netoSeguidores}
                  showLegend={porRed}
                  showAnimation
                  curveType="monotone"
                  autoMinValue
                  className="h-56"
                />
              </div>
            </>
          )}
        </Card>
        {/* Cifras EXACTAS por red: stock al inicio del periodo → actual, crecimiento y %.
            Complementa el chart (abreviado) y los KPIs con el detalle numérico. */}
        {!isPending && !isError && data && data.puntos.length > 0 && (
          <TablaSeguidores
            puntos={data.puntos}
            neto={data.neto}
            netoPorRed={data.neto_por_red}
          />
        )}
      </div>
    </Seccion>
  );
}

/** `deltaType` de Tremor según el signo del neto: verde sube, rojo baja, gris sin cambio. */
function deltaNeto(neto: number): DeltaType {
  if (!Number.isFinite(neto) || neto === 0) return "unchanged";
  return neto > 0 ? "moderateIncrease" : "moderateDecrease";
}

/** Insignia con la variación de seguidores del periodo (flecha + neto con signo). */
function InsigniaNeto({ neto }: { neto: number }) {
  return (
    <BadgeDelta
      deltaType={deltaNeto(neto)}
      size="xs"
      className="shrink-0"
      title={`${numeroCompleto(neto)} en el periodo`}
    >
      {netoSeguidores(neto)}
    </BadgeDelta>
  );
}

/**
 * Total ACTUAL de seguidores como destacado + un KPI por red, cada uno con el neto del
 * periodo como insignia de variación. El total absoluto es el dato protagonista (lo que
 * Metricool muestra en grande); el neto queda como insignia secundaria.
 */
function KpisSeguidores({
  puntos,
  neto,
  netoPorRed,
}: {
  puntos: PuntoSeguidores[];
  neto: number;
  netoPorRed: Record<string, number>;
}) {
  // Total actual GLOBAL = último punto (mismo valor que el extremo derecho de la línea
  // "Total" del chart). Por red, el último valor conocido: una red con hueco al final
  // conserva su stock, no cae a "—".
  const totalActual = puntos[puntos.length - 1]?.total ?? 0;
  const totalRedActual = (red: string): number | null => {
    for (let i = puntos.length - 1; i >= 0; i--) {
      const v = puntos[i].por_red[red];
      if (v != null) return v;
    }
    return null;
  };

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      <TarjetaKpi
        etiqueta="Seguidores totales"
        valor={numeroCompacto(totalActual)}
        titulo={`${numeroCompleto(totalActual)} seguidores`}
        insignia={<InsigniaNeto neto={neto} />}
      />
      {REDES_CANONICAS.map((red) => {
        const total = totalRedActual(red);
        // Red ausente en el periodo (sin un solo punto): "—" honesto, sin insignia.
        if (total === null) {
          return (
            <TarjetaKpi
              key={red}
              etiqueta={nombreRed(red)}
              valor="—"
              titulo="Sin datos para este periodo"
            />
          );
        }
        // El neto puede faltar aunque haya stock (presencia de la clave): sin neto, sin
        // insignia (pero el total sí se muestra).
        const netoRed = Object.prototype.hasOwnProperty.call(netoPorRed, red)
          ? netoPorRed[red]
          : null;
        return (
          <TarjetaKpi
            key={red}
            etiqueta={nombreRed(red)}
            valor={numeroCompacto(total)}
            titulo={`${numeroCompleto(total)} seguidores`}
            insignia={netoRed === null ? undefined : <InsigniaNeto neto={netoRed} />}
          />
        );
      })}
    </div>
  );
}

/** Crecimiento exacto con signo: conteo COMPLETO con separadores (+13,640 / −5,200 / 0). */
function crecimientoExacto(n: number): string {
  if (!Number.isFinite(n) || n === 0) return "0";
  return `${n > 0 ? "+" : "−"}${numeroCompleto(Math.abs(n))}`;
}

/** Color del % de crecimiento: verde sube, rojo baja, neutro sin cambio o sin base. */
function colorCrecimiento(pct: number | null): string {
  if (pct === null || pct === 0) return "text-muted-foreground";
  return pct > 0
    ? "text-emerald-700 dark:text-emerald-300"
    : "text-red-700 dark:text-red-300";
}

/** Primer y último valor CONOCIDO de una red en la serie (ignora huecos en los extremos). */
function extremosRed(
  puntos: PuntoSeguidores[],
  red: string,
): { inicio: number; actual: number } | null {
  let inicio: number | null = null;
  let actual: number | null = null;
  for (const p of puntos) {
    const v = p.por_red[red];
    if (v != null) {
      if (inicio === null) inicio = v;
      actual = v;
    }
  }
  return inicio === null || actual === null ? null : { inicio, actual };
}

/** Celda de % de crecimiento, coloreada y con "—" honesto cuando no hay base de cálculo. */
function CeldaPct({ crecimiento, inicio }: { crecimiento: number; inicio: number }) {
  const pct = inicio > 0 ? (crecimiento / inicio) * 100 : null;
  return (
    <TableCell className={`pr-6 text-right tabular-nums last:pr-6 ${colorCrecimiento(pct)}`}>
      {pct === null ? "—" : variacion(pct)}
    </TableCell>
  );
}

/**
 * Tabla de cifras EXACTAS de seguidores por red: stock al inicio del periodo y actual
 * (los extremos de la serie), el crecimiento absoluto (`neto_por_red`, autoritativo) y el
 * % sobre el inicio. Al pie, los totales. Solo redes CON datos en el periodo (una red sin
 * un solo punto se omite, no se pinta una fila de "—"). Mismo lenguaje visual que
 * «Detalle por red», con las dos columnas de stock encabezadas por su fecha.
 */
function TablaSeguidores({
  puntos,
  neto,
  netoPorRed,
}: {
  puntos: PuntoSeguidores[];
  neto: number;
  netoPorRed: Record<string, number>;
}) {
  const redes = REDES_CANONICAS.filter((red) => puntos.some((p) => p.por_red[red] != null));
  // Totales globales = extremos de la serie `total` (igual que la línea "Total" del chart).
  const inicioTotal = puntos[0]?.total ?? 0;
  const actualTotal = puntos[puntos.length - 1]?.total ?? 0;
  // Fechas de los extremos para encabezar las dos columnas de stock (como MARZO/ABRIL).
  const fechaInicio = puntos[0] ? fechaCorta(puntos[0].fecha) : "Inicio";
  const fechaActual = puntos[puntos.length - 1]
    ? fechaCorta(puntos[puntos.length - 1].fecha)
    : "Actual";

  return (
    <Card className="overflow-hidden py-2">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="pl-6">Red</TableHead>
            <TableHead className="text-right">{fechaInicio}</TableHead>
            <TableHead className="text-right">{fechaActual}</TableHead>
            <TableHead className="text-right">Crecimiento</TableHead>
            <TableHead className="pr-6 text-right last:pr-6">%</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {redes.map((red) => {
            const ex = extremosRed(puntos, red);
            if (ex === null) return null;
            const crecimiento = Object.prototype.hasOwnProperty.call(netoPorRed, red)
              ? netoPorRed[red]
              : ex.actual - ex.inicio;
            return (
              <TableRow key={red}>
                <TableCell className="pl-6 font-medium">{nombreRed(red)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {numeroCompleto(ex.inicio)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {numeroCompleto(ex.actual)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {crecimientoExacto(crecimiento)}
                </TableCell>
                <CeldaPct crecimiento={crecimiento} inicio={ex.inicio} />
              </TableRow>
            );
          })}
          <TableRow className="border-t-2 font-medium">
            <TableCell className="pl-6">Total</TableCell>
            <TableCell className="text-right tabular-nums">{numeroCompleto(inicioTotal)}</TableCell>
            <TableCell className="text-right tabular-nums">{numeroCompleto(actualTotal)}</TableCell>
            <TableCell className="text-right tabular-nums">{crecimientoExacto(neto)}</TableCell>
            <CeldaPct crecimiento={neto} inicio={inicioTotal} />
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
