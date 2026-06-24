/**
 * DetalleHistoriaPagina — el detalle de UNA historia de la Mesa como SUBPÁGINA (URL propia,
 * deep-link), no como diálogo. Clave CALMA: minimalista, con aire, en dos columnas.
 *
 *   · Izquierda (la noticia): titular + última hora, hora·fuente y marca/estado/idioma/
 *     verificación; la frase de corroboración (en tono de cautela si pide corroboración),
 *     resumen y «Fuentes y titulares similares» (línea de tiempo `TimelineFuentes` + la lista
 *     de artículos corroborantes).
 *   · Derecha (el rail de señal): el score (`CalculoScore`) y, al pie, las acciones «Empujar al
 *     feed» y «Descartar» (irreversible, con confirmación, solo si la historia sigue en el pool).
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Globe,
  History,
  Newspaper,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Tooltip } from "@/components/ui/tooltip";
import { api, mensajeError } from "@/lib/api";
import { formatearFechaHora, tiempoRelativoCorto } from "@/lib/fecha";
import { etiquetaLinea } from "@/lib/lineas";
import { estadoCorroboracion, fraseCorroboracion } from "@/lib/noticias/ranking-editorial";
import { nombreFuente } from "@/lib/trends";
import { cn } from "@/lib/utils";

import { BadgeVerificacionFuente, ChipMarca } from "./BadgesInvestigacion";
import { CalculoScore } from "./CalculoScore";
import { TimelineFuentes } from "./TimelineFuentes";

/** Vuelta a la Mesa (la vista de Candidatas vive en el cockpit de Investigación). */
const RUTA_MESA = "/maquina/investigacion?seccion=mesa";

const CLAVE_HISTORIA = (id: string) => ["noticias", "historia", id] as const;

export default function DetalleHistoriaPagina() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: CLAVE_HISTORIA(id),
    queryFn: ({ signal }) => api.noticias.historia(id, signal),
    enabled: !!id,
  });

  // Refresca tanto este detalle como las listas/mesa que muestran la historia.
  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_HISTORIA(id) });
    void queryClient.invalidateQueries({ queryKey: ["noticias", "mesa"] });
    void queryClient.invalidateQueries({ queryKey: ["noticias", "historias"] });
  };

  const usarMut = useMutation({
    mutationFn: () => api.noticias.usarHistoria(id, { generar: true }),
    onSuccess: () => {
      invalidar();
      toast.success("Copy en marcha — aparecerá en el Feed para imagen y aprobación.");
      navigate(RUTA_MESA);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const descartarMut = useMutation({
    mutationFn: () => api.noticias.descartarHistoria(id),
    onSuccess: () => {
      invalidar();
      toast.success("Historia descartada.");
      navigate(RUTA_MESA);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const volver = (
    <Button variant="ghost" size="sm" asChild>
      <Link to={RUTA_MESA}>
        <ArrowLeft className="h-4 w-4" />
        Volver
      </Link>
    </Button>
  );

  if (query.isPending) {
    return (
      <div className="space-y-4">
        {volver}
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="space-y-4">
        {volver}
        <BloqueError
          titulo="No se pudo cargar la historia"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      </div>
    );
  }

  const historia = query.data.historia;
  const esDescartada = historia.estado === "descartado";
  // Estado REAL de cara al feed (lo deriva el back desde la PIEZA, no solo del cluster).
  const piezaEstado =
    historia.pieza_estado ??
    (historia.estado === "usado" ? "en_feed" : esDescartada ? "descartada" : "en_pool");
  const esUltimaHora = historia.breaking === 1 && piezaEstado !== "descartada";
  const enPool = piezaEstado === "en_pool";
  const cuando = tiempoRelativoCorto(historia.primer_visto);
  const cuandoExacto = formatearFechaHora(historia.primer_visto);
  const fuente =
    nombreFuente(historia.primera_fuente_nombre, historia.primera_fuente_id) ||
    historia.marca_nombre;
  const enCurso = usarMut.isPending || descartarMut.isPending;
  const estado = estadoCorroboracion(historia);

  const onDescartar = async () => {
    if (
      await confirmar({
        titulo: "Descartar historia",
        mensaje: "¿Descartar esta historia? No se puede deshacer.",
        destructivo: true,
        textoConfirmar: "Descartar",
      })
    )
      descartarMut.mutate();
  };

  const badgeEstado =
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
    ) : null;

  return (
    <div className="max-w-[1180px] space-y-4">
      {volver}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_348px] lg:items-start lg:gap-16">
        {/* ── La noticia ──────────────────────────────────────────────────── */}
        <div className="min-w-0 max-w-[640px]">
          <div className="space-y-3">
            <h1 className="text-2xl font-medium leading-snug tracking-tight">
              {esUltimaHora && (
                <Badge
                  className="mr-1.5 gap-1 align-middle text-[10px] bg-red-600 hover:bg-red-600 text-white border-0"
                  data-testid="badge-ultima-hora"
                >
                  <Zap className="h-3 w-3" />
                  ÚLTIMA HORA
                </Badge>
              )}
              {historia.titulo || "(sin título)"}
            </h1>

            {(cuando || fuente) && (
              <p
                className="flex items-center gap-1.5 text-sm text-muted-foreground"
                data-testid="hora-fuente"
              >
                {cuando && (
                  <span className="inline-flex items-center gap-1" title={cuandoExacto}>
                    <History className="h-3.5 w-3.5 shrink-0" />
                    {cuando}
                  </span>
                )}
                {cuando && fuente ? <span aria-hidden>·</span> : null}
                {fuente && <span>{fuente}</span>}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <ChipMarca historia={historia} />
              {badgeEstado}
              <Badge variant="outline" className="text-[10px] font-normal text-muted-foreground">
                {etiquetaLinea(historia.breaking === 1 ? "breaking" : historia.categoria)}
              </Badge>
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
                  <span
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground"
                    data-testid="badge-traducido"
                  >
                    <Globe className="h-3 w-3" />
                    {historia.idioma.toUpperCase()}
                  </span>
                </Tooltip>
              )}
              {historia.promovible === true && (
                <Tooltip
                  label={historia.promovible_motivo || "Supera el umbral automático"}
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
            </div>
          </div>

          <p
            className={cn(
              "mt-4 flex items-start gap-2 text-sm leading-relaxed",
              estado.cautela ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground",
            )}
            data-testid="frase-corroboracion"
          >
            {estado.cautela && <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />}
            <span>{fraseCorroboracion(historia)}</span>
          </p>

          {historia.resumen && (
            <p className="mt-4 text-sm leading-relaxed">{historia.resumen}</p>
          )}
          {historia.traducido && historia.titulo_original && (
            <p className="mt-4 border-l border-border pl-4 text-xs leading-relaxed text-muted-foreground">
              Original ({(historia.idioma || "").toUpperCase()}): {historia.titulo_original}
            </p>
          )}

          <section className="mt-6 space-y-4">
            <h2 className="text-[10px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
              Fuentes y titulares similares
            </h2>
            <div className="space-y-2.5">
              <h3 className="text-xs text-muted-foreground">Línea de tiempo de fuentes</h3>
              <TimelineFuentes fuentes={historia.fuentes ?? []} />
            </div>
            {(historia.enlaces?.length ?? 0) > 0 && (
              <div className="space-y-2.5">
                <h3 className="text-xs text-muted-foreground">Titulares similares</h3>
                <ul data-testid="lista-enlaces">
                  {historia.enlaces.map((e, i) => (
                    <li key={i} className="border-t border-border py-3 first:border-t-0 first:pt-0">
                      <a
                        href={e.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group flex items-start gap-2.5 text-[13px] leading-relaxed"
                      >
                        <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                        <span className="min-w-0">
                          <span className="break-words group-hover:text-keni">
                            {e.titulo || e.url}
                          </span>
                          {e.fuente && (
                            <span className="mt-1 block text-xs text-muted-foreground">
                              — {nombreFuente(e.fuente, e.fuente_id)}
                            </span>
                          )}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </div>

        {/* ── El rail de señal: el score + las acciones al pie ─────────────── */}
        <aside className="flex flex-col gap-6">
          <CalculoScore historia={historia} />

          {enPool && (
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="outline"
                className="h-10 w-full justify-center gap-2 bg-card text-sm font-medium shadow-sm transition hover:bg-card hover:shadow-md"
                onClick={() => usarMut.mutate()}
                disabled={enCurso}
                data-testid="btn-empujar"
              >
                {usarMut.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <Newspaper className="h-4 w-4" />
                )}
                Empujar al feed
              </Button>
              <Button
                variant="ghost"
                className="h-10 w-full justify-center gap-2 text-sm font-normal text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                onClick={onDescartar}
                disabled={enCurso}
                data-testid="btn-descartar"
              >
                {descartarMut.isPending ? (
                  <Spinner className="h-4 w-4" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                Descartar
              </Button>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
