/**
 * Estudio de imagen — superficie de "lienzo + acciones".
 *
 * Una pieza visual se trabaja en tres pasos encadenados sobre el ALMACÉN de media
 * (cada paso devuelve el NOMBRE del objeto resultante):
 *
 *  1. Origen: subir una foto (`POST /api/media`) o partir "desde cero" (solo generativo).
 *  2. Generar variantes (IA): `imagenesGenerar` lanza N generaciones (una por variante);
 *     cada una se SONDEA por separado con `useGeneracion` dentro de un componente hijo
 *     `<Variante>` (un hook por generación, ya que los hooks no pueden ir en un bucle).
 *     Al completar, cada candidata aparece en la rejilla.
 *  3. Sobre la candidata ACTIVA: editar (determinista, sin coste) o expandir (generativo).
 *     Cada acción lanza UNA generación que se sondea con un `useGeneracion` dedicado y
 *     reemplaza la imagen activa por el resultado.
 *
 * Elegir final: "Usar en la pieza" (si se abrió desde una publicación, vía router state)
 * y "Descargar".
 *
 * Errores 400 "no configurada" (generar/expandir sin proveedor de imagen): aviso ámbar
 * amable, nunca toast rojo.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Crop,
  Download,
  ImagePlus,
  Loader2,
  Maximize2,
  ShieldCheck,
  Sparkles,
  Type,
  Upload,
  Wand2,
} from "lucide-react";
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { api, ApiError, urlMedia } from "@/lib/api";
import type { FormatoImagen, Generacion, ImagenActiva } from "@/types";

/** Formatos de red con su descripción de relación de aspecto. */
const FORMATOS: { id: FormatoImagen; etiqueta: string }[] = [
  { id: "vertical", etiqueta: "Vertical (9:16)" },
  { id: "feed", etiqueta: "Feed (4:5)" },
  { id: "cuadrado", etiqueta: "Cuadrado (1:1)" },
  { id: "horizontal", etiqueta: "Horizontal (16:9)" },
];

/** Marcas con placa visual disponible (las únicas que el backend acepta en `op: placa`). */
const MARCAS_PLACA = [
  { id: "unotv", nombre: "UnoTV" },
  { id: "claro-sports", nombre: "Claro Sports" },
];

/** Formato sugerido por red (heurística sencilla; el usuario lo puede cambiar). */
function formatoPorRed(red?: string): FormatoImagen {
  const r = (red || "").toLowerCase();
  if (r.includes("tiktok") || r.includes("reel") || r.includes("story") || r.includes("short"))
    return "vertical";
  if (r.includes("youtube") || r.includes("x") || r.includes("twitter")) return "horizontal";
  return "feed";
}

/** Contexto que puede llegar desde una pieza (router state al abrir el Estudio). */
interface ContextoPieza {
  publicacionId?: string;
  copy?: string;
  marca?: string;
  red?: string;
  imagen?: string;
}

/** Resultado de imagen de una generación completada. */
function resultadoImagen(g: Generacion | null): ImagenActiva | null {
  if (!g || g.estado !== "completado") return null;
  const r = g.resultado;
  if (r?.id && r?.url) return { id: r.id, url: r.url };
  return null;
}

/**
 * Sondea UNA generación de variante y reporta su estado al padre. Es un componente
 * (y no un bucle de hooks) porque `useGeneracion` debe llamarse una vez por generación.
 */
function Variante({
  generacion,
  activa,
  onCompletada,
  onClick,
}: {
  generacion: Generacion;
  activa: boolean;
  onCompletada: (img: ImagenActiva) => void;
  onClick: (img: ImagenActiva) => void;
}) {
  const { generacion: g, ejecutando, iniciar } = useGeneracion();
  const iniciadoRef = React.useRef(false);

  // Arranca el seguimiento una sola vez con la generación recibida del POST.
  React.useEffect(() => {
    if (iniciadoRef.current) return;
    iniciadoRef.current = true;
    iniciar(generacion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const img = resultadoImagen(g ?? generacion);
  const reportadoRef = React.useRef(false);
  React.useEffect(() => {
    if (img && !reportadoRef.current) {
      reportadoRef.current = true;
      onCompletada(img);
    }
  }, [img, onCompletada]);

  const estado = (g ?? generacion).estado;

  if (estado === "error") {
    return (
      <div className="flex aspect-square items-center justify-center rounded-md border border-dashed border-border bg-muted/20 p-2 text-center text-xs text-muted-foreground">
        No se pudo generar esta variante.
      </div>
    );
  }

  if (!img || ejecutando) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-md border border-dashed border-border bg-muted/20">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onClick(img)}
      className={`overflow-hidden rounded-md border-2 transition ${
        activa ? "border-primary ring-2 ring-primary/30" : "border-border hover:border-primary/50"
      }`}
      title="Usar esta candidata"
    >
      <img
        src={urlMedia(img.url)}
        alt="Candidata generada"
        className="aspect-square w-full object-cover"
      />
    </button>
  );
}

export default function Estudio() {
  const location = useLocation();
  const navigate = useNavigate();
  const ctx = (location.state ?? {}) as ContextoPieza;

  // Catálogo de marcas (para los selectores).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // --- Estado de configuración (preconfigurado desde el contexto de la pieza) ---
  const [prompt, setPrompt] = React.useState("");
  const [marca, setMarca] = React.useState(ctx.marca ?? "");
  const [formato, setFormato] = React.useState<FormatoImagen>(formatoPorRed(ctx.red));
  const [variantes, setVariantes] = React.useState(2);
  const [aviso, setAviso] = React.useState("");

  // --- Lienzo: candidatas (de generar/subir/editar) y la imagen ACTIVA ---
  const [candidatas, setCandidatas] = React.useState<ImagenActiva[]>([]);
  const [activa, setActiva] = React.useState<ImagenActiva | null>(null);
  // Generaciones de variantes en curso (una `<Variante>` por cada una).
  const [variantesGen, setVariantesGen] = React.useState<Generacion[]>([]);

  // Si el contexto trae una imagen ya adjunta a la pieza, arranca con ella activa.
  React.useEffect(() => {
    if (ctx.imagen) {
      const img = { id: ctx.imagen, url: ctx.imagen };
      setCandidatas((c) => (c.some((x) => x.id === img.id) ? c : [img, ...c]));
      setActiva((a) => a ?? img);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function añadirCandidata(img: ImagenActiva, hacerActiva = true) {
    setCandidatas((c) => (c.some((x) => x.id === img.id) ? c : [...c, img]));
    if (hacerActiva) setActiva(img);
  }

  // --- Subir una foto de origen ---
  const inputRef = React.useRef<HTMLInputElement>(null);
  const subir = useMutation({
    mutationFn: (archivo: File) => api.subirMedia(archivo),
    onSuccess: (data) => {
      añadirCandidata({ id: data.id, url: data.url });
      toast.success("Imagen subida");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo subir la imagen."),
  });

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    const archivo = e.target.files?.[0];
    if (archivo) subir.mutate(archivo);
    if (inputRef.current) inputRef.current.value = "";
  }

  // --- Generar variantes (IA): lanza N generaciones, se sondean en `<Variante>` ---
  const generar = useMutation({
    mutationFn: () =>
      api.imagenesGenerar({
        prompt: prompt.trim(),
        marca: marca || undefined,
        formato,
        variantes,
      }),
    onSuccess: (data) => {
      setAviso("");
      setVariantesGen(data.generaciones);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setAviso(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudieron generar las variantes.");
    },
  });

  const generandoVariantes =
    generar.isPending || variantesGen.some((g) => g.estado === "ejecutando");

  // --- Operación sobre la imagen activa (editar determinista / expandir generativo) ---
  // Un único `useGeneracion` dedicado: cada acción lanza una generación y la sondea.
  const op = useGeneracion();
  const opTerminalRef = React.useRef<string | null>(null);
  const [opAviso, setOpAviso] = React.useState("");
  const [opEtiqueta, setOpEtiqueta] = React.useState("");

  React.useEffect(() => {
    const g = op.generacion;
    if (!g || g.id === opTerminalRef.current) return;
    if (g.estado === "completado") {
      opTerminalRef.current = g.id;
      const img = resultadoImagen(g);
      if (img) {
        añadirCandidata(img);
        toast.success(`${opEtiqueta || "Operación"} aplicada`);
      }
    } else if (g.estado === "error") {
      opTerminalRef.current = g.id;
      toast.error(g.error || "No se pudo completar la operación.");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [op.generacion]);

  const lanzarEditar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.imagenesEditar>[0]) => api.imagenesEditar(cuerpo),
    onSuccess: (data) => {
      setOpAviso("");
      op.iniciar(data.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo editar la imagen.");
    },
  });

  const lanzarExpandir = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.imagenesExpandir>[0]) => api.imagenesExpandir(cuerpo),
    onSuccess: (data) => {
      setOpAviso("");
      op.iniciar(data.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setOpAviso(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo expandir la imagen.");
    },
  });

  const opEjecutando = op.ejecutando || lanzarEditar.isPending || lanzarExpandir.isPending;

  // --- Revisión legal/editorial (gate humano, no bloquea publicar) ---
  // Job "qa-editorial" que VE la imagen activa y devuelve un checklist ✅/⚠️/❌ en `salida`
  // (texto en vivo). Hook dedicado y región propia para no chocar con editar/expandir.
  const revision = useGeneracion();
  const lanzarRevisar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.imagenesRevisar>[0]) => api.imagenesRevisar(cuerpo),
    onSuccess: (data) => revision.iniciar(data.generacion),
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        toast.error(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo revisar la imagen.");
    },
  });
  const revisando = revision.ejecutando || lanzarRevisar.isPending;
  const textoRevision = revision.generacion?.salida ?? "";

  function editar(etiqueta: string, cuerpo: Omit<Parameters<typeof api.imagenesEditar>[0], "imagen">) {
    if (!activa) return;
    setOpEtiqueta(etiqueta);
    lanzarEditar.mutate({ imagen: activa.id, ...cuerpo });
  }

  // --- Parámetros de las operaciones (controles inline) ---
  const [maxPx, setMaxPx] = React.useState("1080");
  const [pesoMb, setPesoMb] = React.useState("2");
  const [placaTexto, setPlacaTexto] = React.useState("");
  const [placaMarca, setPlacaMarca] = React.useState("unotv");
  const [expStrength, setExpStrength] = React.useState("0.6");
  const [expLado, setExpLado] = React.useState<
    "auto" | "arriba" | "abajo" | "izquierda" | "derecha"
  >("auto");

  // --- Elegir final ---
  const usarEnPieza = useMutation({
    mutationFn: () => api.actualizarPublicacion(ctx.publicacionId!, { imagen: activa!.id }),
    onSuccess: () => {
      toast.success("Imagen aplicada a la pieza");
      navigate(-1);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo aplicar a la pieza."),
  });

  const srcActiva = activa ? urlMedia(activa.url) : "";

  return (
    <>
      <PageHeader
        titulo="Estudio de imagen"
        descripcion="Genera variantes, edita (recorte, peso, placa) y expande una imagen. Luego úsala en la pieza o descárgala."
      />

      {ctx.publicacionId && (
        <div className="mb-4 max-w-3xl rounded-md border border-border bg-muted/20 p-3 text-sm">
          <p className="font-medium">Trabajando para una pieza</p>
          {ctx.copy && (
            <p className="mt-1 line-clamp-3 text-muted-foreground">{ctx.copy}</p>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            {ctx.marca ? `Marca: ${ctx.marca}. ` : ""}
            {ctx.red ? `Red: ${ctx.red}.` : ""}
          </p>
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        {/* Columna izquierda: lienzo + candidatas */}
        <div className="space-y-4">
          <div className="space-y-2 rounded-md border border-border p-3">
            <Label className="text-sm font-medium">Lienzo</Label>
            {srcActiva ? (
              <img
                src={srcActiva}
                alt="Imagen activa"
                className="max-h-[26rem] w-auto rounded-md border border-border object-contain"
              />
            ) : (
              <div className="flex h-48 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                Sube una foto o genera variantes para empezar.
              </div>
            )}
            {opEjecutando && (
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Procesando…
              </div>
            )}
            {opAviso && (
              <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                {opAviso}
              </p>
            )}
          </div>

          {/* Candidatas */}
          {(candidatas.length > 0 || variantesGen.length > 0) && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">Candidatas</Label>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {variantesGen.map((g) => (
                  <Variante
                    key={g.id}
                    generacion={g}
                    activa={false}
                    onCompletada={(img) => añadirCandidata(img, false)}
                    onClick={setActiva}
                  />
                ))}
                {candidatas.map((img) => (
                  <button
                    key={img.id}
                    type="button"
                    onClick={() => setActiva(img)}
                    className={`overflow-hidden rounded-md border-2 transition ${
                      activa?.id === img.id
                        ? "border-primary ring-2 ring-primary/30"
                        : "border-border hover:border-primary/50"
                    }`}
                    title="Usar esta imagen"
                  >
                    <img
                      src={urlMedia(img.url)}
                      alt="Candidata"
                      className="aspect-square w-full object-cover"
                    />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Columna derecha: acciones */}
        <div className="space-y-6">
          {/* Origen */}
          <section className="space-y-2">
            <Label className="text-sm font-medium">Origen</Label>
            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              onChange={onArchivo}
              className="hidden"
              aria-label="Subir imagen de origen"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => inputRef.current?.click()}
              disabled={subir.isPending}
            >
              {subir.isPending ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Upload className="mr-1 h-4 w-4" />
              )}
              Subir foto
            </Button>
            <p className="text-xs text-muted-foreground">o genera desde cero abajo.</p>
          </section>

          {/* Generar variantes */}
          <section className="space-y-3 rounded-md border border-border p-3">
            <Label htmlFor="estudio-prompt" className="text-sm font-medium">
              Generar variantes
            </Label>
            <Textarea
              id="estudio-prompt"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe la imagen: p. ej. estadio iluminado al atardecer, estilo editorial deportivo…"
              rows={3}
              disabled={generandoVariantes}
            />
            <div className="space-y-1.5">
              <Label htmlFor="estudio-marca" className="text-xs">
                Marca
              </Label>
              <SelectorMarca
                id="estudio-marca"
                marcas={marcas}
                valor={marca}
                onCambio={setMarca}
                incluirNinguna
                etiquetaNinguna="Sin marca"
                placeholder="Sin marca"
                ariaLabel="Marca para generar"
                className="w-full"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="estudio-formato" className="text-xs">
                  Formato
                </Label>
                <Select
                  value={formato}
                  onValueChange={(v) => setFormato(v as FormatoImagen)}
                >
                  <SelectTrigger id="estudio-formato" aria-label="Formato">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {FORMATOS.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.etiqueta}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="estudio-variantes" className="text-xs">
                  Variantes
                </Label>
                <Select
                  value={String(variantes)}
                  onValueChange={(v) => setVariantes(Number(v))}
                >
                  <SelectTrigger id="estudio-variantes" aria-label="Número de variantes">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[1, 2, 3, 4].map((n) => (
                      <SelectItem key={n} value={String(n)}>
                        {n}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => generar.mutate()}
              disabled={generandoVariantes || prompt.trim().length === 0}
            >
              {generandoVariantes ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1 h-4 w-4" />
              )}
              {generandoVariantes ? "Generando…" : "Generar variantes"}
            </Button>
            {aviso && (
              <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                {aviso}
              </p>
            )}
          </section>

          {/* Editar (determinista) + Expandir (generativo) sobre la activa */}
          <section className="space-y-3 rounded-md border border-border p-3">
            <Label className="text-sm font-medium">Editar la imagen activa</Label>
            {!activa ? (
              <p className="text-xs text-muted-foreground">
                Selecciona una candidata para editarla.
              </p>
            ) : (
              <div className="space-y-3">
                {/* Recortar a formato */}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={opEjecutando}
                  onClick={() => editar("Recorte", { op: "recortar", formato })}
                >
                  <Crop className="mr-1 h-4 w-4" />
                  Recortar a {formato}
                </Button>

                {/* Redimensionar */}
                <div className="flex items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="estudio-max" className="text-xs">
                      Lado máx. (px)
                    </Label>
                    <Input
                      id="estudio-max"
                      type="number"
                      value={maxPx}
                      onChange={(e) => setMaxPx(e.target.value)}
                      className="w-28"
                      disabled={opEjecutando}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando || !Number(maxPx)}
                    onClick={() =>
                      editar("Redimensionado", { op: "redimensionar", max: Number(maxPx) })
                    }
                  >
                    Redimensionar
                  </Button>
                </div>

                {/* Comprimir */}
                <div className="flex items-end gap-2">
                  <div className="space-y-1">
                    <Label htmlFor="estudio-peso" className="text-xs">
                      Peso máx. (MB)
                    </Label>
                    <Input
                      id="estudio-peso"
                      type="number"
                      step="0.1"
                      value={pesoMb}
                      onChange={(e) => setPesoMb(e.target.value)}
                      className="w-28"
                      disabled={opEjecutando}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando}
                    onClick={() =>
                      editar("Compresión", {
                        op: "comprimir",
                        peso_max_mb: Number(pesoMb) || 2,
                      })
                    }
                  >
                    Comprimir
                  </Button>
                </div>

                {/* Extender (relleno de borde al formato) */}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={opEjecutando}
                  onClick={() =>
                    editar("Extensión", { op: "extender", formato, metodo: "borde" })
                  }
                >
                  <Maximize2 className="mr-1 h-4 w-4" />
                  Extender a {formato}
                </Button>

                {/* Placa (solo unotv / claro-sports) */}
                <div className="space-y-1.5 rounded-md border border-border p-2">
                  <Label htmlFor="estudio-placa" className="flex items-center gap-1 text-xs">
                    <Type className="h-3.5 w-3.5" />
                    Placa con texto
                  </Label>
                  <Input
                    id="estudio-placa"
                    value={placaTexto}
                    onChange={(e) => setPlacaTexto(e.target.value)}
                    placeholder="Texto de la placa"
                    disabled={opEjecutando}
                  />
                  <Select value={placaMarca} onValueChange={setPlacaMarca}>
                    <SelectTrigger aria-label="Marca de la placa">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MARCAS_PLACA.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.nombre}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando || placaTexto.trim().length === 0}
                    onClick={() =>
                      editar("Placa", {
                        op: "placa",
                        texto: placaTexto.trim(),
                        marca: placaMarca,
                        formato,
                      })
                    }
                  >
                    Añadir placa
                  </Button>
                </div>

                {/* Expandir (generativo, con coste) */}
                <div className="space-y-1.5 rounded-md border border-border p-2">
                  <Label className="flex items-center gap-1 text-xs">
                    <Wand2 className="h-3.5 w-3.5" />
                    Expandir (IA)
                  </Label>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor="estudio-strength" className="text-xs text-muted-foreground">
                        Fidelidad
                      </Label>
                      <Input
                        id="estudio-strength"
                        type="number"
                        step="0.1"
                        min="0"
                        max="1"
                        value={expStrength}
                        onChange={(e) => setExpStrength(e.target.value)}
                        disabled={opEjecutando}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor="estudio-lado" className="text-xs text-muted-foreground">
                        Lado
                      </Label>
                      <Select
                        value={expLado}
                        onValueChange={(v) =>
                          setExpLado(v as typeof expLado)
                        }
                      >
                        <SelectTrigger id="estudio-lado" aria-label="Lado a expandir">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {(["auto", "arriba", "abajo", "izquierda", "derecha"] as const).map(
                            (l) => (
                              <SelectItem key={l} value={l}>
                                {l}
                              </SelectItem>
                            ),
                          )}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando}
                    onClick={() => {
                      if (!activa) return;
                      setOpEtiqueta("Expansión");
                      lanzarExpandir.mutate({
                        imagen: activa.id,
                        formato,
                        marca: marca || undefined,
                        strength: Number(expStrength),
                        lado: expLado,
                      });
                    }}
                  >
                    Expandir
                  </Button>
                </div>
              </div>
            )}
          </section>

          {/* Revisión legal/editorial (gate humano; no bloquea publicar) */}
          <section className="space-y-2 rounded-md border border-border p-3">
            <Label className="flex items-center gap-1 text-sm font-medium">
              <ShieldCheck className="h-4 w-4" />
              Revisión (legal/editorial)
            </Label>
            {!activa ? (
              <p className="text-xs text-muted-foreground">
                Selecciona una imagen para revisarla.
              </p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground">
                  Pasa la imagen activa por las reglas de imagen y obtén un checklist ✅/⚠️/❌.
                  No bloquea publicar: la decisión final es tuya.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={revisando}
                  onClick={() => {
                    if (!activa) return;
                    lanzarRevisar.mutate({ imagen: activa.id, marca: marca || undefined });
                  }}
                >
                  {revisando ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <ShieldCheck className="mr-1 h-4 w-4" />
                  )}
                  {revisando ? "Revisando…" : "Revisar (legal/editorial)"}
                </Button>
                {textoRevision && (
                  <pre className="max-h-72 overflow-auto whitespace-pre-wrap rounded-md bg-muted/30 px-3 py-2 text-xs text-foreground">
                    {textoRevision}
                  </pre>
                )}
              </>
            )}
          </section>

          {/* Elegir final */}
          <section className="space-y-2 rounded-md border border-border p-3">
            <Label className="text-sm font-medium">Elegir final</Label>
            {!activa ? (
              <p className="text-xs text-muted-foreground">
                Selecciona una imagen para finalizar.
              </p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {ctx.publicacionId && (
                  <Button
                    type="button"
                    size="sm"
                    onClick={() => usarEnPieza.mutate()}
                    disabled={usarEnPieza.isPending}
                  >
                    {usarEnPieza.isPending ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <ImagePlus className="mr-1 h-4 w-4" />
                    )}
                    Usar en la pieza
                  </Button>
                )}
                <Button asChild variant="outline" size="sm">
                  <a href={srcActiva} download>
                    <Download className="mr-1 h-4 w-4" />
                    Descargar
                  </a>
                </Button>
              </div>
            )}
          </section>
        </div>
      </div>
    </>
  );
}
