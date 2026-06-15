import { useQuery } from "@tanstack/react-query";
import { LayoutGrid, Link2, Network, Plug, RefreshCw, Send, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { mensajeError } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatearNumero, iconoPlataforma, nombrePlataforma } from "@/pages/marcas/plataformas";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { MarcaDashboard, RedMarca, TotalesMarcas } from "@/types";

const CLAVE_MARCAS = ["marcas", "dashboard"];

// Ruta a la sección de conexiones (drawer de ajustes de Producción, donde vive Postproxy).
const RUTA_CONEXIONES = "/maquina/produccion?tab=ajustes";

/** Tarjeta de un total del encabezado. */
function TarjetaResumen({
  etiqueta,
  valor,
  icono: Icono,
}: {
  etiqueta: string;
  valor: string;
  icono: typeof Users;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Icono className="h-4 w-4 text-primary" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-xl font-semibold leading-tight">{valor}</p>
          <p className="truncate text-xs text-muted-foreground">{etiqueta}</p>
        </div>
      </CardContent>
    </Card>
  );
}

/** Fila de totales globales del dashboard. */
function FilaResumen({ totales }: { totales: TotalesMarcas }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      <TarjetaResumen etiqueta="Marcas" valor={formatearNumero(totales.marcas)} icono={LayoutGrid} />
      <TarjetaResumen etiqueta="Cuentas" valor={formatearNumero(totales.cuentas)} icono={Users} />
      <TarjetaResumen
        etiqueta="Redes conectadas"
        valor={formatearNumero(totales.redes_conectadas)}
        icono={Network}
      />
      <TarjetaResumen
        etiqueta="Seguidores"
        valor={formatearNumero(totales.seguidores)}
        icono={Users}
      />
      <TarjetaResumen
        etiqueta="Posts totales"
        valor={formatearNumero(totales.posts_totales)}
        icono={Plug}
      />
      <TarjetaResumen
        etiqueta="Posts / día"
        valor={formatearNumero(totales.posts_dia)}
        icono={RefreshCw}
      />
    </div>
  );
}

// Clases del chip de red según su estado: verde=active, ámbar=expired, gris=resto.
function clasesChip(red: RedMarca): string {
  if (red.conectado && red.estado === "active") {
    return "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  }
  if (red.estado === "expired") {
    return "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300";
  }
  return "border-border bg-muted/40 text-muted-foreground";
}

/** Texto del tooltip de un chip de red. */
function tooltipRed(red: RedMarca): string {
  const partes: string[] = [nombrePlataforma(red.plataforma)];
  if (red.nombre_cuenta) partes.push(red.nombre_cuenta);
  if (red.estado === "active") partes.push("conectada");
  else if (red.estado === "expired") partes.push("token caducado");
  else partes.push("sin conectar");
  if (red.post_count != null) partes.push(`${formatearNumero(red.post_count)} posts`);
  return partes.join(" · ");
}

/** Chip de UNA red de una marca. No conectada → enlace a conexiones. */
function ChipRed({ red }: { red: RedMarca }) {
  const Icono = iconoPlataforma(red.plataforma);
  const contenido = (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-medium",
        clasesChip(red),
      )}
    >
      <Icono className="h-3.5 w-3.5" aria-hidden="true" />
      <span>{nombrePlataforma(red.plataforma)}</span>
      {!red.conectado && (
        <Link2 className="h-3 w-3 opacity-70" aria-hidden="true" />
      )}
    </span>
  );

  // Red no conectada (o sin estado activo): CTA que enlaza a la sección de conexiones.
  const enlazable = !red.conectado;

  return (
    <Tooltip label={tooltipRed(red)}>
      {enlazable ? (
        <Link to={RUTA_CONEXIONES} aria-label={`Conectar ${nombrePlataforma(red.plataforma)}`}>
          {contenido}
        </Link>
      ) : (
        contenido
      )}
    </Tooltip>
  );
}

/** Tarjeta de UNA marca con sus conexiones, redes y métricas. */
function TarjetaMarca({ marca }: { marca: MarcaDashboard }) {
  return (
    <Card>
      <CardHeader className="gap-2 p-4 pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="truncate">{marca.etiqueta}</CardTitle>
          <div className="flex shrink-0 items-center gap-1.5">
            <Badge variant={marca.metricool.conectado ? "ok" : "secondary"}>Metricool</Badge>
            <Badge variant={marca.postproxy.conectado ? "ok" : "secondary"}>Postproxy</Badge>
          </div>
        </div>
        {/* Canal de publicación activo de la marca (por dónde salen sus piezas). */}
        <Badge variant="outline" className="w-fit gap-1">
          <Send className="h-3 w-3" aria-hidden="true" />
          Publica por {marca.canal_publicacion === "postproxy" ? "Postproxy" : "Metricool"}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-2">
        {/* Redes: una fila de chips de estado. */}
        {marca.redes.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sin redes configuradas.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {marca.redes.map((red) => (
              <ChipRed key={red.plataforma} red={red} />
            ))}
          </div>
        )}

        {/* Métricas agregadas de la marca. */}
        <div className="grid grid-cols-3 gap-2 border-t border-border pt-3">
          <div>
            <p className="text-sm font-semibold leading-tight">
              {formatearNumero(marca.metricas.seguidores)}
            </p>
            <p className="text-[11px] text-muted-foreground">Seguidores</p>
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">
              {formatearNumero(marca.metricas.posts_totales)}
            </p>
            <p className="text-[11px] text-muted-foreground">Posts</p>
          </div>
          <div>
            <p className="text-sm font-semibold leading-tight">
              {formatearNumero(marca.metricas.posts_dia)}
            </p>
            <p className="text-[11px] text-muted-foreground">Posts / día</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Página MARCAS: la foto EN VIVO de todas las marcas × redes × cuentas. Arriba, los
 * totales globales; debajo, una tarjeta por marca con su estado de conexiones
 * (Metricool/Postproxy), sus redes (verde=conectada, ámbar=token caducado,
 * gris=sin conectar) y sus métricas. Cada red sin conectar enlaza a Conexiones.
 */
export default function Marcas() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_MARCAS,
    queryFn: ({ signal }) => api.getMarcas(signal),
  });

  return (
    <>
      <TituloPagina titulo="Marcas" icono={LayoutGrid} />
      <div className="space-y-4">
        {isPending ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-[68px] w-full rounded-xl" />
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-52 w-full rounded-xl" />
              ))}
            </div>
          </>
        ) : isError ? (
          <BloqueError
            titulo="No se pudo cargar el panel de marcas"
            mensaje={mensajeError(error)}
            onReintentar={() => void refetch()}
            cargando={isFetching}
          />
        ) : data.marcas.length === 0 ? (
          <EstadoVacio
            icono={LayoutGrid}
            titulo="No hay marcas"
            texto="Aún no hay marcas configuradas para mostrar en el panel."
          />
        ) : (
          <>
            <FilaResumen totales={data.totales} />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {data.marcas.map((marca) => (
                <TarjetaMarca key={marca.marca} marca={marca} />
              ))}
            </div>
            {data.generado_en && (
              <p className="text-right text-xs text-muted-foreground">
                Actualizado {tiempoRelativo(data.generado_en)}
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}
