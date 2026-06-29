/**
 * TarjetaHistoria — la tarjeta editorial de una historia del pool, LIMPIA.
 *
 * La tarjeta solo resume lo esencial (titular, hora·fuente, score, ⚡ última hora y el estado
 * de la pieza si no está en el pool) y su ÚNICA acción es ABRIR la subpágina de detalle, donde
 * viven el desglose del score, las fuentes y las acciones (empujar/descartar). El checkbox de
 * selección múltiple no navega; el resto de la tarjeta sí.
 */

import { CheckCircle2, Clock, History, Sparkles, Zap } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { formatearFechaHora, tiempoRelativoCorto } from "@/lib/fecha";
import { nivelPrioridad } from "@/lib/noticias/ranking-editorial";
import { nombreFuente } from "@/lib/trends";
import type { Historia } from "@/types";

export interface PropsTarjetaHistoria {
  historia: Historia;
  /** Selección múltiple (solo la lista plana la usa; la mesa no selecciona en lote). */
  seleccionada?: boolean;
  onToggleSeleccion?: (checked: boolean) => void;
}

// El puntito gradúa el score: alta en verde, media en ámbar, baja en gris apagado.
const COLOR_PRIORIDAD: Record<string, string> = {
  alta: "bg-emerald-500",
  media: "bg-amber-400",
  baja: "bg-muted-foreground/40",
};

export function TarjetaHistoria({
  historia,
  seleccionada,
  onToggleSeleccion,
}: PropsTarjetaHistoria) {
  const navigate = useNavigate();

  const esDescartada = historia.estado === "descartado";
  // Estado REAL de cara al feed (lo deriva el back desde la PIEZA, no solo del cluster).
  const piezaEstado =
    historia.pieza_estado ??
    (historia.estado === "usado" ? "en_feed" : esDescartada ? "descartada" : "en_pool");
  const esUltimaHora = historia.breaking === 1 && piezaEstado !== "descartada";
  const prioridad = nivelPrioridad(historia.score);
  // Lo esencial junto al título: hace cuánto abrió (relativo, no la hora suelta que confunde) y
  // la fuente que abrió. El instante exacto queda en el `title` al pasar el ratón.
  const cuando = tiempoRelativoCorto(historia.primer_visto);
  const cuandoExacto = formatearFechaHora(historia.primer_visto);
  const fuente =
    nombreFuente(historia.primera_fuente_nombre, historia.primera_fuente_id) ||
    historia.marca_nombre;

  const abrir = () => navigate(`/operacion/investigacion/historia/${encodeURIComponent(historia.id)}`);

  // Indicador de estado DISCRETO: solo cuando la historia ya no está plana en el pool.
  const indicadorEstado =
    piezaEstado === "en_feed" ? (
      <Badge variant="ok" className="gap-1 text-xs">
        <CheckCircle2 className="h-3 w-3" />
        En el feed
      </Badge>
    ) : piezaEstado === "generando" ? (
      <Badge variant="aviso" className="gap-1 text-xs" title="Redactando copy">
        <Spinner className="h-3 w-3" />
        Generando…
      </Badge>
    ) : piezaEstado === "en_cola" ? (
      <Badge variant="aviso" className="gap-1 text-xs" title="En cola de procesamiento">
        <Clock className="h-3 w-3" />
        En cola
      </Badge>
    ) : esDescartada ? (
      <Badge variant="secondary" className="text-xs">
        Descartada
      </Badge>
    ) : historia.promovible === true ? (
      <Tooltip label={historia.promovible_motivo || "Supera el umbral automático"} side="top">
        <Badge
          variant="outline"
          className="gap-1 text-xs border-emerald-500 text-emerald-700 dark:text-emerald-300"
          data-testid="badge-sale-sola"
        >
          <Sparkles className="h-3 w-3" />
          Sale sola al feed
        </Badge>
      </Tooltip>
    ) : null;

  return (
    <Card
      className={`text-sm transition hover:border-keni-300 focus-within:border-keni-300 ${esDescartada ? "opacity-60" : ""} ${
        seleccionada ? "ring-2 ring-primary/40" : ""
      }`}
      data-testid="historia-item"
    >
      <CardContent className="pt-3 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex flex-1 min-w-0 items-start gap-2">
            {onToggleSeleccion && (
              <Checkbox
                checked={seleccionada ?? false}
                onCheckedChange={onToggleSeleccion}
                className="mt-0.5"
                aria-label={`Seleccionar «${historia.titulo || "sin título"}»`}
              />
            )}
            {/* Toda la zona del titular abre la subpágina (única acción de la tarjeta). */}
            <button
              type="button"
              className="min-w-0 flex-1 space-y-0.5 text-left"
              onClick={abrir}
              aria-label={`Abrir detalle de «${historia.titulo || "sin título"}»`}
              data-testid="btn-detalle"
            >
              <p className="font-medium leading-snug min-w-0">
                {esUltimaHora && (
                  <Zap
                    className="mr-1 inline-block h-3.5 w-3.5 shrink-0 align-middle text-red-600"
                    aria-label="Última hora"
                    data-testid="badge-ultima-hora"
                  />
                )}
                {historia.traduciendo ? (
                  <span className="inline-flex items-center gap-1 italic text-muted-foreground">
                    <Spinner className="h-3 w-3" />
                    {historia.titulo || "Traduciendo…"}
                  </span>
                ) : (
                  historia.titulo || "(sin título)"
                )}
              </p>
              {(cuando || fuente) && (
                <p
                  className="flex items-center gap-1 text-xs text-muted-foreground"
                  data-testid="hora-fuente"
                >
                  {cuando && (
                    <span className="inline-flex items-center gap-1" title={cuandoExacto}>
                      <History className="h-3 w-3 shrink-0" />
                      {cuando}
                    </span>
                  )}
                  {cuando && fuente ? <span aria-hidden>·</span> : null}
                  {fuente && <span className="truncate">{fuente}</span>}
                </p>
              )}
            </button>
          </div>

          {/* Flanco derecho: estado discreto (si aplica) + el SCORE como pastilla indicadora. */}
          <div className="mt-0.5 flex shrink-0 items-center gap-2">
            {indicadorEstado}
            <span
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums"
              data-testid="punto-prioridad"
            >
              <span className={`h-2 w-2 rounded-full ${COLOR_PRIORIDAD[prioridad]}`} />
              Score {Math.round(historia.score * 100)}
            </span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
