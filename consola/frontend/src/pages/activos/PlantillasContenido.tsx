import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  FileText,
  Loader2,
  Pencil,
  Plus,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import {
  desdeMarca,
  desdeRed,
  ningunaParam,
} from "@/components/comunes/selectores";
import { DialogoAplicarPlantilla } from "@/components/plantillas/DialogoAplicarPlantilla";
import { clavesEnEstructura } from "@/components/plantillas/util";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type {
  ModoPlantilla,
  OpcionesPublicaciones,
  PlantillaContenido,
  VariablePlantilla,
} from "@/types";

const CLAVE_PLANTILLAS_CONTENIDO = ["plantillas-contenido"] as const;
const CLAVE_OPCIONES_PUBLICACIONES = ["publicaciones", "opciones"] as const;

const CABECERA = {
  titulo: "Plantillas",
  descripcion:
    "Catálogo unificado de plantillas de copy reutilizables: planas (texto fijo por marca/red) " +
    "y de estructura por tipo de nota recurrente (gol, alineación, efeméride…) con variables " +
    "{{...}}. No publica nada: solo acelera armar piezas.",
};

/** Formulario controlado de crear/editar una plantilla del catálogo unificado. */
interface FormPlantilla {
  nombre: string;
  modo: ModoPlantilla;
  tipo_nota: string;
  descripcion: string;
  marca: string; // centinela MARCA_TODAS = sin marca
  red: string; // centinela RED_TODAS = sin red
  contenido: string; // modo 'plano'
  estructura: string; // modo 'estructura'
  variables: VariablePlantilla[];
}

const FORM_VACIO: FormPlantilla = {
  nombre: "",
  modo: "plano",
  tipo_nota: "",
  descripcion: "",
  marca: desdeMarca(""),
  red: desdeRed(""),
  contenido: "",
  estructura: "",
  variables: [],
};

export default function PlantillasContenido() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: CLAVE_PLANTILLAS_CONTENIDO,
    queryFn: ({ signal }) => api.plantillasContenido(undefined, signal),
  });
  // Marcas/redes desde el catálogo NEUTRO de publicaciones (antes /api/skills, retirado).
  const opciones = useQuery<OpcionesPublicaciones>({
    queryKey: CLAVE_OPCIONES_PUBLICACIONES,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  const plantillas = query.data?.plantillas ?? [];
  const marcas = opciones.data?.marcas ?? [];
  const redes = opciones.data?.redes ?? [];

  // --- Diálogo de edición/creación ---
  const [abierto, setAbierto] = React.useState(false);
  const [editId, setEditId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<FormPlantilla>(FORM_VACIO);

  function abrirCrear() {
    setEditId(null);
    setForm(FORM_VACIO);
    setAbierto(true);
  }

  function abrirEditar(p: PlantillaContenido) {
    setEditId(p.id);
    setForm({
      nombre: p.nombre,
      modo: p.modo,
      tipo_nota: p.tipo_nota,
      descripcion: p.descripcion,
      marca: desdeMarca(p.marca),
      red: desdeRed(p.red),
      contenido: p.contenido,
      estructura: p.estructura,
      variables: p.variables,
    });
    setAbierto(true);
  }

  const guardar = useMutation({
    mutationFn: async () => {
      const esPlano = form.modo === "plano";
      const cuerpo = {
        nombre: form.nombre.trim(),
        modo: form.modo,
        tipo_nota: form.tipo_nota.trim(),
        descripcion: form.descripcion,
        marca: ningunaParam(form.marca),
        red: ningunaParam(form.red),
        // Solo enviamos el cuerpo del modo activo; el otro queda vacío en el servidor.
        contenido: esPlano ? form.contenido : "",
        estructura: esPlano ? "" : form.estructura,
        variables: esPlano ? [] : form.variables,
      };
      if (editId) return api.actualizarPlantillaContenido(editId, cuerpo);
      return api.crearPlantillaContenido(cuerpo);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVE_PLANTILLAS_CONTENIDO });
      setAbierto(false);
      toast.success(editId ? "Plantilla actualizada." : "Plantilla creada.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo guardar."),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => api.eliminarPlantillaContenido(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVE_PLANTILLAS_CONTENIDO });
      toast.success("Plantilla borrada.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo borrar."),
  });

  // --- Variables del formulario ---
  function setVariable(i: number, parcial: Partial<VariablePlantilla>) {
    setForm((f) => ({
      ...f,
      variables: f.variables.map((v, idx) => (idx === i ? { ...v, ...parcial } : v)),
    }));
  }
  function anadirVariable() {
    setForm((f) => ({
      ...f,
      variables: [...f.variables, { clave: "", etiqueta: "", ejemplo: "" }],
    }));
  }
  function quitarVariable(i: number) {
    setForm((f) => ({ ...f, variables: f.variables.filter((_, idx) => idx !== i) }));
  }

  // Avisos: claves usadas en la estructura pero no declaradas como variable.
  const clavesEstructura = clavesEnEstructura(form.estructura);
  const clavesDeclaradas = new Set(form.variables.map((v) => v.clave).filter(Boolean));
  const sinDeclarar = clavesEstructura.filter((c) => !clavesDeclaradas.has(c));

  const cuerpoLleno =
    form.modo === "plano" ? form.contenido.trim() !== "" : form.estructura.trim() !== "";
  const puedeGuardar = form.nombre.trim() !== "" && cuerpoLleno;

  return (
    <div>
      <PageHeader
        titulo={CABECERA.titulo}
        descripcion={CABECERA.descripcion}
        acciones={
          <Button onClick={abrirCrear} size="sm">
            <Plus className="mr-1.5 h-4 w-4" /> Nueva plantilla
          </Button>
        }
      />

      {query.isError && (
        <BloqueError
          titulo="No se pudieron cargar las plantillas"
          mensaje={query.error instanceof Error ? query.error.message : "Error al cargar."}
          onReintentar={() => query.refetch()}
        />
      )}

      {query.isPending && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      )}

      {query.isSuccess && plantillas.length === 0 && (
        <EstadoVacio
          icono={FileText}
          titulo="Aún no hay plantillas de contenido"
          texto="Crea una estructura por tipo de nota recurrente para no empezar de cero cada vez."
        />
      )}

      {plantillas.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {plantillas.map((p) => (
            <TarjetaPlantilla
              key={p.id}
              plantilla={p}
              onEditar={() => abrirEditar(p)}
              onBorrar={() => eliminar.mutate(p.id)}
              borrando={eliminar.isPending && eliminar.variables === p.id}
            />
          ))}
        </div>
      )}

      <Dialog open={abierto} onOpenChange={setAbierto}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editId ? "Editar plantilla" : "Nueva plantilla"}</DialogTitle>
            <DialogDescription>
              Elige el modo: <strong>plano</strong> (texto fijo reutilizable) o{" "}
              <strong>estructura</strong> con marcadores{" "}
              <code className="rounded bg-muted px-1">{"{{variable}}"}</code> que se rellenan al
              aplicar.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <Tabs
              value={form.modo}
              onValueChange={(v) => setForm((f) => ({ ...f, modo: v as ModoPlantilla }))}
            >
              <TabsList className="grid w-full grid-cols-2 sm:w-80">
                <TabsTrigger value="plano">Texto plano</TabsTrigger>
                <TabsTrigger value="estructura">Estructura</TabsTrigger>
              </TabsList>
            </Tabs>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="pc-nombre">Nombre</Label>
                <Input
                  id="pc-nombre"
                  value={form.nombre}
                  onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
                  placeholder={form.modo === "plano" ? "Despedida de transmisión" : "Plantilla de gol"}
                />
              </div>
              {form.modo === "estructura" && (
                <div className="space-y-1.5">
                  <Label htmlFor="pc-tipo">Tipo de nota</Label>
                  <Input
                    id="pc-tipo"
                    value={form.tipo_nota}
                    onChange={(e) => setForm((f) => ({ ...f, tipo_nota: e.target.value }))}
                    placeholder="gol, alineación, efeméride…"
                  />
                </div>
              )}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Marca</Label>
                <SelectorMarca
                  marcas={marcas}
                  valor={form.marca}
                  onCambio={(v) => setForm((f) => ({ ...f, marca: v }))}
                  incluirTodas={false}
                  incluirNinguna
                  etiquetaNinguna="General (cualquier marca)"
                  className="w-full"
                />
              </div>
              <div className="space-y-1.5">
                <Label>Red</Label>
                <SelectorRed
                  redes={redes}
                  valor={form.red}
                  onCambio={(v) => setForm((f) => ({ ...f, red: v }))}
                  incluirTodas={false}
                  incluirNinguna
                  etiquetaNinguna="Cualquier red"
                  className="w-full"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pc-desc">Descripción</Label>
              <Input
                id="pc-desc"
                value={form.descripcion}
                onChange={(e) => setForm((f) => ({ ...f, descripcion: e.target.value }))}
                placeholder="Cuándo y cómo usar esta plantilla"
              />
            </div>

            {form.modo === "plano" ? (
              <div className="space-y-1.5">
                <Label htmlFor="pc-contenido">Contenido</Label>
                <Textarea
                  id="pc-contenido"
                  value={form.contenido}
                  onChange={(e) => setForm((f) => ({ ...f, contenido: e.target.value }))}
                  placeholder="Escribe aquí el copy reutilizable tal cual se usará…"
                  className="min-h-[120px] font-mono text-sm"
                />
              </div>
            ) : (
              <>
                <div className="space-y-1.5">
                  <Label htmlFor="pc-estructura">Estructura</Label>
                  <Textarea
                    id="pc-estructura"
                    value={form.estructura}
                    onChange={(e) => setForm((f) => ({ ...f, estructura: e.target.value }))}
                    placeholder={"¡GOOOL de {{equipo}}! {{jugador}} marca el {{minuto}}'. {{marcador}} 🔥"}
                    className="min-h-[120px] font-mono text-sm"
                  />
                  {sinDeclarar.length > 0 && (
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      Variables usadas sin declarar: {sinDeclarar.join(", ")}.
                    </p>
                  )}
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label>Variables</Label>
                    <Button type="button" variant="outline" size="sm" onClick={anadirVariable}>
                      <Plus className="mr-1 h-3.5 w-3.5" /> Añadir
                    </Button>
                  </div>
                  {form.variables.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      Declara las variables de la estructura para tener un formulario al aplicar.
                    </p>
                  )}
                  {form.variables.map((v, i) => (
                    <div key={i} className="grid grid-cols-[1fr_1fr_1fr_auto] items-center gap-2">
                      <Input
                        value={v.clave}
                        onChange={(e) => setVariable(i, { clave: e.target.value })}
                        placeholder="clave"
                        aria-label={`Clave de la variable ${i + 1}`}
                      />
                      <Input
                        value={v.etiqueta}
                        onChange={(e) => setVariable(i, { etiqueta: e.target.value })}
                        placeholder="Etiqueta"
                        aria-label={`Etiqueta de la variable ${i + 1}`}
                      />
                      <Input
                        value={v.ejemplo}
                        onChange={(e) => setVariable(i, { ejemplo: e.target.value })}
                        placeholder="Ejemplo"
                        aria-label={`Ejemplo de la variable ${i + 1}`}
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => quitarVariable(i)}
                        aria-label={`Quitar variable ${i + 1}`}
                      >
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAbierto(false)}>
              Cancelar
            </Button>
            <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar || guardar.isPending}>
              {guardar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {editId ? "Guardar" : "Crear"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Tarjeta de una plantilla. Click izquierdo sobre la tarjeta = editar (acción
 * primaria); editar y borrar viven también en el menú contextual (click derecho)
 * y en el kebab "⋮". El CTA "Aplicar" (rellenar variables) se mantiene como botón
 * dominante full-width abajo.
 */
function TarjetaPlantilla({
  plantilla,
  onEditar,
  onBorrar,
  borrando,
}: {
  plantilla: PlantillaContenido;
  onEditar: () => void;
  onBorrar: () => void;
  borrando: boolean;
}) {
  const [aplicando, setAplicando] = React.useState(false);

  // Acción primaria = editar. Editar (explícito) + borrar (con confirmación), al menú.
  const acciones: EntradaMenuContextual[] = [
    { etiqueta: "Editar", icono: Pencil, onClick: onEditar },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: () => {
        if (window.confirm(`¿Borrar la plantilla "${plantilla.nombre}"?`)) onBorrar();
      },
      destructivo: true,
      deshabilitado: borrando,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      onPrimaria={onEditar}
      acciones={acciones}
      etiquetaAcciones={`Acciones de "${plantilla.nombre}"`}
      kebab="hover"
      className="rounded-xl border border-border bg-card text-card-foreground"
    >
      <CardHeader className="pb-2 pr-10">
        <CardTitle className="text-base">{plantilla.nombre}</CardTitle>
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={plantilla.modo === "plano" ? "default" : "secondary"}>
            {plantilla.modo === "plano" ? "Texto plano" : "Estructura"}
          </Badge>
          {plantilla.tipo_nota && <Badge variant="secondary">{plantilla.tipo_nota}</Badge>}
          {plantilla.marca && <Badge variant="outline">{plantilla.marca_nombre || plantilla.marca}</Badge>}
          {plantilla.red && <Badge variant="outline">{plantilla.red_nombre || plantilla.red}</Badge>}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {plantilla.descripcion && (
          <p className="text-sm text-muted-foreground">{plantilla.descripcion}</p>
        )}
        <pre className="max-h-24 overflow-hidden whitespace-pre-wrap rounded bg-muted p-2 text-xs">
          {plantilla.modo === "plano" ? plantilla.contenido : plantilla.estructura}
        </pre>
        <Button variant="secondary" size="sm" className="w-full" onClick={() => setAplicando(true)}>
          <Wand2 className="mr-1.5 h-4 w-4" /> Aplicar
        </Button>
      </CardContent>

      <DialogoAplicarPlantilla
        plantilla={plantilla}
        abierto={aplicando}
        onCerrar={() => setAplicando(false)}
      />
    </FilaConAcciones>
  );
}
