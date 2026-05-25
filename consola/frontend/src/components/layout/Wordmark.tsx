import { cn } from "@/lib/utils";

/**
 * Wordmark de marca: "KENI · Consola".
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="flex items-baseline gap-1.5 text-sm font-medium tracking-wide">
        <span>KENI</span>
        <span className="text-muted-foreground">·</span>
        <span className="text-muted-foreground">Consola</span>
      </div>
    </div>
  );
}
