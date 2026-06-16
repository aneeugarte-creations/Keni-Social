// Diálogo para configurar la MUESTRA de una plantilla DESDE la galería (sin abrir el editor): foto +
// texto (titular y subtítulo/pleca). Es la otra puerta a los mismos campos que el fotón del editor.
// La muestra se ve en el OVERVIEW de la galería «tal cual quedaría», NO en el lienzo del editor (ahí
// la foto solo aparece con el fotón activo y el texto sale del binding real). El llamante sube la foto
// al almacén, hornea todo en la miniatura y persiste en la plantilla. `key={plantilla.id}` reinicia el
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
  // `foto`: dataURL (subida) o URL (pegada); `""` la quita; `null` = no se tocó (se conserva).
  // `titular`/`etiqueta`: texto de muestra ("" = fallback: "TITULAR" / el literal de la pleca).
  onAplicar: (vals: { foto: string | null; titular: string; etiqueta: string }) => void;
}) {
  // Foto elegida (null = sin tocar → se conserva la actual). Texto: arranca con el de la plantilla.
  const [foto, setFoto] = useState<string | null>(null);
  const [titular, setTitular] = useState(plantilla.titular_muestra);
  const [etiqueta, setEtiqueta] = useState(plantilla.etiqueta_muestra);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const actual = plantilla.foto_muestra ? urlMedia(plantilla.foto_muestra) : "";
  const preview = foto ?? actual;

  const onArchivo = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setFoto(reader.result);
    };
    reader.readAsDataURL(file);
  };

  return (
    <Dialog open onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Foto y texto de muestra</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <p className="text-xs leading-snug text-muted-foreground">
            Foto, titular y subtítulo representativos de «{plantilla.nombre || "esta plantilla"}» para
            que la galería se vea tal cual quedaría. No se meten en el documento: en el editor el hueco
            sigue vacío y el texto sale del contenido real.
          </p>

          <div className="aspect-[4/5] w-full overflow-hidden rounded border border-border bg-muted/40">
            {preview ? (
              <img src={preview} alt="" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center bg-gradient-to-tr from-zinc-400 to-zinc-700 text-xs text-white/80">
                Sin foto (huecos grises)
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
              onClick={() => setFoto("")}
              disabled={!preview}
              title="Quitar la foto (la galería vuelve a los huecos grises)"
              className="flex items-center justify-center gap-1 rounded border border-input bg-background px-2 py-1.5 text-xs hover:bg-accent disabled:opacity-40"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Quitar foto
            </button>
          </div>
          <input
            type="url"
            placeholder="…o pega una URL de imagen"
            defaultValue={/^https?:/.test(foto ?? "") ? (foto ?? "") : ""}
            onChange={(e) => setFoto(e.target.value.trim() || null)}
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />

          <label className="text-[11px] font-medium text-muted-foreground">Titular de muestra</label>
          <input
            value={titular}
            onChange={(e) => setTitular(e.target.value)}
            placeholder="TITULAR"
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
          <label className="text-[11px] font-medium text-muted-foreground">Subtítulo / pleca de muestra</label>
          <input
            value={etiqueta}
            onChange={(e) => setEtiqueta(e.target.value)}
            placeholder="(vacío: usa el texto de la plantilla)"
            className="rounded border border-input bg-background px-2 py-1 text-xs"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={aplicando}>
            Cancelar
          </Button>
          <Button disabled={aplicando} onClick={() => onAplicar({ foto, titular, etiqueta })}>
            {aplicando ? "Guardando…" : "Aplicar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
