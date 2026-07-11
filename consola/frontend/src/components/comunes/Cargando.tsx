import { Spinner } from "@/components/ui/spinner";

/**
 * Espera centrada (spinner + texto), tolerante a segundos. Para diálogos, paneles y listados que
 * tardan un instante; sustituye el texto pelado "Cargando…". La `nota` opcional añade una segunda
 * línea de contexto (p. ej. "puede tardar unos segundos").
 */
export function Cargando({ nota }: { nota?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
      <Spinner className="h-6 w-6" />
      <p className="text-sm">Cargando…</p>
      {nota && <p className="text-xs">{nota}</p>}
    </div>
  );
}
