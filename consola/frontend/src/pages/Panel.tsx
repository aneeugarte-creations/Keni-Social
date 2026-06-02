import { useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  ClipboardCheck,
  ExternalLink,
  Lightbulb,
  ListChecks,
  Newspaper,
  Recycle,
  Sparkles,
  TrendingDown,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import { numeroCompacto, porcentaje } from "@/lib/formato";
import type {
  AlertaRendimiento,
  ItemListaDia,
  PicoPanel,
  ProximaPanel,
  Publicacion,
} from "@/types";

import { formatearFechaHora, tiempoRelativo } from "./publicaciones/meta";

const CABECERA = {
  titulo: "Panel",
  descripcion:
    "Un vistazo: rendimiento del periodo, qué espera revisión y qué se publica pronto.",
};

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Enlace al tablero (Pendientes) abriendo el detalle de un contenido por su id.
 *  Opcionalmente fija el workspace (`marca`) para que la pieza no quede filtrada fuera. */
function enlaceAbrir(contenidoId: string, marca?: string): string {
  const params = new URLSearchParams({ abrir: contenidoId });
  if (marca) params.set("marca", marca);
  return `/parrilla/pendientes?${params.toString()}`;
}

/** Estilo compartido para hacer una fila del panel clicable (hover) sin romper el layout. */
const FILA_CLICABLE = "-mx-2 rounded-md px-2 transition-colors hover:bg-muted/60";

/** Esqueleto de carga del panel (KPIs + dos columnas). */
function EsqueletoPanel() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
    </div>
  );
}

/** Flecha + color según la dirección del movimiento ("sube" | "baja" | "estable"). */
function IconoDireccion({ direccion }: { direccion: string }) {
  if (direccion === "sube") {
    return <ArrowUpRight className="h-4 w-4 text-emerald-600 dark:text-emerald-400" aria-hidden="true" />;
  }
  if (direccion === "baja") {
    return <ArrowDownRight className="h-4 w-4 text-rose-600 dark:text-rose-400" aria-hidden="true" />;
  }
  return <ArrowRight className="h-4 w-4 text-muted-foreground" aria-hidden="true" />;
}

/** Fila de un "pico" (movimiento destacado del periodo). */
function FilaPico({ pico }: { pico: PicoPanel }) {
  return (
    <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{pico.marca}</p>
        {pico.pieza_titulo && (
          <p className="truncate text-xs text-muted-foreground">{pico.pieza_titulo}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5 tabular-nums">
        <IconoDireccion direccion={pico.direccion} />
        <span className="text-sm">{numeroCompacto(pico.visualizaciones)}</span>
      </div>
    </li>
  );
}

/** Fila de una pieza programada próxima (con su marca dry-run si ya venció). */
function FilaProxima({ pieza }: { pieza: ProximaPanel }) {
  return (
    <li className="border-b border-border/60 last:border-0">
      <Link
        to={enlaceAbrir(pieza.id, pieza.marca)}
        className={`flex items-center justify-between gap-3 py-2 ${FILA_CLICABLE}`}
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{pieza.titulo || "(sin título)"}</p>
          <p className="truncate text-xs text-muted-foreground">
            {[pieza.marca_nombre, pieza.red_nombre].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <span className="text-xs tabular-nums text-muted-foreground">
            {formatearFechaHora(pieza.fecha_programada)}
          </span>
          {pieza.preparado_en ? (
            <Badge
              variant="ok"
              title="Preparada (dry-run): el posteo real vía Metricool aún no está activo (KENI_PUBLICAR_REAL)."
            >
              Lista (dry-run)
            </Badge>
          ) : (
            <Badge variant="secondary">Programada</Badge>
          )}
        </div>
      </Link>
    </li>
  );
}

/** Fila de una pieza en la cola de aprobación: al hacer click abre su revisión/aprobación
 *  en el tablero (deep-link `?abrir=`). `pieza.id` es el `plataforma_id`; el tablero lo
 *  resuelve a la tarjeta del tema padre. */
function FilaCola({ pieza }: { pieza: Publicacion }) {
  return (
    <li className="border-b border-border/60 last:border-0">
      <Link
        to={enlaceAbrir(pieza.id, pieza.marca)}
        className={`flex items-center justify-between gap-3 py-2 ${FILA_CLICABLE}`}
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{pieza.titulo || "(sin título)"}</p>
          <p className="truncate text-xs text-muted-foreground">
            {[pieza.marca_nombre, pieza.red_nombre].filter(Boolean).join(" · ")}
          </p>
        </div>
        {pieza.enviado_a_revision_en && (
          <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
            {tiempoRelativo(pieza.enviado_a_revision_en)}
          </span>
        )}
      </Link>
    </li>
  );
}

/** Etiqueta legible + icono para cada tipo de alerta de rendimiento. */
const META_ALERTA: Record<string, { etiqueta: string; icono: typeof TrendingDown }> = {
  "pieza.bajo_rendimiento": { etiqueta: "Bajo rendimiento", icono: TrendingDown },
  "pieza.reciclaje_sugerida": { etiqueta: "Reciclaje sugerido", icono: Recycle },
};

/** Fila de una alerta de rendimiento (tipo legible + referencia a la pieza + fecha relativa). */
function FilaAlerta({ alerta }: { alerta: AlertaRendimiento }) {
  const meta = META_ALERTA[alerta.tipo] ?? { etiqueta: alerta.tipo, icono: TriangleAlert };
  const Icono = meta.icono;
  // Referencia a la pieza: preferimos el resumen humano del payload; si no, el id.
  const referencia = alerta.payload?.resumen || alerta.contenido_id || "(pieza)";
  const interior = (
    <>
      <div className="flex min-w-0 items-start gap-2">
        <Icono className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-medium">{meta.etiqueta}</p>
          <p className="truncate text-xs text-muted-foreground">{referencia}</p>
        </div>
      </div>
      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
        {tiempoRelativo(alerta.creado)}
      </span>
    </>
  );
  // Sin contenido_id no hay pieza a la que ir: la dejamos como texto plano.
  if (!alerta.contenido_id) {
    return (
      <li className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-0">
        {interior}
      </li>
    );
  }
  return (
    <li className="border-b border-border/60 last:border-0">
      <Link
        to={enlaceAbrir(alerta.contenido_id)}
        className={`flex items-center justify-between gap-3 py-2 ${FILA_CLICABLE}`}
      >
        {interior}
      </Link>
    </li>
  );
}

/** Etiqueta humana de la fuente (`origen`) de un item de la lista del día. */
const ORIGEN_ETIQUETA: Record<string, string> = {
  "import-calendario": "Calendario",
  "radar-auto": "Radar",
  radar: "Radar",
  rss: "RSS",
  manual: "Manual",
  // Aportaciones manuales desde Fuentes (idea / enlace pegado / contenido interno AMX).
  idea: "Idea",
  enlace: "Enlace",
  interna: "Interno AMX",
};

/** Fila de la "lista viva" del día: tema con su score, fuente, fecha y estado. */
function FilaListaDia({ item }: { item: ItemListaDia }) {
  const esCompromiso = item.etiquetas.some((e) => e.toLowerCase() === "compromiso");
  const esGreen = item.etiquetas.some((e) => e.toLowerCase() === "green");
  const fuente = ORIGEN_ETIQUETA[item.origen] ?? item.origen;
  return (
    <li className="border-b border-border/60 last:border-0">
      <Link
        to={enlaceAbrir(item.id, item.marca)}
        className={`flex items-center justify-between gap-3 py-2 ${FILA_CLICABLE}`}
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{item.titulo || "(sin título)"}</p>
          <div className="flex flex-wrap items-center gap-1.5 pt-1">
            <span className="text-xs text-muted-foreground">
              {[item.marca_nombre, fuente].filter(Boolean).join(" · ")}
            </span>
            {esCompromiso && (
              <Badge
                variant="outline"
                className="border-amber-500/40 text-amber-700 dark:text-amber-300"
              >
                Compromiso
              </Badge>
            )}
            {esGreen && (
              <Badge
                variant="outline"
                className="border-emerald-500/40 text-emerald-700 dark:text-emerald-300"
              >
                Green
              </Badge>
            )}
            {item.fecha_objetivo && (
              <span className="text-xs tabular-nums text-muted-foreground">
                {item.fecha_objetivo}
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge variant="secondary" title="Prioridad calculada (score dinámico)">
            {item.score}
          </Badge>
          <span className="text-xs text-muted-foreground">{item.estado}</span>
        </div>
      </Link>
    </li>
  );
}

export default function Panel() {
  // El panel es de lectura; se refresca al volver a la pestaña como el resto.
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["panel", "semana"],
    queryFn: ({ signal }) => api.panel({ rango: "semana" }, signal),
  });
  // Alertas de rendimiento: query independiente (no toca el contrato de /api/panel).
  const alertas = useQuery({
    queryKey: ["alertas"],
    queryFn: ({ signal }) => api.alertas({}, signal),
  });
  // Cola de aprobación: las piezas que esperan revisión, para listarlas clicables (cada
  // una abre su revisión/aprobación). Query independiente (no toca el contrato de
  // /api/panel, que solo trae el conteo), igual que las alertas.
  const cola = useQuery({
    queryKey: ["panel", "cola-aprobacion"],
    queryFn: ({ signal }) => api.colaAprobacion(signal),
  });
  const piezasEnRevision = cola.data?.cola ?? [];
  // Lista viva del día (H5): contenido del tablero ordenado por score dinámico. Query
  // independiente (no toca el contrato de /api/panel), igual que las alertas.
  const listaDia = useQuery({
    queryKey: ["panel", "lista-dia"],
    queryFn: ({ signal }) => api.listaDia({}, signal),
  });
  // Noticias más importantes sobre algoritmos (inteligencia de plataforma): query
  // independiente a /api/algoritmos (no toca el contrato de /api/panel), igual que las alertas.
  const algoritmos = useQuery({
    queryKey: ["panel", "algoritmos"],
    queryFn: ({ signal }) => api.algoritmos({ limite: 5 }, signal),
  });
  // Sugerencias editoriales pendientes (digest diario): solo para el contador del aviso.
  const sugerencias = useQuery({
    queryKey: ["panel", "sugerencias-editoriales"],
    queryFn: ({ signal }) => api.sugerenciasAlgoritmo("nueva", signal),
  });
  const nuevasSugerencias = sugerencias.data?.nuevas ?? 0;

  return (
    <div>
      <PageHeader titulo={CABECERA.titulo} descripcion={CABECERA.descripcion} />

      {nuevasSugerencias > 0 && (
        <Link
          to="/datos/investigacion/algoritmos"
          className="mb-4 flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-800 transition-colors hover:bg-amber-500/20 dark:text-amber-300"
        >
          <Lightbulb className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>
            <span className="font-medium">
              {nuevasSugerencias} sugerencia{nuevasSugerencias === 1 ? "" : "s"} editorial
              {nuevasSugerencias === 1 ? "" : "es"}
            </span>{" "}
            por revisar: cambios propuestos a las fichas de plataforma y límites.
          </span>
          <ArrowRight className="ml-auto h-4 w-4 shrink-0" aria-hidden="true" />
        </Link>
      )}

      {isLoading && <EsqueletoPanel />}
      {isError && (
        <BloqueError
          titulo="No se pudo cargar el panel"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      )}

      {data && (
        <div className="space-y-6">
          {/* Lista viva del día (H5): el centro del panel — lo que hay que postear hoy,
              alimentado por todas las fuentes y ordenado por score dinámico. */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <ListChecks className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Lista del día
              </CardTitle>
              {(listaDia.data?.total ?? 0) > 0 && (
                <span className="text-xs text-muted-foreground">
                  {listaDia.data!.total} en cola
                </span>
              )}
            </CardHeader>
            <CardContent>
              {listaDia.isError ? (
                <p className="py-4 text-sm text-muted-foreground">
                  No se pudo cargar la lista del día.
                </p>
              ) : (listaDia.data?.items?.length ?? 0) > 0 ? (
                <ul>
                  {listaDia.data!.items.map((item) => (
                    <FilaListaDia key={item.id} item={item} />
                  ))}
                </ul>
              ) : (
                <EstadoVacio
                  icono={ListChecks}
                  titulo="Nada en la lista todavía"
                  texto="Importa un calendario o deja que las fuentes (Radar, RSS) alimenten el tablero."
                />
              )}
            </CardContent>
          </Card>

          {/* Cambios de algoritmo: las noticias más importantes sobre algoritmos (decisiones
              de marca). Reusa el camino de lectura de Algoritmos; el detalle vive en su página. */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <Newspaper className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Cambios de algoritmo
              </CardTitle>
              <Button asChild variant="ghost" size="sm">
                <Link to="/datos/investigacion/algoritmos">Ver todo</Link>
              </Button>
            </CardHeader>
            <CardContent>
              {algoritmos.isError ? (
                <p className="py-4 text-sm text-muted-foreground">
                  No se pudieron cargar las noticias de algoritmo ahora mismo.
                </p>
              ) : (algoritmos.data?.noticias?.length ?? 0) > 0 ? (
                <ul>
                  {algoritmos.data!.noticias.map((n) => (
                    <li key={n.id} className="border-b border-border/60 last:border-0">
                      <a
                        href={n.enlace || undefined}
                        target="_blank"
                        rel="noreferrer"
                        className={`flex items-center justify-between gap-3 py-2 ${FILA_CLICABLE} ${
                          n.enlace ? "" : "pointer-events-none"
                        }`}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">
                            {n.titulo || "(sin título)"}
                          </p>
                          <div className="flex flex-wrap items-center gap-1.5 pt-1">
                            <Badge variant="outline">{n.plataforma_nombre || n.plataforma}</Badge>
                            {n.es_cambio && (
                              <Badge
                                variant="outline"
                                className="border-amber-500/40 text-amber-700 dark:text-amber-300"
                              >
                                Cambio
                              </Badge>
                            )}
                            <span className="text-xs text-muted-foreground">{n.fuente_nombre}</span>
                          </div>
                        </div>
                        {n.enlace && (
                          <ExternalLink
                            className="h-3.5 w-3.5 shrink-0 text-muted-foreground"
                            aria-hidden="true"
                          />
                        )}
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <EstadoVacio
                  icono={Newspaper}
                  titulo="Sin noticias de algoritmo todavía"
                  texto="Configura las fuentes y refresca en Investigación › Algoritmos para ver lo último."
                  accion={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/datos/investigacion/algoritmos">Ir a Algoritmos</Link>
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>

          {/* Resumen de métricas (reusa el camino de lectura de Métricas). */}
          <section className="space-y-3">
            <h3 className="text-sm font-medium text-muted-foreground">
              Rendimiento de la semana
            </h3>
            {data.metricas.disponible && data.metricas.total ? (
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <TarjetaKpi
                  variante="card"
                  etiqueta="Visualizaciones"
                  valor={numeroCompacto(data.metricas.total.visualizaciones)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Alcance"
                  valor={numeroCompacto(data.metricas.total.alcance)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Interacciones"
                  valor={numeroCompacto(data.metricas.total.interacciones)}
                />
                <TarjetaKpi
                  variante="card"
                  etiqueta="Engagement"
                  valor={porcentaje(data.metricas.total.engagement_pct)}
                />
              </div>
            ) : (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  Las métricas no están disponibles ahora mismo.
                </CardContent>
              </Card>
            )}
          </section>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Cola de aprobación. */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <ClipboardCheck className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Cola de aprobación
                </CardTitle>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/operacion/parrilla/pendientes">Ver todo</Link>
                </Button>
              </CardHeader>
              <CardContent>
                {data.cola.total > 0 ? (
                  <div className="space-y-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-semibold tabular-nums">
                        {data.cola.total}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        {data.cola.total === 1
                          ? "pieza espera revisión"
                          : "piezas esperan revisión"}
                      </span>
                    </div>
                    {/* Cada pieza es clicable: abre su revisión/aprobación en el tablero. */}
                    {piezasEnRevision.length > 0 && (
                      <ul>
                        {piezasEnRevision.map((pieza) => (
                          <FilaCola key={pieza.id} pieza={pieza} />
                        ))}
                      </ul>
                    )}
                  </div>
                ) : (
                  <p className="py-4 text-sm text-muted-foreground">
                    Nada pendiente de revisión. Buen trabajo.
                  </p>
                )}
              </CardContent>
            </Card>

            {/* Picos del periodo. */}
            <Card>
              <CardHeader className="space-y-0">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Sparkles className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                  Picos de la semana
                </CardTitle>
              </CardHeader>
              <CardContent>
                {data.metricas.picos.length > 0 ? (
                  <ul>
                    {data.metricas.picos.map((pico, i) => (
                      <FilaPico key={`${pico.marca}-${i}`} pico={pico} />
                    ))}
                  </ul>
                ) : (
                  <p className="py-4 text-sm text-muted-foreground">
                    Sin movimientos destacados en el periodo.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Próximas programadas. */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <CalendarClock className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Próximas programadas
              </CardTitle>
              {data.proximas.total > data.proximas.items.length && (
                <span className="text-xs text-muted-foreground">
                  {data.proximas.total} en total
                </span>
              )}
            </CardHeader>
            <CardContent>
              {data.proximas.items.length > 0 ? (
                <ul>
                  {data.proximas.items.map((pieza) => (
                    <FilaProxima key={pieza.id} pieza={pieza} />
                  ))}
                </ul>
              ) : (
                <EstadoVacio
                  icono={CalendarClock}
                  titulo="Nada programado todavía"
                  texto="Aprueba una pieza y prográmala desde el tablero."
                  accion={
                    <Button asChild variant="outline" size="sm">
                      <Link to="/operacion/parrilla/pendientes">Ir al tablero</Link>
                    </Button>
                  }
                />
              )}
            </CardContent>
          </Card>

          {/* Alertas de rendimiento (bitácora editorial: reciclaje / bajo rendimiento). */}
          <Card>
            <CardHeader className="space-y-0">
              <CardTitle className="flex items-center gap-2 text-base">
                <TriangleAlert className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Alertas de rendimiento
              </CardTitle>
            </CardHeader>
            <CardContent>
              {alertas.isError ? (
                <p className="py-4 text-sm text-muted-foreground">
                  No se pudieron cargar las alertas ahora mismo.
                </p>
              ) : (alertas.data?.alertas?.length ?? 0) > 0 ? (
                <ul>
                  {alertas.data!.alertas.map((alerta) => (
                    <FilaAlerta key={alerta.id} alerta={alerta} />
                  ))}
                </ul>
              ) : (
                <EstadoVacio
                  icono={TriangleAlert}
                  titulo="Sin alertas"
                  texto="No hay piezas con bajo rendimiento ni sugerencias de reciclaje por ahora."
                />
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
