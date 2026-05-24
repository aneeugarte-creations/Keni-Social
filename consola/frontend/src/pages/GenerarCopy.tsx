import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  FileAudio,
  FileText,
  Loader2,
  RefreshCw,
  Sparkles,
  Upload,
  X,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { GrupoSkills, RespuestaEjecutarSkill, Skill } from "@/types";

import { Historial } from "./copy/Historial";
import { Resultado } from "./copy/Resultado";
import { ResultadoRedes } from "./copy/ResultadoRedes";
import { SelectorRedes } from "./copy/SelectorRedes";
import { ORDEN_REDES } from "./publicaciones/meta";

type Modo = "texto" | "archivo";

/** Aplana los grupos en un mapa id -> {skill, grupo} para resolver metadatos. */
function indexarSkills(grupos: GrupoSkills[]): Map<string, { skill: Skill; grupo: GrupoSkills }> {
  const mapa = new Map<string, { skill: Skill; grupo: GrupoSkills }>();
  for (const grupo of grupos) {
    for (const skill of grupo.skills) {
      mapa.set(skill.id, { skill, grupo });
    }
  }
  return mapa;
}

/** Esqueleto de carga para el formulario completo. */
function EsqueletoFormulario() {
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-9 w-32" />
        </CardContent>
      </Card>
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-5 w-28" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-40 w-full" />
        </CardContent>
      </Card>
    </div>
  );
}

export default function GenerarCopy() {
  const queryClient = useQueryClient();

  const skillsQuery = useQuery({
    queryKey: ["skills"],
    queryFn: ({ signal }) => api.skills(signal),
  });

  // Catálogo de redes para los checkboxes. Si no se puede cargar, caemos a las
  // redes canónicas para no bloquear la generación.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });

  const opcionesRedes = React.useMemo(
    () =>
      opcionesQuery.data?.redes.map((r) => ({ id: r.id, nombre: r.nombre })) ??
      ORDEN_REDES.map((id) => ({ id, nombre: id })),
    [opcionesQuery.data],
  );

  const [skillId, setSkillId] = React.useState("");
  const [marcaId, setMarcaId] = React.useState("");
  const [titulo, setTitulo] = React.useState("");
  const [modo, setModo] = React.useState<Modo>("texto");
  const [texto, setTexto] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [redes, setRedes] = React.useState<Set<string>>(new Set());
  const [respuesta, setRespuesta] = React.useState<RespuestaEjecutarSkill | null>(null);
  // Marca/título usados en la última generación (para guardar coherente al editar arriba).
  const [contextoResultado, setContextoResultado] = React.useState<{
    titulo: string;
    marca: string;
  } | null>(null);
  const inputArchivoRef = React.useRef<HTMLInputElement>(null);

  // Por defecto, todas las redes marcadas (en cuanto conocemos el catálogo).
  React.useEffect(() => {
    setRedes((prev) =>
      prev.size === 0 ? new Set(opcionesRedes.map((r) => r.id)) : prev,
    );
  }, [opcionesRedes]);

  const indice = React.useMemo(
    () => (skillsQuery.data ? indexarSkills(skillsQuery.data.grupos) : new Map()),
    [skillsQuery.data],
  );

  // Una skill es "de medios" si su id figura en skills_media: solo acepta
  // archivo (video/audio) y no permite pegar texto (se transcribe en local).
  const esSkillMedia = React.useMemo(
    () => (skillId ? (skillsQuery.data?.skills_media.includes(skillId) ?? false) : false),
    [skillId, skillsQuery.data],
  );

  // Si cambia la skill seleccionada, ajustamos el modo de entrada permitido.
  React.useEffect(() => {
    if (esSkillMedia) {
      setModo("archivo");
      setTexto("");
    } else {
      setModo("texto");
    }
    setArchivo(null);
    if (inputArchivoRef.current) inputArchivoRef.current.value = "";
  }, [skillId, esSkillMedia]);

  const mutacion = useMutation<RespuestaEjecutarSkill, Error>({
    mutationFn: () => {
      const redesSel = [...redes];
      if (modo === "archivo") {
        // archivo no nulo: garantizado por la guarda de `puedeGenerar`.
        return api.ejecutarSkillArchivo(skillId, marcaId, archivo as File, redesSel);
      }
      return api.ejecutarSkill({
        skill: skillId,
        marca: marcaId,
        texto: texto.trim(),
        redes: redesSel,
      });
    },
    onSuccess: (data) => {
      setRespuesta(data);
      setContextoResultado({ titulo, marca: marcaId });
      toast.success("Borrador generado");
      void queryClient.invalidateQueries({ queryKey: ["skills", "historial"] });
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "No se pudo generar el borrador.");
    },
  });

  const generando = mutacion.isPending;

  const puedeGenerar =
    !generando &&
    skillId !== "" &&
    marcaId !== "" &&
    redes.size > 0 &&
    (modo === "archivo" ? archivo !== null : texto.trim().length > 0);

  function onArchivo(e: React.ChangeEvent<HTMLInputElement>) {
    setArchivo(e.target.files?.[0] ?? null);
  }

  function limpiarArchivo() {
    setArchivo(null);
    if (inputArchivoRef.current) inputArchivoRef.current.value = "";
  }

  function alternarRed(red: string, marcada: boolean) {
    setRedes((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  // --- Carga / error de las skills ---
  if (skillsQuery.isPending) {
    return (
      <>
        <PageHeader
          titulo="Generar copy"
          descripcion="Crea borradores de publicaciones con las skills editoriales para cada marca."
        />
        <EsqueletoFormulario />
      </>
    );
  }

  if (skillsQuery.isError) {
    return (
      <>
        <PageHeader
          titulo="Generar copy"
          descripcion="Crea borradores de publicaciones con las skills editoriales para cada marca."
        />
        <Card className="border-destructive/40">
          <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <AlertCircle className="h-6 w-6" />
            </div>
            <div className="space-y-1">
              <p className="font-medium">No se pudieron cargar las skills</p>
              <p className="max-w-md text-sm text-muted-foreground">
                {skillsQuery.error instanceof Error
                  ? skillsQuery.error.message
                  : "Ocurrió un problema inesperado. Vuelve a intentarlo."}
              </p>
            </div>
            <Button
              onClick={() => void skillsQuery.refetch()}
              disabled={skillsQuery.isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", skillsQuery.isFetching && "animate-spin")} />
              Reintentar
            </Button>
          </CardContent>
        </Card>
      </>
    );
  }

  const { grupos, marcas } = skillsQuery.data;
  const skillSeleccionada = skillId ? indice.get(skillId)?.skill : undefined;
  const tienePiezas = (respuesta?.piezas.length ?? 0) > 0;

  return (
    <>
      <PageHeader
        titulo="Generar copy"
        descripcion="Crea borradores de publicaciones con las skills editoriales para cada marca."
      />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Nuevo borrador</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Selectores */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="select-skill">Tipo de contenido</Label>
                  <Select value={skillId} onValueChange={setSkillId}>
                    <SelectTrigger id="select-skill">
                      <SelectValue placeholder="Elige una skill" />
                    </SelectTrigger>
                    <SelectContent>
                      {grupos.map((grupo, gi) => (
                        <React.Fragment key={grupo.etiqueta}>
                          {gi > 0 && <SelectSeparator />}
                          <SelectGroup>
                            <SelectLabel className="flex items-center gap-2">
                              {grupo.etiqueta}
                              {grupo.experimental && (
                                <Badge variant="aviso" className="font-normal">
                                  Experimental
                                </Badge>
                              )}
                            </SelectLabel>
                            {grupo.skills.map((skill) => (
                              <SelectItem key={skill.id} value={skill.id}>
                                <span className="flex items-center gap-2">
                                  {skill.nombre}
                                  {grupo.experimental && (
                                    <Badge variant="aviso" className="font-normal">
                                      Experimental
                                    </Badge>
                                  )}
                                </span>
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </React.Fragment>
                      ))}
                    </SelectContent>
                  </Select>
                  {skillSeleccionada?.descripcion && (
                    <p className="text-xs text-muted-foreground">
                      {skillSeleccionada.descripcion}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="select-marca">Marca</Label>
                  <Select value={marcaId} onValueChange={setMarcaId}>
                    <SelectTrigger id="select-marca">
                      <SelectValue placeholder="Elige una marca" />
                    </SelectTrigger>
                    <SelectContent>
                      {marcas.map((marca) => (
                        <SelectItem key={marca.id} value={marca.id}>
                          {marca.nombre}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Título */}
              <div className="space-y-1.5">
                <Label htmlFor="titulo-publicacion">
                  Título <span className="text-muted-foreground">(opcional)</span>
                </Label>
                <Input
                  id="titulo-publicacion"
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  placeholder="Ej. Lanzamiento campaña verano"
                  maxLength={200}
                />
              </div>

              {/* Redes */}
              <SelectorRedes
                opciones={opcionesRedes}
                seleccionadas={redes}
                onCambio={alternarRed}
              />

              {/* Entrada dual */}
              {esSkillMedia ? (
                <EntradaArchivo
                  archivo={archivo}
                  inputRef={inputArchivoRef}
                  onArchivo={onArchivo}
                  onLimpiar={limpiarArchivo}
                  acepta="video/*,audio/*"
                  ayuda="Sube un video o audio. Se transcribe en tu equipo (en local) y luego se genera el borrador. Esta skill no admite texto pegado."
                  media
                />
              ) : (
                <Tabs value={modo} onValueChange={(v) => setModo(v as Modo)}>
                  <TabsList>
                    <TabsTrigger value="texto">Pegar texto</TabsTrigger>
                    <TabsTrigger value="archivo">Subir archivo</TabsTrigger>
                  </TabsList>
                  <TabsContent value="texto" className="space-y-1.5">
                    <Label htmlFor="texto-entrada" className="sr-only">
                      Texto de entrada
                    </Label>
                    <Textarea
                      id="texto-entrada"
                      value={texto}
                      onChange={(e) => setTexto(e.target.value)}
                      placeholder="Pega aquí la nota, el comunicado o el material base…"
                      className="min-h-[10rem]"
                    />
                  </TabsContent>
                  <TabsContent value="archivo">
                    <EntradaArchivo
                      archivo={archivo}
                      inputRef={inputArchivoRef}
                      onArchivo={onArchivo}
                      onLimpiar={limpiarArchivo}
                      acepta=".txt,.md,.doc,.docx,.pdf,text/*"
                      ayuda="Sube un documento de texto como material base para el borrador."
                    />
                  </TabsContent>
                </Tabs>
              )}

              {/* Generar */}
              <div className="flex items-center gap-3">
                <Button disabled={!puedeGenerar} onClick={() => mutacion.mutate()}>
                  {generando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  {generando ? "Generando…" : "Generar borrador"}
                </Button>
                {generando && (
                  <span className="text-xs text-muted-foreground">
                    Esto puede tardar hasta ~3 min. No cierres la página.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {respuesta !== null &&
            (tienePiezas ? (
              <ResultadoRedes
                respuesta={respuesta}
                titulo={contextoResultado?.titulo ?? ""}
                marca={contextoResultado?.marca ?? marcaId}
              />
            ) : (
              <Resultado resultado={respuesta.resultado} />
            ))}
        </div>

        <Historial />
      </div>
    </>
  );
}

/** Zona de subida de archivo reutilizable (modo texto-doc y modo medios). */
function EntradaArchivo({
  archivo,
  inputRef,
  onArchivo,
  onLimpiar,
  acepta,
  ayuda,
  media = false,
}: {
  archivo: File | null;
  inputRef: React.RefObject<HTMLInputElement>;
  onArchivo: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onLimpiar: () => void;
  acepta: string;
  ayuda: string;
  media?: boolean;
}) {
  const Icono = media ? FileAudio : FileText;
  return (
    <div className="space-y-2">
      <input
        ref={inputRef}
        type="file"
        accept={acepta}
        onChange={onArchivo}
        className="hidden"
      />
      {archivo ? (
        <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-2.5">
          <Icono className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-sm">{archivo.name}</span>
          <span className="shrink-0 text-xs text-muted-foreground">
            {(archivo.size / 1024 / 1024).toFixed(1)} MB
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 shrink-0"
            onClick={onLimpiar}
            aria-label="Quitar archivo"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-2 rounded-md border border-dashed border-border bg-muted/20 px-4 py-8 text-center transition-colors hover:bg-muted/40 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        >
          <Upload className="h-5 w-5 text-muted-foreground" />
          <span className="text-sm font-medium">Haz clic para elegir un archivo</span>
          <span className="text-xs text-muted-foreground">{ayuda}</span>
        </button>
      )}
      {archivo && <p className="text-xs text-muted-foreground">{ayuda}</p>}
    </div>
  );
}
