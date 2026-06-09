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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { CampaniaComercial } from "@/types";

import { CLAVE_COMERCIAL } from "./comercial/claves";
import { DialogoCampania } from "./comercial/DialogoCampania";
import { PanelCampania } from "./comercial/PanelCampania";

// Periodos ofrecidos para la analítica (tokens que entiende el backend).
const RANGOS: { id: string; etiqueta: string }[] = [
  { id: "semana", etiqueta: "Última semana" },
  { id: "mes", etiqueta: "Últimos 30 días" },
];

export default function Comercial() {
  const { marcaActiva, nombreActiva } = useMarcaActiva();

  if (marcaActiva == null) {
    return (
      <EstadoVacio
        icono={Megaphone}
        titulo="Elige una marca para ver sus campañas"
        texto="Las campañas pertenecen a una marca concreta. Selecciona una en el switch de la barra superior."
      />
    );
  }
  return <Panel key={marcaActiva} marca={marcaActiva} nombreMarca={nombreActiva} />;
}

function Panel({ marca, nombreMarca }: { marca: string; nombreMarca: string | null }) {
  const queryClient = useQueryClient();
  const [rango, setRango] = React.useState("mes");
  const [seleccionada, setSeleccionada] = React.useState<string | null>(null);
  const [dialogoAbierto, setDialogoAbierto] = React.useState(false);
  const [editando, setEditando] = React.useState<CampaniaComercial | null>(null);

  const listaQuery = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "lista", marca],
    queryFn: ({ signal }) => api.campanias({ marca }, signal),
  });

  const campanias = React.useMemo(
    () => listaQuery.data?.campanias ?? [],
    [listaQuery.data],
  );
  const esMuestra = Boolean(listaQuery.data?.es_muestra);

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

  const acciones = (
    <Button onClick={abrirNueva}>
      <Plus className="h-4 w-4" />
      Nueva campaña
    </Button>
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
          titulo={`${nombreMarca ?? "Esta marca"} aún no tiene campañas`}
          texto="Crea una campaña con uno o varios hashtags y le daremos seguimiento a las publicaciones que los lleven."
          accion={
            <Button onClick={abrirNueva}>
              <Plus className="h-4 w-4" />
              Nueva campaña
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {esMuestra && <AvisoMuestra />}

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={seleccionada ?? undefined} onValueChange={setSeleccionada}>
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
            <Select value={rango} onValueChange={setRango}>
              <SelectTrigger className="w-full sm:w-[200px]" aria-label="Periodo">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RANGOS.map((r) => (
                  <SelectItem key={r.id} value={r.id}>
                    {r.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {campaniaActual && (
            <div className="flex flex-wrap items-center gap-1.5">
              {campaniaActual.hashtags.map((h) => (
                <Badge key={h} variant="secondary">
                  #{h}
                </Badge>
              ))}
            </div>
          )}

          {seleccionada && <PanelCampania campaniaId={seleccionada} rango={rango} />}
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

/**
 * Aviso, no alarmante, de que las cifras son de MUESTRA (sintéticas) y no datos
 * reales del cliente. Mientras no haya APIs reales conectadas, todo sale de un
 * modelo determinista; que nadie lo confunda con lo real.
 */
function AvisoMuestra() {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
      <Badge variant="aviso">Datos de muestra (sintéticos)</Badge>
      <span>Las cifras son de demostración, no datos reales del cliente.</span>
    </div>
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
