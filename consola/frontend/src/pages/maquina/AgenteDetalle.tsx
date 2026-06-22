/**
 * Página de DETALLE de un daemon de la máquina (`/maquina/agentes/:agente`).
 *
 * Lo abren las TABLAS de daemons (Sistema · servicios de sistema; los cockpits · servicios no-IA
 * de su motor) para ver UNO de cerca: su estado actual, su LOG por barrido (cada iteración del
 * bucle con su duración/resultado/resumen) y los controles in-place (encender/apagar vía su
 * `clave_gate`, «Barrer ahora», y —para los daemons de IA— editar su prompt sin salir de la
 * página). No hay lista de Agentes: los dos agentes IA son los dos cockpits.
 *
 * No hay endpoint de «un daemon»: se filtra la lista (`GET /api/sistema/daemons`) por nombre.
 * El log viene de `GET /api/sistema/daemons/{daemon}/barridos`. Ambos son de admin (403 si no).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  Clock,
  Coins,
  Hash,
  Info,
  Pencil,
  Play,
  SlidersHorizontal,
} from "lucide-react";
import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { ChipEstadoDaemon } from "@/components/comunes/ChipEstado";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { TituloPagina } from "@/components/layout/encabezado";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFechaHora, tiempoRelativo } from "@/lib/fecha";
import { INTERVALO_DETALLE_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { FilaAjuste, useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import { LogBarridos } from "@/pages/maquina/LogBarridos";
import type { ClaseDaemon, LatidoDaemon } from "@/types";

const ETIQUETA_CLASE: Record<ClaseDaemon, string> = {
  ia: "IA",
  maquina: "Máquina",
  sistema: "Sistema",
};

/** Intervalo legible ("90 s", "15 min", "4 h"); espejo del de SeccionDaemons. */
function formatoIntervalo(seg: number): string {
  if (!seg) return "—";
  if (seg < 90) return `${Math.round(seg)} s`;
  if (seg < 5400) return `${Math.round(seg / 60)} min`;
  return `${Math.round(seg / 3600)} h`;
}

/** Dato de cabecera (etiqueta + valor) con icono opcional. */
function Dato({
  icono: Icono,
  etiqueta,
  children,
}: {
  icono: typeof Clock;
  etiqueta: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center gap-2">
      <Icono className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <span className="text-xs text-muted-foreground">{etiqueta}:</span>
      <span className="text-sm">{children}</span>
    </div>
  );
}

/** Controles in-place del agente: toggle de encendido inline + acciones secundarias en menú. */
function Controles({ latido }: { latido: LatidoDaemon }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const guardar = useGuardarAjuste();
  const onToggle = (clave: string, valor: boolean) =>
    guardar.mutate(
      { clave, valor },
      {
        onSuccess: () =>
          void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] }),
      },
    );
  const guardandoClave = guardar.isPending ? (guardar.variables?.clave ?? null) : null;

  const barrer = useMutation({
    mutationFn: (daemon: string) => api.sistemaDaemonBarrer(daemon),
    onSuccess: (r) => {
      toast.success(`Barrido de «${r.daemon}» solicitado: correrá en su siguiente tick.`);
      void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] });
    },
    onError: (e, daemon) => {
      if (e instanceof ApiError && e.status === 409) {
        const detalle = typeof e.cuerpo?.error === "string" ? e.cuerpo.error : null;
        toast.error(
          detalle ?? `«${daemon}» está apagado por su ajuste: enciéndelo antes de barrer.`,
        );
      } else if (e instanceof ApiError && e.status === 404) {
        toast.error(`No hay ningún daemon registrado con el nombre «${daemon}».`);
        void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] });
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const solicitado = latido.barrido_solicitado !== "";
  const barriendo = barrer.isPending;
  const prompts = latido.prompts;

  const acciones = [
    ...(latido.barrible
      ? [
          {
            etiqueta: "Barrer ahora",
            icono: Play,
            onClick: () => barrer.mutate(latido.daemon),
            deshabilitado: barriendo || solicitado,
          },
        ]
      : []),
    // «Editar prompt» abre la SUBPÁGINA del documento (mismo editor completo que una fase), no un
    // overlay: cada prompt se gestiona en su propia URL.
    ...prompts.map((p) => ({
      etiqueta: `Editar prompt: ${p.etiqueta}`,
      icono: Pencil,
      onClick: () => navigate(`/maquina/contexto/doc/${p.doc}`),
    })),
  ];

  return (
    <FilaConAcciones
      como="div"
      kebab="nunca"
      realce
      acciones={acciones}
      className="rounded-lg border bg-card text-card-foreground shadow-sm"
    >
      <div className="p-4">
        <div className="pb-2 text-sm font-semibold text-muted-foreground">Controles</div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          {/* Encendido IN-PLACE: Switch inline sobre la `clave_gate`. Refleja el flag PROPIO
              configurado (`gate_activo`), no el efectivo: encenderlo con la máquina apagada se
              queda ON (estado «en espera») en vez de rebotar. */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">Encendido:</span>
            {latido.clave_gate ? (
              <Switch
                checked={Boolean(latido.gate_activo)}
                disabled={guardandoClave === latido.clave_gate}
                onCheckedChange={(v) => onToggle(latido.clave_gate as string, v)}
                aria-label={`Encender/apagar el daemon ${latido.daemon}`}
              />
            ) : (
              <span className="text-xs text-muted-foreground">Siempre activo</span>
            )}
          </div>
          {latido.estado === "en_espera" && (
            <p className="w-full text-xs text-sky-600 dark:text-sky-400">
              Encendido, pero la máquina de contenido está apagada: no correrá hasta que la
              enciendas.
            </p>
          )}
        </div>
      </div>
    </FilaConAcciones>
  );
}

/** Bloque de DESCRIPCIÓN: qué hace EXACTAMENTE el daemon (texto del backend, `latidos.descripcion_de`). */
function DescripcionDaemon({ texto }: { texto: string }) {
  if (!texto) return null;
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Info className="h-4 w-4" aria-hidden="true" />
          Qué hace
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <p className="text-sm leading-relaxed text-muted-foreground">{texto}</p>
      </CardContent>
    </Card>
  );
}

/** AJUSTES del daemon: sus knobs del catálogo, editables IN-PLACE (reusa `FilaAjuste`). Guardar
 *  invalida la query de daemons para que el valor (y el estado/switch derivados) se refresquen. */
function AjustesDaemon({ ajustes }: { ajustes: LatidoDaemon["ajustes"] }) {
  const queryClient = useQueryClient();
  const guardar = useGuardarAjuste();
  if (!ajustes.length) return null;
  const onGuardar = (cuerpo: { clave: string; valor?: boolean | number | string }) =>
    guardar.mutate(cuerpo, {
      onSuccess: () =>
        void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] }),
    });
  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          Ajustes
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {ajustes.map((a) => (
          <FilaAjuste key={a.clave} ajuste={a} onGuardar={onGuardar} guardando={guardar.isPending} />
        ))}
      </CardContent>
    </Card>
  );
}

/** Sección «Analizar»: conteos + tarjeta clicable a actividad del proceso (si aplica). */
function Analizar({ latido }: { latido: LatidoDaemon }) {
  const navigate = useNavigate();

  return (
    <FilaConAcciones
      como="div"
      kebab="nunca"
      realce
      onPrimaria={
        latido.motor
          ? () => navigate(`/maquina/computo?proceso=${latido.motor}`)
          : undefined
      }
      acciones={[]}
      className="rounded-lg border bg-card text-card-foreground shadow-sm"
    >
      <div className="p-4">
        <div className="flex items-center gap-2 pb-2 text-sm font-semibold text-muted-foreground">
          <Activity className="h-4 w-4" aria-hidden="true" />
          Analizar
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
          <Dato icono={Hash} etiqueta="Barridos totales">
            <span className="tabular-nums">{latido.barridos}</span>
          </Dato>
          <Dato icono={AlertTriangle} etiqueta="Errores">
            <span
              className={cn("tabular-nums", latido.errores > 0 && "text-red-500")}
            >
              {latido.errores}
            </span>
          </Dato>
          {latido.gasta_tokens && (
            <Badge variant="aviso">
              <Coins className="mr-1 h-3.5 w-3.5" aria-hidden="true" />
              gasta tokens
            </Badge>
          )}
          {latido.error_txt && (
            <p className="w-full text-xs text-red-600 dark:text-red-400">
              Último error: {latido.error_txt}
            </p>
          )}
        </div>
      </div>
    </FilaConAcciones>
  );
}

export default function AgenteDetalle() {
  const { agente } = useParams<{ agente: string }>();
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_DETALLE_MS,
  });

  // El detalle se abre desde las tablas de daemons (Sistema / cockpits): «Atrás» vuelve a su
  // origen en vez de a una página fija. El «←» vive en la BARRA SUPERIOR del shell (vía
  // TituloPagina), no como fila del cuerpo.
  const atras = () => navigate(-1);

  if (query.isPending) {
    return (
      <>
        <TituloPagina titulo="Agente" onAtras={atras} />
        <div className="space-y-4 p-4">
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-48 w-full rounded-xl" />
        </div>
      </>
    );
  }
  if (query.isError) {
    return (
      <>
        <TituloPagina titulo="Agente" onAtras={atras} />
        <div className="space-y-4 p-4">
          <BloqueError
            titulo="No se pudo leer el estado de los agentes"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        </div>
      </>
    );
  }

  const latido = (query.data.daemons ?? []).find((d) => d.daemon === agente);

  // Daemon inexistente: ni en la lista (retirado, mal escrito o nunca registrado).
  if (!latido) {
    return (
      <>
        <TituloPagina titulo="Agente" onAtras={atras} />
        <div className="space-y-4 p-4">
          <BloqueError
            titulo="Agente no encontrado"
            mensaje={`No hay ningún agente registrado con el nombre «${agente}». Puede haber sido renombrado o retirado.`}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        </div>
      </>
    );
  }

  const ultimoBarrido = latido.ultimo_barrido
    ? tiempoRelativo(latido.ultimo_barrido)
    : "nunca";

  return (
    <>
      {/* Cabecera (← volver + nombre legible) en la BARRA SUPERIOR del shell, no como fila del
          cuerpo. El nombre no se repite en la tarjeta de abajo (que conserva id, badges y métricas). */}
      <TituloPagina titulo={latido.etiqueta} onAtras={atras} />
      <div className="space-y-4 p-4">
      {/* Cabecera: id + badges (clase, motor, estado) + último barrido e intervalo. */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-muted-foreground">{latido.daemon}</span>
            <Badge variant="secondary">{ETIQUETA_CLASE[latido.clase]}</Badge>
            {latido.motor && (
              <Badge variant="outline" className="capitalize">
                {latido.motor}
              </Badge>
            )}
            <ChipEstadoDaemon estado={latido.estado} />
            {latido.barrido_solicitado !== "" && (
              <Badge variant="info">Barrido solicitado</Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4 pt-0">
          <Dato icono={Clock} etiqueta="Último barrido">
            <span title={formatearFechaHora(latido.ultimo_barrido) || undefined}>
              {ultimoBarrido}
            </span>
          </Dato>
          <Dato icono={Activity} etiqueta="Intervalo">
            {formatoIntervalo(latido.intervalo_seg)}
          </Dato>
        </CardContent>
      </Card>

      <DescripcionDaemon texto={latido.descripcion} />
      <Controles latido={latido} />
      {/* El gate (`clave_gate`) YA es el toggle «Encendido» de Controles; se filtra de los Ajustes
          para no pintar su switch DOS veces (la 1ª clave de `ajustes` suele ser el propio gate). */}
      <AjustesDaemon ajustes={latido.ajustes.filter((a) => a.clave !== latido.clave_gate)} />
      <LogBarridos daemon={latido.daemon} />
      <Analizar latido={latido} />
      </div>
    </>
  );
}
