import { useQuery } from "@tanstack/react-query";
import * as React from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import {
  marcaCanonicaDesdeMetricas,
  marcaMetricasDesdeCanonica,
  marcaParam,
} from "@/components/comunes/selectores";
import { MenuAcciones } from "@/components/layout/MenuAcciones";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import type { OpcionesMetricas } from "@/types";

import { AlertaIngesta } from "./metricas/AlertaIngesta";
import { AnalisisNarrativo } from "./metricas/AnalisisNarrativo";
import {
  EstadoActualizacion,
  ItemActualizarMetricas,
  useActualizarMetricas,
} from "./metricas/BotonActualizar";
import { CompararPeriodos } from "./metricas/CompararPeriodos";
import { MARCA_TODAS, SelectorTiempo } from "./metricas/Controles";
import { ConfiguracionVista } from "./metricas/ConfiguracionVista";
import { SelectorRed, etiquetaRed } from "./metricas/SelectorRed";
import { useVistaConfig } from "./metricas/vistaConfig";
import { CoberturaRedes } from "./metricas/CoberturaRedes";
import { Correlacion } from "./metricas/Correlacion";
import { CrecimientoSeguidores } from "./metricas/CrecimientoSeguidores";
import { Crosstab } from "./metricas/Crosstab";
import { ItemsDescarga } from "./metricas/Descargas";
import { DesgloseInteracciones } from "./metricas/DesgloseInteracciones";
import { etiquetaPeriodo } from "./metricas/exportarPdf";
import { DistribucionEngagement } from "./metricas/DistribucionEngagement";
import { EvolucionRedes } from "./metricas/EvolucionRedes";
import { GraficaMarcas } from "./metricas/GraficaMarcas";
import { GraficaPorSerie } from "./metricas/GraficaPorSerie";
import { Kpis } from "./metricas/Kpis";
import { MetricaPorLinea } from "./metricas/MetricaPorLinea";
import { PanoramaPiezas } from "./metricas/PanoramaPiezas";
import { PiezasConsolidada } from "./metricas/PiezasConsolidada";
import { diasDePeriodo } from "./metricas/rango";
import { SeccionAds } from "./metricas/SeccionAds";
import { TablaCuentas } from "./metricas/TablaCuentas";
import { TablaRedes } from "./metricas/TablaRedes";
import { TendenciaDiaria } from "./metricas/TendenciaDiaria";
import { VistasGuardadas } from "./metricas/VistasGuardadas";

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
  const [searchParams, setSearchParams] = useSearchParams();
  // La marca del dashboard la MANDA el switch global de la barra superior (workspace);
  // Analíticas no tiene selector propio: respeta el global. `marcaActiva` es el id
  // canónico (o null = "Todas", agregado solo para admin).
  const { marcaActiva, cambiarMarca } = useMarcaActiva();
  // Red única en foco (switch propio de Analíticas, persistido en `vistaConfig`): `null`
  // = todas. Filtra TODA la página (cada sub-sección la incluye en su consulta).
  const red = useVistaConfig((s) => s.red);
  // Visibilidad de secciones (panel "Configurar vista"): un id ausente = visible.
  const secciones = useVistaConfig((s) => s.secciones);
  const vis = React.useCallback((id: string) => secciones[id] !== false, [secciones]);
  // Las secciones-grupo (Estrategia, Piezas) se ocultan enteras —encabezado incluido—
  // cuando todos sus sub-bloques están ocultos.
  const algunaEstrategia = [
    "seguidores",
    "desglose",
    "crosstab",
    "por-serie",
    "por-linea",
    "correlacion",
    "ads",
  ].some(vis);
  const algunaPiezas = ["panorama", "distribucion", "piezas-tabla"].some(vis);

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
  // El periodo viaja en la URL (`?periodo=`) para que los enlaces profundos y el
  // historial conserven el corte temporal. Al montar se acepta solo un token válido:
  // un preset del backend o un token `mes:`/`rango:` que resuelva a días.
  const [rango, setRango] = React.useState(() => {
    const token = searchParams.get("periodo");
    if (token && (rangos.some((r) => r.id === token) || diasDePeriodo(token) != null)) {
      return token;
    }
    return rangos[0]?.id ?? "";
  });
  // Único punto de cambio del rango: actualiza el estado Y refleja el token en la URL
  // (replace: cambiar de periodo no debe apilar entradas en el historial).
  const cambiarRango = React.useCallback(
    (token: string) => {
      setRango(token);
      setSearchParams(
        (prev) => {
          prev.set("periodo", token);
          return prev;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  const marca_ = marcaParam(marca);

  // Etiquetas legibles para la portada del PDF y los nombres de archivo.
  const marcaEtiqueta = marca_
    ? (marcas.find((m) => m.id === marca_)?.nombre ?? marca_)
    : "Todas las marcas";
  const redEtiqueta = etiquetaRed(red);
  const periodoEtiqueta = etiquetaPeriodo(rango, rangos);

  // Drill-down: al clicar una marca en "Por marca", enfocamos TODO el dashboard en esa
  // marca cambiando el switch global (lectura: del agregado al detalle) y hacemos scroll
  // a la sección de piezas.
  const piezasRef = React.useRef<HTMLElement>(null);
  const verPiezasDeMarca = React.useCallback(
    (marcaId: string) => {
      cambiarMarca(marcaCanonicaDesdeMetricas(marcaId));
      piezasRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    },
    [cambiarMarca],
  );

  const reporteQuery = useQuery({
    queryKey: ["metricas", "reporte", rango, marca_ ?? "todas", red ?? "todas"],
    queryFn: ({ signal }) =>
      api.metricasReporte({ rango, marca: marca_, red: red ?? undefined }, signal),
    enabled: Boolean(rango),
    // El dato se sirve de la cache del backend (refresco en 2º plano); no hace falta
    // re-pedirlo cada 30 s. El botón "Actualizar" lo invalida cuando hay dato fresco.
    staleTime: 5 * 60_000,
  });

  const refresco = useActualizarMetricas({
    rango,
    marca: marca_,
    generadoEn: reporteQuery.data?.generado_en,
  });

  // Sin rangos del backend no hay nada que consultar: error honesto en vez del
  // esqueleto infinito que dejaría la query deshabilitada (enabled: false).
  if (!rango) {
    return (
      <BloqueError
        titulo="No hay periodos disponibles"
        mensaje="Sin periodos disponibles en el backend."
        onReintentar={() => window.location.reload()}
      />
    );
  }

  // Reparto canónico de cabecera: el FILTRO de vista (rango temporal) queda inline con su
  // indicador de frescura; la ACCIÓN (Actualizar) va al menú "⋮". La conexión Metricool se
  // gestiona ahora en Sistema → Proveedores (junto al resto de conexiones a externos), no aquí.
  // El estado del refresco vive aquí (hook): el item del menú se desmonta al cerrarse y el
  // polling le sobrevive.
  // Toolbar PROPIA del dashboard (fila debajo de las pestañas), NO en la barra superior
  // compartida: con tantos filtros (periodo, red, configurar, vistas, acciones) la cabecera
  // se saturaba y solapaba con las pestañas/título. `flex-wrap` evita cualquier solape: en
  // pantallas estrechas los controles fluyen a la siguiente línea.
  const toolbar = (
    <div className="flex flex-wrap items-center gap-2 border-b border-border/60 pb-3">
      <EstadoActualizacion
        refrescando={refresco.refrescando}
        generadoEn={reporteQuery.data?.generado_en}
      />
      <SelectorTiempo rangos={rangos} valor={rango} onCambio={cambiarRango} />
      {/* Selector de RED único: filtra toda la página (escribe en `vistaConfig.red`). */}
      <SelectorRed />
      {/* Panel "Configurar vista": qué secciones se muestran y orden/visibilidad de columnas. */}
      <ConfiguracionVista />
      {/* Vistas guardadas: presets nombrados (config de vista + marca + periodo). */}
      <VistasGuardadas
        marcaActual={marcaActiva}
        periodoActual={rango}
        onAplicar={(marca, periodo) => {
          cambiarMarca(marca);
          cambiarRango(periodo);
        }}
      />
      {/* El "⋮" agrupa las ACCIONES (descargar CSV/PDF, actualizar) para no saturar la barra:
          inline quedan solo los FILTROS (periodo, red) y Configurar vista / Vistas guardadas. */}
      <MenuAcciones>
        <ItemsDescarga
          rango={rango}
          marca={marca_}
          marcaEtiqueta={marcaEtiqueta}
          redEtiqueta={redEtiqueta}
          periodoEtiqueta={periodoEtiqueta}
          generadoEn={reporteQuery.data?.generado_en}
        />
        <div role="separator" aria-orientation="horizontal" className="my-1 h-px bg-border" />
        <ItemActualizarMetricas
          actualizar={refresco.actualizar}
          deshabilitado={refresco.deshabilitado}
        />
      </MenuAcciones>
    </div>
  );

  return (
    <div className="space-y-6">
      {toolbar}

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
        <div data-deck-root className="flex flex-col gap-8">
          {/* `data-deck-root` marca el cuerpo capturable por el export a PDF; cada bloque
              `data-slide="…"` es una diapositiva (su valor es el título de la diapositiva).
              Usamos `flex flex-col gap-*` (no `space-y-*`) para que los envoltorios de
              diapositiva no alteren el espaciado vertical. */}
          {/* Mientras la fuente sea sintética, el aviso encabeza el dashboard: que
              nadie confunda las cifras de demostración con datos reales del cliente. */}
          {/* Ni marca ni rango se repiten en el cuerpo: la marca la manda el switch global
              de la topbar y el corte temporal ya lo enseña el selector de la cabecera. */}
          <AlertaIngesta marcaActual={marca} rangoActual={rango} />

          {vis("kpis") && (
            <div data-slide="Resumen del periodo">
              <Kpis total={reporteQuery.data.total} marcaActual={marca} rangoActual={rango} />
            </div>
          )}
          {/* Lectura narrativa del periodo (qué pasó y por qué), entre los números
              crudos y la tendencia diaria. Sigue marca/rango global. */}
          {vis("analisis") && (
            <div data-slide="Análisis del periodo">
              <AnalisisNarrativo marcaActual={marca} rangoActual={rango} />
            </div>
          )}
          {vis("tendencia") && (
            <div data-slide="Tendencia diaria">
              <TendenciaDiaria marcaActual={marca} rangoActual={rango} />
            </div>
          )}

          {/* Por marca: la comparativa visual y la tabla detallada son dos lecturas
              del MISMO corte (cada cuenta), así que van juntas bajo un solo
              encabezado. La tabla permite drill-down a las piezas de cada marca. */}
          {vis("por-marca") && (
            <section className="flex flex-col gap-4">
              <h2 className="text-lg font-semibold tracking-tight">Por marca</h2>
              <div data-slide="Por marca · comparativa">
                <GraficaMarcas cuentas={reporteQuery.data.cuentas} desnudo />
              </div>
              <div data-slide="Por marca · detalle">
                <Card className="overflow-hidden py-2">
                  <TablaCuentas
                    cuentas={reporteQuery.data.cuentas}
                    onVerPiezas={verPiezasDeMarca}
                    desnudo
                  />
                </Card>
              </div>
            </section>
          )}
          {/* Por red: agrega las plataformas de todas las marcas del reporte. */}
          {(vis("por-red") || vis("cobertura")) && (
            <section className="flex flex-col gap-4">
              <h2 className="text-lg font-semibold tracking-tight">Por red</h2>
              {vis("por-red") && (
                <>
                  <div data-slide="Por red · evolución">
                    <EvolucionRedes marcaActual={marca} rangoActual={rango} desnudo />
                  </div>
                  <div data-slide="Por red · detalle">
                    <Card className="overflow-hidden py-2">
                      <TablaRedes redes={reporteQuery.data.por_red} desnudo />
                    </Card>
                  </div>
                </>
              )}
              {vis("cobertura") && (
                <div data-slide="Cobertura por red">
                  <CoberturaRedes marcas={reporteQuery.data.cobertura_redes} />
                </div>
              )}
            </section>
          )}

          {/* Estrategia digital: lectura de alto nivel (más allá del día a día),
              ANTES del detalle granular de piezas. Crecimiento de audiencia, de qué
              se compone el engagement, qué formatos rinden y correlación. El tráfico
              web (clics a enlace) vive ahora como columna en "Piezas del periodo".
              Siguen marca/rango global como el resto del dashboard. */}
          {algunaEstrategia && (
            <section className="flex flex-col gap-4">
              <div className="space-y-1">
                <h2 className="text-lg font-semibold tracking-tight">Estrategia digital</h2>
              </div>
              {vis("seguidores") && (
                <div data-slide="Crecimiento de seguidores">
                  <CrecimientoSeguidores marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {vis("desglose") && (
                <div data-slide="Desglose de interacciones">
                  <DesgloseInteracciones marcas={marcas} marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {vis("crosstab") && (
                <div data-slide="Cruce de métricas">
                  <Crosstab marcas={marcas} marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {/* Rendimiento por serie/tipo: cruza piezas de Metricool con el tablero de la
                  BD para clasificarlas (tipo_contenido + etiquetas). Sigue marca/rango global. */}
              {vis("por-serie") && (
                <div data-slide="Rendimiento por serie">
                  <GraficaPorSerie marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {/* Rendimiento por LÍNEA de contenido (vertical) y por ORIGEN del periodo:
                  dos tablas con piezas/visualizaciones/interacciones/engagement. Sigue
                  marca/rango global como el resto del dashboard. */}
              {vis("por-linea") && (
                <div data-slide="Rendimiento por línea">
                  <MetricaPorLinea marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {vis("correlacion") && (
                <div data-slide="Correlación con seguidores">
                  <Correlacion marcas={marcas} marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {vis("ads") && (
                <div data-slide="Publicidad pagada">
                  <SeccionAds marcaActual={marca} rangoActual={rango} />
                </div>
              )}
            </section>
          )}

          {/* Detalle granular de piezas: del alto nivel al caso concreto. UNA tabla
              consolidada (fusiona Lista + Top/Peores + Rendimiento): filtros marca/línea/
              red + búsqueda, stats media/mediana, orden por columna (Vistas desc=top,
              asc=peores), paginación por día y drill-down. El drill-down desde la tabla
              por marca fija su filtro de marca. */}
          {algunaPiezas && (
            <section ref={piezasRef} className="scroll-mt-6 flex flex-col gap-4">
              <h2 className="text-lg font-semibold tracking-tight">Piezas</h2>
              {/* El Panorama usa query y periodo PROPIOS (selector 7d/30d/90d/1año); solo
                  EvolucionRedes comparte caché con PiezasConsolidada. */}
              {vis("panorama") && (
                <div data-slide="Panorama de piezas">
                  <PanoramaPiezas marcaActual={marca} />
                </div>
              )}
              {/* Cómo se reparte el engagement entre las piezas del periodo (distribución,
                  no solo medias): contexto antes de bajar a la tabla consolidada. */}
              {vis("distribucion") && (
                <div data-slide="Distribución de engagement">
                  <DistribucionEngagement marcaActual={marca} rangoActual={rango} />
                </div>
              )}
              {vis("piezas-tabla") && (
                <div data-slide="Piezas del periodo">
                  <PiezasConsolidada marcaActual={marca} rangoActual={rango} marcas={marcas} />
                </div>
              )}
            </section>
          )}

          {vis("comparativa") && (
            <CompararPeriodos opciones={opciones} rangoActual={rango} />
          )}
        </div>
      )}
    </div>
  );
}

/** Esqueleto de carga que imita la estructura del dashboard (KPIs, rango, Tendencia…). */
function EsqueletoDashboard() {
  return (
    <div className="space-y-8">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      {/* Fila de rango temporal. */}
      <Skeleton className="h-8 w-48" />
      {/* Tendencia diaria (Card completa → rounded-xl). */}
      <Skeleton className="h-72 w-full rounded-xl" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Skeleton className="h-80 w-full rounded-xl lg:col-span-3" />
        <Skeleton className="h-80 w-full rounded-xl lg:col-span-2" />
      </div>
      <Skeleton className="h-64 w-full rounded-xl" />
    </div>
  );
}
