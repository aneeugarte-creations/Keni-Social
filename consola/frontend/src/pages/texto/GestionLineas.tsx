/**
 * Estrategia de marcas: la superficie editorial POR MARCA de la Texto. Reúne
 *   - LÍNEAS de contenido (etiquetas clase `vertical`) y ORÍGENES (clase `origen` =
 *     interno / externo), cada una con sus `keywords` (CSV para auto-clasificar);
 *   - el catálogo de ETIQUETAS editoriales transversales (campaña / tipo) y los
 *     GRUPOS de HASHTAGS por marca, accesibles desde la cabecera.
 *
 * Es CRUD sobre `/api/etiquetas` (acotado por clase) y `/api/hashtags`. Permite
 * filtrar por marca y crear/editar/borrar. Aquí el equipo afina la estrategia
 * editorial de cada marca; antes estas piezas vivían dispersas en el menú
 * "Gestionar" del Feed (sitio equivocado).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Hash, Leaf, Loader2, Pencil, Plus, Tag, Tags, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { AccionesPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { GestionHashtags } from "@/pages/publicaciones/GestionHashtags";
import type { Etiqueta } from "@/types";

/** Las dos clases de etiqueta que esta vista gestiona. */
type ClaseLinea = "vertical" | "origen";

const CLASE_LABEL: Record<ClaseLinea, string> = {
  vertical: "Línea de contenido",
  origen: "Origen",
};

const CLASE_AYUDA: Record<ClaseLinea, string> = {
  vertical:
    "Las líneas (verticales) agrupan el contenido por tema/sección. Las keywords ayudan a " +
    "auto-clasificar cada pieza en su línea.",
  origen:
    "El origen distingue contenido interno de externo. Las keywords ayudan a " +
    "clasificarlo automáticamente.",
};

/** Centinela del selector de marca: etiqueta global (sin marca). */
const GLOBAL = "__global__";

const CLAVE_ETIQUETAS = ["etiquetas"] as const;

/** Etiqueta humana del eje de una etiqueta editorial transversal (campaña / tipo). */
const CLASE_ETIQUETA_LABEL: Record<string, string> = {
  campania: "Campaña",
  tipo: "Tipo",
};

export function GestionLineas() {
  const [etiquetasAbierto, setEtiquetasAbierto] = React.useState(false);
  const [hashtagsAbierto, setHashtagsAbierto] = React.useState(false);

  // Marcas para poblar los diálogos de etiquetas y hashtags (los paneles de
  // líneas/orígenes traen las suyas desde /api/etiquetas).
  const catalogosQuery = useQuery({
    queryKey: ["contenido", "catalogos"],
    queryFn: ({ signal }) => api.contenido({}, signal),
  });
  const marcas = catalogosQuery.data?.catalogos?.marcas ?? [];

  return (
    <>
      <AccionesPagina>
        <MenuAcciones>
          <ItemMenu icono={Tag} onClick={() => setEtiquetasAbierto(true)}>
            Etiquetas
          </ItemMenu>
          <ItemMenu icono={Hash} onClick={() => setHashtagsAbierto(true)}>
            Hashtags
          </ItemMenu>
        </MenuAcciones>
      </AccionesPagina>

      <div className="grid gap-6 lg:grid-cols-2">
        <PanelClase clase="vertical" />
        <PanelClase clase="origen" />
      </div>

      <DialogoEtiquetas
        abierto={etiquetasAbierto}
        onCerrar={() => setEtiquetasAbierto(false)}
        marcas={marcas}
      />
      <GestionHashtags
        abierto={hashtagsAbierto}
        onCerrar={() => setHashtagsAbierto(false)}
        marcas={marcas}
      />
    </>
  );
}

/** Un panel CRUD para una clase concreta (líneas o orígenes). */
function PanelClase({ clase }: { clase: ClaseLinea }) {
  const query = useQuery({
    queryKey: [...CLAVE_ETIQUETAS, clase],
    queryFn: ({ signal }) => api.etiquetas({ clase }, signal),
  });

  const etiquetas = React.useMemo(
    () => query.data?.etiquetas ?? [],
    [query.data],
  );
  const marcas = query.data?.marcas ?? [];

  const { marcaActiva } = useMarcaActiva();
  const [creando, setCreando] = React.useState(false);
  const [filtroMarca, setFiltroMarca] = React.useState<string>(
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : "todas",
  );

  const visibles = React.useMemo(
    () =>
      etiquetas.filter((e) =>
        filtroMarca === "todas"
          ? true
          : filtroMarca === GLOBAL
            ? !e.marca
            : e.marca === filtroMarca,
      ),
    [etiquetas, filtroMarca],
  );

  return (
    <Card className="h-fit">
      <CardHeader className="flex flex-row items-center justify-between gap-3 space-y-0 pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Tags className="h-4 w-4" />
          {clase === "vertical" ? "Líneas de contenido" : "Orígenes"}
          <Badge variant="secondary" className="ml-1">
            {visibles.length}
          </Badge>
        </CardTitle>
        <Button
          size="sm"
          variant="outline"
          onClick={() => setCreando((v) => !v)}
          aria-expanded={creando}
        >
          <Plus className="h-4 w-4" />
          Añadir
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{CLASE_AYUDA[clase]}</p>

        {marcas.length > 0 && (
          <div className="flex items-center gap-2">
            <Label
              htmlFor={`filtro-marca-${clase}`}
              className="text-xs text-muted-foreground"
            >
              Marca
            </Label>
            <Select value={filtroMarca} onValueChange={setFiltroMarca}>
              <SelectTrigger id={`filtro-marca-${clase}`} className="h-8 w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas las marcas</SelectItem>
                <SelectItem value={GLOBAL}>Global</SelectItem>
                {marcas.map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.nombre}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {creando && (
          <FormularioLinea
            clase={clase}
            marcas={marcas}
            onListo={() => setCreando(false)}
          />
        )}

        {query.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full rounded-md" />
            ))}
          </div>
        ) : query.isError ? (
          <BloqueError
            titulo={`No se pudieron cargar ${CLASE_LABEL[clase].toLowerCase()}s`}
            mensaje={mensajeError(query.error)}
            onReintentar={() => void query.refetch()}
            cargando={query.isFetching}
          />
        ) : visibles.length === 0 ? (
          <EstadoVacioTexto
            texto={
              etiquetas.length === 0
                ? `Aún no hay ${
                    clase === "vertical" ? "líneas" : "orígenes"
                  }. Crea el primero con el botón de arriba.`
                : "No hay nada para esta marca. Cambia el filtro o crea una."
            }
            className="py-4"
          />
        ) : (
          <div className="space-y-2">
            {visibles.map((e) => (
              <FilaLinea key={e.id} etiqueta={e} clase={clase} marcas={marcas} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/** Formulario de alta (inline). */
function FormularioLinea({
  clase,
  marcas,
  onListo,
}: {
  clase: ClaseLinea;
  marcas: { id: string; nombre: string }[];
  onListo: () => void;
}) {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const [nombre, setNombre] = React.useState("");
  const [marca, setMarca] = React.useState(
    marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : GLOBAL,
  );
  const [keywords, setKeywords] = React.useState("");
  const [ttlDias, setTtlDias] = React.useState(0);
  const [esEvergreen, setEsEvergreen] = React.useState(false);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({
        nombre: nombre.trim(),
        clase,
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
        ttl_dias: ttlDias,
        es_evergreen: esEvergreen,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });
      toast.success(`${CLASE_LABEL[clase]} creada.`);
      onListo();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = nombre.trim().length > 0 && !crear.isPending;

  return (
    <div className="space-y-3 rounded-md border border-dashed border-border p-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <div className="space-y-1.5">
          <Label htmlFor={`linea-nombre-${clase}`}>Nombre</Label>
          <Input
            id={`linea-nombre-${clase}`}
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder={clase === "vertical" ? "Ej. Futbol" : "Ej. Externo"}
            maxLength={60}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor={`linea-marca-${clase}`}>Marca</Label>
          <Select value={marca} onValueChange={setMarca}>
            <SelectTrigger id={`linea-marca-${clase}`} className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GLOBAL}>Global</SelectItem>
              {marcas.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {clase === "vertical" && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor={`linea-ttl-${clase}`}>
              TTL (días)
            </Label>
            <Input
              id={`linea-ttl-${clase}`}
              type="number"
              min={0}
              value={ttlDias}
              onChange={(e) => setTtlDias(Math.max(0, parseInt(e.target.value) || 0))}
              className="w-24"
            />
            <p className="text-xs text-muted-foreground">0 días = sin caducidad / evergreen</p>
          </div>
          <div className="flex items-center gap-3 pt-5">
            <Switch
              id={`linea-evergreen-${clase}`}
              checked={esEvergreen}
              onCheckedChange={setEsEvergreen}
            />
            <Label htmlFor={`linea-evergreen-${clase}`} className="flex items-center gap-1 cursor-pointer">
              <Leaf className="h-3.5 w-3.5 text-evergreen-600" />
              Everevergreen
            </Label>
          </div>
        </div>
      )}
      <div className="space-y-1.5">
        <Label htmlFor={`linea-keywords-${clase}`}>
          Palabras clave{" "}
          <span className="font-normal text-muted-foreground">(separadas por comas)</span>
        </Label>
        <Textarea
          id={`linea-keywords-${clase}`}
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
          placeholder="liga, gol, partido, jornada"
          rows={2}
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onListo} disabled={crear.isPending}>
          Cancelar
        </Button>
        <Button size="sm" onClick={() => crear.mutate()} disabled={!puedeCrear}>
          {crear.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Plus className="h-4 w-4" />
          )}
          Añadir
        </Button>
      </div>
    </div>
  );
}

/** Una fila con edición en línea (nombre · marca · keywords · ttl · evergreen) y borrado. */
function FilaLinea({
  etiqueta,
  clase,
  marcas,
}: {
  etiqueta: Etiqueta;
  clase: ClaseLinea;
  marcas: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const [editando, setEditando] = React.useState(false);
  const [nombre, setNombre] = React.useState(etiqueta.nombre);
  const [marca, setMarca] = React.useState(etiqueta.marca || GLOBAL);
  const [keywords, setKeywords] = React.useState(etiqueta.keywords ?? "");
  const [ttlDias, setTtlDias] = React.useState(etiqueta.ttl_dias ?? 0);
  const [esEvergreen, setEsEvergreen] = React.useState(etiqueta.es_evergreen ?? false);

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });

  const empezar = () => {
    setNombre(etiqueta.nombre);
    setMarca(etiqueta.marca || GLOBAL);
    setKeywords(etiqueta.keywords ?? "");
    setTtlDias(etiqueta.ttl_dias ?? 0);
    setEsEvergreen(etiqueta.es_evergreen ?? false);
    setEditando(true);
  };

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarEtiqueta(etiqueta.id, {
        nombre: nombre.trim(),
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
        ttl_dias: ttlDias,
        es_evergreen: esEvergreen,
      }),
    onSuccess: () => {
      invalidar();
      setEditando(false);
      toast.success(`${CLASE_LABEL[clase]} actualizada.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarEtiqueta(etiqueta.id),
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? `${CLASE_LABEL[clase]} borrada.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  if (editando) {
    return (
      <div className="space-y-3 rounded-md border border-border/60 p-3">
        <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
          <div className="space-y-1.5">
            <Label htmlFor={`edit-nombre-${etiqueta.id}`} className="sr-only">
              Nombre
            </Label>
            <Input
              id={`edit-nombre-${etiqueta.id}`}
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              maxLength={60}
            />
          </div>
          <Select value={marca} onValueChange={setMarca}>
            <SelectTrigger aria-label="Marca" className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={GLOBAL}>Global</SelectItem>
              {marcas.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {clase === "vertical" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`edit-ttl-${etiqueta.id}`}>TTL (días)</Label>
              <Input
                id={`edit-ttl-${etiqueta.id}`}
                type="number"
                min={0}
                value={ttlDias}
                onChange={(e) => setTtlDias(Math.max(0, parseInt(e.target.value) || 0))}
                className="w-24"
              />
              <p className="text-xs text-muted-foreground">0 días = sin caducidad / evergreen</p>
            </div>
            <div className="flex items-center gap-3 pt-5">
              <Switch
                id={`edit-evergreen-${etiqueta.id}`}
                checked={esEvergreen}
                onCheckedChange={setEsEvergreen}
              />
              <Label htmlFor={`edit-evergreen-${etiqueta.id}`} className="flex items-center gap-1 cursor-pointer">
                <Leaf className="h-3.5 w-3.5 text-evergreen-600" />
                Everevergreen
              </Label>
            </div>
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor={`edit-keywords-${etiqueta.id}`}>
            Palabras clave{" "}
            <span className="font-normal text-muted-foreground">(separadas por comas)</span>
          </Label>
          <Textarea
            id={`edit-keywords-${etiqueta.id}`}
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
            placeholder="liga, gol, partido, jornada"
            rows={2}
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditando(false)}
            disabled={actualizar.isPending}
          >
            <X className="h-4 w-4" />
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={() => actualizar.mutate()}
            disabled={nombre.trim().length === 0 || actualizar.isPending}
          >
            {actualizar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Check className="h-4 w-4" />
            )}
            Guardar
          </Button>
        </div>
      </div>
    );
  }

  const palabras = (etiqueta.keywords ?? "")
    .split(",")
    .map((k) => k.trim())
    .filter(Boolean);

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={empezar}
      etiquetaAcciones={`Acciones de "${etiqueta.nombre}"`}
      kebab="hover"
      acciones={[
        { etiqueta: "Editar", icono: Pencil, onClick: empezar },
        { separador: true },
        {
          etiqueta: "Borrar",
          icono: Trash2,
          destructivo: true,
          deshabilitado: borrar.isPending,
          onClick: async () => {
            if (
              await confirmar({
                mensaje: `¿Borrar "${etiqueta.nombre}"? Esta acción no se puede deshacer.`,
                destructivo: true,
                textoConfirmar: "Borrar",
              })
            )
              borrar.mutate();
          },
        },
      ]}
      className="space-y-1.5 rounded-md border border-border/60 p-3 pr-10"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{etiqueta.nombre}</span>
        <Badge variant="outline" className="font-normal">
          {etiqueta.marca_nombre || "Global"}
        </Badge>
        {clase === "vertical" && etiqueta.es_evergreen && (
          <Badge variant="secondary" className="gap-1 font-normal text-evergreen-700">
            <Leaf className="h-3 w-3" />
            Everevergreen
          </Badge>
        )}
        {clase === "vertical" && !etiqueta.es_evergreen && etiqueta.ttl_dias > 0 && (
          <Badge variant="outline" className="font-normal text-amber-600">
            {etiqueta.ttl_dias}d TTL
          </Badge>
        )}
      </div>
      {palabras.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {palabras.map((p) => (
            <Badge key={p} variant="secondary" className="font-normal">
              {p}
            </Badge>
          ))}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Sin palabras clave.</p>
      )}
    </FilaConAcciones>
  );
}

/**
 * Gestión del CATÁLOGO de etiquetas editoriales TRANSVERSALES (ejes `campaña` y
 * `tipo`). Las líneas (`vertical`) y orígenes (`origen`) NO viven aquí: tienen sus
 * propios paneles arriba, con keywords/TTL/evergreen, así que este diálogo no los
 * duplica. Lee/escribe `/api/etiquetas`.
 */
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
    queryKey: ["etiquetas", "transversales"],
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
    void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });
    // El catálogo de etiquetas viaja también dentro de /api/contenido.
    void queryClient.invalidateQueries({ queryKey: ["contenido"] });
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

  // Solo los ejes transversales (campaña / tipo); líneas y orígenes se gestionan arriba.
  const etiquetas = (query.data?.etiquetas ?? []).filter(
    (e) => e.clase in CLASE_ETIQUETA_LABEL,
  );

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
