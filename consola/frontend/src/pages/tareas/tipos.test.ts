import { describe, expect, it } from "vitest";

import type { Publicacion, EventoRota } from "@/types";

import { agrupar } from "./tipos";

// Factoría compacta de tarea de cobertura (cast por brevedad: agrupar solo lee unos campos).
function t(over: Partial<Publicacion>): Publicacion {
  return {
    id: "x",
    clase: "tarea",
    evento_id: "ev1",
    responsable_id: "",
    responsable_nombre: "",
    titulo: "Cruz Azul vs América",
    formato: "foto",
    fecha_objetivo: "2026-07-01",
    hora_objetivo: "20:00",
    ...over,
  } as unknown as Publicacion;
}

describe("agrupar — coberturas, roles soltados y recuperables", () => {
  it("evento con 2 cubridores de roles distintos = 1 cobertura, sin libres", () => {
    const { coberturas, recuperables } = agrupar(
      [
        t({ id: "a", responsable_id: "u1", responsable_nombre: "luis", formato: "foto" }),
        t({ id: "b", responsable_id: "u2", responsable_nombre: "ana", formato: "video" }),
      ],
      [],
    );
    expect(coberturas).toHaveLength(1);
    expect(coberturas[0].cubridores).toHaveLength(2);
    expect(coberturas[0].libres).toHaveLength(0);
    expect(recuperables).toHaveLength(0);
  });

  it("un rol soltado con otro cubridor vivo viaja como `libres` (resurge dentro de la cobertura)", () => {
    const { coberturas, recuperables } = agrupar(
      [
        t({ id: "a", responsable_id: "u1", responsable_nombre: "luis", formato: "foto" }),
        t({ id: "b", responsable_id: "", formato: "video" }), // soltada
      ],
      [],
    );
    expect(coberturas).toHaveLength(1);
    expect(coberturas[0].cubridores.map((c) => c.id)).toEqual(["a"]);
    expect(coberturas[0].libres.map((c) => c.id)).toEqual(["b"]);
    expect(recuperables).toHaveLength(0);
  });

  it("se va el ÚLTIMO cubridor con 2 roles soltados: resurge UNO por rol (ninguno se pierde)", () => {
    const { coberturas, recuperables } = agrupar(
      [
        t({ id: "a", responsable_id: "", formato: "foto" }),
        t({ id: "b", responsable_id: "", formato: "video" }),
      ],
      [],
    );
    expect(coberturas).toHaveLength(0);
    expect(recuperables.map((r) => r.formato).sort()).toEqual(["foto", "video"]);
  });

  it("varias sueltas del MISMO rol se deduplican a una recuperable", () => {
    const { recuperables } = agrupar(
      [
        t({ id: "a", responsable_id: "", formato: "foto" }),
        t({ id: "b", responsable_id: "", formato: "foto" }),
      ],
      [],
    );
    expect(recuperables).toHaveLength(1);
    expect(recuperables[0].formato).toBe("foto");
  });

  it("un evento sin ninguna tarea sale como eventoLibre (Por cubrir)", () => {
    const ev: EventoRota = {
      id: "ev9",
      titulo: "Partido nuevo",
      fecha: "2026-07-02",
      hora: "18:00",
      tipo_cobertura: "transmision",
    } as unknown as EventoRota;
    const { eventosLibres } = agrupar([], [ev]);
    expect(eventosLibres.map((e) => e.id)).toEqual(["ev9"]);
  });

  it("la cobertura HEREDA la prioridad de su evento (las tareas de cobertura no la llevan)", () => {
    // El evento es «alta»; su tarea de cobertura no lleva prioridad propia relevante: la
    // cobertura debe heredar «alta» del evento (vía el Map por id) para poder ser breaking.
    const ev: EventoRota = {
      id: "ev1",
      titulo: "Cruz Azul vs América",
      fecha: "2026-07-01",
      hora: "20:00",
      tipo_cobertura: "transmision",
      prioridad: "alta",
    } as unknown as EventoRota;
    const { coberturas } = agrupar(
      [t({ id: "a", responsable_id: "u1", responsable_nombre: "luis" })],
      [ev],
    );
    expect(coberturas).toHaveLength(1);
    expect(coberturas[0].prioridad).toBe("alta");
  });

  it("sin evento que la respalde, la cobertura deja la prioridad en undefined (se trata como media)", () => {
    const { coberturas } = agrupar(
      [t({ id: "a", responsable_id: "u1", responsable_nombre: "luis" })],
      [],
    );
    expect(coberturas).toHaveLength(1);
    expect(coberturas[0].prioridad).toBeUndefined();
  });
});
