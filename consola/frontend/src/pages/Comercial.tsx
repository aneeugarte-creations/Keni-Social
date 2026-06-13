/**
 * Campañas: seguimiento de campañas de marca agrupadas por uno o varios HASHTAGS.
 *
 * Reemplaza el antiguo seguimiento de publicaciones sueltas por objetivo. Se elige una
 * campaña (definida por sus hashtags) y un periodo, y se ven KPIs (visualizaciones,
 * interacciones, engagement) con comparativa, la tendencia diaria y la tabla de piezas
 * del periodo —solo las publicaciones cuyo texto lleva alguno de los hashtags—. La marca
 * la fija el switch global de la barra superior; cada campaña pertenece a una marca.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Megaphone, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api, mensajeError } from "@/lib/api";
import type { CampaniaComercial } from "@/types";

import { CLAVE_COMERCIAL } from "./comercial/claves";
import { DialogoCampania } from "./comercial/DialogoCampania";
import { PanelCampania } from "./comercial/PanelCampania";
import { SelectorTiempo } from "./metricas/Controles";

/**
 * Token `rango:AAAA-MM-DD_AAAA-MM-DD` de los últimos `n` días (incluye hoy), en fecha
 * LOCAL. El backend (`resolver_rango`) lo entiende igual que los presets. Las campañas
 * abarcan semanas o meses, así que no basta con la ventana de 30 días: un post con el
 * hashtag publicado hace 2 meses (p. ej. de un evento) debe poder verse ampliando el periodo.
 */
function tokenUltimosDias(n: number): string {
  const hasta = new Date();
  const desde = new Date();
  desde.setDate(desde.getDate() - (n - 1));
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  return `rango:${iso(desde)}_${iso(hasta)}`;
}

// Periodos ofrecidos para la analítica (tokens que entiende el backend). Los más largos
// se calculan al cargar como rango personalizado; el backend acota a 366 días.
const RANGOS: { id: string; etiqueta: string }[] = [
  { id: "semana", etiqueta: "Última semana" },
  { id: "mes", etiqueta: "Últimos 30 días" },
  { id: tokenUltimosDias(90), etiqueta: "Últimos 90 días" },
  { id: tokenUltimosDias(180), etiqueta: "Últimos 6 meses" },
];

export default function Comercial() {
  const queryClient = useQueryClient();
  const [rango, setRango] = React.useState("mes");
  const [seleccionada, setSeleccionada] = React.useState<string | null>(null);
  // Modo cliente: oculta TODO lo de Ads (el cliente no debe ver que se usó pauta) y suma las
  // visualizaciones pagadas a las orgánicas. Persiste para que aguante al recargar/compartir.
  const [ocultarAds, setOcultarAds] = React.useState(
    () => localStorage.getItem("keni:campanias:ocultarAds") === "1",
  );
  React.useEffect(() => {
    localStorage.setItem("keni:campanias:ocultarAds", ocultarAds ? "1" : "0");
  }, [ocultarAds]);
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState<CampaniaComercial | null>(null);

  // Las campañas son MULTIMARCA: no se acotan al switch de marca de la barra; se listan
  // todas. La elección de marcas vive en el diálogo (sobre las marcas de la persona).
  const listaQuery = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "lista"],
    queryFn: ({ signal }) => api.campanias({}, signal),
  });

  const campanias = React.useMemo(
    () => listaQuery.data?.campanias ?? [],
    [listaQuery.data],
  );

  // Mantener una campaña seleccionada válida cuando cambia la lista.
  React.useEffect(() => {
    if (campanias.length === 0) {
      if (seleccionada !== null) setSeleccionada(null);
      return;
    }
    if (!seleccionada || !campanias.some((c) => c.id === seleccionada)) {
      setSeleccionada(campanias[0].id);
    }
  }, [campanias, seleccionada]);

  const campaniaActual = campanias.find((c) => c.id === seleccionada) ?? null;

  const eliminar = useMutation({
    mutationFn: (id: string) => api.eliminarCampania(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
      toast.success("Campaña eliminada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const abrirNueva = () => {
    setEditando(null);
    setDialogoAbierto(true);
  };
  const abrirEdicion = (c: CampaniaComercial) => {
    setEditando(c);
    setDialogoAbierto(true);
  };

  // Barra superior limpia: UN "⋮" con la ACCIÓN (nueva campaña) y la entrada «Ajustes»
  // (el AJUSTE persistente «modo cliente»).
  const acciones = (
    <MenuAcciones
      ajustesTitulo="Ajustes de campañas"
      ajustes={
        // Fila de capa base (con su divisor), no una caja con borde dentro del panel.
        <section className="border-t border-border py-3 first:border-t-0">
          <label className="flex items-center justify-between gap-3 text-sm font-medium">
            Modo cliente
            <Switch
              checked={ocultarAds}
              onCheckedChange={setOcultarAds}
              aria-label="Modo cliente: ocultar todo lo de Ads"
            />
          </label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Oculta Ads; suma visualizaciones pagadas a orgánicas. Persiste al recargar.
          </p>
        </section>
      }
    >
      <ItemMenu icono={Plus} onClick={abrirNueva}>
        Nueva campaña
      </ItemMenu>
    </MenuAcciones>
  );

  return (
    <>
      <AccionesPagina>{acciones}</AccionesPagina>

      {listaQuery.isPending ? (
        <Esqueleto />
      ) : listaQuery.isError ? (
        <BloqueError
          titulo="No se pudieron cargar las campañas"
          mensaje={listaQuery.error instanceof Error ? listaQuery.error.message : undefined}
          onReintentar={() => void listaQuery.refetch()}
          cargando={listaQuery.isFetching}
        />
      ) : campanias.length === 0 ? (
        <EstadoVacio
          icono={Megaphone}
          titulo="Aún no hay campañas"
          texto="Crea una campaña para dar seguimiento a publicaciones con sus hashtags."
          accion={
            <Button onClick={abrirNueva}>
              <Plus className="h-4 w-4" />
              Nueva campaña
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={seleccionada ?? ""} onValueChange={setSeleccionada}>
                <SelectTrigger className="w-full sm:w-[260px]" aria-label="Campaña">
                  <SelectValue placeholder="Elige una campaña" />
                </SelectTrigger>
                <SelectContent>
                  {campanias.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {campaniaActual && (
                <MenuAcciones>
                  <ItemMenu icono={Pencil} onClick={() => abrirEdicion(campaniaActual)}>
                    Editar campaña
                  </ItemMenu>
                  <ItemMenu
                    icono={Trash2}
                    className="text-rose-600 dark:text-rose-400"
                    onClick={() => eliminar.mutate(campaniaActual.id)}
                  >
                    Eliminar campaña
                  </ItemMenu>
                </MenuAcciones>
              )}
            </div>
            <div className="flex items-center gap-2">
              {/* Aviso visible mientras el modo cliente (panel de ajustes) está activo: que
                  no se enseñen cifras "sin Ads" creyendo que es la vista completa. */}
              {ocultarAds && (
                <Badge variant="secondary" title="Modo cliente activo: lo de Ads está oculto y sumado a lo orgánico. Se cambia en los ajustes de la página.">
                  Ads ocultos
                </Badge>
              )}
              <SelectorTiempo rangos={RANGOS} valor={rango} onCambio={setRango} />
            </div>
          </div>

          {campaniaActual && (
            <div className="flex flex-wrap items-center gap-1.5">
              {campaniaActual.marcas_nombres.map((nombre) => (
                <Badge key={nombre} variant="outline">
                  {nombre}
                </Badge>
              ))}
              {campaniaActual.marcas_nombres.length > 0 && campaniaActual.hashtags.length > 0 && (
                <span className="mx-1 text-muted-foreground">·</span>
              )}
              {campaniaActual.hashtags.map((h) => (
                <Badge key={h} variant="secondary">
                  #{h}
                </Badge>
              ))}
            </div>
          )}

          {seleccionada && (
            <PanelCampania campaniaId={seleccionada} rango={rango} ocultarAds={ocultarAds} />
          )}
        </div>
      )}

      <DialogoCampania
        abierto={dialogoAbierto}
        campania={editando}
        onCerrar={() => setDialogoAbierto(false)}
      />
    </>
  );
}

function Esqueleto() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-10 w-72 rounded-lg" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-28 w-full rounded-xl" />
        ))}
      </div>
      <Skeleton className="h-72 w-full rounded-xl" />
    </div>
  );
}
