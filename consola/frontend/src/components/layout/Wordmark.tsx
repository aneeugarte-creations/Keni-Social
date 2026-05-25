import { cn } from "@/lib/utils";

/**
 * Wordmark de marca: logo Keni (PNG) + "KENI · Consola".
 * El logo es el isotipo naranja de Keni (public/logo-mark.png).
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <img
        src="/logo-mark.png"
        alt=""
        aria-hidden="true"
        className="h-7 w-7 shrink-0 rounded-md"
      />
      <div className="flex items-baseline gap-1.5 text-sm font-semibold tracking-tight">
        <span>KENI</span>
        <span className="text-muted-foreground">·</span>
        <span className="font-normal text-muted-foreground">Consola</span>
      </div>
    </div>
  );
}
