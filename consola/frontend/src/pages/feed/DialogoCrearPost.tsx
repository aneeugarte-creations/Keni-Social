/**
 * DIÁLOGO "Crear post" (alta creativa desde el feed).
 *
 * Una sola caja donde el equipo PEGA lo que sea —una nota, un enlace, el texto de un doc, o
 * directamente una imagen (Cmd+V) o un archivo arrastrado— y la IA lo convierte en un post.
 * No hace falta escribir el copy final: lo que se aporta es MATERIAL y el motor `aportar`
 * (`POST /api/publicaciones/aportar`, origen='equipo') enciende la auto-generación; el borrador
 * nace por red y PARA en la cola de revisión. De cara a las redes no sale nada sin tu OK.
 *
 * Enrutado por lo que pegas, sin que el equipo elija "modo":
 *  - texto / nota  -> `material` (la IA lo redacta como post).
 *  - enlace (URL)  -> `url` (el backend EXTRAE el texto de la página y redacta desde él).
 *  - imagen pegada/arrastrada -> `imagen` (la foto del equipo; la IA escribe el copy).
 *  - archivo de texto (.txt/.md/.csv) soltado -> se lee y entra como `material`.
 *  - .pdf/.docx soltado -> aviso honesto: el backend aún no los ingiere (pega el texto o el enlace).
 *
 * Marca y redes salen del MISMO catálogo que el resto del feed (`/piezas/opciones`,
 * query ya cacheada por FeedIdeacion). Por defecto: la marca activa de la topbar y las
 * redes del formato foto. NO hay campo de título: el backend lo DERIVA siempre (del titular
 * de la página del enlace, de la 1ª línea del material o, si solo hay foto, un genérico).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Paperclip, Sparkles, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { CLAVE_PIEZAS } from "@/pages/piezas/claves";

import { REDES_POR_FORMATO } from "./formato";

// Etiquetas legibles de las categorías ESPECIALES del plan (claves fijas, no líneas
// editoriales). El resto de categorías son IDs de línea vertical y su nombre se resuelve
// contra el catálogo `lineas` del propio endpoint (ver `etiquetaCategoria`).
const ETIQUETA_CATEGORIA: Record<string, string> = {
  mx: "México",
  internacional: "Internacional",
  breaking: "Última hora",
  entretenimiento: "Entretenimiento",
  evergreen: "Evergreen",
  deportes: "Deportes",
};
// Nombre legible de una categoría del plan: primero el rótulo fijo de las especiales, luego
// el nombre de la línea editorial cuyo ID coincide (es la misma fuente que «Programa/Plan»);
// si no, la clave capitalizada. Así el dropdown nunca muestra IDs crudos.
function etiquetaCategoria(c: string, nombresLinea: Record<string, string>): string {
  return (
    ETIQUETA_CATEGORIA[c] ??
    nombresLinea[c] ??
    c.charAt(0).toUpperCase() + c.slice(1)
  );
}

// Primer enlace http(s) dentro del texto pegado. Sirve para enrutar a `url` (el backend lee
// la página) y para avisar al equipo de que lo voy a leer. Heurística deliberadamente simple.
const RE_URL = /(https?:\/\/[^\s]+)/i;
function primeraUrl(texto: string): string | null {
  const m = texto.match(RE_URL);
  return m ? m[1] : null;
}

// Archivos de TEXTO PLANO que podemos leer en el navegador y volcar como material. Los .pdf/
// .docx NO entran aquí: el backend todavía no los ingiere (avisamos en vez de fingir).
function esTextoPlano(archivo: File): boolean {
  return (
    archivo.type.startsWith("text/") ||
    /\.(txt|md|markdown|csv|rtf)$/i.test(archivo.name)
  );
}

export function DialogoCrearPost({
  abierto,
  onCerrar,
}: {
  abierto: boolean;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();

  // Mismo catálogo (y misma query cacheada) que el feed: marcas y redes reales del backend.
  const opcionesQuery = useQuery({
    queryKey: ["piezas", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: abierto,
  });
  const marcas = opcionesQuery.data?.marcas ?? [];
  // La marca de un post nuevo SIGUE la marca activa global: si hay una concreta activa, se
  // usa esa y NO se muestra selector (ya existe el switch global). Solo en "Todas" se elige.
  const marcaFija = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : null;
  const redesCatalogo = React.useMemo(
    () => opcionesQuery.data?.redes ?? [],
    [opcionesQuery.data],
  );

  const [marca, setMarca] = React.useState("");
  // Categoría del plan (OBLIGATORIA): sin ella la pieza no casaría con ninguna franja y se
  // quedaría sin programar tras aprobarse. Las opciones son las categorías CON franja de la
  // marca efectiva (las que realmente encuentran hueco).
  const [categoria, setCategoria] = React.useState("");
  // La caja única: nota, enlace o el texto de un doc. La IA lo convierte en post.
  const [texto, setTexto] = React.useState("");
  // Imagen que el equipo trae de fuera (pegada con Cmd+V o arrastrada): la foto del post.
  const [imagen, setImagen] = React.useState<File | null>(null);
  const [vistaImagen, setVistaImagen] = React.useState("");
  const [arrastrando, setArrastrando] = React.useState(false);
  const [redes, setRedes] = React.useState<Set<string>>(new Set());
  // Las redes por defecto se aplican UNA vez por apertura, cuando el catálogo ya está
  // (acotadas a él): ni pisan lo que el usuario toque ni dejan seleccionado lo invisible.
  const [redesInicializadas, setRedesInicializadas] = React.useState(false);
  const archivoRef = React.useRef<HTMLInputElement>(null);

  // Marca efectiva del alta (la fija activa o la elegida en "Todas") y SUS categorías con franja.
  const marcaEfectiva = marcaFija ?? marca;
  const categoriasMarca = React.useMemo(
    () => opcionesQuery.data?.categorias?.[marcaEfectiva] ?? [],
    [opcionesQuery.data, marcaEfectiva],
  );
  // Mapa id→nombre de las líneas editoriales (mismas que pueblan «Programa/Plan»): resuelve el
  // nombre legible de las categorías que son una línea, en vez de mostrar su ID.
  const nombresLinea = React.useMemo(() => {
    const m: Record<string, string> = {};
    for (const l of opcionesQuery.data?.lineas ?? []) m[l.id] = l.nombre;
    return m;
  }, [opcionesQuery.data]);

  const url = primeraUrl(texto);

  // Adjunta una imagen y genera su miniatura; revoca la anterior para no fugar object-URLs.
  const adjuntarImagen = React.useCallback((archivo: File) => {
    setImagen(archivo);
    setVistaImagen((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return URL.createObjectURL(archivo);
    });
  }, []);

  const quitarImagen = React.useCallback(() => {
    setImagen(null);
    setVistaImagen((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return "";
    });
    if (archivoRef.current) archivoRef.current.value = "";
  }, []);

  // Lee un archivo de texto plano y lo vuelca al material (lo concatena a lo que ya hubiera).
  const leerTextoArchivo = React.useCallback((archivo: File) => {
    const lector = new FileReader();
    lector.onload = () => {
      const contenido = String(lector.result ?? "").trim();
      if (!contenido) return;
      setTexto((prev) => (prev.trim() ? `${prev.trim()}\n\n${contenido}` : contenido));
    };
    lector.onerror = () => toast.error("No se pudo leer ese archivo.");
    lector.readAsText(archivo);
  }, []);

  // Enruta un archivo (de drop o del selector) por su tipo: imagen, texto plano o no soportado.
  const recibirArchivo = React.useCallback(
    (archivo: File | null | undefined) => {
      if (!archivo) return;
      if (archivo.type.startsWith("image/")) {
        adjuntarImagen(archivo);
        return;
      }
      if (esTextoPlano(archivo)) {
        leerTextoArchivo(archivo);
        return;
      }
      toast.error(
        "Ese archivo no se puede leer aún. Pega el texto o el enlace (los .pdf/.docx todavía no se ingieren).",
      );
    },
    [adjuntarImagen, leerTextoArchivo],
  );

  // Pegar (Cmd+V) en la caja: si el portapapeles trae una IMAGEN, la adjuntamos (y evitamos
  // que su binario caiga como texto). Si trae texto, lo dejamos pegar con normalidad.
  const alPegar = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const archivo = item.getAsFile();
        if (archivo) {
          e.preventDefault();
          adjuntarImagen(archivo);
          return;
        }
      }
    }
  };

  // Al ABRIR: formulario limpio con los defectos del momento (marca activa de la topbar).
  // Re-abrir no arrastra el intento anterior.
  React.useEffect(() => {
    if (!abierto) return;
    setMarca(marcaActiva ?? "");
    setCategoria("");
    setTexto("");
    setRedes(new Set());
    setRedesInicializadas(false);
    setArrastrando(false);
    quitarImagen();
  }, [abierto, marcaActiva, quitarImagen]);
  // Si la categoría elegida no existe para la marca efectiva (cambió de marca en "Todas"), se
  // limpia: no se manda una categoría que no casa con ninguna franja de esa marca.
  React.useEffect(() => {
    if (categoria && !categoriasMarca.includes(categoria)) setCategoria("");
  }, [categoriasMarca, categoria]);
  React.useEffect(() => {
    if (!abierto || redesInicializadas || redesCatalogo.length === 0) return;
    const foto = new Set<string>(REDES_POR_FORMATO.foto);
    setRedes(new Set(redesCatalogo.map((r) => r.id).filter((id) => foto.has(id))));
    setRedesInicializadas(true);
  }, [abierto, redesInicializadas, redesCatalogo]);
  // Revoca la última miniatura al desmontar (evita fuga de object-URLs).
  React.useEffect(() => {
    return () => {
      if (vistaImagen) URL.revokeObjectURL(vistaImagen);
    };
  }, [vistaImagen]);

  const crear = useMutation({
    mutationFn: () => {
      const t = texto.trim();
      // Si lo único pegado es el propio enlace, no lo duplicamos como material (el backend ya
      // lee la página); si hay prosa además del enlace, va entera como material (contexto).
      const material = t && t !== url ? t : undefined;
      return api.aportarMaterial({
        marca,
        categoria,
        // Sin campo de título: el backend lo deriva (titular del enlace, 1ª línea del
        // material o, si solo hay foto, un genérico). Un rótulo menos que rellenar.
        material,
        url: url ?? undefined,
        imagen: imagen ?? undefined,
        redes: [...redes],
      });
    },
    onSuccess: (data) => {
      // Refresca TODO el árbol de piezas: el feed (feed-ideacion), los conteos de
      // las pestañas y las demás superficies (lista, kanban) que cuelgan de la misma clave.
      void queryClient.invalidateQueries({ queryKey: CLAVE_PIEZAS });
      const n = data.contenido.plataformas?.length ?? 0;
      toast.success(
        n === 1
          ? "Post en camino: la IA está redactando 1 borrador para tu revisión."
          : `Post en camino: la IA está redactando ${n} borradores para tu revisión.`,
      );
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Hay algo que aportar si hay texto o una imagen; marca, CATEGORÍA y al menos una red son
  // obligatorias (la categoría, para que la pieza encuentre franja y se programe sola).
  const hayPublicacion = texto.trim() !== "" || imagen !== null;
  const puedeCrear =
    hayPublicacion && marca !== "" && categoria !== "" && redes.size > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Crear post</DialogTitle>
          <DialogDescription>
            Pega un enlace, una nota o una imagen. La IA redacta el borrador y tú decides si se
            publica.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Selector de marca SOLO cuando no hay una marca concreta activa (vista "Todas"):
              con una marca activa, el post va a esa marca y no se pregunta de nuevo. */}
          {marcaFija ? null : (
            <div className="space-y-1.5">
              <Label htmlFor="crear-post-marca">Marca</Label>
              <SelectorMarca
                id="crear-post-marca"
                marcas={marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                placeholder="Elige una marca"
                className="w-full"
                disabled={crear.isPending}
              />
            </div>
          )}

          {/* Categoría del plan (OBLIGATORIA): a qué franja va la pieza. Sin ella no encontraría
              hueco y se quedaría sin programar tras aprobarse. Opciones = categorías CON franja
              de la marca efectiva. */}
          <div className="space-y-1.5">
            <Label htmlFor="crear-post-categoria">Categoría</Label>
            <Select
              value={categoria}
              onValueChange={setCategoria}
              disabled={crear.isPending || categoriasMarca.length === 0}
            >
              <SelectTrigger id="crear-post-categoria" className="w-full">
                <SelectValue
                  placeholder={
                    categoriasMarca.length === 0
                      ? "Sin franjas configuradas para esta marca"
                      : "Elige una categoría"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {categoriasMarca.map((c) => (
                  <SelectItem key={c} value={c}>
                    {etiquetaCategoria(c, nombresLinea)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Define la franja del plan; así la pieza se programa sola al aprobarse.
            </p>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="crear-post-material">Material</Label>
              <input
                ref={archivoRef}
                type="file"
                accept="image/*,text/*,.txt,.md,.markdown,.csv,.rtf"
                className="hidden"
                onChange={(e) => {
                  recibirArchivo(e.target.files?.[0]);
                  e.target.value = "";
                }}
                aria-hidden="true"
                tabIndex={-1}
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1.5 text-xs text-muted-foreground"
                onClick={() => archivoRef.current?.click()}
                disabled={crear.isPending}
              >
                <Paperclip className="h-3.5 w-3.5" />
                Adjuntar imagen o archivo
              </Button>
            </div>
            {/* Zona de pegado/arrastre: la caja acepta texto, y soltar/pegar una imagen o un
                archivo de texto. El anillo se enciende mientras arrastras encima. */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                if (!crear.isPending) setArrastrando(true);
              }}
              onDragLeave={() => setArrastrando(false)}
              onDrop={(e) => {
                e.preventDefault();
                setArrastrando(false);
                if (crear.isPending) return;
                recibirArchivo(e.dataTransfer?.files?.[0]);
              }}
              className={cn(
                "rounded-md transition-shadow",
                arrastrando && "ring-2 ring-primary ring-offset-2 ring-offset-background",
              )}
            >
              <Textarea
                id="crear-post-material"
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                onPaste={alPegar}
                placeholder="Pega aquí un enlace, el texto de una nota o un documento… o pega/arrastra una imagen."
                rows={5}
                disabled={crear.isPending}
              />
            </div>
            {url && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Link2 className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">Leeré el enlace para redactar el post: {url}</span>
              </p>
            )}
            {imagen && (
              <div className="flex items-center gap-2 rounded-md border bg-muted/40 p-2">
                {vistaImagen && (
                  <img
                    src={vistaImagen}
                    alt=""
                    className="h-12 w-12 shrink-0 rounded object-cover"
                  />
                )}
                <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  {imagen.name || "Imagen pegada"}
                </span>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0 text-muted-foreground"
                  onClick={quitarImagen}
                  disabled={crear.isPending}
                  aria-label="Quitar imagen"
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              La IA convierte lo que aportes en un borrador por red. Nada se publica sin tu OK.
            </p>
          </div>

          <SelectorRedMultiple
            opciones={redesCatalogo}
            seleccionadas={redes}
            onCambio={(red, marcada) =>
              setRedes((prev) => {
                const sig = new Set(prev);
                if (marcada) sig.add(red);
                else sig.delete(red);
                return sig;
              })
            }
            disabled={crear.isPending}
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button variant="outline" onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {/* La estrellita marca que la acción la redacta la IA (mismo signo que MarcaIA /
                el resto de acciones de IA de la casa); al lanzar, cede al spinner. */}
            {crear.isPending ? (
              <Spinner className="h-4 w-4" />
            ) : (
              <Sparkles className="h-4 w-4" />
            )}
            {crear.isPending ? "Creando…" : "Crear post"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
