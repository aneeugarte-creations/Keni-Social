/**
 * Lógica PURA del organigrama (sin React): paleta por marca, agrupación por zona y
 * construcción del árbol de reporte a partir de `UsuarioAdmin[]`.
 *
 * Dos ejes ORTOGONALES (regla dictada por la dirección: "estar debajo de alguien ≠
 * reportarle"):
 *   - `manager_id` define el ÁRBOL de reporte (quién reporta a quién). Es lo editable.
 *   - `marcas` define la VERTICAL de trabajo. De aquí salen las "zonas" de color del
 *     organigrama (las áreas por marca que pidió el cliente).
 *
 * La ZONA de una persona se deriva de su CABEZA DE ÁREA (el ancestro que reporta directo
 * a la raíz). Así, mover a alguien de superior recoloca su zona automáticamente, y el
 * organigrama "se redibuja solo" cuando el admin edita la jerarquía.
 */

import { COLOR_MARCA } from "@/lib/marca-colores";
import type { CargoUsuario, UsuarioAdmin } from "@/types";

/** Zonas que NO son una marca: la dirección (raíz) y lo transversal (cruza verticales). */
export const ZONA_DIRECCION = "__direccion__";
export const ZONA_TRANSVERSAL = "__transversal__";

/** Orden de presentación de las marcas como zonas (prioridad para elegir la zona de una
 *  cabeza con varias marcas). Coincide con `keni_shared.marcas` (cliente por defecto). */
export const ORDEN_MARCAS = [
  "claro-sports",
  "unotv",
  "piso-15",
  "nacion-gamer",
  "fundacion",
] as const;

export interface MetaZona {
  /** Etiqueta humana de la zona (cabecera del área). */
  etiqueta: string;
  /** Color de acento de la marca/zona (hex). De aquí salen bordes, chips y tintes. */
  color: string;
  /** Inicial/abreviatura corta para avatares de fallback. */
  corta: string;
}

/**
 * Paleta por zona. Las zonas de marca beben de la paleta canónica de marca
 * (`lib/marca-colores.ts`); las internas (transversal/dirección) tienen su gris propio.
 * Colores fijos (no dependen del tema): se usan como acento sobre tarjetas temadas.
 */
export const META_ZONA: Record<string, MetaZona> = {
  "claro-sports": { etiqueta: "Claro Sports", color: COLOR_MARCA["claro-sports"], corta: "CS" },
  unotv: { etiqueta: "UnoTV", color: COLOR_MARCA.unotv, corta: "U" },
  "piso-15": { etiqueta: "Piso 15", color: COLOR_MARCA["piso-15"], corta: "P15" },
  "nacion-gamer": { etiqueta: "Nación Gamer", color: COLOR_MARCA["nacion-gamer"], corta: "NG" },
  fundacion: { etiqueta: "Fundación", color: COLOR_MARCA.fundacion, corta: "F" },
  [ZONA_TRANSVERSAL]: { etiqueta: "Transversal", color: "#64748b", corta: "T" },
  [ZONA_DIRECCION]: { etiqueta: "Dirección", color: "#0f172a", corta: "D" },
};

/** Devuelve la metadata de una zona (cae a "transversal" si la marca no está en la paleta). */
export function metaZona(zonaId: string): MetaZona {
  return META_ZONA[zonaId] ?? META_ZONA[ZONA_TRANSVERSAL];
}

/**
 * Cargos que, en una CABEZA de área (reporta directo a la raíz), la colocan en la zona
 * TRANSVERSAL en lugar de en una marca: coordinaciones que cruzan verticales (YouTube,
 * operativa), fotografía/verificación y roles de staff. El director es la raíz (zona Dirección), no
 * una cabeza de área, así que su presencia aquí es solo defensiva.
 */
const CARGOS_TRANSVERSALES = new Set<CargoUsuario>([
  "director",
  "coordinador_youtube",
  "coordinador_operativo",
  "coordinador_invitados",
  "fotografia_revision",
  "editor_video",
  "disenador",
  "estrategia",
]);

/** `rgba(color, alpha)` a partir de un hex `#rrggbb` (para tintes de zona/tarjeta). */
export function hexAlpha(hex: string, alpha: number): string {
  const limpio = hex.replace("#", "");
  const r = parseInt(limpio.slice(0, 2), 16);
  const g = parseInt(limpio.slice(2, 4), 16);
  const b = parseInt(limpio.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

/** Iniciales (1-2) a partir del nombre visible, para el avatar de fallback. */
export function iniciales(texto: string): string {
  const partes = texto.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

/** Nombre a mostrar: el `nombre` humano si existe, si no el `usuario` (login). */
export function nombreVisible(u: UsuarioAdmin): string {
  return (u.nombre ?? "").trim() || u.usuario;
}

// --- Árbol de reporte -------------------------------------------------------

export type IndiceUsuarios = Map<string, UsuarioAdmin>;

export function indexarPorId(usuarios: UsuarioAdmin[]): IndiceUsuarios {
  return new Map(usuarios.map((u) => [u.id, u]));
}

/**
 * Una persona es RAÍZ del organigrama si no tiene superior (`manager_id` vacío) o si su
 * superior ya no existe (id colgado tras un borrado): en ambos casos cuelga de la cima.
 */
export function esRaiz(u: UsuarioAdmin, porId: IndiceUsuarios): boolean {
  const mgr = u.manager_id ?? "";
  return !mgr || !porId.has(mgr);
}

/** Mapa `manager_id -> hijos`, cada lista ordenada por nombre visible. */
export function hijosPorManager(usuarios: UsuarioAdmin[]): Map<string, UsuarioAdmin[]> {
  const mapa = new Map<string, UsuarioAdmin[]>();
  for (const u of usuarios) {
    const mgr = u.manager_id ?? "";
    if (!mgr) continue;
    const lista = mapa.get(mgr) ?? [];
    lista.push(u);
    mapa.set(mgr, lista);
  }
  for (const lista of mapa.values()) {
    lista.sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));
  }
  return mapa;
}

/** Raíces (normalmente solo el director), ordenadas por nombre visible. */
export function raices(usuarios: UsuarioAdmin[], porId: IndiceUsuarios): UsuarioAdmin[] {
  return usuarios
    .filter((u) => esRaiz(u, porId))
    .sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));
}

/**
 * Cabeza de área de una persona: el ancestro que reporta DIRECTO a una raíz. Si la propia
 * persona reporta a una raíz, ella es su cabeza. Una raíz no tiene cabeza (devuelve null:
 * pertenece a Dirección). Itera con tope por seguridad ante ciclos preexistentes.
 */
export function cabezaDeArea(
  u: UsuarioAdmin,
  porId: IndiceUsuarios,
): UsuarioAdmin | null {
  if (esRaiz(u, porId)) return null;
  let actual = u;
  const vistos = new Set<string>();
  while (!vistos.has(actual.id)) {
    vistos.add(actual.id);
    const mgr = porId.get(actual.manager_id ?? "");
    if (!mgr || esRaiz(mgr, porId)) return actual;
    actual = mgr;
  }
  return actual; // ciclo defensivo: devolvemos el último visitado
}

/** Zona (marca o transversal) de una CABEZA de área a partir de su cargo + marcas. */
export function zonaDeCabeza(cabeza: UsuarioAdmin): string {
  if (cabeza.cargo && CARGOS_TRANSVERSALES.has(cabeza.cargo)) return ZONA_TRANSVERSAL;
  const marcas = cabeza.marcas ?? [];
  for (const m of ORDEN_MARCAS) {
    if (marcas.includes(m)) return m;
  }
  return ZONA_TRANSVERSAL;
}

/** Zona de cualquier persona (Dirección si es raíz; si no, la de su cabeza de área). */
export function zonaDe(u: UsuarioAdmin, porId: IndiceUsuarios): string {
  const cabeza = cabezaDeArea(u, porId);
  if (cabeza === null) return ZONA_DIRECCION;
  return zonaDeCabeza(cabeza);
}

/** Agrupa las cabezas de área (hijos directos de una raíz) por zona, en orden de marca. */
export function zonasOrdenadas(cabezas: UsuarioAdmin[]): Array<{
  zona: string;
  cabezas: UsuarioAdmin[];
}> {
  const porZona = new Map<string, UsuarioAdmin[]>();
  for (const c of cabezas) {
    const z = zonaDeCabeza(c);
    const lista = porZona.get(z) ?? [];
    lista.push(c);
    porZona.set(z, lista);
  }
  const orden = [...ORDEN_MARCAS, ZONA_TRANSVERSAL];
  return orden
    .filter((z) => porZona.has(z))
    .map((z) => ({ zona: z, cabezas: porZona.get(z)! }));
}

/** Cuenta recursiva de personas en el subárbol que cuelga de `id` (incluido). */
export function tamanoSubarbol(
  id: string,
  hijos: Map<string, UsuarioAdmin[]>,
): number {
  let total = 1;
  for (const h of hijos.get(id) ?? []) {
    total += tamanoSubarbol(h.id, hijos);
  }
  return total;
}

/**
 * Conjunto de descendientes de `id` (sin incluirlo). Sirve para impedir, en la UI, que el
 * admin elija como superior a alguien que cuelga de la propia persona (cerraría un ciclo;
 * el backend también lo rechaza, esto solo es para no ofrecer la opción).
 */
export function descendientes(
  id: string,
  hijos: Map<string, UsuarioAdmin[]>,
): Set<string> {
  const acc = new Set<string>();
  const pila = [...(hijos.get(id) ?? [])];
  while (pila.length > 0) {
    const u = pila.pop()!;
    if (acc.has(u.id)) continue;
    acc.add(u.id);
    pila.push(...(hijos.get(u.id) ?? []));
  }
  return acc;
}
