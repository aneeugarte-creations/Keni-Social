// Tipografías de marca para PINTAR nombres de marca FUERA del editor (p. ej. el selector de marca
// del topbar). Devuelve un mapa marca→familia (la PRIMERA tipografía catalogada de cada marca) y
// registra sus FontFace para que el navegador las pueda pintar. Las MISMAS familias las carga el
// editor (`useFuentesMarca`) y las registra el servidor al exportar: "lo que ves = lo que sale".
//
// Coste: la lista de tipografías es JSON ligero (cacheado), pero los binarios pesan; por eso solo
// se descargan los de las marcas en `idsACargar` (las que de verdad se van a mostrar), no todas.

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo } from "react";

import { api, type ActivoMarca } from "@/lib/api";

// FontFace ya añadidas al documento (evita re-descargar la misma familia). Módulo-global como en
// `useFuentesMarca`, así el topbar y el editor comparten lo ya cargado.
const _cargadas = new Set<string>();

function familiaDe(a: ActivoMarca): string {
  return (((a.metadatos?.familia as string) || a.nombre || "") as string).trim();
}

/**
 * @param idsACargar marcas cuyas FontFace deben descargarse (la familia solo se PINTA si está
 *   cargada). El mapa devuelto incluye TODAS las marcas con tipografía (para consultarlo), pero los
 *   binarios solo se traen para estos ids.
 * @returns mapa `idMarca → familia` (familia representativa = primera tipografía de la marca).
 */
export function useFuentesDeMarcas(idsACargar: string[]): Map<string, string> {
  const q = useQuery({
    queryKey: ["marca-activos", "tipografia", "_todas"],
    queryFn: ({ signal }) => api.marcaActivos({ tipo: "tipografia" }, signal),
    staleTime: Infinity,
  });
  const activos = q.data?.activos ?? [];

  // marca → { familia, objeto } de su PRIMERA tipografía (orden del catálogo).
  const { familias, objetos } = useMemo(() => {
    const familias = new Map<string, string>();
    const objetos = new Map<string, string>();
    for (const a of activos) {
      const familia = familiaDe(a);
      if (!familia || familias.has(a.marca)) continue;
      familias.set(a.marca, familia);
      if (a.objeto) objetos.set(a.marca, a.objeto);
    }
    return { familias, objetos };
  }, [activos]);

  const clavesACargar = idsACargar.filter(Boolean).join(",");
  useEffect(() => {
    if (typeof document === "undefined" || !("fonts" in document)) return;
    for (const id of idsACargar) {
      const familia = familias.get(id);
      const objeto = objetos.get(id);
      if (!familia || !objeto) continue;
      const clave = `${familia}::${objeto}`;
      if (_cargadas.has(clave)) continue;
      _cargadas.add(clave);
      try {
        const ff = new FontFace(familia, `url(/api/media/${objeto})`);
        ff.load()
          .then((cargada) => document.fonts.add(cargada))
          .catch(() => _cargadas.delete(clave));
      } catch {
        _cargadas.delete(clave);
      }
    }
    // `familias`/`objetos` derivan de `activos` (cacheado por react-query); `clavesACargar` cambia
    // al abrir el dropdown (se piden más marcas).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clavesACargar, familias, objetos]);

  return familias;
}
