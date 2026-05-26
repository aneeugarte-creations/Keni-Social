// Guard del artefacto generado `types.gen.ts` (#101 / H5/E6), lado frontend.
//
// `types.gen.ts` se DERIVA del backend (`npm run gen:types`); `types.ts` lo
// re-exporta. Este test no necesita Python: verifica que el artefacto está
// presente, no se ha vaciado/editado a mano (cabecera "GENERADO"), y que `types.ts`
// re-exporta exactamente las interfaces que `types.gen.ts` declara. Si alguien
// borra el archivo, añade una interface al esquema sin re-exportarla, o lo edita a
// mano, este test falla. El guard CRUZADO contra el backend (drift de campos) vive
// en `consola/tests/test_esquema_api.py` (lane de Python).

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const AQUI = dirname(fileURLToPath(import.meta.url));
const GEN = resolve(AQUI, "./types.gen.ts");
const TYPES = resolve(AQUI, "./types.ts");

function interfacesDe(texto: string): string[] {
  return [...texto.matchAll(/export interface ([A-Za-z0-9_]+)/g)].map((m) => m[1]);
}

describe("types.gen.ts (tipos derivados del backend, #101)", () => {
  const gen = readFileSync(GEN, "utf8");
  const types = readFileSync(TYPES, "utf8");

  it("está presente y marcado como GENERADO — NO EDITAR", () => {
    expect(gen.length).toBeGreaterThan(0);
    expect(gen).toContain("GENERADO");
  });

  it("declara al menos las interfaces nucleares del subconjunto estable", () => {
    const nombres = interfacesDe(gen);
    for (const esperado of [
      "RespuestaEstado",
      "RespuestaConfig",
      "RespuestaLimites",
      "ReporteMetricas",
      "CompararMetricas",
      "ErrorApi",
    ]) {
      expect(nombres).toContain(esperado);
    }
  });

  it("toda interface generada se re-exporta desde types.ts", () => {
    const generadas = interfacesDe(gen);
    // Bloque `export type { ... } from "./types.gen";` de types.ts.
    const bloque = types.match(/export type \{([\s\S]*?)\} from "\.\/types\.gen";/);
    expect(bloque, "falta el re-export de ./types.gen en types.ts").not.toBeNull();
    const reexportadas = new Set(
      bloque![1]
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    );
    for (const nombre of generadas) {
      expect(reexportadas.has(nombre), `types.ts no re-exporta ${nombre}`).toBe(true);
    }
  });
});
