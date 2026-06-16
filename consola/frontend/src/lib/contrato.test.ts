// Tests de la validación de contrato en el borde de fetch (#120).
//
// Validamos contra el MISMO esquema que emite el backend (`esquema.gen.json`).
// Cubrimos lo crítico: payload válido pasa, props EXTRA permitidas (cambios
// aditivos del backend NO son falsos positivos), payload malformado se detecta,
// modelo inexistente es no-op, y la política DEV (throw) vs PROD (no fatal).

import { afterEach, describe, expect, it, vi } from "vitest";

import { ContratoDriftError, existeContrato, validarContrato } from "./contrato";

// Mockeamos el aviso de drift (toast + log) para no depender de sonner ni inundar
// la salida; comprobamos que en PROD se llama y NO se lanza.
vi.mock("./drift", () => ({ avisarDriftContrato: vi.fn() }));
import { avisarDriftContrato } from "./drift";

// Modelo simple y estable del esquema para ejercitar la validación de contrato.
const PAGINACION_OK = { total: 1, limite: 10, desplazamiento: 0 };

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("validarContrato (#120)", () => {
  it("acepta una respuesta válida y la devuelve tal cual", () => {
    expect(validarContrato("Paginacion", PAGINACION_OK)).toBe(PAGINACION_OK);
  });

  it("PERMITE propiedades extra (cambio aditivo del backend, no falso positivo)", () => {
    const conExtra = { ...PAGINACION_OK, campo_nuevo_del_backend: 123 };
    expect(validarContrato("Paginacion", conExtra)).toBe(conExtra);
  });

  it("no valida si el modelo no existe en el esquema (no-op)", () => {
    expect(existeContrato("ModeloQueNoExiste")).toBe(false);
    const datos = { lo_que_sea: true };
    expect(validarContrato("ModeloQueNoExiste", datos)).toBe(datos);
  });

  it("detecta una respuesta malformada: en DEV lanza ContratoDriftError", () => {
    // Vitest corre en modo test => import.meta.env.DEV es true.
    const mala = { total: 1 }; // faltan limite/desplazamiento (requeridos en Paginacion)
    expect(() => validarContrato("Paginacion", mala)).toThrow(ContratoDriftError);
  });

  it("en PROD NO es fatal: avisa de drift y devuelve los datos", () => {
    vi.stubEnv("DEV", false);
    const mala = { publicaciones: "no-es-una-lista" };
    const out = validarContrato("RespuestaPublicaciones", mala);
    expect(out).toBe(mala);
    expect(avisarDriftContrato).toHaveBeenCalledTimes(1);
  });
});
