/**
 * Diálogo de crear/editar una plantilla de contenido (catálogo unificado). Extraído de la
 * antigua página de Plantillas para reutilizarlo desde la Biblioteca unificada (las plantillas
 * son ahora un tipo más dentro de la misma navegación). Incluye el editor de variables y el
 * historial de versiones (git), a la par que los documentos.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { History, Loader2, Plus, RotateCcw, Wand2, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { confirmar } from "@/components/comunes/confirmar";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRed } from "@/components/comunes/SelectorRed";
import { desdeMarca, desdeRed, ningunaParam } from "@/components/comunes/selectores";
import { clavesEnEstructura } from "@/components/plantillas/util";
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
import { Markdown } from "@/components/ui/Markdown";
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

export const CLAVE_PLANTILLAS_CONTENIDO = ["plantillas-contenido"] as const;
const CLAVE_OPCIONES_PUBLICACIONES = ["publicaciones", "opciones"] as const;

interface FormPlantilla {
  nombre: string;
  modo: ModoPlantilla;
  tipo_nota: string;
  descripcion: string;
  marca: string;
  red: string;
  contenido: string;
  estructura: string;
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

function formDe(p: PlantillaContenido): FormPlantilla {
  return {
    nombre: p.nombre,
    modo: p.modo,
    tipo_nota: p.tipo_nota,
    descripcion: p.descripcion,
    marca: desdeMarca(p.marca),
    red: desdeRed(p.red),
    contenido: p.contenido,
    estructura: p.estructura,
    variables: p.variables,
  };
}

export function DialogoEditarPlantilla({
  plantilla,
  abierto,
  onCerrar,
}: {
  /** Plantilla a editar, o `null` para crear una nueva. */
  plantilla: PlantillaContenido | null;
  abierto: boolean;
  onCerrar: () => void;
}) {
  const qc = useQueryClient();
  const editId = plantilla?.id ?? null;
  const [form, setForm] = React.useState<FormPlantilla>(FORM_VACIO);
  const [historialAbierto, setHistorialAbierto] = React.useState(false);

  // Carga el formulario al abrir (de la plantilla dada, o vacío para crear).
  React.useEffect(() => {
    if (abierto) setForm(plantilla ? formDe(plantilla) : FORM_VACIO);
  }, [abierto, plantilla]);

  const opciones = useQuery<OpcionesPublicaciones>({
    queryKey: CLAVE_OPCIONES_PUBLICACIONES,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];
  const redes = opciones.data?.redes ?? [];

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
        contenido: esPlano ? form.contenido : "",
        estructura: esPlano ? "" : form.estructura,
        variables: esPlano ? [] : form.variables,
      };
      if (editId) return api.actualizarPlantillaContenido(editId, cuerpo);
      return api.crearPlantillaContenido(cuerpo);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CLAVE_PLANTILLAS_CONTENIDO });
      onCerrar();
      toast.success(editId ? "Plantilla actualizada." : "Plantilla creada.");
    },
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo guardar."),
  });

  function setVariable(i: number, parcial: Partial<VariablePlantilla>) {
    setForm((f) => ({
      ...f,
      variables: f.variables.map((v, idx) => (idx === i ? { ...v, ...parcial } : v)),
    }));
  }
  function anadirVariable() {
    setForm((f) => ({ ...f, variables: [...f.variables, { clave: "", etiqueta: "", ejemplo: "" }] }));
  }
  function quitarVariable(i: number) {
    setForm((f) => ({ ...f, variables: f.variables.filter((_, idx) => idx !== i) }));
  }

  const clavesEstructura = clavesEnEstructura(form.estructura);
  const clavesDeclaradas = new Set(form.variables.map((v) => v.clave).filter(Boolean));
  const sinDeclarar = clavesEstructura.filter((c) => !clavesDeclaradas.has(c));

  function autocompletarVariables() {
    if (sinDeclarar.length === 0) return;
    setForm((f) => ({
      ...f,
      variables: [...f.variables, ...sinDeclarar.map((clave) => ({ clave, etiqueta: "", ejemplo: "" }))],
    }));
  }

  const cuerpoLleno =
    form.modo === "plano" ? form.contenido.trim() !== "" : form.estructura.trim() !== "";
  const puedeGuardar = form.nombre.trim() !== "" && cuerpoLleno;

  return (
    <>
      <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editId ? "Editar plantilla" : "Nueva plantilla"}</DialogTitle>
            <DialogDescription>
              Elige el modo: <strong>plano</strong> (texto fijo reutilizable) o{" "}
              <strong>estructura</strong> con marcadores{" "}
              <code className="rounded bg-muted px-1">{"{{variable}}"}</code> que se rellenan al aplicar.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            <Tabs value={form.modo} onValueChange={(v) => setForm((f) => ({ ...f, modo: v as ModoPlantilla }))}>
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
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="text-xs text-amber-600 dark:text-amber-400">
                        Variables usadas sin declarar: {sinDeclarar.join(", ")}.
                      </p>
                      <Button type="button" variant="outline" size="sm" className="h-7" onClick={autocompletarVariables}>
                        <Wand2 className="mr-1 h-3.5 w-3.5" /> Auto-completar variables
                      </Button>
                    </div>
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
                      <Input value={v.clave} onChange={(e) => setVariable(i, { clave: e.target.value })} placeholder="clave" aria-label={`Clave de la variable ${i + 1}`} />
                      <Input value={v.etiqueta} onChange={(e) => setVariable(i, { etiqueta: e.target.value })} placeholder="Etiqueta" aria-label={`Etiqueta de la variable ${i + 1}`} />
                      <Input value={v.ejemplo} onChange={(e) => setVariable(i, { ejemplo: e.target.value })} placeholder="Ejemplo" aria-label={`Ejemplo de la variable ${i + 1}`} />
                      <Button type="button" variant="ghost" size="icon" onClick={() => quitarVariable(i)} aria-label={`Quitar variable ${i + 1}`}>
                        <X className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          <DialogFooter>
            {editId && (
              <Button variant="outline" className="mr-auto" onClick={() => setHistorialAbierto(true)} title="Historial de versiones">
                <History className="mr-1.5 h-4 w-4" /> Historial
              </Button>
            )}
            <Button variant="outline" onClick={onCerrar}>Cancelar</Button>
            <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar || guardar.isPending}>
              {guardar.isPending && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
              {editId ? "Guardar" : "Crear"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {editId && (
        <DialogHistorialPlantilla
          plantillaId={editId}
          abierto={historialAbierto}
          onCerrar={() => setHistorialAbierto(false)}
          onRestaurada={(p) => {
            setForm(formDe(p));
            qc.invalidateQueries({ queryKey: CLAVE_PLANTILLAS_CONTENIDO });
            setHistorialAbierto(false);
            toast.success("Versión restaurada.");
          }}
        />
      )}
    </>
  );
}

/** Historial de versiones (git) de una plantilla: lista de commits + ver versión + restaurar. */
function DialogHistorialPlantilla({
  plantillaId,
  abierto,
  onCerrar,
  onRestaurada,
}: {
  plantillaId: string;
  abierto: boolean;
  onCerrar: () => void;
  onRestaurada: (p: PlantillaContenido) => void;
}) {
  const [verSha, setVerSha] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!abierto) setVerSha(null);
  }, [abierto]);

  const histQuery = useQuery({
    queryKey: ["plantilla-historial", plantillaId],
    queryFn: ({ signal }) => api.historialPlantilla(plantillaId, signal),
    enabled: abierto,
  });
  const versionQuery = useQuery({
    queryKey: ["plantilla-version", plantillaId, verSha],
    queryFn: ({ signal }) => api.versionPlantilla(plantillaId, verSha as string, signal),
    enabled: abierto && !!verSha,
  });
  const revertir = useMutation({
    mutationFn: (sha: string) => api.revertirPlantilla(plantillaId, sha),
    onSuccess: (r) => onRestaurada(r.plantilla),
    onError: (e) => toast.error(e instanceof ApiError ? e.message : "No se pudo restaurar."),
  });

  const historial = histQuery.data?.historial ?? [];
  const ver = versionQuery.data?.plantilla;

  return (
    <Dialog open={abierto} onOpenChange={(v) => !v && onCerrar()}>
      <DialogContent className="flex max-h-[88vh] flex-col gap-3 overflow-hidden sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <History className="h-4 w-4" /> Historial de versiones
          </DialogTitle>
        </DialogHeader>
        <div className="flex min-h-0 flex-1 gap-3">
          <div className="w-64 shrink-0 overflow-y-auto rounded-md border border-border">
            {histQuery.isPending ? (
              <div className="p-3"><Skeleton className="h-8 w-full" /></div>
            ) : historial.length === 0 ? (
              <p className="p-3 text-sm text-muted-foreground">
                Sin versiones registradas. (El versionado git puede estar desactivado.)
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {historial.map((v) => (
                  <li key={v.sha}>
                    <button
                      onClick={() => setVerSha(v.sha)}
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-muted ${v.sha === verSha ? "bg-muted" : ""}`}
                    >
                      <span className="block font-medium">{v.mensaje}</span>
                      <span className="mt-0.5 block text-muted-foreground">
                        {v.autor} · {v.fecha.slice(0, 16).replace("T", " ")}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-2">
            {!verSha ? (
              <p className="text-sm text-muted-foreground">Elige una versión para verla y, si quieres, restaurarla.</p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Versión {verSha.slice(0, 8)}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    disabled={revertir.isPending}
                    onClick={async () => {
                      if (
                        await confirmar({
                          mensaje: "¿Restaurar esta versión? Se guarda como un cambio nuevo (no se pierde el historial).",
                          textoConfirmar: "Restaurar",
                        })
                      )
                        revertir.mutate(verSha);
                    }}
                  >
                    <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restaurar
                  </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
                  {versionQuery.isPending ? (
                    <Skeleton className="h-24 w-full" />
                  ) : (
                    <Markdown>{ver ? (ver.modo === "plano" ? ver.contenido : ver.estructura) || "_Sin contenido_" : "_Sin contenido_"}</Markdown>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
