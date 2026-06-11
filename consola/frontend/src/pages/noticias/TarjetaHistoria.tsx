/**
 * TarjetaHistoria — la tarjeta editorial de una historia del pool.
 *
 * Rediseño "mesa de redacción": en vez de una nube de badges técnicos, la tarjeta cuenta la
 * historia como la contaría un editor — título, FRASE de corroboración ("Confirmada por
 * Reuters y Milenio · la abrió Reuters hace 42 min"), resumen y un punto de PRIORIDAD
 * (alta/media/baja) cuyo tooltip explica por qué rankea (nunca el número crudo). Una última
 * hora toma el tratamiento rojo de tarjeta entera. Las acciones dicen la verdad del sistema:
 * si la historia "sale sola al feed" (supera el listón) el humano lo VE — no hacer nada es
 * una decisión válida; Adelantar/Empujar y Descartar siguen a un clic.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ExternalLink,
  Globe,
  Loader2,
  Newspaper,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { calculoScoreTexto, factoresRanking, fraseCorroboracion, nivelPrioridad } from "@/lib/noticias/ranking-editorial";
import type { Historia } from "@/types";

import { DetalleHistoria } from "./DetalleHistoria";

export interface PropsTarjetaHistoria {
  historia: Historia;
  /** Query keys a invalidar tras una acción (la lista/mesa que renderiza la tarjeta). */
  clavesAInvalidar: readonly (readonly unknown[])[];
  /** Selección múltiple (solo la lista plana la usa; la mesa no selecciona en lote). */
  seleccionada?: boolean;
  onToggleSeleccion?: (checked: boolean) => void;
  /** Vista Descartadas: ofrece "Devolver al pool" en vez de Empujar/Descartar. */
  conRestaurar?: boolean;
}

const COLOR_PRIORIDAD: Record<string, string> = {
  alta: "bg-emerald-500",
  media: "bg-amber-400",
  baja: "bg-muted-foreground/40",
};

export function TarjetaHistoria({
  historia,
  clavesAInvalidar,
  seleccionada,
  onToggleSeleccion,
  conRestaurar = false,
}: PropsTarjetaHistoria) {
  const queryClient = useQueryClient();
  const [expandida, setExpandida] = React.useState(false);
  const [detalleAbierto, setDetalleAbierto] = React.useState(false);

  const invalidar = () => {
    for (const clave of clavesAInvalidar) {
      void queryClient.invalidateQueries({ queryKey: clave });
    }
  };

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usarHistoria(historia.id, { generar: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Copy en marcha — aparecerá en el Feed para imagen y aprobación.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartarHistoria(historia.id),
    onSuccess: () => {
      invalidar();
      toast.success("Historia descartada. La encuentras en «Descartadas» si te arrepientes.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const restaurarMut = useMutation({
    mutationFn: () => api.noticias.restaurarHistoria(historia.id),
    onSuccess: () => {
      invalidar();
      toast.success("Historia devuelta al pool.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enCurso = usarMut.isPending || descartarMut.isPending || restaurarMut.isPending;
  const esDescartada = historia.estado === "descartado";
  // Estado REAL de cara al feed (lo deriva el back desde la PIEZA, no solo el cluster).
  const piezaEstado =
    historia.pieza_estado ??
    (historia.estado === "usado" ? "en_feed" : esDescartada ? "descartada" : "en_pool");
  const esUltimaHora = historia.breaking === 1 && piezaEstado !== "descartada";
  const prioridad = nivelPrioridad(historia.score);
  const tieneEnlaces = historia.enlaces && historia.enlaces.length > 0;

  return (
    <Card
      className={`text-sm transition-opacity ${esDescartada ? "opacity-60" : ""} ${
        seleccionada ? "ring-2 ring-primary/40" : ""
      } ${esUltimaHora ? "border-red-500/60" : ""}`}
      data-testid="historia-item"
    >
      <CardContent className="pt-3 pb-3 space-y-1.5">
        {/* Cabecera: (checkbox) + última hora + título + acciones */}
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
            <p className="font-medium leading-snug min-w-0">
              {esUltimaHora && (
                <Badge
                  className="mr-1.5 gap-1 align-middle text-[10px] bg-red-600 hover:bg-red-600 text-white border-0"
                  data-testid="badge-ultima-hora"
                >
                  <Zap className="h-3 w-3" />
                  ÚLTIMA HORA
                </Badge>
              )}
              <button
                type="button"
                className="text-left hover:underline"
                onClick={() => setDetalleAbierto(true)}
                aria-label={`Abrir detalle de «${historia.titulo || "sin título"}»`}
                data-testid="btn-detalle"
              >
                {historia.titulo || "(sin título)"}
              </button>
            </p>
          </div>

          {/* Estado / acciones */}
          <div className="flex shrink-0 items-center gap-1">
            {piezaEstado === "en_feed" ? (
              <Badge variant="ok" className="gap-1 text-xs">
                <CheckCircle2 className="h-3 w-3" />
                En el feed
              </Badge>
            ) : piezaEstado === "generando" ? (
              <Badge
                variant="aviso"
                className="gap-1 text-xs"
                title="La pieza ya existe; la IA está redactando el copy. Aparecerá en el feed al terminar."
              >
                <Loader2 className="h-3 w-3 animate-spin" />
                Generando…
              </Badge>
            ) : piezaEstado === "en_cola" ? (
              <Badge
                variant="aviso"
                className="gap-1 text-xs"
                title="Promovida, pero aún SIN pieza en el feed (copy por encolar, sin redes, o duplicada)."
              >
                <Clock className="h-3 w-3" />
                En cola
              </Badge>
            ) : esDescartada ? (
              <>
                <Badge variant="secondary" className="text-xs">Descartada</Badge>
                {conRestaurar && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                    onClick={() => restaurarMut.mutate()}
                    disabled={enCurso}
                    data-testid="btn-restaurar"
                  >
                    {restaurarMut.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <RotateCcw className="h-3 w-3" />
                    )}
                    Devolver al pool
                  </Button>
                )}
              </>
            ) : (
              <>
                {historia.promovible === true && (
                  <Tooltip
                    label={
                      historia.promovible_motivo ||
                      "Supera el listón: el sistema la produce solo. No hacer nada es una decisión válida."
                    }
                    side="top"
                  >
                    <Badge
                      variant="outline"
                      className="gap-1 text-xs border-evergreen-500 text-evergreen-700"
                      data-testid="badge-sale-sola"
                    >
                      <Sparkles className="h-3 w-3" />
                      Sale sola al feed
                    </Badge>
                  </Tooltip>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                  onClick={() => usarMut.mutate()}
                  disabled={enCurso}
                  aria-label={historia.promovible ? "Adelantar al feed" : "Empujar al feed"}
                  title={
                    historia.promovible
                      ? "El sistema ya la va a producir; esto se salta la espera y la manda ahora."
                      : "Forzar esta nota al feed ahora aunque no supere el listón automático."
                  }
                  data-testid="btn-empujar"
                >
                  {usarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Newspaper className="h-3 w-3" />
                  )}
                  {historia.promovible ? "Adelantar" : "Empujar"}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                  onClick={() => descartarMut.mutate()}
                  disabled={enCurso}
                  aria-label="Descartar historia"
                  data-testid="btn-descartar"
                >
                  {descartarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </Button>
              </>
            )}
          </div>
        </div>

        {/* La FRASE de corroboración: quién la confirma, quién la abrió, hace cuánto. */}
        <p
          className={`text-xs leading-relaxed ${
            historia.verificacion === "dudosa" ? "text-amber-600" : "text-muted-foreground"
          }`}
          data-testid="frase-corroboracion"
        >
          {historia.verificacion === "dudosa" && (
            <ShieldAlert className="mr-1 inline h-3 w-3 align-text-bottom" />
          )}
          {fraseCorroboracion(historia)}
        </p>

        {/* Resumen */}
        {historia.resumen && (
          <p className="text-muted-foreground text-xs leading-relaxed line-clamp-2">
            {historia.resumen}
          </p>
        )}

        {/* Fila de meta: prioridad explicable + traducción + fuentes expandibles */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Tooltip
            label={`${calculoScoreTexto(historia)}\n${factoresRanking(historia)
              .map((f) => `• ${f}`)
              .join("\n")}`}
            side="top"
          >
            <span
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground cursor-default tabular-nums"
              data-testid="punto-prioridad"
            >
              <span className={`h-2 w-2 rounded-full ${COLOR_PRIORIDAD[prioridad]}`} />
              Score {Math.round(historia.score * 100)}
            </span>
          </Tooltip>

          {historia.traducido && historia.idioma && (
            <Tooltip
              label={
                historia.titulo_original
                  ? `Traducido del ${historia.idioma.toUpperCase()} — original: ${historia.titulo_original}`
                  : `Traducido del ${historia.idioma.toUpperCase()}`
              }
              side="top"
            >
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" data-testid="badge-traducido">
                <Globe className="h-3 w-3" />
                {historia.idioma.toUpperCase()}
              </span>
            </Tooltip>
          )}

          {tieneEnlaces && (
            <button
              type="button"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              onClick={() => setExpandida((v) => !v)}
              aria-expanded={expandida}
              aria-label={expandida ? "Ocultar fuentes" : "Ver fuentes corroborantes"}
            >
              {expandida ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              {expandida
                ? "Ocultar fuentes"
                : `Ver ${historia.enlaces.length} fuente${historia.enlaces.length !== 1 ? "s" : ""}`}
            </button>
          )}
        </div>

        {/* Enlaces corroborantes (expandible) */}
        {tieneEnlaces && expandida && (
          <ul className="mt-1 space-y-1 pl-4" data-testid="lista-enlaces">
            {historia.enlaces.map((enlace, i) => (
              <li key={i} className="text-xs flex items-start gap-1">
                <a
                  href={enlace.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:underline flex items-center gap-0.5 break-words flex-1 min-w-0"
                >
                  {enlace.titulo || enlace.url}
                  <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                </a>
                {enlace.fuente && (
                  <span className="text-muted-foreground shrink-0">— {enlace.fuente}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </CardContent>

      {detalleAbierto && (
        <DetalleHistoria
          historia={historia}
          abierto={detalleAbierto}
          onCerrar={() => setDetalleAbierto(false)}
          clavesAInvalidar={clavesAInvalidar}
        />
      )}
    </Card>
  );
}
