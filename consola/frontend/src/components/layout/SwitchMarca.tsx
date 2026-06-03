/**
 * Switch de MARCA ACTIVA en la barra superior. Es el "workspace" de marca: la
 * consola entera trabaja sobre la marca activa (no mezclar). Deriva del perfil
 * (`useMarcaActiva`):
 *
 *   - Editor de una sola marca → un chip fijo con su marca (no hay nada que
 *     cambiar; el filtro es implícito y permanente).
 *   - Editor multimarca / admin → un selector entre sus marcas (admin: todas +
 *     "Todas"). Cambiar de marca es deliberado y se persiste por usuario.
 *   - Cuando se está FUERA de la marca de casa, el control se resalta (ámbar) y
 *     aparece "Volver", para que nunca se publique en la marca equivocada por
 *     inercia.
 */
import { Building2, Undo2 } from "lucide-react";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip } from "@/components/ui/tooltip";
import { MARCA_ACTIVA_TODAS, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { cn } from "@/lib/utils";

export function SwitchMarca() {
  const {
    marcaActiva,
    esMultiMarca,
    puedeTodas,
    marcasParaSwitch,
    nombreActiva,
    enMarcaPrimaria,
    marcaPrimaria,
    cambiarMarca,
    volverAPrimaria,
  } = useMarcaActiva();

  // Editor de una sola marca: chip fijo. El filtro de marca es implícito.
  if (!esMultiMarca) {
    if (!marcaActiva) return null; // sin marca asignada y sin poder agregar: nada que mostrar.
    return (
      <Tooltip label="Tu marca">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/40 px-2.5 py-1 text-sm font-medium text-foreground">
          <Building2 className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          <span className="truncate">{nombreActiva ?? marcaActiva}</span>
        </span>
      </Tooltip>
    );
  }

  const valor = marcaActiva ?? MARCA_ACTIVA_TODAS;
  const fueraDeCasa = !enMarcaPrimaria && marcaPrimaria !== null;

  return (
    <div className="flex items-center gap-1.5">
      <Select
        value={valor}
        onValueChange={(v) => cambiarMarca(v === MARCA_ACTIVA_TODAS ? null : v)}
      >
        <SelectTrigger
          aria-label="Marca activa"
          className={cn(
            "h-8 w-[180px] gap-1.5",
            fueraDeCasa &&
              "border-amber-500/60 bg-amber-500/10 text-amber-700 dark:text-amber-400",
          )}
        >
          <Building2 className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden="true" />
          <SelectValue placeholder="Marca" />
        </SelectTrigger>
        <SelectContent>
          {puedeTodas && <SelectItem value={MARCA_ACTIVA_TODAS}>Todas las marcas</SelectItem>}
          {marcasParaSwitch.map((m) => (
            <SelectItem key={m.id} value={m.id}>
              {m.nombre}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {fueraDeCasa && (
        <Tooltip label="Estás fuera de tu marca. Volver a la tuya.">
          <button
            type="button"
            onClick={volverAPrimaria}
            className="inline-flex h-8 items-center gap-1 rounded-md px-1.5 text-xs font-medium text-amber-700 transition-colors hover:bg-amber-500/10 dark:text-amber-400"
            aria-label="Volver a tu marca"
          >
            <Undo2 className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden lg:inline">Volver</span>
          </button>
        </Tooltip>
      )}
    </div>
  );
}
