/**
 * Selector CANÓNICO de cobertura de un evento de la rota.
 *
 * El estado de cobertura de un partido/evento (quién lo cogió, si lo cubre un turno, qué roles
 * faltan, en qué fase temporal está) se reconstruía a mano en DOS sitios con la misma lógica:
 * el Panorama/`Tareas.tsx` (cobertura por turno + claims) y `Calendario.tsx` (colocación del
 * evento en la rejilla + semáforo de cabecera). Este módulo unifica esa derivación en una API
 * pura y tipada, reusando los tipos y primitivas existentes — NO redefine modelo ni inventa
 * reglas: replica la semántica que hoy pintan el chip del calendario y el Panorama.
 *
 * Fuentes reutilizadas:
 *  - `agrupar` / `Cobertura` (pages/tareas/tipos): claims (clase=tarea con `evento_id`) → cubridores.
 *  - `ROLES_COBERTURA` / `rolesCubiertos` (pages/tareas/roles): roles tipados por `formato`.
 *  - `franjaIdParaHoraEvento` (pages/rota/comun): bucketing hora→franja (misma que la rejilla).
 *  - `posicionTemporal` / `minutosHastaEvento` (lib/fecha): fase temporal e instantes CDMX.
 */
import {
  diaCDMX,
  minutosHastaEvento,
  type PosicionTemporal,
} from "@/lib/fecha";
import { ausenciaTocaDia, franjaIdParaHoraEvento } from "@/pages/rota/comun";
import {
  ROLES_COBERTURA,
  rolesCubiertos,
  type RolCobertura,
} from "@/pages/tareas/roles";
import { agrupar, type Cobertura } from "@/pages/tareas/tipos";
import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  Publicacion,
  TurnoRota,
} from "@/types";

/**
 * Umbral (minutos) de la fase PRE-LIVE del semáforo: cuando falta ≤ esto para el saque, el evento
 * pasa de «Programado» plano a «Empieza en X min». Es el mismo valor que `UMBRAL_PRELIVE_MIN` de
 * `tarjetas.tsx` (`SemaforoCobertura`) — la fuente que hoy pinta la luz.
 */
export const UMBRAL_PRELIVE_MIN = 120;

/**
 * Estado de cobertura de un evento, de más a menos específico (la precedencia que hoy aplica el
 * chip del calendario y el Panorama):
 *  - `cogido`: alguien lo COGIÓ (≥1 claim / tarea de cobertura con responsable).
 *  - `cubierto-turno`: nadie lo cogió, pero HAY un turno en la franja de su hora ese día.
 *  - `sin-cubrir`: ni cogido ni cubierto por turno → hueco real.
 */
export type EstadoCobertura = "sin-cubrir" | "cubierto-turno" | "cogido";

/**
 * Fase temporal del evento respecto a AHORA (deriva de `posicionTemporal` + `minutosHastaEvento`):
 *  - `programado`: aún falta (> umbral pre-live, o sin hora y de un día futuro).
 *  - `empieza-en`: PRE-LIVE — aún no empieza pero el saque está a ≤ `UMBRAL_PRELIVE_MIN` min.
 *  - `en-vivo`: transcurriendo (dentro de la ventana «durante»).
 *  - `terminado`: ya pasó (rebasada la ventana).
 */
export type Semaforo = "programado" | "empieza-en" | "en-vivo" | "terminado";

/** Un turno que cubre el evento (persona de turno en la franja de su hora ese día). */
export interface CubridorPorTurno {
  turnoId: string;
  miembroId: string;
  miembroNombre: string;
  franjaId: string;
}

/** La cobertura derivada de un evento: titularidad + cobertura por turno + roles + fase temporal. */
export interface CoberturaEventoDerivada {
  /** El evento subyacente (fuente de fecha/hora/título). */
  evento: EventoRota;
  /** Quién COGIÓ el evento (claims con responsable). Vacío = nadie lo cogió. */
  cubridores: Publicacion[];
  /** La cobertura completa agrupada (cubridores + roles soltados `libres`), si tiene ≥1 claim. */
  cobertura?: Cobertura;
  /** Turnos que cubren el evento por solape de franja. Solo informativo si ya está `cogido`. */
  porTurno: CubridorPorTurno[];
  /** Roles de `ROLES_COBERTURA` aún sin cubrir (los cubiertos salen de los claims, por `formato`). */
  rolesFaltantes: RolCobertura[];
  /** Estado de cobertura con la precedencia cogido > cubierto-turno > sin-cubrir. */
  estado: EstadoCobertura;
  /** Fase temporal (programado / empieza-en / en-vivo / terminado). */
  semaforo: Semaforo;
  /** Minutos hasta el saque (positivo = aún no empieza). `undefined` sin fecha. */
  minutosParaInicio?: number;
}

/** Mapea la posición temporal cruda + el pre-live al enum del semáforo canónico. */
function semaforoDesde(pos: PosicionTemporal | null, minutos: number | null): Semaforo {
  if (pos === "durante") return "en-vivo";
  if (pos === "despues") return "terminado";
  // pos === "antes" (o null sin fecha, que cae a "programado"): PRE-LIVE si el saque está cerca.
  if (pos === "antes" && minutos != null && minutos > 0 && minutos <= UMBRAL_PRELIVE_MIN) {
    return "empieza-en";
  }
  return "programado";
}

/**
 * Turnos que cubren un evento por SOLAPE DE FRANJA: la franja en que cae la hora del evento ese
 * día (vía `franjaIdParaHoraEvento`, el mismo bucketing de la rejilla) tiene ≥1 turno. Replica
 * EXACTAMENTE las dos copias actuales: comparan `turno.franja_id === franjaId && turno.fecha ===
 * evento.fecha` sin un filtro extra de `es_descanso` (la franja de descanso solo sale como FALLBACK
 * del bucketing cuando ninguna franja laboral contiene la hora; ver `franjaIdParaHoraEvento`).
 *
 * Una persona AUSENTE ese día (vacaciones/descanso/baja/otro) NO cuenta como capacidad aunque
 * tenga turno en la franja: su turno no cubre el evento. Sin este filtro, alguien de vacaciones
 * aparece como «cubierto por turno» y el hueco real queda oculto.
 */
function turnosQueCubren(
  evento: EventoRota,
  turnos: TurnoRota[],
  franjas: FranjaSemana[],
  ausencias: AusenciaRota[] = [],
): CubridorPorTurno[] {
  if (!evento.fecha) return [];
  const fecha = evento.fecha;
  const franjaId = franjaIdParaHoraEvento(evento.hora, franjas);
  if (!franjaId) return [];
  const ausente = (miembroId: string) =>
    ausencias.some((a) => a.miembro_id === miembroId && ausenciaTocaDia(a, fecha));
  return turnos
    .filter((t) => t.franja_id === franjaId && t.fecha === fecha && !ausente(t.miembro_id))
    .map((t) => ({
      turnoId: t.id,
      miembroId: t.miembro_id,
      miembroNombre: t.miembro_nombre,
      franjaId,
    }));
}

/** Roles de `ROLES_COBERTURA` que NO están cubiertos por los claims actuales (por `formato`). */
function rolesFaltantesDe(cubridores: Publicacion[]): RolCobertura[] {
  const cubiertos = new Set(rolesCubiertos(cubridores));
  return ROLES_COBERTURA.filter((r) => !cubiertos.has(r));
}

/**
 * Deriva el estado canónico de cobertura de UN evento a partir de:
 *  - `claims`: tareas de cobertura (clase=tarea con `evento_id`) — la titularidad real.
 *  - `turnos` + `franjas`: la rota de la semana del evento (para la cobertura por turno).
 *  - `ahora`: instante de referencia para el semáforo (inyectado para tests deterministas).
 *
 * Nota sobre `ahora`: el semáforo de la app deriva la fase de `Date.now()` (vía `posicionTemporal`/
 * `minutosHastaEvento`, que no aceptan un "ahora" inyectado). El parámetro `ahora` está en la firma
 * por contrato y determinismo de tests; HOY solo se usa cuando difiere del reloj real (se aplica un
 * desplazamiento equivalente sobre los minutos). Con `ahora = new Date()` el resultado es idéntico
 * a lo que pinta la UI.
 */
export function derivarCoberturaEvento(
  evento: EventoRota,
  claims: Publicacion[],
  turnos: TurnoRota[],
  franjas: FranjaSemana[],
  ahora: Date = new Date(),
  ausencias: AusenciaRota[] = [],
): CoberturaEventoDerivada {
  // Claims de ESTE evento, repartidos en cubridores/libres por `agrupar` (misma fuente que el
  // Panorama). `agrupar` resuelve la cobertura sobre TODAS las tareas; filtramos a este evento.
  const claimsEvento = claims.filter((t) => t.evento_id === evento.id);
  const { coberturas } = agrupar(claimsEvento, [evento]);
  const cobertura = coberturas.find((c) => c.eventoId === evento.id);
  const cubridores = cobertura?.cubridores ?? [];

  const porTurno = turnosQueCubren(evento, turnos, franjas, ausencias);

  // Precedencia: cogido > cubierto-turno > sin-cubrir (idéntica al chip y al Panorama).
  const estado: EstadoCobertura =
    cubridores.length > 0 ? "cogido" : porTurno.length > 0 ? "cubierto-turno" : "sin-cubrir";

  // Fase temporal. `posicionTemporal`/`minutosHastaEvento` usan el reloj real; corregimos por el
  // desfase de `ahora` respecto a ese reloj para que un "ahora" inyectado (tests) sea determinista.
  const desfaseMin = (ahora.getTime() - Date.now()) / 60000;
  const minRel = minutosHastaEvento(evento.fecha, evento.hora);
  const minutos = minRel == null ? null : Math.round(minRel - desfaseMin);
  const pos = posicionTemporalAjustada(evento.fecha, evento.hora, minutos, ahora);

  return {
    evento,
    cubridores,
    cobertura,
    porTurno,
    rolesFaltantes: rolesFaltantesDe(cubridores),
    estado,
    semaforo: semaforoDesde(pos, minutos),
    minutosParaInicio: minutos ?? undefined,
  };
}

/**
 * Posición temporal coherente con `minutos` (el desfase de `ahora` ya aplicado). Sin hora concreta
 * se sitúa por DÍA CDMX (futuro → antes, hoy → en curso todo el día, pasado → después), idéntico a
 * `posicionTemporal`; con hora, la fase se decide por los minutos hasta el saque y la ventana
 * «durante» (180', como el original). El día «hoy» se deriva de `ahora` para que un `ahora`
 * inyectado (tests) sea determinista; con `ahora = new Date()` coincide con el reloj real.
 */
function posicionTemporalAjustada(
  fecha: string | null | undefined,
  hora: string | null | undefined,
  minutos: number | null,
  ahora: Date,
): PosicionTemporal | null {
  if (!fecha) return null;
  // Sin hora concreta (igual que `_aMinutos` en fecha.ts: no hay "HH:MM"): cómputo por DÍA.
  const sinHora = !hora || !/^\d{1,2}:\d{2}/.test(String(hora).trim());
  if (sinHora) {
    const dia = String(fecha).slice(0, 10);
    const hoy = diaCDMX(ahora);
    if (dia > hoy) return "antes";
    if (dia < hoy) return "despues";
    return "durante";
  }
  if (minutos == null) return null;
  if (minutos > 0) return "antes";
  return minutos > -180 ? "durante" : "despues";
}

/** Conteo agregado de cobertura para el KPI de cabecera (cuántos cubiertos / pronto / en vivo / huecos). */
export interface ResumenCobertura {
  total: number;
  /** Eventos con titularidad (cogidos) o cubiertos por turno — no son huecos. */
  cubiertos: number;
  /** Eventos en PRE-LIVE (empieza-en): el saque está a ≤ umbral. */
  pronto: number;
  /** Eventos en vivo (transcurriendo ahora). */
  enVivo: number;
  /** Huecos reales: ni cogidos ni cubiertos por turno. */
  sinCubrir: number;
}

/**
 * Resume la cobertura de un conjunto de eventos (para el KPI de cabecera). `cubiertos` = no-huecos
 * (cogido o cubierto-turno), `sinCubrir` = huecos reales; `pronto`/`enVivo` son cortes del semáforo
 * (independientes del estado de cobertura). Misma derivación por evento que `derivarCoberturaEvento`.
 */
export function resumenCobertura(
  eventos: EventoRota[],
  claims: Publicacion[],
  turnos: TurnoRota[],
  franjas: FranjaSemana[],
  ahora: Date = new Date(),
  ausencias: AusenciaRota[] = [],
): ResumenCobertura {
  const r: ResumenCobertura = { total: 0, cubiertos: 0, pronto: 0, enVivo: 0, sinCubrir: 0 };
  for (const evento of eventos) {
    const d = derivarCoberturaEvento(evento, claims, turnos, franjas, ahora, ausencias);
    r.total += 1;
    if (d.estado === "sin-cubrir") r.sinCubrir += 1;
    else r.cubiertos += 1;
    if (d.semaforo === "empieza-en") r.pronto += 1;
    if (d.semaforo === "en-vivo") r.enVivo += 1;
  }
  return r;
}
