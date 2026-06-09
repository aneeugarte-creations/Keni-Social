/**
 * Diálogo para crear o editar una CAMPAÑA: nombre + hashtags configurables (varios).
 *
 * La marca la fija el switch global de la barra superior (`useMarcaActiva`); una campaña
 * pertenece a una marca concreta. Los hashtags se escriben separados por espacios o comas
 * y se previsualizan normalizados (sin '#', en minúsculas) tal como los guardará el backend.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { CampaniaComercial } from "@/types";

import { CLAVE_COMERCIAL } from "./claves";

/** Normaliza un texto de hashtags (separados por espacios/comas) a una lista única. */
function parsearHashtags(texto: string): string[] {
  const vistos: string[] = [];
  for (const bruto of texto.split(/[\s,]+/)) {
    const tag = bruto.trim().replace(/^#+/, "").toLowerCase();
    if (tag && !vistos.includes(tag)) vistos.push(tag);
  }
  return vistos;
}

export function DialogoCampania({
  abierto,
  campania,
  onCerrar,
}: {
  abierto: boolean;
  /** Campaña a editar, o `null` para crear una nueva. */
  campania: CampaniaComercial | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva, nombreActiva } = useMarcaActiva();
  const editando = campania != null;

  const [nombre, setNombre] = React.useState("");
  const [hashtagsTexto, setHashtagsTexto] = React.useState("");

  // Al abrir, sembrar el formulario con los datos de la campaña (edición) o vacío (alta).
  React.useEffect(() => {
    if (!abierto) return;
    setNombre(campania?.nombre ?? "");
    setHashtagsTexto(campania ? campania.hashtags.map((h) => `#${h}`).join(" ") : "");
  }, [abierto, campania]);

  const hashtags = parsearHashtags(hashtagsTexto);

  const guardar = useMutation({
    mutationFn: () => {
      if (editando) {
        return api.actualizarCampania(campania.id, { nombre: nombre.trim(), hashtags });
      }
      return api.crearCampania({ marca: marcaActiva ?? "", nombre: nombre.trim(), hashtags });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
      toast.success(editando ? "Campaña actualizada" : "Campaña creada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar =
    (editando || marcaActiva != null) &&
    Boolean(nombre.trim()) &&
    hashtags.length > 0 &&
    !guardar.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar campaña" : "Nueva campaña"}</DialogTitle>
          <DialogDescription>
            {editando
              ? "Cambia el nombre o los hashtags que agrupan las piezas."
              : `Agrupa las piezas de ${nombreActiva ?? "la marca"} por uno o varios hashtags.`}
          </DialogDescription>
        </DialogHeader>

        {!editando && marcaActiva == null ? (
          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
            Elige una marca concreta en la barra superior para crear una campaña.
          </p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="campania-nombre">Nombre</Label>
              <Input
                id="campania-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Campaña Chihuahua"
                autoFocus
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="campania-hashtags">Hashtags</Label>
              <Input
                id="campania-hashtags"
                value={hashtagsTexto}
                onChange={(e) => setHashtagsTexto(e.target.value)}
                placeholder="#Chihuahua #Turismo"
              />
              <p className="text-xs text-muted-foreground">
                Separa varios con espacios o comas. Se buscan en el texto de cada publicación.
              </p>
              {hashtags.length > 0 && (
                <div className="flex flex-wrap gap-1.5 pt-1">
                  {hashtags.map((h) => (
                    <Badge key={h} variant="outline">
                      #{h}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {editando ? "Guardar cambios" : "Crear campaña"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
