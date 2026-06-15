import { useNavigate } from "react-router-dom";

import type { ItemTabHub } from "@/components/layout/hub-tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

/**
 * Pestaña activa para un `pathname`: la de coincidencia más específica (la ruta más larga que
 * matchea). Replica la lógica de `NavLink` (`end` exige coincidencia exacta; el resto matchea
 * también las sub-rutas). Si nada matchea, cae a la primera (no debería pasar dentro de un hub).
 */
function tabActivo(pestanas: ItemTabHub[], pathname: string): ItemTabHub {
  let mejor: ItemTabHub | null = null;
  for (const p of pestanas) {
    const matchea = p.end
      ? pathname === p.ruta
      : pathname === p.ruta || pathname.startsWith(`${p.ruta}/`);
    if (matchea && (!mejor || p.ruta.length > mejor.ruta.length)) mejor = p;
  }
  return mejor ?? pestanas[0];
}

/**
 * Navegación de sección como DROPDOWN. Muestra la sección activa —icono + etiqueta— y al elegir
 * otra navega a su ruta. Vive en la barra superior. Mucho más compacto en móvil que una fila
 * de pestañas.
 */
export function SelectorSeccion({
  pestanas,
  pathname,
}: {
  pestanas: ItemTabHub[];
  pathname: string;
}) {
  const navigate = useNavigate();
  const activo = tabActivo(pestanas, pathname);

  return (
    <Select
      value={activo.ruta}
      onValueChange={(ruta) => {
        if (ruta !== activo.ruta) navigate(ruta);
      }}
    >
      <SelectTrigger
        aria-label="Sección"
        className="h-8 w-auto gap-2 border-none bg-transparent px-2 font-medium shadow-none focus:ring-0 focus:ring-offset-0"
      >
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {pestanas.map((p) => {
          const Icono = p.icono;
          return (
            <SelectItem key={p.ruta} value={p.ruta}>
              <span className="flex items-center gap-2">
                <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                {p.etiqueta}
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}
