/**
 * Página AGENTES (`/maquina/agentes`): los AGENTES IA de la máquina de contenido —los daemons
 * PROACTIVOS (`clase=ia`) que corren `claude -p`— como protagonistas, agrupados por motor
 * (Investigación | Producción). Es la pestaña de aterrizaje del hub de la máquina; sus hermanas
 * (Cómputo, Economía, Actividad) viven en pestañas aparte.
 *
 * Cada agente es UNA tarjeta con todo su control in-place: encendido (toggle sobre su
 * `clave_gate`), «Barrer ahora», editar sus prompts de la Biblioteca y un acceso a su detalle
 * (el log por barrido). Estado, último barrido, intervalo, barridos/errores y si gasta tokens
 * salen del latido del API (`clase`/`motor`/…), sin listas de daemons hardcodeadas. Solo admin
 * (el endpoint de daemons es admin). Sondeo en vivo.
 *
 * `?proceso=investigacion|produccion` (los cockpits enlazan aquí) ENFOCA la página a un motor.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Clock, Coins, FileText, Pencil, Play, RefreshCw } from "lucide-react";
import * as React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFechaHora, tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_VIVO_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { nombreLegible, PROMPTS_POR_DAEMON } from "@/pages/maquina/agentes-meta";
import { PROC_META } from "@/pages/monitor/comun";
import { ChipEstadoDaemon, formatoIntervalo } from "@/pages/sistema/SeccionDaemons";
import type { LatidoDaemon, Proceso } from "@/types";

/** Los dos motores de la máquina (ADR 0011), en orden de flujo. */
const MOTORES: Proceso[] = ["investigacion", "produccion"];

/** TARJETA de un AGENTE IA (clase=ia): el agente PROACTIVO que corre `claude -p`, con TODO su
 *  control in-place (encender/apagar, barrer, editar prompts) y un acceso al detalle (el log). */
function TarjetaAgente({
  latido,
  onToggle,
  guardandoClave,
  onBarrer,
  barriendo,
  onEditarPrompt,
}: {
  latido: LatidoDaemon;
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
  onBarrer: (daemon: string) => void;
  barriendo: boolean;
  onEditarPrompt: (doc: string) => void;
}) {
  const solicitado = latido.barrido_solicitado !== "";
  const barrido = latido.ultimo_barrido ? tiempoRelativo(latido.ultimo_barrido) : "nunca";
  const prompts = PROMPTS_POR_DAEMON[latido.daemon] ?? [];

  return (
    <Card className="border-border">
      <CardHeader className="p-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <CardTitle className="flex flex-wrap items-center gap-2 text-sm">
              <Bot className="h-4 w-4 text-sky-600" aria-hidden="true" />
              {nombreLegible(latido.daemon)}
              <Badge
                variant="outline"
                className="border-transparent bg-sky-500/15 text-[10px] text-sky-600 dark:text-sky-400"
              >
                IA
              </Badge>
              {latido.gasta_tokens && (
                <Badge
                  variant="outline"
                  className="border-transparent bg-amber-500/15 text-[10px] text-amber-600 dark:text-amber-400"
                >
                  <Coins className="mr-1 h-3 w-3" aria-hidden="true" />
                  gasta tokens
                </Badge>
              )}
            </CardTitle>
          </div>
          {/* Encendido IN-PLACE (clave_gate). */}
          {latido.clave_gate ? (
            <Switch
              checked={latido.activo}
              disabled={guardandoClave === latido.clave_gate}
              onCheckedChange={(v) => onToggle(latido.clave_gate as string, v)}
              aria-label={`Encender/apagar el agente ${latido.daemon}`}
            />
          ) : (
            <span className="shrink-0 text-xs text-muted-foreground">Siempre activo</span>
          )}
        </div>

        {/* Estado + señales. */}
        <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <ChipEstadoDaemon estado={latido.estado} />
          {solicitado && (
            <Badge
              variant="outline"
              className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
            >
              Barrido solicitado
            </Badge>
          )}
          <span title={formatearFechaHora(latido.ultimo_barrido) || undefined}>
            último barrido {barrido}
          </span>
          <span aria-hidden="true">·</span>
          <span>cada {formatoIntervalo(latido.intervalo_seg)}</span>
          <span aria-hidden="true">·</span>
          <span className="tabular-nums">
            {latido.barridos} barridos
            {latido.errores > 0 && (
              <span className="text-red-500"> · {latido.errores} err</span>
            )}
          </span>
        </div>
        {latido.error_txt && (latido.estado === "error" || latido.errores > 0) && (
          <p className="mt-1 flex items-start gap-1 text-xs text-red-600 dark:text-red-400">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span className="truncate" title={latido.error_txt}>
              {latido.error_txt}
            </span>
          </p>
        )}
      </CardHeader>

      {/* Acciones in-place: barrer, editar prompt(s) y ver el log (detalle). */}
      <CardContent className="flex flex-wrap items-center gap-2 p-4 pt-0">
        {latido.barrible && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => onBarrer(latido.daemon)}
            disabled={barriendo || solicitado}
          >
            <Play className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Barrer ahora
          </Button>
        )}
        {prompts.map((p) => (
          <Button key={p.doc} variant="outline" size="sm" onClick={() => onEditarPrompt(p.doc)}>
            <Pencil className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Editar: {p.etiqueta}
          </Button>
        ))}
        <Button variant="ghost" size="sm" asChild className="ml-auto">
          <Link to={`/maquina/agentes/${latido.daemon}`}>
            <FileText className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
            Ver log
          </Link>
        </Button>
      </CardContent>
    </Card>
  );
}

/** Columna de un MOTOR: cabecera + tarjetas de sus agentes IA. */
function ColumnaMotor({
  motor,
  agentes,
  ...controles
}: {
  motor: Proceso;
  agentes: LatidoDaemon[];
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
  onBarrer: (daemon: string) => void;
  barriendoDaemon: string | null;
  onEditarPrompt: (doc: string) => void;
}) {
  const meta = PROC_META[motor];
  return (
    <section className="space-y-3">
      <h2 className={cn("flex items-center gap-2 text-lg font-semibold", meta.texto)}>
        <span className={cn("h-2.5 w-2.5 rounded-full", meta.barra)} aria-hidden="true" />
        {meta.etiqueta}
      </h2>
      {agentes.length === 0 ? (
        <p className="text-sm text-muted-foreground">Sin agentes IA en este motor.</p>
      ) : (
        agentes.map((latido) => (
          <TarjetaAgente
            key={latido.daemon}
            latido={latido}
            onToggle={controles.onToggle}
            guardandoClave={controles.guardandoClave}
            onBarrer={controles.onBarrer}
            barriendo={controles.barriendoDaemon === latido.daemon}
            onEditarPrompt={controles.onEditarPrompt}
          />
        ))
      )}
    </section>
  );
}

export default function Agentes() {
  const { usuario } = useSesion();
  const esAdmin = usuario?.rol === "admin";
  const [searchParams, setSearchParams] = useSearchParams();
  const crudoProceso = searchParams.get("proceso");
  const proceso: Proceso | undefined =
    crudoProceso === "investigacion" || crudoProceso === "produccion" ? crudoProceso : undefined;
  const qc = useQueryClient();
  const [promptAbierto, setPromptAbierto] = React.useState<string | null>(null);

  // Latidos de los daemons: endpoint de ADMIN. Mismo queryKey que SeccionDaemons => dedupe.
  const daemonsQuery = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_VIVO_MS,
    enabled: esAdmin,
  });

  // Encendido/apagado IN-PLACE: la mutación COMPARTIDA de ajustes; tras guardar, refresca latidos.
  const guardarAjuste = useGuardarAjuste();
  const onToggle = (clave: string, valor: boolean) =>
    guardarAjuste.mutate(
      { clave, valor },
      { onSuccess: () => void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] }) },
    );
  const guardandoClave = guardarAjuste.isPending ? (guardarAjuste.variables?.clave ?? null) : null;

  const barrer = useMutation({
    mutationFn: (daemon: string) => api.sistemaDaemonBarrer(daemon),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });
    },
    onError: (e, daemon) => {
      if (e instanceof ApiError && e.status === 409) {
        const detalle = typeof e.cuerpo?.error === "string" ? e.cuerpo.error : null;
        toast.error(detalle ?? `«${daemon}» está apagado por su ajuste: enciéndelo antes de barrer.`);
      } else if (e instanceof ApiError && e.status === 404) {
        toast.error(`No hay ningún daemon registrado con el nombre «${daemon}».`);
        void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });
      } else {
        toast.error(mensajeError(e));
      }
    },
  });
  const barriendoDaemon = barrer.isPending ? (barrer.variables ?? null) : null;

  const refrescar = () => void qc.invalidateQueries({ queryKey: ["sistema", "daemons"] });

  const quitarProceso = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("proceso");
    setSearchParams(params, { replace: true });
  };

  const motores: Proceso[] = proceso ? [proceso] : MOTORES;
  const daemons = daemonsQuery.data?.daemons ?? [];
  // Agentes IA por motor (derivado del latido: clase=ia, sin listas hardcodeadas).
  const agentesDe = (m: Proceso) => daemons.filter((d) => d.clase === "ia" && d.motor === m);

  return (
    <>
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={RefreshCw} onClick={refrescar} disabled={daemonsQuery.isFetching}>
            Actualizar
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      {/* Prefiltro de proceso (?proceso=). */}
      {proceso && (
        <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <span>
            Enfocado a{" "}
            <strong className={PROC_META[proceso].texto}>{PROC_META[proceso].etiqueta}</strong>.
          </span>
          <Button variant="ghost" size="sm" onClick={quitarProceso}>
            Ver ambos motores
          </Button>
        </div>
      )}

      {!esAdmin ? (
        <Card>
          <CardContent className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" aria-hidden="true" />
            El estado y el control de los agentes solo están disponibles para administradores.
          </CardContent>
        </Card>
      ) : daemonsQuery.isError ? (
        <BloqueError
          titulo="No se pudo leer el estado de los agentes"
          mensaje={mensajeError(daemonsQuery.error)}
          onReintentar={() => void daemonsQuery.refetch()}
          cargando={daemonsQuery.isFetching}
        />
      ) : daemonsQuery.isPending ? (
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div
          className={cn("grid grid-cols-1 gap-8", motores.length > 1 && "xl:grid-cols-2 xl:gap-6")}
        >
          {motores.map((m) => (
            <ColumnaMotor
              key={m}
              motor={m}
              agentes={agentesDe(m)}
              onToggle={onToggle}
              guardandoClave={guardandoClave}
              onBarrer={(d) => barrer.mutate(d)}
              barriendoDaemon={barriendoDaemon}
              onEditarPrompt={setPromptAbierto}
            />
          ))}
        </div>
      )}

      <EditorPromptOverlay
        docId={promptAbierto}
        abierto={promptAbierto !== null}
        onCerrar={() => setPromptAbierto(null)}
      />
    </>
  );
}
