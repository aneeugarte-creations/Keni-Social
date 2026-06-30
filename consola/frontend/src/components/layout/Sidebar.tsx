import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { IndicadorUso } from "@/components/layout/IndicadorUso";
import { rutaVisibleParaMarca } from "@/components/layout/gating-marca";
import { subPestanasDe } from "@/components/layout/hub-tabs";
import { iconoDe } from "@/components/layout/navegacion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Clases de un item del sidebar (estilo shadcn: activo resaltado con acento). */
function clasesItem({ isActive }: { isActive: boolean }) {
  return cn(
    "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
    isActive
      ? "bg-accent font-medium text-foreground"
      : "font-normal text-foreground hover:bg-accent hover:text-foreground",
  );
}

/** Clases de un icono del rail (barra colapsada, solo iconos). */
function clasesIconoRail(activa: boolean) {
  return cn(
    "flex h-10 w-10 items-center justify-center rounded-md transition-colors",
    activa
      ? "bg-accent text-foreground"
      : "text-muted-foreground hover:bg-accent hover:text-foreground",
  );
}

/**
 * Barra lateral fija de la consola. La navegación se agrupa por MOMENTO DEL FLUJO
 * (no por dueño de app): el backend (`/api/catalogo` → `navegacion`, ADR 0005)
 * entrega los bloques ya ordenados y etiquetados — `Operación` (checkpoints diarios) ·
 * `Publicacion` (herramientas para crear/editar a mano) · `Datos` (lo que alimenta o
 * refleja la automatización). Cada bloque pinta su encabezado y, debajo,
 * sus entradas como enlaces (icono + nombre). Los hubs (Investigación, Revisión,
 * Analíticas, Parrilla) son UNA entrada; su sub-navegación vive como pestañas
 * in-page (`SubnavHub`), no en el sidebar: así la barra no lista herramientas que se
 * usan dentro de un flujo, no sueltas.
 *
 * En escritorio la barra vive COLAPSADA a un **rail** estrecho de solo iconos (los mismos
 * items, agrupados por bloque con un separador) y se EXPANDE al acercar el ratón (estilo Dock de
 * macOS): el AppShell aloja ese estado de hover/foco y nos pasa `colapsado`; el panel expandido
 * FLOTA sobre el contenido, sin botón ni persistencia. En móvil va siempre expandida (slide-over).
 */
/**
 * ¿`pathname` cae dentro del hub de la entrada `ruta` (una pestaña suya o una sub-ruta de ella)?
 * Para hubs cuyas pestañas no comparten el prefijo de la entrada (la sala de máquinas: la entrada
 * «Agentes» y sus pestañas Cómputo/Economía/Actividad), así la entrada del sidebar sigue marcada
 * activa estando en una pestaña hermana. Para entradas que no son hub, devuelve `false`.
 */
function enHubDe(ruta: string, pathname: string): boolean {
  const pestanas = subPestanasDe(ruta);
  if (!pestanas) return false;
  return pestanas.some((p) => pathname === p.ruta || pathname.startsWith(`${p.ruta}/`));
}

export function Sidebar({
  onNavegar,
  colapsado = false,
  onCuentaAbierta,
}: {
  onNavegar?: () => void;
  colapsado?: boolean;
  /** Avisa cuando el menú de cuenta abre/cierra: el dock no colapsa con el menú abierto. */
  onCuentaAbierta?: (abierto: boolean) => void;
}) {
  const { pathname } = useLocation();
  // Sidebar DATA-DRIVEN (ADR 0005): se hidrata de `/api/catalogo`. El backend ya
  // agrupa la nav por bloque de flujo (apps activas según flags + el Panel del
  // shell) y la ordena; aquí solo la pintamos. `staleTime: Infinity`: el catálogo
  // solo cambia con un redeploy (flags).
  const catalogoQuery = useQuery({
    queryKey: ["catalogo"],
    queryFn: ({ signal }) => api.catalogo(signal),
    staleTime: Infinity,
  });

  // Gating por marca (multitenant): algunas entradas (p. ej. Calendario, solo Claro Sports)
  // se ocultan cuando la marca activa del switch global es otra. Se filtran los ítems y se
  // descartan los bloques que queden vacíos. "Todas" (marcaActiva null, admin) ve todo.
  const { marcaActiva, marcaActivaEsNoticias } = useMarcaActiva();
  const bloques = (catalogoQuery.data?.navegacion ?? [])
    .map((bloque) => ({
      ...bloque,
      items: bloque.items.filter((item) =>
        rutaVisibleParaMarca(item.ruta, marcaActiva, marcaActivaEsNoticias),
      ),
    }))
    .filter((bloque) => bloque.items.length > 0);

  // ---------- Rail (barra colapsada a solo iconos) ----------
  if (colapsado) {
    return (
      <nav
        aria-label="Navegación principal"
        className="flex h-full w-full flex-col border-r border-border bg-background"
      >
        <div className="flex h-12 items-center justify-center border-b border-border">
          <CuentaUsuario soloIcono onAbiertoChange={onCuentaAbierta} />
        </div>

        <div className="flex flex-1 flex-col items-center gap-1 overflow-y-auto py-3">
          {bloques.map((bloque, i) => (
            <div key={bloque.etiqueta || i} className="flex flex-col items-center gap-1">
              {i > 0 && <hr className="my-1 w-8 border-border" />}
              {bloque.items.map((item) => {
                const Icono = iconoDe(item.icono);
                return (
                  <Tooltip key={item.ruta} label={item.etiqueta} side="right">
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      aria-label={item.etiqueta}
                      className={({ isActive }) =>
                        clasesIconoRail(isActive || enHubDe(item.ruta, pathname))
                      }
                    >
                      <Icono className="h-4 w-4" aria-hidden="true" />
                    </NavLink>
                  </Tooltip>
                );
              })}
            </div>
          ))}
        </div>

        <div className="flex flex-col items-center gap-2 border-t border-border py-3">
          <IndicadorUso colapsado />
        </div>
      </nav>
    );
  }

  // ---------- Barra completa (bloques de flujo con encabezado) ----------
  return (
    <nav
      aria-label="Navegación principal"
      className="flex h-full w-full flex-col border-r border-border bg-background"
    >
      <div className="flex h-12 items-center border-b border-border px-2">
        <CuentaUsuario onAbiertoChange={onCuentaAbierta} />
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto px-3 py-4">
        {bloques.map((bloque, i) => (
          <div key={bloque.etiqueta || i} className="space-y-0.5">
            {bloque.etiqueta && (
              <p className="px-3 pb-1 pt-1 text-xs font-medium tracking-wide text-muted-foreground/70">
                {bloque.etiqueta}
              </p>
            )}
            <ul className="space-y-0.5">
              {bloque.items.map((item) => {
                const Icono = iconoDe(item.icono);
                return (
                  <li key={item.ruta}>
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      title={item.descripcion}
                      className={({ isActive }) =>
                        clasesItem({ isActive: isActive || enHubDe(item.ruta, pathname) })
                      }
                    >
                      <Icono className="h-4 w-4 shrink-0" aria-hidden="true" />
                      <span>{item.etiqueta}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      {/* Pie: indicador sutil de uso de la cuenta (la barra ya no se colapsa a mano: se expande al
          acercar el ratón, ver AppShell). */}
      <div className="space-y-1 border-t border-border px-3 py-2">
        <IndicadorUso />
      </div>
    </nav>
  );
}
