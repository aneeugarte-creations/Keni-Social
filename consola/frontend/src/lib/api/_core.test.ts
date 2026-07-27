import { describe, expect, it } from "vitest";

import { ApiError, esCaidaDeConexion } from "./_core";

describe("esCaidaDeConexion", () => {
  it("sin respuesta HTTP es una caída", () => {
    expect(esCaidaDeConexion(new ApiError("Sin conexión", 0))).toBe(true);
  });

  it("un 5xx del proxy (sin cuerpo de aplicación) es una caída", () => {
    expect(esCaidaDeConexion(new ApiError("Bad Gateway", 502))).toBe(true);
    expect(esCaidaDeConexion(new ApiError("Service Unavailable", 503, { detalle: 1 }))).toBe(true);
  });

  it("el 503 del front durante un deploy sigue siendo una caída", () => {
    expect(esCaidaDeConexion(new ApiError("Actualizando", 503, { motivo: "deploy" }))).toBe(true);
    expect(esCaidaDeConexion(new ApiError("Avería", 503, { motivo: "incidente" }))).toBe(true);
  });

  it("un 5xx del back CON mensaje propio no es una caída: es la API respondiendo", () => {
    const error = new ApiError("No se pudo traducir", 503, { error: "No se pudo traducir" });
    expect(esCaidaDeConexion(error)).toBe(false);
  });

  it("los errores de negocio (4xx) nunca son una caída", () => {
    expect(esCaidaDeConexion(new ApiError("Estamos traduciendo", 409, { error: "x" }))).toBe(false);
    expect(esCaidaDeConexion(new ApiError("No existe", 404))).toBe(false);
    expect(esCaidaDeConexion(new Error("cualquier cosa"))).toBe(false);
  });
});
