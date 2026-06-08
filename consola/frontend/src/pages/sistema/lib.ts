import { toast } from "sonner";

import type { ObjetoS3 } from "@/types";

import type { ClaveOrden, OrdenS3 } from "./tipos";

// Auto-refresco de los recursos: cada 8 s da un pulso vivo sin martillear el back.
export const INTERVALO_RECURSOS_MS = 8000;

/** Bytes → cadena legible (GB/MB/KB). 0 si no hay dato. */
export function formatoBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const unidades = ["KB", "MB", "GB", "TB", "PB"];
  let valor = bytes / 1024;
  let i = 0;
  while (valor >= 1024 && i < unidades.length - 1) {
    valor /= 1024;
    i += 1;
  }
  return `${valor.toFixed(valor >= 100 || i === 0 ? 0 : 1)} ${unidades[i]}`;
}

export function formatoPorcentaje(pct: number | null | undefined): string {
  return pct == null ? "—" : `${pct.toFixed(0)}%`;
}

/** Color de la barra según el nivel de uso (verde → ámbar → rojo). */
export function colorUso(pct: number | null | undefined): string {
  if (pct == null) return "bg-muted-foreground/40";
  if (pct >= 90) return "bg-red-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

const EXT_IMAGEN = new Set(["png", "jpg", "jpeg", "gif", "webp", "avif", "svg"]);

/** `true` si la key/nombre apunta a una imagen previsualizable (por extensión). */
export function esImagen(key: string): boolean {
  const ext = key.split(".").pop()?.toLowerCase() ?? "";
  return EXT_IMAGEN.has(ext);
}

/**
 * Devuelve una copia ordenada de `objetos`. Sin orden activo respeta el orden del bucket.
 * Por tamaño/fecha el default es descendente (lo más grande/reciente primero); por nombre,
 * ascendente. El nulo de `modificado` se va al final en ambas direcciones.
 */
export function ordenarObjetos(objetos: ObjetoS3[], orden: OrdenS3 | null): ObjetoS3[] {
  if (!orden) return objetos;
  const factor = orden.dir === "asc" ? 1 : -1;
  return [...objetos].sort((a, b) => {
    if (orden.clave === "tamano") return (a.tamano - b.tamano) * factor;
    if (orden.clave === "modificado") {
      // Sin fecha al final, independientemente de la dirección.
      if (!a.modificado) return 1;
      if (!b.modificado) return -1;
      return a.modificado.localeCompare(b.modificado) * factor;
    }
    return a.nombre.localeCompare(b.nombre, "es") * factor;
  });
}

/** Dirección por defecto al activar una columna: texto asc, tamaño/fecha desc. */
export function dirPorDefecto(clave: ClaveOrden): "asc" | "desc" {
  return clave === "nombre" ? "asc" : "desc";
}

/** Copia un texto al portapapeles, con aviso. */
export async function copiarTexto(texto: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(texto);
    toast.success("Clave copiada al portapapeles.");
  } catch {
    toast.error("No se pudo copiar la clave.");
  }
}
