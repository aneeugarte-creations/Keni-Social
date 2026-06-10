// Estilo de objeto REUTILIZABLE: extraer el subconjunto "de estilo" de una capa (sin geometría ni
// contenido) y aplicarlo a otra. Sirve para copiar/pegar estilo (⌘⌥C / ⌘⌥V) y para los estilos
// guardados por marca. NO toca el esquema: solo selecciona campos que ya existen en `documento.ts`.
//
// Reglas de diseño:
// - Común a todas las capas: `opacidad`, `mezcla`.
// - Texto: tipografía y efectos (familia, tamaño, peso, cursiva, subrayado, color, alineación,
//   valign, mayúsculas, interlineado, interletra, contorno, sombra, chip, relleno_degradado, curva).
// - Marco: forma, relleno, borde, radio(s), relleno_degradado, sombra.
// - Imagen: forma, radio(s), ajuste, filtros, sombra. NUNCA copia `objeto`/`crop`/`foco`/`zoom`/
//   `es_foto` (son contenido/encuadre de ESA foto, no estilo transferible).
// - Al aplicar un estilo a una capa de OTRO tipo, solo entran los campos compatibles con el destino
//   (un estilo de texto sobre un marco solo pega lo común: opacidad/mezcla).

import type { Capa, TipoCapa } from "./documento";

// Estilo serializable: un saco de propiedades de estilo de una capa, etiquetado por el tipo de
// capa origen. `campos` son SIEMPRE un subconjunto de `Partial<Capa>` (claves válidas del esquema).
export interface EstiloCapa {
  tipo: TipoCapa;
  campos: Partial<Capa>;
}

// Campos COMUNES (cualquier tipo de capa los entiende).
const COMUNES = ["opacidad", "mezcla"] as const;

// Campos de estilo por tipo de capa (además de los comunes). Mantener alineado con `documento.ts`.
const POR_TIPO: Partial<Record<TipoCapa, readonly string[]>> = {
  texto: [
    "familia", "tamano", "peso", "cursiva", "subrayado", "color", "alineacion", "valign", "mayusculas",
    "interlineado", "interletra", "contorno", "sombra", "chip", "relleno_degradado", "curva",
  ],
  marco: ["forma", "relleno", "borde", "radio", "radios", "relleno_degradado", "sombra"],
  imagen: ["forma", "radio", "radios", "ajuste", "filtros", "sombra"],
};

// Claves de estilo aplicables a una capa de `tipo` (comunes + las propias del tipo).
function clavesDe(tipo: TipoCapa): Set<string> {
  return new Set<string>([...COMUNES, ...(POR_TIPO[tipo] ?? [])]);
}

// Clona profundamente un valor (sombra/chip/degradado/filtros son objetos anidados).
function clonar<T>(v: T): T {
  return typeof structuredClone === "function" ? structuredClone(v) : JSON.parse(JSON.stringify(v));
}

// Extrae el ESTILO de una capa: solo las claves de estilo de su tipo que estén PRESENTES en la
// capa (las ausentes no se incluyen, para no inyectar `undefined`).
export function estiloDe(capa: Capa): EstiloCapa {
  const claves = clavesDe(capa.tipo);
  const campos: Record<string, unknown> = {};
  const fuente = capa as unknown as Record<string, unknown>;
  for (const k of claves) {
    if (k in fuente) campos[k] = clonar(fuente[k]);
  }
  return { tipo: capa.tipo, campos: campos as Partial<Capa> };
}

// Calcula los CAMBIOS de estilo a aplicar a `capa` desde `estilo`, quedándose solo con los campos
// compatibles con el tipo de la capa DESTINO. No muta la capa; devuelve un `Partial<Capa>` listo
// para `actualizar`. Si no hay nada compatible devuelve `{}`.
export function aplicarEstilo(capa: Capa, estilo: EstiloCapa): Partial<Capa> {
  const claves = clavesDe(capa.tipo);
  const cambios: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(estilo.campos)) {
    if (claves.has(k)) cambios[k] = clonar(v);
  }
  return cambios as Partial<Capa>;
}
