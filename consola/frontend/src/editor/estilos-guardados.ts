// Portapapeles de ESTILO en memoria (módulo, compartido entre el Lienzo y el inspector) + estilos
// GUARDADOS con nombre, persistidos en localStorage por marca. Sin esquema nuevo: un estilo es el
// subconjunto de campos que extrae `estilo.ts::estiloDe`.

import type { Capa } from "./documento";
import { type EstiloCapa, estiloDe } from "./estilo";

// --- Portapapeles en memoria (⌘⌥C / ⌘⌥V y botones del inspector comparten esta var) ----------
let _estiloPortapapeles: EstiloCapa | null = null;

export function copiarEstiloPortapapeles(capa: Capa): void {
  _estiloPortapapeles = estiloDe(capa);
}
export function estiloPortapapeles(): EstiloCapa | null {
  return _estiloPortapapeles;
}

// --- Estilos guardados con nombre, por marca (localStorage) -----------------------------------
export interface EstiloGuardado {
  id: string;
  nombre: string;
  tipo: EstiloCapa["tipo"];
  estilo: EstiloCapa;
}

const clave = (marca: string) => `keni:estilos:${marca || "_"}`;

// Lee la lista de estilos guardados de una marca (tolerante a JSON corrupto/ausente).
export function cargarEstilosGuardados(marca: string): EstiloGuardado[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(clave(marca));
    if (!raw) return [];
    const v = JSON.parse(raw);
    return Array.isArray(v) ? (v as EstiloGuardado[]) : [];
  } catch {
    return [];
  }
}

function escribir(marca: string, lista: EstiloGuardado[]): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(clave(marca), JSON.stringify(lista));
  } catch {
    // Cuota llena / modo privado: el guardado es best-effort, no rompe la edición.
  }
}

// Guarda el estilo de una capa con un nombre; devuelve la lista actualizada.
export function guardarEstilo(marca: string, nombre: string, capa: Capa): EstiloGuardado[] {
  const lista = cargarEstilosGuardados(marca);
  const item: EstiloGuardado = {
    id: `est-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e6).toString(36)}`,
    nombre: nombre.trim() || "Estilo",
    tipo: capa.tipo,
    estilo: estiloDe(capa),
  };
  const next = [...lista, item];
  escribir(marca, next);
  return next;
}

// Elimina un estilo guardado por id; devuelve la lista actualizada.
export function quitarEstiloGuardado(marca: string, id: string): EstiloGuardado[] {
  const next = cargarEstilosGuardados(marca).filter((e) => e.id !== id);
  escribir(marca, next);
  return next;
}
