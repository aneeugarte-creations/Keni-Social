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
  Library,
  Loader2,
  Maximize2,
  Settings2,
  ShieldCheck,
  Stamp,
  Trash2,
  Upload,
  Wand2,
} from "lucide-react";
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { EditorPlantillaMarca } from "@/components/editor/EditorPlantillaMarca";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
 * Persistencia de la SESIÓN del Estudio en `sessionStorage` (sobrevive a cambiar de
 * página y volver dentro de la misma pestaña). Las imágenes son objetos durables del
 * almacén; lo que se perdía era la VISTA (candidatas, activa, variantes en vuelo). Los
 * trabajos de IA siguen corriendo en el servidor: al volver, reanudamos su sondeo
 * (las generaciones `op`/`revisión` por su `persistKey`; las variantes re-sondean por id).
 * La clave incluye el id de la pieza para no mezclar sesiones de piezas distintas.
 */
interface SesionEstudio {
  candidatas: ImagenActiva[];
  activaId: string | null;
  variantesGen: Generacion[];
  prompt: string;
  marca: string;
  formato: FormatoImagen;
  variantes: number;
}

function claveSesion(pubId?: string): string {
  return "keni:estudio:" + (pubId || "libre");
}

function cargarSesion(clave: string): Partial<SesionEstudio> {
  try {
    const crudo = sessionStorage.getItem(clave);
    return crudo ? (JSON.parse(crudo) as Partial<SesionEstudio>) : {};
  } catch {
    return {};
  }
}

function guardarSesion(clave: string, s: SesionEstudio): void {
  try {
    sessionStorage.setItem(clave, JSON.stringify(s));
  } catch {
    // Sin persistencia si el almacenamiento falla (modo privado, cuota llena…). No es fatal.
  }
}

/**
 * Sondea UNA generación de variante y reporta su estado al padre. Es un componente
 * (y no un bucle de hooks) porque `useGeneracion` debe llamarse una vez por generación.
 */
function Variante({
  generacion,
  onResuelta,
  onFallida,
}: {
  generacion: Generacion;
  onResuelta: (id: string, img: ImagenActiva) => void;
  onFallida: (id: string) => void;
}) {
  // Sin persistKey propio: la lista `variantesGen` se persiste a nivel de sesión y al
  // remontar este componente re-sondea por id (la generación sigue viva en el servidor).
  const { generacion: g, iniciar } = useGeneracion();
  const iniciadoRef = React.useRef(false);

  // Arranca (o REANUDA) el seguimiento una sola vez con la generación recibida.
  React.useEffect(() => {
    if (iniciadoRef.current) return;
    iniciadoRef.current = true;
    iniciar(generacion);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const actual = g ?? generacion;
  const img = resultadoImagen(actual);

  // Al RESOLVERSE (imagen lista) o FALLAR, lo reportamos UNA vez: el padre la saca de
  // `variantesGen` y la mueve a `candidatas` (evita el duplicado y deja solo spinners aquí).
  const reportadoRef = React.useRef(false);
  React.useEffect(() => {
    if (reportadoRef.current) return;
    if (img) {
      reportadoRef.current = true;
      onResuelta(generacion.id, img);
    } else if (actual.estado === "error") {
      reportadoRef.current = true;
      onFallida(generacion.id);
    }
  }, [img, actual.estado, generacion.id, onResuelta, onFallida]);

  if (actual.estado === "error") {
    return (
      <div className="flex aspect-square items-center justify-center rounded-md border border-dashed border-border bg-muted/20 p-2 text-center text-xs text-muted-foreground">
        No se pudo generar esta variante.
      </div>
    );
  }

  return (
    <div className="flex aspect-square items-center justify-center rounded-md border border-dashed border-border bg-muted/20">
      <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
    </div>
  );
}

/** Ayuda contextual breve de un paso del flujo (Origen→Generar→Ajustar→Marca→Revisar). */
function AyudaPaso({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md bg-muted/40 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
      {children}
    </p>
  );
}

export default function Estudio() {
  const location = useLocation();
  const navigate = useNavigate();
  const ctx = (location.state ?? {}) as ContextoPieza;

  // Sesión persistida (por pieza): se rehidrata en el primer render con inicializadores
  // perezosos para no parpadear ni pisar lo guardado con valores vacíos.
  const sesionKey = claveSesion(ctx.publicacionId);
  const sesion0 = React.useMemo(() => cargarSesion(sesionKey), [sesionKey]);

  // Catálogo de marcas (para los selectores).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // --- Estado de configuración (sesión > contexto de la pieza > por defecto) ---
  const [prompt, setPrompt] = React.useState(() => sesion0.prompt ?? "");
  const [marca, setMarca] = React.useState(() => sesion0.marca ?? ctx.marca ?? "");
  const [formato, setFormato] = React.useState<FormatoImagen>(
    () => sesion0.formato ?? formatoPorRed(ctx.red),
  );
  const [variantes, setVariantes] = React.useState(() => sesion0.variantes ?? 2);
  const [aviso, setAviso] = React.useState("");

  // --- Lienzo: candidatas (de generar/subir/editar) y la imagen ACTIVA ---
  const [candidatas, setCandidatas] = React.useState<ImagenActiva[]>(
    () => sesion0.candidatas ?? [],
  );
  const [activa, setActiva] = React.useState<ImagenActiva | null>(() =>
    sesion0.activaId ? (sesion0.candidatas ?? []).find((c) => c.id === sesion0.activaId) ?? null : null,
  );
  // Generaciones de variantes EN VUELO (una `<Variante>` por cada una; al resolverse se
  // mueven a `candidatas`). Persistidas para reanudar el sondeo al volver a la página.
  const [variantesGen, setVariantesGen] = React.useState<Generacion[]>(
    () => sesion0.variantesGen ?? [],
  );

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

  // Menú contextual de una candidata (clic derecho) para borrar iteraciones del lienzo.
  const [menuCand, setMenuCand] = React.useState<{ id: string; x: number; y: number } | null>(null);
  function borrarCandidata(id: string) {
    setCandidatas((c) => {
      const resto = c.filter((x) => x.id !== id);
      setActiva((a) => (a?.id === id ? (resto[resto.length - 1] ?? null) : a));
      return resto;
    });
    setMenuCand(null);
  }

  // Persistir la sesión cuando cambie: al volver a la página se recupera la vista (las
  // imágenes son objetos durables; los trabajos en vuelo se reanudan por su id/persistKey).
  React.useEffect(() => {
    guardarSesion(sesionKey, {
      candidatas,
      activaId: activa?.id ?? null,
      variantesGen,
      prompt,
      marca,
      formato,
      variantes,
    });
  }, [sesionKey, candidatas, activa, variantesGen, prompt, marca, formato, variantes]);

  // Una variante se RESOLVIÓ: sácala de las que están en vuelo y añádela como candidata
  // (sin activarla). Una que FALLÓ: sácala y avisa. Así el grid no duplica tiles.
  const resolverVariante = React.useCallback((id: string, img: ImagenActiva) => {
    setVariantesGen((prev) => prev.filter((g) => g.id !== id));
    setCandidatas((c) => (c.some((x) => x.id === img.id) ? c : [...c, img]));
  }, []);
  const fallarVariante = React.useCallback((id: string) => {
    setVariantesGen((prev) => prev.filter((g) => g.id !== id));
    toast.error("No se pudo generar una variante.");
  }, []);

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
  // Con `persistKey` reanuda el sondeo si cambias de página mientras corre.
  const op = useGeneracion(sesionKey + ":op");
  const opTerminalRef = React.useRef<string | null>(null);
  const [opAviso, setOpAviso] = React.useState("");
  const [opEtiqueta, setOpEtiqueta] = React.useState("");
  // Foto BASE de la composición de marca en vuelo (para etiquetar el resultado y reemplazar
  // una composición previa de la MISMA base, sin apilar/duplicar el logo).
  const baseComposicionRef = React.useRef<string | null>(null);

  React.useEffect(() => {
    const g = op.generacion;
    if (!g || g.id === opTerminalRef.current) return;
    if (g.estado === "completado") {
      opTerminalRef.current = g.id;
      const img = resultadoImagen(g);
      if (img) {
        if (opEtiqueta === "Marca" && baseComposicionRef.current) {
          // Aplicar marca: la imagen lleva la base como `origen`; sustituye cualquier
          // composición ANTERIOR de esa misma base (idempotente: o está aplicada o no).
          const base = baseComposicionRef.current;
          const conOrigen = { ...img, origen: base };
          setCandidatas((c) => [...c.filter((x) => x.origen !== base), conOrigen]);
          setActiva(conOrigen);
        } else {
          añadirCandidata(img);
        }
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

  // Retoque por instrucción (generativo, con coste): pasa la imagen activa al modelo con una
  // indicación ("oscurece el cielo") y devuelve una generación nueva. Entra como candidata vía
  // el mismo hook `op`. Distinto de Expandir (outpainting): aquí el modelo reinterpreta la escena.
  const lanzarRetocar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.imagenesRetocar>[0]) => api.imagenesRetocar(cuerpo),
    onSuccess: (data) => {
      setOpAviso("");
      op.iniciar(data.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setOpAviso(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo retocar la imagen.");
    },
  });

  // --- Aplicar marca (plantilla): estampa logo/pleca/titular sobre la activa ---
  // Composición DETERMINISTA en el backend; el resultado entra como candidata vía el
  // MISMO hook `op` (respeta la persistencia de sesión, igual que editar/expandir).
  const [marcaPlantilla, setMarcaPlantilla] = React.useState(() => ctx.marca ?? "");
  const [titularPlantilla, setTitularPlantilla] = React.useState("");
  const [etiquetaPlantilla, setEtiquetaPlantilla] = React.useState("");
  const [editorPlantillaAbierto, setEditorPlantillaAbierto] = React.useState(false);

  // Si la marca de "Aplicar marca" aún no está fijada, sigue a la del bloque de generar.
  React.useEffect(() => {
    if (!marcaPlantilla && marca) setMarcaPlantilla(marca);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marca]);

  const lanzarComponer = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.imagenesComponer>[0]) => api.imagenesComponer(cuerpo),
    onSuccess: (data) => {
      setOpAviso("");
      setOpEtiqueta("Marca");
      op.iniciar(data.generacion);
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 400) {
        setOpAviso(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "No se pudo aplicar la marca.");
    },
  });

  const opEjecutando =
    op.ejecutando ||
    lanzarEditar.isPending ||
    lanzarExpandir.isPending ||
    lanzarRetocar.isPending ||
    lanzarComponer.isPending;

  // --- Revisión legal/editorial (gate humano, no bloquea publicar) ---
  // Job "qa-editorial" que VE la imagen activa y devuelve un checklist ✅/⚠️/❌ en `salida`
  // (texto en vivo). Hook dedicado y región propia para no chocar con editar/expandir.
  const revision = useGeneracion(sesionKey + ":rev");
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

  // Empezar de cero: limpia la sesión persistida y deja de seguir los trabajos (no toca el
  // servidor; las imágenes ya generadas siguen en el almacén). Útil al cambiar de pieza.
  function limpiarSesion() {
    setCandidatas([]);
    setActiva(null);
    setVariantesGen([]);
    op.limpiar();
    revision.limpiar();
    try {
      sessionStorage.removeItem(sesionKey);
    } catch {
      // Sin almacenamiento: no hay nada que limpiar.
    }
  }

  function editar(etiqueta: string, cuerpo: Omit<Parameters<typeof api.imagenesEditar>[0], "imagen">) {
    if (!activa) return;
    setOpEtiqueta(etiqueta);
    lanzarEditar.mutate({ imagen: activa.id, ...cuerpo });
  }

  // --- Parámetros de las operaciones (controles inline) ---
  const [maxPx, setMaxPx] = React.useState("1080");
  const [pesoMb, setPesoMb] = React.useState("2");
  const [expStrength, setExpStrength] = React.useState("0.6");
  const [retoqueInstruccion, setRetoqueInstruccion] = React.useState("");
  const [expLado, setExpLado] = React.useState<
    "auto" | "arriba" | "abajo" | "izquierda" | "derecha"
  >("auto");

  // --- Elegir final ---
  // SIEMPRE pasa por la composición antes de guardar: si la pieza tiene marca y la imagen
  // activa AÚN no lleva la plantilla estampada (no tiene `origen`), integramos la foto en la
  // plantilla de marca (composición determinista por SPEC en el backend) usando el titular
  // vigente. Así no se pierde la plantilla al "Usar en la pieza". Si la activa ya está
  // compuesta (`origen` presente) o la pieza no tiene marca, se guarda tal cual. En todos los
  // casos ACTUALIZA la pieza existente (no duplica): vuelve a ella al terminar.
  const marcaPieza = ctx.marca || marcaPlantilla || marca;
  const usarEnPieza = useMutation({
    mutationFn: async () => {
      let imagenFinal = activa!.id;
      const yaCompuesta = !!activa!.origen;
      if (marcaPieza && !yaCompuesta) {
        const r = await api.integrarFotoPublicacion(
          ctx.publicacionId!,
          activa!.id,
          titularPlantilla.trim() || undefined,
        );
        imagenFinal = r.imagen;
      }
      return api.actualizarPublicacion(ctx.publicacionId!, { imagen: imagenFinal });
    },
    onSuccess: () => {
      toast.success("Imagen aplicada a la pieza");
      navigate(-1);
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "No se pudo aplicar a la pieza."),
  });

  // Guardar en la biblioteca de artes: catalogamos el FONDO limpio (la base de la que se
  // compuso la placa, si la hay) para reutilizarlo después sin estampar dos veces la marca.
  const guardarEnBiblioteca = useMutation({
    mutationFn: () =>
      api.guardarArte({
        objeto: activa!.origen || activa!.id,
        marca: ctx.marca || undefined,
        tipo: "estudio",
      }),
    onSuccess: () => toast.success("Guardado en la biblioteca"),
    onError: (e) =>
      toast.error(e instanceof Error ? e.message : "No se pudo guardar en la biblioteca."),
  });

  const srcActiva = activa ? urlMedia(activa.url) : "";

  return (
    <>
      <PageHeader
        titulo="Estudio de imagen"
        descripcion="Sigue el flujo paso a paso: Origen → Generar → Ajustar → Marca → Revisar. Luego úsala en la pieza o descárgala."
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
                className="mx-auto max-h-[72vh] w-auto rounded-md border border-border object-contain"
              />
            ) : (
              <div className="flex h-72 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
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
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Candidatas</Label>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs text-muted-foreground"
                  onClick={limpiarSesion}
                  title="Vaciar el lienzo y empezar de cero (no borra imágenes del almacén)"
                >
                  Empezar de cero
                </Button>
              </div>
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                {variantesGen.map((g) => (
                  <Variante
                    key={g.id}
                    generacion={g}
                    onResuelta={resolverVariante}
                    onFallida={fallarVariante}
                  />
                ))}
                {candidatas.map((img) => (
                  <button
                    key={img.id}
                    type="button"
                    onClick={() => setActiva(img)}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      setMenuCand({ id: img.id, x: e.clientX, y: e.clientY });
                    }}
                    className={`overflow-hidden rounded-md border-2 transition ${
                      activa?.id === img.id
                        ? "border-primary ring-2 ring-primary/30"
                        : "border-border hover:border-primary/50"
                    }`}
                    title="Clic: usar · clic derecho: borrar"
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

        {/* Menú contextual de candidata (borrar iteración del lienzo) */}
        {menuCand && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setMenuCand(null)} onContextMenu={(e) => { e.preventDefault(); setMenuCand(null); }} />
            <div
              className="fixed z-50 min-w-36 overflow-hidden rounded-md border border-border bg-popover py-1 text-sm shadow-md"
              style={{ left: menuCand.x, top: menuCand.y }}
            >
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-destructive hover:bg-muted"
                onClick={() => borrarCandidata(menuCand.id)}
              >
                <Trash2 className="h-4 w-4" /> Borrar del lienzo
              </button>
            </div>
          </>
        )}

        {/* Columna derecha: acciones por pestañas */}
        <div className="space-y-3">
          {/* Acciones finales (siempre visibles cuando hay imagen activa) */}
          {activa && (
            <div className="flex flex-wrap items-center gap-2 rounded-md border border-border p-2">
              {ctx.publicacionId && (
                <Button type="button" size="sm" onClick={() => usarEnPieza.mutate()} disabled={usarEnPieza.isPending}>
                  {usarEnPieza.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <ImagePlus className="mr-1 h-4 w-4" />
                  )}
                  Usar en la pieza
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => guardarEnBiblioteca.mutate()}
                disabled={guardarEnBiblioteca.isPending}
                title="Guardar esta imagen en la biblioteca de artes para reutilizarla en publicaciones"
              >
                {guardarEnBiblioteca.isPending ? (
                  <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                ) : (
                  <Library className="mr-1 h-4 w-4" />
                )}
                Guardar en biblioteca
              </Button>
              <Button asChild variant="outline" size="sm">
                <a href={srcActiva} download>
                  <Download className="mr-1 h-4 w-4" />
                  Descargar
                </a>
              </Button>
            </div>
          )}

          <Tabs defaultValue="origen">
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="origen">1 · Origen</TabsTrigger>
              <TabsTrigger value="generar">2 · Generar</TabsTrigger>
              <TabsTrigger value="ajustar">3 · Ajustar</TabsTrigger>
              <TabsTrigger value="marca">4 · Marca</TabsTrigger>
              <TabsTrigger value="revisar">5 · Revisar</TabsTrigger>
            </TabsList>

            <TabsContent value="origen" className="space-y-4">
          {/* Origen */}
          <section className="space-y-2">
            <Label className="text-sm font-medium">Origen</Label>
            <AyudaPaso>
              Empieza por una imagen: sube una foto real o pásate a la pestaña Generar para crearla
              con IA desde un texto.
            </AyudaPaso>
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
            <p className="text-xs text-muted-foreground">o genera desde cero en el paso 2.</p>
          </section>

            </TabsContent>

            <TabsContent value="generar" className="space-y-4">
          {/* Generar variantes */}
          <section className="space-y-3 rounded-md border border-border p-3">
            <AyudaPaso>
              Describe la imagen y la IA crea varias opciones. Elige una en las Candidatas; podrás
              ajustarla y ponerle la marca en los pasos siguientes.
            </AyudaPaso>
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
                <MarcaIA costo className="mr-1" />
              )}
              {generandoVariantes ? "Generando…" : "Generar variantes"}
            </Button>
            {aviso && (
              <p className="rounded-md bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                {aviso}
              </p>
            )}
          </section>

            </TabsContent>

            <TabsContent value="ajustar" className="space-y-4">
          {/* Editar (determinista) + Expandir (generativo) sobre la activa */}
          <section className="space-y-3 rounded-md border border-border p-3">
            <Label className="text-sm font-medium">Editar la imagen activa</Label>
            <AyudaPaso>
              Recorta, redimensiona o comprime (sin coste), o usa IA: Expandir encaja a formato sin
              tocar el sujeto y Retocar cambia la escena con una instrucción.
            </AyudaPaso>
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
                    <MarcaIA costo />
                    Expandir
                  </Button>
                </div>

                {/* Retoque por instrucción (generativo, con coste) */}
                <div className="space-y-1.5 rounded-md border border-border p-2">
                  <Label htmlFor="estudio-retoque" className="flex items-center gap-1 text-xs">
                    <Wand2 className="h-3.5 w-3.5" />
                    Retocar con instrucción (IA)
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Describe el cambio en lenguaje natural; el modelo reinterpreta la imagen. Para
                    encajar a formato sin tocar el sujeto, usa Expandir.
                  </p>
                  <Textarea
                    id="estudio-retoque"
                    value={retoqueInstruccion}
                    onChange={(e) => setRetoqueInstruccion(e.target.value)}
                    placeholder="p. ej. oscurece el cielo, haz el fondo más cálido, quita el reflejo del cristal…"
                    rows={2}
                    disabled={opEjecutando}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando || retoqueInstruccion.trim().length === 0}
                    onClick={() => {
                      if (!activa || retoqueInstruccion.trim().length === 0) return;
                      setOpEtiqueta("Retoque");
                      lanzarRetocar.mutate({
                        imagen: activa.id,
                        instruccion: retoqueInstruccion.trim(),
                      });
                    }}
                  >
                    <MarcaIA costo />
                    Retocar
                  </Button>
                </div>
              </div>
            )}
          </section>

            </TabsContent>

            <TabsContent value="marca" className="space-y-4">
          {/* Aplicar marca (plantilla): estampa la plantilla diseñada sobre la activa */}
          <section className="space-y-3 rounded-md border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <Label className="flex items-center gap-1 text-sm font-medium">
                <Stamp className="h-4 w-4" />
                Aplicar marca
              </Label>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-muted-foreground"
                onClick={() => setEditorPlantillaAbierto(true)}
              >
                <Settings2 className="mr-1 h-3.5 w-3.5" />
                Editar plantilla de marca
              </Button>
            </div>
            <AyudaPaso>
              Estampa la identidad de la marca (logo, pleca y titular) sobre la imagen. Diseña esa
              plantilla con "Editar plantilla de marca"; disponible para todas las marcas.
            </AyudaPaso>
            {!activa ? (
              <p className="text-xs text-muted-foreground">
                Selecciona una candidata para estamparle la marca.
              </p>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="estudio-marca-plantilla" className="text-xs">
                    Marca
                  </Label>
                  <SelectorMarca
                    id="estudio-marca-plantilla"
                    marcas={marcas}
                    valor={marcaPlantilla}
                    onCambio={setMarcaPlantilla}
                    incluirTodas={false}
                    placeholder="Elige una marca"
                    ariaLabel="Marca a aplicar"
                    className="w-full"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="estudio-titular" className="text-xs">
                    Titular (opcional)
                  </Label>
                  <Input
                    id="estudio-titular"
                    value={titularPlantilla}
                    onChange={(e) => setTitularPlantilla(e.target.value)}
                    placeholder="Texto del titular"
                    disabled={opEjecutando}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="estudio-etiqueta" className="text-xs">
                    Etiqueta/pleca (opcional)
                  </Label>
                  <Input
                    id="estudio-etiqueta"
                    value={etiquetaPlantilla}
                    onChange={(e) => setEtiquetaPlantilla(e.target.value)}
                    placeholder="p. ej. ÚLTIMA HORA"
                    disabled={opEjecutando}
                  />
                  <p className="text-xs text-muted-foreground">
                    Vacío = usa la etiqueta de la plantilla.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={opEjecutando || !marcaPlantilla}
                    onClick={() => {
                      if (!activa || !marcaPlantilla) return;
                      // SIEMPRE desde la foto base (no desde una ya marcada): idempotente, no
                      // apila ni duplica el logo. Cambiar parámetros recompone desde la base.
                      const base = activa.origen ?? activa.id;
                      baseComposicionRef.current = base;
                      setOpEtiqueta("Marca");
                      lanzarComponer.mutate({
                        imagen: base,
                        marca: marcaPlantilla,
                        formato,
                        titular: titularPlantilla.trim() || undefined,
                        etiqueta: etiquetaPlantilla.trim() || undefined,
                      });
                    }}
                  >
                    {opEjecutando ? (
                      <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                    ) : (
                      <Stamp className="mr-1 h-4 w-4" />
                    )}
                    {activa?.origen ? "Reaplicar marca" : "Aplicar marca"}
                  </Button>
                  {activa?.origen && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={opEjecutando}
                      onClick={() => {
                        const raw = candidatas.find((c) => c.id === activa.origen);
                        if (raw) setActiva(raw);
                      }}
                    >
                      Quitar marca
                    </Button>
                  )}
                </div>
              </div>
            )}
          </section>

            </TabsContent>

            <TabsContent value="revisar" className="space-y-4">
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

            </TabsContent>
          </Tabs>
        </div>
      </div>

      <EditorPlantillaMarca
        abierto={editorPlantillaAbierto}
        onOpenChange={setEditorPlantillaAbierto}
        marcas={marcas}
        marcaInicial={marcaPlantilla || marca || ctx.marca}
      />
    </>
  );
}
