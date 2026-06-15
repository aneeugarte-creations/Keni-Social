/**
 * Vista DETALLE de un documento de la Biblioteca de Prompts.
 *
 * Cabecera de estado (título editable + línea de deployment + acciones), cuerpo SIEMPRE
 * WYSIWYG (EditorWysiwyg con chips de variables; la edición es libre: producción no
 * cambia hasta publicar), y panel lateral con pestañas:
 *   - Versiones (PanelVersiones: publicado ↔ tu borrador, diff ancho, traer/descartar),
 *   - Uso (dónde entra el doc: procesos, pipelines y su sitio en el riel de la máquina),
 *   - Compilado (solo prompts base de pipeline: el prompt ENSAMBLADO que verá el modelo),
 *   - Ficha (metadata: descripción, carpeta, clase, marcas, etiquetas, prioridad).
 *
 * El candado "forzar edición" desapareció: con el modelo de publicación editar es seguro
 * (los pipelines sirven la versión PUBLICADA si existe). En prompts con `procesos` queda
 * una nota informativa de dónde se inyecta.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  MoreHorizontal,
  Rocket,
  Send,
  Trash2,
  Zap,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { DialogPublicar } from "@/components/biblioteca/DialogPublicar";
import { LectorProsa } from "@/components/biblioteca/LectorProsa";
import { PanelVersiones } from "@/components/biblioteca/PanelVersiones";
import { confirmar } from "@/components/comunes/confirmar";
import { MenuFlotante } from "@/components/comunes/MenuContextual";
import { EditorWysiwyg } from "@/components/editor/EditorWysiwyg";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMenuContextual } from "@/hooks/use-menu-contextual";
import { useEsAdmin } from "@/hooks/use-biblioteca";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { tiempoRelativo } from "@/lib/fecha";
import type { DocumentoTexto, EtapaPrompt, RespuestaMaquinaTexto } from "@/types";

import { claveEstrategiaBase } from "./estrategia/api";
import { separarFrontmatter } from "./lib";
import { PanelLanzar } from "./PanelLanzar";

const ESTADOS_DOC = ["activo", "borrador", "archivado"] as const;
const CLASES_EDITORIAL = ["marca", "voz", "plataforma", "tropicalizacion", "reglas"] as const;

type PestanaPanel = "versiones" | "uso" | "compilado" | "ficha";

/** Pestaña "Uso": dónde entra este documento (procesos, pipelines y su etapa en las máquinas). */
function PanelUso({ doc, maquina }: { doc: DocumentoTexto; maquina?: RespuestaMaquinaTexto }) {
  // Posición del doc en las TRES máquinas: etapas `prompt` cuyo doc_id es este doc.
  const etapas = React.useMemo(
    () =>
      (maquina?.maquinas ?? []).flatMap((m) =>
        m.etapas
          .filter((e): e is EtapaPrompt => e.tipo === "prompt" && e.doc_id === doc.id)
          .map((e) => `${m.titulo} → ${e.titulo}`),
      ),
    [maquina, doc.id],
  );
  const procesos = doc.procesos ?? [];
  const pipelines = doc.pipelines ?? [];
  const nada =
    procesos.length === 0 && pipelines.length === 0 && etapas.length === 0 && !doc.rol;

  return (
    <div className="space-y-4 text-sm">
      {procesos.length > 0 ? (
        <section>
          <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            <Zap className="h-3.5 w-3.5 text-keni" /> Procesos donde se inyecta
          </h4>
          <ul className="mt-1.5 space-y-1">
            {procesos.map((p) => (
              <li key={p} className="flex gap-2">
                <span className="text-keni">→</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {pipelines.length > 0 || doc.rol ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Pipelines
          </h4>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {doc.rol ? (
              <span className="rounded-full bg-keni/10 px-2 py-0.5 text-xs font-medium text-keni">
                rol: {doc.rol}
              </span>
            ) : null}
            {pipelines.map((p) => (
              <span key={p} className="rounded-full bg-muted px-2 py-0.5 text-xs">
                {p}
              </span>
            ))}
          </div>
        </section>
      ) : null}
      {etapas.length > 0 ? (
        <section>
          <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            En las máquinas
          </h4>
          <ul className="mt-1.5 space-y-1 text-sm">
            {etapas.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {nada ? (
        <p className="text-sm text-muted-foreground">
          Se ejecuta a mano con «Probar» o se adjunta según su clase y marcas.
        </p>
      ) : null}
    </div>
  );
}

/** Pestaña "Compilado": el prompt ENSAMBLADO del pipeline (lo que verá el modelo). */
function PanelCompilado({ pipelineId }: { pipelineId: string }) {
  const { marcaActiva } = useMarcaActiva();
  const previewQuery = useQuery({
    queryKey: ["texto-preview", pipelineId, marcaActiva],
    queryFn: ({ signal }) => api.previewPipeline(pipelineId, marcaActiva as string, undefined, signal),
    enabled: !!marcaActiva,
  });

  if (!marcaActiva) {
    return (
      <p className="text-sm text-muted-foreground">
        Elige una marca para ver el prompt ensamblado de ese modelo.
      </p>
    );
  }
  if (previewQuery.isPending) return <Skeleton className="h-24 w-full" />;
  if (previewQuery.isError) {
    return <p className="text-sm text-muted-foreground">{mensajeError(previewQuery.error)}</p>;
  }
  const preview = previewQuery.data;
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Prompt ensamblado para esta marca
      </p>
      {preview.adjuntos.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {preview.adjuntos.map((a) => (
            <span key={a.id} className="rounded-full bg-muted px-2 py-0.5 text-xs" title={a.clase}>
              {a.titulo}
            </span>
          ))}
        </div>
      ) : null}
      <div className="rounded-md border border-border bg-muted/20 p-3">
        <LectorProsa cuerpo={preview.prompt_efectivo} />
      </div>
    </div>
  );
}

/** Pestaña "Ficha": metadata editable del documento (vive en el panel, no estorba al cuerpo). */
function PanelFicha({
  borrador,
  marcas,
  onEditar,
}: {
  borrador: DocumentoTexto;
  marcas: { id: string; nombre: string }[];
  onEditar: (parcial: Partial<DocumentoTexto>) => void;
}) {
  const esEditorial = borrador.tipo !== "prompt";
  return (
    <div className="space-y-3 text-sm">
      <div className="space-y-1">
        <Label htmlFor="ficha-descripcion" className="text-xs">
          Descripción
        </Label>
        <Input
          id="ficha-descripcion"
          value={borrador.descripcion ?? ""}
          onChange={(e) => onEditar({ descripcion: e.target.value })}
          placeholder="Qué es y para qué"
          className="h-8 text-xs"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="ficha-carpeta" className="text-xs">
          Carpeta
        </Label>
        <Input
          id="ficha-carpeta"
          value={borrador.carpeta}
          onChange={(e) => onEditar({ carpeta: e.target.value })}
          placeholder="sin carpeta"
          className="h-8 text-xs"
        />
      </div>
      {esEditorial ? (
        <div className="space-y-1">
          <Label htmlFor="ficha-clase" className="text-xs">
            Clase
          </Label>
          <select
            id="ficha-clase"
            value={borrador.clase || ""}
            onChange={(e) => onEditar({ clase: e.target.value })}
            className="h-8 w-full rounded-md border border-input bg-background px-2 text-xs"
          >
            <option value="">(sin clase)</option>
            {CLASES_EDITORIAL.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      ) : null}
      {esEditorial && marcas.length > 0 ? (
        <fieldset className="space-y-1">
          <legend className="text-xs font-medium">Marcas a las que aplica</legend>
          <div className="space-y-1">
            {marcas.map((m) => {
              const activa = (borrador.marcas ?? []).includes(m.id);
              return (
                <label key={m.id} className="flex cursor-pointer items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={activa}
                    onChange={(e) => {
                      const set = new Set(borrador.marcas ?? []);
                      if (e.target.checked) set.add(m.id);
                      else set.delete(m.id);
                      onEditar({ marcas: [...set] });
                    }}
                    className="h-3.5 w-3.5 accent-foreground"
                  />
                  {m.nombre}
                </label>
              );
            })}
          </div>
        </fieldset>
      ) : null}
      <div className="space-y-1">
        <Label htmlFor="ficha-etiquetas" className="text-xs">
          Etiquetas
        </Label>
        <Input
          id="ficha-etiquetas"
          defaultValue={(borrador.etiquetas ?? []).join(", ")}
          onBlur={(e) =>
            onEditar({
              etiquetas: e.target.value
                .split(",")
                .map((t) => t.trim())
                .filter(Boolean),
            })
          }
          placeholder="ej. breaking, deportes"
          className="h-8 text-xs"
        />
      </div>
      {esEditorial ? (
        <div className="space-y-1">
          <Label htmlFor="ficha-prioridad" className="text-xs">
            Prioridad de ensamblaje (menor = antes)
          </Label>
          <Input
            id="ficha-prioridad"
            type="number"
            value={borrador.prioridad ?? 0}
            onChange={(e) => onEditar({ prioridad: Number(e.target.value) })}
            className="h-8 w-24 text-xs"
          />
        </div>
      ) : null}
    </div>
  );
}

export function DetalleDocumento({
  docId,
  maquina,
  onCerrar,
  onIdCambiado,
}: {
  docId: string;
  /** Riel de la máquina (para situar el doc en la pestaña "Uso"). */
  maquina?: RespuestaMaquinaTexto;
  onCerrar: () => void;
  /** El id puede cambiar al renombrar/mover: el contenedor actualiza la URL. */
  onIdCambiado: (id: string) => void;
}) {
  const qc = useQueryClient();
  const esAdmin = useEsAdmin();

  const docQuery = useQuery({
    queryKey: ["texto-doc", docId],
    queryFn: ({ signal }) => api.documento(docId, signal),
  });
  const doc = docQuery.data?.documento ?? null;

  // ── Borrador local con autosave (debounce 600ms), frontmatter oculto readjuntado. ──
  // `sincronizado` marca el id del doc YA cargado en el borrador: el refetch de la query
  // (invalidaciones, focus) NO pisa lo que se está tecleando; solo se resincroniza al
  // cambiar de documento o cuando se pide explícitamente (restaurar versión).
  const [borrador, setBorrador] = React.useState<DocumentoTexto | null>(null);
  const [frontmatterOculto, setFrontmatterOculto] = React.useState("");
  const sincronizado = React.useRef<string | null>(null);
  // ── Concurrencia optimista: `rev` (ETag) que cargamos / último confirmado. Se echa en cada
  // autosave; si otro editor guardó debajo el backend devuelve 409 y mostramos un aviso. Va en
  // refs (no estado) para que el timer con debounce lea siempre el último valor sin re-cerrar. ──
  const revRef = React.useRef<string | null>(null);
  const conflictoRef = React.useRef(false);
  const [conflicto, setConflicto] = React.useState(false);
  React.useEffect(() => {
    if (sincronizado.current !== docId) {
      sincronizado.current = null;
      setBorrador(null);
      setFrontmatterOculto("");
      revRef.current = null;
      conflictoRef.current = false;
      setConflicto(false);
    }
  }, [docId]);
  React.useEffect(() => {
    if (!doc || sincronizado.current === doc.id) return;
    sincronizado.current = doc.id;
    const { oculto, visible } = separarFrontmatter(doc.cuerpo);
    setBorrador({ ...doc, cuerpo: visible });
    setFrontmatterOculto(oculto);
    revRef.current = doc.rev ?? null;
    conflictoRef.current = false;
    setConflicto(false);
  }, [doc]);

  // Recarga el doc desde el servidor descartando el borrador local (tras un conflicto 409).
  const recargarDesdeServidor = React.useCallback(() => {
    sincronizado.current = null;
    revRef.current = null;
    conflictoRef.current = false;
    setConflicto(false);
    qc.invalidateQueries({ queryKey: ["texto-doc", docId] });
  }, [qc, docId]);

  const guardarTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const guardarMut = useMutation({
    mutationFn: ({ id, cuerpo }: { id: string; cuerpo: Partial<DocumentoTexto> }) =>
      api.guardarDocumento(id, cuerpo),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-maquina"] });
      qc.invalidateQueries({ queryKey: ["texto-historial", r.documento.id] });
      // Documentos editoriales: la Estrategia de marca refleja extractos y estado.
      if (r.documento.tipo !== "prompt") {
        qc.invalidateQueries({ queryKey: claveEstrategiaBase });
      }
      // Confirmado: este `rev` pasa a ser la base del siguiente autosave.
      revRef.current = r.documento.rev ?? null;
      if (r.documento.id !== docId) {
        // Renombrado/movido: el id cambia; resincroniza la URL y la caché del nuevo id.
        qc.setQueryData(["texto-doc", r.documento.id], r);
        onIdCambiado(r.documento.id);
      } else {
        // Refresca el estado de publicación (sin pisar el cuerpo en edición).
        qc.setQueryData(["texto-doc", docId], r);
      }
    },
    onError: (e) => {
      // 409 = otro editor guardó debajo (concurrencia optimista): avisa UNA vez y bloquea
      // el autosave hasta que la persona recargue, para no pisar el trabajo ajeno.
      if (e instanceof ApiError && e.status === 409) {
        if (!conflictoRef.current) {
          conflictoRef.current = true;
          setConflicto(true);
          toast.error("Alguien más editó este documento. Recarga para no pisar sus cambios.");
        }
        return;
      }
      toast.error(mensajeError(e));
    },
  });

  function editar(parcial: Partial<DocumentoTexto>) {
    if (!borrador) return;
    const siguiente = { ...borrador, ...parcial };
    setBorrador(siguiente);
    // En conflicto, no seguimos guardando (pisaría al otro editor): hay que recargar antes.
    if (conflictoRef.current) return;
    if (guardarTimer.current) clearTimeout(guardarTimer.current);
    guardarTimer.current = setTimeout(() => {
      guardarMut.mutate({
        id: borrador.id,
        cuerpo: {
          titulo: siguiente.titulo,
          descripcion: siguiente.descripcion ?? "",
          cuerpo: frontmatterOculto + siguiente.cuerpo,
          carpeta: siguiente.carpeta,
          clase: siguiente.clase,
          marcas: siguiente.marcas,
          estado: siguiente.estado,
          etiquetas: siguiente.etiquetas,
          pipelines: siguiente.pipelines,
          rol: siguiente.rol,
          prioridad: siguiente.prioridad,
          rev: revRef.current ?? undefined,
        },
      });
    }, 600);
  }

  // ── Eliminar (papelera) y menú ⋯ (estado + papelera). ──
  const eliminarMut = useMutation({
    mutationFn: (id: string) => api.eliminarDocumento(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-papelera"] });
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const menu = useMenuContextual();
  const botonMenuRef = React.useRef<HTMLButtonElement>(null);

  // ── Publicar / solicitar: diff producción ↔ copia de trabajo. ──
  const [publicarAbierto, setPublicarAbierto] = React.useState(false);
  const produccion = doc?.produccion ?? null;
  const antesQuery = useQuery({
    queryKey: ["texto-version", docId, produccion?.sha],
    queryFn: ({ signal }) => api.versionTexto(docId, produccion?.sha as string, signal),
    enabled: publicarAbierto && !!produccion?.sha,
  });

  // ── Probar (PanelLanzar) — solo prompts. ──
  const esPrompt = borrador?.tipo === "prompt";
  const [lanzarAbierto, setLanzarAbierto] = React.useState(false);
  const marcasQuery = useQuery({
    queryKey: ["texto-marcas"],
    queryFn: ({ signal }) => api.marcasTexto(signal),
  });
  const areasQuery = useQuery({
    queryKey: ["texto-areas"],
    queryFn: ({ signal }) => api.areasTexto(signal),
    enabled: esPrompt,
  });

  // ── Compilado: solo prompts BASE de un pipeline del registro. ──
  const pipelinesQuery = useQuery({
    queryKey: ["texto-pipelines"],
    queryFn: ({ signal }) => api.pipelinesTexto(signal),
    enabled: esPrompt,
    staleTime: 5 * 60_000,
  });
  const pipelineBase = React.useMemo(
    () => (pipelinesQuery.data?.pipelines ?? []).find((p) => p.prompt_base_id === doc?.id),
    [pipelinesQuery.data, doc?.id],
  );

  const [pestana, setPestana] = React.useState<PestanaPanel>("versiones");
  React.useEffect(() => {
    // Si desaparece la pestaña compilado (cambio de doc), vuelve a versiones.
    if (pestana === "compilado" && !pipelineBase) setPestana("versiones");
  }, [pestana, pipelineBase]);

  if (docQuery.isPending || !borrador) {
    return (
      <div className="space-y-3" data-testid="detalle-cargando">
        <Skeleton className="h-9 w-2/3" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  if (docQuery.isError) {
    return (
      <div className="space-y-3">
        <Button size="sm" variant="ghost" onClick={onCerrar}>
          <ArrowLeft className="mr-1 h-3.5 w-3.5" /> Volver
        </Button>
        <p className="text-sm text-muted-foreground">{mensajeError(docQuery.error)}</p>
      </div>
    );
  }

  const sinPublicar = !!doc?.sin_publicar;
  const procesos = borrador.procesos ?? [];
  const puedePublicar = !produccion || sinPublicar;

  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      {/* ───────── Cabecera de estado ───────── */}
      <div className="flex flex-wrap items-center gap-2">
        <Button size="icon" variant="ghost" className="h-8 w-8" onClick={onCerrar} aria-label="Volver a la biblioteca">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <Input
          value={borrador.titulo}
          onChange={(e) => editar({ titulo: e.target.value })}
          className="min-w-[12rem] flex-1 border-transparent text-base font-medium shadow-none hover:border-input focus-visible:border-input"
          placeholder="Título"
          aria-label="Título del documento"
        />
        {sinPublicar ? (
          <Badge variant="aviso" className="gap-1 rounded-full">
            <AlertTriangle className="h-3 w-3" aria-hidden /> Cambios sin publicar
          </Badge>
        ) : null}
        {esAdmin ? (
          <Button
            variant="brand"
            size="sm"
            disabled={!puedePublicar}
            title={puedePublicar ? "Publicar para que lo usen los agentes" : "No hay cambios sin publicar"}
            onClick={() => setPublicarAbierto(true)}
          >
            <Rocket className="mr-1 h-3.5 w-3.5" /> Publicar
          </Button>
        ) : (
          <Button
            variant="brand"
            size="sm"
            disabled={!puedePublicar}
            title={puedePublicar ? "Proponer estos cambios para publicar" : "No hay cambios sin publicar"}
            onClick={() => setPublicarAbierto(true)}
          >
            <Send className="mr-1 h-3.5 w-3.5" /> Solicitar publicación
          </Button>
        )}
        {esPrompt ? (
          <Button variant="outline" size="sm" onClick={() => setLanzarAbierto(true)}>
            <Send className="mr-1 h-3.5 w-3.5" /> Probar
          </Button>
        ) : null}
        <Button
          ref={botonMenuRef}
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          aria-label="Más acciones"
          onClick={(e) => menu.abrirEn(e, botonMenuRef.current)}
        >
          <MoreHorizontal className="h-4 w-4" />
        </Button>
        {menu.abierto && menu.pos ? (
          <MenuFlotante
            pos={menu.pos}
            onClose={menu.cerrar}
            etiqueta="Acciones del documento"
            items={[
              ...ESTADOS_DOC.map((s) => ({
                etiqueta: `Estado: ${s}`,
                activo: (borrador.estado || "activo") === s,
                onClick: () => editar({ estado: s }),
              })),
              { separador: true as const },
              {
                etiqueta: "Mover a la papelera",
                icono: Trash2,
                destructivo: true,
                onClick: () => {
                  void (async () => {
                    if (
                      await confirmar({
                        mensaje: "¿Mover este documento a la papelera?",
                        destructivo: true,
                        textoConfirmar: "Mover",
                      })
                    )
                      eliminarMut.mutate(borrador.id);
                  })();
                },
              },
            ]}
          />
        ) : null}
      </div>

      {/* Línea de deployment + nota de inyección. */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        {produccion ? (
          <span
            className="inline-flex items-center gap-1.5"
            title="Lo publicado es lo que ven los agentes en todas las generaciones."
          >
            <span className="text-emerald-600 dark:text-emerald-400" aria-hidden>●</span>
            Publicado (lo que ven los agentes) desde{" "}
            {tiempoRelativo(produccion.creado) || produccion.creado.slice(0, 10)}{" "}
            ({produccion.autor || "—"})
          </span>
        ) : (
          <span>Sin publicar aún — los agentes usan tu borrador.</span>
        )}
        {procesos.length > 0 ? (
          <span className="inline-flex items-center gap-1" title={procesos.join("\n")}>
            <Zap className="h-3 w-3 text-keni" aria-hidden />
            Inyectado en: {procesos.join(" · ")}
          </span>
        ) : null}
        <span className="ml-auto">
          {conflicto
            ? "Sin guardar — recarga"
            : guardarMut.isPending
              ? "Guardando borrador…"
              : `Borrador guardado ${tiempoRelativo(borrador.actualizado) || borrador.actualizado || ""}`.trim()}
        </span>
      </div>

      {/* Conflicto de edición (otro editor guardó debajo): el autosave queda en pausa. */}
      {conflicto ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>
            Alguien más editó este documento. Tus cambios dejaron de guardarse para no pisar los
            suyos.
          </span>
          <Button
            size="sm"
            variant="outline"
            className="ml-auto h-7"
            onClick={recargarDesdeServidor}
          >
            Recargar
          </Button>
        </div>
      ) : null}

      {/* ───────── Cuerpo + panel lateral ───────── */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
          <EditorWysiwyg
            key={borrador.id}
            value={borrador.cuerpo}
            onContenido={(md) => editar({ cuerpo: md })}
            conVariables
            placeholder={
              esPrompt
                ? "Escribe el prompt… ({{ para insertar una variable)"
                : "Escribe la pieza editorial (voz, reglas, plataforma…)…"
            }
          />
        </div>

        <aside className="flex w-full shrink-0 flex-col gap-2 lg:w-96">
          <Tabs value={pestana} onValueChange={(v) => setPestana(v as PestanaPanel)}>
            <TabsList className={`grid w-full ${pipelineBase ? "grid-cols-4" : "grid-cols-3"}`}>
              <TabsTrigger value="versiones">Versiones</TabsTrigger>
              <TabsTrigger value="uso">Uso</TabsTrigger>
              {pipelineBase ? <TabsTrigger value="compilado">Compilado</TabsTrigger> : null}
              <TabsTrigger value="ficha">Ficha</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
            {pestana === "versiones" ? (
              <PanelVersiones
                docId={borrador.id}
                produccionSha={produccion?.sha ?? null}
                cuerpoBorrador={frontmatterOculto + borrador.cuerpo}
                sinPublicar={sinPublicar}
                onPublicar={() => setPublicarAbierto(true)}
                onBorradorActualizado={() => {
                  // Fuerza la RE-SINCRONIZACIÓN del borrador con el cuerpo cargado.
                  sincronizado.current = null;
                  qc.invalidateQueries({ queryKey: ["texto-doc", docId] });
                  qc.invalidateQueries({ queryKey: ["texto-maquina"] });
                  if (borrador.tipo !== "prompt") {
                    qc.invalidateQueries({ queryKey: claveEstrategiaBase });
                  }
                }}
              />
            ) : pestana === "uso" ? (
              <PanelUso doc={borrador} maquina={maquina} />
            ) : pestana === "compilado" && pipelineBase ? (
              <PanelCompilado pipelineId={pipelineBase.id} />
            ) : (
              <PanelFicha
                borrador={borrador}
                marcas={marcasQuery.data?.marcas ?? []}
                onEditar={editar}
              />
            )}
          </div>
        </aside>
      </div>

      {/* ───────── Publicar / solicitar ───────── */}
      <DialogPublicar
        docId={borrador.id}
        abierto={publicarAbierto}
        onCerrar={() => setPublicarAbierto(false)}
        esAdmin={esAdmin}
        antes={produccion ? antesQuery.data?.documento.cuerpo ?? "" : ""}
        despues={frontmatterOculto + borrador.cuerpo}
        onHecho={() => {
          qc.invalidateQueries({ queryKey: ["texto-doc", docId] });
          qc.invalidateQueries({ queryKey: ["texto-maquina"] });
          if (borrador.tipo !== "prompt") {
            qc.invalidateQueries({ queryKey: claveEstrategiaBase });
          }
        }}
      />

      {/* ───────── Probar (panel lanzar, solo prompts) ───────── */}
      {esPrompt ? (
        <PanelLanzar
          key={borrador.id}
          promptId={borrador.id}
          salida={borrador.salida ?? ""}
          marcas={marcasQuery.data?.marcas ?? []}
          areas={areasQuery.data?.areas ?? []}
          open={lanzarAbierto}
          onOpenChange={setLanzarAbierto}
        />
      ) : null}
    </div>
  );
}
