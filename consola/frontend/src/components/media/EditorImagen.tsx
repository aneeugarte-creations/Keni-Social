/**
 * Zona de imagen de una pieza: el usuario solo decide DE DÓNDE SALE EL FONDO y, si la pieza
 * tiene marca con plantilla, la placa de marca + el copy-in se componen ENCIMA casi solos.
 *
 * Tres orígenes de fondo:
 *   - **Biblioteca (S3)**: elegir un arte ya guardado (`SelectorArtes`).
 *   - **Subir**: un archivo del equipo (`POST /api/media`).
 *   - **Generar con IA**: a partir de un prompt (`POST /api/media/generar`).
 *
 * Tras obtener el fondo por cualquiera de las tres vías, si hay `marca` se AUTO-COMPONE la
 * placa (`POST /api/imagenes/componer`, sondeada con `useGeneracion`) usando el copy-in como
 * titular, y se muestra la preview; el usuario puede reajustar titular/etiqueta y re-componer,
 * o **guardar el fondo en la biblioteca** para reutilizarlo. Sin `marca` (uso suelto, p. ej.
 * en el tablero) el fondo se adjunta tal cual, sin componer.
 *
 * El componente es controlado: el padre guarda el `nombre` de la imagen final (vacío = sin
 * imagen) y lo incluye al guardar la pieza. El FONDO limpio se recuerda solo en esta sesión
 * (para re-componer y para guardarlo en la biblioteca sin la placa estampada).
 */
import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle,
  ImageOff,
  ImagePlus,
  Library,
  Loader2,
  RefreshCw,
  Save,
  Upload,
  Wand2,
  X,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import { nombreRed, tamanoRed } from "@/pages/publicaciones/meta";
import type { Arte, FormatoImagen, TipoArte } from "@/types";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Convierte una relación tipo "16:9" o "1.91:1" en un número (ancho/alto). */
function ratioDe(txt: string): number | null {
  const [w, h] = txt.split(/[:/]/).map((n) => parseFloat(n));
  return w && h ? w / h : null;
}

/**
 * Formato de placa para una red (espejo de `estudio_imagen.formato_por_red` del backend):
 * el compositor solo entiende `vertical|feed|cuadrado`; se elige el encaje más cercano.
 */
function formatoDeRed(red: string | undefined): FormatoImagen {
  if (red === "tiktok") return "vertical";
  if (red === "instagram") return "cuadrado";
  return "feed";
}

/** Fondo limpio elegido en esta sesión (antes de estampar la placa). */
interface Fondo {
  id: string;
  url: string;
  /** De dónde salió, para catalogarlo con el origen correcto al guardarlo. */
  tipo: TipoArte;
}

export interface EditorImagenProps {
  /** Nombre del archivo de imagen actual (`""` si no hay). */
  imagen: string;
  /** URL conocida para servir la imagen (de la publicación); opcional. */
  imagenUrl?: string;
  /** Notifica el nuevo nombre de imagen (o `""` al quitarla). */
  onCambio: (nombre: string, url: string) => void;
  disabled?: boolean;
  idPrefijo?: string;
  /**
   * Contexto de la pieza, opcional: si se pasa, se muestra un enlace discreto
   * "Abrir en Estudio" que lleva al Estudio de imagen preconfigurado (router state).
   */
  publicacionId?: string;
  marca?: string;
  red?: string;
  copy?: string;
  /** Texto que va DENTRO de la imagen (copy-in); titular al componer la placa. */
  copyIn?: string;
  /**
   * Imagen ORIGINAL del artículo (URL), p.ej. de un RSS de marca propia. Si la pieza la
   * trae, se ofrece "Usar imagen original" para volver a ella tras haberla reemplazado.
   * La pieza ya la muestra por defecto (imagen_url cae a esta URL cuando no hay archivo).
   */
  imagenFuente?: string;
}

export function EditorImagen({
  imagen,
  imagenUrl,
  onCambio,
  disabled,
  idPrefijo = "img",
  publicacionId,
  marca,
  red,
  copy,
  copyIn,
  imagenFuente,
}: EditorImagenProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = React.useState("");
  // Aviso amable cuando la generación no está configurada (400).
  const [avisoGenerar, setAvisoGenerar] = React.useState("");
  // Galería de artes (biblioteca S3).
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  // Fondo limpio de ESTA sesión (lo que se compone y lo que se puede guardar sin placa).
  const [fondo, setFondo] = React.useState<Fondo | null>(null);
  // Ajustes de la placa (solo si hay marca). El titular parte del copy-in de la pieza.
  const [titular, setTitular] = React.useState(copyIn ?? "");
  const [etiqueta, setEtiqueta] = React.useState("");

  // Si cambia el copy-in de la pieza y el usuario aún no tocó el titular, lo seguimos.
  const titularTocado = React.useRef(false);
  React.useEffect(() => {
    if (!titularTocado.current) setTitular(copyIn ?? "");
  }, [copyIn]);

  const componible = !!marca; // solo las piezas con marca auto-componen la placa.
  const src = urlMedia(imagenUrl || imagen);

  // Aspect-ratio real de la imagen (medido al cargar) frente al recomendado de la red.
  const [ratioReal, setRatioReal] = React.useState<number | null>(null);
  React.useEffect(() => {
    setRatioReal(null);
  }, [src]);
  const tamRed = red ? tamanoRed(red) : null;
  const ratioRec = tamRed ? ratioDe(tamRed.ratio) : null;
  const aspectoFueraDeEstandar =
    ratioReal != null && ratioRec != null && Math.abs(ratioReal - ratioRec) / ratioRec > 0.1;

  // --- Composición de la placa (job de imagen en background, sondeado) --- //
  const { generacion: genComp, ejecutando: componiendo, iniciar: iniciarComp } = useGeneracion();
  const componer = useMutation({
    mutationFn: (base: Fondo) =>
      api.imagenesComponer({
        imagen: base.id,
        marca: marca!,
        formato: formatoDeRed(red),
        titular: titular.trim() || undefined,
        etiqueta: etiqueta.trim() || undefined,
      }),
    onSuccess: (data) => iniciarComp(data.generacion),
    onError: (e) => {
      // Si la marca no tiene placa (o falla la composición), usamos el fondo tal cual.
      toast.message("Se usó el fondo sin placa de marca.", { description: mensajeError(e) });
      if (fondo) onCambio(fondo.id, fondo.url);
    },
  });

  // Al completar la composición, fijamos la imagen compuesta como la de la pieza.
  const compTerminal = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!genComp || genComp.id === compTerminal.current) return;
    if (genComp.estado === "completado") {
      compTerminal.current = genComp.id;
      const r = genComp.resultado;
      if (r?.id && r?.url) {
        onCambio(r.id, r.url);
        toast.success("Marca aplicada");
      }
    } else if (genComp.estado === "error") {
      compTerminal.current = genComp.id;
      toast.message("Se usó el fondo sin placa de marca.", { description: genComp.error || "" });
      if (fondo) onCambio(fondo.id, fondo.url);
    }
  }, [genComp, onCambio, fondo]);

  /** Aplica un fondo recién elegido: lo recuerda y, si hay marca, compone la placa encima. */
  const aplicarFondo = React.useCallback(
    (base: Fondo) => {
      setFondo(base);
      if (componible) {
        componer.mutate(base);
      } else {
        onCambio(base.id, base.url); // uso suelto: se adjunta tal cual.
      }
    },
    // `componer` es estable (useMutation); lo omitimos para no recrear el callback en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [componible, onCambio],
  );

  // --- Subir un archivo como fondo --- //
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (data) => aplicarFondo({ id: data.id, url: data.url, tipo: "subida" }),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // --- Generar el fondo con IA (job de imagen en background, sondeado) --- //
  const { generacion: genIA, ejecutando: generandoIA, iniciar: iniciarIA } = useGeneracion();
  const generar = useMutation({
    mutationFn: () => api.generarMedia({ prompt: prompt.trim() }),
    onSuccess: (data) => {
      setAvisoGenerar("");
      iniciarIA(data.generacion);
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
      if (r?.id && r?.url) {
        setPrompt("");
        aplicarFondo({ id: r.id, url: r.url, tipo: "ia" });
      }
    } else if (genIA.estado === "error") {
      iaTerminal.current = genIA.id;
      toast.error(genIA.error || "No se pudo generar la imagen.");
    }
  }, [genIA, aplicarFondo]);

  // --- Guardar el fondo en la biblioteca (durable + reutilizable) --- //
  const guardar = useMutation({
    mutationFn: () => {
      if (!fondo) throw new Error("Elige primero un fondo.");
      return api.guardarArte({ objeto: fondo.id, marca: marca || undefined, tipo: fondo.tipo });
    },
    onSuccess: () => toast.success("Fondo guardado en la biblioteca"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    if (inputRef.current) inputRef.current.value = "";
  }

  function elegirArte(arte: Arte) {
    aplicarFondo({ id: arte.objeto, url: arte.url, tipo: arte.tipo || "subida" });
  }

  function quitar() {
    setFondo(null);
    setAvisoGenerar("");
    onCambio("", "");
  }

  /** Vuelve a la imagen ORIGINAL del artículo: limpia el archivo compuesto/subido, de modo
   *  que `imagen_url` cae de nuevo a `imagen_fuente` (la URL original). */
  function usarOriginal() {
    if (!imagenFuente) return;
    setFondo(null);
    setAvisoGenerar("");
    onCambio("", imagenFuente);
  }
  // Ofrecemos el botón solo si hay original Y no es ya la imagen mostrada.
  const mostrandoOriginal = !imagen && (imagenUrl || "") === imagenFuente;

  const trabajando =
    subir.isPending || generar.isPending || generandoIA || componer.isPending || componiendo;
  const ocupado = trabajando || !!disabled;

  const fuente = (
    <FuenteFondo
      idPrefijo={idPrefijo}
      compacto={!!src}
      ocupado={ocupado}
      subiendo={subir.isPending}
      generandoIA={generar.isPending || generandoIA}
      prompt={prompt}
      onPrompt={setPrompt}
      onSubir={() => inputRef.current?.click()}
      onBiblioteca={() => setGaleriaAbierta(true)}
      onGenerar={() => generar.mutate()}
      avisoGenerar={avisoGenerar}
      mostrarOriginal={!!imagenFuente && !mostrandoOriginal}
      onOriginal={usarOriginal}
    />
  );

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen <span className="font-normal text-muted-foreground">(opcional)</span>
        </Label>
        {publicacionId && (
          <Button
            asChild
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            disabled={!!disabled}
          >
            <Link to="/estudio" state={{ publicacionId, marca, red, copy, imagen: imagen || undefined }}>
              <Wand2 className="mr-1 h-3.5 w-3.5" />
              Abrir en Estudio
            </Link>
          </Button>
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

      {src ? (
        <div className="space-y-2">
          <div className="relative inline-block">
            <img
              src={src}
              alt="Imagen de la publicación"
              onLoad={(e) =>
                setRatioReal(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)
              }
              className="max-h-56 w-auto rounded-md border border-border object-contain"
            />
            {componiendo && (
              <div className="absolute inset-0 flex items-center justify-center rounded-md bg-background/60">
                <Loader2 className="h-5 w-5 animate-spin" />
              </div>
            )}
            <Button
              type="button"
              variant="destructive"
              size="icon"
              className="absolute right-1.5 top-1.5 h-7 w-7"
              onClick={quitar}
              disabled={ocupado}
              aria-label="Quitar imagen"
              title="Quitar imagen"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {aspectoFueraDeEstandar && tamRed && red && (
            <p className="flex items-start gap-1.5 text-xs text-amber-600 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                La relación de aspecto no es la {tamRed.ratio} estándar de {nombreRed(red)}: se
                recortará. {publicacionId ? "Adáptala en el Estudio" : "Recórtala"} a {tamRed.px} px.
              </span>
            </p>
          )}

          {/* Ajustes de la placa: solo cuando hay un fondo de esta sesión y la marca compone. */}
          {componible && fondo && (
            <div className="space-y-2 rounded-md border border-dashed border-border bg-muted/20 p-2.5">
              <div className="grid gap-2 sm:grid-cols-2">
                <div className="space-y-1">
                  <Label htmlFor={`${idPrefijo}-titular`} className="text-xs">
                    Titular en la placa
                  </Label>
                  <Input
                    id={`${idPrefijo}-titular`}
                    value={titular}
                    onChange={(e) => {
                      titularTocado.current = true;
                      setTitular(e.target.value);
                    }}
                    placeholder="Texto del titular…"
                    disabled={ocupado}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor={`${idPrefijo}-etiqueta`} className="text-xs">
                    Etiqueta <span className="text-muted-foreground">(vacío = la de marca)</span>
                  </Label>
                  <Input
                    id={`${idPrefijo}-etiqueta`}
                    value={etiqueta}
                    onChange={(e) => setEtiqueta(e.target.value)}
                    placeholder="ÚLTIMA HORA…"
                    disabled={ocupado}
                  />
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fondo && componer.mutate(fondo)}
                  disabled={ocupado}
                >
                  {componiendo ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="h-3.5 w-3.5" />
                  )}
                  Re-componer
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => guardar.mutate()}
                  disabled={ocupado || guardar.isPending}
                >
                  {guardar.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  Guardar fondo en biblioteca
                </Button>
              </div>
            </div>
          )}

          {/* Sin marca: aún se puede guardar el fondo (sin placa) para reutilizarlo. */}
          {!componible && fondo && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => guardar.mutate()}
              disabled={ocupado || guardar.isPending}
            >
              {guardar.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              Guardar en biblioteca
            </Button>
          )}

          {/* Cambiar de fondo desde la propia preview. */}
          {fuente}
        </div>
      ) : (
        fuente
      )}

      <SelectorArtes
        open={galeriaAbierta}
        onCerrar={() => setGaleriaAbierta(false)}
        onSeleccionar={elegirArte}
        marca={marca}
      />
    </div>
  );
}

/** Selector de origen del fondo: biblioteca · subir · generar con IA. */
function FuenteFondo({
  idPrefijo,
  compacto,
  ocupado,
  subiendo,
  generandoIA,
  prompt,
  onPrompt,
  onSubir,
  onBiblioteca,
  onGenerar,
  avisoGenerar,
  mostrarOriginal,
  onOriginal,
}: {
  idPrefijo: string;
  compacto?: boolean;
  ocupado: boolean;
  subiendo: boolean;
  generandoIA: boolean;
  prompt: string;
  onPrompt: (v: string) => void;
  onSubir: () => void;
  onBiblioteca: () => void;
  onGenerar: () => void;
  avisoGenerar: string;
  /** La pieza trae imagen original (RSS de marca propia) y NO es la mostrada ahora. */
  mostrarOriginal?: boolean;
  onOriginal?: () => void;
}) {
  return (
    <div className="space-y-2.5 rounded-md border border-dashed border-border bg-muted/20 p-3">
      {!compacto && (
        <p className="text-xs text-muted-foreground">
          Elige de dónde sale la foto/fondo (puedes subir una foto real, elegir de la biblioteca
          o generarla con IA):
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {mostrarOriginal && (
          <Button type="button" variant="outline" size="sm" onClick={onOriginal} disabled={ocupado}>
            <ImagePlus className="h-4 w-4" />
            Usar imagen original
          </Button>
        )}
        <Button type="button" variant="outline" size="sm" onClick={onBiblioteca} disabled={ocupado}>
          <Library className="h-4 w-4" />
          Biblioteca
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onSubir} disabled={ocupado}>
          {subiendo ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Subir foto
        </Button>
        <span className="text-xs text-muted-foreground">o genera con IA:</span>
      </div>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Label htmlFor={`${idPrefijo}-prompt`} className="sr-only">
          Describe la imagen a generar
        </Label>
        <Input
          id={`${idPrefijo}-prompt`}
          value={prompt}
          onChange={(e) => onPrompt(e.target.value)}
          placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer…"
          disabled={ocupado}
          onKeyDown={(e) => {
            if (e.key === "Enter" && prompt.trim() && !ocupado) {
              e.preventDefault();
              onGenerar();
            }
          }}
        />
        <Button
          type="button"
          size="sm"
          onClick={onGenerar}
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
      {!compacto && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <ImageOff className="h-3.5 w-3.5" />
          La placa de marca y el copy-in se aplican encima automáticamente.
        </p>
      )}
    </div>
  );
}
