/**
 * GUION DEL PARTIDO (run-of-show por fases) — Ola 3.
 *
 * El "matchday workflow" del deporte en vivo tiene 3 fases con su reloj maestro en la hora de
 * inicio: PRE (antes del pitido) · DURANTE (en juego) · POST (después). Cada fase sugiere unos
 * ENTREGABLES, cada uno con su ROL de cobertura (Foto/Video/Texto/Live). Es una CHECKLIST DE
 * REFERENCIA NEUTRA, no un tablero de estado: la app no marca ni fuerza nada, solo RECUERDA qué
 * suele entregarse y en qué fase. Qué roles están de verdad cubiertos lo dice el semáforo agregado
 * (`RolesCubiertos`), no el guion (no se duplica el estado de cobertura aquí).
 *
 * CONFIG DE FRONTEND, sin migración: las plantillas viven aquí. Hay un default ("Partido normal") y
 * un dial por TAMAÑO de partido ("Partido grande") LISTO para variar; el TAMAÑO aún NO viene en los
 * datos (es DEFERIDO_FIXTURES_OPTA), así que el componente siempre usa el default. OJO: el TAMAÑO
 * (normal/grande) es distinto del `tipo_cobertura` (transmisión/imágenes), que SÍ está en los datos
 * y el componente respeta (en «solo imágenes» recorta la fase de directo).
 *
 * DEFERIDOS (NO se construyen aquí; necesitan backend/daemon/datos externos — ver DEFERIDO_*):
 *  - DEFERIDO_SLOTS_BD: auto-crear en BD los slots de rol (Foto/Video/…) por evento desde el guion.
 *    Necesita un endpoint backend que materialice las tareas de cobertura; el guion solo SUGIERE.
 *  - DEFERIDO_PUSH_PITIDO: notificación push "empieza en 30 min". Necesita un daemon que vigile la
 *    cuenta atrás (`minutosHastaEvento`) y empuje al dispositivo; el front solo PINTA el aviso.
 *  - DEFERIDO_FIXTURES_OPTA: feed externo de fixtures/Opta para fijar el TAMAÑO de partido
 *    (normal/grande) y auto-rellenar alineación/resultado. Necesita un proveedor de datos del partido.
 */
import type { RolCobertura } from "./roles";

/** Las 3 fases del matchday, en orden cronológico (su reloj maestro es la hora de inicio). */
export type FaseGuion = "pre" | "vivo" | "post";

/** Un entregable sugerido de una fase. `rol` (opcional) es su etiqueta de cobertura (Foto/Video/…). */
export type Entregable = {
  titulo: string;
  rol?: RolCobertura;
};

/** Una fase del guion con sus entregables sugeridos. */
export type Fase = {
  id: FaseGuion;
  etiqueta: string;
  entregables: Entregable[];
};

/** Una plantilla completa de guion (por TIPO de partido). */
export type PlantillaGuion = {
  id: string;
  etiqueta: string;
  fases: Fase[];
};

/** Metadatos de las fases (orden + etiqueta humana). Compartido por todas las plantillas. */
const FASES: { id: FaseGuion; etiqueta: string }[] = [
  { id: "pre", etiqueta: "Antes" },
  // "Durante el partido", NO "En vivo": evita chocar con el badge «En vivo» del semáforo (otra cosa).
  { id: "vivo", etiqueta: "Durante el partido" },
  { id: "post", etiqueta: "Después" },
];

/**
 * Entregables del partido NORMAL por fase. Cada rol (Foto/Video/Texto/Live) aparece al menos una vez
 * (la fase de directo —«Durante»— concentra Live/Video, que el «solo imágenes» luego recorta).
 */
const ENTREGABLES_NORMAL: Record<FaseGuion, Entregable[]> = {
  pre: [
    { titulo: "Gráfico de matchday", rol: "foto" },
    { titulo: "Previa del partido", rol: "texto" },
    { titulo: "Alineaciones", rol: "texto" },
  ],
  vivo: [
    { titulo: "Gol o clip", rol: "video" },
    { titulo: "Foto del momento", rol: "foto" },
    { titulo: "Minuto a minuto", rol: "live" },
    { titulo: "Reacción en caliente", rol: "texto" },
  ],
  post: [
    { titulo: "Resultado final", rol: "texto" },
    { titulo: "Jugador del partido", rol: "foto" },
    { titulo: "Resumen del partido", rol: "video" },
  ],
};

/** El partido GRANDE = el normal + un entregable extra por fase (más narrativa/cobertura). */
const ENTREGABLES_GRANDE: Record<FaseGuion, Entregable[]> = {
  pre: [...ENTREGABLES_NORMAL.pre, { titulo: "Hilo de contexto", rol: "texto" }],
  vivo: [...ENTREGABLES_NORMAL.vivo, { titulo: "Reacción de la afición", rol: "video" }],
  post: [...ENTREGABLES_NORMAL.post, { titulo: "Análisis táctico", rol: "texto" }],
};

function construirPlantilla(
  id: string,
  etiqueta: string,
  mapa: Record<FaseGuion, Entregable[]>,
): PlantillaGuion {
  return { id, etiqueta, fases: FASES.map((f) => ({ ...f, entregables: mapa[f.id] })) };
}

export const PLANTILLA_NORMAL = construirPlantilla("normal", "Partido normal", ENTREGABLES_NORMAL);
export const PLANTILLA_GRANDE = construirPlantilla("grande", "Partido grande", ENTREGABLES_GRANDE);

/** Registro de plantillas disponibles (el dial por tipo de partido). */
export const PLANTILLAS: PlantillaGuion[] = [PLANTILLA_NORMAL, PLANTILLA_GRANDE];

/** Plantilla por defecto: hoy todos los partidos usan "Partido normal" (no hay tamaño en datos). */
export const PLANTILLA_DEFECTO = PLANTILLA_NORMAL;

/**
 * Plantilla de guion para un TAMAÑO de partido (normal/grande). DIAL PREPARADO: hoy los datos NO
 * traen el tamaño (la BD no lo modela — ver DEFERIDO_FIXTURES_OPTA), así que SIEMPRE cae al default
 * ("Partido normal"). En cuanto el backend exponga el tamaño, basta pasarlo aquí para variar el
 * run-of-show sin tocar el componente. (No confundir con `tipo_cobertura`, que sí está en datos.)
 */
export function plantillaParaTipo(tipo?: string | null): PlantillaGuion {
  return PLANTILLAS.find((p) => p.id === tipo) ?? PLANTILLA_DEFECTO;
}
