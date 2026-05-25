import { ChevronsUpDown } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Bloque de cuenta del sidebar, al estilo del selector de cuenta de Vercel:
 * avatar con degradado, nombre del usuario y un chevron de "cambiar de cuenta".
 * Por ahora es visual (no abre menú); da sensación de sesión iniciada real.
 */
export function CuentaUsuario({ className }: { className?: string }) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent",
        className,
      )}
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
        <span className="block truncate text-sm font-medium text-foreground">Mikel Martin</span>
        <span className="block truncate text-xs text-muted-foreground">Keni AI</span>
      </span>
      <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
    </button>
  );
}
