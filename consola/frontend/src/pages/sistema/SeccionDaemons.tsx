import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ExternalLink, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { Badge } from "@/components/ui/badge";
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
import { tiempoRelativo } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import { useGuardarAjuste } from "@/pages/configuracion/SeccionFuncionalidad";
import type { ClaseDaemon, EstadoDaemon, LatidoDaemon, Proceso } from "@/types";

import { INTERVALO_RECURSOS_MS } from "./lib";

/** Orden de severidad para listar primero lo que requiere atención. */
const PESO_ESTADO: Record<EstadoDaemon, number> = {
  atrasado: 0,
  error: 1,
  ok: 2,
  inactivo: 3,
};

const ETIQUETA_ESTADO: Record<EstadoDaemon, string> = {
  ok: "OK",
  error: "Error",
  // «Inactivo» se pinta como lo que ES: el gate del daemon está apagado por su ajuste
  // (mismo lenguaje que el 409 de «Barrer ahora»), no un fallo.
  inactivo: "Apagado por ajuste",
  atrasado: "Atrasado",
};

/** Chip de estado de daemon con color semántico (verde/rojo/gris/ámbar). Exportado para que
 *  las tarjetas de agente IA de la página Agentes pinten el mismo estado con el mismo color. */
export function ChipEstadoDaemon({ estado }: { estado: EstadoDaemon }) {
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

/** Intervalo legible ("90 s", "15 min", "4 h"). Exportado para las tarjetas de agente IA. */
export function formatoIntervalo(seg: number): string {
  if (!seg) return "—";
  if (seg < 90) return `${Math.round(seg)} s`;
  if (seg < 5400) return `${Math.round(seg / 60)} min`;
  return `${Math.round(seg / 3600)} h`;
}

function FilaDaemon({
  latido,
  onBarrer,
  barriendo,
  onToggle,
  guardandoClave,
}: {
  latido: LatidoDaemon;
  onBarrer: (daemon: string) => void;
  /** Daemon cuya solicitud de barrido está en vuelo (deshabilita SOLO su botón). */
  barriendo: string | null;
  /** Enciende/apaga el daemon IN-PLACE (POST /api/ajustes con su `clave_gate`). */
  onToggle: (clave: string, valor: boolean) => void;
  /** Clave de ajuste cuyo guardado está en vuelo (deshabilita SOLO ese switch). */
  guardandoClave: string | null;
}) {
  const navigate = useNavigate();
  const barrido = latido.ultimo_barrido
    ? tiempoRelativo(latido.ultimo_barrido)
    : "nunca";
  const solicitado = latido.barrido_solicitado !== "";

  const acciones: EntradaMenuContextual[] = [];

  if (latido.barrible) {
    acciones.push({
      etiqueta: "Barrer ahora",
      icono: Play,
      onClick: () => onBarrer(latido.daemon),
      deshabilitado: barriendo === latido.daemon || solicitado,
    });
  }

  acciones.push({
    etiqueta: "Ver detalle",
    icono: ExternalLink,
    onClick: () => navigate(`/maquina/agentes/${latido.daemon}`),
  });

  return (
    <FilaConAcciones como="tr" kebab="hover" acciones={acciones}>
      <TableCell className="font-medium">{latido.daemon}</TableCell>
      <TableCell>
        <span className="inline-flex flex-wrap items-center gap-1.5">
          <ChipEstadoDaemon estado={latido.estado} />
          {/* Solicitud de barrido forzado pendiente (campo `barrido_solicitado`): el bucle
              del daemon la consume en su siguiente tick (<= ~1 min). */}
          {solicitado && (
            <Badge
              variant="outline"
              className="border-transparent bg-sky-500/15 text-sky-600 dark:text-sky-400"
            >
              Barrido solicitado
            </Badge>
          )}
        </span>
      </TableCell>
      <TableCell className="text-muted-foreground">
        {barrido}
        {latido.ultimo_barrido && latido.duracion_ms > 0 && (
          <span className="text-muted-foreground/70"> · {latido.duracion_ms} ms</span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">
        {formatoIntervalo(latido.intervalo_seg)}
      </TableCell>
      <TableCell className="tabular-nums text-muted-foreground">
        {latido.barridos}
        {latido.errores > 0 && (
          <span className="text-red-500"> ({latido.errores} err)</span>
        )}
      </TableCell>
      <TableCell
        className="max-w-[28ch] truncate text-xs text-muted-foreground"
        title={latido.error_txt || undefined}
      >
        {latido.estado === "error" || latido.errores > 0 ? latido.error_txt : ""}
      </TableCell>
      {/* Encendido IN-PLACE: si el daemon tiene un gate (`clave_gate`), un Switch lo
          enciende/apaga al vuelo (POST /api/ajustes). Si no, es siempre-activo (sin toggle). */}
      <TableCell>
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
      </TableCell>
    </FilaConAcciones>
  );
}

/** Tabla de daemons (cabecera + filas). `filas` ya viene ordenada por severidad. */
function TablaDaemons({
  filas,
  onBarrer,
  barriendo,
  onToggle,
  guardandoClave,
}: {
  filas: LatidoDaemon[];
  onBarrer: (daemon: string) => void;
  barriendo: string | null;
  onToggle: (clave: string, valor: boolean) => void;
  guardandoClave: string | null;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Servicio</TableHead>
          <TableHead>Estado</TableHead>
          <TableHead>Último barrido</TableHead>
          <TableHead>Intervalo</TableHead>
          <TableHead>Barridos</TableHead>
          <TableHead>Último error</TableHead>
          <TableHead>Encendido</TableHead>
          <TableHead className="w-10" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {filas.map((l) => (
          <FilaDaemon
            key={l.daemon}
            latido={l}
            onBarrer={onBarrer}
            barriendo={barriendo}
            onToggle={onToggle}
            guardandoClave={guardandoClave}
          />
        ))}
      </TableBody>
    </Table>
  );
}

/**
 * Sección de DAEMONS (servicios de fondo): estado de cada uno a partir de sus latidos
 * persistidos (`/api/sistema/daemons`). Lo que requiere atención (atrasado/error) se lista
 * primero. Auto-refresco con la misma cadencia que los recursos. Por fila: encendido IN-PLACE
 * (Switch sobre su `clave_gate`; «Siempre activo» si no tiene gate), «Barrer ahora» (POST
 * …/barrer) para los `barrible`, y «Ver detalle» (drill-in a `/maquina/agentes/{daemon}`). El
 * endpoint es de admin (403 si no), así que se monta en contextos admin.
 *
 * Filtra por `clase`/`motor` (campos del API, no nombres hardcodeados):
 *   - Página Agentes: servicios NO-IA de cada motor (`clases=["maquina"]`, `motor=…`).
 *   - Página Sistema: pura infraestructura (`clases=["sistema"]`).
 */
export function SeccionDaemons({
  clases,
  motor,
  titulo = "Servicios de fondo",
  descripcion,
}: {
  /** Clases a incluir (campo `clase` del API). `undefined` = todas. */
  clases?: ClaseDaemon[];
  /** Si se pasa, restringe a los daemons de ese motor (campo `motor` del API). */
  motor?: Proceso;
  /** Título de la tarjeta. */
  titulo?: string;
  /** Subtítulo opcional bajo el título. */
  descripcion?: React.ReactNode;
} = {}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["sistema", "daemons"],
    queryFn: ({ signal }) => api.sistemaDaemons(signal),
    refetchInterval: INTERVALO_RECURSOS_MS,
  });

  // Encendido/apagado IN-PLACE de cada daemon: la mutación COMPARTIDA de ajustes (la misma del
  // presupuesto y los maestros de etapa). Tras guardar, refresca la tabla para que el chip de
  // estado y el switch reflejen el nuevo gate al instante (no solo en el próximo polling).
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
      // Refresca la tabla para que el chip «Barrido solicitado» aparezca al instante.
      void queryClient.invalidateQueries({ queryKey: ["sistema", "daemons"] });
    },
    onError: (e, daemon) => {
      if (e instanceof ApiError && e.status === 409) {
        // El 409 trae la causa exacta del back (gate apagado o daemon no barrible).
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

  if (query.isPending) {
    return <Skeleton className="h-48 w-full rounded-xl" />;
  }
  if (query.isError) {
    return (
      <BloqueError
        titulo="No se pudo leer el estado de los servicios"
        mensaje={mensajeError(query.error)}
        onReintentar={() => void query.refetch()}
        cargando={query.isFetching}
      />
    );
  }

  const { daemons = [], error } = query.data;
  // Filtro por CLASE/MOTOR con los campos del API (no nombres hardcodeados en el front).
  const visibles = daemons.filter(
    (d) =>
      (clases ? clases.includes(d.clase) : true) && (motor ? d.motor === motor : true),
  );
  const ordenados = [...visibles].sort(
    (a, b) =>
      PESO_ESTADO[a.estado] - PESO_ESTADO[b.estado] ||
      a.daemon.localeCompare(b.daemon, "es"),
  );

  const barriendo = barrer.isPending ? (barrer.variables ?? null) : null;
  const onBarrer = (d: string) => barrer.mutate(d);

  return (
    <Card>
      <CardHeader className="p-4 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm text-muted-foreground">
          <Activity className="h-4 w-4" aria-hidden="true" />
          {titulo}
        </CardTitle>
        {descripcion && <p className="text-xs text-muted-foreground">{descripcion}</p>}
      </CardHeader>
      <CardContent className="p-4 pt-0">
        {error ? (
          <p className="text-sm text-muted-foreground">{error}</p>
        ) : ordenados.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sin latidos</p>
        ) : (
          <TablaDaemons
            filas={ordenados}
            onBarrer={onBarrer}
            barriendo={barriendo}
            onToggle={onToggle}
            guardandoClave={guardandoClave}
          />
        )}
      </CardContent>
    </Card>
  );
}
