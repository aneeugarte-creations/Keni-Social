/**
 * Editor de imagen INLINE (estilo WhatsApp/GIMP): un `<canvas>` que compone la placa de marca
 * EN EL NAVEGADOR con el MISMO motor que el servidor (`dibujar.mjs`), en vivo a medida que se
 * teclea el titular. Sin round-trips de "aplicar/quitar marca": la composición es local.
 *
 *  - El titular (`copyIn`) se dibuja sobre la placa al instante (debounced).
 *  - Toggle "Mostrar marca" (visibilidad de capa): con la marca oculta se ve sólo la foto.
 *  - Origen de la FOTO de fondo: Subir · Biblioteca · IA · Usar imagen original (cada uno fija
 *    un media id en `foto`; la pieza recuerda la foto cruda para re-editar al reabrir).
 *  - Al guardar, el padre llama al "bake" (registrado via `registrarBake`): hornea el canvas a
 *    PNG, lo sube a media y devuelve su id, que se fija como `imagen` (lo publicable).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Eye, EyeOff, ImagePlus, Library, Loader2, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import { cargarFuentesPlaca } from "@/lib/placa/fuentes";
import { dibujarPlaca, formatoPorRed } from "@/lib/placa/render";
import type { FormatoSpec, PlantillaSpec } from "@/lib/specPlantilla";
import type { Arte } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Carga una URL como `HTMLImageElement` (o null si falla/está vacía). */
function cargarImagen(url: string | null): Promise<HTMLImageElement | null> {
  if (!url) return Promise.resolve(null);
  return new Promise((resolve) => {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => resolve(img);
    img.onerror = () => resolve(null);
    img.src = url;
  });
}

/** Familias (reales) que usa un formato, para precargar solo esas fuentes. */
function familiasDeFormato(spec: PlantillaSpec, fmt: FormatoSpec): string[] {
  const reales = new Set<string>([spec.fuentes.sans, spec.fuentes.condensada]);
  for (const t of fmt.textos) {
    reales.add(t.familia === "sans" ? spec.fuentes.sans : t.familia === "condensada" ? spec.fuentes.condensada : t.familia);
  }
  return [...reales].filter(Boolean);
}

export interface EditorPlacaInlineProps {
  marca: string;
  red: string;
  /** Titular en vivo (campo "Texto en imagen" de la pieza). */
  copyIn: string;
  /** Media id de la FOTO de fondo cruda ("" = sin foto, se muestra el hueco). */
  foto: string;
  /** Notifica un cambio de foto (nuevo media id + url). */
  onCambioFoto: (id: string) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /**
   * Registra (o limpia con null) la función de "bake": el padre la invoca al guardar para
   * hornear el canvas actual a un media id publicable. Devuelve null si no hay nada que hornear.
   */
  registrarBake: (fn: (() => Promise<string | null>) | null) => void;
}

export function EditorPlacaInline({
  marca,
  red,
  copyIn,
  foto,
  onCambioFoto,
  imagenFuente,
  registrarBake,
}: EditorPlacaInlineProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [mostrarMarca, setMostrarMarca] = React.useState(true);
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  const [prompt, setPrompt] = React.useState("");
  const [avisoGenerar, setAvisoGenerar] = React.useState("");
  const [fuentesListas, setFuentesListas] = React.useState(false);

  const specQuery = useQuery({
    queryKey: ["plantilla-spec", marca],
    queryFn: ({ signal }) => api.specPlantilla(marca, signal),
    enabled: !!marca,
  });
  const spec = specQuery.data?.spec;
  const formatoNombre = formatoPorRed(red);
  const fmt = spec?.formatos[formatoNombre];

  // Precarga de fuentes (una vez por formato): sin ellas el ajuste de líneas no cuadra.
  React.useEffect(() => {
    if (!spec || !fmt) return;
    let vivo = true;
    void cargarFuentesPlaca(familiasDeFormato(spec, fmt)).then(() => {
      if (vivo) setFuentesListas(true);
    });
    return () => {
      vivo = false;
    };
  }, [spec, fmt]);

  // Imágenes (foto/logo/fondo) cargadas como Image. Se recargan al cambiar sus fuentes.
  const [imgs, setImgs] = React.useState<{
    foto: HTMLImageElement | null;
    logo: HTMLImageElement | null;
    fondo: HTMLImageElement | null;
  }>({ foto: null, logo: null, fondo: null });

  const logoId = fmt?.logo?.media_id || "";
  const fondoId = fmt?.fondo?.tipo === "imagen" ? fmt.fondo.imagen?.media_id || "" : "";
  const fotoUrl = foto ? urlMedia(foto) : imagenFuente || "";

  React.useEffect(() => {
    let vivo = true;
    void Promise.all([
      cargarImagen(fotoUrl || null),
      cargarImagen(logoId ? urlMedia(logoId) : null),
      cargarImagen(fondoId ? urlMedia(fondoId) : null),
    ]).then(([f, l, fo]) => {
      if (vivo) setImgs({ foto: f, logo: l, fondo: fo });
    });
    return () => {
      vivo = false;
    };
  }, [fotoUrl, logoId, fondoId]);

  // --- Render en vivo (debounced) --- //
  const render = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !spec || !fmt) return;
    const { w, h } = fmt.lienzo;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    if (mostrarMarca) {
      dibujarPlaca(ctx, {
        formato: fmt,
        fuentes: spec.fuentes,
        bindings: { copy_in: copyIn, etiqueta_default: "" },
        placeholder: !imgs.foto,
        imgs,
      });
    } else {
      // Capa de marca OCULTA: solo la foto (cover) o un fondo neutro si no hay foto.
      ctx.fillStyle = "#111315";
      ctx.fillRect(0, 0, w, h);
      if (imgs.foto) {
        const iw = imgs.foto.width;
        const ih = imgs.foto.height;
        const esc = Math.max(w / iw, h / ih);
        const dw = iw * esc;
        const dh = ih * esc;
        ctx.drawImage(imgs.foto, (w - dw) / 2, (h - dh) / 2, dw, dh);
      }
    }
  }, [spec, fmt, copyIn, imgs, mostrarMarca]);

  React.useEffect(() => {
    if (!fuentesListas) return;
    const t = setTimeout(render, 120);
    return () => clearTimeout(t);
  }, [render, fuentesListas]);

  // --- Bake: hornea el canvas a un media id (lo llama el padre al guardar) --- //
  React.useEffect(() => {
    if (!spec || !fmt) {
      registrarBake(null);
      return;
    }
    const bake = async (): Promise<string | null> => {
      const canvas = canvasRef.current;
      if (!canvas) return null;
      // Asegura un render final con el copy_in vigente antes de hornear.
      render();
      const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/png"));
      if (!blob) return null;
      const file = new File([blob], "placa.png", { type: "image/png" });
      const subida = await api.subirMedia(file);
      return subida.id;
    };
    registrarBake(bake);
    return () => registrarBake(null);
  }, [spec, fmt, render, registrarBake]);

  // --- Origen de la FOTO de fondo --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) => onCambioFoto(d.id),
    onError: (e) => toast.error(mensajeError(e)),
  });
  const usarOriginal = useMutation({
    mutationFn: () => {
      if (!imagenFuente) throw new Error("Sin imagen original.");
      return api.mediaDesdeUrl(imagenFuente);
    },
    onSuccess: (d) => {
      onCambioFoto(d.id);
      toast.success("Imagen original cargada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const { generacion: genIA, ejecutando: generandoIA, iniciar: iniciarIA } = useGeneracion();
  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim() }),
    onSuccess: (d) => {
      setAvisoGenerar("");
      iniciarIA(d.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setAvisoGenerar(e.message);
        return;
      }
      toast.error(mensajeError(e));
    },
  });
  const iaTerminal = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!genIA || genIA.id === iaTerminal.current) return;
    if (genIA.estado === "completado") {
      iaTerminal.current = genIA.id;
      const r = genIA.resultado;
      if (r?.id) {
        setPrompt("");
        onCambioFoto(r.id);
      }
    } else if (genIA.estado === "error") {
      iaTerminal.current = genIA.id;
      toast.error(genIA.error || "No se pudo generar la imagen.");
    }
  }, [genIA, onCambioFoto]);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    if (inputRef.current) inputRef.current.value = "";
  }
  function elegirArte(arte: Arte) {
    onCambioFoto(arte.objeto);
  }

  const ocupado = subir.isPending || generar.isPending || generandoIA || usarOriginal.isPending;

  if (specQuery.isError) {
    // Marca sin plantilla utilizable: el padre debería usar el editor de foto cruda. Por si acaso,
    // avisamos en vez de romper.
    return (
      <p className="text-sm text-muted-foreground">
        Esta marca no tiene una placa de imagen configurada.
      </p>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen <span className="font-normal text-muted-foreground">· se compone en vivo</span>
        </span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 px-2 text-xs"
          onClick={() => setMostrarMarca((v) => !v)}
        >
          {mostrarMarca ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
          {mostrarMarca ? "Marca visible" : "Marca oculta"}
        </Button>
      </div>

      {/* Lienzo en vivo: resolución real, escalado por CSS. */}
      <div className="flex justify-center rounded-md border border-border bg-muted/20 p-2">
        {specQuery.isPending || !fuentesListas ? (
          <div className="flex h-56 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            className="max-h-[22rem] w-auto rounded-md"
            style={{ aspectRatio: fmt ? `${fmt.lienzo.w} / ${fmt.lienzo.h}` : undefined }}
          />
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        onChange={onArchivo}
        className="hidden"
        aria-label="Adjuntar imagen"
      />

      {/* Origen de la foto de fondo. */}
      <div className="space-y-2 rounded-md border border-dashed border-border bg-muted/20 p-3">
        <div className="flex flex-wrap items-center gap-2">
          {imagenFuente && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => usarOriginal.mutate()}
              disabled={ocupado}
            >
              {usarOriginal.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ImagePlus className="h-4 w-4" />
              )}
              Usar imagen original
            </Button>
          )}
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setGaleriaAbierta(true)}
            disabled={ocupado}
          >
            <Library className="h-4 w-4" />
            Biblioteca
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => inputRef.current?.click()}
            disabled={ocupado}
          >
            {subir.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
            Subir
          </Button>
          <span className="text-xs text-muted-foreground">o genera con IA:</span>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer…"
            disabled={ocupado}
            onKeyDown={(e) => {
              if (e.key === "Enter" && prompt.trim() && !ocupado) {
                e.preventDefault();
                generar.mutate();
              }
            }}
          />
          <Button
            type="button"
            size="sm"
            onClick={() => generar.mutate()}
            disabled={ocupado || prompt.trim().length === 0}
            className="shrink-0"
          >
            {generandoIA ? <Loader2 className="h-4 w-4 animate-spin" /> : <MarcaIA costo />}
            {generandoIA ? "Generando…" : "Generar con IA"}
          </Button>
        </div>
        {avisoGenerar && (
          <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300">
            {avisoGenerar}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          El titular y la placa de marca se dibujan encima automáticamente, en vivo.
        </p>
      </div>

      <SelectorArtes
        open={galeriaAbierta}
        onCerrar={() => setGaleriaAbierta(false)}
        onSeleccionar={elegirArte}
        marca={marca}
      />
    </div>
  );
}
