import { NavLink, useLocation } from "react-router-dom";

import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { pestanasDeRuta } from "@/components/layout/hub-tabs";
import { clasesPestanaSeccion } from "@/components/layout/pestanas-seccion";
import { SelectorSeccion } from "@/components/layout/SelectorSeccion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";

/**
 * Cabecera de sección UNIFICADA, dentro de la barra superior, a la izquierda del flanco derecho
 * (acciones de página + control de marca/filtros + notificaciones). Dos zonas contiguas:
 *   - SECCIÓN: si la ruta cae en un hub con 2+ pestañas, se pinta de DOS formas según el ancho:
 *       · ESCRITORIO (`md+`): la tira de pestañas horizontal de siempre (la activa muerde el
 *         borde inferior del header).
 *       · MÓVIL (`<md`): un DROPDOWN compacto (`SelectorSeccion`), que no ocupa una fila entera.
 *   - Hueco de TÍTULO: si es una página plana, su `<TituloPagina/>` se portaliza aquí.
 *     (Hub y título son excluyentes por diseño.)
 *
 * El hueco de TÍTULO lo entrega el `AppShell` por contexto (ref `refInicio`). Las ACCIONES de la
 * página (el menú "⋮", los controles de la máquina…) NO viven aquí: el AppShell las portaliza en
 * el flanco derecho de la barra, separadas de las pestañas para que el "⋮" no caiga en el camino
 * de lectura de la navegación ni compita con ella.
 */
export function EncabezadoSeccion({
  refInicio,
}: {
  refInicio: (el: HTMLElement | null) => void;
}) {
  const { pathname } = useLocation();
  const { marcaActiva, marcaActivaEsNoticias, etiquetaInvestigacion } = useMarcaActiva();
  const pestanas = pestanasDeRuta(pathname)
    ?.filter((p) => rutaVisibleParaMarca(p.ruta, marcaActiva, marcaActivaEsNoticias))
    // El panel de investigación se llama según la marca activa (p.ej. "Curiosidades"); "Noticias" por defecto.
    .map((p) =>
      p.ruta === "/datos/investigacion" ? { ...p, etiqueta: etiquetaInvestigacion ?? "Noticias" } : p,
    );
  // Hub solo si quedan 2+ pestañas tras el gating por marca (si no, no hay nada que conmutar).
  const hayTabs = !!pestanas && pestanas.length >= 2;

  return (
    <nav
      aria-label="Cabecera de sección"
      className="flex h-full min-w-0 items-stretch gap-1 self-stretch"
    >
      {hayTabs && (
        <>
          {/* ESCRITORIO: tira de pestañas a altura completa; la activa muerde el borde del header. */}
          <div className="hidden h-full items-stretch md:flex">
            {pestanas.map((pestana) => {
              const Icono = pestana.icono;
              return (
                <NavLink
                  key={pestana.ruta}
                  to={pestana.ruta}
                  end={pestana.end}
                  className={({ isActive }) => clasesPestanaSeccion(isActive)}
                >
                  <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{pestana.etiqueta}</span>
                </NavLink>
              );
            })}
          </div>

          {/* MÓVIL: el mismo conjunto de pestañas, como dropdown compacto. */}
          <div className="flex items-center md:hidden">
            <SelectorSeccion pestanas={pestanas} pathname={pathname} />
          </div>
        </>
      )}

      {/* Hueco del título de página plana (portal). Excluyente con la sección. `min-w-0`
          deja ENCOGER el hueco en móvil para que el `truncate` del título actúe (sin esto
          el control de marca de la derecha lo pisaba). */}
      <div ref={refInicio} className="flex min-w-0 items-center" />
    </nav>
  );
}
