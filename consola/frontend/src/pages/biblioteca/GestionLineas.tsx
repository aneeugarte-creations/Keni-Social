/**
 * Gestión de LÍNEAS de contenido (etiquetas clase `vertical`) y de ORÍGENES
 * (etiquetas clase `origen` = interno / externo). Las líneas son POR MARCA; el
 * panel se filtra por marca para no mezclarlas.
 *
 * Es CRUD sobre el catálogo de etiquetas (`/api/etiquetas`) acotado a esas dos clases,
 * con el campo `keywords` (CSV de palabras clave para auto-clasificar) editable. Permite
 * filtrar por marca y crear/editar/borrar tanto líneas como orígenes. El equipo ve aquí
 * las líneas sembradas y afina sus keywords.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Pencil, Plus, Tags, Trash2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacioTexto } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
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

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

const CLAVE_ETIQUETAS = ["etiquetas"] as const;

export function GestionLineas() {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <PanelClase clase="vertical" />
      <PanelClase clase="origen" />
    </div>
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

  const [creando, setCreando] = React.useState(false);
  const [filtroMarca, setFiltroMarca] = React.useState<string>("todas");

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
  const [nombre, setNombre] = React.useState("");
  const [marca, setMarca] = React.useState(GLOBAL);
  const [keywords, setKeywords] = React.useState("");

  const crear = useMutation({
    mutationFn: () =>
      api.crearEtiqueta({
        nombre: nombre.trim(),
        clase,
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
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

/** Una fila con edición en línea (nombre · marca · keywords) y borrado. */
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

  const invalidar = () =>
    void queryClient.invalidateQueries({ queryKey: CLAVE_ETIQUETAS });

  const empezar = () => {
    setNombre(etiqueta.nombre);
    setMarca(etiqueta.marca || GLOBAL);
    setKeywords(etiqueta.keywords ?? "");
    setEditando(true);
  };

  const actualizar = useMutation({
    mutationFn: () =>
      api.actualizarEtiqueta(etiqueta.id, {
        nombre: nombre.trim(),
        marca: marca === GLOBAL ? "" : marca,
        keywords: keywords.trim(),
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
