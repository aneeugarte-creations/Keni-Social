/**
 * Diálogos de gestión del catálogo de skills: crear, editar y borrar.
 *
 * - Crear: nombre + básicos (grupo, salida) → `POST /api/skills/catalogo`.
 * - Editar: editor con dos partes —metadatos (incl. editor de `campos`) y el
 *   cuerpo SKILL.md (Markdown)—. Carga ambos con `GET /api/skills/catalogo/{id}`;
 *   guarda metadatos con `PUT` y el SKILL.md con `PUT .../skill-md`.
 * - Borrar: confirmación → `DELETE`.
 *
 * React Query + invalidación (catálogo + la query `["skills"]` de Generar copy);
 * toasts (sonner); texto es-MX.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus, Save, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import type { Campo, SalidaSkill, SkillDef } from "@/types";

import { CLAVE_CATALOGO_SKILLS, claveSkill, mensajeError } from "./claves";
import { EditorCampos } from "./EditorCampos";

/** Invalida las cachés afectadas por un cambio en el catálogo. */
function useInvalidarSkills() {
  const queryClient = useQueryClient();
  return React.useCallback(
    (id?: string) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_CATALOGO_SKILLS });
      // La query de Generar copy también debe reflejar los cambios.
      void queryClient.invalidateQueries({ queryKey: ["skills"] });
      if (id) void queryClient.invalidateQueries({ queryKey: claveSkill(id) });
    },
    [queryClient],
  );
}

/** Diálogo para crear una skill nueva (nombre + básicos). */
export function DialogoCrearSkill({
  abierto,
  onCerrar,
  onCreada,
}: {
  abierto: boolean;
  onCerrar: () => void;
  onCreada: (id: string) => void;
}) {
  const invalidar = useInvalidarSkills();
  const [nombre, setNombre] = React.useState("");
  const [grupo, setGrupo] = React.useState<"validadas" | "experimentales">("validadas");
  const [salida, setSalida] = React.useState<SalidaSkill>("piezas");

  React.useEffect(() => {
    if (!abierto) {
      setNombre("");
      setGrupo("validadas");
      setSalida("piezas");
    }
  }, [abierto]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearSkill({ nombre: nombre.trim(), grupo, salida, aplica_redes: salida === "piezas" }),
    onSuccess: (res) => {
      invalidar();
      toast.success(`Skill «${res.skill.nombre}» creada`);
      onCerrar();
      onCreada(res.skill.id);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeCrear = nombre.trim().length > 0 && !crear.isPending;

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Crear skill
          </DialogTitle>
          <DialogDescription>
            Crea una skill nueva con lo básico. Después podrás editar sus campos, la
            plantilla de invocación y el cuerpo SKILL.md.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="skill-nombre">Nombre</Label>
            <Input
              id="skill-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Ej. Hilo para X"
              maxLength={100}
              autoFocus
              onKeyDown={(e) => {
                if (e.key === "Enter" && puedeCrear) crear.mutate();
              }}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="skill-grupo">Grupo</Label>
              <Select
                value={grupo}
                onValueChange={(v) => setGrupo(v as "validadas" | "experimentales")}
              >
                <SelectTrigger id="skill-grupo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="validadas">Validadas</SelectItem>
                  <SelectItem value="experimentales">Experimentales</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="skill-salida">Salida</Label>
              <Select value={salida} onValueChange={(v) => setSalida(v as SalidaSkill)}>
                <SelectTrigger id="skill-salida">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="piezas">Piezas por red</SelectItem>
                  <SelectItem value="documento">Documento</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={crear.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => crear.mutate()} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Formulario de metadatos + campos de una skill. El estado vive aquí dentro. */
function FormularioMetadatos({
  skill,
  onGuardar,
  guardando,
}: {
  skill: SkillDef;
  onGuardar: (cambios: {
    nombre: string;
    explicacion: string;
    grupo: "validadas" | "experimentales";
    aplica_redes: boolean;
    salida: SalidaSkill;
    media: boolean;
    orden: number;
    plantilla_invocacion: string;
    campos: Campo[];
  }) => void;
  guardando: boolean;
}) {
  const [nombre, setNombre] = React.useState(skill.nombre);
  const [explicacion, setExplicacion] = React.useState(skill.explicacion);
  const [grupo, setGrupo] = React.useState(skill.grupo);
  const [aplicaRedes, setAplicaRedes] = React.useState(skill.aplica_redes);
  const [salida, setSalida] = React.useState<SalidaSkill>(skill.salida);
  const [orden, setOrden] = React.useState(String(skill.orden));
  const [plantilla, setPlantilla] = React.useState(skill.plantilla_invocacion);
  const [campos, setCampos] = React.useState<Campo[]>(skill.campos);

  // `media` se deriva de los campos: hay archivo ⇒ es de medios.
  const media = campos.some((c) => c.tipo === "archivo");

  const puedeGuardar = nombre.trim().length > 0 && !guardando;

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="edit-nombre">Nombre</Label>
          <Input
            id="edit-nombre"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            maxLength={100}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="edit-orden">Orden</Label>
          <Input
            id="edit-orden"
            type="number"
            value={orden}
            onChange={(e) => setOrden(e.target.value)}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="edit-explicacion">Explicación</Label>
        <Textarea
          id="edit-explicacion"
          value={explicacion}
          onChange={(e) => setExplicacion(e.target.value)}
          placeholder="Una línea que describe qué hace la skill (se muestra en Generar copy)."
          className="min-h-[4rem]"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="edit-grupo">Grupo</Label>
          <Select
            value={grupo}
            onValueChange={(v) => setGrupo(v as "validadas" | "experimentales")}
          >
            <SelectTrigger id="edit-grupo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="validadas">Validadas</SelectItem>
              <SelectItem value="experimentales">Experimentales</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="edit-salida">Salida</Label>
          <Select value={salida} onValueChange={(v) => setSalida(v as SalidaSkill)}>
            <SelectTrigger id="edit-salida">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="piezas">Piezas por red</SelectItem>
              <SelectItem value="documento">Documento</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-start gap-2 rounded-md border border-border bg-muted/20 p-3">
        <Checkbox
          id="edit-aplica-redes"
          checked={aplicaRedes}
          onCheckedChange={setAplicaRedes}
          className="mt-0.5"
        />
        <div className="space-y-0.5">
          <Label htmlFor="edit-aplica-redes" className="cursor-pointer font-normal">
            Aplica a redes
          </Label>
          <p className="text-xs text-muted-foreground">
            Si está activo, Generar copy muestra el selector de redes y genera una
            pieza por red.
          </p>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="edit-plantilla">Plantilla de invocación</Label>
        <Textarea
          id="edit-plantilla"
          value={plantilla}
          onChange={(e) => setPlantilla(e.target.value)}
          placeholder="El prompt que se envía a Claude, con marcadores para los campos."
          className="min-h-[8rem] font-mono text-xs"
        />
        <p className="text-xs text-muted-foreground">
          Campo de medios:{" "}
          <span className="font-medium text-foreground">{media ? "sí" : "no"}</span> (se
          deriva de tener un campo de tipo archivo).
        </p>
      </div>

      <EditorCampos campos={campos} onCambio={setCampos} />

      <div className="flex justify-end">
        <Button
          onClick={() =>
            onGuardar({
              nombre: nombre.trim(),
              explicacion: explicacion.trim(),
              grupo,
              aplica_redes: aplicaRedes,
              salida,
              media,
              orden: Number.parseInt(orden, 10) || 0,
              plantilla_invocacion: plantilla,
              campos,
            })
          }
          disabled={!puedeGuardar}
        >
          {guardando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar metadatos
        </Button>
      </div>
    </div>
  );
}

/** Editor del cuerpo SKILL.md (Markdown). */
function EditorSkillMd({
  inicial,
  onGuardar,
  guardando,
}: {
  inicial: string;
  onGuardar: (contenido: string) => void;
  guardando: boolean;
}) {
  const [contenido, setContenido] = React.useState(inicial);

  return (
    <div className="space-y-3">
      <div className="space-y-1.5">
        <Label htmlFor="edit-skill-md">SKILL.md</Label>
        <Textarea
          id="edit-skill-md"
          value={contenido}
          onChange={(e) => setContenido(e.target.value)}
          placeholder="Instrucciones de la skill en Markdown."
          className="min-h-[24rem] font-mono text-xs leading-relaxed"
        />
      </div>
      <div className="flex justify-end">
        <Button onClick={() => onGuardar(contenido)} disabled={guardando}>
          {guardando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Guardar SKILL.md
        </Button>
      </div>
    </div>
  );
}

/** Diálogo de edición completo de una skill (metadatos + campos + SKILL.md). */
export function DialogoEditarSkill({
  skillId,
  onCerrar,
}: {
  /** Id de la skill a editar; `null` cierra el diálogo. */
  skillId: string | null;
  onCerrar: () => void;
}) {
  const invalidar = useInvalidarSkills();

  const detalle = useQuery({
    queryKey: skillId ? claveSkill(skillId) : ["skills", "catalogo", "vacio"],
    queryFn: ({ signal }) => api.skillCatalogo(skillId as string, signal),
    enabled: skillId !== null,
  });

  const guardarMeta = useMutation({
    mutationFn: (cambios: Parameters<typeof api.actualizarSkill>[1]) =>
      api.actualizarSkill(skillId as string, cambios),
    onSuccess: () => {
      invalidar(skillId ?? undefined);
      toast.success("Metadatos guardados");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const guardarMd = useMutation({
    mutationFn: (contenido: string) => api.guardarSkillMd(skillId as string, contenido),
    onSuccess: (res) => {
      invalidar(skillId ?? undefined);
      toast.success(res?.mensaje ?? "SKILL.md guardado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={skillId !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {detalle.data ? `Editar: ${detalle.data.skill.nombre}` : "Editar skill"}
          </DialogTitle>
          <DialogDescription>
            Edita los metadatos y los campos del formulario, y el cuerpo de instrucciones
            (SKILL.md). Cada parte se guarda por separado.
          </DialogDescription>
        </DialogHeader>

        {detalle.isPending ? (
          <div className="space-y-3">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : detalle.isError ? (
          <p className="text-sm text-destructive">
            {detalle.error instanceof Error
              ? detalle.error.message
              : "No se pudo cargar la skill."}
          </p>
        ) : detalle.data ? (
          <Tabs defaultValue="metadatos">
            <TabsList>
              <TabsTrigger value="metadatos">Metadatos y campos</TabsTrigger>
              <TabsTrigger value="skill-md">SKILL.md</TabsTrigger>
            </TabsList>
            <TabsContent value="metadatos" className="pt-4">
              <FormularioMetadatos
                skill={detalle.data.skill}
                onGuardar={(cambios) => guardarMeta.mutate(cambios)}
                guardando={guardarMeta.isPending}
              />
            </TabsContent>
            <TabsContent value="skill-md" className="pt-4">
              <EditorSkillMd
                inicial={detalle.data.skill_md}
                onGuardar={(c) => guardarMd.mutate(c)}
                guardando={guardarMd.isPending}
              />
            </TabsContent>
          </Tabs>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/** Diálogo de confirmación para borrar una skill. */
export function DialogoBorrarSkill({
  skill,
  onCerrar,
}: {
  /** Skill a borrar; `null` cierra el diálogo. */
  skill: SkillDef | null;
  onCerrar: () => void;
}) {
  const invalidar = useInvalidarSkills();

  const borrar = useMutation({
    mutationFn: () => {
      if (!skill) throw new Error("Sin skill seleccionada.");
      return api.eliminarSkill(skill.id);
    },
    onSuccess: (res) => {
      invalidar();
      toast.success(res?.mensaje ?? "Skill borrada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={skill !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <Trash2 className="h-5 w-5" />
            Borrar skill
          </DialogTitle>
          <DialogDescription>
            Vas a borrar la skill{" "}
            <span className="font-medium text-foreground">{skill?.nombre}</span>. Esto
            elimina su definición y su SKILL.md. Esta acción no se puede deshacer.
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={borrar.isPending}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={() => borrar.mutate()}
            disabled={borrar.isPending}
          >
            {borrar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4" />
            )}
            Borrar skill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
