import { cn } from "@/lib/utils";

/**
 * Wordmark de marca: cuadro-logo naranja Keni + "KENI · Consola".
 * El cuadro lleva la inicial "K" en blanco sobre el naranja #ff5a1f.
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-sm font-bold text-white shadow-sm"
        style={{ backgroundColor: "#ff5a1f" }}
        aria-hidden="true"
      >
        K
      </div>
      <div className="flex items-baseline gap-1.5 text-sm font-semibold tracking-tight">
        <span>KENI</span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">Consola</span>
      </div>
    </div>
  );
}
