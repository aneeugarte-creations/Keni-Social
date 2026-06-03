/**
 * Editor de imagen INLINE (estilo WhatsApp/GIMP): un `<canvas>` que compone la placa de marca
 * EN EL NAVEGADOR con el MISMO motor que el servidor (`dibujar.mjs`), en vivo a medida que se
 * teclea el titular. Sin round-trips de "aplicar/quitar marca": la composición es local.
 *
 *  - El titular (`copyIn`) se dibuja sobre la placa al instante (debounced).
 *  - Toggle "Con plantilla / Sin plantilla" (QUITAR LA PLANTILLA): "Sin plantilla" oculta la placa
 *    y, al guardar, se publica SOLO la foto cruda (sin placa ni titular encima). La plantilla es
 *    parte del copy-in; quitarla = publicar la imagen tal cual.
 *  - Origen de la FOTO de fondo: Subir · Biblioteca · IA · Usar imagen original (cada uno fija
 *    un media id en `foto`; la pieza recuerda la foto cruda para re-editar al reabrir).
 *  - Al guardar, el padre llama al "bake" (registrado via `registrarBake`): hornea el canvas a
 *    PNG, lo sube a media y devuelve su id, que se fija como `imagen` (lo publicable).
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Crop,
  ImagePlus,
  LayoutTemplate,
  Library,
  Loader2,
  Move,
  Slash,
  Upload,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import { ENCUADRE_DEFECTO, normalizarEncuadre, type EncuadreFoto } from "@/lib/placa/encuadre";
import { cargarFuentesPlaca } from "@/lib/placa/fuentes";
import { dibujarPlaca, formatoPorRed } from "@/lib/placa/render";
import type { CapaTexto, FormatoSpec, PlantillaSpec } from "@/lib/specPlantilla";
import type { Arte } from "@/types";

/**
 * Caja (en px de lienzo) que ocupa la capa del titular, para situar el editor in place encima. La
 * capa de texto NO guarda alto (se ajusta al contenido): lo estimamos por nº de líneas e
 * interlineado. Si la capa está anclada "abajo", `y` es su borde inferior y el bloque crece hacia
 * arriba (espejo de `dibujarTexto`).
 */
function cajaTitularLienzo(c: CapaTexto): { x: number; y: number; w: number; h: number } {
  const interlineado = c.interlineado || 1.14;
  const maxLineas = Math.max(1, c.auto_ajuste?.max_lineas ?? 2);
  const h = Math.round(c.tamano * interlineado * maxLineas);
  const ancla = (c as { ancla?: string }).ancla;
  return { x: c.x, y: ancla === "abajo" ? c.y - h : c.y, w: c.w, h };
}

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
  /** Titular en vivo (texto DENTRO de la imagen / copy-in de la pieza). */
  copyIn: string;
  /** Edita el titular: el copy-in es clicable y reescribible IN PLACE sobre la placa. */
  onCopyInCambio?: (valor: string) => void;
  /** Media id de la FOTO de fondo cruda ("" = sin foto, se muestra el hueco). */
  foto: string;
  /** Notifica un cambio de foto (nuevo media id + url). */
  onCambioFoto: (id: string) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** Estado INICIAL de "quitar plantilla" (la pieza lo persiste). Default: con plantilla. */
  placaOculta?: boolean;
  /** Notifica al padre cuando se quita/pone la plantilla, para persistirlo al guardar. */
  onPlacaOcultaCambio?: (oculta: boolean) => void;
  /** Reencuadre manual actual de la foto dentro del marco 4:5 (null = sin reencuadre = por defecto). */
  encuadre?: EncuadreFoto | null;
  /** Notifica un cambio de reencuadre (arrastre/zoom) para persistirlo al guardar. */
  onEncuadreCambio?: (encuadre: EncuadreFoto) => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
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
  onCopyInCambio,
  foto,
  onCambioFoto,
  imagenFuente,
  placaOculta = false,
  onPlacaOcultaCambio,
  encuadre = null,
  onEncuadreCambio,
  onAbrirGaleria,
  registrarBake,
}: EditorPlacaInlineProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  // "Con plantilla" = mostrar la placa. Arranca desde la elección persistida de la pieza.
  const [mostrarMarca, setMostrarMarca] = React.useState(!placaOculta);
  const alternarPlantilla = () => {
    const nuevoMostrar = !mostrarMarca;
    setMostrarMarca(nuevoMostrar);
    onPlacaOcultaCambio?.(!nuevoMostrar);
  };
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

  // Reencuadre vigente (foco+zoom). `tieneEncuadre` = el humano lo tocó (hay valor persistido o de
  // sesión): solo entonces PISAMOS el foco de diseño de la placa; sin tocar, se respeta el del spec.
  const tieneEncuadre = !!encuadre;
  const enc = encuadre ?? ENCUADRE_DEFECTO;
  // Ref con el encuadre vivo para los handlers de arrastre (evita closures obsoletas entre renders).
  const encRef = React.useRef(enc);
  encRef.current = enc;

  // Edición IN PLACE del titular: la capa de texto del copy-in es clicable sobre la placa. Solo con
  // plantilla de marca (en "sin plantilla" no hay titular) y si el padre permite editarlo.
  const capaTitular = mostrarMarca ? fmt?.textos?.find((t) => t.binding === "copy_in") : undefined;
  const [editandoTitular, setEditandoTitular] = React.useState(false);
  const [cajaTitular, setCajaTitular] = React.useState<
    { left: number; top: number; width: number; height: number } | null
  >(null);
  const titularEditable = !!capaTitular && !!onCopyInCambio;

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
      // Con plantilla: pisamos el encuadre del hueco de foto SOLO si el humano reencuadró, para no
      // alterar el encaje de diseño de las piezas que nadie tocó.
      const formato =
        tieneEncuadre && fmt.foto_slot
          ? { ...fmt, foto_slot: { ...fmt.foto_slot, foco: enc.foco, zoom: enc.zoom } }
          : fmt;
      dibujarPlaca(ctx, {
        formato,
        fuentes: spec.fuentes,
        // Mientras se edita el titular in place, el canvas NO lo dibuja: lo muestra el overlay.
        bindings: { copy_in: editandoTitular ? "" : copyIn, etiqueta_default: "" },
        placeholder: !imgs.foto,
        imgs,
      });
    } else {
      // Capa de marca OCULTA: solo la foto (cover con el reencuadre) o un fondo neutro si no hay foto.
      ctx.fillStyle = "#111315";
      ctx.fillRect(0, 0, w, h);
      if (imgs.foto) {
        const iw = imgs.foto.width;
        const ih = imgs.foto.height;
        const esc = Math.max(w / iw, h / ih) * enc.zoom;
        const dw = iw * esc;
        const dh = ih * esc;
        ctx.drawImage(imgs.foto, (w - dw) * enc.foco[0], (h - dh) * enc.foco[1], dw, dh);
      }
    }
  }, [spec, fmt, copyIn, imgs, mostrarMarca, tieneEncuadre, enc, editandoTitular]);

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

  // --- Reencuadre manual: arrastrar para encuadrar + zoom dentro del marco 4:5 --- //
  // La caja donde vive la foto: el hueco del spec (con plantilla) o el lienzo entero (sin plantilla).
  const cajaFoto = React.useCallback((): { w: number; h: number } => {
    if (mostrarMarca && fmt?.foto_slot) return { w: fmt.foto_slot.w, h: fmt.foto_slot.h };
    if (fmt) return { w: fmt.lienzo.w, h: fmt.lienzo.h };
    return { w: 0, h: 0 };
  }, [mostrarMarca, fmt]);
  const arrastre = React.useRef<{ x: number; y: number } | null>(null);
  const inicioPunt = React.useRef<{ x: number; y: number } | null>(null);
  const arrastrado = React.useRef(false); // ¿hubo movimiento real? (distingue arrastre de clic)

  function onPointerDownFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    if (editandoTitular) return;
    inicioPunt.current = { x: e.clientX, y: e.clientY };
    arrastrado.current = false;
    if (imgs.foto && onEncuadreCambio) {
      arrastre.current = { x: e.clientX, y: e.clientY };
      e.currentTarget.setPointerCapture(e.pointerId);
    }
  }
  function onPointerMoveFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    const inicio = inicioPunt.current;
    if (inicio && Math.hypot(e.clientX - inicio.x, e.clientY - inicio.y) > 4) {
      arrastrado.current = true;
    }
    const ancla = arrastre.current;
    const canvas = canvasRef.current;
    if (!ancla || !imgs.foto || !canvas || !onEncuadreCambio) return;
    const caja = cajaFoto();
    if (!caja.w) return;
    const rect = canvas.getBoundingClientRect();
    const escalaCss = rect.width ? canvas.width / rect.width : 1; // px de lienzo por px de pantalla
    const iw = imgs.foto.width;
    const ih = imgs.foto.height;
    const actual = encRef.current;
    const esc = Math.max(caja.w / iw, caja.h / ih) * actual.zoom;
    const sobranteX = iw * esc - caja.w;
    const sobranteY = ih * esc - caja.h;
    const dxLienzo = (e.clientX - ancla.x) * escalaCss;
    const dyLienzo = (e.clientY - ancla.y) * escalaCss;
    // Arrastrar la foto a la derecha muestra su parte izquierda → el foco DISMINUYE.
    const dFx = sobranteX > 0 ? -dxLienzo / sobranteX : 0;
    const dFy = sobranteY > 0 ? -dyLienzo / sobranteY : 0;
    arrastre.current = { x: e.clientX, y: e.clientY };
    onEncuadreCambio(
      normalizarEncuadre({ foco: [actual.foco[0] + dFx, actual.foco[1] + dFy], zoom: actual.zoom }),
    );
  }
  function onPointerUpFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    const fueArrastre = arrastrado.current;
    arrastre.current = null;
    inicioPunt.current = null;
    arrastrado.current = false;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* el puntero pudo soltarse fuera del canvas */
    }
    // Un CLIC (sin arrastre) sobre la caja del titular abre la edición in place del copy-in.
    if (fueArrastre || !titularEditable || !capaTitular || !fmt) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cx = ((e.clientX - rect.left) / rect.width) * fmt.lienzo.w;
    const cy = ((e.clientY - rect.top) / rect.height) * fmt.lienzo.h;
    const box = cajaTitularLienzo(capaTitular);
    if (cx >= box.x && cx <= box.x + box.w && cy >= box.y && cy <= box.y + box.h) {
      setEditandoTitular(true);
    }
  }
  function onZoom(valor: number) {
    onEncuadreCambio?.(normalizarEncuadre({ foco: encRef.current.foco, zoom: valor }));
  }

  // Caja en pantalla (px CSS) de la capa del titular, para posicionar el editor in place encima.
  const recalcularCajaTitular = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !capaTitular || !fmt) {
      setCajaTitular(null);
      return;
    }
    const sx = canvas.clientWidth / fmt.lienzo.w;
    const sy = canvas.clientHeight / fmt.lienzo.h;
    const box = cajaTitularLienzo(capaTitular);
    setCajaTitular({
      left: box.x * sx,
      top: box.y * sy,
      width: box.w * sx,
      height: box.h * sy,
    });
  }, [capaTitular, fmt]);

  React.useEffect(() => {
    if (!editandoTitular) return;
    recalcularCajaTitular();
    window.addEventListener("resize", recalcularCajaTitular);
    return () => window.removeEventListener("resize", recalcularCajaTitular);
  }, [editandoTitular, recalcularCajaTitular]);

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
          Imagen
        </span>
        {/* Selector nativo de plantilla: quitar plantilla (publicar solo la foto) · elegir plantilla
            del estudio (galería por marca). Todo es 4:5, así que la plantilla la dicta la MARCA. */}
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={mostrarMarca ? "outline" : "secondary"}
            size="icon"
            className="h-7 w-7"
            onClick={alternarPlantilla}
            title={
              mostrarMarca
                ? "Quitar la plantilla: publicar solo la foto, sin placa ni titular encima"
                : "Plantilla quitada: se publica solo la foto. Toca para volver a la placa de marca"
            }
            aria-pressed={!mostrarMarca}
          >
            <span className="relative inline-flex">
              <LayoutTemplate className="h-3.5 w-3.5" />
              <Slash className="absolute inset-0 h-3.5 w-3.5 text-destructive" />
            </span>
          </Button>
          {onAbrirGaleria && (
            <Button
              type="button"
              variant="outline"
              size="icon"
              className="h-7 w-7"
              onClick={onAbrirGaleria}
              title="Elegir una plantilla del estudio (por marca)"
            >
              <LayoutTemplate className="h-3.5 w-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Lienzo en vivo: resolución real, escalado por CSS. Arrastrable para reencuadrar la foto;
          el titular es clicable y reescribible in place. */}
      <div className="flex justify-center rounded-md border border-border bg-muted/20 p-2">
        {specQuery.isPending || !fuentesListas ? (
          <div className="flex h-56 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="relative">
            <canvas
              ref={canvasRef}
              className="max-h-[22rem] w-auto rounded-md"
              style={{
                aspectRatio: fmt ? `${fmt.lienzo.w} / ${fmt.lienzo.h}` : undefined,
                cursor: imgs.foto && onEncuadreCambio ? "move" : "default",
                touchAction: "none",
              }}
              onPointerDown={onPointerDownFoto}
              onPointerMove={onPointerMoveFoto}
              onPointerUp={onPointerUpFoto}
              onPointerCancel={onPointerUpFoto}
            />
            {editandoTitular && cajaTitular && (
              <textarea
                autoFocus
                value={copyIn}
                onChange={(e) => onCopyInCambio?.(e.target.value)}
                onBlur={() => setEditandoTitular(false)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    e.preventDefault();
                    setEditandoTitular(false);
                  }
                }}
                placeholder="Escribe el titular…"
                className="absolute resize-none overflow-hidden rounded-sm bg-black/55 p-1 text-center font-bold uppercase leading-tight text-white shadow-lg outline-none ring-2 ring-primary placeholder:text-white/60"
                style={{
                  left: cajaTitular.left,
                  top: cajaTitular.top,
                  width: cajaTitular.width,
                  height: cajaTitular.height,
                  fontSize: Math.max(11, cajaTitular.height * 0.16),
                }}
              />
            )}
          </div>
        )}
      </div>
      {titularEditable && (
        <p className="text-xs text-muted-foreground">
          Toca el titular sobre la imagen para reescribirlo. No afecta a la foto ni a la plantilla.
        </p>
      )}

      {/* Reencuadre 4:5: arrastra la foto en el lienzo + zoom. Solo si hay foto y se puede persistir. */}
      {imgs.foto && onEncuadreCambio && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Move className="h-3.5 w-3.5" />
            Arrastra la foto para encuadrarla
          </span>
          <span className="flex flex-1 items-center gap-2">
            <Crop className="h-3.5 w-3.5 shrink-0" />
            <input
              type="range"
              min={1}
              max={3}
              step={0.02}
              value={enc.zoom}
              onChange={(e) => onZoom(Number(e.target.value))}
              aria-label="Zoom de la foto"
              className="h-1.5 w-full min-w-[6rem] max-w-[16rem] cursor-pointer accent-primary"
            />
          </span>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs"
            disabled={enc.foco[0] === 0.5 && enc.foco[1] === 0.5 && enc.zoom === 1}
            onClick={() => onEncuadreCambio(ENCUADRE_DEFECTO)}
          >
            Centrar
          </Button>
        </div>
      )}

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
