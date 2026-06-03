/**
 * Desglose de interacciones por marca×red (estrategia digital).
 *
 * Descompone el engagement bruto del periodo en sus partes (likes, comentarios,
 * compartidos, guardados, video_views) por cada celda marca×red. Pinta un BarChart
 * apilado (una barra por marca×red, segmentada por tipo de interacción) y una tabla
 * con el detalle y los `totales` del periodo. Separación clara por marca y por red.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas: si la fuente no expone celdas, lo dice en vez de inventar. La sección es
 * colapsable y filtra client-side por red y por marca (selectores en la cabecera).
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { Heart } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
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
import { nombreMarca, nombreRed, numeroCompacto } from "@/lib/formato";
import type { CeldaDesglose, MarcaDisponible } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

// Componentes del engagement bruto: orden y color estables en la barra apilada.
const COMPONENTES: Array<{ clave: keyof CeldaDesglose; etiqueta: string; color: string }> = [
  { clave: "likes", etiqueta: "Likes", color: "rose" },
  { clave: "comentarios", etiqueta: "Comentarios", color: "blue" },
  { clave: "compartidos", etiqueta: "Compartidos", color: "emerald" },
  { clave: "guardados", etiqueta: "Guardados", color: "amber" },
  { clave: "video_views", etiqueta: "Reproducciones", color: "violet" },
];

const ETIQUETAS = COMPONENTES.map((c) => c.etiqueta);
const COLORES = COMPONENTES.map((c) => c.color);

/** Centinela "sin filtro" para los selectores de red/marca. */
const TODAS = "__todas__";

export function DesgloseInteracciones({
  marcas,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada celda. */
  marcas: MarcaDisponible[];
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "desglose", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasDesglose({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Filtros client-side por red y marca, derivados de las celdas del periodo.
  const [redFiltro, setRedFiltro] = React.useState(TODAS);
  const [marcaFiltro, setMarcaFiltro] = React.useState(TODAS);

  const celdas = React.useMemo(() => data?.celdas ?? [], [data]);
  const redesDisp = React.useMemo(
    () => Array.from(new Set(celdas.map((c) => c.red))),
    [celdas],
  );
  const marcasDisp = React.useMemo(
    () => Array.from(new Set(celdas.map((c) => c.marca))),
    [celdas],
  );
  const celdasFiltradas = React.useMemo(
    () =>
      celdas.filter(
        (c) =>
          (redFiltro === TODAS || c.red === redFiltro) &&
          (marcaFiltro === TODAS || c.marca === marcaFiltro),
      ),
    [celdas, redFiltro, marcaFiltro],
  );

  const acciones =
    redesDisp.length || marcasDisp.length ? (
      <>
        <Select value={redFiltro} onValueChange={setRedFiltro}>
          <SelectTrigger className="w-full sm:w-40" aria-label="Filtrar por red">
            <SelectValue placeholder="Red" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODAS}>Todas las redes</SelectItem>
            {redesDisp.map((r) => (
              <SelectItem key={r} value={r}>
                {nombreRed(r)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={marcaFiltro} onValueChange={setMarcaFiltro}>
          <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por marca">
            <SelectValue placeholder="Marca" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODAS}>Todas las marcas</SelectItem>
            {marcasDisp.map((m) => (
              <SelectItem key={m} value={m}>
                {nombreMarca(m, marcas)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </>
    ) : undefined;

  return (
    <SeccionColapsable
      titulo="Desglose de interacciones"
      icono={Heart}
      descripcion="De qué se compone el engagement de cada marca y red: likes, comentarios, compartidos, guardados y reproducciones del periodo."
      acciones={acciones}
      contentClassName="space-y-6"
    >
      {isPending ? (
        <Skeleton className="h-72 w-full rounded-lg" />
      ) : isError ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          No se pudo cargar el desglose de interacciones.
        </p>
      ) : data.celdas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          La fuente activa no expone el desglose de interacciones para este periodo.
        </p>
      ) : celdasFiltradas.length === 0 ? (
        <p className="py-10 text-center text-sm text-muted-foreground">
          Ninguna celda coincide con los filtros seleccionados.
        </p>
      ) : (
        <>
          <GraficaApilada celdas={celdasFiltradas} marcas={marcas} />
          <TablaDesglose celdas={celdasFiltradas} totales={data.totales} marcas={marcas} />
        </>
      )}
    </SeccionColapsable>
  );
}

/** Una etiqueta legible "Marca · Red" por celda (eje del BarChart / filas de tabla). */
function etiquetaCelda(c: CeldaDesglose, marcas: MarcaDisponible[]): string {
  return `${nombreMarca(c.marca, marcas)} · ${nombreRed(c.red)}`;
}

function GraficaApilada({
  celdas,
  marcas,
}: {
  celdas: CeldaDesglose[];
  marcas: MarcaDisponible[];
}) {
  const datos = celdas.map((c) => ({
    grupo: etiquetaCelda(c, marcas),
    Likes: c.likes,
    Comentarios: c.comentarios,
    Compartidos: c.compartidos,
    Guardados: c.guardados,
    Reproducciones: c.video_views,
  }));
  return (
    <BarChart
      data={datos}
      index="grupo"
      categories={ETIQUETAS}
      colors={COLORES}
      valueFormatter={numeroCompacto}
      stack
      showAnimation
      className="h-72"
    />
  );
}

type ClaveDesglose = keyof CeldaDesglose;

function TablaDesglose({
  celdas,
  totales,
  marcas,
}: {
  celdas: CeldaDesglose[];
  totales: Record<string, number>;
  marcas: MarcaDisponible[];
}) {
  // Cada componente del engagement + nº de piezas es ordenable.
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CeldaDesglose, ClaveDesglose>(
    celdas,
    {
      likes: (c) => c.likes,
      comentarios: (c) => c.comentarios,
      compartidos: (c) => c.compartidos,
      guardados: (c) => c.guardados,
      video_views: (c) => c.video_views,
      n_piezas: (c) => c.n_piezas,
      // El resto de claves de CeldaDesglose no se usan como orden, pero el tipo las exige.
      marca: (c) => c.marca,
      red: (c) => c.red,
      interacciones: (c) => c.interacciones,
      visualizaciones: (c) => c.visualizaciones,
      engagement_pct: (c) => c.engagement_pct,
    } as Record<ClaveDesglose, (c: CeldaDesglose) => number | string | null>,
  );

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            {COMPONENTES.map((c) => (
              <CabeceraOrdenable
                key={c.clave as string}
                activa={estado.clave === c.clave}
                direccion={estado.direccion}
                onClick={() => alClicar(c.clave)}
                alinear="right"
              >
                {c.etiqueta}
              </CabeceraOrdenable>
            ))}
            <CabeceraOrdenable
              activa={estado.clave === "n_piezas"}
              direccion={estado.direccion}
              onClick={() => alClicar("n_piezas")}
              alinear="right"
            >
              Piezas
            </CabeceraOrdenable>
          </TableRow>
        </TableHeader>
        <TableBody>
          {filasOrdenadas.map((c) => (
            <TableRow key={`${c.marca}-${c.red}`}>
              <TableCell className="font-medium">{nombreMarca(c.marca, marcas)}</TableCell>
              <TableCell className="text-muted-foreground">{nombreRed(c.red)}</TableCell>
              {COMPONENTES.map((comp) => (
                <TableCell key={comp.clave} className="text-right tabular-nums">
                  {numeroCompacto(c[comp.clave] as number)}
                </TableCell>
              ))}
              <TableCell className="text-right tabular-nums">{c.n_piezas}</TableCell>
            </TableRow>
          ))}
          <TableRow className="border-t-2 font-medium">
            <TableCell>Total</TableCell>
            <TableCell />
            {COMPONENTES.map((comp) => (
              <TableCell key={comp.clave} className="text-right tabular-nums">
                {numeroCompacto(totales[comp.clave] ?? 0)}
              </TableCell>
            ))}
            <TableCell className="text-right tabular-nums">
              {totales.n_piezas ?? 0}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  );
}
