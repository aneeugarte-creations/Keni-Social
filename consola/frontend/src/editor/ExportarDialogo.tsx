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

import { adaptarDocumento } from "./adaptar";
import { dataUrlABlob } from "./dataUrl";
import { type CapaTexto, conFotoEnHuecosVacios, conTextosHorneados, type Documento, tieneHuecoFotoVacio } from "./documento";
import { PRESETS_FORMATO } from "./formatos";
import { copyMuestra, getFotoMuestraSrc, getObjetoMuestraExport, setObjetoMuestraExport } from "./muestra";
import type { StoreEditor } from "./store";

type Formato = "png" | "jpg";

const ESCALAS: { valor: number; etiqueta: string }[] = [
  { valor: 0.5, etiqueta: "0.5x" },
  { valor: 1, etiqueta: "1x" },
  { valor: 2, etiqueta: "2x" },
];

/** Reparación del nombre de archivo: minúsculas, sin acentos ni símbolos raros; fallback `diseno`. */
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

/**
 * Texto a HORNEAR en una capa de texto para que la descarga muestre lo mismo que el lienzo, o `null`
 * para dejarla como está (el render server-side la pinta por su cuenta). Solo afecta a capas con
 * `binding`: el render usa el valor del binding y, sin pieza, llega vacío (titular sin texto).
 *  - "Copy de muestra" activo: el lienzo enseña el copy de ejemplo -> se hornea ese.
 *  - Hay copy REAL de la pieza para ese binding -> no se hornea (lo pinta el server vía `bindings`).
 *  - Si no, se hornea el `texto` ESCRITO por el equipo. El placeholder genérico de hueco vacío
 *    ("Titular de ejemplo"/"PLECA") NO se hornea: es una pista de edición, no contenido publicable.
 */
function textoHornear(
  c: CapaTexto,
  muestraCopy: boolean,
  bindings: Record<string, string> | undefined,
): string | null {
  if (!c.binding) return null;
  if (muestraCopy) {
    const m = copyMuestra(c.binding);
    return m && m.trim() ? m : null;
  }
  const real = bindings?.[c.binding];
  if (real && real.trim()) return null;
  return (c.texto || "").trim() ? c.texto : null;
}

export function ExportarDialogo({
  store,
  bindings,
  nombre,
  variante = "primario",
  muestraFoto = false,
  muestraCopy = false,
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
  // "Vista con muestra (copy)" activa: si lo está, los titulares/plecas con binding se HORNEAN con el
  // copy de ejemplo al descargar (lo que se ve). El titular ESCRITO se hornea siempre (con o sin él).
  muestraCopy?: boolean;
}) {
  const [abierto, setAbierto] = useState(false);
  const [formato, setFormato] = useState<Formato>("png");
  const [escala, setEscala] = useState(1);
  const [calidad, setCalidad] = useState(90);
  const [exportando, setExportando] = useState(false);
  // Fase visible mientras se exporta (null = inactivo). En el lote incluye el nº de formato en curso.
  const [fase, setFase] = useState<string | null>(null);
  const [ultimaUrl, setUltimaUrl] = useState<string | null>(null);

  // HORNEA lo que se ve en `doc` (foto de muestra en el hueco vacío + texto de titulares/plecas), lo
  // renderiza server-side y descarga el archivo `nombreArchivo`. Devuelve la URL del render (por si la
  // descarga automática la bloquea el navegador). `avisarFase` narra el progreso al usuario.
  const hornearYDescargar = async (
    doc: Documento,
    opciones: OpcionesExport,
    nombreArchivo: string,
    avisarFase: (f: string) => void,
  ): Promise<string> => {
    // WYSIWYG: si la "Vista con muestra (foto)" está activa y el hueco de foto sigue vacío, hornea la
    // foto de muestra en el hueco para que la descarga la incluya (en vez del gris del export).
    let horneado = doc;
    if (muestraFoto && tieneHuecoFotoVacio(horneado)) {
      const objeto = await objetoFotoMuestra();
      if (objeto) horneado = conFotoEnHuecosVacios(horneado, objeto);
    }
    // WYSIWYG (texto): hornea en cada titular/pleca el texto que se ve en el lienzo (escrito por el
    // equipo, o el copy de muestra si ese modo está activo) para que la descarga no salga sin texto.
    horneado = conTextosHorneados(horneado, (c) => textoHornear(c, muestraCopy, bindings));
    avisarFase("Renderizando…");
    const res = await api.imagenRender(horneado, bindings, opciones);
    const url = urlMedia(res.url || res.id);
    avisarFase("Descargando…");
    await descargarArchivo(url, nombreArchivo);
    return url;
  };

  const opcionesActuales = (): OpcionesExport => {
    const o: OpcionesExport = { formato, escala };
    if (formato === "jpg") o.calidad = calidad;
    return o;
  };

  const onDescargar = async () => {
    setExportando(true);
    setFase("Renderizando…");
    try {
      const doc = store.getState().documento;
      const archivo = `${repararNombre(nombre || doc.marca)}.${formato}`;
      const url = await hornearYDescargar(doc, opcionesActuales(), archivo, setFase);
      setUltimaUrl(url);
      toast.success("Imagen descargada.");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setExportando(false);
      setFase(null);
    }
  };

  // LOTE multi-formato: para cada preset (9:16, 4:5, 1:1, 16:9) reencuadra el documento con
  // `adaptarDocumento` (mismas proporciones que «Adaptar a…») y baja un archivo, secuencial (como el
  // carrusel). El sufijo del nombre (`-9x16`…) distingue los archivos en la carpeta de descargas.
  const onDescargarTodos = async () => {
    setExportando(true);
    try {
      const doc = store.getState().documento;
      const base = repararNombre(nombre || doc.marca);
      let ultima: string | null = null;
      for (let i = 0; i < PRESETS_FORMATO.length; i++) {
        const preset = PRESETS_FORMATO[i];
        const prefijoFase = `Formato ${i + 1}/${PRESETS_FORMATO.length} (${preset.etiqueta}) · `;
        setFase(`${prefijoFase}Renderizando…`);
        const adaptado = adaptarDocumento(doc, preset.f);
        const sufijo = preset.etiqueta.replace(":", "x");
        const archivo = `${base}-${sufijo}.${formato}`;
        ultima = await hornearYDescargar(adaptado, opcionesActuales(), archivo, (f) =>
          setFase(`${prefijoFase}${f}`),
        );
      }
      setUltimaUrl(ultima);
      toast.success(`${PRESETS_FORMATO.length} formatos descargados.`);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setExportando(false);
      setFase(null);
    }
  };

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button size="sm" variant={variante === "secundario" ? "outline" : "default"} className="h-8 w-8 px-0" title="Exportar imagen (PNG/JPG)" aria-label="Exportar">
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

          {/* FASE en curso: narra Renderizando…/Descargando… (y el nº de formato en el lote). El
              render puede tardar; el mensaje evita la sensación de cuelgue. */}
          {fase && (
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground" role="status">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {fase} Si tarda, la conexión puede estar lenta; espera o reinténtalo.
            </p>
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

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            onClick={onDescargarTodos}
            disabled={exportando}
            className="w-full sm:w-auto"
            title="Reencuadra el diseño a 9:16, 4:5, 1:1 y 16:9 y descarga cada uno"
          >
            <Download className="mr-1 h-4 w-4" />
            Descargar todos los formatos
          </Button>
          <Button onClick={onDescargar} disabled={exportando} className="w-full sm:w-auto">
            {exportando ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Download className="mr-1 h-4 w-4" />}
            Descargar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
