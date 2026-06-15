/**
 * Modal de PUBLICACIÓN de la Biblioteca: muestra el diff entre lo que hay en producción
 * y la versión a publicar, exige una nota de cambio y, según el rol:
 *   - admin   → "Publicar a producción" (POST /texto/{id}/publicar).
 *   - no admin → "Solicitar publicación" (POST /texto/{id}/solicitar): queda en la
 *     bandeja de solicitudes para que un admin la apruebe o rechace.
 *
 * Aviso claro del efecto: la versión publicada pasa a servir TODAS las generaciones.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Rocket, Send } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DiffProsa } from "@/components/biblioteca/DiffProsa";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import { claveSolicitudes } from "@/hooks/use-biblioteca";

export interface DialogPublicarProps {
  docId: string;
  abierto: boolean;
  onCerrar: () => void;
  /** `true` => publica directo; `false` => solo puede solicitar. Ver `useEsAdmin`. */
  esAdmin: boolean;
  /** Cuerpo (markdown) de la versión EN PRODUCCIÓN ("" si nunca se publicó). */
  antes: string;
  /** Cuerpo (markdown) de la versión A PUBLICAR. */
  despues: string;
  /** SHA de la versión a publicar; omitido = la versión actual (HEAD). */
  sha?: string;
  /** Tras publicar o solicitar con éxito (además de cerrar y refrescar queries). */
  onHecho?: () => void;
}

export function DialogPublicar({
  docId,
  abierto,
  onCerrar,
  esAdmin,
  antes,
  despues,
  sha,
  onHecho,
}: DialogPublicarProps) {
  const qc = useQueryClient();
  const [nota, setNota] = React.useState("");
  const [soloCambios, setSoloCambios] = React.useState(true);
  React.useEffect(() => {
    if (abierto) {
      setNota("");
      setSoloCambios(true);
    }
  }, [abierto]);

  const alExito = (mensaje: string) => {
    toast.success(mensaje);
    qc.invalidateQueries({ queryKey: ["texto"] });
    qc.invalidateQueries({ queryKey: claveSolicitudes("abierta") });
    onCerrar();
    onHecho?.();
  };

  const publicarMut = useMutation({
    mutationFn: () => api.publicarTexto(docId, { sha, nota: nota.trim() }),
    onSuccess: () => alExito("Versión publicada: ya sirve todas las generaciones."),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const solicitarMut = useMutation({
    mutationFn: () => api.solicitarPublicacionTexto(docId, { sha, nota: nota.trim() }),
    onSuccess: () =>
      alExito("Solicitud enviada: un admin la revisará antes de publicar."),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const enviando = publicarMut.isPending || solicitarMut.isPending;
  const notaValida = nota.trim().length > 0;

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="flex max-h-[88vh] max-w-4xl flex-col gap-3 overflow-hidden">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {esAdmin ? <Rocket className="h-4 w-4" /> : <Send className="h-4 w-4" />}
            {esAdmin ? "Publicar cambios" : "Solicitar publicación"}
          </DialogTitle>
        </DialogHeader>

        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          {esAdmin
            ? "Servirá todas las generaciones."
            : "Si un admin la aprueba, servirá todas las generaciones. Hasta entonces, sin cambios."}
        </p>

        {/* Qué cambia respecto a lo que hay en producción. */}
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{antes ? "Cambios respecto a lo publicado" : "Primera publicación de este documento"}</span>
          <label className="flex cursor-pointer items-center gap-1.5">
            Solo cambios
            <Switch checked={soloCambios} onCheckedChange={setSoloCambios} />
          </label>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
          <DiffProsa antes={antes} despues={despues} soloCambios={soloCambios} />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor={`nota-publicar-${docId}`}>
            Nota de cambio <span className="text-destructive">*</span>
          </Label>
          <Textarea
            id={`nota-publicar-${docId}`}
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            rows={2}
            placeholder="Qué cambia y por qué"
          />
        </div>

        <div className="flex items-center justify-end gap-2">
          <Button variant="ghost" onClick={onCerrar} disabled={enviando}>
            Cancelar
          </Button>
          {esAdmin ? (
            <Button
              variant="brand"
              disabled={!notaValida || enviando}
              onClick={() => publicarMut.mutate()}
            >
              <Rocket className="mr-1 h-3.5 w-3.5" />
              {publicarMut.isPending ? "Publicando…" : "Publicar cambios"}
            </Button>
          ) : (
            <Button
              variant="brand"
              disabled={!notaValida || enviando}
              onClick={() => solicitarMut.mutate()}
            >
              <Send className="mr-1 h-3.5 w-3.5" />
              {solicitarMut.isPending ? "Enviando…" : "Solicitar publicación"}
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
