/**
 * Desglose de interacciones por marca×red (estrategia digital).
 *
 * Descompone el engagement bruto del periodo en sus partes (likes, comentarios,
 * compartidos, guardados, video_views) por cada celda marca×red. Pinta un BarChart
 * apilado (una barra por marca×red, segmentada por tipo de interacción) y una tabla
 * con el detalle y los `totales` del periodo. Separación clara por marca y por red.
 *
 * Mismo stack (Tremor) y estados honestos (carga / vacío / error) que el resto de
 * Métricas: si la fuente no expone celdas, lo dice en vez de inventar.
 */
import { useQuery } from "@tanstack/react-query";
import { BarChart } from "@tremor/react";
import { Heart } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
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
import { api } from "@/lib/api";
import { nombreMarca, nombreRed, numeroCompacto } from "@/lib/formato";
import type { CeldaDesglose, MarcaDisponible } from "@/types";

import { MARCA_TODAS } from "./Controles";

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

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <Heart className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Desglose de interacciones</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          De qué se compone el engagement de cada marca y red: likes, comentarios,
          compartidos, guardados y reproducciones del periodo.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
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
        ) : (
          <>
            <GraficaApilada celdas={data.celdas} marcas={marcas} />
            <TablaDesglose celdas={data.celdas} totales={data.totales} marcas={marcas} />
          </>
        )}
      </CardContent>
    </Card>
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

function TablaDesglose({
  celdas,
  totales,
  marcas,
}: {
  celdas: CeldaDesglose[];
  totales: Record<string, number>;
  marcas: MarcaDisponible[];
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Marca</TableHead>
            <TableHead>Red</TableHead>
            {COMPONENTES.map((c) => (
              <TableHead key={c.clave} className="text-right">
                {c.etiqueta}
              </TableHead>
            ))}
            <TableHead className="text-right">Piezas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {celdas.map((c) => (
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
