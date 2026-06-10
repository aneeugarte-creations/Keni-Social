/**
 * Botón "Actualizar" del dashboard de Métricas + indicador de "última actualización".
 *
 * Las métricas se sirven desde una CACHE en el backend (instantáneo) que un daemon
 * refresca cada ~4 h. Este control fuerza un refresco BAJO DEMANDA:
 *
 *   1. `POST /api/metricas/refrescar` arranca un refresco en 2º plano que recalcula
 *      PRIMERO el combo (rango, marca) que se está viendo y luego el resto.
 *   2. Mientras corre, polleamos `GET /api/metricas/estado` cada 2 s.
 *   3. En cuanto el `generado_en` del combo visto avanza (o el refresco termina),
 *      invalidamos las queries de métricas para que la vista se repinte con el dato
 *      fresco — y dejamos de pollear (el resto del barrido sigue en el servidor).
 *
 * Idempotente: si ya hay un refresco corriendo, el backend no arranca otro.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import * as React from "react";

import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";

import { tiempoRelativo } from "../publicaciones/meta";

export function BotonActualizar({
  rango,
  marca,
  generadoEn,
}: {
  /** Rango seleccionado arriba: el combo que se prioriza al refrescar. */
  rango?: string;
  /** Marca acotada (marcaParam; undefined = todas): parte del combo prioritario. */
  marca?: string;
  /** `generado_en` del reporte que se está viendo (para "Actualizado hace X"). */
  generadoEn?: string;
}) {
  const queryClient = useQueryClient();
  // `solicitado` guarda el `generado_en` que había al pulsar; null = no estamos
  // refrescando. Detectamos "vista lista" comparando contra este valor.
  const [solicitado, setSolicitado] = React.useState<string | null>(null);
  const polling = solicitado !== null;

  const estadoQuery = useQuery({
    queryKey: ["metricas", "estado", rango ?? "", marca ?? "todas"],
    queryFn: ({ signal }) => api.metricasEstado({ rango, marca }, signal),
    enabled: polling && Boolean(rango),
    refetchInterval: polling ? 2000 : false,
  });

  // Cuando la vista actual ya está fresca (su timestamp avanzó) o el refresco
  // terminó, repintamos las métricas y dejamos de pollear.
  React.useEffect(() => {
    if (solicitado === null) return;
    const data = estadoQuery.data;
    if (!data) return;
    const vistaFresca = Boolean(data.generado_en) && data.generado_en !== solicitado;
    if (vistaFresca || !data.corriendo) {
      void queryClient.invalidateQueries({ queryKey: ["metricas"] });
      setSolicitado(null);
    }
  }, [estadoQuery.data, solicitado, queryClient]);

  // `disparando` cubre el hueco entre el click y el aterrizaje del POST: el polling NO
  // arranca hasta que el backend confirmó el disparo. Antes se fijaba `solicitado` ANTES
  // del POST y el primer poll podía ver `corriendo=false` (refresco aún no arrancado) y
  // mostrar "Actualizado" con datos viejos.
  const [disparando, setDisparando] = React.useState(false);

  async function actualizar() {
    const base = generadoEn ?? "";
    setDisparando(true);
    try {
      await api.metricasRefrescar({ rango, marca });
      // Purga el estado cacheado de la sesión de polling anterior: si quedara en caché,
      // el efecto lo evaluaría al instante y cortaría este polling antes de arrancar.
      queryClient.removeQueries({ queryKey: ["metricas", "estado"] });
      setSolicitado(base); // ahora sí: el refresco está en marcha, empieza el polling
    } catch (e) {
      // El disparo falló: avisa (antes se silenciaba) y no te quedes polleando.
      toast.error(mensajeError(e));
    } finally {
      setDisparando(false);
    }
  }

  const relativo = tiempoRelativo(generadoEn);

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground" aria-live="polite">
        {polling || disparando ? "Actualizando…" : relativo ? `Actualizado ${relativo}` : null}
      </span>
      <Button
        variant="outline"
        size="sm"
        onClick={() => void actualizar()}
        disabled={polling || disparando || !rango}
        title="Vuelve a descargar las métricas desde las plataformas"
      >
        <RefreshCw className={cn("h-4 w-4", (polling || disparando) && "animate-spin")} />
        Actualizar
      </Button>
    </div>
  );
}
