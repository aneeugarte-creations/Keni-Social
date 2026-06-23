/**
 * Sección "Publicidad (Meta Ads)": el INORGÁNICO del periodo a nivel marca.
 *
 * Lista las campañas de pago (impresiones, gasto, clics) con sus totales, claramente
 * separadas de lo orgánico. Sólo aparece si hubo inversión con entrega en el periodo
 * (si no, no ensucia el dashboard). Reusa el stack del resto de Métricas: encuadre
 * uniforme `Seccion` + editor de columnas + tabla ordenable, con estados honestos
 * (carga / error / vacío).
 */
import { useQuery } from "@tanstack/react-query";
import { Megaphone } from "lucide-react";

import { marcaParam } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
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
import { nombreRed, numeroCompacto, numeroCompleto } from "@/lib/formato";
import type { CampaniaAdsMetrica } from "@/types";

import { CabeceraOrdenable } from "./CabeceraOrdenable";
import type { ColumnaMeta } from "./columnasMeta";
import { MARCA_TODAS } from "./Controles";
import { Seccion } from "./Seccion";
import { useOrdenTabla } from "./useOrdenTabla";
import { columnasVisibles, useVistaConfig } from "./vistaConfig";

function dinero(v: number, moneda: string): string {
  return `${v.toLocaleString("es-MX", { maximumFractionDigits: 0 })} ${moneda}`.trim();
}

type ClaveOrden = "impresiones" | "gasto" | "clics";

// Accesores de orden a nivel módulo: identidad estable entre renders.
const ACCESORES: Record<ClaveOrden, (a: CampaniaAdsMetrica) => number> = {
  impresiones: (a) => a.impresiones,
  gasto: (a) => a.gasto,
  clics: (a) => a.clics,
};

/** Columnas FIJAS de la tabla de campañas de Ads (orden base + etiquetas legibles). */
const COLUMNAS: ColumnaMeta[] = [
  { id: "campania", etiqueta: "Campaña" },
  { id: "red", etiqueta: "Red" },
  { id: "impresiones", etiqueta: "Impresiones" },
  { id: "gasto", etiqueta: "Gasto" },
  { id: "clics", etiqueta: "Clics" },
];

const IDS_BASE = COLUMNAS.map((c) => c.id);

/** ¿La columna es una métrica ordenable (cabecera con clic)? */
function esOrdenable(id: string): id is ClaveOrden {
  return id === "impresiones" || id === "gasto" || id === "clics";
}

export function SeccionAds({
  marcaActual = MARCA_TODAS,
  rangoActual,
}: {
  marcaActual?: string;
  rangoActual?: string;
}) {
  const marca_ = marcaParam(marcaActual);
  const red = useVistaConfig((s) => s.red);
  const { data, isPending, isError } = useQuery({
    queryKey: ["metricas", "ads", rangoActual ?? "", marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) => api.metricasAds({ rango: rangoActual, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rangoActual),
    staleTime: 2 * 60_000,
  });

  const ads = data?.ads ?? [];
  const { filasOrdenadas, estado, alClicar } = useOrdenTabla<CampaniaAdsMetrica, ClaveOrden>(
    ads,
    ACCESORES,
    { clave: "impresiones", direccion: "desc" },
  );

  const cfgGuardada = useVistaConfig((s) => s.columnas["ads"]);
  const cfg = cfgGuardada ?? { orden: IDS_BASE, ocultas: [] };
  const columnas = columnasVisibles(IDS_BASE, cfg);

  // Sin inversión con entrega en el periodo (o sin Ads conectado): no se muestra la sección.
  if (!isPending && !isError && (data?.total.campanias ?? 0) === 0) return null;

  const total = data?.total;
  const etiquetaDe = (id: string) => COLUMNAS.find((c) => c.id === id)?.etiqueta ?? id;
  const padding = (idx: number) =>
    [idx === 0 ? "pl-6" : "", idx === columnas.length - 1 ? "pr-6" : ""].filter(Boolean).join(" ");

  const encabezado = (id: string, idx: number) => {
    const clase = padding(idx) || undefined;
    if (esOrdenable(id)) {
      return (
        <CabeceraOrdenable
          key={id}
          activa={estado.clave === id}
          direccion={estado.direccion}
          onClick={() => alClicar(id)}
          alinear="right"
          className={clase}
        >
          {etiquetaDe(id)}
        </CabeceraOrdenable>
      );
    }
    return (
      <TableHead key={id} className={clase}>
        {etiquetaDe(id)}
      </TableHead>
    );
  };

  const celda = (a: CampaniaAdsMetrica, id: string, idx: number) => {
    const borde = padding(idx);
    if (id === "campania") {
      return (
        <TableCell key={id} className={borde || undefined}>
          <span className="block max-w-[28rem] truncate font-medium" title={a.nombre}>
            {a.nombre}
          </span>
        </TableCell>
      );
    }
    if (id === "red") {
      return (
        <TableCell key={id} className={borde || undefined}>
          <Badge variant="outline">{nombreRed(a.red)}</Badge>
        </TableCell>
      );
    }
    const claseNum = `text-right tabular-nums ${borde}`.trim();
    if (id === "impresiones") {
      return (
        <TableCell key={id} className={claseNum} title={numeroCompleto(a.impresiones)}>
          {numeroCompacto(a.impresiones)}
        </TableCell>
      );
    }
    if (id === "gasto") {
      return (
        <TableCell key={id} className={claseNum}>
          {dinero(a.gasto, a.moneda)}
        </TableCell>
      );
    }
    return (
      <TableCell key={id} className={claseNum}>
        {numeroCompacto(a.clics)}
      </TableCell>
    );
  };

  return (
    <Seccion
      id="ads"
      titulo="Publicidad"
      icono={Megaphone}
      descripcion="Campañas de pago"
      tablaId="ads"
      columnas={COLUMNAS}
    >
      <Card className="overflow-hidden py-2">
        {isPending ? (
          <div className="p-4">
            <Skeleton className="h-40 w-full rounded-lg" />
          </div>
        ) : isError ? (
          <p className="p-6 text-sm text-muted-foreground">No se pudieron cargar las campañas de Ads.</p>
        ) : (
          <>
            {total && (
              <div className="flex flex-wrap gap-x-8 gap-y-2 border-b px-6 py-4">
                {/* `total.visualizaciones` es la SUMA de la columna Impresiones (no son
                    vistas orgánicas): el término correcto en Ads es "Impresiones". */}
                <Kpi etiqueta="Impresiones" valor={numeroCompacto(total.visualizaciones)} titulo={numeroCompleto(total.visualizaciones)} />
                <Kpi etiqueta="Gasto" valor={dinero(total.gasto, total.moneda)} />
                <Kpi etiqueta="Campañas" valor={String(total.campanias)} />
                <Kpi etiqueta="Clics" valor={numeroCompacto(total.clics)} />
              </div>
            )}
            <Table>
              <TableHeader>
                <TableRow>{columnas.map(encabezado)}</TableRow>
              </TableHeader>
              <TableBody>
                {filasOrdenadas.map((a, i) => (
                  // Clave estable ante reordenaciones: nombre+red+inicio identifica la
                  // campaña; el índice solo entra si `inicio` llega vacío.
                  <TableRow key={`${a.nombre}-${a.red}-${a.inicio || i}`}>
                    {columnas.map((id, idx) => celda(a, id, idx))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </Card>
    </Seccion>
  );
}

function Kpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
  return (
    <div className="space-y-0.5">
      <p className="text-xs text-muted-foreground">{etiqueta}</p>
      <p className="text-lg font-semibold tabular-nums" title={titulo ?? valor}>
        {valor}
      </p>
    </div>
  );
}
