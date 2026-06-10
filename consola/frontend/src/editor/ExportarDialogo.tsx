// Diálogo compacto de EXPORTACIÓN del editor: elige formato (PNG/JPG), escala (0.5x/1x/2x) y, si es
// JPG, la calidad; al confirmar renderiza en el servidor y DESCARGA el archivo directamente (fetch →
// blob → <a download> programático; sin `window.open`, que los bloqueadores de popups frenan).
//
// El diálogo recibe el `store` del editor y llama al API por sí mismo (el documento sale del store
// vigente). Mantiene visible el enlace al último archivo generado por si la descarga automática
// falla (p. ej. el navegador la bloquea).

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { api, mensajeError, urlMedia } from "@/lib/api";
import { cabecerasAuth } from "@/lib/api/_core";
import type { OpcionesExport } from "@/lib/api/imagen";

import type { StoreEditor } from "./store";

type Formato = "png" | "jpg";

const ESCALAS: { valor: number; etiqueta: string }[] = [
  { valor: 0.5, etiqueta: "0.5x" },
  { valor: 1, etiqueta: "1x" },
  { valor: 2, etiqueta: "2x" },
];

/** Saneo del nombre de archivo: minúsculas, sin acentos ni símbolos raros; fallback `diseno`. */
function sanearNombre(nombre: string | undefined): string {
  const base = (nombre || "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
  return base || "diseno";
}

/** Descarga `url` como archivo `nombreArchivo` (fetch con auth → blob → <a download> programático). */
async function descargarArchivo(url: string, nombreArchivo: string): Promise<void> {
  const res = await fetch(url, { headers: cabecerasAuth() });
  if (!res.ok) throw new Error("No se pudo descargar la imagen generada.");
  const blob = await res.blob();
  const objUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = nombreArchivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(objUrl);
}

export function ExportarDialogo({
  store,
  bindings,
  nombre,
  variante = "primario",
}: {
  store: StoreEditor;
  // Titular/pleca REAL de la pieza (cuando la pestaña está anclada a una publicación). Sin pieza
  // no se pasan y las capas con `binding` renderizan el texto de muestra.
  bindings?: Record<string, string>;
  // Nombre de la plantilla/pieza (si existe) para el archivo descargado.
  nombre?: string;
  // Jerarquía del botón disparador: "primario" (acción principal del editor) u "outline" cuando la
  // acción primaria del contexto es otra (p. ej. «Guardar en pieza»).
  variante?: "primario" | "secundario";
}) {
  const [abierto, setAbierto] = useState(false);
  const [formato, setFormato] = useState<Formato>("png");
  const [escala, setEscala] = useState(1);
  const [calidad, setCalidad] = useState(90);
  const [exportando, setExportando] = useState(false);
  const [ultimaUrl, setUltimaUrl] = useState<string | null>(null);

  const onDescargar = async () => {
    setExportando(true);
    try {
      const opciones: OpcionesExport = { formato, escala };
      if (formato === "jpg") opciones.calidad = calidad;
      const res = await api.imagenRender(store.getState().documento, bindings, opciones);
      const url = urlMedia(res.url || res.id);
      const archivo = `${sanearNombre(nombre || store.getState().documento.marca)}.${formato}`;
      await descargarArchivo(url, archivo);
      setUltimaUrl(url);
      toast.success("Imagen descargada.");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setExportando(false);
    }
  };

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button size="sm" variant={variante === "secundario" ? "outline" : "default"} className="ml-1 h-8" title="Exportar imagen (PNG/JPG)">
          <Download className="h-4 w-4 sm:mr-1" />
          <span className="hidden sm:inline">Exportar</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Exportar imagen</DialogTitle>
          <DialogDescription>Elige el formato y la resolución y descárgala.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* FORMATO */}
          <div className="space-y-1.5">
            <Label>Formato</Label>
            <div className="grid grid-cols-2 gap-2">
              {(["png", "jpg"] as Formato[]).map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setFormato(f)}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    formato === f
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {f.toUpperCase()}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-muted-foreground">
              {formato === "png"
                ? "PNG: sin pérdida, admite transparencia (más pesado)."
                : "JPG: más ligero, sin transparencia."}
            </p>
          </div>

          {/* ESCALA */}
          <div className="space-y-1.5">
            <Label>Escala</Label>
            <div className="grid grid-cols-3 gap-2">
              {ESCALAS.map((e) => (
                <button
                  key={e.valor}
                  type="button"
                  onClick={() => setEscala(e.valor)}
                  className={`rounded-md border px-3 py-1.5 text-sm font-medium transition-colors ${
                    escala === e.valor
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {e.etiqueta}
                </button>
              ))}
            </div>
          </div>

          {/* CALIDAD (solo JPG) */}
          {formato === "jpg" && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="export-calidad">Calidad</Label>
                <span className="text-sm tabular-nums text-muted-foreground">{calidad}</span>
              </div>
              <input
                id="export-calidad"
                type="range"
                min={1}
                max={100}
                step={1}
                value={calidad}
                onChange={(ev) => setCalidad(Number(ev.target.value))}
                className="w-full accent-primary"
              />
            </div>
          )}

          {ultimaUrl && (
            <p className="text-[11px] text-muted-foreground">
              Si la descarga no empezó,{" "}
              <a href={ultimaUrl} target="_blank" rel="noreferrer" className="text-primary underline">
                ábrela aquí
              </a>
              .
            </p>
          )}
        </div>

        <DialogFooter>
          <Button onClick={onDescargar} disabled={exportando} className="w-full sm:w-auto">
            {exportando ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />}
            Descargar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
