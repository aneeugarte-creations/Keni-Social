/**
 * Editor de imagen para piezas sin marca: el usuario elige o sube una foto/fondo sin procesamiento
 * de placa. Se adjunta tal cual a la pieza.
 *
 * Tres orígenes de imagen:
 *   - **Galería de artes**: elegir un arte ya guardado (`SelectorArtes`).
 *   - **Subir**: un archivo del equipo (`POST /api/media`).
 *   - **Generar con IA**: a partir de un prompt (`POST /api/media/generar`).
 *
 * El componente es controlado: el padre guarda el `nombre` de la imagen final (vacío = sin imagen)
 * y lo incluye al guardar la pieza.
 */
import { useMutation } from "@tanstack/react-query";
import {
  ImagePlus,
  Library,
  Save,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { Aviso } from "@/components/comunes/Aviso";
import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorArtes } from "@/components/media/SelectorArtes";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { useGeneracion } from "@/hooks/use-generacion";
import { ApiError, api, mensajeError, urlMedia } from "@/lib/api";
import { nombreRed, tamanoRed } from "@/pages/piezas/meta";
import type { Arte, TipoArte } from "@/types";

/** Convierte una relación tipo "16:9" o "1.91:1" en un número (ancho/alto). */
function ratioDe(txt: string): number | null {
  const [w, h] = txt.split(/[:/]/).map((n) => parseFloat(n));
  return w && h ? w / h : null;
}

/** Fondo elegido en esta sesión. */
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
  piezaId?: string;
  red?: string;
  copy?: string;
}

export function EditorImagen({
  imagen,
  imagenUrl,
  onCambio,
  disabled,
  idPrefijo = "img",
  piezaId,
  red,
  copy,
}: EditorImagenProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = React.useState("");
  // Aviso amable cuando la generación no está configurada (400).
  const [avisoGenerar, setAvisoGenerar] = React.useState("");
  // Galería de artes.
  const [galeriaAbierta, setGaleriaAbierta] = React.useState(false);
  // Fondo elegido en esta sesión.
  const [fondo, setFondo] = React.useState<Fondo | null>(null);
  const src = urlMedia(imagenUrl || imagen);

  // Aspect-ratio real de la imagen (medido al cargar) frente al recomendado de la red.
  const [ratioReal, setRatioReal] = React.useState<number | null>(null);
  React.useEffect(() => {
    setRatioReal(null);
  }, [src]);
  const tamRed = red ? tamanoRed(red) : null;
  const ratioRec = tamRed ? ratioDe(tamRed.ratio) : null;
  // Warning si la relación de aspecto de la imagen cargada no coincide con el estándar de la red.
  const aspectoFueraDeEstandar =
    ratioReal != null &&
    ratioRec != null &&
    Math.abs(ratioReal - ratioRec) / ratioRec > 0.1;

  /** Aplica un fondo recién elegido: lo recuerda y lo adjunta. */
  const aplicarFondo = React.useCallback(
    (base: Fondo) => {
      setFondo(base);
      onCambio(base.id, base.url);
    },
    [onCambio],
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
    mutationFn: () => api.generarMedia({ prompt: prompt.trim(), pieza_id: piezaId }),
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

  // --- Guardar el fondo en la galería (durable + reutilizable) --- //
  const guardar = useMutation({
    mutationFn: () => {
      if (!fondo) throw new Error("Elige primero un fondo.");
      return api.guardarArte({ objeto: fondo.id, tipo: fondo.tipo });
    },
    onSuccess: () => toast.success("Fondo guardado en la galería"),
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

  const trabajando =
    subir.isPending ||
    generar.isPending ||
    generandoIA;
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
      onTexto={() => setGaleriaAbierta(true)}
      onGenerar={() => generar.mutate()}
      avisoGenerar={avisoGenerar}
    />
  );

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1.5">
          <ImagePlus className="h-4 w-4 text-muted-foreground" />
          Imagen
        </Label>
        {piezaId && (
          <Button
            asChild={!disabled}
            type="button"
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            disabled={!!disabled}
            onClick={
              disabled
                ? undefined
                : () => {
                    // Link navigation handled by asChild when not disabled
                  }
            }
          >
            {disabled ? (
              <span>
                <Wand2 className="mr-1 h-3.5 w-3.5" />
                Abrir en Estudio
              </span>
            ) : (
              <Link to="/publicaciones/estudio" state={{ piezaId, red, copy, imagen: imagen || undefined }}>
                <Wand2 className="mr-1 h-3.5 w-3.5" />
                Abrir en Estudio
              </Link>
            )}
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
          <FilaConAcciones
            como="div"
            kebab="nunca"
            realce
            acciones={
              [
                fondo && {
                  etiqueta: "Guardar en la galería",
                  icono: Save,
                  onClick: () => guardar.mutate(),
                  deshabilitado: ocupado || guardar.isPending,
                },
                {
                  etiqueta: "Quitar imagen",
                  icono: Trash2,
                  onClick: async () => {
                    if (
                      await confirmar({
                        mensaje: "¿Quitar la imagen?",
                        destructivo: true,
                        textoConfirmar: "Quitar",
                      })
                    )
                      quitar();
                  },
                  destructivo: true,
                  deshabilitado: ocupado,
                },
              ].filter(Boolean) as EntradaMenuContextual[]
            }
          >
            <div className="relative inline-block">
              <img
                src={src}
                alt="Imagen de la publicación"
                onLoad={(e) =>
                  setRatioReal(e.currentTarget.naturalWidth / e.currentTarget.naturalHeight)
                }
                className="max-h-56 w-auto rounded-md border border-border object-contain transition-colors hover:border-keni-300 focus-within:border-keni-300"
              />
            </div>
          </FilaConAcciones>

          {aspectoFueraDeEstandar && tamRed && red && (
            <Aviso>
              La relación de aspecto no es la {tamRed.ratio} estándar de {nombreRed(red)}: se
              recortará. {piezaId ? "Adáptala en el Estudio" : "Recórtala"} a {tamRed.px} px.
            </Aviso>
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
      />
    </div>
  );
}

/** Selector de origen del fondo: texto · subir · generar con IA. */
function FuenteFondo({
  idPrefijo,
  compacto,
  ocupado,
  subiendo,
  generandoIA,
  prompt,
  onPrompt,
  onSubir,
  onTexto,
  onGenerar,
  avisoGenerar,
}: {
  idPrefijo: string;
  compacto?: boolean;
  ocupado: boolean;
  subiendo: boolean;
  generandoIA: boolean;
  prompt: string;
  onPrompt: (v: string) => void;
  onSubir: () => void;
  onTexto: () => void;
  onGenerar: () => void;
  avisoGenerar: string;
}) {
  return (
    <div className="space-y-2.5 rounded-md border border-dashed border-border bg-muted/20 p-3">
      {!compacto && (
        <p className="text-xs text-muted-foreground">
          Elige la fuente:
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onTexto} disabled={ocupado}>
          <Library className="h-4 w-4" />
          Galería
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onSubir} disabled={ocupado}>
          {subiendo ? <Spinner className="h-4 w-4" /> : <Upload className="h-4 w-4" />}
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
          placeholder="Ej. estadio iluminado al atardecer"
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
          {generandoIA ? <Spinner className="h-4 w-4" /> : <MarcaIA costo />}
          {generandoIA ? "Generando…" : "Generar con IA"}
        </Button>
      </div>
      {avisoGenerar && <Aviso icono={false}>{avisoGenerar}</Aviso>}
    </div>
  );
}
