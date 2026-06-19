/**
 * Editor de carrusel LATERAL: el MISMO editor de placa de la portada (`EditorPlacaInline`)
 * pero PAGINADO de lado, un slide a la vez —como el slideshow del feed, pero editable—.
 *
 * Cada página es un slide: la PORTADA (índice 0) y los slides EXTRA detrás. En cada uno se
 * edita lo de siempre: foto (toca el hueco), titular (toca el texto), plantilla (galería) y
 * "sin placa". La descripción (copy del post) NO vive aquí: va debajo, en el editor de pieza.
 *
 * Persistencia:
 *  - Portada (índice 0): edita el estado de la pieza (fotos/copy_in/plantilla/placa_oculta) vía
 *    callbacks del padre; se sirve on-demand desde la receta (no se hornea aquí).
 *  - Slides extra: editan su PROCEDENCIA dentro de `slides[]`; el `objeto` publicable se RE-HORNEA
 *    (servidor, `componerSlide`) de forma DEBOUNCED al cambiar la receta. La previa es el lienzo en
 *    vivo (instantáneo); el horneado solo refresca el media que se publica.
 */
import { ChevronLeft, ChevronRight, Download, Plus, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import type { Documento } from "@/editor/documento";
import { api, mensajeError, urlMedia, type PlantillaDiseno } from "@/lib/api";
import { slidePlacaEditable, type SlideCarrusel } from "@/lib/carrusel";
import { descargarUrlConAuth, ofrecerCopiarCopy, slugNombre } from "@/lib/descargas";
import type { FotoCollage } from "@/lib/placa/docPieza";
import { parsearEncuadre, serializarEncuadre } from "@/lib/placa/encuadre";
import { cn } from "@/lib/utils";

const RETARDO_HORNEADO_MS = 1200;

export function EditorCarruselLateral({
  marca,
  piezaId,
  plantillas,
  copy = "",
  imagenFuente,
  portadaFotos,
  onPortadaFotos,
  portadaCopyIn,
  onPortadaCopyIn,
  portadaPlantillaId,
  onPortadaPlantillaId,
  portadaPlacaOculta,
  onPortadaPlacaOculta,
  slides,
  onSlides,
  disabled = false,
  onGuardarPortada,
}: {
  marca: string;
  piezaId: string;
  plantillas: PlantillaDiseno[];
  /** Copy del post: sugerencia del prompt al generar foto con IA. */
  copy?: string;
  /** Imagen original (RSS) de respaldo del hueco 0 de la PORTADA. */
  imagenFuente?: string;
  // PORTADA (slide 0): estado del padre, persistido por su autoguardado.
  portadaFotos: FotoCollage[];
  onPortadaFotos: (f: FotoCollage[]) => void;
  portadaCopyIn: string;
  onPortadaCopyIn: (s: string) => void;
  portadaPlantillaId: string;
  onPortadaPlantillaId: (id: string) => void;
  portadaPlacaOculta: boolean;
  onPortadaPlacaOculta: (v: boolean) => void;
  // SLIDES EXTRA (detrás de la portada).
  slides: SlideCarrusel[];
  onSlides: (s: SlideCarrusel[]) => void;
  disabled?: boolean;
  /** Fuerza el guardado de la pieza (la portada se sirve del estado GUARDADO): se llama antes de
   *  descargar para que `/compuesta` no devuelva un render anterior a la última edición. */
  onGuardarPortada?: () => Promise<void>;
}) {
  const total = slides.length + 1;
  const [activo, setActivo] = React.useState(0);
  const [galeria, setGaleria] = React.useState(false);
  const [horneando, setHorneando] = React.useState<number | null>(null);
  const [descargando, setDescargando] = React.useState(false);

  // El índice activo nunca debe salirse de rango (al quitar el último slide).
  React.useEffect(() => {
    if (activo > total - 1) setActivo(total - 1);
  }, [activo, total]);

  // --- Horneado DEBOUNCED de los slides extra --- //
  const slidesRef = React.useRef(slides);
  slidesRef.current = slides;
  const temporizadores = React.useRef<Map<number, number>>(new Map());

  const hornear = React.useCallback(
    async (i: number) => {
      const s = slidesRef.current[i];
      // Sin foto NI titular no hay placa que hornear (componer-slide daría 400): se deja como está.
      if (!s || !slidePlacaEditable(s)) return;
      setHorneando(i);
      try {
        const resp = await api.componerSlide(piezaId, {
          foto: s.foto ?? "",
          titular: s.titular ?? "",
          plantilla_id: s.sinPlaca ? "" : s.plantillaId ?? "",
          foto_encuadre: s.fotoEncuadre ?? "",
          sin_plantilla: s.sinPlaca ?? false,
        });
        // Fija el media horneado SIN tocar la receta (no reprograma otro horneado).
        onSlides(slidesRef.current.map((x, k) => (k === i ? { ...x, objeto: resp.id } : x)));
      } catch (e) {
        toast.error(mensajeError(e));
      } finally {
        setHorneando((h) => (h === i ? null : h));
      }
    },
    [piezaId, onSlides],
  );

  const programarHornear = React.useCallback(
    (i: number) => {
      const prev = temporizadores.current.get(i);
      if (prev) window.clearTimeout(prev);
      const t = window.setTimeout(() => {
        temporizadores.current.delete(i);
        void hornear(i);
      }, RETARDO_HORNEADO_MS);
      temporizadores.current.set(i, t);
    },
    [hornear],
  );

  // Al DESMONTAR (solo), dispara los horneados pendientes (best-effort) para no perder ediciones.
  // Vía ref para no re-suscribir el efecto en cada render (si no, un `hornear` inestable flush-earía
  // el debounce en cada render).
  const hornearRef = React.useRef(hornear);
  hornearRef.current = hornear;
  React.useEffect(() => {
    const timers = temporizadores.current;
    return () => {
      for (const [i, t] of timers) {
        window.clearTimeout(t);
        void hornearRef.current(i);
      }
      timers.clear();
    };
  }, []);

  // Parchea la receta de un slide extra `i` (índice en `slides`) y reprograma su horneado.
  const editarExtra = React.useCallback(
    (i: number, parche: Partial<SlideCarrusel>) => {
      onSlides(slidesRef.current.map((s, k) => (k === i ? { ...s, ...parche } : s)));
      programarHornear(i);
    },
    [onSlides, programarHornear],
  );

  // --- Plantilla efectiva por slide --- //
  const idPlacaDeMarca =
    plantillas.find((p) => p.nombre === "Placa de marca")?.id ?? plantillas[0]?.id ?? "";
  const documentoDe = React.useCallback(
    (plantillaId: string, sin: boolean): Documento | null => {
      if (sin) return null;
      const id = plantillaId || idPlacaDeMarca;
      const p = plantillas.find((x) => x.id === id);
      return (p?.documento as Documento | undefined) ?? null;
    },
    [plantillas, idPlacaDeMarca],
  );

  // Elegir plantilla de la galería: aplica al slide ACTIVO (portada o extra).
  const elegirPlantilla = (p: PlantillaDiseno) => {
    if (activo === 0) {
      onPortadaPlantillaId(p.id);
      onPortadaPlacaOculta(false);
    } else {
      editarExtra(activo - 1, { plantillaId: p.id, sinPlaca: false });
    }
    setGaleria(false);
  };

  // --- Gestión de slides extra --- //
  const anadirSlide = () => {
    onSlides([...slidesRef.current, { tipo: "imagen", objeto: "", titular: "" }]);
    setActivo(total); // navega al nuevo (índice = longitud previa + 1 = total actual)
  };
  const quitarActivo = () => {
    if (activo === 0) return; // la portada no se quita
    const i = activo - 1;
    const prev = temporizadores.current.get(i);
    if (prev) window.clearTimeout(prev);
    temporizadores.current.delete(i);
    onSlides(slidesRef.current.filter((_, k) => k !== i));
    setActivo((a) => Math.max(0, a - 1));
  };
  const moverActivo = (delta: -1 | 1) => {
    if (activo === 0) return; // la portada va fija en el frente
    const i = activo - 1;
    const j = i + delta;
    if (j < 0 || j >= slidesRef.current.length) return;
    const copia = [...slidesRef.current];
    [copia[i], copia[j]] = [copia[j], copia[i]];
    onSlides(copia);
    setActivo(j + 1);
  };

  const ir = (delta: -1 | 1) => setActivo((a) => Math.min(total - 1, Math.max(0, a + delta)));

  // Descarga el carrusel ENTERO como archivos sueltos (uno por slide, en orden), para postear a mano
  // donde Metricool no llega. Cada slide se descarga en su forma PUBLICABLE:
  //  - Portada: composite on-demand del servidor (`/compuesta`, refleja la receta guardada).
  //  - Slide extra de imagen: se RE-HORNEA con su receta actual (sin depender del debounce) y se baja.
  //  - Slide extra de video: su media de video tal cual.
  // Al terminar, ofrece copiar el copy del post al portapapeles.
  const descargarCarrusel = React.useCallback(async () => {
    setDescargando(true);
    const base = slugNombre(marca);
    try {
      // La portada se sirve del estado GUARDADO: fuerza el guardado primero para que `/compuesta`
      // refleje la última edición (no la versión anterior al autoguardado debounced). Best-effort:
      // si falla, la autosave previa suele bastar, así que seguimos con la descarga igualmente.
      if (onGuardarPortada) {
        try {
          await onGuardarPortada();
        } catch {
          /* la autosave previa suele cubrirlo; no abortamos la descarga */
        }
      }
      // Portada (archivo 1). Cache-bust para no reusar un render viejo del navegador.
      await descargarUrlConAuth(`/api/piezas/${piezaId}/compuesta?d=${Date.now()}`, `${base}-1`);
      // Slides extra (archivos 2..N): re-hornea imágenes, baja el video tal cual.
      const lista = slidesRef.current;
      for (let i = 0; i < lista.length; i++) {
        const s = lista[i];
        const nombre = `${base}-${i + 2}`;
        if (s.tipo === "video") {
          if (s.objeto) await descargarUrlConAuth(urlMedia(s.objeto), nombre, "mp4");
          continue;
        }
        let id = s.objeto ?? "";
        if (slidePlacaEditable(s)) {
          const resp = await api.componerSlide(piezaId, {
            foto: s.foto ?? "",
            titular: s.titular ?? "",
            plantilla_id: s.sinPlaca ? "" : s.plantillaId ?? "",
            foto_encuadre: s.fotoEncuadre ?? "",
            sin_plantilla: s.sinPlaca ?? false,
          });
          id = resp.id;
        }
        if (id) await descargarUrlConAuth(urlMedia(id), nombre);
      }
      toast.success("Carrusel descargado.");
      await ofrecerCopiarCopy(copy);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setDescargando(false);
    }
  }, [marca, piezaId, copy, onGuardarPortada]);

  // --- Receta del slide activo para el editor de placa --- //
  const esPortada = activo === 0;
  const slideExtra = esPortada ? null : slides[activo - 1];
  const enc = slideExtra ? parsearEncuadre(slideExtra.fotoEncuadre) : null;
  const fotosExtra = React.useMemo<FotoCollage[]>(
    () => [{ objeto: slideExtra?.foto ?? "", foco: enc?.foco ?? null, zoom: enc?.zoom ?? 0 }],
    [slideExtra?.foto, enc?.foco, enc?.zoom],
  );
  const esVideo = slideExtra?.tipo === "video";

  return (
    <div className="space-y-2">
      {/* Cabecera: posición + gestión de slides. */}
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {esPortada ? "Portada" : `Slide ${activo + 1}`}{" "}
          <span className="text-xs font-normal text-muted-foreground">de {total}</span>
        </span>
        <div className="flex items-center gap-1">
          {!esPortada && (
            <>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                onClick={() => moverActivo(-1)}
                disabled={disabled || activo <= 1}
                aria-label="Mover slide a la izquierda"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 px-2"
                onClick={() => moverActivo(1)}
                disabled={disabled || activo >= total - 1}
                aria-label="Mover slide a la derecha"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                className="h-7 gap-1 px-2 text-destructive hover:text-destructive"
                onClick={quitarActivo}
                disabled={disabled}
                aria-label="Quitar slide"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-2"
            onClick={anadirSlide}
            disabled={disabled}
            aria-label="Añadir slide"
          >
            <Plus className="h-4 w-4" />
            Slide
          </Button>
          {/* Descarga el carrusel entero (un archivo por slide) para postear a mano donde
              Metricool no llega (p. ej. X). */}
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 px-2"
            onClick={() => void descargarCarrusel()}
            disabled={disabled || descargando}
            aria-label="Descargar carrusel"
            title="Descargar carrusel para postear"
          >
            {descargando ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Carrusel
          </Button>
        </div>
      </div>

      {/* Editor del slide activo + flechas laterales. */}
      <div className="relative">
        {activo > 0 && (
          <button
            type="button"
            onClick={() => ir(-1)}
            className="absolute left-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-background/85 p-1.5 text-foreground shadow-sm hover:bg-background"
            aria-label="Slide anterior"
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
        )}
        {activo < total - 1 && (
          <button
            type="button"
            onClick={() => ir(1)}
            className="absolute right-1 top-1/2 z-10 -translate-y-1/2 rounded-full bg-background/85 p-1.5 text-foreground shadow-sm hover:bg-background"
            aria-label="Slide siguiente"
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        )}

        {esVideo ? (
          // Slide de VIDEO: previa con controles (no lleva placa). Se gestiona con quitar/mover.
          <div className="overflow-hidden rounded-md border bg-black">
            <video
              key={slideExtra?.objeto}
              src={urlMedia(slideExtra?.objeto ?? "")}
              controls
              playsInline
              preload="metadata"
              className="mx-auto aspect-[4/5] w-full object-contain"
            />
          </div>
        ) : esPortada ? (
          <EditorPlacaInline
            // `key` por slide: remonta el editor al cambiar de página (estado interno limpio).
            key="portada"
            marca={marca}
            piezaId={piezaId}
            documento={documentoDe(portadaPlantillaId, portadaPlacaOculta)}
            copyIn={portadaCopyIn}
            onCopyInCambio={onPortadaCopyIn}
            copy={copy}
            fotos={portadaFotos}
            onFotosCambio={onPortadaFotos}
            imagenFuente={imagenFuente}
            sinPlantilla={portadaPlacaOculta}
            onAlternarSinPlantilla={() => onPortadaPlacaOculta(!portadaPlacaOculta)}
            onAbrirGaleria={() => setGaleria(true)}
          />
        ) : (
          <EditorPlacaInline
            key={`extra-${activo}`}
            marca={marca}
            piezaId={piezaId}
            documento={documentoDe(slideExtra?.plantillaId ?? "", slideExtra?.sinPlaca ?? false)}
            copyIn={slideExtra?.titular ?? ""}
            onCopyInCambio={(t) => editarExtra(activo - 1, { titular: t })}
            copy={copy}
            fotos={fotosExtra}
            onFotosCambio={(f) => {
              const f0 = f[0];
              editarExtra(activo - 1, {
                foto: f0?.objeto ?? "",
                fotoEncuadre: f0?.foco ? serializarEncuadre({ foco: f0.foco, zoom: f0.zoom || 1 }) : "",
              });
            }}
            sinPlantilla={slideExtra?.sinPlaca ?? false}
            onAlternarSinPlantilla={() => editarExtra(activo - 1, { sinPlaca: !slideExtra?.sinPlaca })}
            onAbrirGaleria={() => setGaleria(true)}
          />
        )}

        {/* Spinner mientras se hornea el slide extra activo (la previa ya está en el lienzo). */}
        {!esPortada && horneando === activo - 1 && (
          <span className="absolute right-2 top-2 z-10 inline-flex items-center gap-1 rounded-md bg-background/85 px-2 py-1 text-xs text-muted-foreground shadow-sm">
            <Spinner className="h-3 w-3" /> Guardando…
          </span>
        )}
      </div>

      {/* Puntos de posición (clic para ir a un slide), como el feed. */}
      {total > 1 && (
        <div className="flex justify-center gap-1.5 pt-0.5">
          {Array.from({ length: total }, (_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setActivo(i)}
              className={cn(
                "h-2 w-2 rounded-full transition-colors",
                i === activo ? "bg-foreground" : "bg-muted-foreground/40 hover:bg-muted-foreground/70",
              )}
              aria-label={`Ir al slide ${i + 1}`}
              aria-current={i === activo}
            />
          ))}
        </div>
      )}

      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillas}
          onCargar={elegirPlantilla}
          onCerrar={() => setGaleria(false)}
          tipoFijo="foto"
        />
      )}
    </div>
  );
}
