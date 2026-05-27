// Generador de tipos del frontend desde el esquema del backend (#101 / H5/E6).
//
// Flujo: invoca el export de JSON Schema del backend
//   (`python -m keni_consola.esquema_api`) y, con `json-schema-to-typescript`,
//   emite `src/types.gen.ts` con una `interface` por modelo del subconjunto
//   estable del contrato `/api/*`. Asi esos tipos se DERIVAN del backend en vez
//   de mantenerse a mano (ver `README.md` › "Tipos derivados del backend").
//
// El resto de `types.ts` sigue a mano (las ~50 rutas construyen dicts ad-hoc, no
// modelos; generar todo seria fragil). `types.ts` re-exporta lo de `types.gen.ts`.
//
// Uso:
//   node scripts/gen-types.mjs            -> escribe src/types.gen.ts
//   node scripts/gen-types.mjs --check    -> NO escribe; sale 1 si difiere (guard)
//
// Python: por defecto usa `python3`. Override con KENI_PYTHON (p. ej. el del venv
// donde esta instalado `keni-consola`). El backend debe ser importable.

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";

const AQUI = dirname(fileURLToPath(import.meta.url));
const SALIDA = resolve(AQUI, "../src/types.gen.ts");
// Artefacto JSON Schema BUNDLEADO para la validacion en runtime (#120): el mismo
// esquema que emite el backend, sin segunda fuente de verdad (un Zod paralelo
// volveria a driftar). `lib/api.ts` lo carga y valida el body contra su `$def`.
const SALIDA_ESQUEMA = resolve(AQUI, "../src/esquema.gen.json");
const PYTHON = process.env.KENI_PYTHON || "python3";
const MODULO = "keni_consola.esquema_api";

const CABECERA = `/**
 * GENERADO — NO EDITAR A MANO.
 *
 * Tipos DERIVADOS del backend (subconjunto estable del contrato \`/api/*\`).
 * Fuente: \`keni_consola.esquema_api\` (Python). Regenerar con \`npm run gen:types\`.
 * El guard \`npm run gen:types:check\` (y el test del backend) falla si esto se
 * desincroniza del backend. El resto de tipos vive a mano en \`types.ts\`. Ver #101.
 */
`;

/** Pide al backend el JSON Schema del subconjunto estable (texto crudo). */
function obtenerEsquemaTexto() {
  try {
    return execFileSync(PYTHON, ["-m", MODULO], {
      encoding: "utf8",
      maxBuffer: 32 * 1024 * 1024,
    });
  } catch (err) {
    const detalle = err.stderr ? `\n${err.stderr}` : "";
    throw new Error(
      `No se pudo ejecutar \`${PYTHON} -m ${MODULO}\`. ¿Está instalado el ` +
        `paquete keni-consola en ese Python? (usa KENI_PYTHON para apuntar al ` +
        `venv correcto).${detalle}`,
    );
  }
}

/**
 * Serializa el esquema de forma DETERMINISTA para escribirlo/compararlo (mismo
 * formato que el emisor del backend: `indent=2`, sin reordenar claves).
 */
function esquemaSerializado(esquema) {
  return JSON.stringify(esquema, null, 2) + "\n";
}

/**
 * Compila el esquema a TypeScript. `json-schema-to-typescript` recorre los
 * `$defs` referenciados desde la raíz (`anyOf`) y emite una `interface` por cada
 * uno, conservando el nombre (`title`). Descartamos el tipo raíz anónimo: solo
 * nos interesan las interfaces nombradas.
 */
async function generarTs(esquema) {
  const cuerpo = await compile(esquema, esquema.title || "ContratoApiKeni", {
    bannerComment: "",
    additionalProperties: false,
    declareExternallyReferenced: true,
    enableConstEnums: false,
    unknownAny: false,
    // Salida determinista y legible.
    style: { singleQuote: false, semi: true },
  });

  // Quita la declaración del tipo raíz (union anónima `ContratoApiKeni`): no
  // aporta nada al frontend y mete ruido. Conserva todas las interfaces.
  const sinRaiz = cuerpo
    .replace(
      /export type ContratoApiKeni =[\s\S]*?;\n/,
      "",
    )
    .trimStart();

  return CABECERA + "\n" + sinRaiz.trimEnd() + "\n";
}

/** Lee un artefacto si existe; cadena vacía si falta (ausente => divergencia). */
function leerSiExiste(ruta) {
  try {
    return readFileSync(ruta, "utf8");
  } catch {
    return "";
  }
}

async function main() {
  const modoCheck = process.argv.includes("--check");
  const esquema = JSON.parse(obtenerEsquemaTexto());
  const ts = await generarTs(esquema);
  const json = esquemaSerializado(esquema);

  if (modoCheck) {
    const tsActual = leerSiExiste(SALIDA);
    const jsonActual = leerSiExiste(SALIDA_ESQUEMA);
    const tsOk = tsActual === ts;
    const jsonOk = jsonActual === json;
    if (!tsOk || !jsonOk) {
      const cuales = [!tsOk && "types.gen.ts", !jsonOk && "esquema.gen.json"]
        .filter(Boolean)
        .join(" y ");
      console.error(
        `✗ ${cuales} está(n) desincronizado(s) del backend.\n` +
          "  Regenéralo con:  npm run gen:types\n" +
          "  (los tipos y el esquema del subconjunto estable se DERIVAN del backend, no se editan a mano).",
      );
      process.exit(1);
    }
    console.log("✓ types.gen.ts y esquema.gen.json coinciden con el esquema del backend.");
    return;
  }

  writeFileSync(SALIDA, ts, "utf8");
  writeFileSync(SALIDA_ESQUEMA, json, "utf8");
  console.log(`✓ Generado ${SALIDA} y ${SALIDA_ESQUEMA} desde ${MODULO}.`);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
