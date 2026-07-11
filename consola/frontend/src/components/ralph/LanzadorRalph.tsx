/**
 * Lanzador de un Ralph nuevo — diseño Ane Ugarte.
 *
 * El textarea ES la interfaz: cromo al mínimo y el input como protagonista. El modelo
 * (y el tipo, solo para superadmin) son controles silenciosos en el pie; lanzar es una
 * única acción circular que solo se enciende en naranja cuando hay algo que decir.
 * Al lanzar, el store crea el Ralph, abre su chat y empieza a seguir su stream en vivo.
 */
import { ArrowUp } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { ETIQUETA_MODELO, useRalphStore } from "@/store/ralphStore";
import type { ModeloRalph, TipoRalph } from "@/types/ralph";

const MODELOS: ModeloRalph[] = ["opus", "sonnet", "haiku"];

/** Selector silencioso del pie: solo texto + chevron, sin caja, hasta que lo tocas. */
const DISPARADOR_SILENCIOSO =
  "h-8 w-auto gap-1 rounded-full border-0 bg-transparent px-3 text-sm text-muted-foreground shadow-none hover:bg-accent hover:text-foreground focus:ring-0";

/** El tipo (Operativo/Desarrollo) reposa aún más apagado que el modelo y oculta su
 *  chevron hasta el hover: casi una etiqueta, porque rara vez se cambia. */
const DISPARADOR_TIPO =
  "h-8 w-auto gap-1 rounded-full border-0 bg-transparent px-3 text-sm text-muted-foreground/50 shadow-none hover:bg-accent hover:text-foreground focus:ring-0 [&>svg]:opacity-0 [&>svg]:transition-opacity hover:[&>svg]:opacity-50";

export function LanzadorRalph() {
  const spawn = useRalphStore((s) => s.spawn);
  const spawneando = useRalphStore((s) => s.spawneando);
  const superadmin = useRalphStore((s) => s.superadmin);
  const cerrarLanzador = useRalphStore((s) => s.cerrarLanzador);

  const [prompt, setPrompt] = React.useState("");
  const [modelo, setModelo] = React.useState<ModeloRalph>("opus");
  // Solo el superadmin elige tipo; el resto siempre lanza un Ralph operativo.
  const [tipo, setTipo] = React.useState<TipoRalph>("operativo");

  // Esc cierra el lanzador (sin botón Cancelar visible). No interfiere con el Esc
  // que cierra un Select abierto: Radix lo consume (stopPropagation) antes de llegar.
  React.useEffect(() => {
    const alPulsar = (e: KeyboardEvent) => {
      if (e.key === "Escape") cerrarLanzador();
    };
    document.addEventListener("keydown", alPulsar);
    return () => document.removeEventListener("keydown", alPulsar);
  }, [cerrarLanzador]);

  const hayTexto = prompt.trim().length > 0;
  const esDev = superadmin && tipo === "dev";

  const lanzar = async () => {
    const limpio = prompt.trim();
    if (!limpio) return;
    try {
      await spawn({ prompt: limpio, modelo, tipo: superadmin ? tipo : "operativo" });
      setPrompt("");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo lanzar el Ralph.");
    }
  };

  return (
    <div className="w-[380px] max-w-[calc(100vw-3rem)] rounded-[20px] border border-border bg-card shadow-[0_20px_50px_-20px_rgba(0,0,0,0.25)]">
      <p className="px-4 pt-3 text-[13px] font-medium text-muted-foreground">Ralph</p>
      <AutoTextarea
        autoFocus
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => {
          // Cmd/Ctrl+Enter lanza sin salir del textarea.
          if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
            e.preventDefault();
            void lanzar();
          }
        }}
        placeholder={
          esDev ? "¿Qué quieres que desarrolle este Ralph?" : "¿En qué te ayudo?"
        }
        maxHeight={220}
        className="min-h-[92px] border-0 bg-transparent px-4 pt-1 text-lg shadow-none placeholder:text-muted-foreground/50 focus-visible:ring-0"
      />
      <div className="flex items-center justify-between gap-2 px-2 pb-2">
        <div className="flex items-center gap-1">
          {superadmin && (
            <Select value={tipo} onValueChange={(v) => setTipo(v as TipoRalph)}>
              <SelectTrigger className={DISPARADOR_TIPO} aria-label="Tipo de Ralph">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="operativo">Operativo</SelectItem>
                <SelectItem value="dev">Desarrollo</SelectItem>
              </SelectContent>
            </Select>
          )}
          <Select value={modelo} onValueChange={(v) => setModelo(v as ModeloRalph)}>
            <SelectTrigger className={DISPARADOR_SILENCIOSO} aria-label="Modelo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODELOS.map((m) => (
                <SelectItem key={m} value={m}>
                  {ETIQUETA_MODELO[m]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          type="button"
          variant={hayTexto ? "brand" : "ghost"}
          size="icon"
          onClick={lanzar}
          disabled={spawneando || !hayTexto}
          aria-label="Lanzar"
          className={cn(
            "h-9 w-9 shrink-0 rounded-full",
            !hayTexto && "bg-muted text-muted-foreground/40",
          )}
        >
          {spawneando ? <Spinner className="h-4 w-4" /> : <ArrowUp className="h-4 w-4" />}
        </Button>
      </div>
    </div>
  );
}
