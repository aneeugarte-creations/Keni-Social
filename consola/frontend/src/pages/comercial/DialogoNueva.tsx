/**
 * Diálogo para empezar a monitorear una publicación comercial.
 *
 * En vez de pegar un enlace a mano, se ELIGE un post real ya publicado: marca → red →
 * selector de posts (traídos en vivo de Metricool). Al guardar, el backend arranca el
 * seguimiento del post por su `id_post_metricool` y la serie crece con cada captura real.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { NINGUNA, ningunaParam } from "@/components/comunes/selectores";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { numeroCompacto } from "@/lib/formato";
import type {
  CuerpoCrearComercial,
  MetricaComercial,
  OpcionesComercial,
  PostSeleccionableComercial,
} from "@/types";

import { CLAVE_COMERCIAL } from "./claves";
import { fechaCorta } from "./formato";

/** Resumen legible de un post en el selector: fecha + título + métricas. */
function etiquetaPost(p: PostSeleccionableComercial): string {
  const titulo = p.titulo?.trim() || "(sin texto)";
  const corto = titulo.length > 70 ? `${titulo.slice(0, 70)}…` : titulo;
  return `${fechaCorta(p.publicado)} · ${corto} · ${numeroCompacto(p.visualizaciones)} vis`;
}

export function DialogoNueva({
  abierto,
  opciones,
  onCerrar,
}: {
  abierto: boolean;
  opciones: OpcionesComercial;
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const marcaPorDefecto =
    marcaActiva && opciones.marcas.some((m) => m.id === marcaActiva) ? marcaActiva : NINGUNA;
  const [marca, setMarca] = React.useState(marcaPorDefecto);
  const [red, setRed] = React.useState(NINGUNA);
  const [idPost, setIdPost] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [cliente, setCliente] = React.useState("");
  const [campania, setCampania] = React.useState("");
  const [metrica, setMetrica] = React.useState<MetricaComercial>("interacciones");
  const [objetivo, setObjetivo] = React.useState("");
  const [notas, setNotas] = React.useState("");

  // Reseteamos el formulario cada vez que se abre.
  React.useEffect(() => {
    if (!abierto) return;
    setMarca(marcaPorDefecto);
    setRed(NINGUNA);
    setIdPost("");
    setTitulo("");
    setCliente("");
    setCampania("");
    setMetrica("interacciones");
    setObjetivo("");
    setNotas("");
  }, [abierto]);

  const marcaParam = ningunaParam(marca);
  const redParam = ningunaParam(red);

  // Cambiar de marca/red invalida el post elegido (ya no pertenece a la nueva lista).
  React.useEffect(() => {
    setIdPost("");
  }, [marcaParam, redParam]);

  // Posts seleccionables: en vivo de Metricool, solo cuando hay marca Y red.
  const postsQuery = useQuery({
    queryKey: [...CLAVE_COMERCIAL, "posts", marcaParam, redParam],
    queryFn: ({ signal }) =>
      api.comercialPosts({ marca: marcaParam, red: redParam }, signal),
    enabled: abierto && Boolean(marcaParam && redParam),
  });
  const posts = postsQuery.data?.posts ?? [];
  const postSeleccionado = posts.find((p) => p.id === idPost) ?? null;

  // Al elegir un post, prerellenamos el título si el usuario no escribió uno propio.
  function elegirPost(id: string) {
    setIdPost(id);
    const post = posts.find((p) => p.id === id);
    if (post && !titulo.trim()) setTitulo(post.titulo?.trim() || "");
  }

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearComercial = {
        id_post_metricool: idPost,
        url: postSeleccionado?.url ?? "",
        titulo: titulo.trim(),
        marca: marcaParam,
        red: redParam,
        cliente: cliente.trim(),
        campania: campania.trim(),
        publicado: postSeleccionado?.publicado,
        metrica_objetivo: metrica,
        objetivo: objetivo ? Number(objetivo) : 0,
        notas: notas.trim(),
      };
      return api.crearComercial(cuerpo);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_COMERCIAL });
      toast.success("Publicación en seguimiento");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeGuardar = Boolean(idPost) && !crear.isPending;

  // Mensaje contextual bajo el selector de posts (carga / vacío / error / pista).
  function ayudaPosts(): string | null {
    if (!marcaParam || !redParam)
      return "Elige una marca y una red para ver sus publicaciones.";
    if (postsQuery.isPending) return "Cargando publicaciones…";
    if (postsQuery.isError) return "No se pudieron cargar las publicaciones. Reintenta.";
    if (posts.length === 0) return "No hay publicaciones para esa marca y red en el periodo.";
    return null;
  }

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Monitorear publicación</DialogTitle>
          <DialogDescription>
            Elige una publicación ya hecha de tus redes (vía Metricool). Le daremos
            seguimiento a interacciones y visualizaciones, y podrás pedir su reporte cuando
            llegue el KPI.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-marca">Marca *</Label>
              <SelectorMarca
                id="nueva-marca"
                className="w-full"
                marcas={opciones.marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                incluirNinguna
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-red">Red *</Label>
              <SelectorRed
                id="nueva-red"
                className="w-full"
                redes={opciones.redes}
                valor={red}
                onCambio={setRed}
                incluirTodas={false}
                incluirNinguna
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-post">Publicación *</Label>
            <Select
              value={idPost}
              onValueChange={elegirPost}
              disabled={!marcaParam || !redParam || posts.length === 0}
            >
              <SelectTrigger id="nueva-post">
                <SelectValue placeholder="Selecciona una publicación…" />
              </SelectTrigger>
              <SelectContent>
                {posts.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {etiquetaPost(p)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {ayudaPosts() && <p className="text-xs text-muted-foreground">{ayudaPosts()}</p>}
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-titulo">Título o referencia</Label>
            <Input
              id="nueva-titulo"
              placeholder="Spot lanzamiento, sorteo…"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-cliente">Cliente</Label>
              <Input
                id="nueva-cliente"
                placeholder="Anunciante"
                value={cliente}
                onChange={(e) => setCliente(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-campania">Campaña</Label>
              <Input
                id="nueva-campania"
                placeholder="Agrupa una serie de piezas"
                value={campania}
                onChange={(e) => setCampania(e.target.value)}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="nueva-metrica">Métrica del objetivo</Label>
              <Select value={metrica} onValueChange={(v) => setMetrica(v as MetricaComercial)}>
                <SelectTrigger id="nueva-metrica">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {opciones.metricas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nueva-objetivo">Objetivo (KPI)</Label>
              <Input
                id="nueva-objetivo"
                type="number"
                min={0}
                placeholder="Ej. 100000"
                value={objetivo}
                onChange={(e) => setObjetivo(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="nueva-notas">Notas</Label>
            <Textarea
              id="nueva-notas"
              rows={2}
              placeholder="Contexto del reporte, condiciones de la pauta…"
              value={notas}
              onChange={(e) => setNotas(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeGuardar}>
            {crear.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Empezar seguimiento
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
