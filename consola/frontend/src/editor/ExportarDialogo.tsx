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

import { conFotoEnHuecosVacios, type Documento, tieneHuecoFotoVacio } from "./documento";
import { getFotoMuestraSrc, getObjetoMuestraExport, setObjetoMuestraExport } from "./muestra";
import type { StoreEditor } from "./store";

type Formato = "png" | "jpg";

const ESCALAS: { valor: number; etiqueta: string }[] = [
  { valor: 0.5, etiqueta: "0.5x" },
  { valor: 1, etiqueta: "1x" },
  { valor: 2, etiqueta: "2x" },
];

/** Saneo del nombre de archivo: minúsculas, sin acentos ni símbolos raros; fallback `diseno`. */
function repararNombre(nombre: string | undefined): string {
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

/** dataURL (`data:image/png;base64,…`) -> Blob, sin `fetch` (robusto y testeable). */
function dataUrlABlob(dataUrl: string): Blob {
  const coma = dataUrl.indexOf(",");
  const cabecera = dataUrl.slice(5, coma); // tras "data:"
  const datos = dataUrl.slice(coma + 1);
  const mime = cabecera.split(";")[0] || "image/png";
  const esBase64 = /;base64/i.test(cabecera);
  const binario = esBase64 ? atob(datos) : decodeURIComponent(datos);
  const bytes = new Uint8Array(binario.length);
  for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/**
 * Objeto S3 con el que HORNEAR la foto de muestra en la descarga, o `null` si no hay foto real
 * (superficie gris por defecto). La sube una vez (dataURL -> `subirMedia`; URL pegada ->
 * `mediaDesdeUrl`) y CACHEA su objeto en el módulo `muestra` para no resubirla en cada descarga.
 */
async function objetoFotoMuestra(): Promise<string | null> {
  const src = getFotoMuestraSrc().trim();
  if (!src) return null; // sin foto real: el hueco se queda gris (igual que en el lienzo)
  const cacheado = getObjetoMuestraExport();
  if (cacheado) return cacheado;
  let id: string;
  if (src.startsWith("data:")) {
    const blob = dataUrlABlob(src);
    const ext = (blob.type.split("/")[1] || "png").replace("jpeg", "jpg");
    const archivo = new File([blob], `foto-muestra.${ext}`, { type: blob.type || "image/png" });
    id = (await api.subirMedia(archivo, "plantillas")).id;
  } else {
    // URL externa (pegada): el back la descarga al almacén y devuelve su objeto.
    id = (await api.mediaDesdeUrl(src)).id;
  }
  setObjetoMuestraExport(id);
  return id;
}

export function ExportarDialogo({
  store,
  bindings,
  nombre,
  variante = "primario",
  muestraFoto = false,
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
  // "Vista con muestra (foto)" activa: si lo está y hay foto de muestra real, se HORNEA en el hueco
  // de foto vacío al descargar, para que el archivo salga WYSIWYG (la foto que se ve, no el gris).
  muestraFoto?: boolean;
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
      // WYSIWYG: si la "Vista con muestra (foto)" está activa y el hueco de foto sigue vacío, hornea
      // la foto de muestra en el hueco para que la descarga la incluya (en vez del gris del export).
      let doc: Documento = store.getState().documento;
      if (muestraFoto && tieneHuecoFotoVacio(doc)) {
        const objeto = await objetoFotoMuestra();
        if (objeto) doc = conFotoEnHuecosVacios(doc, objeto);
      }
      const res = await api.imagenRender(doc, bindings, opciones);
      const url = urlMedia(res.url || res.id);
      const archivo = `${repararNombre(nombre || doc.marca)}.${formato}`;
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
        <Button size="sm" variant={variante === "secundario" ? "outline" : "default"} className={`h-8 w-8 px-0${variante === "secundario" ? "" : " boton-exportar-cta"}`} title="Exportar imagen (PNG/JPG)" aria-label="Exportar">
          <Download className="h-4 w-4" />
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
