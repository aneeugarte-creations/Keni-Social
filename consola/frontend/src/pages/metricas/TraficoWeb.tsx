/**
 * Tráfico web: ranking de piezas por CLICS A ENLACE (clave para UnoTV).
 *
 * Las piezas del periodo (`/api/metricas/piezas`) traen `clics_enlace` cuando la
 * fuente lo expone (Metricool no siempre lo da). Esta vista junta las piezas que el
 * endpoint reporta (top + peores por engagement, ambas listas portan los clics) y
 * las RANKEA por clics a enlace descendente, mostrando pieza (con enlace al post
 * real si hay url), red, clics, vistas y engagement. La tabla es ORDENABLE por
 * cualquier columna numérica y FILTRABLE por red (cliente).
 *
 * Degradación honesta: si NINGUNA pieza trae clics (`clics_enlace == null`), no
 * inventa un 0; muestra un vacío que lo explica.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Link2 } from "lucide-react";
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
import { nombreMarca, nombreRed, numeroCompacto, porcentaje } from "@/lib/formato";
import type { MarcaDisponible, PiezaMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { SeccionColapsable } from "./SeccionColapsable";
import { useOrdenTabla } from "./useOrdenTabla";

const RED_TODAS = "__todas__";

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

  // Solo las piezas con clics > 0 reales (el orden de columna lo aplica la tabla).
  const conClics = data
    ? piezasUnicas(data.top, data.peores).filter(
        (p) => p.clics_enlace != null && p.clics_enlace > 0,
      )
    : [];

  return (
    <SeccionColapsable
      titulo="Tráfico web"
      icono={Link2}
      descripcion="Piezas que más clics llevaron a su enlace en el periodo. Señal de qué copy mandó tráfico fuera de la red."
    >
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
    </SeccionColapsable>
  );
}

type ClaveTrafico = "clics_enlace" | "visualizaciones" | "engagement_pct";

function TablaTrafico({
  piezas,
  marcas,
}: {
  piezas: PiezaMetrica[];
  marcas: MarcaDisponible[];
}) {
  const [redFiltro, setRedFiltro] = React.useState(RED_TODAS);
  const redesDisponibles = React.useMemo(
    () => Array.from(new Set(piezas.map((p) => p.plataforma).filter(Boolean))).sort(),
    [piezas],
  );

  // Filtro de red (cliente) antes de ordenar.
  const visibles =
    redFiltro === RED_TODAS ? piezas : piezas.filter((p) => p.plataforma === redFiltro);

  // Orden por defecto: clics a enlace descendente (lo más relevante para UnoTV).
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaMetrica, ClaveTrafico>(
    visibles,
    {
      clics_enlace: (p) => p.clics_enlace,
      visualizaciones: (p) => p.visualizaciones,
      engagement_pct: (p) => p.engagement_pct,
    },
    { clave: "clics_enlace", direccion: "desc" },
  );

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Select value={redFiltro} onValueChange={setRedFiltro}>
          <SelectTrigger className="w-full sm:w-44" aria-label="Filtrar por red">
            <SelectValue placeholder="Red" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={RED_TODAS}>Todas las redes</SelectItem>
            {redesDisponibles.map((r) => (
              <SelectItem key={r} value={r}>
                {nombreRed(r)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pieza</TableHead>
              <TableHead>Red</TableHead>
              <CabeceraOrdenable
                activa={estado.clave === "clics_enlace"}
                direccion={estado.direccion}
                onClick={() => alClicar("clics_enlace")}
                alinear="right"
              >
                Clics
              </CabeceraOrdenable>
              <CabeceraOrdenable
                activa={estado.clave === "visualizaciones"}
                direccion={estado.direccion}
                onClick={() => alClicar("visualizaciones")}
                alinear="right"
              >
                Vistas
              </CabeceraOrdenable>
              <CabeceraOrdenable
                activa={estado.clave === "engagement_pct"}
                direccion={estado.direccion}
                onClick={() => alClicar("engagement_pct")}
                alinear="right"
              >
                Eng.
              </CabeceraOrdenable>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filasOrdenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                  No hay piezas para la red seleccionada.
                </TableCell>
              </TableRow>
            ) : (
              filasOrdenadas.map((p) => (
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
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
