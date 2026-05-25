import { useQuery } from "@tanstack/react-query";
import { FileText, Image, Network, Pencil, Plus, RefreshCw, Trash2, Wand2 } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { SkillDef } from "@/types";

import { CLAVE_CATALOGO_SKILLS, etiquetaGrupo, mensajeError } from "./skills/claves";
import {
  DialogoBorrarSkill,
  DialogoCrearSkill,
  DialogoEditarSkill,
} from "./skills/GestionSkills";

/** Esqueleto de carga que imita la rejilla de skills. */
function EsqueletoSkills() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-56" />
          </CardHeader>
          <CardContent className="flex gap-2 pt-0">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-5 w-20" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

/** Insignias resumen de una skill (salida, redes, medios). */
function InsigniasSkill({ skill }: { skill: SkillDef }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant="secondary" className="gap-1 font-normal">
        {skill.salida === "documento" ? (
          <FileText className="h-3 w-3" />
        ) : (
          <Network className="h-3 w-3" />
        )}
        {skill.salida === "documento" ? "Documento" : "Piezas por red"}
      </Badge>
      {skill.aplica_redes && (
        <Badge variant="outline" className="gap-1 font-normal">
          <Network className="h-3 w-3" />
          Redes
        </Badge>
      )}
      {skill.media && (
        <Badge variant="outline" className="gap-1 font-normal">
          <Image className="h-3 w-3" aria-hidden />
          Medios
        </Badge>
      )}
      <Badge variant="outline" className="font-normal">
        {skill.campos.length} {skill.campos.length === 1 ? "campo" : "campos"}
      </Badge>
    </div>
  );
}

/** Tarjeta de una skill del catálogo, con acciones de editar y borrar. */
function TarjetaSkill({
  skill,
  onEditar,
  onBorrar,
}: {
  skill: SkillDef;
  onEditar: (id: string) => void;
  onBorrar: (s: SkillDef) => void;
}) {
  return (
    <Card className="flex flex-col">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Wand2 className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <span className="truncate">{skill.nombre}</span>
        </CardTitle>
        {skill.explicacion && (
          <p className="line-clamp-2 text-sm text-muted-foreground">{skill.explicacion}</p>
        )}
      </CardHeader>
      <CardContent className="pt-0">
        <InsigniasSkill skill={skill} />
      </CardContent>
      <div className="mt-auto flex items-center justify-end gap-1 border-t border-border px-4 py-2">
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground"
          onClick={() => onEditar(skill.id)}
        >
          <Pencil className="h-4 w-4" />
          Editar
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => onBorrar(skill)}
        >
          <Trash2 className="h-4 w-4" />
          Borrar
        </Button>
      </div>
    </Card>
  );
}

/**
 * Página de Skills: gestiona el catálogo editable de skills (las plantillas de
 * Generar copy). Lista por grupo (Validadas / Experimentales), y permite crear,
 * editar (metadatos + campos + SKILL.md) y borrar.
 */
export default function Skills() {
  const { data, isPending, isError, error, refetch, isFetching } = useQuery({
    queryKey: CLAVE_CATALOGO_SKILLS,
    queryFn: ({ signal }) => api.catalogoSkills(signal),
  });

  const [crear, setCrear] = React.useState(false);
  const [editando, setEditando] = React.useState<string | null>(null);
  const [borrando, setBorrando] = React.useState<SkillDef | null>(null);

  // Agrupa por grupo y ordena por `orden` dentro de cada grupo.
  const porGrupo = React.useMemo(() => {
    const grupos = new Map<string, SkillDef[]>();
    for (const skill of data?.skills ?? []) {
      const lista = grupos.get(skill.grupo) ?? [];
      lista.push(skill);
      grupos.set(skill.grupo, lista);
    }
    for (const lista of grupos.values()) lista.sort((a, b) => a.orden - b.orden);
    // Orden de grupos: validadas primero, experimentales después.
    return ["validadas", "experimentales"]
      .filter((g) => grupos.has(g))
      .map((g) => ({ grupo: g, skills: grupos.get(g) as SkillDef[] }));
  }, [data]);

  const acciones = (
    <>
      <Button variant="outline" onClick={() => void refetch()} disabled={isFetching}>
        <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} />
        Actualizar
      </Button>
      <Button onClick={() => setCrear(true)}>
        <Plus className="h-4 w-4" />
        Crear skill
      </Button>
    </>
  );

  return (
    <>
      <PageHeader
        titulo="Skills"
        descripcion="Gestiona las skills editoriales que alimentan Generar copy: sus campos, su plantilla de invocación y su SKILL.md."
        acciones={acciones}
      />

      {isPending ? (
        <EsqueletoSkills />
      ) : isError ? (
        <BloqueError
          titulo="No se pudieron cargar las skills"
          mensaje={mensajeError(error)}
          onReintentar={() => void refetch()}
          cargando={isFetching}
        />
      ) : data.skills.length === 0 ? (
        <EstadoVacio
          icono={Wand2}
          titulo="Aún no hay skills"
          texto="Crea una skill para definir un tipo de contenido con su propio formulario."
          accion={
            <Button size="sm" onClick={() => setCrear(true)}>
              <Plus className="h-4 w-4" />
              Crear skill
            </Button>
          }
        />
      ) : (
        <div className="space-y-8">
          {porGrupo.map(({ grupo, skills }) => (
            <section key={grupo} className="space-y-3">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-foreground">{etiquetaGrupo(grupo)}</h2>
                {grupo === "experimentales" && (
                  <Badge variant="aviso" className="font-normal">
                    Experimental
                  </Badge>
                )}
                <span className="text-xs text-muted-foreground">
                  {skills.length} {skills.length === 1 ? "skill" : "skills"}
                </span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {skills.map((skill) => (
                  <TarjetaSkill
                    key={skill.id}
                    skill={skill}
                    onEditar={setEditando}
                    onBorrar={setBorrando}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <DialogoCrearSkill
        abierto={crear}
        onCerrar={() => setCrear(false)}
        onCreada={(id) => setEditando(id)}
      />
      <DialogoEditarSkill skillId={editando} onCerrar={() => setEditando(null)} />
      <DialogoBorrarSkill skill={borrando} onCerrar={() => setBorrando(null)} />
    </>
  );
}
