/**
 * TarjetaHistoria — la tarjeta editorial de una historia del pool.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart2,
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

import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { fraseCorroboracion, nivelPrioridad } from "@/lib/noticias/ranking-editorial";
import type { Historia } from "@/types";

import { BadgeVeredictoFuente, ChipMarca } from "./BadgesInvestigacion";
import { CalculoScore } from "./CalculoScore";
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
  const [calculoAbierto, setCalculoAbierto] = React.useState(false);

  const invalidar = () => {
    for (const clave of clavesAInvalidar) {
      void queryClient.invalidateQueries({ queryKey: clave });
    }
  };

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usarHistoria(historia.id, { generar: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Copy en marcha");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartarHistoria(historia.id),
    onSuccess: () => {
      invalidar();
      toast.success("Historia descartada");
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
  const esEnPool = piezaEstado === "en_pool";

  // Acción primaria (click izq): empujar/adelantar en pool; restaurar en vista descartadas.
  const accionPrimaria =
    esEnPool && !enCurso
      ? () => usarMut.mutate()
      : conRestaurar && esDescartada && !enCurso
        ? () => restaurarMut.mutate()
        : undefined;

  // Menú contextual (click der / long-press / teclado): destructivas + secundarias.
  const accionesMenu: EntradaMenuContextual[] = [
    ...(esEnPool
      ? [
          {
            etiqueta: historia.promovible ? "Adelantar al feed" : "Empujar al feed",
            icono: Newspaper,
            onClick: () => usarMut.mutate(),
            deshabilitado: enCurso,
          },
          {
            etiqueta: "Descartar",
            icono: Trash2,
            onClick: () => descartarMut.mutate(),
            destructivo: true,
            deshabilitado: enCurso,
          },
        ]
      : []),
    ...(conRestaurar && esDescartada
      ? [
          {
            etiqueta: "Devolver al pool",
            icono: RotateCcw,
            onClick: () => restaurarMut.mutate(),
            deshabilitado: enCurso,
          },
        ]
      : []),
    {
      etiqueta: "Ver score",
      icono: BarChart2,
      onClick: () => setCalculoAbierto(true),
    },
    ...(tieneEnlaces
      ? [
          {
            etiqueta: expandida
              ? "Ocultar fuentes"
              : `Ver ${historia.enlaces.length} fuente${historia.enlaces.length !== 1 ? "s" : ""}`,
            icono: expandida ? ChevronDown : ChevronRight,
            onClick: () => setExpandida((v) => !v),
          },
        ]
      : []),
  ];

  return (
    <FilaConAcciones
      como="div"
      kebab="nunca"
      realce
      onPrimaria={accionPrimaria}
      acciones={accionesMenu}
    >
      <Card
        className={`text-sm transition-opacity ${esDescartada ? "opacity-60" : ""} ${
          seleccionada ? "ring-2 ring-primary/40" : ""
        } ${esUltimaHora ? "border-red-500/60" : ""}`}
        data-testid="historia-item"
      >
        <CardContent className="pt-3 pb-3 space-y-1.5">
          {/* Cabecera: (checkbox) + última hora + título + estado */}
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

            {/* Estado visual — sin botones de acción; las acciones van al menú contextual */}
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
                  title="Redactando copy"
                >
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Generando…
                </Badge>
              ) : piezaEstado === "en_cola" ? (
                <Badge
                  variant="aviso"
                  className="gap-1 text-xs"
                  title="En cola de procesamiento"
                >
                  <Clock className="h-3 w-3" />
                  En cola
                </Badge>
              ) : esDescartada ? (
                <Badge variant="secondary" className="text-xs">Descartada</Badge>
              ) : (
                <>
                  {historia.promovible === true && (
                    <Tooltip
                      label={
                        historia.promovible_motivo ||
                        "Supera el umbral automático"
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
                  {enCurso && (
                    <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />
                  )}
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

          {/* Fila de meta: marca + veredicto de verificación + prioridad + traducción */}
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <ChipMarca historia={historia} />

            <BadgeVeredictoFuente veredicto={historia.qa_veredicto} />

            {/* Score: dato visual inline; "Ver score" en el menú contextual abre el desglose. */}
            <span
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums"
              data-testid="punto-prioridad"
            >
              <span className={`h-2 w-2 rounded-full ${COLOR_PRIORIDAD[prioridad]}`} />
              Score {Math.round(historia.score * 100)}
            </span>

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
          </div>

          {/* Enlaces corroborantes (expandible vía menú contextual → "Ver fuentes") */}
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

        {/* Pop-up COMPACTO del cálculo del score (un tooltip no da para leer una fórmula). */}
        {calculoAbierto && (
          <Dialog open={calculoAbierto} onOpenChange={(o) => !o && setCalculoAbierto(false)}>
            <DialogContent className="max-w-md" data-testid="popup-calculo">
              <DialogHeader>
                <DialogTitle className="text-base">
                  Score {Math.round(historia.score * 100)}
                </DialogTitle>
                <DialogDescription className="line-clamp-1">{historia.titulo}</DialogDescription>
              </DialogHeader>
              <CalculoScore historia={historia} />
            </DialogContent>
          </Dialog>
        )}
      </Card>
    </FilaConAcciones>
  );
}
