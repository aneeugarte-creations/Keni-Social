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
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { confirmar } from "@/components/comunes/confirmar";
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
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { formatearHora } from "@/lib/fecha";
import { fraseCorroboracion, nivelPrioridad } from "@/lib/noticias/ranking-editorial";
import type { Historia } from "@/types";

import { BadgeVerificacionFuente, ChipMarca } from "./BadgesInvestigacion";
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

// El puntito gradúa el score: alta en verde, media en ámbar, baja en gris apagado.
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
  // Lo esencial que se ve en colapsado junto al título: hora de apertura y fuente que abrió.
  const hora = formatearHora(historia.primer_visto);
  const fuente = historia.primera_fuente_nombre || historia.marca_nombre;

  // Acción primaria (click izq): NO ejecuta sin más — abre un diálogo de confirmación
  // antes de mutar (regla: el click izquierdo solo abre pop-ups, nunca ejecuta a ciegas).
  // Empujar/adelantar en pool; restaurar en la vista de descartadas. Como esta acción
  // vive en el click izquierdo, NO se duplica en el menú contextual (regla de dedup).
  const accionPrimaria =
    esEnPool && !enCurso
      ? async () => {
          if (
            await confirmar({
              mensaje: `¿${historia.promovible ? "Adelantar" : "Empujar"} "${historia.titulo || "esta historia"}" al feed?`,
              textoConfirmar: historia.promovible ? "Adelantar" : "Empujar",
            })
          )
            usarMut.mutate();
        }
      : conRestaurar && esDescartada && !enCurso
        ? async () => {
            if (
              await confirmar({
                mensaje: `¿Devolver "${historia.titulo || "esta historia"}" al pool?`,
                textoConfirmar: "Devolver",
              })
            )
              restaurarMut.mutate();
          }
        : undefined;

  // Menú contextual (click der / long-press / teclado): destructivas + secundarias.
  // Empujar/adelantar y devolver al pool NO van aquí: son la acción de click izquierdo.
  const accionesMenu: EntradaMenuContextual[] = [
    ...(esEnPool
      ? [
          {
            etiqueta: "Descartar",
            icono: Trash2,
            onClick: () => descartarMut.mutate(),
            destructivo: true,
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
        className={`text-sm transition hover:border-keni-300 focus-within:border-keni-300 ${esDescartada ? "opacity-60" : ""} ${
          seleccionada ? "ring-2 ring-primary/40" : ""
        }`}
        data-testid="historia-item"
      >
        <CardContent className="pt-3 pb-3 space-y-1.5">
          {/* Cabecera (siempre visible): (checkbox) + chevron + título + hora · fuente.
              El chevron alterna el detalle expandido; el resto vive bajo `expandida`. */}
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
              <button
                type="button"
                className="mt-0.5 shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                onClick={() => setExpandida((v) => !v)}
                aria-expanded={expandida}
                aria-label={expandida ? "Colapsar historia" : "Expandir historia"}
                data-testid="btn-expandir"
              >
                {expandida ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </button>
              <div className="min-w-0 flex-1 space-y-0.5">
                <p className="font-medium leading-snug min-w-0">
                  {esUltimaHora && (
                    <Zap
                      className="mr-1 inline-block h-3.5 w-3.5 shrink-0 align-middle text-red-600"
                      aria-label="Última hora"
                      data-testid="badge-ultima-hora"
                    />
                  )}
                  <button
                    type="button"
                    className="text-left hover:underline"
                    onClick={() => setDetalleAbierto(true)}
                    aria-label={`Abrir detalle de «${historia.titulo || "sin título"}»`}
                    data-testid="btn-detalle"
                  >
                    {historia.traduciendo ? (
                      <span className="inline-flex items-center gap-1 italic text-muted-foreground">
                        <Spinner className="h-3 w-3" />
                        {historia.titulo || "Traduciendo…"}
                      </span>
                    ) : (
                      historia.titulo || "(sin título)"
                    )}
                  </button>
                </p>
                {(hora || fuente) && (
                  <p className="text-xs text-muted-foreground" data-testid="hora-fuente">
                    {hora}
                    {hora && fuente ? " · " : ""}
                    {fuente}
                  </p>
                )}
              </div>
            </div>

            {/* Flanco derecho: el SCORE va SIEMPRE visible (escaneable sin desplegar);
                los badges de estado solo al expandir, a su izquierda. */}
            <div className="mt-0.5 flex shrink-0 items-center gap-2">
              {expandida &&
                (piezaEstado === "en_feed" ? (
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
                    <Spinner className="h-3 w-3" />
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
                          className="gap-1 text-xs border-emerald-500 text-emerald-700 dark:text-emerald-300"
                          data-testid="badge-sale-sola"
                        >
                          <Sparkles className="h-3 w-3" />
                          Sale sola al feed
                        </Badge>
                      </Tooltip>
                    )}
                    {enCurso && (
                      <Spinner className="h-3 w-3 text-muted-foreground" />
                    )}
                  </>
                ))}
              {/* Score (siempre visible): dato escaneable; "Ver score" en el menú abre el desglose. */}
              <span
                className="inline-flex items-center gap-1.5 text-xs text-muted-foreground tabular-nums"
                data-testid="punto-prioridad"
              >
                <span className={`h-2 w-2 rounded-full ${COLOR_PRIORIDAD[prioridad]}`} />
                Score {Math.round(historia.score * 100)}
              </span>
            </div>
          </div>

          {expandida && (
            <>
              {/* La FRASE de corroboración: quién la confirma, quién la abrió, hace cuánto.
                  Si la verificación es dudosa, se eleva a un aviso ámbar; si no, texto gris. */}
              {historia.verificacion === "dudosa" ? (
                <Aviso className="py-1.5" data-testid="frase-corroboracion">
                  {fraseCorroboracion(historia)}
                </Aviso>
              ) : (
                <p className="text-xs leading-relaxed text-muted-foreground" data-testid="frase-corroboracion">
                  {fraseCorroboracion(historia)}
                </p>
              )}

              {/* Resumen */}
              {historia.resumen && (
                <p className="text-muted-foreground text-xs leading-relaxed line-clamp-2">
                  {historia.resumen}
                </p>
              )}

              {/* Fila de meta: marca + resultado de verificación + traducción (el score va arriba) */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <ChipMarca historia={historia} />

                <BadgeVerificacionFuente verificacion_fuente={historia.verificacion_fuente} />

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

              {/* Enlaces corroborantes */}
              {tieneEnlaces && (
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
            </>
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
