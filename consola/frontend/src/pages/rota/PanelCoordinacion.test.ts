import { describe, expect, it } from "vitest";

import type {
  AusenciaRota,
  EventoRota,
  FranjaSemana,
  Publicacion,
  SwapTurno,
  TurnoRota,
} from "@/types";

import { derivarPanelCoordinacion } from "./PanelCoordinacion";

// --- Factorías compactas (cast por brevedad: la derivación solo lee unos campos) -----------

const LUNES = "2026-06-29"; // semana lun 29-jun → dom 5-jul

/** Un evento de la rota. Por defecto: 1-jul 20:00 (dentro de la semana de LUNES). */
function ev(over: Partial<EventoRota> = {}): EventoRota {
  return {
    id: "ev1",
    titulo: "Cruz Azul vs América",
    fecha: "2026-07-01",
    hora: "20:00",
    tipo_cobertura: "transmision",
    prioridad: "media",
    ...over,
  } as unknown as EventoRota;
}

/** Una tarea de cobertura (claim) con responsable → cubridor del evento. */
function claim(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "c1",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "u1",
    responsable_nombre: "luis",
    formato: "foto",
    fecha_objetivo: "2026-07-01",
    hora_objetivo: "20:00",
    ...over,
  } as unknown as Publicacion;
}

function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-tarde",
    lunes: LUNES,
    nombre: "Tarde",
    inicio: "14:00",
    fin: "22:00",
    orden: 1,
    es_descanso: false,
    marca: "",
    marca_nombre: "",
    ...over,
  } as unknown as FranjaSemana;
}

function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: LUNES,
    fecha: "2026-07-01",
    miembro_id: "u9",
    miembro_nombre: "ana",
    franja_id: "f-tarde",
    franja_nombre: "Tarde",
    inicio: "",
    fin: "",
    ...over,
  } as unknown as TurnoRota;
}

function ausencia(over: Partial<AusenciaRota> = {}): AusenciaRota {
  return {
    id: "a1",
    miembro_id: "u9",
    miembro_nombre: "ana",
    tipo: "vacaciones",
    desde: "2026-07-01",
    hasta: "2026-07-01",
    motivo: "",
    ...over,
  } as unknown as AusenciaRota;
}

function swap(over: Partial<SwapTurno> = {}): SwapTurno {
  return {
    id: "s1",
    solicitante_id: "u1",
    solicitante_nombre: "Ana",
    destinatario_id: "u2",
    destinatario_nombre: "Bruno",
    fecha_a: "2026-06-29",
    franja_a: "f-a",
    fecha_b: "2026-06-30",
    franja_b: "f-b",
    motivo: "",
    estado: "propuesto",
    respuesta_destinatario: "",
    respuesta_admin: "",
    creado: "2026-06-20T12:00:00",
    actualizado: "2026-06-20T12:00:00",
    decidido_destinatario: "",
    decidido_admin: "",
    aplicado: "",
    marca: "",
    marca_nombre: "",
    tipo: "intercambio",
    ...over,
  } as SwapTurno;
}

const FRANJAS: FranjaSemana[] = [
  franja({ id: "f-manana", nombre: "Mañana", inicio: "08:00", fin: "14:00", orden: 0 }),
  franja({ id: "f-tarde", nombre: "Tarde", inicio: "14:00", fin: "22:00", orden: 1 }),
];

describe("derivarPanelCoordinacion — agrega las señales de coordinación de la semana", () => {
  it("semana limpia → todas las señales en 0", () => {
    const s = derivarPanelCoordinacion(
      LUNES, [], [], [], FRANJAS, [], [], "yo", true,
    );
    expect(s).toEqual({ sinCubrir: 0, cambiosPendientes: 0, conflictos: 0 });
  });

  it("sinCubrir = huecos reales de la semana (ni cogidos ni cubiertos por turno)", () => {
    // Un evento sin claim ni turno → hueco; otro con turno en su franja → cubierto.
    const s = derivarPanelCoordinacion(
      LUNES,
      [ev({ id: "ev-hueco" }), ev({ id: "ev-cubierto" })],
      [],
      [turno({ franja_id: "f-tarde", fecha: "2026-07-01" })], // cubre la franja Tarde de ambos
      FRANJAS,
      [],
      [],
      "yo",
      true,
    );
    // El turno cubre los DOS (misma franja, mismo día) → 0 huecos.
    expect(s.sinCubrir).toBe(0);
  });

  it("un evento sin nadie de turno en su franja cuenta como hueco", () => {
    const s = derivarPanelCoordinacion(
      LUNES, [ev()], [], [], FRANJAS, [], [], "yo", true,
    );
    expect(s.sinCubrir).toBe(1);
  });

  it("un claim con responsable saca el evento de los huecos (cogido)", () => {
    const s = derivarPanelCoordinacion(
      LUNES, [ev()], [claim()], [], FRANJAS, [], [], "yo", true,
    );
    expect(s.sinCubrir).toBe(0);
  });

  it("eventos de OTRA semana no cuentan", () => {
    const s = derivarPanelCoordinacion(
      LUNES,
      [ev({ id: "ev-otra", fecha: "2026-07-20" })], // fuera de la semana de LUNES
      [],
      [],
      FRANJAS,
      [],
      [],
      "yo",
      true,
    );
    expect(s.sinCubrir).toBe(0);
  });

  it("cambiosPendientes = swaps que esperan mi acción (mismo criterio que el badge)", () => {
    const swaps = [
      swap({ id: "a", estado: "propuesto", destinatario_id: "yo" }), // me toca responder
      swap({ id: "b", estado: "aceptado", destinatario_id: "otro" }), // espera aprobación admin
      swap({ id: "c", estado: "propuesto", destinatario_id: "otro" }), // no es para mí
    ];
    const admin = derivarPanelCoordinacion(LUNES, [], [], [], FRANJAS, [], swaps, "yo", true);
    expect(admin.cambiosPendientes).toBe(2); // propuesto-a-mí + aceptado-a-aprobar

    const editor = derivarPanelCoordinacion(LUNES, [], [], [], FRANJAS, [], swaps, "yo", false);
    expect(editor.cambiosPendientes).toBe(1); // solo el propuesto dirigido a mí
  });

  it("conflictos: cuenta solapes de turno por persona y ausentes con turno de la semana", () => {
    const turnos = [
      // Lunes 29: ana solapada en dos franjas que comparten 14:00 (Mañana 08–14 no solapa con Tarde
      // 14–22). Usamos franjas que sí solapan abajo para el solape.
      turno({ id: "t1", fecha: "2026-06-29", miembro_id: "u1", miembro_nombre: "Luis", franja_id: "f-manana", franja_nombre: "Mañana" }),
      turno({ id: "t2", fecha: "2026-06-29", miembro_id: "u1", miembro_nombre: "Luis", franja_id: "f-solapa", franja_nombre: "Solapa" }),
      // Miércoles 1-jul: ana de turno pero de vacaciones ese día → ausente con turno.
      turno({ id: "t3", fecha: "2026-07-01", miembro_id: "u9", miembro_nombre: "ana", franja_id: "f-tarde", franja_nombre: "Tarde" }),
    ];
    const franjas = [
      ...FRANJAS,
      franja({ id: "f-solapa", nombre: "Solapa", inicio: "12:00", fin: "18:00", orden: 2 }), // solapa con Mañana 08–14
    ];
    const s = derivarPanelCoordinacion(
      LUNES, [], [], turnos, franjas, [ausencia()], [], "yo", true,
    );
    // 1 solape (Luis lun 29) + 1 ausente con turno (ana 1-jul) = 2.
    expect(s.conflictos).toBe(2);
  });

  it("un ausente que NO está de turno no cuenta como conflicto", () => {
    const s = derivarPanelCoordinacion(
      LUNES, [], [], [], FRANJAS, [ausencia()], [], "yo", true,
    );
    expect(s.conflictos).toBe(0);
  });
});
