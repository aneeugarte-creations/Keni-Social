/**
 * Hook local de ordenación de tablas para el dashboard de Métricas.
 *
 * Implementa un sort simple y reutilizable (sin dependencias nuevas tipo
 * tanstack-table): mantiene la clave activa y la dirección, alterna asc/desc al
 * volver a clicar la misma columna, y devuelve la lista ya ordenada de forma
 * estable. Los valores `null`/no finitos se ordenan SIEMPRE al final (no son un 0
 * real), independientemente de la dirección.
 */
import * as React from "react";

export type DireccionOrden = "asc" | "desc";

/** Estado de orden: columna activa (o null = orden natural) + dirección. */
export interface EstadoOrden<Clave extends string> {
  clave: Clave | null;
  direccion: DireccionOrden;
}

/** Valor de aria-sort para la cabecera de una columna dado el estado actual. */
export function ariaSort<Clave extends string>(
  estado: EstadoOrden<Clave>,
  clave: Clave,
): "ascending" | "descending" | "none" {
  if (estado.clave !== clave) return "none";
  return estado.direccion === "asc" ? "ascending" : "descending";
}

/**
 * Ordena `filas` según una columna seleccionable por el usuario.
 *
 * - `accesores`: mapa clave -> función que extrae el valor comparable de una fila
 *   (número o string; `null`/`undefined` van al final).
 * - `inicial`: orden por defecto (clave + dirección). Si se omite, no ordena.
 *
 * Devuelve la lista ordenada (estable), el estado actual y `alClicar(clave)` para
 * el `onClick` de la cabecera (alterna asc/desc; primer clic en columna nueva = desc
 * para numéricas suele ser lo útil, pero respetamos el `inicial` si lo das).
 */
export function useOrdenTabla<Fila, Clave extends string>(
  filas: readonly Fila[],
  accesores: Record<Clave, (fila: Fila) => number | string | null | undefined>,
  inicial?: EstadoOrden<Clave>,
): {
  filasOrdenadas: Fila[];
  estado: EstadoOrden<Clave>;
  alClicar: (clave: Clave) => void;
} {
  const [estado, setEstado] = React.useState<EstadoOrden<Clave>>(
    inicial ?? { clave: null, direccion: "desc" },
  );

  const alClicar = React.useCallback((clave: Clave) => {
    setEstado((prev) =>
      prev.clave === clave
        ? { clave, direccion: prev.direccion === "asc" ? "desc" : "asc" }
        : // Columna nueva: arrancamos en descendente (lo natural para métricas).
          { clave, direccion: "desc" },
    );
  }, []);

  const filasOrdenadas = React.useMemo(() => {
    if (estado.clave == null) return [...filas];
    const acceso = accesores[estado.clave];
    const signo = estado.direccion === "asc" ? 1 : -1;
    // `map`+`sort` con índice para un orden estable entre elementos equivalentes.
    return filas
      .map((fila, i) => ({ fila, i }))
      .sort((a, b) => {
        const va = acceso(a.fila);
        const vb = acceso(b.fila);
        const na = va == null || (typeof va === "number" && !Number.isFinite(va));
        const nb = vb == null || (typeof vb === "number" && !Number.isFinite(vb));
        // null/no finito SIEMPRE al final, sea asc o desc.
        if (na && nb) return a.i - b.i;
        if (na) return 1;
        if (nb) return -1;
        let cmp: number;
        if (typeof va === "number" && typeof vb === "number") {
          cmp = va - vb;
        } else {
          cmp = String(va).localeCompare(String(vb), "es-MX");
        }
        return cmp !== 0 ? cmp * signo : a.i - b.i;
      })
      .map((x) => x.fila);
  }, [filas, accesores, estado]);

  return { filasOrdenadas, estado, alClicar };
}
