/**
 * Lista COMPLETA de piezas del periodo (todas, no solo top/peores), abrible.
 *
 * Tabla con TODAS las piezas que la fuente única emite para el periodo
 * (`/api/metricas/piezas-listado`): buscador por título (filtro client-side), orden por
 * vistas / engagement / clics / fecha (reúsa `useOrdenTabla` + `CabeceraOrdenable`), red y
 * formato legibles y enlace al post real. Cada fila es ABRIBLE: al clicar abre el
 * `DetallePieza` (métricas + granulares + curva histórica + velocidad).
 *
 * Sigue la marca/rango global del dashboard, como el resto de las secciones de detalle.
 */
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, ListChecks, Search } from "lucide-react";
import * as React from "react";

import { marcaParam } from "@/components/comunes/selectores";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import { nombreFormato, nombreRed, numeroCompacto, porcentaje } from "@/lib/formato";
import type { PiezaMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import { MARCA_TODAS } from "./Controles";
import { DetallePieza } from "./DetallePieza";
import { useOrdenTabla } from "./useOrdenTabla";

type ClaveOrden = "publicado" | "visualizaciones" | "engagement_pct" | "clics_enlace";

const ACCESORES: Record<ClaveOrden, (p: PiezaMetrica) => number | string | null> = {
  publicado: (p) => p.publicado,
  visualizaciones: (p) => p.visualizaciones,
  engagement_pct: (p) => p.engagement_pct,
  clics_enlace: (p) => p.clics_enlace,
};

export function ListaPiezas({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  /** Marca global del dashboard: la lista la sigue. */
  marcaActual?: string;
  /** Rango global del dashboard: el periodo listado. */
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const [busqueda, setBusqueda] = React.useState("");
  const [seleccion, setSeleccion] = React.useState<PiezaMetrica | null>(null);
  const [detalleAbierto, setDetalleAbierto] = React.useState(false);

  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "piezas-listado", rangoActual ?? "", marca_ ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasPiezasListado({ rango: rangoActual, marca: marca_ }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const piezas = React.useMemo(() => data?.piezas ?? [], [data]);

  // Filtro por título (client-side), case/acentos-insensible básico.
  const filtradas = React.useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    if (!q) return piezas;
    return piezas.filter((p) => (p.titulo || "").toLowerCase().includes(q));
  }, [piezas, busqueda]);

  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<PiezaMetrica, ClaveOrden>(
    filtradas,
    ACCESORES,
    { clave: "publicado", direccion: "desc" },
  );

  function abrir(pieza: PiezaMetrica) {
    setSeleccion(pieza);
    setDetalleAbierto(true);
  }

  return (
    <Card>
      <CardHeader className="gap-3 pb-4">
        <div className="flex items-center gap-2">
          <ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          <CardTitle className="text-base">Todas las piezas del periodo</CardTitle>
        </div>
        <p className="text-sm text-muted-foreground">
          Listado completo de la fuente. Busca, ordena y toca una pieza para ver su
          desglose y su curva histórica.
        </p>
        <div className="relative max-w-sm">
          <Search
            className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por título…"
            className="pl-8"
            aria-label="Buscar piezas por título"
          />
        </div>
      </CardHeader>

      <CardContent className="px-0 pb-0">
        {isPending ? (
          <Skeleton className="mx-6 mb-6 h-72 rounded-lg" />
        ) : isError ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            No se pudo cargar el listado de piezas.
          </p>
        ) : piezas.length === 0 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Sin piezas en este periodo.
          </p>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Pieza</TableHead>
                  <CabeceraOrdenable
                    activa={estado.clave === "visualizaciones"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("visualizaciones")}
                    alinear="right"
                    className="text-right"
                  >
                    Vistas
                  </CabeceraOrdenable>
                  <CabeceraOrdenable
                    activa={estado.clave === "engagement_pct"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("engagement_pct")}
                    alinear="right"
                    className="text-right"
                  >
                    Eng.
                  </CabeceraOrdenable>
                  <CabeceraOrdenable
                    activa={estado.clave === "clics_enlace"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("clics_enlace")}
                    alinear="right"
                    className="hidden text-right sm:table-cell"
                  >
                    Clics
                  </CabeceraOrdenable>
                  <CabeceraOrdenable
                    activa={estado.clave === "publicado"}
                    direccion={estado.direccion}
                    onClick={() => alClicar("publicado")}
                    alinear="right"
                    className="hidden text-right sm:table-cell"
                  >
                    Fecha
                  </CabeceraOrdenable>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filasOrdenadas.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-muted-foreground">
                      Ninguna pieza coincide con “{busqueda}”.
                    </TableCell>
                  </TableRow>
                ) : (
                  filasOrdenadas.map((p) => (
                    <FilaPieza key={p.id} pieza={p} onAbrir={() => abrir(p)} />
                  ))
                )}
              </TableBody>
            </Table>
            <p className="px-6 py-3 text-xs text-muted-foreground">
              {filtradas.length} de {piezas.length} piezas
            </p>
          </>
        )}
      </CardContent>

      <DetallePieza
        pieza={seleccion}
        abierto={detalleAbierto}
        onOpenChange={setDetalleAbierto}
      />
    </Card>
  );
}

function FilaPieza({ pieza, onAbrir }: { pieza: PiezaMetrica; onAbrir: () => void }) {
  const titulo = pieza.titulo || "(sin título)";

  return (
    <TableRow
      onClick={onAbrir}
      tabIndex={0}
      role="button"
      aria-label={`Ver detalle de "${titulo}"`}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onAbrir();
        }
      }}
      className="cursor-pointer"
    >
      <TableCell className="max-w-[18rem]">
        <span className="block truncate font-medium" title={titulo}>
          {titulo}
        </span>
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          {nombreRed(pieza.plataforma)} · {nombreFormato(pieza.formato)}
          {pieza.url ? (
            <a
              href={pieza.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex items-center underline-offset-4 hover:underline"
              aria-label="Abrir el post en la red"
            >
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          ) : null}
        </span>
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {numeroCompacto(pieza.visualizaciones)}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {porcentaje(pieza.engagement_pct)}
      </TableCell>
      <TableCell className="hidden text-right tabular-nums sm:table-cell">
        {pieza.clics_enlace == null ? "—" : numeroCompacto(pieza.clics_enlace)}
      </TableCell>
      <TableCell className="hidden text-right text-xs text-muted-foreground tabular-nums sm:table-cell">
        {pieza.publicado}
      </TableCell>
    </TableRow>
  );
}
