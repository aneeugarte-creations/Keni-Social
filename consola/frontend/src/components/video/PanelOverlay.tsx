/**
 * Pista de OVERLAY: reutiliza el EDITOR DE CAPAS del Estudio de imagen para añadir logos,
 * marcos, image-in-video y textos como capas `Documento`. El render server-side rasteriza
 * estas capas a un PNG transparente (`renderizar_documento_bytes`) y lo compone con `overlay`
 * en FFmpeg sobre el video (contrato G-video-engine §1).
 *
 * Monta `EditorDocumento` sobre un store cuyo lienzo coincide con el formato de la composición
 * (fondo TRANSPARENTE, sin hueco de foto: aquí no se sustituye foto, se sobreimprime sobre el
 * video). Cada cambio del documento sincroniza `documento.capas` hacia la composición.
 *
 * PLANTILLAS (paridad Canva con Imagen): el rail ofrece la MISMA galería de plantillas de diseño
 * de la marca; aplicar una es 1 clic (se adapta al formato del video con la heurística de
 * «Adaptar a…» y se quitan los huecos de foto: el video hace de foto). Y al revés: «Guardar como
 * plantilla…» persiste el overlay como PlantillaDiseno, así lo creado en video aparece también
 * en Imagen (puente `overlayPlantillas.ts`).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Image, SaveAll, Video } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { Capa, Documento } from "@/editor/documento";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { api, urlMedia, type PlantillaDiseno } from "@/lib/api";
import { pistaBase, presetParaAspecto, type ComposicionVideo } from "@/lib/video";

import { overlayAPlantilla, plantillaAOverlay } from "./overlayPlantillas";

type TipoPlantilla = "foto" | "miniatura";

export interface PanelOverlayProps {
  doc: ComposicionVideo;
  marca: string;
  /** Capas actuales de la pista overlay. */
  capas: Capa[];
  /** Notifica el nuevo conjunto de capas tras cada edición. */
  onCapas: (capas: Capa[]) => void;
  /** URL del clip base: se pinta DETRÁS del lienzo de capas para editar el overlay sobre el vídeo. */
  videoBaseUrl?: string;
}

/** `<video>` base como fondo del lienzo de overlay (object-fit + foco del clip base). */
function FondoVideo({ doc, url }: { doc: ComposicionVideo; url: string }) {
  const clip = pistaBase(doc)?.clips[0];
  const recorteInMs = clip?.recorte_in_ms ?? 0;
  return (
    <video
      src={urlMedia(url)}
      muted
      playsInline
      preload="metadata"
      className="h-full w-full"
      style={{
        objectFit: clip?.ajuste === "contain" ? "contain" : "cover",
        objectPosition: clip ? `${clip.foco[0] * 100}% ${clip.foco[1] * 100}%` : "center",
      }}
      onLoadedMetadata={(e) => {
        if (recorteInMs > 0) (e.currentTarget as HTMLVideoElement).currentTime = recorteInMs / 1000;
      }}
    />
  );
}

/** Construye un Documento transparente del tamaño de la composición con las capas dadas. */
export function documentoOverlay(doc: ComposicionVideo, marca: string, capas: Capa[]): Documento {
  const preset = presetParaAspecto(doc.formato.preset);
  return {
    version: 1,
    marca,
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato: { w: doc.formato.w, h: doc.formato.h, safe_top: preset.safe_top, safe_bottom: preset.safe_bottom },
    fondo: { tipo: "color", color: "#00000000" },
    capas,
  };
}

export function PanelOverlay({ doc, marca, capas, onCapas, videoBaseUrl }: PanelOverlayProps) {
  // Un store POR montaje, inicializado con las capas actuales. Se recrea si cambia el formato del
  // lienzo (las capas se preservan vía el documento).
  const storeRef = React.useRef<StoreEditor | null>(null);
  const formatoClave = `${doc.formato.w}x${doc.formato.h}`;
  const formatoPrev = React.useRef(formatoClave);

  if (!storeRef.current || formatoPrev.current !== formatoClave) {
    storeRef.current = crearStoreEditor(documentoOverlay(doc, marca, capas));
    formatoPrev.current = formatoClave;
  }
  const store = storeRef.current;

  // Sincroniza las capas del store hacia el padre en cada cambio (debounced por microtask vía
  // la suscripción de zustand). El padre es la fuente de verdad de la composición.
  React.useEffect(() => {
    const unsub = store.subscribe(() => {
      onCapas(store.getState().documento.capas);
    });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [store]);

  // ── PLANTILLAS compartidas con Imagen ────────────────────────────────────────────────────────
  const qc = useQueryClient();
  const [galeria, setGaleria] = React.useState(false);
  // Diálogo de «Guardar como plantilla» (nombre + tipo), mismo patrón que Imagen.
  const [dialogo, setDialogo] = React.useState<{ nombre: string; tipo: TipoPlantilla } | null>(null);

  // La galería filtra por la marca de la COMPOSICIÓN (cae a la marca activa si aún no la lleva).
  const marcaGaleria = doc.marca || marca;
  const plantillasQ = useQuery({
    queryKey: ["plantillas-diseno", marcaGaleria],
    queryFn: ({ signal }) => api.plantillasDiseno({ marca: marcaGaleria || undefined }, signal),
    enabled: galeria,
  });

  // Aplica una plantilla al overlay A UN CLIC: adapta el documento al formato del video (si
  // difiere) reutilizando la lógica de «Adaptar a…», quita los huecos de foto (el video hace de
  // foto) y REEMPLAZA las capas actuales (con confirmación si las había; `cargar` resetea el
  // historial y no se puede deshacer).
  const aplicarPlantilla = async (p: PlantillaDiseno) => {
    if (store.getState().documento.capas.length > 0) {
      const ok = await confirmar({
        titulo: "Aplicar plantilla",
        mensaje: `¿Reemplazar las capas actuales?`,
        destructivo: true,
        textoConfirmar: "Aplicar",
      });
      if (!ok) return;
    }
    store.getState().cargar(plantillaAOverlay(p.documento as Documento, doc.formato, marca));
    setGaleria(false);
    toast.success(`Plantilla «${p.nombre || "sin nombre"}» aplicada al overlay.`);
  };

  // «Guardar como plantilla…»: persiste el documento del overlay como PlantillaDiseno de la marca
  // (con el hueco de foto oculto que exige el servidor), para que aparezca también en Imagen.
  const guardarComo = useMutation({
    mutationFn: async ({ nombre, tipo }: { nombre: string; tipo: TipoPlantilla }) => {
      const documento = overlayAPlantilla(store.getState().documento, marcaGaleria);
      // Miniatura best-effort (mismo patrón que Imagen): si el render falla, se guarda sin ella
      // (la galería cae al preview on-demand).
      let miniatura = "";
      try {
        miniatura = (await api.imagenRender(documento, { copy_in: "TITULAR", etiqueta_default: "" })).id;
      } catch {
        /* sin miniatura */
      }
      return api.crearPlantillaDiseno({
        marca: marcaGaleria,
        nombre,
        categoria: "post",
        tipo,
        documento,
        ...(miniatura ? { miniatura } : {}),
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["plantillas-diseno"] });
      toast.success("Plantilla guardada. Disponible también en Imagen.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo guardar la plantilla."),
  });

  const abrirGuardarComo = () => {
    if (store.getState().documento.capas.length === 0) {
      toast.error("El overlay está vacío. Añade una capa.");
      return;
    }
    setDialogo({ nombre: "", tipo: "foto" });
  };

  const confirmarNombre = () => {
    const nombre = dialogo?.nombre.trim();
    if (!nombre) return;
    guardarComo.mutate({ nombre, tipo: dialogo?.tipo ?? "foto" });
    setDialogo(null);
  };

  return (
    // En lg+ llena el alto que le da la columna (Video.tsx le pasa flex-1); por debajo, alto
    // fijo para que el editor no colapse cuando el contenedor apilado no tiene alto definido.
    <div className="h-[60vh] min-h-[420px] overflow-hidden rounded-xl border bg-card lg:h-full">
      {/* `accionesEnCabecera`: el clúster del editor (DESHACER/REHACER, muestra, «Más») se
          portaliza a la barra de cabecera unificada del shell —mismo sitio que en el Estudio de
          imagen—, así Deshacer/Rehacer quedan siempre visibles mientras se edita el overlay. */}
      <EditorDocumento
        store={store}
        marca={marca}
        accionesEnCabecera
        fondoLienzo={videoBaseUrl ? <FondoVideo doc={doc} url={videoBaseUrl} /> : undefined}
        onPlantillas={() => setGaleria(true)}
        menuExtra={
          <button
            onClick={abrirGuardarComo}
            disabled={guardarComo.isPending}
            className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent disabled:opacity-40"
          >
            <SaveAll className="h-4 w-4 text-muted-foreground" /> Guardar como plantilla…
          </button>
        }
      />

      {/* Galería modal compartida con Imagen, en modo SELECTOR (sin borrar/duplicar/renombrar). */}
      {galeria && (
        <GaleriaPlantillas
          plantillas={plantillasQ.data?.plantillas ?? []}
          onCargar={(p) => void aplicarPlantilla(p)}
          onCerrar={() => setGaleria(false)}
        />
      )}

      {/* Diálogo «Guardar como plantilla» (nombre + tipo), espejo del de Imagen. */}
      <Dialog open={!!dialogo} onOpenChange={(o) => !o && setDialogo(null)}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Guardar como plantilla</DialogTitle>
          </DialogHeader>
          <Input
            autoFocus
            placeholder="Nombre de la plantilla"
            value={dialogo?.nombre ?? ""}
            onChange={(e) => setDialogo((d) => (d ? { ...d, nombre: e.target.value } : d))}
            onKeyDown={(e) => { if (e.key === "Enter") confirmarNombre(); }}
          />
          {/* Selector de tipo: foto (post de imagen) o miniatura (portada de video). */}
          <div className="flex gap-2">
            {(["foto", "miniatura"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setDialogo((d) => (d ? { ...d, tipo: t } : d))}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded border px-3 py-2 text-sm transition-colors ${
                  (dialogo?.tipo ?? "foto") === t
                    ? "border-primary bg-primary/10 font-medium text-primary"
                    : "border-border text-muted-foreground hover:border-muted-foreground"
                }`}
              >
                {t === "foto" ? <Image className="h-3.5 w-3.5" /> : <Video className="h-3.5 w-3.5" />}
                {t === "foto" ? "Foto" : "Miniatura"}
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogo(null)}>Cancelar</Button>
            <Button onClick={confirmarNombre} disabled={!dialogo?.nombre.trim()}>Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
