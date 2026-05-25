import { cn } from "@/lib/utils";

/**
 * Wordmark de marca: "KENI · Consola".
 */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="flex items-baseline text-sm font-semibold tracking-tight">
        <span>KENI</span>
      </div>
    </div>
  );
}
