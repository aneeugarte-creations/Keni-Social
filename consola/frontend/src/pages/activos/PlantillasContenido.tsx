import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ClipboardCheck,
  Copy,
  FileText,
  Loader2,
  Pencil,
  Plus,
  Sparkles,
  Trash2,
  Wand2,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import {
  desdeMarca,
  desdeRed,
  ningunaParam,
} from "@/components/comunes/selectores";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { Textarea } from "@/components/ui/textarea";
import { api, ApiError } from "@/lib/api";
import type {
  PlantillaContenido,
  RespuestaSkills,
  VariablePlantilla,
} from "@/types";

const CLAVE_PLANTILLAS_CONTENIDO = ["plantillas-contenido"] as const;
const CLAVE_OPCIONES_SKILLS = ["skills"] as const;

const CABECERA = {
  titulo: "Plantillas de contenido",
  descripcion:
    "Estructuras reutilizables por tipo de nota recurrente (gol, alineación, efeméride…). " +
    "Rellena las variables y obtén el copy base. No publica nada: solo acelera armar piezas.",
};

// Extrae los marcadores `{{clave}}` de una estructura (para avisar de variables sin declarar).
const RE_MARCADOR = /\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g;

function clavesEnEstructura(estructura: string): string[] {
  const vistas: string[] = [];
  for (const m of estructura.matchAll(RE_MARCADOR)) {
    if (!vistas.includes(m[1])) vistas.push(m[1]);
  }
  return vistas;
}

/** Formulario controlado de crear/editar una plantilla de contenido. */
interface FormPlantilla {
  nombre: string;
  tipo_nota: string;
  descripcion: string;
  marca: string; // centinela MARCA_TODAS = sin marca
  red: string; // centinela RED_TODAS = sin red
  estructura: string;
  variables: VariablePlantilla[];
}

const FORM_VACIO: FormPlantilla = {
  nombre: "",
  tipo_nota: "",
  descripcion: "",
  marca: desdeMarca(""),
  red: desdeRed(""),
  estructura: "",
  variables: [],
};

export default function PlantillasContenido() {
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: CLAVE_PLANTILLAS_CONTENIDO,
    queryFn: ({ signal }) => api.plantillasContenido(undefined, signal),
  });
  const opciones = useQuery<RespuestaSkills>({
    queryKey: CLAVE_OPCIONES_SKILLS,
    queryFn: ({ signal }) => api.skills(signal),
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
      tipo_nota: p.tipo_nota,
      descripcion: p.descripcion,
      marca: desdeMarca(p.marca),
      red: desdeRed(p.red),
      estructura: p.estructura,
      variables: p.variables,
    });
    setAbierto(true);
  }

  const guardar = useMutation({
    mutationFn: async () => {
      const cuerpo = {
        nombre: form.nombre.trim(),
        tipo_nota: form.tipo_nota.trim(),
        descripcion: form.descripcion,
        marca: ningunaParam(form.marca),
        red: ningunaParam(form.red),
        estructura: form.estructura,
        variables: form.variables,
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

  const puedeGuardar = form.nombre.trim() !== "" && form.estructura.trim() !== "";

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
              Usa <code className="rounded bg-muted px-1">{"{{variable}}"}</code> en la
              estructura; declara cada variable abajo para rellenarla al aplicar.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="pc-nombre">Nombre</Label>
                <Input
                  id="pc-nombre"
                  value={form.nombre}
                  onChange={(e) => setForm((f) => ({ ...f, nombre: e.target.value }))}
                  placeholder="Plantilla de gol"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="pc-tipo">Tipo de nota</Label>
                <Input
                  id="pc-tipo"
                  value={form.tipo_nota}
                  onChange={(e) => setForm((f) => ({ ...f, tipo_nota: e.target.value }))}
                  placeholder="gol, alineación, efeméride…"
                />
              </div>
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

/** Tarjeta de una plantilla con su acción de "Aplicar" (rellenar variables). */
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
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-base">{plantilla.nombre}</CardTitle>
          <div className="flex shrink-0 gap-0.5">
            <Button variant="ghost" size="icon" onClick={onEditar} aria-label="Editar plantilla">
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onBorrar}
              disabled={borrando}
              aria-label="Borrar plantilla"
            >
              {borrando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
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
          {plantilla.estructura}
        </pre>
        <Button variant="secondary" size="sm" className="w-full" onClick={() => setAplicando(true)}>
          <Wand2 className="mr-1.5 h-4 w-4" /> Aplicar
        </Button>
      </CardContent>

      <DialogAplicar
        plantilla={plantilla}
        abierto={aplicando}
        onCerrar={() => setAplicando(false)}
      />
    </Card>
  );
}

/** Diálogo que rellena las variables y compone el copy en el servidor. */
function DialogAplicar({
  plantilla,
  abierto,
  onCerrar,
}: {
  plantilla: PlantillaContenido;
  abierto: boolean;
  onCerrar: () => void;
}) {
  const [valores, setValores] = React.useState<Record<string, string>>({});
  const [copy, setCopy] = React.useState("");
  const [faltan, setFaltan] = React.useState<string[]>([]);
  const [copiado, setCopiado] = React.useState(false);

  // Variables a rellenar: las declaradas o, si no hay, las detectadas en la estructura.
  const claves =
    plantilla.variables.length > 0
      ? plantilla.variables
      : clavesEnEstructura(plantilla.estructura).map((c) => ({ clave: c, etiqueta: "", ejemplo: "" }));

  React.useEffect(() => {
    if (abierto) {
      setValores({});
      setCopy("");
      setFaltan([]);
      setCopiado(false);
    }
  }, [abierto]);

  const aplicar = useMutation({
    mutationFn: () => api.aplicarPlantillaContenido(plantilla.id, { valores }),
    onSuccess: (r) => {
      setCopy(r.copy);
      setFaltan(r.faltan);
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo aplicar."),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(copy);
      setCopiado(true);
      toast.success("Copy copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar al portapapeles.");
    }
  }

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Aplicar: {plantilla.nombre}</DialogTitle>
          <DialogDescription>
            Rellena las variables y genera el copy base. Las que dejes vacías quedarán como
            marcador para completar a mano.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {claves.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Esta plantilla no tiene variables; el copy es su estructura tal cual.
            </p>
          )}
          {claves.map((v) => (
            <div key={v.clave} className="space-y-1.5">
              <Label htmlFor={`ap-${v.clave}`}>{v.etiqueta || v.clave}</Label>
              <Input
                id={`ap-${v.clave}`}
                value={valores[v.clave] ?? ""}
                onChange={(e) => setValores((prev) => ({ ...prev, [v.clave]: e.target.value }))}
                placeholder={v.ejemplo || `{{${v.clave}}}`}
              />
            </div>
          ))}

          {copy && (
            <div className="space-y-1.5">
              <Label>Copy</Label>
              <pre className="whitespace-pre-wrap rounded border bg-muted p-2 text-sm">{copy}</pre>
              {faltan.length > 0 && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Sin rellenar: {faltan.join(", ")}.
                </p>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
          {copy ? (
            <Button onClick={copiar}>
              {copiado ? (
                <ClipboardCheck className="mr-1.5 h-4 w-4" />
              ) : (
                <Copy className="mr-1.5 h-4 w-4" />
              )}
              Copiar copy
            </Button>
          ) : (
            <Button onClick={() => aplicar.mutate()} disabled={aplicar.isPending}>
              {aplicar.isPending ? (
                <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="mr-1.5 h-4 w-4" />
              )}
              Generar copy
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
