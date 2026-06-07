/**
 * Estudio de Video — editor del "toque RRSS" sobre video YA editado (la edición cruda es
 * Premiere). Produce/edita el `documento` de COMPOSICIÓN del contrato (G-video-engine.md) y lo
 * manda a renderizar server-side con FFmpeg.
 *
 * Secciones (sub-navegación dentro de la página):
 *   - Base    : formato/aspecto + clip base + reencuadre (cover/contain, foco).
 *   - Overlay : editor de capas reutilizado (logos/marcos/image-in-video/textos).
 *   - PiP     : segundo video posicionado como Picture-in-Picture.
 *   - Subtítulos : transcribir (ASR) + corrección humana es-MX + marcar listo.
 *   - Render  : encola el render y muestra el mp4 resultante.
 *
 * Honestidad: el preview del navegador es APROXIMADO; el render fiel lo produce el servidor.
 * Nada se quema/publica sin criterio humano. La composición se crea en el backend al subir el
 * clip base y se autoguarda al cambiar de sección o antes de renderizar.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Captions, Clapperboard, Film, Layers, PictureInPicture2, Video as VideoIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { EditorSubtitulos } from "@/components/video/EditorSubtitulos";
// El editor de capas (Konva) se carga PEREZOSAMENTE: pesa y solo se necesita en la sección
// Overlay. Así el bundle inicial es menor y los tests/SSR no importan Konva salvo que entren ahí.
const PanelOverlay = React.lazy(() =>
  import("@/components/video/PanelOverlay").then((m) => ({ default: m.PanelOverlay })),
);
import { PanelPip } from "@/components/video/PanelPip";
import { PanelRender } from "@/components/video/PanelRender";
import { PistaBase } from "@/components/video/PistaBase";
import { PreviewComposicion } from "@/components/video/PreviewComposicion";
import { SelectorFormato } from "@/components/video/SelectorFormato";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import {
  cambiarAspecto,
  composicionVacia,
  pistaSubtitulos,
  quitarPip,
  setCajaPip,
  setCapasOverlay,
  setClipBase,
  setClipPip,
  setReencuadreBase,
  type AspectoVideo,
  type ComposicionVideo,
  type SegmentoSub,
} from "@/lib/video";

type Seccion = "base" | "overlay" | "pip" | "subs" | "render";

const SECCIONES: { clave: Seccion; etiqueta: string; Icono: typeof VideoIcon }[] = [
  { clave: "base", etiqueta: "Base", Icono: VideoIcon },
  { clave: "overlay", etiqueta: "Overlay", Icono: Layers },
  { clave: "pip", etiqueta: "PiP", Icono: PictureInPicture2 },
  { clave: "subs", etiqueta: "Subtítulos", Icono: Captions },
  { clave: "render", etiqueta: "Render", Icono: Film },
];

export default function EstudioVideo() {
  const { marcaActiva, marcaPrimaria } = useMarcaActiva();
  const marca = marcaActiva ?? marcaPrimaria ?? "";

  const [seccion, setSeccion] = React.useState<Seccion>("base");
  const [aspecto, setAspecto] = React.useState<AspectoVideo>("9:16");
  const [doc, setDoc] = React.useState<ComposicionVideo>(() => composicionVacia("9:16", marca));

  // Media servible para el preview (la composición guarda claves; aquí guardamos las urls).
  const [baseKey, setBaseKey] = React.useState("");
  const [baseUrl, setBaseUrl] = React.useState("");
  const [pipKey, setPipKey] = React.useState("");
  const [pipUrl, setPipUrl] = React.useState("");

  // Identidad backend de la composición.
  const [composicionId, setComposicionId] = React.useState<string | null>(null);
  const [segmentos, setSegmentos] = React.useState<SegmentoSub[]>([]);

  // Presets de formato del servidor (con fallback local dentro del selector).
  const formatosQ = useQuery({
    queryKey: ["video-formatos"],
    queryFn: ({ signal }) => api.video.formatos(signal).then((r) => r.formatos),
    // Si la API aún no está desplegada, el selector usa el fallback local: no bloquear.
    retry: false,
  });

  // Crea la composición en el backend (una vez por sesión, al fijar el primer clip base).
  // `marca` es obligatoria en la API: sin marca activa no se puede crear.
  const crear = useMutation({
    mutationFn: (d: ComposicionVideo) =>
      api.video.crearComposicion({ marca: d.marca || marca, documento: d }),
    onSuccess: (r) => setComposicionId(r.id),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardar = useMutation({
    mutationFn: (d: ComposicionVideo) => api.video.guardarComposicion(composicionId!, d),
    onError: (e) => toast.error(mensajeError(e)),
  });

  /** Aplica una mutación pura al documento y, si ya hay composición, la persiste. */
  const mutar = React.useCallback(
    (fn: (d: ComposicionVideo) => ComposicionVideo) => {
      setDoc((prev) => {
        const siguiente = fn(prev);
        // Sin cambio real (misma referencia): no reguardar (evita bucles de autoguardado).
        if (siguiente !== prev && composicionId) void guardar.mutateAsync(siguiente).catch(() => {});
        return siguiente;
      });
    },
    [composicionId, guardar],
  );

  function onCambioFormato(a: AspectoVideo) {
    setAspecto(a);
    mutar((d) => cambiarAspecto(d, a));
  }

  function onCambioBase(clave: string, url: string) {
    setBaseKey(clave);
    setBaseUrl(url);
    if (!clave) {
      mutar((d) => setClipBase(d, "", 0));
      return;
    }
    // Lee la duración real del clip para fijar duracion_ms; si falla, usa 0 (el render la recalcula).
    leerDuracion(url)
      .then((ms) => fijarBase(clave, ms))
      .catch(() => fijarBase(clave, 0));
  }

  function fijarBase(clave: string, ms: number) {
    setDoc((prev) => {
      // Asegura que la composición lleve la marca activa (la API la exige al crear).
      const siguiente = setClipBase({ ...prev, marca: prev.marca || marca }, clave, ms);
      // La composición se CREA al tener el primer clip base; luego se autoguarda.
      if (!composicionId) {
        if (!siguiente.marca) {
          toast.error("Selecciona una marca antes de editar el video.");
          return siguiente;
        }
        crear.mutate(siguiente);
      } else {
        void guardar.mutateAsync(siguiente).catch(() => {});
      }
      return siguiente;
    });
  }

  function onCambioPip(clave: string, url: string) {
    setPipKey(clave);
    setPipUrl(url);
    if (!clave) {
      mutar((d) => quitarPip(d));
      return;
    }
    leerDuracion(url)
      .then((ms) => mutar((d) => setClipPip(d, clave, ms)))
      .catch(() => mutar((d) => setClipPip(d, clave, 0)));
  }

  // Escribe el id de subtítulo en la pista subs de la composición (idempotente: si ya coincide,
  // no muta ni reguarda, para no entrar en bucle de autoguardado).
  function onSubtituloLigado(id: string) {
    mutar((d) => {
      if (pistaSubtitulos(d)?.subtitulo_id === id) return d;
      return {
        ...d,
        pistas: d.pistas.map((p) => (p.tipo === "subtitulos" ? { ...p, subtitulo_id: id } : p)),
      };
    });
  }

  const tieneBase = !!baseKey;

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col">
      {/* Cabecera */}
      <div className="flex items-center gap-2 border-b border-border p-3">
        <Clapperboard className="h-4 w-4 text-muted-foreground" />
        <h1 className="text-base font-semibold">Editor de video</h1>
        <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          Toque RRSS · render server-side
        </span>
      </div>

      {/* Sub-navegación de secciones */}
      <nav className="flex shrink-0 gap-1 overflow-x-auto border-b border-border px-3 py-1.5" aria-label="Secciones del editor de video">
        {SECCIONES.map(({ clave, etiqueta, Icono }) => {
          const activo = seccion === clave;
          // Overlay/PiP/Subs/Render requieren un clip base; se deshabilitan hasta tenerlo.
          const requiereBase = clave !== "base";
          const off = requiereBase && !tieneBase;
          return (
            <button
              key={clave}
              type="button"
              disabled={off}
              onClick={() => setSeccion(clave)}
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:opacity-40 ${
                activo ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60"
              }`}
            >
              <Icono className="h-4 w-4" />
              {etiqueta}
            </button>
          );
        })}
      </nav>

      {/* Cuerpo: controles (izq) + preview (der) */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto grid max-w-6xl gap-6 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
          {/* Columna de controles según la sección */}
          <section className="min-w-0 space-y-4">
            {seccion === "base" && (
              <>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-foreground">Formato</h2>
                  <SelectorFormato
                    aspecto={aspecto}
                    onCambio={onCambioFormato}
                    presets={formatosQ.data}
                  />
                </div>
                <div>
                  <h2 className="mb-2 text-sm font-semibold text-foreground">Pista base</h2>
                  <PistaBase
                    doc={doc}
                    videoKey={baseKey}
                    videoUrl={baseUrl}
                    onCambioVideo={onCambioBase}
                    onReencuadre={(c) => mutar((d) => setReencuadreBase(d, c))}
                  />
                </div>
              </>
            )}

            {seccion === "overlay" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Capas de overlay</h2>
                <p className="text-xs text-muted-foreground">
                  Logos, marcos de marca, imagen-in-video y textos. Se sobreimprimen sobre el video
                  (el render rasteriza estas capas y las compone con FFmpeg).
                </p>
                <React.Suspense
                  fallback={
                    <div className="flex h-[60vh] min-h-[420px] items-center justify-center rounded-md border border-border text-sm text-muted-foreground">
                      Cargando editor de capas…
                    </div>
                  }
                >
                  <PanelOverlay
                    doc={doc}
                    marca={marca}
                    capas={pistaOverlayCapas(doc)}
                    onCapas={(capas) => mutar((d) => setCapasOverlay(d, capas))}
                  />
                </React.Suspense>
              </>
            )}

            {seccion === "pip" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Picture-in-Picture</h2>
                <PanelPip
                  doc={doc}
                  videoKey={pipKey}
                  videoUrl={pipUrl}
                  onCambioVideo={onCambioPip}
                  onCaja={(caja) => mutar((d) => setCajaPip(d, caja))}
                  onQuitar={() => {
                    setPipKey("");
                    setPipUrl("");
                    mutar((d) => quitarPip(d));
                  }}
                />
              </>
            )}

            {seccion === "subs" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Subtítulos (es-MX)</h2>
                <EditorSubtitulos
                  composicionId={composicionId}
                  baseMediaId={baseKey}
                  onSubtituloLigado={onSubtituloLigado}
                  onSegmentos={setSegmentos}
                />
              </>
            )}

            {seccion === "render" && (
              <>
                <h2 className="text-sm font-semibold text-foreground">Renderizar</h2>
                <p className="text-xs text-muted-foreground">
                  Genera el mp4 final componiendo base, overlay, PiP y subtítulos con FFmpeg en el
                  servidor. El preview de la derecha es solo una aproximación.
                </p>
                <PanelRender
                  composicionId={composicionId}
                  onAntesDeRenderizar={async () => {
                    if (composicionId) await guardar.mutateAsync(doc);
                  }}
                />
              </>
            )}
          </section>

          {/* Columna de preview (persistente) */}
          <aside className="space-y-2 lg:sticky lg:top-0">
            <h2 className="text-sm font-semibold text-foreground">Vista previa</h2>
            <PreviewComposicion
              doc={doc}
              baseUrl={baseUrl}
              pipUrl={pipUrl}
              segmentos={segmentos}
            />
          </aside>
        </div>
      </div>
    </div>
  );
}

/** Lee la duración (ms) de un video desde su URL, cargando metadatos en un <video> efímero. */
function leerDuracion(url: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      const ms = Number.isFinite(v.duration) ? Math.round(v.duration * 1000) : 0;
      resolve(ms);
    };
    v.onerror = () => reject(new Error("No se pudo leer la duración del video."));
    v.src = url;
  });
}

/** Capas de la pista overlay (vacío si no hay pista). */
function pistaOverlayCapas(doc: ComposicionVideo) {
  const p = doc.pistas.find((x) => x.tipo === "overlay");
  return p && "capas" in p ? p.capas : [];
}
