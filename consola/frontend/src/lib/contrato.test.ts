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

const RUNS_OK = {
  runs: [
    {
      id: "r1",
      prompt: "hola",
      modo: "headless",
      estado: "completado",
      motivo: "",
      fecha_inicio: "2026-05-26T10:00:00",
      metricas: null,
    },
  ],
  paginacion: { total: 1, limite: 1, desplazamiento: 0 },
};

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("validarContrato (#120)", () => {
  it("acepta una respuesta válida y la devuelve tal cual", () => {
    expect(validarContrato("RespuestaRuns", RUNS_OK)).toBe(RUNS_OK);
  });

  it("PERMITE propiedades extra (cambio aditivo del backend, no falso positivo)", () => {
    const conExtra = { ...RUNS_OK, campo_nuevo_del_backend: 123 };
    expect(validarContrato("RespuestaRuns", conExtra)).toBe(conExtra);
  });

  it("no valida si el modelo no existe en el esquema (no-op)", () => {
    expect(existeContrato("ModeloQueNoExiste")).toBe(false);
    const datos = { lo_que_sea: true };
    expect(validarContrato("ModeloQueNoExiste", datos)).toBe(datos);
  });

  it("detecta una respuesta malformada: en DEV lanza ContratoDriftError", () => {
    // Vitest corre en modo test => import.meta.env.DEV es true.
    const mala = { runs: [{ id: "r1" }] }; // faltan prompt/modo/estado/... y paginacion
    expect(() => validarContrato("RespuestaRuns", mala)).toThrow(ContratoDriftError);
  });

  it("en PROD NO es fatal: avisa de drift y devuelve los datos", () => {
    vi.stubEnv("DEV", false);
    const mala = { publicaciones: "no-es-una-lista" };
    const out = validarContrato("RespuestaPublicaciones", mala);
    expect(out).toBe(mala);
    expect(avisarDriftContrato).toHaveBeenCalledTimes(1);
  });

  it("valida el contrato comercial con fuente/es_muestra (#124)", () => {
    const ok = {
      publicaciones: [],
      fuente: "muestra",
      es_muestra: true,
    };
    expect(validarContrato("RespuestaPublicacionesComercial", ok)).toBe(ok);
    // Falta `fuente`/`es_muestra` => drift en DEV.
    expect(() =>
      validarContrato("RespuestaPublicacionesComercial", { publicaciones: [] }),
    ).toThrow(ContratoDriftError);
  });
});
