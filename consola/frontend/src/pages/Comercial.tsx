import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Megaphone, Plus, RefreshCw, Search } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { OpcionesComercial, PublicacionComercial } from "@/types";

import { CLAVE_COMERCIAL } from "./comercial/claves";
import { Detalle } from "./comercial/Detalle";
import { DialogoNueva } from "./comercial/DialogoNueva";
import { presentacionEstado } from "./comercial/formato";
import { numeroCompacto, numeroCompleto } from "./metricas/formato";

const ESTADO_TODAS = "__todas__";

function Cabecera({ acciones }: { acciones?: React.ReactNode }) {
  return (
    <PageHeader
      titulo="Comercial"
      descripcion="Monitorea publicaciones comerciales por su enlace, vigila su objetivo y entrega su reporte al llegar el KPI. Aparte del rendimiento diario de Métricas."
      acciones={acciones}
    />
  );
}

export default function Comercial() {
  const opcionesQuery = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "opciones"],
    queryFn: ({ signal }) => api.comercialOpciones(signal),
  });

  if (opcionesQuery.isPending) {
    return (
      <>
        <Cabecera />
        <Esqueleto />
      </>
    );
  }
  if (opcionesQuery.isError) {
    return (
      <>
        <Cabecera />
        <BloqueError
          titulo="No se pudo cargar el apartado comercial"
          mensaje={opcionesQuery.error instanceof Error ? opcionesQuery.error.message : undefined}
          onReintentar={() => void opcionesQuery.refetch()}
          cargando={opcionesQuery.isFetching}
        />
      </>
    );
  }
  return <Panel opciones={opcionesQuery.data} />;
}

function Panel({ opciones }: { opciones: OpcionesComercial }) {
  const queryClient = useQueryClient();
  const [estadoFiltro, setEstadoFiltro] = React.useState(ESTADO_TODAS);
  const [busqueda, setBusqueda] = React.useState("");
  const [nuevaAbierta, setNuevaAbierta] = React.useState(false);
  const [detalleId, setDetalleId] = React.useState<string | null>(null);

  const estadoParam = estadoFiltro === ESTADO_TODAS ? undefined : estadoFiltro;
  const listaQuery = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "lista", estadoParam ?? "todas"],
    queryFn: ({ signal }) => api.comerciales({ estado: estadoParam }, signal),
  });

  const refrescarDatos = useMutation({
    mutationFn: () => api.refrescarComerciales(),
    onSuccess: (r) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
      toast.success(
        r.actualizadas > 0
          ? `Datos actualizados (${r.actualizadas} pieza${r.actualizadas === 1 ? "" : "s"})`
          : "No hay piezas activas que actualizar",
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const refrescando = listaQuery.isFetching || refrescarDatos.isPending;
  const acciones = (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        variant="outline"
        onClick={() => refrescarDatos.mutate()}
        disabled={refrescarDatos.isPending}
      >
        <RefreshCw className={cn("h-4 w-4", refrescando && "animate-spin")} />
        Refrescar datos
      </Button>
      <Button onClick={() => setNuevaAbierta(true)}>
        <Plus className="h-4 w-4" />
        Monitorear publicación
      </Button>
    </div>
  );

  const todas = listaQuery.data?.publicaciones ?? [];
  const termino = busqueda.trim().toLowerCase();
  const filtradas = termino
    ? todas.filter((p) =>
        [p.titulo, p.cliente, p.campania, p.url].some((c) => c.toLowerCase().includes(termino)),
      )
    : todas;

  return (
    <>
      <Cabecera acciones={acciones} />

      {listaQuery.isPending ? (
        <Esqueleto />
      ) : listaQuery.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las publicaciones"
          mensaje={listaQuery.error instanceof Error ? listaQuery.error.message : undefined}
          onReintentar={() => void listaQuery.refetch()}
          cargando={listaQuery.isFetching}
        />
      ) : todas.length === 0 ? (
        <EstadoVacio
          icono={Megaphone}
          titulo="Aún no monitoreas ninguna publicación"
          texto="Elige una publicación ya hecha de tus redes y le daremos seguimiento a interacciones y visualizaciones hasta que llegue su KPI."
          accion={
            <Button onClick={() => setNuevaAbierta(true)}>
              <Plus className="h-4 w-4" />
              Monitorear publicación
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {listaQuery.data?.es_muestra && <AvisoMuestra />}
          <Kpis publicaciones={todas} esMuestra={Boolean(listaQuery.data?.es_muestra)} />

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="relative w-full sm:max-w-xs">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                className="pl-8"
                placeholder="Buscar por título, cliente o campaña…"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                aria-label="Buscar publicaciones"
              />
            </div>
            <Select value={estadoFiltro} onValueChange={setEstadoFiltro}>
              <SelectTrigger className="w-full sm:w-[180px]" aria-label="Filtrar por estado">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ESTADO_TODAS}>Todos los estados</SelectItem>
                {opciones.estados.map((e) => (
                  <SelectItem key={e.id} value={e.id}>
                    {e.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <Tabla
            publicaciones={filtradas}
            esMuestra={Boolean(listaQuery.data?.es_muestra)}
            onAbrir={setDetalleId}
          />
        </div>
      )}

      <DialogoNueva
        abierto={nuevaAbierta}
        opciones={opciones}
        onCerrar={() => setNuevaAbierta(false)}
      />
      <Detalle
        publicacionId={detalleId}
        opciones={opciones}
        onCerrar={() => setDetalleId(null)}
      />
    </>
  );
}

/**
 * Aviso, no alarmante, de que las cifras son de MUESTRA (sintéticas) y no datos
 * reales del cliente. Mientras no haya APIs reales conectadas, todo el apartado
 * Comercial sale de un modelo determinista; que nadie lo confunda con lo real.
 */
function AvisoMuestra() {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
      <Badge variant="aviso">Datos de muestra (sintéticos)</Badge>
      <span>
        Las cifras de alcance e interacciones son de demostración, no datos reales del cliente.
      </span>
    </div>
  );
}

function TarjetaKpi({ etiqueta, valor, titulo }: { etiqueta: string; valor: string; titulo?: string }) {
  return (
    <Card>
      <CardContent className="space-y-1.5 p-5">
        <p className="text-sm text-muted-foreground">{etiqueta}</p>
        <p className="truncate text-2xl font-semibold tracking-tight tabular-nums" title={titulo ?? valor}>
          {valor}
        </p>
      </CardContent>
    </Card>
  );
}

// Métrica de volumen mostrada en el listado: visualizaciones (datos reales de Metricool)
// o alcance (modo muestra; Metricool no da alcance por pieza).
function volumenLista(esMuestra: boolean): {
  etiqueta: string;
  valor: (p: PublicacionComercial) => number;
} {
  return esMuestra
    ? { etiqueta: "Alcance", valor: (p) => p.actual.alcance }
    : { etiqueta: "Visualizaciones", valor: (p) => p.actual.visualizaciones };
}

function Kpis({
  publicaciones,
  esMuestra,
}: {
  publicaciones: PublicacionComercial[];
  esMuestra: boolean;
}) {
  const activas = publicaciones.filter((p) => p.estado === "activa").length;
  const alcanzadas = publicaciones.filter((p) => p.alcanzado).length;
  const vol = volumenLista(esMuestra);
  const volTotal = publicaciones.reduce((s, p) => s + vol.valor(p), 0);
  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <TarjetaKpi etiqueta="En seguimiento" valor={numeroCompleto(publicaciones.length)} />
      <TarjetaKpi etiqueta="Activas" valor={numeroCompleto(activas)} />
      <TarjetaKpi etiqueta="Objetivo alcanzado" valor={numeroCompleto(alcanzadas)} />
      <TarjetaKpi
        etiqueta={`${vol.etiqueta} acumulado`}
        valor={numeroCompacto(volTotal)}
        titulo={numeroCompleto(volTotal)}
      />
    </div>
  );
}

function Tabla({
  publicaciones,
  esMuestra,
  onAbrir,
}: {
  publicaciones: PublicacionComercial[];
  esMuestra: boolean;
  onAbrir: (id: string) => void;
}) {
  const vol = volumenLista(esMuestra);
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">Publicación</TableHead>
              <TableHead>Red</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="text-right">{vol.etiqueta}</TableHead>
              <TableHead className="text-right">Interacciones</TableHead>
              <TableHead className="pr-6">Objetivo</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {publicaciones.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  Ninguna publicación coincide con la búsqueda.
                </TableCell>
              </TableRow>
            ) : (
              publicaciones.map((p) => {
                const estado = presentacionEstado(p.estado);
                const sub = [p.cliente, p.campania].filter(Boolean).join(" · ");
                return (
                  <TableRow
                    key={p.id}
                    className="cursor-pointer"
                    onClick={() => onAbrir(p.id)}
                  >
                    <TableCell className="pl-6">
                      <span
                        className="block max-w-[20rem] truncate font-medium"
                        title={p.titulo || p.url || "Publicación"}
                      >
                        {p.titulo || p.url || "Publicación"}
                      </span>
                      {sub && <span className="block text-xs text-muted-foreground">{sub}</span>}
                    </TableCell>
                    <TableCell>
                      {p.red_nombre ? (
                        <Badge variant="outline">{p.red_nombre}</Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={estado.variante}>{estado.texto}</Badge>
                    </TableCell>
                    <TableCell
                      className="text-right tabular-nums"
                      title={numeroCompleto(vol.valor(p))}
                    >
                      {numeroCompacto(vol.valor(p))}
                    </TableCell>
                    <TableCell
                      className="text-right tabular-nums"
                      title={numeroCompleto(p.actual.interacciones)}
                    >
                      {numeroCompacto(p.actual.interacciones)}
                    </TableCell>
                    <TableCell className="pr-6">
                      <CeldaObjetivo publicacion={p} />
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function CeldaObjetivo({ publicacion }: { publicacion: PublicacionComercial }) {
  if (publicacion.objetivo <= 0) {
    return <span className="text-muted-foreground">Sin objetivo</span>;
  }
  const progreso = Math.min(publicacion.progreso_pct, 100);
  return (
    <div className="flex w-36 items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded bg-muted">
        <div
          className={cn("h-1.5 rounded", publicacion.alcanzado ? "bg-emerald-500" : "bg-primary")}
          style={{ width: `${progreso}%` }}
        />
      </div>
      {publicacion.alcanzado ? (
        <Bell className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" aria-label="Objetivo alcanzado" />
      ) : (
        <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
          {publicacion.progreso_pct}%
        </span>
      )}
    </div>
  );
}

function Esqueleto() {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-80 w-full rounded-xl" />
    </div>
  );
}
