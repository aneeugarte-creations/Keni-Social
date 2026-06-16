// Diálogo para asignar la FOTO DE MUESTRA de una plantilla DESDE la galería (sin abrir el editor):
// la otra puerta al mismo `foto_muestra` que el fotón del editor. Recoge una foto (subida o URL) y
// la entrega al llamante, que la sube al almacén, la hornea en la miniatura/preview y la persiste en
// la plantilla. La muestra se ve en la galería «tal cual quedaría», NO en el lienzo del editor (ahí
// solo aparece con el fotón activo). El render condicional con `key={plantilla.id}` reinicia el
// estado al cambiar de plantilla.

import { RotateCcw, Upload } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { urlMedia, type PlantillaDiseno } from "@/lib/api";

export function DialogoFotoMuestra({
  plantilla,
  aplicando,
  onCerrar,
  onAplicar,
}: {
  plantilla: PlantillaDiseno;
  aplicando: boolean;
  onCerrar: () => void;
  // `src`: dataURL (foto subida) o URL (pegada). `""` quita la muestra (vuelve a huecos grises).
  onAplicar: (src: string) => void;
}) {
  // Foto elegida en este diálogo (null = aún no se ha tocado; se ve la muestra actual de la plantilla).
  const [src, setSrc] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const actual = plantilla.foto_muestra ? urlMedia(plantilla.foto_muestra) : "";
  const preview = src ?? actual;

  const onArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setSrc(reader.result);
    };
    reader.readAsDataURL(file);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Foto de muestra</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <p className="text-xs leading-snug text-muted-foreground">
            Una foto representativa de «{plantilla.nombre || "esta plantilla"}» para que la galería se
            vea tal cual quedaría. No se mete en el documento: en el editor el hueco sigue vacío (la
            muestra solo aparece con el fotón activo).
          </p>

          <div className="aspect-[4/5] w-full overflow-hidden rounded border border-border bg-muted/40">
            {preview ? (
              <img src={preview} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-tr from-zinc-400 to-zinc-700 text-xs text-white/80">
                Sin muestra (huecos grises)
              </div>
            )}
          </div>

          <input ref={fileRef} type="file" accept="image/*" onChange={onArchivo} className="hidden" />
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="flex flex-1 items-center justify-center gap-1 rounded border border-input bg-background px-2 py-1.5 text-xs hover:bg-accent"
            >
              <Upload className="h-3.5 w-3.5" /> Subir foto
            </button>
            <button
              type="button"
              onClick={() => setSrc("")}
              disabled={!preview}
              title="Quitar la muestra (la galería vuelve a los huecos grises)"
              className="flex items-center justify-center gap-1 rounded border border-input bg-background px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-40"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Quitar
            </button>
          </div>
          <input
            type="url"
            placeholder="…o pega una URL de imagen"
            defaultValue={/^https?:/.test(src ?? "") ? (src ?? "") : ""}
            onChange={(e) => setSrc(e.target.value.trim() || null)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={aplicando}>
            Cancelar
          </Button>
          <Button
            // `src === null` => no se tocó nada; nada que aplicar.
            disabled={src === null || aplicando}
            onClick={() => src !== null && onAplicar(src)}
          >
            {aplicando ? "Guardando…" : "Aplicar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
