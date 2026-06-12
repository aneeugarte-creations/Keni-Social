/**
 * DIÁLOGO "Crear post" (alta directa desde el feed).
 *
 * El equipo crea un post DESDE CERO tecleando el COPY FINAL: el mismo motor por el que
 * nacen las piezas al usar una noticia/investigación (un tema + un borrador por red), pero
 * sin generación de copy —el copy es el del humano, tal cual—. La pieza nace con copy
 * listo y "Falta imagen", aparece en el feed al instante y sigue el flujo normal (arte
 * por red, aprobación, programación).
 *
 * Marca y redes salen del MISMO catálogo que el resto del feed (`/publicaciones/opciones`,
 * query ya cacheada por FeedIdeacion). Por defecto: la marca activa de la topbar y las
 * redes del formato foto (las mismas a las que el flujo automático manda una pieza).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { CLAVE_PUBLICACIONES } from "@/pages/publicaciones/claves";

import { REDES_POR_FORMATO } from "./formato";

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
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: abierto,
  });
  const marcas = opcionesQuery.data?.marcas ?? [];
  const redesCatalogo = React.useMemo(
    () => opcionesQuery.data?.redes ?? [],
    [opcionesQuery.data],
  );

  const [marca, setMarca] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [copy, setCopy] = React.useState("");
  const [redes, setRedes] = React.useState<Set<string>>(new Set());
  // Las redes por defecto se aplican UNA vez por apertura, cuando el catálogo ya está
  // (acotadas a él): ni pisan lo que el usuario toque ni dejan seleccionado lo invisible.
  const [redesInicializadas, setRedesInicializadas] = React.useState(false);

  // Al ABRIR: formulario limpio con los defectos del momento (marca activa de la topbar).
  // Re-abrir no arrastra el intento anterior.
  React.useEffect(() => {
    if (!abierto) return;
    setMarca(marcaActiva ?? "");
    setTitulo("");
    setCopy("");
    setRedes(new Set());
    setRedesInicializadas(false);
  }, [abierto, marcaActiva]);
  React.useEffect(() => {
    if (!abierto || redesInicializadas || redesCatalogo.length === 0) return;
    const foto = new Set<string>(REDES_POR_FORMATO.foto);
    setRedes(new Set(redesCatalogo.map((r) => r.id).filter((id) => foto.has(id))));
    setRedesInicializadas(true);
  }, [abierto, redesInicializadas, redesCatalogo]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearPostDirecto({
        copy: copy.trim(),
        marca,
        titulo: titulo.trim() || undefined,
        redes: [...redes],
      }),
    onSuccess: (data) => {
      // Refresca TODO el árbol de publicaciones: el feed (feed-ideacion), los conteos de
      // las pestañas y las demás superficies (lista, kanban) que cuelgan de la misma clave.
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const n = data.contenido.plataformas?.length ?? 0;
      toast.success(
        n === 1 ? "Post creado: 1 borrador en el feed." : `Post creado: ${n} borradores en el feed.`,
      );
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = copy.trim() !== "" && marca !== "" && redes.size > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Crear post</DialogTitle>
          <DialogDescription>Tu copy tal cual, como borrador en las redes elegidas.</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
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

          <div className="space-y-1.5">
            <Label htmlFor="crear-post-copy">Copy</Label>
            <Textarea
              id="crear-post-copy"
              value={copy}
              onChange={(e) => setCopy(e.target.value)}
              placeholder="El texto del post, listo para publicar…"
              rows={5}
              disabled={crear.isPending}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="crear-post-titulo">Título</Label>
            <Input
              id="crear-post-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Opcional: etiqueta de la idea"
              disabled={crear.isPending}
            />
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
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {crear.isPending ? "Creando…" : "Crear post"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
