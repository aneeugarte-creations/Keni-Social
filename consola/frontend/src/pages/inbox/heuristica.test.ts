import { describe, expect, it } from "vitest";

import type { ParticipanteInbox } from "@/types";

import { avatarAudiencia, esMensajeEntrante, nombreAudiencia } from "./heuristica";

const PARTICIPANTES: ParticipanteInbox[] = [
  { id: "aud-1", nombre: "Ana Audiencia", avatar: "https://cdn/ana.jpg" },
];

describe("esMensajeEntrante", () => {
  it("es ENTRANTE cuando el autor coincide con un participante (audiencia)", () => {
    expect(esMensajeEntrante({ autor_id: "aud-1" }, PARTICIPANTES)).toBe(true);
  });

  it("es SALIENTE cuando el autor no es participante (el propio negocio)", () => {
    expect(esMensajeEntrante({ autor_id: "pagina-9" }, PARTICIPANTES)).toBe(false);
  });

  it("es SALIENTE cuando no hay autor (sin autor_id)", () => {
    expect(esMensajeEntrante({ autor_id: null }, PARTICIPANTES)).toBe(false);
  });

  it("no casa un participante sin id contra un autor nulo", () => {
    const sinId: ParticipanteInbox[] = [{ id: null, nombre: "x", avatar: null }];
    expect(esMensajeEntrante({ autor_id: null }, sinId)).toBe(false);
  });
});

describe("nombreAudiencia / avatarAudiencia", () => {
  it("toma el primer participante con nombre y con avatar", () => {
    expect(nombreAudiencia({ participantes: PARTICIPANTES })).toBe("Ana Audiencia");
    expect(avatarAudiencia({ participantes: PARTICIPANTES })).toBe("https://cdn/ana.jpg");
  });

  it("degrada cuando no hay nombre ni avatar", () => {
    const vacios: ParticipanteInbox[] = [{ id: "x", nombre: null, avatar: null }];
    expect(nombreAudiencia({ participantes: vacios })).toBe("Sin nombre");
    expect(avatarAudiencia({ participantes: vacios })).toBeNull();
  });
});
