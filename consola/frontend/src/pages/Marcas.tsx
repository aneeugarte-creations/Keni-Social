import { useQuery, useQueryClient } from "@tanstack/react-query";
import { LayoutGrid, Loader2, Plus, RefreshCw, Unplug } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { DialogoMarca, type MarcaEditable } from "@/pages/marcas/DialogoMarca";
import { iconoPlataforma, nombrePlataforma } from "@/pages/marcas/plataformas";
import { tiempoRelativo } from "@/pages/piezas/meta";
import type { CanalPieza, ConteoCuenta, MarcaDashboard, RedMarca } from "@/types";

/** Convierte una marca del dashboard a la forma editable del catálogo (id/etiqueta/id_metricas/tipo). */
function aEditable(m: MarcaDashboard): MarcaEditable {
  return { id: m.id, etiqueta: m.etiqueta, id_metricas: m.marca, tipo: m.tipo };
}

const CLAVE_MARCAS = ["marcas", "dashboard"];

// Ruta de retorno del OAuth: una ventana mínima de Keni que avisa al panel y se cierra.
const RUTA_OAUTH_RETORNO = "/oauth/conectado";
const MSG_OAUTH = "keni-oauth-conectado";

/** Entero con separador de miles (es-MX), o «—» si no hay dato (no es 0). */
function fmtEntero(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-MX").format(n);
}

/** Decimal con 1 cifra (posts/día), o «—» si no hay dato. */
function fmtDia(n: number | null | undefined): string {
  if (n == null) return "—";
  return new Intl.NumberFormat("es-MX", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n);
}

/** Las tres celdas numéricas de una fila (mismo ancho y alineación en todas las filas). */
function CeldasNumero({ c }: { c: ConteoCuenta }) {
  return (
    <>
      <td className="w-32 px-3 py-2 text-right tabular-nums">{fmtEntero(c.seguidores)}</td>
      <td className="w-28 px-3 py-2 text-right tabular-nums">{fmtEntero(c.posts_totales)}</td>
      <td className="w-24 px-3 py-2 text-right tabular-nums">{fmtDia(c.posts_dia)}</td>
    </>
  );
}

/** Opciones del selector de canal de publicación. */
const CANALES: { id: CanalPieza; etiqueta: string }[] = [
  { id: "metricool", etiqueta: "Metricool" },
  { id: "postproxy", etiqueta: "Postproxy" },
];

/** Control segmentado «Publica por: ( Metricool | Postproxy )» de una marca. */
function SelectorCanal({
  canal,
  postproxyDisponible,
  deshabilitado,
  onCambiar,
}: {
  canal: CanalPieza;
  postproxyDisponible: boolean;
  deshabilitado: boolean;
  onCambiar: (canal: CanalPieza) => void;
}) {
  return (
    <div className="inline-flex rounded-md border border-border bg-muted p-0.5">
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
              "rounded px-2 py-0.5 text-xs font-medium transition-colors",
              activo ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground",
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
  );
}

// Color del punto de estado de una red.
function clasesPunto(red: RedMarca): string {
  if (red.conectado && red.estado === "active") return "bg-emerald-500";
  if (red.estado === "expired") return "bg-amber-500";
  return "bg-muted-foreground/40";
}

/** Botón de acción de una red: Conectar / Reconectar / Desconectar. */
function AccionRed({
  red,
  ocupada,
  onConectar,
  onDesconectar,
}: {
  red: RedMarca;
  ocupada: boolean;
  onConectar: () => void;
  onDesconectar: () => void;
}) {
  const conectada = red.conectado && red.estado === "active";
  if (conectada) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
        disabled={ocupada || !red.perfil_id}
        onClick={onDesconectar}
      >
        {ocupada ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Unplug className="h-3.5 w-3.5" />}
        Desconectar
      </Button>
    );
  }
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-7 px-2 text-xs"
      disabled={ocupada}
      onClick={onConectar}
    >
      {ocupada ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
      {red.estado === "expired" ? "Reconectar" : "Conectar"}
    </Button>
  );
}

/** Bloque de una marca: fila de sumatorio (+ selector de canal) y una fila por red. */
function BloqueMarca({
  marca,
  pendiente,
  onConectar,
  onDesconectar,
  onCanal,
  onEditar,
}: {
  marca: MarcaDashboard;
  pendiente: string | null;
  onConectar: (marca: string, plataforma: string) => void;
  onDesconectar: (marca: string, red: RedMarca) => void;
  onCanal: (marca: string, canal: CanalPieza) => void;
  onEditar: (marca: MarcaDashboard) => void;
}) {
  const conectadas = marca.redes.filter((r) => r.conectado && r.estado === "active").length;
  return (
    <>
      {/* Sumatorio de la marca + canal de publicación. */}
      <tr className="border-b border-border bg-muted/40 font-medium">
        <td className="py-2 pl-3 pr-2">
          {/* Clic en el nombre → abre el editor de la marca (con borrar dentro). */}
          <Tooltip label="Editar marca">
            <button
              type="button"
              onClick={() => onEditar(marca)}
              className="rounded text-left hover:underline"
            >
              {marca.etiqueta}
            </button>
          </Tooltip>
        </td>
        <CeldasNumero c={marca.total} />
        <td className="px-3 py-2 text-right">
          <SelectorCanal
            canal={marca.canal_publicacion}
            postproxyDisponible={conectadas > 0}
            deshabilitado={pendiente === `${marca.marca}:canal`}
            onCambiar={(c) => onCanal(marca.marca, c)}
          />
        </td>
      </tr>
      {/* Una línea por red: estado + números + acción. */}
      {marca.redes.map((red) => {
        const Icono = iconoPlataforma(red.plataforma);
        const clave = `${marca.marca}:${red.plataforma}`;
        return (
          <tr key={red.plataforma} className="border-b border-border last:border-0">
            <td className="py-1.5 pl-8 pr-2">
              <span className="flex min-w-0 items-center gap-2 text-muted-foreground">
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", clasesPunto(red))} aria-hidden="true" />
                <Icono className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {nombrePlataforma(red.plataforma)}
                {red.nombre_cuenta && (
                  <span className="truncate text-xs text-muted-foreground/70">· {red.nombre_cuenta}</span>
                )}
              </span>
            </td>
            <CeldasNumero c={red} />
            <td className="px-3 py-1.5 text-right">
              <AccionRed
                red={red}
                ocupada={pendiente === clave}
                onConectar={() => onConectar(marca.marca, red.plataforma)}
                onDesconectar={() => onDesconectar(marca.marca, red)}
              />
            </td>
          </tr>
        );
      })}
    </>
  );
}

/**
 * Página MARCAS (admin): una sola lista (de Postproxy). Por marca, una fila de sumatorio
 * con su selector de canal; debajo, una fila por red con sus números (seguidores / posts /
 * posts-día) y el botón de conectar/desconectar. El total global va arriba. Las cuentas se
 * conectan con el OAuth oficial de la red dentro de una ventana de Keni (el equipo nunca
 * sale a un tercero). Las métricas de audiencia tienen su página en Analíticas.
 */
export default function Marcas() {
  const queryClient = useQueryClient();
  const [pendiente, setPendiente] = React.useState<string | null>(null);
  // CRUD del catálogo: un único diálogo de crear/editar (null = crear). El borrado vive
  // dentro del editor (clic en el nombre de la marca lo abre).
  const [editor, setEditor] = React.useState<{ abierto: boolean; marca: MarcaEditable | null }>({
    abierto: false,
    marca: null,
  });
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_MARCAS,
    queryFn: ({ signal }) => api.getMarcas(signal),
  });

  const refrescar = () => queryClient.invalidateQueries({ queryKey: CLAVE_MARCAS });

  // La ventana de retorno del OAuth nos avisa al terminar: refrescamos al instante.
  React.useEffect(() => {
    function alMensaje(e: MessageEvent) {
      if (e.origin !== window.location.origin) return;
      if (e.data?.tipo !== MSG_OAUTH) return;
      void refrescar();
      if (e.data.ok) toast.success("Red conectada.");
    }
    window.addEventListener("message", alMensaje);
    return () => window.removeEventListener("message", alMensaje);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);

  function conectar(marca: string, plataforma: string) {
    // Ventana abierta SINCRÓNICAMENTE en el clic (los bloqueadores de popups lo exigen).
    const popup = window.open("about:blank", "keni_conectar_red", "width=620,height=760");
    setPendiente(`${marca}:${plataforma}`);
    api
      .conectarPostproxy(marca, { platform: plataforma, redirect_url: window.location.origin + RUTA_OAUTH_RETORNO })
      .then((res) => {
        if (popup) popup.location.href = res.url;
        else window.open(res.url, "_blank", "noopener,noreferrer");
      })
      .catch((e) => {
        popup?.close();
        toast.error(mensajeError(e));
      })
      .finally(() => setPendiente(null));
  }

  function desconectar(marca: string, red: RedMarca) {
    if (!red.perfil_id) return;
    setPendiente(`${marca}:${red.plataforma}`);
    api
      .eliminarPerfilPostproxy(red.perfil_id)
      .then(() => {
        toast.success(`${nombrePlataforma(red.plataforma)} desconectada.`);
        void refrescar();
      })
      .catch((e) => toast.error(mensajeError(e)))
      .finally(() => setPendiente(null));
  }

  function cambiarCanal(marca: string, canal: CanalPieza) {
    setPendiente(`${marca}:canal`);
    api
      .canalPostproxy(marca, canal)
      .then((res) => {
        toast.success(res.mensaje || `Canal: ${res.canal}.`);
        void refrescar();
      })
      .catch((e) => toast.error(mensajeError(e)))
      .finally(() => setPendiente(null));
  }

  return (
    <>
      <TituloPagina titulo="Marcas" icono={LayoutGrid} />
      {isPending ? (
        <Card className="p-4">
          <div className="space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        </Card>
      ) : isError ? (
        <BloqueError
          titulo="No se pudo cargar el panel de marcas"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : data.marcas.length === 0 ? (
        <EstadoVacio icono={LayoutGrid} titulo="No hay marcas" texto="Aún no hay marcas configuradas." />
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
            <p className="text-xs text-muted-foreground">
              {data.generado_en ? `Actualizado ${tiempoRelativo(data.generado_en)}` : "Marcas × redes"}
            </p>
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={() => setEditor({ abierto: true, marca: null })}
              >
                <Plus className="h-3.5 w-3.5" />
                Añadir marca
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => void refetch()} disabled={isFetching}>
                <RefreshCw className={cn("h-3.5 w-3.5", isFetching && "animate-spin")} />
                Actualizar
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted-foreground">
                  <th className="w-full py-2 pl-3 pr-2 text-left font-medium">Cuenta</th>
                  <th className="w-32 px-3 py-2 text-right font-medium">Seguidores</th>
                  <th className="w-28 px-3 py-2 text-right font-medium">Posts</th>
                  <th className="w-24 px-3 py-2 text-right font-medium">Posts/día</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {/* Total global ARRIBA, encima de las marcas. */}
                <tr className="border-b-2 border-border font-semibold">
                  <td className="py-2 pl-3 pr-2">Total</td>
                  <CeldasNumero c={data.totales} />
                  <td className="px-3 py-2" />
                </tr>
                {data.marcas.map((marca) => (
                  <BloqueMarca
                    key={marca.marca}
                    marca={marca}
                    pendiente={pendiente}
                    onConectar={conectar}
                    onDesconectar={desconectar}
                    onCanal={cambiarCanal}
                    onEditar={(m) => setEditor({ abierto: true, marca: aEditable(m) })}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <DialogoMarca
        abierto={editor.abierto}
        inicial={editor.marca}
        onCerrar={() => setEditor({ abierto: false, marca: null })}
      />
    </>
  );
}
