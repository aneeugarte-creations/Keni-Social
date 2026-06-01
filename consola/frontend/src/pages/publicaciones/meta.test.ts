import { describe, expect, it } from "vitest";

import { metaVeredicto } from "./meta";

describe("metaVeredicto (veredicto de publicación = texto libre)", () => {
  it("devuelve null si el veredicto está vacío", () => {
    expect(metaVeredicto("")).toBeNull();
  });

  it("mapea los tres veredictos canónicos del enum histórico", () => {
    expect(metaVeredicto("listo")).toEqual({ nombre: "Listo", variante: "ok" });
    expect(metaVeredicto("revisar")).toEqual({ nombre: "Revisar", variante: "aviso" });
    expect(metaVeredicto("no_publicar")).toEqual({ nombre: "No publicar", variante: "error" });
  });

  it("acepta TEXTO LIBRE del auto-verificador y deriva la variante por prefijo", () => {
    // Estos valores rompían el contrato cuando `veredicto` era un enum cerrado.
    expect(metaVeredicto("ok")).toEqual({ nombre: "ok", variante: "ok" });
    expect(metaVeredicto("ok — confirmar marcador con el equipo")).toEqual({
      nombre: "ok — confirmar marcador con el equipo",
      variante: "ok",
    });
    expect(
      metaVeredicto("marcar claramente como rumor/filtración — no confirmar"),
    ).toEqual({
      nombre: "marcar claramente como rumor/filtración — no confirmar",
      variante: "aviso",
    });
    expect(metaVeredicto("pendiente resultado real del partido")).toEqual({
      nombre: "pendiente resultado real del partido",
      variante: "aviso",
    });
  });

  it("trata 'no publicar' (con espacio o guion bajo) como error", () => {
    expect(metaVeredicto("no publicar")?.variante).toBe("error");
    expect(metaVeredicto("No Publicar: contiene un dato sin confirmar")?.variante).toBe(
      "error",
    );
  });

  it("conserva el texto íntegro como nombre (la UI lo recorta/tooltipea)", () => {
    const largo = "ok — cifras deben verificarse con el área de impacto antes de publicar";
    expect(metaVeredicto(largo)?.nombre).toBe(largo);
  });
});
