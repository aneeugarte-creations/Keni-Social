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
  ArrowLeft,
  CheckCircle2,
  Clock,
  Coins,
  FileText,
  Hash,
  Pencil,
  Play,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { EditorPromptOverlay } from "@/components/biblioteca/EditorPromptOverlay";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFechaHora, tiempoRelativo } from "@/lib/fecha";
import { duracion } from "@/lib/formato";
import { INTERVALO_DETALLE_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import type { ClaseDaemon, EstadoDaemon, LatidoDaemon } from "@/types";

// Cuántos barridos pedir al log (el back acota a su cota dura por daemon).
const LIMITE_BARRIDOS = 50;

const ETIQUETA_ESTADO: Record<EstadoDaemon, string> = {
  ok: "OK",
  error: "Error",
  inactivo: "Apagado por ajuste",
  atrasado: "Atrasado",
};
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

/** Chip de estado con color semántico (verde/rojo/gris/ámbar). */
function ChipEstado({ estado }: { estado: EstadoDaemon }) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "border-transparent",
        estado === "ok" && "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
        estado === "error" && "bg-red-500/15 text-red-600 dark:text-red-400",
        estado === "atrasado" && "bg-amber-500/15 text-amber-600 dark:text-amber-400",
        estado === "inactivo" && "bg-muted text-muted-foreground",
      )}
    >
      {ETIQUETA_ESTADO[estado]}
    </Badge>
  );
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
  const [promptAbierto, setPromptAbierto] = React.useState<string | null>(null);

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
    ...prompts.map((p) => ({
      etiqueta: `Editar prompt: ${p.etiqueta}`,
      icono: Pencil,
      onClick: () => setPromptAbierto(p.doc),
    })),
  ];

  return (
    <>
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
            {/* Encendido IN-PLACE: Switch inline sobre la `clave_gate` */}
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Encendido:</span>
              {latido.clave_gate ? (
                <Switch
                  checked={latido.activo}
                  disabled={guardandoClave === latido.clave_gate}
                  onCheckedChange={(v) => onToggle(latido.clave_gate as string, v)}
                  aria-label={`Encender/apagar el daemon ${latido.daemon}`}
                />
              ) : (
                <span className="text-xs text-muted-foreground">Siempre activo</span>
              )}
            </div>
          </div>
        </div>
      </FilaConAcciones>
      <EditorPromptOverlay
        docId={promptAbierto}
        abierto={promptAbierto !== null}
        onCerrar={() => setPromptAbierto(null)}
      />
    </>
  );
}

/** Log por barrido: tabla de `GET …/barridos` (nuevo primero). */
function LogBarridos({ daemon }: { daemon: string }) {
  const query = useQuery({
    queryKey: ["sistema", "daemons", daemon, "barridos"],
    queryFn: ({ signal }) => api.sistemaDaemonBarridos(daemon, LIMITE_BARRIDOS, signal),
    refetchInterval: INTERVALO_DETALLE_MS,
  });

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <FileText className="h-4 w-4" aria-hidden="true" />
          Log por barrido
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {query.isPending ? (
          <Skeleton className="h-40 w-full rounded-xl" />
        ) : query.isError ? (
          <BloqueError
            titulo="No se pudo leer el log de barridos"
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : query.data.barridos.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin barridos</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Hora</TableHead>
                <TableHead>Resultado</TableHead>
                <TableHead>Duración</TableHead>
                <TableHead>Resumen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.barridos.map((b) => (
                <TableRow key={b.id}>
                  <TableCell
                    className="whitespace-nowrap text-muted-foreground"
                    title={formatearFechaHora(b.ts_inicio)}
                  >
                    {tiempoRelativo(b.ts_inicio)}
                  </TableCell>
                  <TableCell>
                    {b.ok ? (
                      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                        OK
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
                        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                        Error
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="whitespace-nowrap tabular-nums text-muted-foreground">
                    {b.duracion_ms > 0 ? duracion(b.duracion_ms) : "—"}
                  </TableCell>
                  <TableCell className="text-sm">
                    {/* `resumen` puede venir vacío hoy: si falta, el error (cuando lo hay) o un
                        guion. Así una fila nunca queda muda. */}
                    {b.resumen ? (
                      <span>{b.resumen}</span>
                    ) : b.error_txt ? (
                      <span className="text-red-600 dark:text-red-400">{b.error_txt}</span>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                    {b.resumen && b.error_txt && (
                      <span className="mt-0.5 block text-xs text-red-600 dark:text-red-400">
                        {b.error_txt}
                      </span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
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
            <Badge
              variant="outline"
              className="border-transparent bg-amber-500/15 text-amber-600 dark:text-amber-400"
            >
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
  // origen en vez de a una página fija (ya no hay lista de Agentes).
  const volver = (
    <Button variant="ghost" size="sm" className="mb-2 -ml-2 w-fit" onClick={() => navigate(-1)}>
      <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
      Atrás
    </Button>
  );

  if (query.isPending) {
    return (
      <div className="space-y-4 p-4">
        {volver}
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-48 w-full rounded-xl" />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="space-y-4 p-4">
        {volver}
        <BloqueError
          titulo="No se pudo leer el estado de los agentes"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      </div>
    );
  }

  const latido = (query.data.daemons ?? []).find((d) => d.daemon === agente);

  // Daemon inexistente: ni en la lista (retirado, mal escrito o nunca registrado).
  if (!latido) {
    return (
      <div className="space-y-4 p-4">
        {volver}
        <BloqueError
          titulo="Agente no encontrado"
          mensaje={`No hay ningún agente registrado con el nombre «${agente}». Puede haber sido renombrado o retirado.`}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      </div>
    );
  }

  const ultimoBarrido = latido.ultimo_barrido
    ? tiempoRelativo(latido.ultimo_barrido)
    : "nunca";

  return (
    <div className="space-y-4 p-4">
      {volver}

      {/* Cabecera: nombre legible + badges (clase, motor, estado) + último barrido e intervalo. */}
      <Card>
        <CardHeader className="p-4 pb-2">
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-lg">{latido.etiqueta}</CardTitle>
            <span className="font-mono text-xs text-muted-foreground">{latido.daemon}</span>
            <Badge variant="secondary">{ETIQUETA_CLASE[latido.clase]}</Badge>
            {latido.motor && (
              <Badge variant="outline" className="capitalize">
                {latido.motor}
              </Badge>
            )}
            <ChipEstado estado={latido.estado} />
            {latido.barrido_solicitado !== "" && (
              <Badge
                variant="outline"
                className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
              >
                Barrido solicitado
              </Badge>
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

      <Controles latido={latido} />
      <LogBarridos daemon={latido.daemon} />
      <Analizar latido={latido} />
    </div>
  );
}
