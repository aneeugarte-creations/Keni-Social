import { describe, expect, it } from "vitest";

import { metaRevision, piezaFueraDeVentana } from "./meta";

describe("metaRevision (revision de publicación = texto libre)", () => {
  it("devuelve null si el revision está vacío", () => {
    expect(metaRevision("")).toBeNull();
  });

  it("mapea los tres revisiones canónicos del enum histórico", () => {
    expect(metaRevision("listo")).toEqual({ nombre: "Listo", variante: "ok" });
    expect(metaRevision("revisar")).toEqual({ nombre: "Revisar", variante: "aviso" });
    expect(metaRevision("no_publicar")).toEqual({ nombre: "No publicar", variante: "error" });
  });

  it("acepta TEXTO LIBRE del auto-verificador y deriva la variante por prefijo", () => {
    // Estos valores rompían el contrato cuando `revision` era un enum cerrado.
    expect(metaRevision("ok")).toEqual({ nombre: "ok", variante: "ok" });
    expect(metaRevision("ok — confirmar marcador con el equipo")).toEqual({
      nombre: "ok — confirmar marcador con el equipo",
      variante: "ok",
    });
    expect(
      metaRevision("marcar claramente como rumor/filtración — no confirmar"),
    ).toEqual({
      nombre: "marcar claramente como rumor/filtración — no confirmar",
      variante: "aviso",
    });
    expect(metaRevision("pendiente resultado real del partido")).toEqual({
      nombre: "pendiente resultado real del partido",
      variante: "aviso",
    });
  });

  it("trata 'no publicar' (con espacio o guion bajo) como error", () => {
    expect(metaRevision("no publicar")?.variante).toBe("error");
    expect(metaRevision("No Publicar: contiene un dato sin confirmar")?.variante).toBe(
      "error",
    );
  });

  it("conserva el texto íntegro como nombre (la UI lo recorta/tooltipea)", () => {
    const largo = "ok — cifras deben verificarse con el área de impacto antes de publicar";
    expect(metaRevision(largo)?.nombre).toBe(largo);
  });
});

describe("piezaFueraDeVentana (ventana de frescura del programador, 2 h)", () => {
  const ahora = new Date("2026-05-27T12:00:00Z");
  const base = { estado: "programado", fecha_programada: "2026-05-27T08:00", preparado_en: "" };

  it("una programada vencida hace >2 h y sin preparar está fuera de ventana", () => {
    expect(piezaFueraDeVentana(base, ahora)).toBe(true);
  });

  it("vencida hace <2 h (el barrido aún la publica solo) NO está fuera de ventana", () => {
    expect(
      piezaFueraDeVentana({ ...base, fecha_programada: "2026-05-27T11:00" }, ahora),
    ).toBe(false);
  });

  it("preparada, en otro estado o sin fecha: nunca fuera de ventana", () => {
    expect(piezaFueraDeVentana({ ...base, preparado_en: "2026-05-27T08:01" }, ahora)).toBe(false);
    expect(piezaFueraDeVentana({ ...base, estado: "publicado" }, ahora)).toBe(false);
    expect(piezaFueraDeVentana({ ...base, fecha_programada: "" }, ahora)).toBe(false);
  });
});
