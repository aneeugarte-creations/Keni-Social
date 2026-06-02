import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { marcaParam } from "@/components/comunes/selectores";
import { PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import type { OpcionesMetricas } from "@/types";

import { AnalisisDiario } from "./metricas/AnalisisDiario";
import { BotonActualizar } from "./metricas/BotonActualizar";
import { CompararPeriodos } from "./metricas/CompararPeriodos";
import { MARCA_TODAS, SelectorMarca, SelectorTiempo } from "./metricas/Controles";
import { Correlacion } from "./metricas/Correlacion";
import { CrecimientoSeguidores } from "./metricas/CrecimientoSeguidores";
import { Crosstab } from "./metricas/Crosstab";
import { Descargas } from "./metricas/Descargas";
import { DesgloseInteracciones } from "./metricas/DesgloseInteracciones";
import { GraficaMarcas } from "./metricas/GraficaMarcas";
import { GraficaPorSerie } from "./metricas/GraficaPorSerie";
import { Kpis } from "./metricas/Kpis";
import { PiezasAnalitica } from "./metricas/PiezasAnalitica";
import { PiezasRendimiento } from "./metricas/PiezasRendimiento";
import { TablaCuentas } from "./metricas/TablaCuentas";
import { TablaRedes } from "./metricas/TablaRedes";
import { TendenciaDiaria } from "./metricas/TendenciaDiaria";

/** Etiqueta legible cuando el reporte no acota marca (backend devuelve `""`). */
const ETIQUETA_TODAS = "Todas las marcas";

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
    <PageHeader titulo="Métricas" acciones={acciones} />
  );
}

/** Cuerpo del dashboard una vez que tenemos las opciones disponibles. */
function DashboardMetricas({ opciones }: { opciones: OpcionesMetricas }) {
  const { marcas, rangos } = opciones;
  const location = useLocation();
  const navigate = useNavigate();

  // A-5: usamos useState con inicializador lazy en vez de useMemo para capturar
  // la marca inicial exactamente una vez al montar, sin recalcular en re-renders.
  const [marca, setMarca] = React.useState(() => {
    const estado = location.state as { marca?: string } | null;
    const desdeQuery = new URLSearchParams(location.search).get("marca") ?? undefined;
    const candidata = estado?.marca ?? desdeQuery;
    return candidata && marcas.some((m) => m.id === candidata) ? candidata : MARCA_TODAS;
  });
  const [rango, setRango] = React.useState(rangos[0]?.id ?? "");

  // Limpiamos el `state` de navegación tras consumirlo, para que no reaparezca
  // al volver atrás o refrescar (la query, si la hubiera, se deja intacta).
  React.useEffect(() => {
    if ((location.state as { marca?: string } | null)?.marca != null) {
      navigate(location.pathname + location.search, { replace: true, state: null });
    }
    // Solo al montar / cambiar el state de navegación.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const marca_ = marcaParam(marca);

  const reporteQuery = useQuery({
    queryKey: ["metricas", "reporte", rango, marca_ ?? "todas"],
    queryFn: ({ signal }) => api.metricasReporte({ rango, marca: marca_ }, signal),
    enabled: Boolean(rango),
    // El dato se sirve de la cache del backend (refresco en 2º plano); no hace falta
    // re-pedirlo cada 30 s. El botón "Actualizar" lo invalida cuando hay dato fresco.
    staleTime: 5 * 60_000,
  });

  const acciones = (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <BotonActualizar
        rango={rango}
        marca={marca_}
        generadoEn={reporteQuery.data?.generado_en}
      />
      <SelectorMarca marcas={marcas} valor={marca} onCambio={setMarca} />
      <SelectorTiempo rangos={rangos} valor={rango} onCambio={setRango} />
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
              Mostrando{" "}
              <span className="font-medium text-foreground">
                {reporteQuery.data.marca || ETIQUETA_TODAS}
              </span>{" "}
              · {reporteQuery.data.etiqueta_rango}
            </p>
            <Descargas rango={rango} marca={marca_} />
          </div>

          <Kpis total={reporteQuery.data.total} />
          {/* Lectura "qué cambió y por qué" + siguiente paso (F6/#146): la
              narrativa va arriba para que el día a día empiece por la lectura,
              no por la tabla (principio UX #1: el veredicto primero). */}
          <AnalisisDiario marcaActual={marca} rangoActual={rango} />
          <TendenciaDiaria marcaActual={marca} rangoActual={rango} />
          <GraficaMarcas cuentas={reporteQuery.data.cuentas} />
          {/* Dos lecturas del mismo periodo: por marca (cada cuenta) y por red
              (agregando las plataformas de todas las marcas del reporte). */}
          <div className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Por marca</h2>
            <TablaCuentas cuentas={reporteQuery.data.cuentas} />
          </div>
          <div className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Por red</h2>
            <TablaRedes redes={reporteQuery.data.por_red} />
          </div>
          <PiezasAnalitica opciones={opciones} rangoActual={rango} />
          {/* Rendimiento por serie/tipo: cruza piezas de Metricool con el tablero de la
              BD para clasificarlas (tipo_contenido + etiquetas). Sigue marca/rango global. */}
          <GraficaPorSerie marcaActual={marca} rangoActual={rango} />
          {/* Drill-down marca -> pieza: piezas publicadas con su rendimiento real
              (misma fuente única, Metricool) y enlace a la pieza en el tablero. */}
          <PiezasRendimiento opciones={opciones} />

          {/* Estrategia digital: lectura más allá del día a día. Crecimiento de
              audiencia, de qué se compone el engagement, qué formatos rinden y
              cómo se relaciona publicar con ganar seguidores. Siguen marca/rango
              global como el resto del dashboard. */}
          <section className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">Estrategia digital</h2>
              <p className="text-sm text-muted-foreground">
                Crecimiento de audiencia, composición del engagement y qué formatos
                rinden mejor en el periodo seleccionado.
              </p>
            </div>
            <CrecimientoSeguidores marcaActual={marca} rangoActual={rango} />
            <DesgloseInteracciones marcaActual={marca} rangoActual={rango} />
            <Crosstab marcaActual={marca} rangoActual={rango} />
            <Correlacion marcaActual={marca} rangoActual={rango} />
          </section>

          <CompararPeriodos opciones={opciones} marcaActual={marca} rangoActual={rango} />
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
