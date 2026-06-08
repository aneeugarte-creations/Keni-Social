import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Rss } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { desdeMarca, marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import type { FuenteRss, MarcaDisponible, RedPublicacion } from "@/types";

import { CLAVE_FUENTES, CLAVE_ITEMS } from "./lib";

/** Diálogo de alta / edición de un feed. */
export function DialogoFuente({
  abierto,
  fuente,
  marcas,
  redes,
  onCerrar,
}: {
  abierto: boolean;
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onCerrar: () => void;
}) {
  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Rss className="h-5 w-5" />
            {fuente ? "Editar feed" : "Nuevo feed"}
          </DialogTitle>
          <DialogDescription>
            Configura el feed RSS: filtros por palabra clave, redes por defecto al generar y si
            está activo.
          </DialogDescription>
        </DialogHeader>
        {abierto && (
          <FormularioFuente
            fuente={fuente}
            marcas={marcas}
            redes={redes}
            onListo={onCerrar}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Formulario de alta/edición de un feed (dentro del diálogo). */
function FormularioFuente({
  fuente,
  marcas,
  redes,
  onListo,
}: {
  fuente: FuenteRss | null;
  marcas: MarcaDisponible[];
  redes: RedPublicacion[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  // Feed NUEVO: por defecto la marca activa (así nace tagueado y alimenta su radar).
  // Editando: respeta la marca guardada del feed.
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState(fuente?.nombre ?? "");
  const [url, setUrl] = React.useState(fuente?.url ?? "");
  // La marca la fija el switch global (ya no hay selector propio): un feed NUEVO es de la marca
  // activa (o compartido cuando el global está en "Todas"); al EDITAR se conserva la del feed.
  const marca = fuente
    ? desdeMarca(fuente.marca)
    : desdeMarca(marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : undefined);
  const nombreMarcaFuente =
    marcas.find((m) => m.id === marcaParam(marca))?.nombre ?? "Compartida (todas las marcas)";
  const [incluir, setIncluir] = React.useState(fuente?.incluir ?? "");
  const [excluir, setExcluir] = React.useState(fuente?.excluir ?? "");
  const [activo, setActivo] = React.useState(fuente?.activo ?? true);
  const [propia, setPropia] = React.useState(fuente?.propia ?? false);
  const [redesDef, setRedesDef] = React.useState<Set<string>>(
    () => new Set(fuente?.redes_def ?? []),
  );

  const guardar = useMutation({
    mutationFn: () => {
      const marcaVal = marcaParam(marca) ?? "";
      const redesArr = [...redesDef];
      if (fuente) {
        return api.actualizarFuenteRss(fuente.id, {
          nombre: nombre.trim(),
          url: url.trim(),
          marca: marcaVal,
          activo,
          incluir: incluir.trim(),
          excluir: excluir.trim(),
          redes_def: redesArr,
          propia,
        });
      }
      return api.crearFuenteRss({
        nombre: nombre.trim(),
        url: url.trim(),
        marca: marcaVal || undefined,
        incluir: incluir.trim() || undefined,
        excluir: excluir.trim() || undefined,
        redes_def: redesArr.length > 0 ? redesArr : undefined,
        propia: propia || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_FUENTES });
      void queryClient.invalidateQueries({ queryKey: CLAVE_ITEMS });
      toast.success(fuente ? "Feed actualizado" : "Feed añadido");
      onListo();
    },
    // El backend puede devolver 400 si la URL no es válida o por SSRF.
    onError: (e) => toast.error(mensajeError(e)),
  });

  function alternarRed(red: string, marcada: boolean) {
    setRedesDef((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const opcionesRedes = React.useMemo(
    () => redes.map((r) => ({ id: r.id, nombre: r.nombre })),
    [redes],
  );

  const puedeGuardar =
    nombre.trim().length > 0 && url.trim().length > 0 && !guardar.isPending;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="fuente-nombre">Nombre</Label>
        <Input
          id="fuente-nombre"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          placeholder="Ej. UnoTV Deportes"
          maxLength={120}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="fuente-url">URL del feed</Label>
        <Input
          id="fuente-url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ejemplo.com/rss.xml"
          type="url"
          inputMode="url"
        />
      </div>
      <div className="space-y-1.5">
        <Label>Marca</Label>
        <p className="text-sm text-muted-foreground">{nombreMarcaFuente}</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="fuente-incluir">
            Incluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-incluir"
            value={incluir}
            onChange={(e) => setIncluir(e.target.value)}
            placeholder="fútbol, liga"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="fuente-excluir">
            Excluir <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Input
            id="fuente-excluir"
            value={excluir}
            onChange={(e) => setExcluir(e.target.value)}
            placeholder="opinión, podcast"
          />
        </div>
      </div>
      <SelectorRedMultiple
        opciones={opcionesRedes}
        seleccionadas={redesDef}
        onCambio={alternarRed}
      />
      <p className="-mt-1 text-xs text-muted-foreground">
        Redes por defecto al generar copy desde una noticia de este feed.
      </p>
      <div className="flex items-center gap-2">
        <Checkbox
          id="fuente-activo"
          checked={activo}
          onCheckedChange={(v) => setActivo(v)}
          aria-label="Feed activo"
        />
        <Label htmlFor="fuente-activo" className="cursor-pointer font-normal">
          Feed activo
        </Label>
      </div>
      <div className="flex items-start gap-2">
        <Checkbox
          id="fuente-propia"
          checked={propia}
          onCheckedChange={(v) => setPropia(!!v)}
          aria-label="Fuente de marca propia"
          className="mt-0.5"
        />
        <div className="space-y-0.5">
          <Label htmlFor="fuente-propia" className="cursor-pointer font-normal">
            Fuente de marca propia
          </Label>
          <p className="text-xs text-muted-foreground">
            Sitio propio: su imagen original es reutilizable, así que las piezas generadas
            desde sus noticias nacen con la imagen del artículo lista para usarse.
          </p>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={guardar.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          {fuente ? "Guardar cambios" : "Añadir feed"}
        </Button>
      </div>
    </div>
  );
}
