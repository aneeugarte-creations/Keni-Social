/**
 * Diálogo para crear o editar una CAMPAÑA: marcas (multimarca) + nombre + hashtags.
 *
 * Una campaña puede abarcar VARIAS marcas: se eligen con casillas (de las marcas a las que
 * la persona tiene acceso). Los hashtags se escriben separados por espacios o comas y se
 * previsualizan conservando su casing ('#Chihuahua') tal como los guardará el backend.
 *
 * Validación EN LÍNEA (design-system §8): al pulsar Guardar con un campo obligatorio vacío,
 * el error sale bajo ese campo (y le marca el borde), no como toast.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as React from "react";
import { toast } from "sonner";

import { Campo } from "@/components/comunes/Campo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Spinner } from "@/components/ui/spinner";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { Campania } from "@/types";

import { CLAVE_CAMPANIAS } from "./claves";

/**
 * Limpia un texto de hashtags (separados por espacios/comas) a una lista única,
 * CONSERVANDO el casing tal cual se escribió ('#Chihuahua' se guarda '#Chihuahua').
 * La deduplicación es case-insensitive (no repetir '#Chihuahua' y '#chihuahua').
 */
function parsearHashtags(texto: string): string[] {
  const vistos: string[] = [];
  const claves = new Set<string>();
  for (const bruto of texto.split(/[\s,]+/)) {
    const tag = bruto.trim().replace(/^#+/, "");
    const clave = tag.toLowerCase();
    if (tag && !claves.has(clave)) {
      vistos.push(tag);
      claves.add(clave);
    }
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
  campania: Campania | null;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva, marcasParaSwitch } = useMarcaActiva();
  const editando = campania != null;

  const [nombre, setNombre] = React.useState("");
  const [hashtagsTexto, setHashtagsTexto] = React.useState("");
  const [etiquetaWeb, setEtiquetaWeb] = React.useState("");
  const [marcasSel, setMarcasSel] = React.useState<string[]>([]);
  // El error solo se muestra tras un intento de guardar (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  // Al abrir, inicializar el formulario: en edición, con los datos de la campaña; en alta,
  // preseleccionar la marca activa (si hay una concreta) como atajo.
  React.useEffect(() => {
    if (!abierto) return;
    setNombre(campania?.nombre ?? "");
    setHashtagsTexto(campania ? campania.hashtags.map((h) => `#${h}`).join(" ") : "");
    setEtiquetaWeb(campania?.etiqueta_web ?? "");
    setMarcasSel(campania ? campania.marcas : marcaActiva ? [marcaActiva] : []);
    setIntentado(false);
  }, [abierto, campania, marcaActiva]);

  const hashtags = parsearHashtags(hashtagsTexto);

  const alternarMarca = (id: string, marcada: boolean) =>
    setMarcasSel((prev) => (marcada ? [...prev, id] : prev.filter((m) => m !== id)));

  const errNombre = !nombre.trim() ? "El nombre es obligatorio." : null;
  const errMarcas = marcasSel.length === 0 ? "Elige al menos una marca." : null;
  const errHashtags = hashtags.length === 0 ? "Añade al menos un hashtag." : null;
  const hayErrores = Boolean(errNombre || errMarcas || errHashtags);

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo = {
        marcas: marcasSel,
        nombre: nombre.trim(),
        hashtags,
        etiqueta_web: etiquetaWeb.trim(),
      };
      return editando
        ? api.actualizarCampania(campania.id, cuerpo)
        : api.crearCampania(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CAMPANIAS });
      toast.success(editando ? "Campaña actualizada" : "Campaña creada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const onGuardar = () => {
    setIntentado(true);
    if (hayErrores) return;
    guardar.mutate();
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editando ? "Editar campaña" : "Nueva campaña"}</DialogTitle>
          <DialogDescription>
            Agrupa por hashtags las piezas de una o varias marcas.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <Campo
            etiqueta="Nombre"
            htmlFor="campania-nombre"
            error={intentado ? errNombre : null}
          >
            <Input
              id="campania-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Campaña Chihuahua"
              aria-invalid={(intentado && Boolean(errNombre)) || undefined}
              autoFocus
            />
          </Campo>

          <Campo etiqueta="Marcas" error={intentado ? errMarcas : null}>
            <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              {marcasParaSwitch.map((m) => {
                const marcada = marcasSel.includes(m.id);
                return (
                  <Label
                    key={m.id}
                    className="flex cursor-pointer items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                  >
                    <Checkbox
                      checked={marcada}
                      onCheckedChange={(v) => alternarMarca(m.id, v)}
                      aria-label={m.nombre}
                    />
                    <span className="truncate">{m.nombre}</span>
                  </Label>
                );
              })}
            </div>
          </Campo>

          <Campo
            etiqueta="Hashtags"
            htmlFor="campania-hashtags"
            ayuda="Espacios o comas. Se buscan en cada publicación."
            error={intentado ? errHashtags : null}
          >
            <Input
              id="campania-hashtags"
              value={hashtagsTexto}
              onChange={(e) => setHashtagsTexto(e.target.value)}
              placeholder="#Chihuahua #Turismo"
              aria-invalid={(intentado && Boolean(errHashtags)) || undefined}
            />
            {hashtags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {hashtags.map((h) => (
                  <Badge key={h} variant="outline">
                    #{h}
                  </Badge>
                ))}
              </div>
            )}
          </Campo>

          <Campo
            etiqueta="Etiqueta web (URL o slug)"
            htmlFor="campania-etiqueta-web"
            ayuda="Opcional. Pega la URL de la etiqueta del sitio (p. ej. …/etiqueta/w-radio/) o solo el slug para cruzar el tráfico web de las notas en GA4."
          >
            <Input
              id="campania-etiqueta-web"
              value={etiquetaWeb}
              onChange={(e) => setEtiquetaWeb(e.target.value)}
              placeholder="https://…/etiqueta/w-radio/"
            />
          </Campo>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onCerrar}>
            Cancelar
          </Button>
          <Button onClick={onGuardar} disabled={guardar.isPending}>
            {guardar.isPending && <Spinner className="h-4 w-4" />}
            {editando ? "Guardar cambios" : "Crear campaña"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
