import { describe, expect, it } from "vitest";

import type { TurnoRota } from "@/types";

import { construirCuerpoEdicion, type EdicionTurno } from "./dialogs";

// El turno arranca en una franja A MEDIDA («Nocturna», id `f-noche`), el caso que el viejo
// desplegable legacy (matutino/vespertino/descanso) corrompía al editar.
function turno(over: Partial<TurnoRota> = {}): TurnoRota {
  return {
    id: "t1",
    semana: "2026-06-15",
    fecha: "2026-06-16",
    miembro_id: "u-luis",
    miembro_nombre: "Luis",
    franja_id: "f-noche",
    franja_nombre: "Nocturna",
    franja: "Nocturna",
    inicio: "17:00",
    fin: "01:00",
    horario_propio: false,
    estado: "aprobado",
    override: false,
    motivo: "",
    nota_relevo: "",
    es_sabado: false,
    marca: "claro-sports",
    marca_nombre: "Claro Sports",
    ...over,
  };
}

function edicionDe(t: TurnoRota, over: Partial<EdicionTurno> = {}): EdicionTurno {
  return {
    fecha: t.fecha,
    miembroId: t.miembro_id,
    franjaId: t.franja_id,
    inicio: t.inicio,
    fin: t.fin,
    motivo: t.motivo,
    notaRelevo: t.nota_relevo,
    ...over,
  };
}

describe("construirCuerpoEdicion — PATCH de turno solo con lo que cambió", () => {
  it("sin cambios → cuerpo vacío", () => {
    const t = turno();
    expect(construirCuerpoEdicion(t, edicionDe(t), false)).toEqual({});
  });

  it("cambiar la franja viaja como `franja_id` (no como literal `franja` legacy)", () => {
    const t = turno(); // estaba en la franja a medida «Nocturna»
    const cuerpo = construirCuerpoEdicion(t, edicionDe(t, { franjaId: "f-manana" }), false);
    expect(cuerpo).toEqual({ franja_id: "f-manana" });
    // El campo legacy `franja` (que el backend mapea por NOMBRE y saca al turno de su franja
    // a medida) NO debe colarse: ése era el bug de corrupción.
    expect("franja" in cuerpo).toBe(false);
  });

  it("solo manda los campos tocados; `override` añade override:true", () => {
    const t = turno();
    const cuerpo = construirCuerpoEdicion(t, edicionDe(t, { motivo: "cobertura crítica" }), true);
    expect(cuerpo).toEqual({ motivo: "cobertura crítica", override: true });
  });
});
