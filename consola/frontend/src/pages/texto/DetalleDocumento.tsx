/**
 * Vista DETALLE de un documento de la Biblioteca de Prompts.
 *
 * Cabecera (título editable + acciones), cuerpo SIEMPRE WYSIWYG (EditorWysiwyg con chips
 * de variables; la edición es libre: producción no cambia hasta publicar), y panel lateral
 * COLAPSABLE (estado en localStorage; colapsado el editor ocupa todo el ancho) con pestañas:
 *   - Versiones (PanelVersiones: publicado ↔ tu borrador, diff ancho, traer/descartar),
 *   - Acerca de (PanelAcerca: en prosa, qué es el doc y dónde entra en el pipeline),
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Lock,
  MoreHorizontal,
  PanelLeftClose,
  PanelLeftOpen,
  Rocket,
  Send,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { PanelAcerca } from "@/components/biblioteca/PanelAcerca";
import { DialogPublicar } from "@/components/biblioteca/DialogPublicar";
import { PanelVersiones } from "@/components/biblioteca/PanelVersiones";
import { confirmar } from "@/components/comunes/confirmar";
import { MenuFlotante } from "@/components/comunes/MenuContextual";
import { EditorWysiwyg } from "@/components/editor/EditorWysiwyg";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMenuContextual } from "@/hooks/use-menu-contextual";
import { useEsAdmin } from "@/hooks/use-biblioteca";
import { ApiError, api, mensajeError } from "@/lib/api";
import type { DocumentoTexto, RespuestaMaquinaTexto } from "@/types";

import { claveEstrategiaBase } from "./estrategia/api";
import {
  componerCuerpoTexto,
  PLACEHOLDER_CONTRATO,
  quitarContratoSalida,
  separarFrontmatter,
} from "./lib";

/** Clave de persistencia del estado abierto/colapsado del panel lateral. */
const CLAVE_PANEL = "keni.biblioteca.panel-abierto";

type PestanaPanel = "versiones" | "acerca";

export function DetalleDocumento({
  docId,
  maquina,
  onCerrar,
  onIdCambiado,
}: {
  docId: string;
  /** Línea de la máquina (para situar el doc en la pestaña "Uso"). */
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
  // `true` si el cuerpo cargado llevaba el placeholder `{{CONTRATO_SALIDA}}` (prompts cuyo
  // contrato se inyecta por placeholder). Decide si se readjunta al guardar: parrilla tiene
  // `contrato_salida` (para el bloque read-only) pero NO usa el placeholder, así que NO se readjunta.
  const [contratoInline, setContratoInline] = React.useState(false);
  const sincronizado = React.useRef<string | null>(null);
  // ── Concurrencia optimista: `rev` (ETag) que cargamos / último confirmado. Se echa en cada
  // autosave; si otro editor guardó debajo el backend devuelve 409 y mostramos un aviso. Va en
  // refs (no estado) para que el timer con debounce lea siempre el último valor sin re-cerrar. ──
  const revRef = React.useRef<string | null>(null);
  const conflictoRef = React.useRef(false);
  const [conflicto, setConflicto] = React.useState(false);
  // Resolver del conflicto "sobrescribir con lo mío" (re-fetch del rev + reintento): deshabilita
  // los botones mientras corre para no disparar guardados en paralelo.
  const [resolviendoConflicto, setResolviendoConflicto] = React.useState(false);
  // Anti auto-conflicto: NO lanzamos un autosave nuevo mientras hay uno en curso (mandaría un
  // `rev` viejo y chocaríamos contra nosotros mismos). `guardandoRef` marca el guardado activo; `pendienteRef`
  // encola el último estado tecleado para guardarlo al volver. `borradorRef` espeja el borrador para
  // que la resolución del conflicto guarde SIEMPRE lo último tecleado.
  const guardandoRef = React.useRef(false);
  const pendienteRef = React.useRef<DocumentoTexto | null>(null);
  const borradorRef = React.useRef<DocumentoTexto | null>(null);
  React.useEffect(() => {
    borradorRef.current = borrador;
  }, [borrador]);
  React.useEffect(() => {
    if (sincronizado.current !== docId) {
      sincronizado.current = null;
      setBorrador(null);
      setFrontmatterOculto("");
      setContratoInline(false);
      revRef.current = null;
      conflictoRef.current = false;
      setConflicto(false);
      guardandoRef.current = false;
      pendienteRef.current = null;
    }
  }, [docId]);
  React.useEffect(() => {
    if (!doc || sincronizado.current === doc.id) return;
    sincronizado.current = doc.id;
    const { oculto, visible } = separarFrontmatter(doc.cuerpo);
    // El contrato de salida (prompts estructurados) no se edita: se oculta su placeholder del
    // editor y se pinta read-only aparte. Se readjunta al guardar (`construirPayload`).
    setBorrador({ ...doc, cuerpo: quitarContratoSalida(visible) });
    setFrontmatterOculto(oculto);
    setContratoInline(visible.includes(PLACEHOLDER_CONTRATO));
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
    guardandoRef.current = false;
    pendienteRef.current = null;
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
      // Sincroniza la marca de tiempo del guardado SIN pisar el cuerpo/título en edición,
      // para que la etiqueta "Borrador guardado hace X" avance de verdad.
      setBorrador((b) => (b ? { ...b, actualizado: r.documento.actualizado } : b));
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
      // 409 = otro editor guardó debajo (concurrencia optimista): avisa UNA vez y pausa el
      // autosave, PERO conserva el borrador local. La persona decide en el banner si sobrescribe
      // con lo suyo o descarta y recarga; nada se pierde sin que lo elija.
      if (e instanceof ApiError && e.status === 409) {
        pendienteRef.current = null;
        if (!conflictoRef.current) {
          conflictoRef.current = true;
          setConflicto(true);
          toast.error("Alguien más editó este documento. Elige si sobrescribes o recargas.");
        }
        return;
      }
      toast.error(mensajeError(e));
    },
    onSettled: () => {
      // Fin del vuelo: si quedó un estado encolado (se tecleó mientras guardábamos), lánzalo
      // ahora con el `rev` ya confirmado. En conflicto no reanudamos: lo decide la persona.
      guardandoRef.current = false;
      const pendiente = pendienteRef.current;
      pendienteRef.current = null;
      if (pendiente && !conflictoRef.current) solicitarGuardado(pendiente);
    },
  });

  // Construye el payload de guardado leyendo el `rev` vigente en el momento del envío.
  function construirPayload(b: DocumentoTexto): { id: string; cuerpo: Partial<DocumentoTexto> } {
    return {
      id: b.id,
      cuerpo: {
        titulo: b.titulo,
        descripcion: b.descripcion ?? "",
        cuerpo: componerCuerpoTexto(frontmatterOculto, b.cuerpo, contratoInline),
        carpeta: b.carpeta,
        clase: b.clase,
        marcas: b.marcas,
        etiquetas: b.etiquetas,
        pipelines: b.pipelines,
        rol: b.rol,
        prioridad: b.prioridad,
        rev: revRef.current ?? undefined,
      },
    };
  }

  // Guardado de un solo vuelo: si ya hay uno en curso, encola el último estado en vez de
  // disparar otro con un `rev` viejo (que provocaría un 409 contra uno mismo).
  function solicitarGuardado(b: DocumentoTexto) {
    if (conflictoRef.current) return;
    if (guardandoRef.current) {
      pendienteRef.current = b;
      return;
    }
    guardandoRef.current = true;
    guardarMut.mutate(construirPayload(b));
  }

  function editar(parcial: Partial<DocumentoTexto>) {
    if (!borrador) return;
    const siguiente = { ...borrador, ...parcial };
    setBorrador(siguiente);
    // En conflicto, no seguimos guardando (pisaría al otro editor): la persona decide en el banner.
    // El borrador local sí se conserva, así que lo tecleado no se pierde.
    if (conflictoRef.current) return;
    if (guardarTimer.current) clearTimeout(guardarTimer.current);
    guardarTimer.current = setTimeout(() => solicitarGuardado(siguiente), 600);
  }

  // "Sobrescribir con lo mío": re-fetch del `rev` actual del servidor y reintenta el guardado del
  // borrador local con ese rev (last-write-wins explícito y consciente; nada se descarta).
  async function sobrescribirConLoMio() {
    const local = borradorRef.current;
    if (!local || resolviendoConflicto) return;
    setResolviendoConflicto(true);
    try {
      const actual = await api.documento(docId);
      revRef.current = actual.documento.rev ?? null;
      conflictoRef.current = false;
      setConflicto(false);
      guardandoRef.current = false;
      pendienteRef.current = null;
      solicitarGuardado(local);
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setResolviendoConflicto(false);
    }
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

  const esPrompt = borrador?.tipo === "prompt";

  // ── Panel lateral colapsable: con el panel oculto el editor ocupa todo el ancho
  // (legibilidad). El estado se recuerda entre sesiones en localStorage. ──
  const [panelAbierto, setPanelAbierto] = React.useState(() => {
    try {
      return localStorage.getItem(CLAVE_PANEL) !== "false";
    } catch {
      return true;
    }
  });
  React.useEffect(() => {
    try {
      localStorage.setItem(CLAVE_PANEL, String(panelAbierto));
    } catch {
      /* almacenamiento no disponible: el estado vive solo en memoria */
    }
  }, [panelAbierto]);

  const [pestana, setPestana] = React.useState<PestanaPanel>("versiones");

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
  const cuerpoVacio = !(borrador.cuerpo ?? "").trim();
  const puedePublicar = (!produccion || sinPublicar) && !cuerpoVacio;

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
            title={
              puedePublicar
                ? "Publicar para que lo usen los agentes"
                : cuerpoVacio
                  ? "El cuerpo está vacío"
                  : "No hay cambios sin publicar"
            }
            onClick={() => setPublicarAbierto(true)}
          >
            <Rocket className="mr-1 h-3.5 w-3.5" /> Publicar
          </Button>
        ) : (
          <Button
            variant="brand"
            size="sm"
            disabled={!puedePublicar}
            title={
              puedePublicar
                ? "Proponer estos cambios para publicar"
                : cuerpoVacio
                  ? "El cuerpo está vacío"
                  : "No hay cambios sin publicar"
            }
            onClick={() => setPublicarAbierto(true)}
          >
            <Send className="mr-1 h-3.5 w-3.5" /> Solicitar publicación
          </Button>
        )}
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

      {/* Conflicto de edición (otro editor guardó debajo): el autosave queda en pausa, pero tu
          borrador local sigue intacto. Decides tú: sobrescribir con lo tuyo o descartar y recargar. */}
      {conflicto ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-[12rem] flex-1">
            Alguien más editó este documento. Tus cambios siguen aquí sin guardarse. Elige cómo
            resolver:
          </span>
          <Button
            size="sm"
            variant="brand"
            className="h-7"
            disabled={resolviendoConflicto}
            onClick={() => void sobrescribirConLoMio()}
            title="Vuelve a leer la versión del servidor y guarda lo tuyo encima"
          >
            {resolviendoConflicto ? "Guardando…" : "Sobrescribir con lo mío"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7"
            disabled={resolviendoConflicto}
            onClick={recargarDesdeServidor}
            title="Descarta lo que escribiste y carga la versión de los demás"
          >
            Descartar lo mío y recargar
          </Button>
        </div>
      ) : null}

      {/* ───────── Panel lateral (izquierda, colapsable) + cuerpo (derecha) ───────── */}
      <div className="flex min-h-0 flex-1 flex-col gap-3 lg:flex-row">
        {panelAbierto ? (
          <aside className="flex w-full shrink-0 flex-col gap-2 lg:w-96">
            <div className="flex items-center gap-1">
              <Tabs
                value={pestana}
                onValueChange={(v) => setPestana(v as PestanaPanel)}
                className="min-w-0 flex-1"
              >
                <TabsList className="grid h-auto w-full grid-cols-2 gap-1 p-1">
                  <TabsTrigger value="versiones" className="text-xs">
                    Versiones
                  </TabsTrigger>
                  <TabsTrigger value="acerca" className="text-xs">
                    Acerca de
                  </TabsTrigger>
                </TabsList>
              </Tabs>
              {/* Colapsar va A LA PAR de las pestañas que oculta. */}
              <Button
                size="icon"
                variant="ghost"
                className="h-8 w-8 shrink-0"
                aria-label="Colapsar panel lateral"
                title="Colapsar panel"
                onClick={() => setPanelAbierto(false)}
              >
                <PanelLeftClose className="h-4 w-4" />
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-muted/20 p-3">
              {pestana === "versiones" ? (
                <PanelVersiones
                  docId={borrador.id}
                  produccionSha={produccion?.sha ?? null}
                  sinPublicar={sinPublicar}
                  cuerpoBorrador={componerCuerpoTexto(
                    frontmatterOculto,
                    borrador.cuerpo,
                    contratoInline,
                  )}
                  esAdmin={esAdmin}
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
              ) : (
                <PanelAcerca doc={borrador} maquina={maquina} />
              )}
            </div>
          </aside>
        ) : (
          // Panel colapsado: botón pequeño para reabrirlo (el editor ocupa el resto del ancho).
          <Button
            size="icon"
            variant="outline"
            className="h-8 w-8 shrink-0 self-start"
            aria-label="Abrir panel lateral"
            title="Abrir panel"
            onClick={() => setPanelAbierto(true)}
          >
            <PanelLeftOpen className="h-4 w-4" />
          </Button>
        )}

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
          {/* Contrato de salida (prompts estructurados): NO editable, lo gestiona el sistema.
              Va siempre al FINAL del prompt que ve el modelo. */}
          {borrador.contrato_salida ? (
            <div className="mt-4 rounded-md border border-dashed border-border bg-muted/30 p-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Lock className="h-3 w-3" aria-hidden />
                Salida · formato fijo (lo gestiona el sistema, no editable)
              </div>
              <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-foreground/80">
                {borrador.contrato_salida}
              </pre>
            </div>
          ) : null}
        </div>
      </div>

      {/* ───────── Publicar / solicitar ───────── */}
      <DialogPublicar
        docId={borrador.id}
        abierto={publicarAbierto}
        onCerrar={() => setPublicarAbierto(false)}
        esAdmin={esAdmin}
        antes={produccion ? antesQuery.data?.documento.cuerpo ?? "" : ""}
        despues={componerCuerpoTexto(frontmatterOculto, borrador.cuerpo, contratoInline)}
        onHecho={() => {
          qc.invalidateQueries({ queryKey: ["texto-doc", docId] });
          qc.invalidateQueries({ queryKey: ["texto-maquina"] });
          if (borrador.tipo !== "prompt") {
            qc.invalidateQueries({ queryKey: claveEstrategiaBase });
          }
        }}
      />
    </div>
  );
}
