import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Images,
  Loader2,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { marcaParam, ningunaParam } from "@/components/comunes/selectores";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
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
import { Skeleton } from "@/components/ui/skeleton";
import { api, ApiError } from "@/lib/api";
import type { MedioBiblioteca, OpcionesPublicaciones } from "@/types";

const CLAVE_BIBLIOTECA = ["biblioteca-media"] as const;
const CLAVE_OPCIONES_PUBLICACIONES = ["publicaciones", "opciones"] as const;

const CABECERA = {
  titulo: "Biblioteca de medios",
  descripcion:
    "Repositorio interno de imágenes y clips aprobados, etiquetables y reutilizables al " +
    "armar piezas. No publica a redes (eso lo hace Metricool); es tu banco editorial.",
};

const TIPOS: { id: string; nombre: string }[] = [
  { id: "imagen", nombre: "Imagen" },
  { id: "clip", nombre: "Clip" },
];

const FILTRO_MARCA_TODAS = "__todas__";
const FILTRO_TIPO_TODOS = "__todos__";

export default function BibliotecaMedia() {
  const qc = useQueryClient();

  const [filtroMarca, setFiltroMarca] = React.useState(FILTRO_MARCA_TODAS);
  const [filtroTipo, setFiltroTipo] = React.useState(FILTRO_TIPO_TODOS);
  const [soloAprobados, setSoloAprobados] = React.useState(false);
  const [filtroTexto, setFiltroTexto] = React.useState("");

  // Marcas desde el catálogo NEUTRO de publicaciones (antes /api/skills, retirado).
  const opciones = useQuery<OpcionesPublicaciones>({
    queryKey: CLAVE_OPCIONES_PUBLICACIONES,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];

  const query = useQuery({
    queryKey: [...CLAVE_BIBLIOTECA, filtroMarca, filtroTipo, soloAprobados],
    queryFn: ({ signal }) =>
      api.bibliotecaMedia(
        {
          marca: marcaParam(filtroMarca),
          tipo: filtroTipo === FILTRO_TIPO_TODOS ? undefined : filtroTipo,
          soloAprobados,
        },
        signal,
      ),
  });

  // Filtro de texto en cliente (título, etiquetas, crédito): el backend ya filtra por
  // marca/tipo/aprobado; el texto libre se cruza aquí para no pegarle a la API en cada tecla.
  const medios = React.useMemo(() => {
    const todos = query.data?.medios ?? [];
    const q = filtroTexto.trim().toLowerCase();
    if (!q) return todos;
    return todos.filter((m) =>
      [m.titulo, m.credito, ...m.etiquetas].join(" ").toLowerCase().includes(q),
    );
  }, [query.data, filtroTexto]);

  const [subiendoAbierto, setSubiendoAbierto] = React.useState(false);

  const eliminar = useMutation({
    mutationFn: (id: string) => api.eliminarMedioBiblioteca(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVE_BIBLIOTECA });
      toast.success("Medio eliminado de la biblioteca.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo eliminar."),
  });

  const aprobar = useMutation({
    mutationFn: ({ id, aprobado }: { id: string; aprobado: boolean }) =>
      api.actualizarMedioBiblioteca(id, { aprobado }),
    onSuccess: () => qc.invalidateQueries({ queryKey: CLAVE_BIBLIOTECA }),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo actualizar."),
  });

  return (
    <div>
      <PageHeader
        titulo={CABECERA.titulo}
        descripcion={CABECERA.descripcion}
        acciones={
          <Button size="sm" onClick={() => setSubiendoAbierto(true)}>
            <Upload className="mr-1.5 h-4 w-4" /> Subir medio
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <SelectorMarca
          marcas={marcas}
          valor={filtroMarca}
          onCambio={setFiltroMarca}
          incluirTodas
          className="w-full sm:w-[200px]"
        />
        <Select value={filtroTipo} onValueChange={setFiltroTipo}>
          <SelectTrigger className="w-full sm:w-[150px]" aria-label="Filtrar por tipo">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={FILTRO_TIPO_TODOS}>Todos los tipos</SelectItem>
            {TIPOS.map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.nombre}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          value={filtroTexto}
          onChange={(e) => setFiltroTexto(e.target.value)}
          placeholder="Buscar por título o etiqueta…"
          className="w-full sm:w-[240px]"
          aria-label="Buscar en la biblioteca"
        />
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <Checkbox checked={soloAprobados} onCheckedChange={setSoloAprobados} id="solo-aprobados" />
          Solo aprobados
        </label>
      </div>

      {query.isError && (
        <BloqueError
          titulo="No se pudo cargar la biblioteca"
          mensaje={query.error instanceof Error ? query.error.message : "Error al cargar."}
          onReintentar={() => query.refetch()}
        />
      )}

      {query.isPending && (
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-56 w-full" />
          ))}
        </div>
      )}

      {query.isSuccess && medios.length === 0 && (
        <EstadoVacio
          icono={Images}
          titulo="La biblioteca está vacía"
          texto="Sube imágenes o clips aprobados para reutilizarlos al armar piezas."
        />
      )}

      {medios.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {medios.map((m) => (
            <TarjetaMedio
              key={m.id}
              medio={m}
              onBorrar={() => eliminar.mutate(m.id)}
              borrando={eliminar.isPending && eliminar.variables === m.id}
              onAprobar={(aprobado) => aprobar.mutate({ id: m.id, aprobado })}
            />
          ))}
        </div>
      )}

      <DialogSubir
        abierto={subiendoAbierto}
        onCerrar={() => setSubiendoAbierto(false)}
        marcas={marcas}
        onSubido={() => {
          qc.invalidateQueries({ queryKey: CLAVE_BIBLIOTECA });
          setSubiendoAbierto(false);
        }}
      />
    </div>
  );
}

function TarjetaMedio({
  medio,
  onBorrar,
  borrando,
  onAprobar,
}: {
  medio: MedioBiblioteca;
  onBorrar: () => void;
  borrando: boolean;
  onAprobar: (aprobado: boolean) => void;
}) {
  return (
    <Card className="overflow-hidden">
      <div className="relative aspect-video bg-muted">
        {/* Solo previsualizamos imágenes; un clip muestra su portada/objeto igual por src. */}
        <img
          src={medio.url}
          alt={medio.titulo || "Medio de la biblioteca"}
          className="h-full w-full object-cover"
          loading="lazy"
        />
        {!medio.aprobado && (
          <Badge variant="aviso" className="absolute left-2 top-2">
            Pendiente
          </Badge>
        )}
      </div>
      <CardContent className="space-y-2 py-3">
        <p className="truncate text-sm font-medium" title={medio.titulo}>
          {medio.titulo || "(sin título)"}
        </p>
        <div className="flex flex-wrap gap-1">
          {medio.marca && (
            <Badge variant="outline">{medio.marca_nombre || medio.marca}</Badge>
          )}
          <Badge variant="secondary">{medio.tipo}</Badge>
        </div>
        {medio.etiquetas.length > 0 && (
          <div className="flex flex-wrap items-center gap-1 text-xs text-muted-foreground">
            <Tag className="h-3 w-3" />
            {medio.etiquetas.map((t) => (
              <span key={t} className="rounded bg-muted px-1.5 py-0.5">
                {t}
              </span>
            ))}
          </div>
        )}
        {medio.credito && (
          <p className="truncate text-xs text-muted-foreground">Crédito: {medio.credito}</p>
        )}
      </CardContent>
      <CardFooter className="flex justify-between gap-1 py-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onAprobar(!medio.aprobado)}
          className="text-xs"
        >
          <Check className="mr-1 h-3.5 w-3.5" />
          {medio.aprobado ? "Quitar aprobación" : "Aprobar"}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          onClick={onBorrar}
          disabled={borrando}
          aria-label="Eliminar de la biblioteca"
        >
          {borrando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
        </Button>
      </CardFooter>
    </Card>
  );
}

function DialogSubir({
  abierto,
  onCerrar,
  marcas,
  onSubido,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: { id: string; nombre: string }[];
  onSubido: () => void;
}) {
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [titulo, setTitulo] = React.useState("");
  const [marca, setMarca] = React.useState("__ninguna__");
  const [tipo, setTipo] = React.useState("imagen");
  const [credito, setCredito] = React.useState("");
  const [etiquetasTexto, setEtiquetasTexto] = React.useState("");

  React.useEffect(() => {
    if (abierto) {
      setArchivo(null);
      setTitulo("");
      setMarca("__ninguna__");
      setTipo("imagen");
      setCredito("");
      setEtiquetasTexto("");
    }
  }, [abierto]);

  const subir = useMutation({
    mutationFn: () => {
      if (!archivo) throw new ApiError("Selecciona un archivo.", 400);
      const etiquetas = etiquetasTexto
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean);
      return api.subirMedioBiblioteca(archivo, {
        titulo: titulo.trim(),
        marca: ningunaParam(marca),
        tipo,
        credito: credito.trim(),
        etiquetas,
      });
    },
    onSuccess: () => {
      toast.success("Medio añadido a la biblioteca.");
      onSubido();
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo subir."),
  });

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Subir medio</DialogTitle>
          <DialogDescription>
            Sube una imagen o clip aprobado para reutilizarlo. Las etiquetas (separadas por
            comas) facilitan buscarlo después.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="bm-archivo">Archivo</Label>
            <Input
              id="bm-archivo"
              type="file"
              accept="image/*"
              onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bm-titulo">Título</Label>
            <Input
              id="bm-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              placeholder="Foto de portada Clásico"
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Marca</Label>
              <SelectorMarca
                marcas={marcas}
                valor={marca}
                onCambio={setMarca}
                incluirTodas={false}
                incluirNinguna
                etiquetaNinguna="General (cualquier marca)"
                className="w-full"
              />
            </div>
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={tipo} onValueChange={setTipo}>
                <SelectTrigger className="w-full" aria-label="Tipo de medio">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS.map((t) => (
                    <SelectItem key={t.id} value={t.id}>
                      {t.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bm-etiquetas">Etiquetas</Label>
            <Input
              id="bm-etiquetas"
              value={etiquetasTexto}
              onChange={(e) => setEtiquetasTexto(e.target.value)}
              placeholder="clásico, américa, portada (separadas por comas)"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="bm-credito">Crédito</Label>
            <Input
              id="bm-credito"
              value={credito}
              onChange={(e) => setCredito(e.target.value)}
              placeholder="Fuente / autor de la imagen"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            <X className="mr-1.5 h-4 w-4" /> Cancelar
          </Button>
          <Button onClick={() => subir.mutate()} disabled={!archivo || subir.isPending}>
            {subir.isPending ? (
              <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
            ) : (
              <Upload className="mr-1.5 h-4 w-4" />
            )}
            Subir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
