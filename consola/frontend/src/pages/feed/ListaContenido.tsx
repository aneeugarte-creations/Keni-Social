import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarClock,
  Check,
  ChevronDown,
  FileText,
  Gauge,
  Hash,
  Loader2,
  Pencil,
  Plus,
  Settings2,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { MenuContextual } from "@/components/comunes/MenuContextual";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
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
import { Badge } from "@/components/ui/badge";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { GestionCadencia } from "@/pages/publicaciones/GestionCadencia";
import { GestionFranjas } from "@/pages/publicaciones/GestionFranjas";
import { GestionHashtags } from "@/pages/publicaciones/GestionHashtags";
import { GestionPublicaciones } from "@/pages/publicaciones/GestionPublicaciones";
import { PanelReciclaje } from "@/pages/publicaciones/PanelReciclaje";
import { DialogoImportarCalendario } from "@/pages/publicaciones/DialogoImportarCalendario";
import type { Etiqueta } from "@/types";

const CLAVE = ["contenido"] as const;

const CABECERA = {
  titulo: "Contenido",
  descripcion:
    "El contenido del equipo en lista: cada pieza con su estado y checklist por plataforma.",
};

/** Workspace "todas las marcas" (sin aislar): coincide con el centinela global de marca. */
const WORKSPACE_TODAS = "__todas__";

/** Etiqueta humana del eje de una etiqueta editorial (para agrupar el catálogo). */
const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  vertical: "Vertical",
  tipo: "Tipo",
};

/**
 * Pestaña "Lista" del hub Feed: la SUPERFICIE de contenido en lista.
 *
 * Reúne el menú "Gestionar" (plantillas, hashtags, franjas, etiquetas, importación) con sus
 * diálogos, el panel de reciclaje y la gestión de publicaciones en modo lista
 * (`GestionPublicaciones`). La CREACIÓN de contenido vive ahora en Investigación/Fuentes
 * (Aportar material), no aquí. La marca del workspace ES la marca activa global (sin
 * selector local).
 */
export default function ListaContenido() {
  // Catálogos (marcas/redes) para los diálogos de gestión (etiquetas/franjas/hashtags/
  // importación). La lista de piezas en sí la pinta GestionPublicaciones desde
  // /api/publicaciones.
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.contenido({}, signal),
  });

  const [importarAbierto, setImportarAbierto] = React.useState(false);
  const [gestionEtiquetas, setGestionEtiquetas] = React.useState(false);
  const [gestionFranjas, setGestionFranjas] = React.useState(false);
  const [gestionCadencia, setGestionCadencia] = React.useState(false);
  const [gestionHashtags, setGestionHashtags] = React.useState(false);

  const navigate = useNavigate();
  // El workspace ES la marca activa global (switch de la topbar). No hay estado ni
  // persistencia local de marca aquí.
  const { marcaActiva } = useMarcaActiva();
  const workspace = marcaActiva ?? WORKSPACE_TODAS;

  const catalogos = query.data?.catalogos;

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          <div className="flex flex-wrap items-center gap-2">
            <MenuContextual
              disparador="click"
              etiqueta="Gestionar el contenido"
              items={[
                {
                  etiqueta: "Plantillas",
                  icono: FileText,
                  onClick: () => navigate("/contenido/biblioteca/plantillas"),
                },
                {
                  etiqueta: "Hashtags",
                  icono: Hash,
                  onClick: () => setGestionHashtags(true),
                },
                {
                  etiqueta: "Franjas",
                  icono: CalendarClock,
                  onClick: () => setGestionFranjas(true),
                },
                {
                  etiqueta: "Cadencia",
                  icono: Gauge,
                  onClick: () => setGestionCadencia(true),
                },
                {
                  etiqueta: "Etiquetas",
                  icono: Tag,
                  deshabilitado: query.isPending,
                  onClick: () => setGestionEtiquetas(true),
                },
                { separador: true },
                {
                  etiqueta: "Importar calendario…",
                  icono: Upload,
                  onClick: () => setImportarAbierto(true),
                },
              ]}
            >
              <Button
                variant="outline"
                size="sm"
                title="Gestionar plantillas, hashtags, franjas, etiquetas e importación"
              >
                <Settings2 className="h-4 w-4" />
                Gestionar
                <ChevronDown className="h-4 w-4 opacity-60" />
              </Button>
            </MenuContextual>
          </div>
        }
      />

      {/* Sugerencias proactivas de reciclaje (#110): se ocultan solas si no hay candidatas.
          Respetan el workspace activo. */}
      <PanelReciclaje
        filtros={{ marca: workspace === WORKSPACE_TODAS ? undefined : workspace }}
        onGestionarFranjas={() => setGestionFranjas(true)}
      />

      <GestionPublicaciones
        modo="lista"
        onGestionarFranjas={() => setGestionFranjas(true)}
      />

      <DialogoImportarCalendario
        abierto={importarAbierto}
        onCerrar={() => setImportarAbierto(false)}
        marcas={catalogos?.marcas ?? []}
        onImportado={(creados) => {
          toast.success(
            creados === 1
              ? "1 contenido importado."
              : `${creados} contenidos importados.`,
          );
          void query.refetch();
        }}
      />
      <DialogoEtiquetas
        abierto={gestionEtiquetas}
        onCerrar={() => setGestionEtiquetas(false)}
        marcas={catalogos?.marcas ?? []}
      />
      <GestionFranjas
        abierto={gestionFranjas}
        onCerrar={() => setGestionFranjas(false)}
        marcas={catalogos?.marcas ?? []}
        redes={catalogos?.redes ?? []}
      />
      <GestionCadencia
        abierto={gestionCadencia}
        onCerrar={() => setGestionCadencia(false)}
        marcas={catalogos?.marcas ?? []}
        redes={catalogos?.redes ?? []}
      />
      <GestionHashtags
        abierto={gestionHashtags}
        onCerrar={() => setGestionHashtags(false)}
        marcas={catalogos?.marcas ?? []}
      />
    </>
  );
}

/** Gestión del CATÁLOGO de etiquetas (crear/editar/borrar). Lee de `/api/etiquetas`. */
function DialogoEtiquetas({
  abierto,
  onCerrar,
  marcas,
}: {
  abierto: boolean;
  onCerrar: () => void;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["etiquetas"],
    queryFn: ({ signal }) => api.etiquetas({}, signal),
    enabled: abierto,
  });
  const [nombre, setNombre] = React.useState("");
  const [clase, setClase] = React.useState("campania");
  const [marca, setMarca] = React.useState("");

  // Edición en línea de una etiqueta existente (renombrar / cambiar eje / marca).
  const [editandoId, setEditandoId] = React.useState<string | null>(null);
  const [editNombre, setEditNombre] = React.useState("");
  const [editClase, setEditClase] = React.useState("campania");
  const [editMarca, setEditMarca] = React.useState("");

  const invalidar = () => {
    void queryClient.invalidateQueries({ queryKey: ["etiquetas"] });
    // El catálogo de etiquetas viaja dentro de /api/contenido.
    void queryClient.invalidateQueries({ queryKey: CLAVE });
  };

  const empezarEdicion = (e: Etiqueta) => {
    setEditandoId(e.id);
    setEditNombre(e.nombre);
    setEditClase(e.clase);
    setEditMarca(e.marca || "");
  };
  const cancelarEdicion = () => setEditandoId(null);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({ nombre: nombre.trim(), clase: clase as never, marca }),
    onSuccess: () => {
      invalidar();
      setNombre("");
      toast.success("Etiqueta creada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const actualizar = useMutation({
    mutationFn: (id: string) =>
      api.actualizarEtiqueta(id, {
        nombre: editNombre.trim(),
        clase: editClase as never,
        marca: editMarca,
      }),
    onSuccess: () => {
      invalidar();
      setEditandoId(null);
      toast.success("Etiqueta actualizada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.eliminarEtiqueta(id),
    onSuccess: () => {
      invalidar();
      toast.success("Etiqueta borrada.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const etiquetas = query.data?.etiquetas ?? [];

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tag className="h-4 w-4" />
            Etiquetas editoriales
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          {/* Alta de etiqueta. */}
          <div className="grid grid-cols-[1fr_auto_auto_auto] items-end gap-2">
            <div className="space-y-1.5">
              <Label htmlFor="et-nombre">Nombre</Label>
              <Input
                id="et-nombre"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                placeholder="Ej. Mundial 2026"
                maxLength={60}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-clase">Eje</Label>
              <Select value={clase} onValueChange={setClase}>
                <SelectTrigger id="et-clase" aria-label="Eje" className="w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                    <SelectItem key={v} value={v}>
                      {l}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="et-marca">Marca</Label>
              <Select value={marca || "__global__"} onValueChange={(v) => setMarca(v === "__global__" ? "" : v)}>
                <SelectTrigger id="et-marca" aria-label="Marca" className="w-36">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__global__">Global</SelectItem>
                  {marcas.map((m) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              onClick={() => crear.mutate()}
              disabled={nombre.trim().length === 0 || crear.isPending}
            >
              {crear.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Plus className="h-4 w-4" />
              )}
              Añadir
            </Button>
          </div>

          {/* Listado del catálogo. */}
          {query.isPending ? (
            <Skeleton className="h-24 w-full rounded-md" />
          ) : etiquetas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no hay etiquetas. Crea la primera arriba.
            </p>
          ) : (
            <div className="space-y-1.5">
              {etiquetas.map((e) =>
                editandoId === e.id ? (
                  <div
                    key={e.id}
                    className="grid grid-cols-[1fr_auto_auto_auto_auto] items-end gap-2 rounded-md border border-border/60 px-2 py-1.5"
                  >
                    <div className="space-y-1.5">
                      <Label htmlFor={`et-edit-nombre-${e.id}`} className="sr-only">
                        Nombre
                      </Label>
                      <Input
                        id={`et-edit-nombre-${e.id}`}
                        value={editNombre}
                        onChange={(ev) => setEditNombre(ev.target.value)}
                        maxLength={60}
                      />
                    </div>
                    <Select value={editClase} onValueChange={setEditClase}>
                      <SelectTrigger aria-label="Eje" className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(CLASE_ETIQUETA_LABEL).map(([v, l]) => (
                          <SelectItem key={v} value={v}>
                            {l}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select
                      value={editMarca || "__global__"}
                      onValueChange={(v) => setEditMarca(v === "__global__" ? "" : v)}
                    >
                      <SelectTrigger aria-label="Marca" className="w-36">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="__global__">Global</SelectItem>
                        {marcas.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.nombre}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      size="icon"
                      aria-label={`Guardar etiqueta ${e.nombre}`}
                      className="h-9 w-9"
                      onClick={() => actualizar.mutate(e.id)}
                      disabled={editNombre.trim().length === 0 || actualizar.isPending}
                    >
                      {actualizar.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Check className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Cancelar edición"
                      className="h-9 w-9"
                      onClick={cancelarEdicion}
                      disabled={actualizar.isPending}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ) : (
                  <FilaConAcciones
                    key={e.id}
                    como="div"
                    onPrimaria={() => empezarEdicion(e)}
                    etiquetaAcciones={`Acciones de la etiqueta ${e.nombre}`}
                    kebab="hover"
                    claseKebab="top-1.5"
                    acciones={[
                      {
                        etiqueta: "Editar",
                        icono: Pencil,
                        onClick: () => empezarEdicion(e),
                      },
                      { separador: true },
                      {
                        etiqueta: "Borrar etiqueta",
                        icono: Trash2,
                        destructivo: true,
                        deshabilitado: borrar.isPending,
                        onClick: async () => {
                          if (
                            await confirmar({
                              mensaje: `¿Borrar la etiqueta "${e.nombre}"? Esta acción no se puede deshacer.`,
                              destructivo: true,
                              textoConfirmar: "Borrar",
                            })
                          ) {
                            borrar.mutate(e.id);
                          }
                        },
                      },
                    ]}
                    className="flex items-center gap-2 rounded-md border border-border/60 px-2 py-1.5 pr-10 text-sm transition-colors hover:border-foreground/20"
                  >
                    <Tag className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-medium">{e.nombre}</span>
                    <Badge variant="secondary" className="font-normal">
                      {CLASE_ETIQUETA_LABEL[e.clase] ?? e.clase}
                    </Badge>
                    <Badge variant="outline" className="font-normal">
                      {e.marca_nombre || "Global"}
                    </Badge>
                  </FilaConAcciones>
                ),
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
