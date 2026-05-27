import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, RefreshCw, Sparkles } from "lucide-react";
import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import { EstadoMensaje } from "@/components/layout/EstadoMensaje";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { GrupoSkills, RespuestaEjecutarSkill, RespuestaGeneracion, Skill } from "@/types";

import { CamposSkill } from "./CamposSkill";
import {
  campoArchivo,
  campoUrl,
  esSkillConArchivo,
  esSkillDesdeUrl,
  filtrarGrupos,
  puedeGenerarSkill,
  valoresIniciales,
  valoresRecortados,
} from "./dynamico";
import { Historial } from "./Historial";
import { ResultadoDocumento } from "./ResultadoDocumento";
import { ResultadoRedes } from "./ResultadoRedes";
import { VistaPrompt } from "./VistaPrompt";
import { ORDEN_REDES } from "../publicaciones/meta";

/** Aplana los grupos en un mapa id -> skill para resolver metadatos. */
function indexarSkills(grupos: GrupoSkills[]): Map<string, Skill> {
  const mapa = new Map<string, Skill>();
  for (const grupo of grupos) {
    for (const skill of grupo.skills) mapa.set(skill.id, skill);
  }
  return mapa;
}

/** Esqueleto de carga para el formulario completo. */
function EsqueletoFormulario({ conHistorial }: { conHistorial: boolean }) {
  return (
    <div className={cn("grid gap-6", conHistorial && "lg:grid-cols-[minmax(0,1fr)_22rem]")}>
      <Card>
        <CardHeader className="pb-3">
          <Skeleton className="h-5 w-40" />
        </CardHeader>
        <CardContent className="space-y-4">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-36 w-full" />
          <Skeleton className="h-9 w-32" />
        </CardContent>
      </Card>
      {conHistorial && (
        <Card>
          <CardHeader className="pb-3">
            <Skeleton className="h-5 w-28" />
          </CardHeader>
          <CardContent>
            <Skeleton className="h-40 w-full" />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/**
 * Núcleo reutilizable del flujo de generación con skills: selector de skill +
 * marca, formulario dinámico (incluido subir archivo), ejecución en segundo plano
 * (streaming en vivo + reanudable) y visor del resultado (piezas por red o
 * documento con galería de imágenes).
 *
 * Es el motor compartido entre "Generar copy" (skills editoriales NO de imagen) e
 * "Imágenes" (Estudio de imagen). Cada página lo configura con su cabecera, su
 * `filtroSkills` y su `claveGen` de `sessionStorage` (para no pisarse la
 * generación en curso entre pestañas).
 */
export function FlujoGeneracion({
  titulo,
  descripcion,
  claveGen,
  filtroSkills,
  placeholderSkill = "Elige una skill",
  etiquetaSkill = "Tipo de contenido",
  vacioMensaje = "No hay skills disponibles para esta sección.",
  conHistorial = true,
  iconoGenerar: IconoGenerar = Sparkles,
  textoGenerar = "Generar borrador",
}: {
  titulo: string;
  descripcion: string;
  /** Clave de sessionStorage para reanudar la generación en curso. */
  claveGen: string;
  /** Predicado para quedarse solo con ciertas skills (p. ej. de imagen). */
  filtroSkills: (skill: Skill) => boolean;
  placeholderSkill?: string;
  etiquetaSkill?: string;
  /** Mensaje cuando el filtro no deja ninguna skill. */
  vacioMensaje?: string;
  /** Muestra la columna del historial al lado del formulario. */
  conHistorial?: boolean;
  iconoGenerar?: React.ComponentType<{ className?: string }>;
  textoGenerar?: string;
}) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();

  const skillsQuery = useQuery({
    queryKey: ["skills"],
    queryFn: ({ signal }) => api.skills(signal),
  });

  const [skillId, setSkillId] = React.useState("");
  const [marcaId, setMarcaId] = React.useState("");
  // Valores del formulario dinámico: id de campo -> valor de texto.
  const [valores, setValores] = React.useState<Record<string, string>>({});
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [redes, setRedes] = React.useState<Set<string>>(new Set());

  // Generación en segundo plano (streaming en vivo + reanudable al cambiar de pestaña).
  const { generacion, ejecutando, cancelando, iniciar, cancelar } = useGeneracion(claveGen);

  // Grupos filtrados a las skills de esta sección (descarta grupos vacíos).
  const grupos = React.useMemo(
    () => (skillsQuery.data ? filtrarGrupos(skillsQuery.data.grupos, filtroSkills) : []),
    [skillsQuery.data, filtroSkills],
  );

  const indice = React.useMemo(() => indexarSkills(grupos), [grupos]);
  const skillSeleccionada = skillId ? indice.get(skillId) : undefined;

  // Catálogo de redes: del backend (`/api/skills`); si falta, caemos a las canónicas.
  const opcionesRedes = React.useMemo(
    () =>
      skillsQuery.data?.redes?.map((r) => ({ id: r.id, nombre: r.nombre })) ??
      ORDEN_REDES.map((id) => ({ id, nombre: id })),
    [skillsQuery.data],
  );

  // Al cambiar de skill, reinicializamos los valores del formulario y el archivo.
  React.useEffect(() => {
    setValores(valoresIniciales(skillSeleccionada));
    setArchivo(null);
    // Solo depende de la skill seleccionada.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skillId, skillSeleccionada?.id]);

  // Por defecto, todas las redes marcadas (en cuanto conocemos el catálogo).
  React.useEffect(() => {
    setRedes((prev) => (prev.size === 0 ? new Set(opcionesRedes.map((r) => r.id)) : prev));
  }, [opcionesRedes]);

  // Prellenado desde otra página (p. ej. "Usar en Generar copy" desde Fuentes, o
  // "Generar copy" desde Métricas con una marca preseleccionada). Aceptamos
  // `texto` y `marca` por el `state` del router y, como alternativa, `?marca=` en
  // la query. El `texto` se vuelca en el PRIMER campo de tipo textarea/texto de la
  // skill seleccionada; si aún no hay skill, queda pendiente hasta que se elija.
  const [textoPendiente, setTextoPendiente] = React.useState<string | null>(null);
  React.useEffect(() => {
    const estado = location.state as { texto?: string; marca?: string } | null;
    const prefillTexto = estado?.texto;
    const marcaQuery = new URLSearchParams(location.search).get("marca") ?? undefined;
    const prefillMarca = estado?.marca ?? marcaQuery;

    if (typeof prefillTexto === "string" && prefillTexto.length > 0) {
      setTextoPendiente(prefillTexto);
    }
    if (typeof prefillMarca === "string" && prefillMarca.length > 0) {
      setMarcaId(prefillMarca);
    }
    if (estado?.texto != null || estado?.marca != null) {
      navigate(location.pathname, { replace: true, state: null });
    }
    // Solo al montar / cambiar el state o la query de navegación.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, location.search]);

  // Cuando hay texto pendiente y ya tenemos una skill con un campo de texto,
  // lo volcamos en el primer campo textarea/texto y limpiamos el pendiente.
  React.useEffect(() => {
    if (textoPendiente === null || !skillSeleccionada) return;
    const destino = skillSeleccionada.campos.find(
      (c) => c.tipo === "textarea" || c.tipo === "texto",
    );
    if (!destino) return;
    setValores((prev) => ({ ...prev, [destino.id]: textoPendiente }));
    setTextoPendiente(null);
  }, [textoPendiente, skillSeleccionada]);

  function setValor(id: string, valor: string) {
    setValores((prev) => ({ ...prev, [id]: valor }));
  }

  function alternarRed(red: string, marcada: boolean) {
    setRedes((prev) => {
      const siguiente = new Set(prev);
      if (marcada) siguiente.add(red);
      else siguiente.delete(red);
      return siguiente;
    });
  }

  // C-1: terminalRef se limpia en onSuccess de la mutación, para que la 2ª
  // generación (y sucesivas) disparen el toast y la invalidación correctamente.
  const terminalRef = React.useRef<string | null>(null);
  // A-3: captura la skill en el momento de lanzar la generación para que
  // resultadoCopy no dependa del selector UI (skillSeleccionada puede cambiar
  // mientras la generación corre en background).
  const skillGeneracionRef = React.useRef<Skill | undefined>(undefined);

  const mutacion = useMutation<RespuestaGeneracion, Error>({
    mutationFn: () => {
      if (!skillSeleccionada) throw new Error("Elige una skill.");
      const limpio = valoresRecortados(valores);
      const redesSel = skillSeleccionada.aplica_redes ? [...redes] : undefined;

      // Generar desde una URL (F9): el único insumo es un enlace; la extracción del
      // texto ocurre en el servidor. Va por su propio endpoint `ejecutar-url`.
      if (esSkillDesdeUrl(skillSeleccionada)) {
        const campo = campoUrl(skillSeleccionada);
        return api.ejecutarSkillUrl({
          skill: skillId,
          marca: marcaId,
          url: campo ? (limpio[campo.id] ?? "") : "",
          redes: redesSel,
        });
      }

      // Vía multipart SOLO si de verdad hay archivo. Una skill con campo archivo
      // OPCIONAL (p. ej. estudio-imagen, que puede generar sin foto) cae a la vía
      // JSON cuando el usuario no subió ninguno; el backend valida el resto de campos.
      if (esSkillConArchivo(skillSeleccionada) && archivo !== null) {
        return api.ejecutarSkillArchivo(skillId, marcaId, archivo, limpio, redesSel);
      }
      return api.ejecutarSkill({
        skill: skillId,
        marca: marcaId,
        valores: limpio,
        redes: redesSel,
      });
    },
    onSuccess: (data) => {
      // C-1: limpiar terminalRef antes de iniciar para que el useEffect terminal
      // se dispare también en la 2ª generación (y sucesivas) con el mismo id.
      terminalRef.current = null;
      // A-3: fijar la skill usada en el momento de lanzar.
      skillGeneracionRef.current = skillSeleccionada ?? undefined;
      // No bloquea: seguimos la generación en vivo y reaccionamos al completarse.
      iniciar(data.generacion);
      toast.success("Generación en curso. Puedes seguirla aquí o cambiar de pestaña.");
    },
    onError: (err) => {
      toast.error(err instanceof Error ? err.message : "No se pudo generar el borrador.");
    },
  });

  // Resultado de copy (forma RespuestaEjecutarSkill) cuando la generación completa
  // y la skill es de salida "piezas".
  const resultadoCopy: RespuestaEjecutarSkill | null = React.useMemo(() => {
    if (!generacion || generacion.estado !== "completado" || !generacion.resultado) return null;
    // A-3: usamos skillGeneracionRef (capturada al lanzar) en vez de skillSeleccionada
    // (selector UI), para que cambiar de skill durante la generación en background
    // no oculte el resultado.
    const skillUsada = skillGeneracionRef.current;
    if (skillUsada && skillUsada.salida !== "piezas") return null;
    const r = generacion.resultado;
    // Las skills de documento no traen `resultado`/`piezas`; las descartamos arriba.
    if (r.documento !== undefined && (r.piezas?.length ?? 0) === 0) return null;
    return {
      resultado: r.resultado ?? "",
      historial_id: r.historial_id ?? "",
      verdicto: r.verdicto ?? "",
      piezas: r.piezas ?? [],
      publicaciones: r.publicaciones ?? [],
    };
  }, [generacion]);

  // Resultado de documento cuando la generación completa y la skill es "documento".
  const resultadoDocumento = React.useMemo(() => {
    if (!generacion || generacion.estado !== "completado" || !generacion.resultado) return null;
    const r = generacion.resultado;
    if (r.documento === undefined) return null;
    return {
      documento: r.documento,
      historialId: r.historial_id ?? "",
      imagenes: r.imagenes ?? [],
    };
  }, [generacion]);

  // Efectos secundarios al alcanzar el estado terminal (una sola vez por generación).
  React.useEffect(() => {
    if (!generacion || generacion.id === terminalRef.current) return;
    if (generacion.estado === "completado") {
      terminalRef.current = generacion.id;
      const n = generacion.resultado?.publicaciones?.length ?? 0;
      toast.success(
        n > 0
          ? `Borrador generado y guardado en ${n} ${n === 1 ? "publicación" : "publicaciones"}`
          : "Borrador generado",
      );
      void queryClient.invalidateQueries({ queryKey: ["skills", "historial"] });
      void queryClient.invalidateQueries({ queryKey: ["publicaciones"] });
    } else if (generacion.estado === "error") {
      terminalRef.current = generacion.id;
      toast.error(generacion.error || "No se pudo generar el borrador.");
    }
  }, [generacion, queryClient]);

  const generando = mutacion.isPending || ejecutando;

  const puedeGenerar =
    !generando &&
    marcaId !== "" &&
    puedeGenerarSkill({ skill: skillSeleccionada, valores, archivo, redes });

  // --- Carga / error de las skills ---
  if (skillsQuery.isPending) {
    return (
      <>
        <PageHeader titulo={titulo} descripcion={descripcion} />
        <EsqueletoFormulario conHistorial={conHistorial} />
      </>
    );
  }

  if (skillsQuery.isError) {
    return (
      <>
        <PageHeader titulo={titulo} descripcion={descripcion} />
        <EstadoMensaje
          icono={AlertCircle}
          titulo="No se pudieron cargar las skills"
          mensaje={
            skillsQuery.error instanceof Error
              ? skillsQuery.error.message
              : "Ocurrió un problema inesperado. Vuelve a intentarlo."
          }
          accion={
            <Button
              variant="outline"
              size="sm"
              onClick={() => void skillsQuery.refetch()}
              disabled={skillsQuery.isFetching}
            >
              <RefreshCw className={cn("h-4 w-4", skillsQuery.isFetching && "animate-spin")} />
              Reintentar
            </Button>
          }
        />
      </>
    );
  }

  const { marcas } = skillsQuery.data;
  const campoArch = campoArchivo(skillSeleccionada);

  // Sin skills tras el filtro: la sección no aplica con el catálogo actual.
  if (grupos.length === 0) {
    return (
      <>
        <PageHeader titulo={titulo} descripcion={descripcion} />
        <EstadoMensaje icono={AlertCircle} titulo="Sin skills disponibles" mensaje={vacioMensaje} />
      </>
    );
  }

  return (
    <>
      <PageHeader titulo={titulo} descripcion={descripcion} />

      <div className={cn("grid gap-6", conHistorial && "lg:grid-cols-[minmax(0,1fr)_22rem]")}>
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Nuevo borrador</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {/* Selectores */}
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <Label htmlFor="select-skill">{etiquetaSkill}</Label>
                  <Select value={skillId} onValueChange={setSkillId}>
                    <SelectTrigger id="select-skill">
                      <SelectValue placeholder={placeholderSkill} />
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
                  {skillSeleccionada?.explicacion && (
                    <p className="text-xs text-muted-foreground">
                      {skillSeleccionada.explicacion}
                    </p>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="select-marca">Marca</Label>
                  <SelectorMarca
                    id="select-marca"
                    marcas={marcas}
                    valor={marcaId}
                    onCambio={setMarcaId}
                    incluirTodas={false}
                    placeholder="Elige una marca"
                    ariaLabel="Marca"
                    className="w-full"
                  />
                </div>
              </div>

              {skillSeleccionada ? (
                <>
                  {/* Formulario dinámico: un control por campo de la skill. */}
                  <CamposSkill
                    campos={skillSeleccionada.campos}
                    valores={valores}
                    onValor={setValor}
                    archivo={archivo}
                    onArchivo={setArchivo}
                  />

                  {/* Redes: solo si la skill genera piezas por red. */}
                  {skillSeleccionada.aplica_redes && (
                    <SelectorRedMultiple
                      opciones={opcionesRedes}
                      seleccionadas={redes}
                      onCambio={alternarRed}
                    />
                  )}

                  {/* Vista previa del prompt (solo lectura, en vivo). */}
                  <VistaPrompt
                    skillId={skillId}
                    marca={marcaId}
                    valores={valoresRecortados(valores)}
                    redes={skillSeleccionada.aplica_redes ? [...redes] : []}
                  />
                </>
              ) : (
                <p className="rounded-md border border-dashed border-border bg-muted/20 px-4 py-8 text-center text-sm text-muted-foreground">
                  Elige una skill para ver su formulario.
                </p>
              )}

              {/* Generar */}
              <div className="flex items-center gap-3">
                <Button disabled={!puedeGenerar} onClick={() => mutacion.mutate()}>
                  {generando ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <IconoGenerar className="h-4 w-4" />
                  )}
                  {generando ? "Generando…" : textoGenerar}
                </Button>
                {campoArch && (
                  <span className="text-xs text-muted-foreground">
                    El archivo se procesa en tu equipo antes de generar.
                  </span>
                )}
                {generando && (
                  <span className="text-xs text-muted-foreground">
                    Se genera en segundo plano: puedes cambiar de pestaña, el progreso continúa.
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Progreso en vivo mientras corre (texto token a token + métricas) + Cancelar (#137). */}
          {generacion && ejecutando && (
            <ProgresoGeneracion
              generacion={generacion}
              onCancelar={cancelar}
              cancelando={cancelando}
            />
          )}
          {/* Estado de error con opción de reintentar. */}
          {generacion && generacion.estado === "error" && (
            <ProgresoGeneracion generacion={generacion} onReintentar={() => mutacion.mutate()} />
          )}
          {/* Resultado por red (editores) cuando completa una skill de piezas. */}
          {resultadoCopy !== null && <ResultadoRedes respuesta={resultadoCopy} />}
          {/* Resultado en documento cuando completa una skill de documento. */}
          {resultadoDocumento !== null && (
            <ResultadoDocumento
              documento={resultadoDocumento.documento}
              historialId={resultadoDocumento.historialId}
              imagenes={resultadoDocumento.imagenes}
            />
          )}
        </div>

        {conHistorial && <Historial />}
      </div>
    </>
  );
}
