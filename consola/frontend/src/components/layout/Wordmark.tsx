import { cn } from "@/lib/utils";

/** Marca: wordmark "KENI". */
export function Wordmark({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center", className)}>
      <span className="text-[13px] font-normal tracking-wider text-foreground">KENI</span>
    </div>
  );
}
