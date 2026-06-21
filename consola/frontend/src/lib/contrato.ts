/**
 * Validación del contrato `/api/*` en el borde de fetch.
 *
 * Validamos el body ya parseado contra el MISMO JSON Schema que emite el backend
 * (`esquema.gen.json`, generado por `keni_consola.esquema_api` y bundleado por
 * `scripts/gen-types.mjs`). NO hay una segunda fuente de verdad (un Zod paralelo
 * volvería a driftar): el esquema es el contrato declarado en Python.
 *
 * CRÍTICO — propiedades extra PERMITIDAS: el emisor omite `additionalProperties:
 * false` a propósito (el backend puede añadir campos sin romper a clientes; p. ej.
 * `fuente`/`paginacion` se añadieron después). AJV, sin esa palabra clave, las
 * acepta: validamos lo que el frontend CONSUME, no prohibimos extras. Por eso un
 * cambio ADITIVO del backend NUNCA es un falso positivo aquí.
 *
 * Política de fallo (la validación NUNCA debe romper la página en producción):
 *   - DEV (`import.meta.env.DEV`): lanza `ContratoDriftError` para cazarlo pronto.
 *   - PROD: NO fatal. Loguea un aviso estructurado "contract drift" y, si hay
 *     toaster, un toast no bloqueante; DEVUELVE igualmente los datos.
 *
 * Coste: la instancia de AJV y cada validador se construyen UNA vez (memoizados).
 * Para listas grandes/sondeadas, el llamante decide si validar (ver `api.ts`):
 * gateamos a DEV o muestreamos para que no sea un sumidero de CPU en cada poll.
 */
import Ajv2020, { type ValidateFunction } from "ajv/dist/2020.js";

import esquemaContrato from "../esquema.gen.json";
import { avisarDriftContrato } from "./drift";

/** Nombre de un `$def` del esquema (= nombre de la interface generada). */
export type NombreContrato = string;

/** Error de validación: el body no cumple el `$def` esperado (solo se lanza en DEV). */
export class ContratoDriftError extends Error {
  readonly contrato: NombreContrato;
  readonly errores: string[];
  constructor(contrato: NombreContrato, errores: string[]) {
    super(`El contrato «${contrato}» no coincide con la respuesta del backend.`);
    this.name = "ContratoDriftError";
    this.contrato = contrato;
    this.errores = errores;
  }
}

// AJV se construye perezosamente (la primera validación) y se memoiza. `strict:
// false` evita que palabras clave del Draft-2020-12 que no afectan a la validación
// (p. ej. `$comment`, `title`) emitan falsos positivos; mantenemos la validación de datos.
let _ajv: Ajv2020 | null = null;
const _cache = new Map<NombreContrato, ValidateFunction | null>();

function ajv(): Ajv2020 {
  if (_ajv === null) {
    _ajv = new Ajv2020({ strict: false, allErrors: true });
    // Registramos el esquema raíz con un id para resolver los `$ref` internos
    // (`#/$defs/...`) al pedir el validador de cada modelo.
    _ajv.addSchema(esquemaContrato as object, "contrato");
  }
  return _ajv;
}

/** Validador compilado para un `$def`, o `null` si ese modelo no existe en el esquema. */
function validador(contrato: NombreContrato): ValidateFunction | null {
  if (_cache.has(contrato)) return _cache.get(contrato) ?? null;
  let fn: ValidateFunction | null = null;
  try {
    fn = ajv().getSchema(`contrato#/$defs/${contrato}`) ?? null;
  } catch {
    // Esquema corrupto / `$def` inexistente: degradamos a "sin validador".
    fn = null;
  }
  _cache.set(contrato, fn);
  return fn;
}

/** `true` si el esquema bundleado declara un `$def` con ese nombre (validable). */
export function existeContrato(contrato: NombreContrato): boolean {
  return validador(contrato) !== null;
}

/** Resume los errores de AJV en mensajes legibles (acotados para no inundar el log). */
function resumirErrores(fn: ValidateFunction): string[] {
  const errs = fn.errors ?? [];
  return errs
    .slice(0, 10)
    .map((e) => `${e.instancePath || "(raíz)"} ${e.message ?? "inválido"}`.trim());
}

/**
 * Valida `datos` contra el `$def` `contrato`. Si no hay validador (modelo aún no
 * modelado), no hace nada. En mismatch: DEV lanza; PROD avisa (no fatal) y sigue.
 * Devuelve `datos` tal cual (la validación NUNCA transforma el body).
 */
export function validarContrato<T>(contrato: NombreContrato, datos: T): T {
  const fn = validador(contrato);
  if (fn === null) return datos; // sin contrato modelado: nada que validar
  if (fn(datos)) return datos; // cumple

  const errores = resumirErrores(fn);
  if (import.meta.env.DEV) {
    throw new ContratoDriftError(contrato, errores);
  }
  avisarDriftContrato(contrato, errores);
  return datos;
}
