import { ChevronsUpDown, LogOut } from "lucide-react";
import * as React from "react";

import { useSesion } from "@/hooks/sesion-contexto";
import { cn } from "@/lib/utils";
import type { RolUsuario } from "@/types";

/** Etiqueta legible del rol para mostrar bajo el nombre. */
const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

function etiquetaRol(rol: RolUsuario): string {
  return ROL_LABEL[rol] ?? rol;
}

/**
 * Bloque de cuenta del sidebar (estilo selector de cuenta de Vercel): avatar con
 * degradado, nombre del usuario actual y su rol. Al pulsarlo abre un menú con la
 * acción "Cerrar sesión" (POST /api/auth/logout → vuelve al login). El usuario
 * sale del contexto de sesión; si todavía no hay (carga), no pinta nada.
 */
export function CuentaUsuario({ className }: { className?: string }) {
  const { usuario, cerrarSesion } = useSesion();
  const [abierto, setAbierto] = React.useState(false);
  const [cerrando, setCerrando] = React.useState(false);
  const contenedorRef = React.useRef<HTMLDivElement>(null);

  // Cierra el menú al pulsar fuera o con Escape.
  React.useEffect(() => {
    if (!abierto) return;
    function alPulsarFuera(e: MouseEvent) {
      if (contenedorRef.current && !contenedorRef.current.contains(e.target as Node)) {
        setAbierto(false);
      }
    }
    function alTeclear(e: KeyboardEvent) {
      if (e.key === "Escape") setAbierto(false);
    }
    document.addEventListener("mousedown", alPulsarFuera);
    document.addEventListener("keydown", alTeclear);
    return () => {
      document.removeEventListener("mousedown", alPulsarFuera);
      document.removeEventListener("keydown", alTeclear);
    };
  }, [abierto]);

  if (!usuario) return null;

  async function alCerrarSesion() {
    setCerrando(true);
    setAbierto(false);
    await cerrarSesion();
    // No reseteamos `cerrando`: la pantalla de login reemplaza este árbol.
  }

  return (
    <div ref={contenedorRef} className={cn("relative w-full", className)}>
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={abierto}
        className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent"
      >
        {/* Avatar de degradado (estilo Vercel). */}
        <span
          className="h-5 w-5 shrink-0 rounded-full ring-1 ring-border"
          style={{
            backgroundImage: "linear-gradient(135deg, #ff9670 0%, #ff5a1f 45%, #d12d07 100%)",
          }}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-sm font-medium text-foreground">
            {usuario.usuario}
          </span>
          <span className="block truncate text-xs text-muted-foreground">
            {etiquetaRol(usuario.rol)}
          </span>
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      </button>

      {abierto && (
        <div
          role="menu"
          aria-label="Cuenta"
          className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-md border border-border bg-popover py-1 text-popover-foreground shadow-md"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => void alCerrarSesion()}
            disabled={cerrando}
            className="flex w-full items-center gap-2.5 px-3 py-2 text-left text-sm text-foreground transition-colors hover:bg-accent disabled:opacity-50"
          >
            <LogOut className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}
