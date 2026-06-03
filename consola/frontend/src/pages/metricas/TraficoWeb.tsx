/**
 * Tráfico web: ranking de piezas por CLICS A ENLACE (clave para UnoTV).
 *
 * Las piezas del periodo (`/api/metricas/piezas`) traen `clics_enlace` cuando la
 * fuente lo expone (Metricool no siempre lo da). Esta vista junta las piezas que el
 * endpoint reporta (top + peores por engagement, ambas listas portan los clics) y
 * las RANKEA por clics a enlace descendente, mostrando pieza (con enlace al post
 * real si hay url), red, clics, vistas y engagement.
 *
 * Degradación honesta: si NINGUNA pieza trae clics (`clics_enlace == null`), no
 * inventa un 0; muestra un vacío que lo explica.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Link2 } from "lucide-react";

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
import { nombreMarca, nombreRed, numeroCompacto, porcentaje } from "@/lib/formato";
import type { MarcaDisponible, PiezaMetrica } from "@/types";

import { MARCA_TODAS } from "./Controles";

/** Une top+peores y deduplica por (plataforma,id): ambas listas portan `clics_enlace`. */
function piezasUnicas(top: PiezaMetrica[], peores: PiezaMetrica[]): PiezaMetrica[] {
  const vistas = new Map<string, PiezaMetrica>();
  for (const p of [...top, ...peores]) {
    vistas.set(`${p.plataforma}-${p.id}`, p);
  }
  return [...vistas.values()];
}

export function TraficoWeb({
  marcas,
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Catálogo {id, nombre} para resolver el id crudo de marca de cada pieza. */
  marcas: MarcaDisponible[];
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "trafico-web", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasPiezas({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  // Solo las piezas con clics > 0 reales; ordenadas por clics desc.
  const conClics = data
    ? piezasUnicas(data.top, data.peores)
        .filter((p) => p.clics_enlace != null && p.clics_enlace > 0)
        .sort((a, b) => (b.clics_enlace ?? 0) - (a.clics_enlace ?? 0))
    : [];

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <Link2 className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Tráfico web</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Piezas que más clics llevaron a su enlace en el periodo. Señal de qué copy
          mandó tráfico fuera de la red.
        </p>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <Skeleton className="h-56 w-full rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar el tráfico web.
          </p>
        ) : conClics.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Ninguna pieza del periodo reporta clics a enlace. La fuente (Metricool) no
            siempre expone este dato.
          </p>
        ) : (
          <TablaTrafico piezas={conClics} marcas={marcas} />
        )}
      </CardContent>
    </Card>
  );
}

function TablaTrafico({
  piezas,
  marcas,
}: {
  piezas: PiezaMetrica[];
  marcas: MarcaDisponible[];
}) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Pieza</TableHead>
            <TableHead>Red</TableHead>
            <TableHead className="text-right">Clics</TableHead>
            <TableHead className="text-right">Vistas</TableHead>
            <TableHead className="text-right">Eng.</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {piezas.map((p) => (
            <TableRow key={`${p.plataforma}-${p.id}`}>
              <TableCell className="max-w-[20rem]">
                {p.url ? (
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex max-w-full items-center gap-1 truncate font-medium text-foreground underline-offset-4 hover:underline"
                    title={p.titulo}
                  >
                    <span className="truncate">{p.titulo}</span>
                    <ExternalLink className="h-3 w-3 shrink-0 opacity-60" aria-hidden="true" />
                  </a>
                ) : (
                  <span className="block truncate font-medium" title={p.titulo}>
                    {p.titulo}
                  </span>
                )}
                {p.cuenta && (
                  <span className="block text-xs text-muted-foreground">
                    {nombreMarca(p.cuenta, marcas)}
                  </span>
                )}
              </TableCell>
              <TableCell className="text-muted-foreground">{nombreRed(p.plataforma)}</TableCell>
              <TableCell className="text-right font-medium tabular-nums">
                {numeroCompacto(p.clics_enlace ?? 0)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {numeroCompacto(p.visualizaciones)}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {porcentaje(p.engagement_pct)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
