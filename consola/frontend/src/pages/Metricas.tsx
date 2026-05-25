import { useQuery } from "@tanstack/react-query";
import { AlertCircle, RefreshCw } from "lucide-react";
import * as React from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { OpcionesMetricas } from "@/types";

import { CompararPeriodos } from "./metricas/CompararPeriodos";
import { MARCA_TODAS, SelectorMarca, SelectorRango } from "./metricas/Controles";
import { Descargas } from "./metricas/Descargas";
import { GraficaMarcas } from "./metricas/GraficaMarcas";
import { Kpis } from "./metricas/Kpis";
import { TablaCuentas } from "./metricas/TablaCuentas";

/**
 * Dashboard de Métricas multi-marca.
 *
 * Carga primero las opciones (marcas y rangos disponibles), inicializa los
 * controles y consulta el reporte vía React Query. El reporte se vuelve a pedir
 * automáticamente al cambiar marca o rango. Maneja los tres estados
 * (cargando / error / datos) con soporte impecable de modo claro y oscuro.
 */
export default function Metricas() {
  const opcionesQuery = useQuery({
    queryKey: ["metricas", "opciones"],
    queryFn: ({ signal }) => api.metricasOpciones(signal),
  });

  if (opcionesQuery.isPending) {
    return (
      <>
        <CabeceraMetricas />
        <EsqueletoDashboard />
      </>
    );
  }

  if (opcionesQuery.isError) {
    return (
      <>
        <CabeceraMetricas />
        <BloqueError
          titulo="No se pudieron cargar las métricas"
          mensaje={
            opcionesQuery.error instanceof Error ? opcionesQuery.error.message : undefined
          }
          onReintentar={() => void opcionesQuery.refetch()}
          cargando={opcionesQuery.isFetching}
        />
      </>
    );
  }

  return <DashboardMetricas opciones={opcionesQuery.data} />;
}

function CabeceraMetricas({ acciones }: { acciones?: React.ReactNode }) {
  return (
    <PageHeader
      titulo="Métricas"
      descripcion="Visualizaciones, alcance e interacciones de tus marcas, con comparativas entre periodos."
      acciones={acciones}
    />
  );
}

/** Cuerpo del dashboard una vez que tenemos las opciones disponibles. */
function DashboardMetricas({ opciones }: { opciones: OpcionesMetricas }) {
  const { marcas, rangos } = opciones;

  const [marca, setMarca] = React.useState(MARCA_TODAS);
  const [rango, setRango] = React.useState(rangos[0]?.id ?? "");

  const marcaParam = marca === MARCA_TODAS ? undefined : marca;

  const reporteQuery = useQuery({
    queryKey: ["metricas", "reporte", rango, marcaParam ?? "todas"],
    queryFn: ({ signal }) => api.metricasReporte({ rango, marca: marcaParam }, signal),
    enabled: Boolean(rango),
  });

  const acciones = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <SelectorMarca marcas={marcas} valor={marca} onCambio={setMarca} />
      <SelectorRango rangos={rangos} valor={rango} onCambio={setRango} />
    </div>
  );

  return (
    <>
      <CabeceraMetricas acciones={acciones} />

      {reporteQuery.isPending ? (
        <EsqueletoDashboard />
      ) : reporteQuery.isError ? (
        <BloqueError
          titulo="No se pudo cargar el reporte"
          mensaje={
            reporteQuery.error instanceof Error ? reporteQuery.error.message : undefined
          }
          onReintentar={() => void reporteQuery.refetch()}
          cargando={reporteQuery.isFetching}
        />
      ) : (
        <div className="space-y-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              Mostrando <span className="font-medium text-foreground">{reporteQuery.data.marca}</span>{" "}
              · {reporteQuery.data.etiqueta_rango}
            </p>
            <Descargas rango={rango} marca={marcaParam} />
          </div>

          <Kpis total={reporteQuery.data.total} />
          <GraficaMarcas cuentas={reporteQuery.data.cuentas} />
          <TablaCuentas cuentas={reporteQuery.data.cuentas} />
          <CompararPeriodos opciones={opciones} />
        </div>
      )}
    </>
  );
}

/** Esqueleto de carga que imita la estructura del dashboard. */
function EsqueletoDashboard() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Skeleton className="h-80 w-full rounded-xl lg:col-span-3" />
        <Skeleton className="h-80 w-full rounded-xl lg:col-span-2" />
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}

/** Bloque de error reutilizable con botón de reintento. */
function BloqueError({
  titulo,
  mensaje,
  onReintentar,
  cargando,
}: {
  titulo: string;
  mensaje?: string;
  onReintentar: () => void;
  cargando: boolean;
}) {
  return (
    <Card className="border-destructive/40">
      <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertCircle className="h-6 w-6" />
        </div>
        <div className="space-y-1">
          <p className="font-medium">{titulo}</p>
          <p className="max-w-md text-sm text-muted-foreground">
            {mensaje ?? "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento."}
          </p>
        </div>
        <Button onClick={onReintentar} disabled={cargando}>
          <RefreshCw className={cn("h-4 w-4", cargando && "animate-spin")} />
          Reintentar
        </Button>
      </CardContent>
    </Card>
  );
}
