/**
 * Vista previa VISUAL del Termómetro mundial.
 *
 * En vez del Card genérico de Markdown (`ResultadoDocumento`, compartido con otras
 * superficies), este componente renderiza el documento de la galería como lo que es:
 * una PORTADA + N SLIDES en miniatura (carrusel/grid de tarjetas), más el veredicto
 * destacado arriba y el detalle editorial (fuentes, auto-verificación) plegable abajo.
 *
 * Es SOLO PRESENTACIÓN: parsea el mismo documento Markdown que produce el prompt
 * `termometro-mundial` (veredicto → PORTADA → SLIDES → Fuentes → Auto-verificación +
 * bloque ```json con `piezas`). El guardado sigue el MISMO contrato neutro que el resto:
 * `POST /api/prompts/historial/{id}/guardar` con `{ redes: [...] }` (un borrador por red).
 * No toca el parser de `piezas` del backend.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Copy,
  ExternalLink,
  Image as ImageIcon,
  Layers,
  Loader2,
  Save,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Markdown } from "@/components/ui/Markdown";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";

/** Enlace de éxito al feed (modo Publicaciones) que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/operacion/feed/lista" className="inline-flex items-center gap-1 underline">
      Ver feed
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

// --- Parser del documento de la galería -----------------------------------

interface SlideParseado {
  /** Etiqueta de orden del slide ("Portada", "2/8", "3"…). */
  numero: string;
  /** Primera línea con peso (titular del slide / título de la portada). */
  titulo: string;
  /** Resto del cuerpo del slide (contexto, región, registro). */
  cuerpo: string;
  /** `true` para la portada (slide 1). */
  esPortada: boolean;
}

interface TermometroParseado {
  /** Línea de veredicto (LISTO PARA APROBAR · REVISAR… · NO PUBLICAR), si se detecta. */
  veredicto: string | null;
  /** Portada + slides numerados como tarjetas. */
  slides: SlideParseado[];
  /** Prosa editorial restante (Fuentes, Auto-verificación, notas) para plegar. */
  detalle: string;
}

const RE_VEREDICTO =
  /(LISTO PARA APROBAR|REVISAR ANTES DE PUBLICAR|NO PUBLICAR|✅|⚠️|❌)/i;

// Encabezado de portada: "Termómetro mundial · <fecha>" (con o sin almohadillas markdown).
const RE_PORTADA = /term[óo]metro\s+mundial/i;

// Etiqueta de slide numerado al inicio de línea: "2/8", "3 /8", "Slide 2", "2.", "**3/8**"…
const RE_SLIDE =
  /^\s*\**\s*(?:slide\s*)?(\d{1,2})\s*(?:\/\s*\d{1,2})?\s*[).:·-]?\s*\**/i;

// Quita marcas markdown de encabezado/énfasis de una línea para mostrarla como título.
function limpiarTitulo(linea: string): string {
  return linea
    .replace(/^#{1,6}\s*/, "")
    .replace(/^\s*[-*]\s+/, "")
    .replace(RE_SLIDE, "")
    .replace(/\*\*/g, "")
    .replace(/__/g, "")
    .trim();
}

// Marca de inicio de la sección de detalle (fuentes / verificación): a partir de aquí
// dejamos de parsear slides y todo va al bloque plegable.
const RE_DETALLE = /^#{0,6}\s*\**\s*(fuentes?|auto[\s-]?verificaci[óo]n|verificaci[óo]n)\b/i;

/**
 * Parsea el documento Markdown del prompt en veredicto + slides (portada incluida) +
 * detalle. Tolerante: si el formato no encaja (modelo se sale del molde), `slides` puede
 * venir vacío y el llamador cae al render Markdown plano. Nunca lanza.
 */
function parsearTermometro(documento: string): TermometroParseado {
  const texto = (documento ?? "").trim();
  // El bloque JSON final (```json {"piezas": …}) es para el backend, no para mostrar.
  const sinJson = texto.replace(/```json[\s\S]*?```/gi, "").trim();

  if (!sinJson) return { veredicto: null, slides: [], detalle: "" };

  const lineas = sinJson.split("\n");

  // 1) Veredicto: primera línea con peso que contenga uno de los estados/íconos.
  let veredicto: string | null = null;
  let inicio = 0;
  for (let i = 0; i < lineas.length; i++) {
    const l = lineas[i].trim();
    if (!l) continue;
    if (RE_VEREDICTO.test(l)) {
      veredicto = limpiarTitulo(l) || l.replace(/\*\*/g, "").trim();
      inicio = i + 1;
    }
    break; // solo miramos la primera línea no vacía
  }

  // 2) Recorre el resto agrupando por slide. Un nuevo slide empieza en: la portada
  //    ("Termómetro mundial · …") o una línea que arranque con número de slide.
  const slides: SlideParseado[] = [];
  let detalleDesde = -1;
  let actual: { numero: string; lineas: string[]; esPortada: boolean } | null = null;

  const empuja = () => {
    if (!actual) return;
    const cuerpoLineas = [...actual.lineas];
    const titulo = limpiarTitulo(cuerpoLineas.shift() ?? "");
    slides.push({
      numero: actual.numero,
      titulo,
      cuerpo: cuerpoLineas.join("\n").trim(),
      esPortada: actual.esPortada,
    });
  };

  for (let i = inicio; i < lineas.length; i++) {
    const cruda = lineas[i];
    const l = cruda.trim();

    if (RE_DETALLE.test(l)) {
      detalleDesde = i;
      break;
    }

    const sinMarcas = limpiarTitulo(l);
    const esPortada = !!sinMarcas && RE_PORTADA.test(sinMarcas) && slides.length === 0 && !actual;
    const mSlide = RE_SLIDE.exec(l);

    if (esPortada) {
      empuja();
      actual = { numero: "Portada", lineas: [l], esPortada: true };
    } else if (mSlide && l.length > mSlide[0].length) {
      empuja();
      // Etiqueta del slide tal cual la escribió el prompt ("2/8", "3"…), sin la puntuación.
      const etiqueta = mSlide[0].replace(/[).:·\-*\s]+$/g, "").replace(/\*\*/g, "").trim();
      actual = { numero: etiqueta || String(slides.length + 1), lineas: [l], esPortada: false };
    } else if (actual) {
      actual.lineas.push(cruda);
    }
    // líneas sueltas antes del primer slide/portada se ignoran en el visual (van implícitas).
  }
  empuja();

  const detalle = detalleDesde >= 0 ? lineas.slice(detalleDesde).join("\n").trim() : "";

  return { veredicto, slides, detalle };
}

// --- UI --------------------------------------------------------------------

/** Color del badge de veredicto según el estado detectado. */
function variantVeredicto(v: string): React.ComponentProps<typeof Badge>["variant"] {
  if (/no publicar|❌/i.test(v)) return "error";
  if (/revisar|⚠️/i.test(v)) return "aviso";
  return "ok";
}

/** Una tarjeta de slide en miniatura (portada o nota). */
function TarjetaSlide({ slide, indice }: { slide: SlideParseado; indice: number }) {
  return (
    <div
      className={cn(
        "flex w-56 shrink-0 snap-start flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-colors",
        slide.esPortada ? "border-primary/40 ring-1 ring-primary/20" : "border-border",
      )}
    >
      {/* Cabecera tipo "lienzo" del slide: número + naturaleza. */}
      <div
        className={cn(
          "flex items-center justify-between gap-2 px-3 py-2 text-[11px] font-medium uppercase tracking-wide",
          slide.esPortada
            ? "bg-primary/10 text-primary"
            : "bg-muted/60 text-muted-foreground",
        )}
      >
        <span className="inline-flex items-center gap-1.5">
          <ImageIcon className="h-3.5 w-3.5" aria-hidden="true" />
          {slide.esPortada ? "Portada" : `Slide ${slide.numero}`}
        </span>
        <span className="tabular-nums opacity-70">{indice + 1}</span>
      </div>
      <div className="flex flex-1 flex-col gap-1.5 p-3">
        <p
          className={cn(
            "font-semibold leading-snug",
            slide.esPortada ? "text-sm" : "text-[13px]",
          )}
        >
          {slide.titulo || <span className="italic text-muted-foreground">Sin título</span>}
        </p>
        {slide.cuerpo && (
          <div className="text-[12px] leading-snug text-muted-foreground [&_p]:my-0 [&_ul]:my-0">
            <Markdown>{slide.cuerpo}</Markdown>
          </div>
        )}
      </div>
    </div>
  );
}

export function TermometroPreview({
  documento,
  historialId,
  marca,
}: {
  documento: string;
  historialId: string;
  /** Marca del termómetro (informativa; aparece en la cabecera del visor). */
  marca?: string;
}) {
  const queryClient = useQueryClient();
  const [redes, setRedes] = React.useState<Set<string>>(() => new Set());
  const [copiado, setCopiado] = React.useState(false);
  const [verDetalle, setVerDetalle] = React.useState(false);
  const timerRef = React.useRef<number | null>(null);
  React.useEffect(() => {
    return () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    };
  }, []);

  const { veredicto, slides, detalle } = React.useMemo(
    () => parsearTermometro(documento),
    [documento],
  );

  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const opcionesData = opcionesQuery.data;
  const opcionesRedes = React.useMemo(
    () => opcionesData?.redes.map((r) => ({ id: r.id, nombre: r.nombre })) ?? [],
    [opcionesData],
  );
  const nombrePorId = React.useMemo(
    () => new Map(opcionesRedes.map((r) => [r.id, r.nombre])),
    [opcionesRedes],
  );

  function alternarRed(red: string, marcada: boolean) {
    setRedes((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  const guardar = useMutation({
    mutationFn: () => api.guardarHistorial(historialId, { redes: [...redes] }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const n = data?.publicaciones?.length ?? 1;
      toast.success(
        `Se ${n === 1 ? "guardó" : "guardaron"} ${n} ${n === 1 ? "publicación" : "publicaciones"}`,
        { description: <EnlacePublicaciones /> },
      );
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(documento);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  const puedeGuardar = !guardar.isPending && historialId !== "" && redes.size > 0;
  const seleccionadas = [...redes].map((id) => nombrePorId.get(id) ?? id);

  return (
    <Card data-testid="termometro-preview">
      <CardHeader className="space-y-2 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Layers className="h-4 w-4 text-muted-foreground" />
            Galería del termómetro
          </CardTitle>
          {marca && (
            <span className="text-xs text-muted-foreground">· {marca}</span>
          )}
          <Badge variant="aviso" className="ml-auto">
            Borrador · no guardado
          </Badge>
        </div>
        {veredicto && (
          <div>
            <Badge variant={variantVeredicto(veredicto)}>{veredicto}</Badge>
          </div>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {slides.length > 0 ? (
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-medium">
                {slides.length} {slides.length === 1 ? "slide" : "slides"} (incluye portada)
              </span>
              <span className="hidden sm:inline">Desliza para ver todos →</span>
            </div>
            <div
              className="flex snap-x gap-3 overflow-x-auto pb-2"
              role="list"
              aria-label="Slides de la galería"
            >
              {slides.map((slide, i) => (
                <div role="listitem" key={`${slide.numero}-${i}`}>
                  <TarjetaSlide slide={slide} indice={i} />
                </div>
              ))}
            </div>
          </div>
        ) : (
          // Sin slides reconocibles: caemos al documento Markdown plano (tolerancia).
          <div className="max-h-[28rem] overflow-auto rounded-md border border-border bg-muted/20 p-4 leading-relaxed">
            {documento.trim() ? (
              <Markdown>{documento}</Markdown>
            ) : (
              <p className="text-sm italic text-muted-foreground">El documento llegó vacío.</p>
            )}
          </div>
        )}

        {detalle && (
          <div className="rounded-md border border-border">
            <button
              type="button"
              onClick={() => setVerDetalle((v) => !v)}
              aria-expanded={verDetalle}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <span>Fuentes y auto-verificación</span>
              <span className="text-xs">{verDetalle ? "Ocultar" : "Ver"}</span>
            </button>
            {verDetalle && (
              <div className="max-h-80 overflow-auto border-t border-border bg-muted/20 px-4 py-3 text-sm leading-relaxed">
                <Markdown>{detalle}</Markdown>
              </div>
            )}
          </div>
        )}

        <div className="space-y-2 border-t border-border pt-3">
          <SelectorRedMultiple
            opciones={opcionesRedes}
            seleccionadas={redes}
            onCambio={alternarRed}
            disabled={guardar.isPending}
          />
          <p className="text-xs text-muted-foreground" aria-live="polite">
            {redes.size === 0
              ? "Elige al menos una red para guardar la galería como borrador."
              : `Se ${redes.size === 1 ? "creará" : "crearán"} ${redes.size} ${
                  redes.size === 1 ? "borrador" : "borradores"
                } (${seleccionadas.join(", ")}).`}
          </p>
        </div>

        <div className="flex flex-wrap items-end gap-2">
          <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Guardar como publicación
          </Button>
          <Button variant="outline" size="sm" onClick={() => void copiar()}>
            {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            {copiado ? "Copiado" : "Copiar documento"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
