/**
 * El «doctor» en la UI (`GET /api/estado`, Fase 1 de la consolidación del Monitor):
 * la zona de ESTADO que sustituye al viejo BannerAlertas. Dos consumidores:
 *
 *  - `ZonaEstado` (Monitor, todo el equipo): si todo está ok, una línea discreta;
 *    si no, la lista de chequeos con su siguiente paso. Los chequeos `admin:true`
 *    (infra/métricas) solo se muestran a admins. Integra además los TEMAS BLOQUEADOS
 *    del pipeline (`GET /api/pipelines/problemas`) de forma compacta y plegable.
 *  - `AvisosDoctor` (página Sistema, admin): solo los chequeos de operador
 *    (`admin:true`) que no están ok; sin problemas no pinta nada.
 */
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, CircleCheck, OctagonX, TriangleAlert } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { INTERVALO_SERIE_MS } from "@/lib/refresco";
import { cn } from "@/lib/utils";
import type { ChequeoEstado } from "@/types";

/** Query compartida del doctor (misma queryKey en Monitor y Sistema: una sola petición). */
function useDoctor() {
  return useQuery({
    queryKey: ["estado", "doctor"],
    queryFn: ({ signal }) => api.estado(signal),
    // El doctor corre sondas reales en el back: cadencia moderada (no es la cola en vivo).
    refetchInterval: INTERVALO_SERIE_MS,
  });
}

/** Una fila de chequeo NO-ok: nombre + detalle + el paso accionable que manda el back. */
function FilaChequeo({ chequeo }: { chequeo: ChequeoEstado }) {
  const esError = chequeo.estado === "error";
  const Icono = esError ? OctagonX : TriangleAlert;
  return (
    <li className="flex items-start gap-2.5 px-3.5 py-2.5 text-sm">
      <Icono
        className={cn("mt-0.5 h-4 w-4 shrink-0", esError ? "text-red-500" : "text-amber-500")}
        aria-hidden="true"
      />
      <div className="min-w-0 space-y-0.5">
        <p className="font-medium">{chequeo.nombre}</p>
        <p className="text-xs text-muted-foreground">{chequeo.detalle}</p>
        {chequeo.siguiente_paso && (
          <p className="text-xs text-foreground/80">→ {chequeo.siguiente_paso}</p>
        )}
      </div>
    </li>
  );
}

/** Lista de chequeos con problema, como franja de alerta (ámbar; rojo si hay errores). */
function ListaChequeos({ chequeos }: { chequeos: ChequeoEstado[] }) {
  const hayError = chequeos.some((c) => c.estado === "error");
  return (
    <ul
      role="alert"
      className={cn(
        "divide-y divide-border/50 rounded-xl border",
        hayError ? "border-red-500/40 bg-red-500/5" : "border-amber-500/40 bg-amber-500/5",
      )}
    >
      {chequeos.map((c) => (
        <FilaChequeo key={c.id} chequeo={c} />
      ))}
    </ul>
  );
}

/**
 * Temas BLOQUEADOS del pipeline (veredicto `problema`): salieron del flujo y nadie los
 * reintenta solo. Compacto y plegable: una franja con el conteo; al abrir, tema + marca +
 * motivo, con enlace al detalle de su run para decidir (relanzar a mano / descartar).
 */
function TemasBloqueados({ marca }: { marca?: string }) {
  const [abierto, setAbierto] = React.useState(false);
  const q = useQuery({
    queryKey: ["pipelines", "problemas", marca ?? "todas"],
    queryFn: ({ signal }) => api.pipelinesProblemas({ marca }, signal),
    refetchInterval: INTERVALO_SERIE_MS,
  });
  const items = q.data?.problemas ?? [];
  const total = q.data?.total ?? items.length;
  if (items.length === 0) return null;
  const Flecha = abierto ? ChevronDown : ChevronRight;
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-500/5">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left text-sm"
      >
        <OctagonX className="h-4 w-4 shrink-0 text-red-500" aria-hidden="true" />
        <span className="font-medium">Temas bloqueados ({total})</span>
        <span className="hidden text-xs text-muted-foreground sm:inline">
          · fuera del flujo hasta que alguien decida
        </span>
        <Flecha className="ml-auto h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </button>
      {abierto && (
        <ul className="divide-y divide-border/50 border-t border-border/50">
          {items.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 px-3.5 py-2 text-sm">
              <Badge variant="outline" className="shrink-0 font-normal text-muted-foreground">
                {p.marca_nombre || p.marca}
              </Badge>
              <Link
                to={`/datos/produccion/pipelines/${encodeURIComponent(p.id)}`}
                className="min-w-0 truncate font-medium underline-offset-2 hover:underline"
                title={p.titulo}
              >
                {p.titulo || p.id}
              </Link>
              <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={p.error || p.resumen}>
                {p.error || p.resumen}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Zona de ESTADO del Monitor (arriba de la pestaña En vivo, visible para todos): el doctor.
 * Con todo ok, una sola línea discreta; con avisos/errores, las tarjetas de cada chequeo
 * NO-ok (los `admin:true` solo a admins) + los temas bloqueados del pipeline.
 */
export function ZonaEstado({ esAdmin, marca }: { esAdmin: boolean; marca?: string }) {
  const doctor = useDoctor();
  const visibles = (doctor.data?.resultados ?? []).filter((c) => esAdmin || !c.admin);
  const conProblema = visibles.filter((c) => c.estado !== "ok");
  // Sin datos aún no se pinta nada (la zona es diagnóstico, no debe meter ruido), pero el
  // DOCTOR CAÍDO no desaparece en silencio: «todo en orden» y «no sé leer el estado» no
  // pueden verse igual, así que el fallo se avisa con reintento.
  return (
    <div className="space-y-3">
      {doctor.isError ? (
        <AvisoDoctorCaido doctor={doctor} />
      ) : (
        doctor.data &&
        (conProblema.length === 0 ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <CircleCheck className="h-4 w-4 text-emerald-500" aria-hidden="true" />
            Máquina operando con normalidad.
          </p>
        ) : (
          <ListaChequeos chequeos={conProblema} />
        ))
      )}
      <TemasBloqueados marca={marca} />
    </div>
  );
}

/** Aviso de DOCTOR CAÍDO (`GET /api/estado` falló): franja ámbar con reintento, en vez de
 *  una zona vacía que parezca «todo bien». Compacto: no es un chequeo más, es que no se
 *  pudo preguntar. */
function AvisoDoctorCaido({ doctor }: { doctor: ReturnType<typeof useDoctor> }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-2.5 rounded-xl border border-amber-500/40 bg-amber-500/5 px-3.5 py-2.5 text-sm"
    >
      <TriangleAlert className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
      <span className="min-w-0 flex-1">No se pudo leer el estado de la máquina.</span>
      <button
        type="button"
        onClick={() => void doctor.refetch()}
        disabled={doctor.isFetching}
        className="shrink-0 text-xs font-medium underline-offset-2 hover:underline disabled:opacity-50"
      >
        {doctor.isFetching ? "Reintentando…" : "Reintentar"}
      </button>
    </div>
  );
}

/**
 * Avisos del doctor para la página SISTEMA (admin): solo los chequeos de operador
 * (`admin:true`) que requieren atención. Sustituye al viejo BannerAlertas (que recomputaba
 * umbrales en el front); ahora el back es la única fuente del juicio. Sin problemas, nada.
 */
export function AvisosDoctor() {
  const doctor = useDoctor();
  // El doctor caído tampoco se calla aquí: sin él, Sistema parecería sin avisos.
  if (doctor.isError) return <AvisoDoctorCaido doctor={doctor} />;
  const avisos = (doctor.data?.resultados ?? []).filter((c) => c.admin && c.estado !== "ok");
  if (avisos.length === 0) return null;
  return <ListaChequeos chequeos={avisos} />;
}
