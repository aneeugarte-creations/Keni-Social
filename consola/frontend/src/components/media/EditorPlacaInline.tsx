/**
 * Editor de imagen INLINE: un `<canvas>` que compone la PLANTILLA DEL ESTUDIO de la pieza EN EL
 * NAVEGADOR, con el MISMO motor que el servidor (`dibujarDocumento`), en vivo. Sistema ÚNICO de
 * plantillas (la placa de marca legacy se migró a una plantilla del estudio más).
 *
 *  - La plantilla (documento de capas) se renderiza con la foto de la pieza metida en su HUECO DE
 *    FOTO (`es_foto`), el reencuadre aplicado y el copy-in vinculado al titular.
 *  - Cabecera: quitar plantilla (publicar solo la foto cruda) · elegir plantilla del estudio.
 *  - Reencuadre: arrastra la foto + zoom dentro del marco 4:5. Titular: clic para reescribir in place.
 *  - Origen de la FOTO: Subir · Biblioteca · IA · Usar imagen original.
 *  - El canvas es SOLO previa en vivo: al guardar NO se hornea ningún PNG. La pieza guarda su
 *    RECETA (foto + copy_in + plantilla + encuadre) y la imagen publicable se renderiza
 *    on-demand en el servidor (`/api/publicaciones/{id}/compuesta`).
 */
import { useMutation } from "@tanstack/react-query";
import { Crop, ImagePlus, LayoutTemplate, Library, Loader2, Move, Slash, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { CapaTexto, Documento } from "@/editor/documento";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import { dibujarDocumento } from "@/lib/placa/dibujar.mjs";
import { capaFotoDoc, capaTitularDoc, mediaIdsDe, prepararDocumento } from "@/lib/placa/docPieza";
import { ENCUADRE_DEFECTO, normalizarEncuadre, type EncuadreFoto } from "@/lib/placa/encuadre";
import { cargarFuentesPlaca } from "@/lib/placa/fuentes";
import { familiaRealDe } from "@/lib/placa/render";
import type { Arte } from "@/types";

/** Lienzo por defecto del post de foto (4:5) cuando no hay plantilla (foto cruda). */
const LIENZO_4_5 = { w: 1080, h: 1350, safe_top: 0, safe_bottom: 0 };

/**
 * Caja (en px de lienzo) que ocupa la capa del titular, para situar el editor in place encima.
 * Modo CAJA (la capa trae `h>0`): la caja es ESA, fija e inamovible (`[y, y+h]`); el render
 * encoge el texto para caber. Modo LEGADO (`h<=0`, plantillas antiguas sin alto): se estima por
 * nº de líneas × interlineado, y con `ancla:"abajo"` el bloque crece hacia arriba desde `y`.
 */
function cajaTitularLienzo(c: CapaTexto): { x: number; y: number; w: number; h: number } {
  if (c.h > 0) return { x: c.x, y: c.y, w: c.w, h: c.h };
  const interlineado = c.interlineado || 1.14;
  const maxLineas = Math.max(1, c.auto_ajuste?.max_lineas ?? 2);
  const h = Math.round(c.tamano * interlineado * maxLineas);
  return { x: c.x, y: c.ancla === "abajo" ? c.y - h : c.y, w: c.w, h };
}

/** Familias (reales) que usa un documento, para precargar solo esas fuentes. */
function familiasDeDocumento(doc: Documento): string[] {
  const fr = familiaRealDe(doc.fuentes);
  const reales = new Set<string>([doc.fuentes.sans, doc.fuentes.condensada]);
  for (const c of doc.capas) {
    if (c.tipo === "texto") reales.add(fr(c.familia));
    else if (c.tipo === "logo" && c.tipo_logo === "wordmark") reales.add(fr(c.wordmark.familia));
  }
  return [...reales].filter(Boolean);
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

export interface EditorPlacaInlineProps {
  marca: string;
  /** Plantilla del estudio elegida (documento de capas). `null` = sin plantilla = foto cruda. */
  documento: Documento | null;
  /** Titular en vivo (texto DENTRO de la imagen / copy-in de la pieza). */
  copyIn: string;
  /** Edita el titular: el copy-in es clicable y reescribible IN PLACE sobre la plantilla. */
  onCopyInCambio?: (valor: string) => void;
  /** Copy de la pieza (contenido del post): se usa como SUGERENCIA del prompt al generar con IA. */
  copy?: string;
  /** Media id de la FOTO de la pieza ("" = sin foto). */
  foto: string;
  /** Notifica un cambio de foto (nuevo media id). */
  onCambioFoto: (id: string) => void;
  /** URL de la imagen original (RSS de marca propia), si la pieza la trae. */
  imagenFuente?: string;
  /** "Sin plantilla": publicar solo la foto cruda (sin la plantilla encima). */
  sinPlantilla: boolean;
  /** Alterna "sin plantilla" (icono de plantilla tachada). */
  onAlternarSinPlantilla: () => void;
  /** Reencuadre manual actual de la foto dentro del marco 4:5 (null = sin reencuadre). */
  encuadre?: EncuadreFoto | null;
  /** Notifica un cambio de reencuadre (arrastre/zoom). */
  onEncuadreCambio?: (encuadre: EncuadreFoto) => void;
  /** Abre la galería de plantillas del estudio (selector nativo en la cabecera). */
  onAbrirGaleria?: () => void;
}

export function EditorPlacaInline({
  marca,
  documento,
  copyIn,
  onCopyInCambio,
  copy = "",
  foto,
  onCambioFoto,
  imagenFuente,
  sinPlantilla,
  onAlternarSinPlantilla,
  encuadre = null,
  onEncuadreCambio,
  onAbrirGaleria,
}: EditorPlacaInlineProps) {
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  // Opciones de ORIGEN de la foto (Biblioteca / Subir / Generar con IA): se abren al TOCAR la imagen
  // (fuera del titular), no como bloque permanente en el panel de edición.
  const [fuenteAbierta, setFuenteAbierta] = React.useState(false);
  const [prompt, setPrompt] = React.useState("");
  const [avisoGenerar, setAvisoGenerar] = React.useState("");
  const [fuentesListas, setFuentesListas] = React.useState(false);

  // ¿Hay plantilla activa? (documento presente y NO en modo "solo foto").
  const activo = !sinPlantilla && !!documento;
  const lienzo = activo && documento ? documento.formato : LIENZO_4_5;

  // Reencuadre vigente (foco+zoom). `tieneEncuadre` = el humano lo tocó: solo entonces pisamos el
  // encuadre de diseño del hueco; sin tocar, se respeta el de la plantilla.
  const tieneEncuadre = !!encuadre;
  const enc = encuadre ?? ENCUADRE_DEFECTO;
  const encRef = React.useRef(enc);
  encRef.current = enc;

  // Edición IN PLACE del titular: la capa de texto del copy-in (si la plantilla la tiene).
  const capaTitular = activo && documento ? capaTitularDoc(documento) : null;
  const [editandoTitular, setEditandoTitular] = React.useState(false);
  const [cajaTitular, setCajaTitular] = React.useState<
    { left: number; top: number; width: number; height: number } | null
  >(null);
  const titularEditable = !!capaTitular && !!onCopyInCambio;

  // Precarga de fuentes del documento (sin ellas el ajuste de líneas no cuadra). Sin plantilla,
  // no hay texto que dibujar: listo de inmediato.
  React.useEffect(() => {
    if (!activo || !documento) {
      setFuentesListas(true);
      return;
    }
    let vivo = true;
    setFuentesListas(false);
    void cargarFuentesPlaca(familiasDeDocumento(documento)).then(() => {
      if (vivo) setFuentesListas(true);
    });
    return () => {
      vivo = false;
    };
  }, [activo, documento]);

  // Imágenes del documento (logos, fondos, fotos de muestra de otras capas) por media id.
  const [assets, setAssets] = React.useState<Record<string, HTMLImageElement | null>>({});
  React.useEffect(() => {
    if (!activo || !documento) {
      setAssets({});
      return;
    }
    let vivo = true;
    const ids = mediaIdsDe(documento);
    void Promise.all(
      ids.map((id) => cargarImagen(urlMedia(id)).then((img) => [id, img] as const)),
    ).then((pares) => {
      if (vivo) setAssets(Object.fromEntries(pares));
    });
    return () => {
      vivo = false;
    };
  }, [activo, documento]);

  // Foto de la pieza (o la imagen original como respaldo).
  const fotoUrl = foto ? urlMedia(foto) : imagenFuente || "";
  const [fotoImg, setFotoImg] = React.useState<HTMLImageElement | null>(null);
  React.useEffect(() => {
    let vivo = true;
    void cargarImagen(fotoUrl || null).then((img) => {
      if (vivo) setFotoImg(img);
    });
    return () => {
      vivo = false;
    };
  }, [fotoUrl]);

  // --- Render en vivo (debounced) --- //
  const render = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const { w, h } = lienzo;
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, w, h);
    if (activo && documento) {
      const doc = prepararDocumento(documento, { foto, encuadre: tieneEncuadre ? enc : null });
      dibujarDocumento(ctx, {
        documento: doc,
        imgs: { ...assets, [foto]: fotoImg },
        // Mientras se edita el titular in place, el canvas NO lo dibuja: lo muestra el overlay.
        bindings: { copy_in: editandoTitular ? "" : copyIn, etiqueta_default: "" },
        familiaReal: familiaRealDe(documento.fuentes),
      });
    } else {
      // Sin plantilla: solo la foto (cover con el reencuadre) o un fondo neutro si no hay foto.
      ctx.fillStyle = "#111315";
      ctx.fillRect(0, 0, w, h);
      if (fotoImg) {
        const esc = Math.max(w / fotoImg.width, h / fotoImg.height) * enc.zoom;
        const dw = fotoImg.width * esc;
        const dh = fotoImg.height * esc;
        ctx.drawImage(fotoImg, (w - dw) * enc.foco[0], (h - dh) * enc.foco[1], dw, dh);
      }
    }
  }, [activo, documento, lienzo, assets, fotoImg, foto, copyIn, editandoTitular, enc, tieneEncuadre]);

  React.useEffect(() => {
    if (!fuentesListas) return;
    const t = setTimeout(render, 120);
    return () => clearTimeout(t);
  }, [render, fuentesListas]);

  // --- Origen de la FOTO --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (d) => {
      onCambioFoto(d.id);
      setFuenteAbierta(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const usarOriginal = useMutation({
    mutationFn: () => {
      if (!imagenFuente) throw new Error("Sin imagen original.");
      return api.mediaDesdeUrl(imagenFuente);
    },
    onSuccess: (d) => {
      onCambioFoto(d.id);
      setFuenteAbierta(false);
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
        setFuenteAbierta(false);
      }
    } else if (genIA.estado === "error") {
      iaTerminal.current = genIA.id;
      toast.error(genIA.error || "No se pudo generar la imagen.");
    }
  }, [genIA, onCambioFoto]);

  // --- Reencuadre manual: arrastrar para encuadrar + zoom dentro del marco --- //
  // La caja donde vive la foto: el hueco de la plantilla (con plantilla) o el lienzo (sin plantilla).
  const cajaFoto = React.useCallback((): { w: number; h: number } => {
    if (activo && documento) {
      const hueco = capaFotoDoc(documento);
      if (hueco) return { w: hueco.w, h: hueco.h };
    }
    return { w: lienzo.w, h: lienzo.h };
  }, [activo, documento, lienzo]);
  const arrastre = React.useRef<{ x: number; y: number } | null>(null);
  const inicioPunt = React.useRef<{ x: number; y: number } | null>(null);
  const arrastrado = React.useRef(false); // ¿hubo movimiento real? (distingue arrastre de clic)

  function onPointerDownFoto(e: React.PointerEvent<HTMLCanvasElement>) {
    if (editandoTitular) return;
    inicioPunt.current = { x: e.clientX, y: e.clientY };
    arrastrado.current = false;
    if (fotoImg && onEncuadreCambio) {
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
    if (!ancla || !fotoImg || !canvas || !onEncuadreCambio) return;
    const caja = cajaFoto();
    if (!caja.w) return;
    const rect = canvas.getBoundingClientRect();
    const escalaCss = rect.width ? canvas.width / rect.width : 1; // px de lienzo por px de pantalla
    const actual = encRef.current;
    const esc = Math.max(caja.w / fotoImg.width, caja.h / fotoImg.height) * actual.zoom;
    const sobranteX = fotoImg.width * esc - caja.w;
    const sobranteY = fotoImg.height * esc - caja.h;
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
    // Solo nos interesa un CLIC (sin arrastre): el arrastre era reencuadre.
    if (editandoTitular || fueArrastre) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const cx = ((e.clientX - rect.left) / rect.width) * lienzo.w;
    const cy = ((e.clientY - rect.top) / rect.height) * lienzo.h;
    // Clic sobre la caja del TITULAR -> reescribir el copy-in in place.
    if (titularEditable && capaTitular) {
      const box = cajaTitularLienzo(capaTitular);
      if (cx >= box.x && cx <= box.x + box.w && cy >= box.y && cy <= box.y + box.h) {
        setEditandoTitular(true);
        return;
      }
    }
    // Clic en la IMAGEN (fuera del titular) -> opciones de origen de la foto (Biblioteca/Subir/IA).
    abrirFuente();
  }
  function onZoom(valor: number) {
    onEncuadreCambio?.(normalizarEncuadre({ foco: encRef.current.foco, zoom: valor }));
  }

  // Caja en pantalla (px CSS) de la capa del titular, para posicionar el editor in place encima.
  const recalcularCajaTitular = React.useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas || !capaTitular) {
      setCajaTitular(null);
      return;
    }
    const sx = canvas.clientWidth / lienzo.w;
    const sy = canvas.clientHeight / lienzo.h;
    const box = cajaTitularLienzo(capaTitular);
    setCajaTitular({ left: box.x * sx, top: box.y * sy, width: box.w * sx, height: box.h * sy });
  }, [capaTitular, lienzo]);

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
    setFuenteAbierta(false);
  }

  // Abre las opciones de origen de la foto y SIEMBRA el prompt de IA con el copy del post (o el
  // titular), como sugerencia editable, si el prompt está vacío.
  function abrirFuente() {
    setPrompt((p) => (p.trim() ? p : (copy || copyIn || "").trim()));
    setFuenteAbierta(true);
  }

  const ocupado = subir.isPending || generar.isPending || generandoIA || usarOriginal.isPending;
  const hayFoto = !!fotoImg && !!onEncuadreCambio;

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5 text-sm font-medium">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen
          {sinPlantilla && <span className="font-normal text-muted-foreground">· solo foto</span>}
        </span>
        {/* Selector nativo de plantilla: quitar plantilla (publicar solo la foto) · elegir plantilla
            del estudio (galería por marca). Todo es 4:5, así que la plantilla la dicta la MARCA. */}
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={sinPlantilla ? "secondary" : "outline"}
            size="icon"
            className="h-7 w-7"
            onClick={onAlternarSinPlantilla}
            title={
              sinPlantilla
                ? "Solo foto (sin plantilla). Toca para volver a aplicar la plantilla"
                : "Quitar la plantilla: publicar solo la foto, sin nada encima"
            }
            aria-pressed={sinPlantilla}
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
        {!fuentesListas ? (
          <div className="flex h-56 items-center justify-center">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="relative">
            <canvas
              ref={canvasRef}
              className="max-h-[22rem] w-auto rounded-md"
              style={{
                aspectRatio: `${lienzo.w} / ${lienzo.h}`,
                cursor: hayFoto ? "move" : "pointer",
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
      <p className="text-xs text-muted-foreground">
        {titularEditable
          ? "Toca el titular para reescribirlo · toca la imagen para cambiar la foto."
          : "Toca la imagen para añadir o cambiar la foto (biblioteca, subir o generar con IA)."}
      </p>

      {/* Reencuadre 4:5: arrastra la foto en el lienzo + zoom. Solo si hay foto y se puede persistir. */}
      {hayFoto && (
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
            onClick={() => onEncuadreCambio?.(ENCUADRE_DEFECTO)}
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

      {/* Origen de la foto: se abre al TOCAR la imagen (no es un bloque fijo del panel). */}
      <Dialog open={fuenteAbierta} onOpenChange={setFuenteAbierta}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Imagen de la pieza</DialogTitle>
            <DialogDescription>
              Elígela de la biblioteca, súbela o genérala con IA.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
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
                onClick={() => {
                  setFuenteAbierta(false);
                  setGaleriaAbierta(true);
                }}
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
            </div>
            <div className="space-y-1.5">
              <span className="text-xs text-muted-foreground">
                o genera con IA (sugerencia: el copy del post):
              </span>
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
            </div>
            {avisoGenerar && (
              <p className="rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300">
                {avisoGenerar}
              </p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <SelectorArtes
        open={galeriaAbierta}
        onCerrar={() => setGaleriaAbierta(false)}
        onSeleccionar={elegirArte}
        marca={marca}
      />
    </div>
  );
}
