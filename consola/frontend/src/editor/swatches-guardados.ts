// Swatches (muestras de color) GUARDADAS por la persona, por marca, en localStorage. A diferencia
// de las otras fuentes del ColorControl (marca, documento, recientes, predeterminados), estas son
// una paleta ELEGIDA a mano que persiste entre sesiones. Mismo patrón que `estilos-guardados.ts`.

const clave = (marca: string) => `keni:swatches:${marca || "_"}`;

// Normaliza a #RRGGBB / #RRGGBBAA en mayúsculas; devuelve null si no es un hex válido.
function normalizar(color: string): string | null {
  const c = color.trim().toUpperCase();
  return /^#([0-9A-F]{6}|[0-9A-F]{8})$/.test(c) ? c : null;
}

// Lee las swatches guardadas de una marca (tolerante a JSON corrupto/ausente).
export function cargarSwatches(marca: string): string[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(clave(marca));
    if (!raw) return [];
    const v = JSON.parse(raw);
    return Array.isArray(v) ? (v as unknown[]).filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function escribir(marca: string, lista: string[]): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(clave(marca), JSON.stringify(lista));
  } catch {
    // Cuota llena / modo privado: el guardado es best-effort, no rompe la edición.
  }
}

// Guarda un color al frente de la lista (sin duplicados); devuelve la lista actualizada. Ignora
// colores no válidos devolviendo la lista intacta.
export function guardarSwatch(marca: string, color: string): string[] {
  const c = normalizar(color);
  if (!c) return cargarSwatches(marca);
  const next = [c, ...cargarSwatches(marca).filter((x) => x !== c)];
  escribir(marca, next);
  return next;
}

// Elimina un color guardado; devuelve la lista actualizada.
export function quitarSwatch(marca: string, color: string): string[] {
  const c = color.toUpperCase();
  const next = cargarSwatches(marca).filter((x) => x !== c);
  escribir(marca, next);
  return next;
}
