import { describe, expect, it } from "vitest";

import type { EventoRota, FranjaSemana, Publicacion, TurnoRota } from "@/types";

import { datetimeLocalAIso } from "@/lib/fecha";
import { derivarCoberturaEvento, resumenCobertura } from "./cobertura";

// --- Factorías compactas (cast por brevedad: las funciones solo leen unos campos) -----------

/** Un evento de la rota. Por defecto: 2026-07-01 20:00 (CDMX), transmisión. */
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

/** Una tarea de cobertura (claim): clase=tarea con `evento_id` y, si lleva responsable, cubridor. */
function claim(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "c1",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "u1",
    responsable_nombre: "luis",
    titulo: "Cruz Azul vs América",
    formato: "foto",
    fecha_objetivo: "2026-07-01",
    hora_objetivo: "20:00",
    ...over,
  } as unknown as Publicacion;
}

/** Una franja viva de la semana. */
function franja(over: Partial<FranjaSemana> = {}): FranjaSemana {
  return {
    id: "f-tarde",
    lunes: "2026-06-29",
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

/** Un turno (persona × día × franja). */
function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: "2026-06-29",
    fecha: "2026-07-01",
    miembro_id: "u9",
    miembro_nombre: "ana",
    franja_id: "f-tarde",
    franja_nombre: "Tarde",
    ...over,
  } as unknown as TurnoRota;
}

// Franjas estándar de la semana del evento de prueba: una laboral (cubre 20:00) + descanso.
const FRANJAS: FranjaSemana[] = [
  franja({ id: "f-manana", nombre: "Mañana", inicio: "08:00", fin: "14:00", orden: 0 }),
  franja({ id: "f-tarde", nombre: "Tarde", inicio: "14:00", fin: "22:00", orden: 1 }),
  franja({ id: "f-descanso", nombre: "Descanso", inicio: "00:00", fin: "00:00", orden: 999, es_descanso: true }),
];

/** «Ahora» = `min` minutos ANTES del saque del evento (CDMX wall time → instante real). */
function ahoraAntesDelSaque(evento: EventoRota, min: number): Date {
  const saque = new Date(datetimeLocalAIso(`${evento.fecha}T${evento.hora}`)!);
  return new Date(saque.getTime() - min * 60000);
}

describe("derivarCoberturaEvento — estado y precedencia", () => {
  it("sin claims ni turnos → sin-cubrir", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.cubridores).toHaveLength(0);
    expect(d.porTurno).toHaveLength(0);
  });

  it("un turno en la franja de la hora del evento ese día → cubierto-turno", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [turno()], FRANJAS);
    expect(d.estado).toBe("cubierto-turno");
    expect(d.porTurno).toHaveLength(1);
    expect(d.porTurno[0].miembroNombre).toBe("ana");
    expect(d.porTurno[0].franjaId).toBe("f-tarde");
  });

  it("un turno en OTRA franja (no la de la hora) NO cubre → sin-cubrir", () => {
    const e = ev(); // 20:00 cae en la franja Tarde, no en Mañana
    const d = derivarCoberturaEvento(e, [], [turno({ franja_id: "f-manana" })], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.porTurno).toHaveLength(0);
  });

  it("un turno en OTRO día NO cubre → sin-cubrir", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [turno({ fecha: "2026-07-02" })], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.porTurno).toHaveLength(0);
  });

  it("un claim con responsable → cogido (la titularidad anula el turno)", () => {
    const e = ev();
    // Hay turno Y claim: el claim manda (precedencia cogido > cubierto-turno).
    const d = derivarCoberturaEvento(e, [claim()], [turno()], FRANJAS);
    expect(d.estado).toBe("cogido");
    expect(d.cubridores.map((c) => c.id)).toEqual(["c1"]);
    // El turno sigue informándose, pero no decide el estado.
    expect(d.porTurno).toHaveLength(1);
  });

  it("varios cubridores de roles distintos = un cogido con todos los cubridores", () => {
    const e = ev();
    const d = derivarCoberturaEvento(
      e,
      [
        claim({ id: "c1", responsable_id: "u1", responsable_nombre: "luis", formato: "foto" }),
        claim({ id: "c2", responsable_id: "u2", responsable_nombre: "ana", formato: "video" }),
      ],
      [],
      FRANJAS,
    );
    expect(d.estado).toBe("cogido");
    expect(d.cubridores).toHaveLength(2);
    expect(d.cobertura?.libres).toHaveLength(0);
  });

  it("un claim soltado (sin responsable) NO cuenta como cubridor → sin-cubrir si no hay turno", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [claim({ responsable_id: "" })], [], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.cubridores).toHaveLength(0);
  });

  it("claims de OTRO evento se ignoran", () => {
    const e = ev({ id: "ev1" });
    const d = derivarCoberturaEvento(e, [claim({ evento_id: "ev2" })], [], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.cubridores).toHaveLength(0);
  });

  it("un evento sin fecha nunca lo cubre un turno → sin-cubrir", () => {
    const e = ev({ fecha: "" });
    const d = derivarCoberturaEvento(e, [], [turno()], FRANJAS);
    expect(d.estado).toBe("sin-cubrir");
    expect(d.porTurno).toHaveLength(0);
  });
});

describe("derivarCoberturaEvento — roles faltantes", () => {
  it("sin cubridores faltan los 4 roles", () => {
    const d = derivarCoberturaEvento(ev(), [], [], FRANJAS);
    expect(d.rolesFaltantes).toEqual(["foto", "video", "texto", "live"]);
  });

  it("con foto y video cubiertos faltan texto y live", () => {
    const d = derivarCoberturaEvento(
      ev(),
      [
        claim({ id: "c1", formato: "foto" }),
        claim({ id: "c2", formato: "video" }),
      ],
      [],
      FRANJAS,
    );
    expect(d.rolesFaltantes).toEqual(["texto", "live"]);
  });

  it("`formato` vacío cuenta como foto (su defecto en BD)", () => {
    const d = derivarCoberturaEvento(ev(), [claim({ formato: "" })], [], FRANJAS);
    expect(d.rolesFaltantes).toEqual(["video", "texto", "live"]);
  });
});

describe("derivarCoberturaEvento — semáforo temporal", () => {
  it("falta mucho (> umbral) → programado", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS, ahoraAntesDelSaque(e, 300));
    expect(d.semaforo).toBe("programado");
    expect(d.minutosParaInicio).toBe(300);
  });

  it("saque a ≤ 120 min y aún no empieza → empieza-en", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS, ahoraAntesDelSaque(e, 90));
    expect(d.semaforo).toBe("empieza-en");
    expect(d.minutosParaInicio).toBe(90);
  });

  it("justo en el umbral (120 min) → empieza-en", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS, ahoraAntesDelSaque(e, 120));
    expect(d.semaforo).toBe("empieza-en");
  });

  it("transcurriendo (dentro de la ventana de 180 min) → en-vivo", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS, ahoraAntesDelSaque(e, -30));
    expect(d.semaforo).toBe("en-vivo");
  });

  it("pasada la ventana (> 180 min después del saque) → terminado", () => {
    const e = ev();
    const d = derivarCoberturaEvento(e, [], [], FRANJAS, ahoraAntesDelSaque(e, -200));
    expect(d.semaforo).toBe("terminado");
  });
});

describe("resumenCobertura — KPI de cabecera", () => {
  it("cuenta cubiertos (cogido + turno), huecos, pronto y en vivo", () => {
    // Ahora = 90 min antes de las 20:00 del 1-jul → los eventos de las 20:00 están en «empieza-en».
    const ancla = ev({ id: "base" });
    const ahora = ahoraAntesDelSaque(ancla, 90);

    const eCogido = ev({ id: "e-cogido" }); // 1-jul 20:00, con claim → cogido + pronto
    const eTurno = ev({ id: "e-turno" }); // 1-jul 20:00, turno cubre f-tarde ese día → cubierto + pronto
    const eHueco = ev({ id: "e-hueco", fecha: "2026-07-03" }); // otro día, sin turno → hueco + programado
    const eVivo = ev({ id: "e-vivo", hora: "18:00" }); // 1-jul 18:00, ya arrancó a las 18:30 (franja Tarde) → en vivo + cubierto-turno

    const claims = [claim({ id: "cc", evento_id: "e-cogido" })];
    const turnos = [turno({ id: "tt", franja_id: "f-tarde", fecha: "2026-07-01" })];

    const r = resumenCobertura([eCogido, eTurno, eHueco, eVivo], claims, turnos, FRANJAS, ahora);
    expect(r.total).toBe(4);
    // e-cogido (claim) + e-turno (turno, 20:00) + e-vivo (turno, 18:00 franja Tarde) = 3 cubiertos.
    expect(r.cubiertos).toBe(3);
    // e-hueco es de otro día (3-jul): el turno del 1-jul no lo toca → hueco real.
    expect(r.sinCubrir).toBe(1);
    // e-cogido/e-turno son de las 20:00 del 1-jul (a 90 min del saque → pronto); e-hueco es del 3-jul
    // (a ~2 días → programado). e-vivo (18:00 del 1-jul) ya arrancó a las 18:30 → en vivo.
    expect(r.pronto).toBe(2);
    expect(r.enVivo).toBe(1);
  });

  it("evento sin cubrir cuenta como hueco", () => {
    const r = resumenCobertura([ev()], [], [], FRANJAS);
    expect(r.total).toBe(1);
    expect(r.cubiertos).toBe(0);
    expect(r.sinCubrir).toBe(1);
  });
});
