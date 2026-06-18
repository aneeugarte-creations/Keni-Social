/**
 * Lanzador de un Ralph nuevo: textarea de prompt + selector de modelo (opus por
 * defecto) + botón Lanzar. Al lanzar, el store crea el Ralph, abre su chat y empieza
 * a seguir su stream en vivo.
 */
import { Loader2, Rocket } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ETIQUETA_MODELO, useRalphStore } from "@/store/ralphStore";
import type { ModeloRalph, TipoRalph } from "@/types/ralph";

const MODELOS: ModeloRalph[] = ["opus", "sonnet", "haiku"];

export function LanzadorRalph() {
  const spawn = useRalphStore((s) => s.spawn);
  const spawneando = useRalphStore((s) => s.spawneando);
  const cerrarLanzador = useRalphStore((s) => s.cerrarLanzador);
  const superadmin = useRalphStore((s) => s.superadmin);

  const [prompt, setPrompt] = React.useState("");
  const [modelo, setModelo] = React.useState<ModeloRalph>("opus");
  // Solo el superadmin elige tipo; el resto siempre lanza un Ralph operativo.
  const [tipo, setTipo] = React.useState<TipoRalph>("operativo");

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

  const esDev = superadmin && tipo === "dev";

  return (
    <Card className="w-[360px] max-w-[calc(100vw-3rem)] shadow-xl">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Lanzar Ralph</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {superadmin && (
          <Select value={tipo} onValueChange={(v) => setTipo(v as TipoRalph)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="operativo">Operativo · asistente del equipo (MCP)</SelectItem>
              <SelectItem value="dev">Desarrollo · sobre el repo (solo tú)</SelectItem>
            </SelectContent>
          </Select>
        )}
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
            esDev
              ? "¿Qué quieres que desarrolle este Ralph?"
              : "¿En qué te ayudo hoy? (marcas, contenido, métricas, noticias…)"
          }
          maxHeight={200}
          className="min-h-[88px]"
        />
        <div className="flex items-center gap-2">
          <Select value={modelo} onValueChange={(v) => setModelo(v as ModeloRalph)}>
            <SelectTrigger className="w-[130px]">
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
          <div className="ml-auto flex gap-2">
            <Button variant="ghost" size="sm" onClick={cerrarLanzador} disabled={spawneando}>
              Cancelar
            </Button>
            <Button
              variant="brand"
              size="sm"
              onClick={lanzar}
              disabled={spawneando || !prompt.trim()}
            >
              {spawneando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Rocket className="h-4 w-4" />
              )}
              Lanzar
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
