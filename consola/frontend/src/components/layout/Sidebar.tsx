import { NavLink } from "react-router-dom";

import { CuentaUsuario } from "@/components/layout/CuentaUsuario";
import { navegacionParaRol } from "@/components/layout/navegacion";
import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";

/**
 * Barra lateral fija con el wordmark, los grupos de navegacion (Trabajo /
 * Ajustes) y un pie discreto. Resalta la ruta activa con el color de marca. La
 * sección "Usuarios" (gestión de cuentas) solo aparece para el rol admin.
 */
export function Sidebar({ onNavegar }: { onNavegar?: () => void }) {
  const { usuario } = useSesion();
  const navegacion = navegacionParaRol(usuario?.rol === "admin");

  return (
    <nav
      aria-label="Navegación principal"
      className="flex h-full w-64 flex-col border-r border-border bg-background"
    >
      <div className="flex h-12 items-center border-b border-border px-2">
        <CuentaUsuario />
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        {navegacion.map((grupo, idx) => (
          <div key={grupo.etiqueta || `__bloque-${idx}`}>
            {grupo.etiqueta !== "" && (
              <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                {grupo.etiqueta}
              </p>
            )}
            <ul className="space-y-0.5">
              {grupo.items.map((item) => {
                const Icono = item.icono;
                return (
                  <li key={item.ruta}>
                    <NavLink
                      to={item.ruta}
                      onClick={onNavegar}
                      title={item.descripcion}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                          isActive
                            ? "bg-accent font-medium text-foreground"
                            : "font-normal text-muted-foreground hover:bg-accent hover:text-foreground",
                        )
                      }
                    >
                      <Icono className="h-4 w-4 shrink-0" />
                      <span>{item.etiqueta}</span>
                    </NavLink>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-border px-4 py-3 text-xs text-muted-foreground">
        <span>Herramienta local · 127.0.0.1</span>
        <span className="ml-2 inline-flex items-center rounded-full border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium tracking-wider text-muted-foreground">
          beta
        </span>
      </div>
    </nav>
  );
}
