import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import {
  marcaCanonicaDesdeMetricas,
  marcaMetricasDesdeCanonica,
  marcaParam,
} from "@/components/comunes/selectores";
import { AccionesPagina } from "@/components/layout/encabezado";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import type { OpcionesMetricas } from "@/types";

import { BotonActualizar } from "./metricas/BotonActualizar";
import { CompararPeriodos } from "./metricas/CompararPeriodos";
import { MARCA_TODAS, SelectorTiempo } from "./metricas/Controles";
import { CoberturaRedes } from "./metricas/CoberturaRedes";
import { Correlacion } from "./metricas/Correlacion";
import { CrecimientoSeguidores } from "./metricas/CrecimientoSeguidores";
import { Crosstab } from "./metricas/Crosstab";
import { Descargas } from "./metricas/Descargas";
import { DesgloseInteracciones } from "./metricas/DesgloseInteracciones";
import { GraficaMarcas } from "./metricas/GraficaMarcas";
import { GraficaPorSerie } from "./metricas/GraficaPorSerie";
import { Kpis } from "./metricas/Kpis";
import { MetricaPorLinea } from "./metricas/MetricaPorLinea";
import { PiezasConsolidada } from "./metricas/PiezasConsolidada";
import { TablaCuentas } from "./metricas/TablaCuentas";
import { TablaRedes } from "./metricas/TablaRedes";
import { TendenciaDiaria } from "./metricas/TendenciaDiaria";

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
        <EsqueletoDashboard />
      </>
    );
  }

  if (opcionesQuery.isError) {
    return (
      <>
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

/** Cuerpo del dashboard una vez que tenemos las opciones disponibles. */
function DashboardMetricas({ opciones }: { opciones: OpcionesMetricas }) {
  const { marcas, rangos } = opciones;
  const location = useLocation();
  const navigate = useNavigate();
  // La marca del dashboard la MANDA el switch global de la barra superior (workspace);
  // Analíticas no tiene selector propio: respeta el global. `marcaActiva` es el id
  // canónico (o null = "Todas", agregado solo para admin).
  const { marcaActiva, cambiarMarca } = useMarcaActiva();

  // Deep-link: si llegamos con una marca en el `state` de navegación (canónica), la
  // fijamos en el switch global una vez y limpiamos el state para que no reaparezca al
  // volver atrás o refrescar.
  React.useEffect(() => {
    const estado = location.state as { marca?: string } | null;
    if (estado?.marca != null) {
      cambiarMarca(estado.marca);
      navigate(location.pathname + location.search, { replace: true, state: null });
    }
    // Solo al montar / cambiar el state de navegación.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  // La marca acotada DERIVA de la marca activa global, en la forma id_metricas que usa
  // esta frontera. Sin marca activa (o fuera del catálogo) → agregado ("Todas").
  const marca = React.useMemo(() => {
    if (!marcaActiva) return MARCA_TODAS;
    const idMetricas = marcaMetricasDesdeCanonica(marcaActiva);
    return marcas.some((m) => m.id === idMetricas) ? idMetricas : MARCA_TODAS;
  }, [marcaActiva, marcas]);
  const [rango, setRango] = React.useState(rangos[0]?.id ?? "");

  const marca_ = marcaParam(marca);

  // Drill-down: al clicar una marca en "Por marca", enfocamos TODO el dashboard en esa
  // marca cambiando el switch global (lectura: del agregado al detalle) y hacemos scroll
  // a la tabla de piezas.
  const piezasRef = React.useRef<HTMLDivElement>(null);
  const verPiezasDeMarca = React.useCallback(
    (marcaId: string) => {
      cambiarMarca(marcaCanonicaDesdeMetricas(marcaId));
      piezasRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    [cambiarMarca],
  );

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
      <SelectorTiempo rangos={rangos} valor={rango} onCambio={setRango} />
    </div>
  );

  return (
    <>
      <AccionesPagina>{acciones}</AccionesPagina>

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
          {/* La marca la manda el switch global de la topbar: no se repite aquí. Solo se
              conserva el rango temporal del corte, como texto sutil junto a las descargas. */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">{reporteQuery.data.etiqueta_rango}</p>
            <Descargas rango={rango} marca={marca_} />
          </div>

          <Kpis total={reporteQuery.data.total} />
          <TendenciaDiaria marcaActual={marca} rangoActual={rango} />

          {/* Por marca: la comparativa visual y la tabla detallada son dos lecturas
              del MISMO corte (cada cuenta), así que van juntas bajo un solo
              encabezado. La tabla permite drill-down a las piezas de cada marca. */}
          <div className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Por marca</h2>
            <GraficaMarcas cuentas={reporteQuery.data.cuentas} />
            <TablaCuentas
              cuentas={reporteQuery.data.cuentas}
              onVerPiezas={verPiezasDeMarca}
            />
          </div>
          {/* Por red: agrega las plataformas de todas las marcas del reporte. */}
          <div className="space-y-3">
            <h2 className="text-lg font-semibold tracking-tight">Por red</h2>
            <TablaRedes redes={reporteQuery.data.por_red} />
            {/* Auditoría: TODAS las redes de cada marca (aunque no tengan datos) con
                el motivo de por qué no aportan. Hace visibles las redes vacías. */}
            <CoberturaRedes marcas={reporteQuery.data.cobertura_redes} />
          </div>

          {/* Estrategia digital: lectura de alto nivel (más allá del día a día),
              ANTES del detalle granular de piezas. Crecimiento de audiencia, de qué
              se compone el engagement, qué formatos rinden y correlación. El tráfico
              web (clics a enlace) vive ahora como columna en "Piezas del periodo".
              Siguen marca/rango global como el resto del dashboard. */}
          <section className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold tracking-tight">Estrategia digital</h2>
              <p className="text-sm text-muted-foreground">
                Crecimiento de audiencia, composición del engagement y qué formatos
                rinden mejor.
              </p>
            </div>
            <CrecimientoSeguidores marcaActual={marca} rangoActual={rango} />
            <DesgloseInteracciones marcas={marcas} marcaActual={marca} rangoActual={rango} />
            <Crosstab marcas={marcas} marcaActual={marca} rangoActual={rango} />
            <Correlacion marcas={marcas} marcaActual={marca} rangoActual={rango} />
          </section>

          {/* Detalle granular de piezas: del alto nivel al caso concreto. UNA tabla
              consolidada (fusiona Lista + Top/Peores + Rendimiento): filtros marca/línea/
              red + búsqueda, stats media/mediana, orden por columna (Vistas desc=top,
              asc=peores), paginación por día y drill-down. El drill-down desde la tabla
              por marca fija su filtro de marca. */}
          <div ref={piezasRef} className="scroll-mt-6">
            <PiezasConsolidada marcaActual={marca} rangoActual={rango} marcas={marcas} />
          </div>
          {/* Rendimiento por serie/tipo: cruza piezas de Metricool con el tablero de la
              BD para clasificarlas (tipo_contenido + etiquetas). Sigue marca/rango global. */}
          <GraficaPorSerie marcaActual={marca} rangoActual={rango} />
          {/* Rendimiento por LÍNEA de contenido (vertical) y por ORIGEN del periodo:
              dos tablas con piezas/visualizaciones/interacciones/engagement. Sigue
              marca/rango global como el resto del dashboard. */}
          <MetricaPorLinea marcaActual={marca} rangoActual={rango} />

          <CompararPeriodos opciones={opciones} rangoActual={rango} />
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
