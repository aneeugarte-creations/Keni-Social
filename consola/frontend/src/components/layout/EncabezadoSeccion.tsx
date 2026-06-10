import { useLocation } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { SelectorSeccion } from "@/components/layout/SelectorSeccion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

/**
 * Cabecera de sección UNIFICADA, dentro de la barra superior (donde antes estaban los
 * breadcrumbs), a la izquierda del control de marca/filtros y las notificaciones. Tres zonas
 * contiguas:
 *   - SECCIÓN: si la ruta cae en un hub con 2+ pestañas, se pinta como un DROPDOWN compacto
 *     (`SelectorSeccion`) en vez de una tira de pestañas (mucho más cómodo en móvil).
 *   - Hueco de TÍTULO: si es una página plana, su `<TituloPagina/>` se portaliza aquí.
 *     (Hub y título son excluyentes por diseño.)
 *   - Hueco de ACCIONES: el menú "⋮" (vertical) o los controles que la página portalice, JUNTO
 *     a la sección/título.
 *
 * Los huecos los entrega el `AppShell` por contexto (refs `refInicio`/`refAcciones`).
 */
export function EncabezadoSeccion({
  refInicio,
  refAcciones,
}: {
  refInicio: (el: HTMLElement | null) => void;
  refAcciones: (el: HTMLElement | null) => void;
}) {
  const { pathname } = useLocation();
  const { marcaActiva } = useMarcaActiva();
  const pestanas = pestanasDeRuta(pathname)?.filter((p) =>
    rutaVisibleParaMarca(p.ruta, marcaActiva),
  );
  // Hub solo si quedan 2+ pestañas tras el gating por marca (si no, no hay nada que conmutar).
  const hayTabs = !!pestanas && pestanas.length >= 2;

  return (
    <nav aria-label="Cabecera de sección" className="flex h-full min-w-0 items-center gap-1">
      {hayTabs && <SelectorSeccion pestanas={pestanas} pathname={pathname} />}

      {/* Hueco del título de página plana (portal). Excluyente con el dropdown de sección. */}
      <div ref={refInicio} className="flex items-center" />

      {/* Hueco de acciones, JUNTO a la sección/título (portal). */}
      <div ref={refAcciones} className="flex items-center" />
    </nav>
  );
}
