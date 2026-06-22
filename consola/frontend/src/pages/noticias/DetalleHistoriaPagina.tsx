/**
 * DetalleHistoriaPagina — el detalle de UNA historia de la Mesa como SUBPÁGINA (URL propia,
 * deep-link), no como diálogo. Secciones separadas:
 *
 *   · Cabecera/overview: última hora, titular, hora·fuente, marca, estado de la pieza,
 *     idioma/traducción, verificación de la fuente y la frase de corroboración + resumen.
 *   · Score: el desglose del ranking (`CalculoScore`), montado UNA sola vez aquí.
 *   · Fuentes y titulares similares: la línea de tiempo de outlets (`TimelineFuentes`) y la
 *     lista de artículos corroborantes (`historia.enlaces`).
 *   · Acciones: «Empujar al feed» y «Descartar» (irreversible, con confirmación). Solo si la
 *     historia sigue en el pool.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  ExternalLink,
  Globe,
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
import { formatearHora } from "@/lib/fecha";
import { etiquetaLinea } from "@/lib/lineas";
import { fraseCorroboracion } from "@/lib/noticias/ranking-editorial";

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
  const hora = formatearHora(historia.primer_visto);
  const fuente = historia.primera_fuente_nombre || historia.marca_nombre;
  const enCurso = usarMut.isPending || descartarMut.isPending;

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
    <div className="space-y-6">
      {volver}

      {/* ── Cabecera / overview ─────────────────────────────────────────────── */}
      <div className="space-y-3">
        <h1 className="text-xl font-semibold leading-tight">
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

        {(hora || fuente) && (
          <p className="text-sm text-muted-foreground" data-testid="hora-fuente">
            {hora}
            {hora && fuente ? " · " : ""}
            {fuente}
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

        <p className="text-sm leading-relaxed text-muted-foreground" data-testid="frase-corroboracion">
          {fraseCorroboracion(historia)}
        </p>

        {historia.resumen && <p className="text-sm leading-relaxed">{historia.resumen}</p>}
        {historia.traducido && historia.titulo_original && (
          <p className="text-xs text-muted-foreground">
            Original ({(historia.idioma || "").toUpperCase()}): {historia.titulo_original}
          </p>
        )}

        {/* ── Acciones ──────────────────────────────────────────────────────── */}
        {enPool && (
          <div className="flex flex-wrap items-center gap-2 border-t pt-4">
            <Button
              className="gap-1"
              onClick={() => usarMut.mutate()}
              disabled={enCurso}
              data-testid="btn-empujar"
            >
              {usarMut.isPending ? <Spinner className="h-4 w-4" /> : <Newspaper className="h-4 w-4" />}
              Empujar al feed
            </Button>
            <Button
              variant="ghost"
              className="gap-1 text-destructive hover:text-destructive"
              onClick={onDescartar}
              disabled={enCurso}
              data-testid="btn-descartar"
            >
              {descartarMut.isPending ? <Spinner className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
              Descartar
            </Button>
          </div>
        )}
      </div>

      {/* ── Score ───────────────────────────────────────────────────────────── */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Score
        </h2>
        <CalculoScore historia={historia} />
      </section>

      {/* ── Fuentes y titulares similares ───────────────────────────────────── */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Fuentes y titulares similares
        </h2>
        <div className="space-y-1.5">
          <h3 className="text-sm font-semibold">Línea de tiempo de fuentes</h3>
          <TimelineFuentes fuentes={historia.fuentes ?? []} />
        </div>
        {(historia.enlaces?.length ?? 0) > 0 && (
          <div className="space-y-1.5">
            <h3 className="text-sm font-semibold">Titulares similares</h3>
            <ul className="space-y-1" data-testid="lista-enlaces">
              {historia.enlaces.map((e, i) => (
                <li key={i} className="flex items-start gap-1 text-xs">
                  <a
                    href={e.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex min-w-0 flex-1 items-center gap-0.5 break-words hover:underline"
                  >
                    {e.titulo || e.url}
                    <ExternalLink className="h-3 w-3 shrink-0 text-muted-foreground" />
                  </a>
                  {e.fuente && <span className="shrink-0 text-muted-foreground">— {e.fuente}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
}
