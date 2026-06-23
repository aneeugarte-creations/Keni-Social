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
import { Bloque } from "./metricas/Bloque";
import { CompararPeriodos } from "./metricas/CompararPeriodos";
import { MARCA_TODAS, SelectorTiempo } from "./metricas/Controles";
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
  // La visibilidad de cada sección la resuelve su propio `<Bloque>` (toggle inline): una
  // sección oculta no se monta —ni consulta— y deja en su sitio una barra para mostrarla.

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
      {/* La visibilidad de secciones y el orden/visibilidad de columnas se editan AHORA en
          cada sección (toggle de ojo + kebab de columnas), no en un panel macro aparte. */}
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
        <div className="flex flex-col gap-8">
          {/* Cada sección es INDEPENDIENTE y consistente: su propio `<Bloque>` (gate) decide si
              se monta —oculta ⇒ ni se monta ni consulta, deja una barra fina para mostrarla—, y
              cada componente trae su cabecera uniforme (`<Seccion>`: título FUERA, controles
              propios, editor de campos en las tablas, y el toggle de ocultar). Sin colapsables,
              sin agrupaciones: el orden es la lectura (de lo general a lo concreto). */}
          {/* El aviso de ingesta encabeza el dashboard; no es sección configurable (sin toggle). */}
          <AlertaIngesta marcaActual={marca} rangoActual={rango} />

          <Bloque id="kpis">
            <Kpis total={reporteQuery.data.total} marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="analisis">
            <AnalisisNarrativo marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="tendencia">
            <TendenciaDiaria marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="marca-comparativa">
            <GraficaMarcas cuentas={reporteQuery.data.cuentas} />
          </Bloque>
          <Bloque id="marca-detalle">
            <TablaCuentas cuentas={reporteQuery.data.cuentas} onVerPiezas={verPiezasDeMarca} />
          </Bloque>
          <Bloque id="red-evolucion">
            <EvolucionRedes marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="red-detalle">
            <TablaRedes redes={reporteQuery.data.por_red} />
          </Bloque>
          <Bloque id="cobertura">
            <CoberturaRedes marcas={reporteQuery.data.cobertura_redes} />
          </Bloque>
          <Bloque id="seguidores">
            <CrecimientoSeguidores marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="desglose">
            <DesgloseInteracciones marcas={marcas} marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="crosstab">
            <Crosstab marcas={marcas} marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="por-serie">
            <GraficaPorSerie marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="por-linea">
            <MetricaPorLinea marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="correlacion">
            <Correlacion marcas={marcas} marcaActual={marca} rangoActual={rango} />
          </Bloque>
          <Bloque id="ads">
            <SeccionAds marcaActual={marca} rangoActual={rango} />
          </Bloque>
          {/* `piezasRef`: destino del drill-down desde "Detalle por marca". */}
          <section ref={piezasRef} className="scroll-mt-6 flex flex-col gap-8">
            <Bloque id="panorama">
              <PanoramaPiezas marcaActual={marca} />
            </Bloque>
            <Bloque id="distribucion">
              <DistribucionEngagement marcaActual={marca} rangoActual={rango} />
            </Bloque>
            <Bloque id="piezas-tabla">
              <PiezasConsolidada marcaActual={marca} rangoActual={rango} marcas={marcas} />
            </Bloque>
          </section>

          <Bloque id="comparativa">
            <CompararPeriodos opciones={opciones} rangoActual={rango} />
          </Bloque>
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
