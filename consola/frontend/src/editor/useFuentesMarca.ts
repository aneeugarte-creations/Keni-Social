// Carga las tipografías propias de la marca (activos tipo 'tipografia') como FontFace para que el
// lienzo Konva las pinte, y devuelve sus nombres de familia para el selector del inspector. El
// servidor registra las MISMAS familias al exportar (dominio `_fuentes_extra_de_marca`), así que
// "lo que ves = lo que sale".

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { api, type ActivoMarca } from "@/lib/api";

// Familias ya cargadas en el documento (evita re-añadir la misma FontFace).
const _cargadas = new Set<string>();

function familiaDe(a: ActivoMarca): string {
  const meta = (a.metadatos?.familia as string) || "";
  return (meta || a.nombre || "").trim();
}

export function useFuentesMarca(marca: string): string[] {
  const q = useQuery({
    queryKey: ["marca-activos", "tipografia", marca],
    queryFn: ({ signal }) => api.marcaActivos({ marca: marca || undefined, tipo: "tipografia" }, signal),
    enabled: !!marca,
  });
  const activos = q.data?.activos ?? [];

  useEffect(() => {
    if (typeof document === "undefined" || !("fonts" in document)) return;
    for (const a of activos) {
      const familia = familiaDe(a);
      if (!familia || !a.objeto) continue;
      const clave = `${familia}::${a.objeto}`;
      if (_cargadas.has(clave)) continue;
      _cargadas.add(clave);
      try {
        const ff = new FontFace(familia, `url(/api/media/${a.objeto})`);
        ff.load()
          .then((cargada) => document.fonts.add(cargada))
          .catch(() => _cargadas.delete(clave));
      } catch {
        _cargadas.delete(clave);
      }
    }
  }, [activos]);

  return activos.map(familiaDe).filter(Boolean);
}
