import { useQuery } from "@tanstack/react-query";
import { Activity, RefreshCw } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TarjetaKpi } from "@/components/comunes/TarjetaKpi";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { costeUsd, duracion, numeroCompacto, numeroCompleto } from "@/lib/formato";
import type {
  ActividadAgregados,
  ActividadItem,
  ActividadPorDia,
  ActividadPorTipo,
  ActividadTotal,
  FuenteActividad,
} from "@/types";

/** Centinela del filtro "todas las fuentes / todos los tipos". */
const TODOS = "__todos__";

/** Tamaño de página de la tabla de actividad (cuántos suma cada "Cargar más"). */
const TAM_PAGINA = 50;

/** Texto legible del error de la API (o un fallback en español). */
function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo en un momento.";
}

/** Formatea una fecha ISO completa en formato corto es-MX; tolera inválidas. */
function formatearFecha(iso: string): string {
  if (!iso) return "—";
  const fecha = new Date(iso);
  if (Number.isNaN(fecha.getTime())) return iso;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(fecha);
}

/** Formatea un día (`YYYY-MM-DD`) en es-MX; tolera valores inesperados. */
function formatearDia(dia: string): string {
  if (!dia) return "—";
  // Interpretamos como fecha local a mediodía para evitar desfases de zona.
  const fecha = new Date(`${dia}T12:00:00`);
  if (Number.isNaN(fecha.getTime())) return dia;
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(fecha);
}

/** Etiqueta legible de la fuente de un ítem. */
function etiquetaFuente(fuente: FuenteActividad): string {
  return fuente === "run" ? "Agente" : "Generación";
}

/** Variante de badge por fuente (sutil, sin gritar). */
function varianteFuente(fuente: FuenteActividad): BadgeProps["variant"] {
  return fuente === "run" ? "secondary" : "outline";
}

/** Etiqueta + variante de badge para un estado de actividad (generación o run). */
function presentacionEstado(estado: string): {
  texto: string;
  variante: BadgeProps["variant"];
} {
  switch (estado) {
    case "completado":
      return { texto: "Completado", variante: "ok" };
    case "error":
      return { texto: "Error", variante: "error" };
    case "ejecutando":
      return { texto: "Visualizando…", variante: "aviso" };
    case "lanzado":
      return { texto: "Lanzado", variante: "secondary" };
    default:
      return { texto: estado || "—", variante: "secondary" };
  }
}

/** Coste con guion para nulos (el formateador trata `null` como no-finito). */
function costeCelda(v: number | null): string {
  return v == null ? "—" : costeUsd(v);
}

/** Duración con guion para nulos. */
function duracionCelda(v: number | null): string {
  return v == null ? "—" : duracion(v);
}

/** Tokens con guion para nulos. */
function tokensCelda(v: number | null): string {
  return v == null ? "—" : numeroCompacto(v);
}

/** Fila de KPIs con los totales del periodo disponible. */
function KpisTotales({ total }: { total: ActividadTotal }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <TarjetaKpi variante="card" etiqueta="Actividad total" valor={numeroCompleto(total.items)} />
      <TarjetaKpi variante="card" etiqueta="Coste total" valor={costeUsd(total.coste_usd)} />
      <TarjetaKpi
        variante="card"
        etiqueta="Tokens"
        valor={numeroCompacto(total.tokens)}
        titulo={numeroCompleto(total.tokens)}
      />
    </div>
  );
}

/** Mini-tabla de desglose por tipo de trabajo. */
function DesglosePorTipo({ filas }: { filas: ActividadPorTipo[] }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por tipo</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Tipo</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="py-8 text-center text-muted-foreground">
                  Sin actividad por tipo.
                </TableCell>
              </TableRow>
            ) : (
              filas.map((f) => (
                <TableRow key={f.tipo}>
                  <TableCell className="pl-6 font-medium">{f.tipo || "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell
                    className="text-right tabular-nums"
                    title={numeroCompleto(f.tokens)}
                  >
                    {numeroCompacto(f.tokens)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/** Mini-tabla de desglose por día (más reciente primero). */
function DesglosePorDia({ filas }: { filas: ActividadPorDia[] }) {
  // Por si el backend no lo ordena: mostramos del más reciente al más antiguo.
  const ordenadas = React.useMemo(
    () => [...filas].sort((a, b) => b.dia.localeCompare(a.dia)),
    [filas],
  );
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Por día</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Día</TableHead>
              <TableHead className="text-right">Items</TableHead>
              <TableHead className="pr-6 text-right">Coste</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {ordenadas.length === 0 ? (
              <TableRow>
                <TableCell colSpan={3} className="py-8 text-center text-muted-foreground">
                  Sin actividad por día.
                </TableCell>
              </TableRow>
            ) : (
              ordenadas.map((f) => (
                <TableRow key={f.dia}>
                  <TableCell className="pl-6 font-medium">{formatearDia(f.dia)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numeroCompleto(f.items)}
                  </TableCell>
                  <TableCell className="pr-6 text-right tabular-nums">
                    {costeUsd(f.coste_usd)}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

/**
 * Visor EN VIVO de una generación en curso (item D): carga el estado ACTUAL de la
 * generación por id (`GET /api/generaciones/{id}`) y, en cuanto lo tiene, lo entrega
 * a `useGeneracion` para REANUDAR el polling (~1.2 s) y pintar el stream con
 * `ProgresoGeneracion` —incluido el botón Cancelar—. Reusa el mismo hook que las
 * páginas de generación; el trabajo corre en el servidor, esto solo recupera la vista.
 */
function VisorEnVivo({ id, onClose }: { id: string; onClose: () => void }) {
  const { generacion, iniciar, cancelar, cancelando } = useGeneracion();

  // Carga el estado actual de la generación y arranca el seguimiento (polling). Si la
  // generación ya no existe (404) o falla la carga, lo reflejamos como error visible.
  const cargaQuery = useQuery({
    queryKey: ["generacion-visor", id],
    queryFn: ({ signal }) => api.generacion(id, signal),
  });
  React.useEffect(() => {
    if (cargaQuery.data) iniciar(cargaQuery.data.generacion);
  }, [cargaQuery.data, iniciar]);

  return (
    <Dialog open onOpenChange={(abierto) => !abierto && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Generación</DialogTitle>
          <DialogDescription>
            Stream del modelo (token a token mientras corre) y el prompt exacto enviado. El
            trabajo corre en el servidor; cerrar esta ventana no lo detiene.
          </DialogDescription>
        </DialogHeader>
        {cargaQuery.isError ? (
          <p className="text-sm text-destructive">
            {cargaQuery.error instanceof ApiError && cargaQuery.error.status === 404
              ? "Esa generación ya no está disponible."
              : mensajeError(cargaQuery.error)}
          </p>
        ) : generacion ? (
          <div className="space-y-3">
            <ProgresoGeneracion
              generacion={generacion}
              onCancelar={cancelar}
              cancelando={cancelando}
            />
            {generacion.prompt && (
              <details className="rounded-md border bg-muted/30 text-sm">
                <summary className="cursor-pointer select-none px-3 py-2 font-medium">
                  Ver prompt enviado al modelo
                </summary>
                <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words border-t px-3 py-2 text-xs text-muted-foreground">
                  {generacion.prompt}
                </pre>
              </details>
            )}
          </div>
        ) : (
          <Skeleton className="h-40 w-full rounded-xl" />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Tabla principal del feed unificado de actividad (recientes primero). */
function TablaActividad({
  items,
  total,
  cargando,
  onCargarMas,
  onVerEnVivo,
  onVerResultado,
}: {
  items: ActividadItem[];
  total: number;
  cargando: boolean;
  onCargarMas: () => void;
  onVerEnVivo: (id: string) => void;
  onVerResultado: (item: ActividadItem) => void;
}) {
  const hayMas = items.length < total;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          Actividad
          <Badge variant="secondary">{items.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Etiqueta</TableHead>
              <TableHead>Tipo</TableHead>
              <TableHead>Marca</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Fecha</TableHead>
              <TableHead className="text-right">Tokens</TableHead>
              <TableHead className="text-right">Coste</TableHead>
              <TableHead className="pr-6 text-right">Duración</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="py-8 text-center text-muted-foreground">
                  No hay actividad para este filtro.
                </TableCell>
              </TableRow>
            ) : (
              items.map((it) => {
                const est = presentacionEstado(it.estado);
                const m = it.metricas;
                // Acción PRINCIPAL del item (sin columna aparte): la fila entera la dispara.
                // Generación en vivo -> verla en directo; con resultado -> abrirlo donde salga.
                // Generación EN VIVO o SIN página de resultado (p.ej. importar parrilla) ->
                // abrir el visor (stream + prompt + error), también en estados terminales.
                // Generación/agente CON resultado -> abrir su página. Resto -> no clicable.
                const accion =
                  it.fuente === "generacion" &&
                  (it.estado === "ejecutando" || !it.resultado_url)
                    ? () => onVerEnVivo(it.id)
                    : it.resultado_url
                      ? () => onVerResultado(it)
                      : null;
                return (
                  <TableRow
                    key={`${it.fuente}:${it.id}`}
                    onClick={accion ?? undefined}
                    role={accion ? "button" : undefined}
                    tabIndex={accion ? 0 : undefined}
                    onKeyDown={
                      accion
                        ? (e) => {
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              accion();
                            }
                          }
                        : undefined
                    }
                    className={cn(accion && "cursor-pointer hover:bg-muted/40")}
                  >
                    <TableCell className="max-w-[22rem] pl-6 font-medium">
                      <span className="block truncate" title={it.etiqueta}>
                        {it.etiqueta || <span className="text-muted-foreground">Sin etiqueta</span>}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <Badge variant={varianteFuente(it.fuente)}>
                          {etiquetaFuente(it.fuente)}
                        </Badge>
                        <Badge variant="outline">{it.tipo || "—"}</Badge>
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {it.marca || <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <Badge variant={est.variante}>{est.texto}</Badge>
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatearFecha(it.fecha)}
                    </TableCell>
                    <TableCell
                      className="text-right tabular-nums"
                      title={m.tokens != null ? numeroCompleto(m.tokens) : undefined}
                    >
                      {tokensCelda(m.tokens)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {costeCelda(m.coste_usd)}
                    </TableCell>
                    <TableCell className="pr-6 text-right tabular-nums">
                      {duracionCelda(m.duration_ms)}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
        {hayMas && (
          <div className="flex flex-col items-center gap-1 border-t border-border py-4">
            <Button variant="outline" size="sm" onClick={onCargarMas} disabled={cargando}>
              {cargando ? "Cargando…" : "Cargar más"}
            </Button>
            <p className="text-xs text-muted-foreground">
              Mostrando {items.length} de {total}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Esqueleto de carga que imita la estructura de la página. */
function EsqueletoActividad() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Skeleton className="h-64 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </div>
      <Skeleton className="h-80 w-full rounded-xl" />
    </div>
  );
}

/**
 * Página Actividad IA: feed unificado de la actividad de IA (generaciones en
 * segundo plano + runs de agentes) con sus métricas (tokens, coste, duración).
 *
 * Combina dos consultas: los agregados (`GET /api/actividad/agregados`) para las
 * tarjetas KPI y los desgloses, y el listado paginado (`GET /api/actividad`) para
 * la tabla, con filtros por `fuente` y `tipo`. Cada bloque maneja su carga; un
 * error en cualquiera de las dos consultas se muestra como bloque de error.
 */
export default function Actividad() {
  const navigate = useNavigate();
  // Item D: id de la generación que se está viendo EN VIVO en el modal (o null).
  const [visorId, setVisorId] = React.useState<string | null>(null);
  const [fuente, setFuente] = React.useState<string>(TODOS);
  const [tipo, setTipo] = React.useState<string>(TODOS);
  // Paginación offset-based: pedimos `paginas * TAM_PAGINA` (offset 0) y "Cargar
  // más" sube `paginas`. Cambiar de filtro reinicia las páginas.
  const [paginas, setPaginas] = React.useState(1);
  const limite = paginas * TAM_PAGINA;

  const fuenteParam = fuente === TODOS ? undefined : fuente;
  const tipoParam = tipo === TODOS ? undefined : tipo;

  const listaQuery = useQuery({
    queryKey: ["actividad", "lista", limite, fuenteParam, tipoParam],
    queryFn: ({ signal }) =>
      api.actividad({ limite, fuente: fuenteParam, tipo: tipoParam }, signal),
  });
  const agregadosQuery = useQuery({
    queryKey: ["actividad", "agregados"],
    queryFn: ({ signal }) => api.actividadAgregados(signal),
  });

  const cargando = agregadosQuery.isPending || listaQuery.isPending;
  const conError = agregadosQuery.isError || listaQuery.isError;
  const refrescando = agregadosQuery.isFetching || listaQuery.isFetching;

  function refrescar() {
    void agregadosQuery.refetch();
    void listaQuery.refetch();
  }

  // Catálogo de tipos para el filtro: de los agregados (visión global, no solo lo cargado).
  const tipos = React.useMemo(
    () =>
      (agregadosQuery.data?.por_tipo ?? [])
        .map((t) => t.tipo)
        .filter((t) => t)
        .sort((a, b) => a.localeCompare(b, "es-MX")),
    [agregadosQuery.data],
  );

  const acciones = (
    <Button variant="outline" onClick={refrescar} disabled={refrescando}>
      <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
      Actualizar
    </Button>
  );

  return (
    <>
      <PageHeader
        titulo="Actividad IA"
        descripcion="Tokens, coste y duración de la actividad de IA (generaciones y agentes)."
        acciones={acciones}
      />

      <div className="mb-6 flex flex-col gap-3 sm:flex-row">
        <Select
          value={fuente}
          onValueChange={(v) => {
            setFuente(v);
            setPaginas(1);
          }}
        >
          <SelectTrigger className="w-full sm:w-[200px]" aria-label="Filtrar por fuente">
            <SelectValue placeholder="Fuente" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todas las fuentes</SelectItem>
            <SelectItem value="generacion">Generación</SelectItem>
            <SelectItem value="run">Agente</SelectItem>
          </SelectContent>
        </Select>
        <Select
          value={tipo}
          onValueChange={(v) => {
            setTipo(v);
            setPaginas(1);
          }}
        >
          <SelectTrigger className="w-full sm:w-[200px]" aria-label="Filtrar por tipo">
            <SelectValue placeholder="Tipo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={TODOS}>Todos los tipos</SelectItem>
            {tipos.map((t) => (
              <SelectItem key={t} value={t}>
                {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {cargando ? (
        <EsqueletoActividad />
      ) : conError ? (
        <BloqueError
          titulo="No se pudo cargar la actividad IA"
          mensaje={mensajeError(agregadosQuery.error ?? listaQuery.error)}
          onReintentar={refrescar}
          cargando={refrescando}
        />
      ) : (
        <Contenido
          agregados={agregadosQuery.data}
          items={listaQuery.data.items}
          total={listaQuery.data.total}
          filtrado={fuenteParam != null || tipoParam != null}
          cargando={listaQuery.isFetching}
          onCargarMas={() => setPaginas((p) => p + 1)}
          onVerEnVivo={setVisorId}
          onVerResultado={(item) => {
            if (item.resultado_url) navigate(item.resultado_url);
          }}
        />
      )}

      {visorId && <VisorEnVivo id={visorId} onClose={() => setVisorId(null)} />}
    </>
  );
}

/** Cuerpo de la página una vez resueltas ambas consultas. */
function Contenido({
  agregados,
  items,
  total,
  filtrado,
  cargando,
  onCargarMas,
  onVerEnVivo,
  onVerResultado,
}: {
  agregados: ActividadAgregados;
  items: ActividadItem[];
  total: number;
  filtrado: boolean;
  cargando: boolean;
  onCargarMas: () => void;
  onVerEnVivo: (id: string) => void;
  onVerResultado: (item: ActividadItem) => void;
}) {
  // Sin filtros y sin nada en absoluto: estado vacío honesto.
  if (!filtrado && agregados.total.items === 0 && items.length === 0) {
    return (
      <EstadoVacio
        icono={Activity}
        titulo="Aún no hay actividad IA"
        texto="Cuando se generen copies o se lancen runs de agentes, aquí verás sus tokens, coste y duración."
      />
    );
  }

  return (
    <div className="space-y-6">
      <KpisTotales total={agregados.total} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DesglosePorTipo filas={agregados.por_tipo} />
        <DesglosePorDia filas={agregados.por_dia} />
      </div>
      <TablaActividad
        items={items}
        total={total}
        cargando={cargando}
        onCargarMas={onCargarMas}
        onVerEnVivo={onVerEnVivo}
        onVerResultado={onVerResultado}
      />
    </div>
  );
}
