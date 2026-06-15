import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Check, LayoutGrid, Loader2, Network, Plus, Send, Unplug, Users } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { formatearNumero, iconoPlataforma, nombrePlataforma } from "@/pages/marcas/plataformas";
import { tiempoRelativo } from "@/pages/publicaciones/meta";
import type { CanalPublicacion, MarcaDashboard, RedMarca, TotalesMarcas } from "@/types";

const CLAVE_MARCAS = ["marcas", "dashboard"];

// Página de métricas de audiencia (Metricool). El panel de Marcas es CONEXIONES; los
// números de audiencia viven aquí y se enlazan, no se duplican.
const RUTA_ANALITICAS = "/analiticas/metricas";

// Ruta de retorno del OAuth: una ventana mínima de Keni que avisa al panel y se cierra.
const RUTA_OAUTH_RETORNO = "/oauth/conectado";

// Mensaje que la ventana de retorno del OAuth envía al panel para que refresque.
const MSG_OAUTH = "keni-oauth-conectado";

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

/** Fila de totales de conexión del dashboard. */
function FilaResumen({ totales }: { totales: TotalesMarcas }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      <TarjetaResumen etiqueta="Marcas" valor={formatearNumero(totales.marcas)} icono={LayoutGrid} />
      <TarjetaResumen
        etiqueta="Redes conectadas"
        valor={formatearNumero(totales.redes_conectadas)}
        icono={Network}
      />
      <TarjetaResumen etiqueta="Cuentas" valor={formatearNumero(totales.cuentas)} icono={Users} />
    </div>
  );
}

/** Opciones del selector de canal de publicación. */
const CANALES: { id: CanalPublicacion; etiqueta: string }[] = [
  { id: "metricool", etiqueta: "Metricool" },
  { id: "postproxy", etiqueta: "Postproxy" },
];

/**
 * Control segmentado «Publica por: ( Metricool | Postproxy )». Postproxy se
 * deshabilita (con tooltip) hasta que la marca tenga al menos una red conectada:
 * no se fija un canal sin destino real.
 */
function SelectorCanal({
  canal,
  postproxyDisponible,
  deshabilitado,
  onCambiar,
}: {
  canal: CanalPublicacion;
  postproxyDisponible: boolean;
  deshabilitado: boolean;
  onCambiar: (canal: CanalPublicacion) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Publica por:</span>
      <div className="inline-flex rounded-md border border-border p-0.5">
        {CANALES.map((opcion) => {
          const activo = canal === opcion.id;
          const bloqueado = opcion.id === "postproxy" && !postproxyDisponible;
          const boton = (
            <button
              type="button"
              role="radio"
              aria-checked={activo}
              disabled={deshabilitado || bloqueado || activo}
              onClick={() => onCambiar(opcion.id)}
              className={cn(
                "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                activo ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
                bloqueado && "cursor-not-allowed opacity-50",
              )}
            >
              {opcion.etiqueta}
            </button>
          );
          return bloqueado ? (
            <Tooltip key={opcion.id} label="Conecta al menos una red para publicar por Postproxy.">
              {boton}
            </Tooltip>
          ) : (
            <React.Fragment key={opcion.id}>{boton}</React.Fragment>
          );
        })}
      </div>
    </div>
  );
}

// Clases del punto de estado de una red: verde=active, ámbar=expired, gris=resto.
function clasesPunto(red: RedMarca): string {
  if (red.conectado && red.estado === "active") return "bg-emerald-500";
  if (red.estado === "expired") return "bg-amber-500";
  return "bg-muted-foreground/40";
}

/** Texto de estado legible de una red. */
function textoEstado(red: RedMarca): string {
  if (red.conectado && red.estado === "active") return red.nombre_cuenta || "Conectada";
  if (red.estado === "expired") return "Token caducado — reconecta";
  return "Sin conectar";
}

/**
 * Fila de UNA red de una marca: estado + acción. Sin conectar → «Conectar» (abre el
 * OAuth oficial de la red en una ventana de Keni). Conectada → cuenta + «Desconectar».
 * Caducada → «Reconectar». En ningún punto se menciona el proveedor: el equipo solo ve
 * la red (Instagram, Facebook…) y Keni.
 */
function FilaRed({
  red,
  ocupada,
  onConectar,
  onDesconectar,
}: {
  red: RedMarca;
  ocupada: boolean;
  onConectar: (plataforma: string) => void;
  onDesconectar: (red: RedMarca) => void;
}) {
  const Icono = iconoPlataforma(red.plataforma);
  const conectada = red.conectado && red.estado === "active";
  return (
    <div className="flex items-center justify-between gap-2 rounded-md border border-border px-2.5 py-1.5">
      <div className="flex min-w-0 items-center gap-2">
        <Icono className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <p className="truncate text-sm leading-tight">{nombrePlataforma(red.plataforma)}</p>
          <p className="flex items-center gap-1 truncate text-[11px] text-muted-foreground">
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", clasesPunto(red))} aria-hidden="true" />
            {textoEstado(red)}
          </p>
        </div>
      </div>
      {conectada ? (
        <Button
          size="sm"
          variant="ghost"
          className="h-7 shrink-0 px-2 text-xs text-muted-foreground hover:text-destructive"
          disabled={ocupada || !red.perfil_id}
          onClick={() => onDesconectar(red)}
        >
          {ocupada ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
          Desconectar
        </Button>
      ) : (
        <Button
          size="sm"
          variant={red.estado === "expired" ? "outline" : "default"}
          className="h-7 shrink-0 px-2 text-xs"
          disabled={ocupada}
          onClick={() => onConectar(red.plataforma)}
        >
          {ocupada ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
          {red.estado === "expired" ? "Reconectar" : "Conectar"}
        </Button>
      )}
    </div>
  );
}

/** Tarjeta de UNA marca con sus conexiones y redes accionables. */
function TarjetaMarca({ marca }: { marca: MarcaDashboard }) {
  const queryClient = useQueryClient();
  const [accion, setAccion] = React.useState<string | null>(null);

  const conectadas = marca.redes.filter((r) => r.conectado && r.estado === "active").length;

  const refrescar = () => queryClient.invalidateQueries({ queryKey: CLAVE_MARCAS });

  function conectar(plataforma: string) {
    // Abrimos la ventana SINCRÓNICAMENTE en el clic (los bloqueadores de popups exigen
    // que nazca del gesto del usuario); luego la apuntamos a la URL del OAuth al llegar.
    const popup = window.open("about:blank", "keni_conectar_red", "width=620,height=760");
    setAccion(plataforma);
    api
      .conectarPostproxy(marca.marca, {
        platform: plataforma,
        redirect_url: window.location.origin + RUTA_OAUTH_RETORNO,
      })
      .then((res) => {
        if (popup) popup.location.href = res.url;
        else window.open(res.url, "_blank", "noopener,noreferrer");
      })
      .catch((e) => {
        popup?.close();
        toast.error(mensajeError(e));
      })
      .finally(() => setAccion(null));
  }

  function desconectar(red: RedMarca) {
    if (!red.perfil_id) return;
    setAccion(red.plataforma);
    api
      .eliminarPerfilPostproxy(red.perfil_id)
      .then(() => {
        toast.success(`${nombrePlataforma(red.plataforma)} desconectada.`);
        void refrescar();
      })
      .catch((e) => toast.error(mensajeError(e)))
      .finally(() => setAccion(null));
  }

  function cambiarCanal(canal: CanalPublicacion) {
    setAccion("__canal__");
    api
      .canalPostproxy(marca.marca, canal)
      .then((res) => {
        toast.success(res.mensaje || `Canal de ${marca.etiqueta}: ${res.canal}.`);
        void refrescar();
      })
      .catch((e) => toast.error(mensajeError(e)))
      .finally(() => setAccion(null));
  }

  const ocupado = accion !== null;

  return (
    <Card>
      <CardHeader className="gap-2 p-4 pb-2">
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="truncate">{marca.etiqueta}</CardTitle>
          <div className="flex shrink-0 items-center gap-1.5">
            <Tooltip label={marca.metricool.conectado ? "Métricas vía Metricool" : "Metricool sin conectar"}>
              <Badge variant={marca.metricool.conectado ? "ok" : "secondary"}>
                {marca.metricool.conectado ? <Check className="h-3 w-3" /> : null} Métricas
              </Badge>
            </Tooltip>
            <Badge variant={conectadas > 0 ? "ok" : "secondary"}>
              <Network className="h-3 w-3" /> {conectadas} {conectadas === 1 ? "red" : "redes"}
            </Badge>
          </div>
        </div>
        <SelectorCanal
          canal={marca.canal_publicacion}
          postproxyDisponible={conectadas > 0}
          deshabilitado={ocupado}
          onCambiar={cambiarCanal}
        />
      </CardHeader>
      <CardContent className="space-y-3 p-4 pt-2">
        {/* Redes: una fila accionable por red (conectar / desconectar / reconectar). */}
        {marca.redes.length === 0 ? (
          <p className="text-xs text-muted-foreground">Sin redes disponibles.</p>
        ) : (
          <div className="space-y-1.5">
            {marca.redes.map((red) => (
              <FilaRed
                key={red.plataforma}
                red={red}
                ocupada={accion === red.plataforma}
                onConectar={conectar}
                onDesconectar={desconectar}
              />
            ))}
          </div>
        )}

        {/* Las métricas de audiencia viven en Analíticas (Metricool): enlace, no duplicado. */}
        <Link
          to={RUTA_ANALITICAS}
          className="flex items-center justify-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />
          Ver analíticas
        </Link>
      </CardContent>
    </Card>
  );
}

/**
 * Página MARCAS (admin): el centro de control de CONEXIONES de todas las marcas × redes.
 * Arriba, los totales de conexión; debajo, una tarjeta por marca donde se CONECTA cada
 * red en un par de clics (OAuth oficial de la red dentro de una ventana de Keni; el
 * equipo nunca sale a un tercero), se desconecta, se ve el estado real y se elige el
 * canal por el que publica. Las métricas de audiencia tienen su página en Analíticas.
 */
export default function Marcas() {
  const queryClient = useQueryClient();
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_MARCAS,
    queryFn: ({ signal }) => api.getMarcas(signal),
  });

  // La ventana de retorno del OAuth nos avisa al terminar: refrescamos el panel para
  // que la red recién conectada aparezca al instante (sin esperar al refetch por foco).
  React.useEffect(() => {
    function alMensaje(e: MessageEvent) {
      if (e.origin !== window.location.origin) return;
      if (e.data?.tipo !== MSG_OAUTH) return;
      void queryClient.invalidateQueries({ queryKey: CLAVE_MARCAS });
      if (e.data.ok) toast.success("Red conectada.");
    }
    window.addEventListener("message", alMensaje);
    return () => window.removeEventListener("message", alMensaje);
  }, [queryClient]);

  return (
    <>
      <TituloPagina titulo="Marcas" icono={LayoutGrid} />
      <div className="space-y-4">
        {isPending ? (
          <>
            <div className="grid grid-cols-3 gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-[68px] w-full rounded-xl" />
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-72 w-full rounded-xl" />
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
              <p className="flex items-center justify-end gap-1 text-right text-xs text-muted-foreground">
                <Send className="h-3 w-3" aria-hidden="true" />
                Actualizado {tiempoRelativo(data.generado_en)}
              </p>
            )}
          </>
        )}
      </div>
    </>
  );
}
