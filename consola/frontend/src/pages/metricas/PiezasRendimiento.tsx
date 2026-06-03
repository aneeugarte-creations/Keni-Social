/**
 * Drill-down marca -> pieza: lista las piezas YA PUBLICADAS con su rendimiento REAL.
 *
 * A diferencia de `PiezasAnalitica` (estadísticas agregadas top/peores del periodo,
 * descubiertas desde la lista de posts), esta sección lista las piezas CONCRETAS que el
 * equipo publicó desde la Consola y cierra el bucle con su rendimiento leído de
 * Metricool —la MISMA fuente única que el dashboard y las tarjetas del tablero, sin
 * desfase—. Cada fila enlaza a la pieza en el tablero (`/parrilla/pendientes`).
 *
 * Degradación honesta: las piezas que Metricool aún no tiene (recién publicadas) salen
 * marcadas como "sin datos todavía", nunca con ceros falsos. Un tab por marca (+ "Todas"),
 * perezoso (Radix desmonta el inactivo), así que solo el tab visible consulta.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, LayoutList } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
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
import { nombreRed, numeroCompacto, porcentaje } from "@/lib/formato";
import type { OpcionesMetricas, PiezaRendimiento } from "@/types";

const TAB_TODAS = "todas";

/** Enlace al tablero, resaltando la pieza por su `contenido_id` (query aditiva). */
function enlaceTablero(contenidoId: string): string {
  return `/parrilla/pendientes?contenido=${encodeURIComponent(contenidoId)}`;
}

export function PiezasRendimiento({ opciones }: { opciones: OpcionesMetricas }) {
  const [tab, setTab] = React.useState(TAB_TODAS);

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <LayoutList className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Piezas publicadas</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Rendimiento real por pieza publicada (Metricool). Toca una pieza para abrirla en
          el tablero.
        </p>
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
            <ContenidoRendimiento marca={undefined} />
          </TabsContent>
          {opciones.marcas.map((m) => (
            <TabsContent key={m.id} value={m.id}>
              <ContenidoRendimiento marca={m.id} />
            </TabsContent>
          ))}
        </Tabs>
      </CardHeader>
    </Card>
  );
}

function ContenidoRendimiento({ marca }: { marca?: string }) {
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-rendimiento", marca ?? "todas"],
    queryFn: ({ signal }) => api.metricasPiezasRendimiento({ marca }, signal),
    // Tabs por marca: 2 min de frescura para que alternar tabs no re-pegue a Metricool en
    // cada click pero el dato no quede rancio; "Actualizar" invalida igualmente.
    staleTime: 2 * 60_000,
  });

  if (isPending) return <Skeleton className="mt-2 h-72 w-full rounded-lg" />;
  if (isError) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        No se pudo cargar el rendimiento de las piezas.
      </p>
    );
  }
  if (data.total === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        Aún no hay piezas publicadas con métricas para esta selección.
      </p>
    );
  }

  return (
    <CardContent className="px-0 pb-0">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Pieza</TableHead>
            <TableHead className="text-right">Vistas</TableHead>
            <TableHead className="text-right">Interac.</TableHead>
            <TableHead className="text-right">Eng.</TableHead>
            <TableHead className="w-10">
              <span className="sr-only">Acciones</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.piezas.map((p) => (
            <FilaPieza key={p.plataforma_id || `${p.contenido_id}-${p.red}`} pieza={p} />
          ))}
        </TableBody>
      </Table>
    </CardContent>
  );
}

function FilaPieza({ pieza }: { pieza: PiezaRendimiento }) {
  const navigate = useNavigate();
  const titulo = pieza.titulo || "(sin título)";

  // Acción primaria = abrir la pieza en el tablero (resaltada por su contenido_id).
  // "Abrir en la red" (si hay url) queda como acción secundaria en el menú.
  const acciones: EntradaMenuContextual[] = pieza.url
    ? [
        {
          etiqueta: "Abrir en la red",
          icono: ExternalLink,
          onClick: () => window.open(pieza.url!, "_blank", "noopener,noreferrer"),
        },
      ]
    : [];

  return (
    <FilaConAcciones
      como="tr"
      onPrimaria={() => navigate(enlaceTablero(pieza.contenido_id))}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${titulo}"`}
      kebab="hover"
    >
      <TableCell className="max-w-[20rem]">
        <span className="block truncate font-medium" title={titulo}>
          {titulo}
        </span>
        <span className="text-xs text-muted-foreground">
          {pieza.marca_nombre} · {nombreRed(pieza.red)}
        </span>
      </TableCell>
      {pieza.encontrado ? (
        <>
          <TableCell className="text-right tabular-nums">
            {numeroCompacto(pieza.visualizaciones)}
          </TableCell>
          <TableCell className="text-right tabular-nums">
            {numeroCompacto(pieza.interacciones)}
          </TableCell>
          <TableCell className="text-right tabular-nums">
            {porcentaje(pieza.engagement_pct)}
          </TableCell>
        </>
      ) : (
        <TableCell colSpan={3} className="text-right">
          {/* Degradación honesta: Metricool aún no tiene datos de esta pieza. */}
          <Badge variant="outline" className="text-muted-foreground">
            sin datos todavía
          </Badge>
        </TableCell>
      )}
    </FilaConAcciones>
  );
}
