/**
 * Texto: almacén único de PROMPTS + LÍNEA EDITORIAL con editor markdown a pantalla
 * completa (toggle editar/vista) y un panel para LANZAR un prompt sobre un target
 * (contenido pegado / URL / sección de la Consola / archivo), adjuntando la línea editorial
 * de la marca. El resultado llega por streaming (sondeo de la generación).
 *
 * Reemplaza la antigua página de generación por formulario: aquí el contenido es markdown
 * libre, no un formulario rígido. Reutiliza el editor (AutoTextarea + BarraFormato + Markdown), el
 * selector de marca y el hook de generación existentes.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  History,
  Loader2,
  Plus,
  RotateCcw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";

import { confirmar } from "@/components/comunes/confirmar";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { SelectorRedMultiple } from "@/components/comunes/SelectorRedMultiple";
import { EditorWysiwyg } from "@/components/editor/EditorWysiwyg";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Markdown } from "@/components/ui/Markdown";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { MENSAJE_MARCA_REQUERIDA, useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import type { DocumentoTexto, TargetLanzamiento } from "@/types";

type TipoTarget = TargetLanzamiento["tipo"] | "archivo";

const ESTADOS_DOC = ["activo", "borrador", "archivado"] as const;

/**
 * Separa un bloque de "frontmatter" al INICIO del cuerpo (un bloque `---\n…\n---`) del
 * resto del texto. El store ya quita el frontmatter real; pero algunos documentos llevan
 * ADEMÁS un bloque de metadatos al principio del cuerpo, que no aporta nada al editor.
 * Lo separamos para EDITARLO oculto y readjuntarlo al guardar (no se pierde del fichero).
 * Guarda: solo separa si el bloque PARECE metadatos (líneas `clave: valor` o comentarios `#`),
 * para no tragarse un separador `---` legítimo de prosa.
 */
function separarFrontmatter(cuerpo: string): { oculto: string; visible: string } {
  const m = /^---\r?\n([\s\S]*?)\r?\n---[ \t]*\r?\n[ \t\r\n]*/.exec(cuerpo);
  if (!m || m.index !== 0) return { oculto: "", visible: cuerpo };
  const lineas = m[1].split(/\r?\n/).filter((l) => l.trim());
  const pareceMeta = lineas.length > 0 && lineas.every((l) => /^\s*(#|[\w.-]+\s*:)/.test(l));
  if (!pareceMeta) return { oculto: "", visible: cuerpo };
  return { oculto: m[0], visible: cuerpo.slice(m[0].length) };
}

export default function Texto() {
  const qc = useQueryClient();
  // Marca activa del workspace: default del filtro (con "Todas" disponible: la
  // texto es editorial y consultar otras marcas es legítimo).
  const { marcaActiva } = useMarcaActiva();

  // --- Navegación / lista ---
  // La Texto es CONTEXTO: una sola lista de documentos (sin distinguir prompt/editorial
  // en la navegación). El filtro por marca lo manda el selector GLOBAL del workspace
  // (`marcaActiva`); aquí no hay filtro de marca propio.
  const [q, setQ] = React.useState("");
  const [enPapelera, setEnPapelera] = React.useState(false);
  const [seleccionId, setSeleccionId] = React.useState<string | null>(null);
  // Config avanzada (estado, etiquetas, clase/marcas, atribución) plegada tras el engranaje.
  const [historialAbierto, setHistorialAbierto] = React.useState(false);
  const [carpetasCerradas, setCarpetasCerradas] = React.useState<Set<string>>(new Set());
  const [lanzarAbierto, setLanzarAbierto] = React.useState(false);
  // Frontmatter del cuerpo que ocultamos en el editor (se readjunta al guardar).
  const [frontmatterOculto, setFrontmatterOculto] = React.useState("");
  // Arrastrar y soltar para mover documentos entre carpetas.
  const [arrastrando, setArrastrando] = React.useState<string | null>(null);
  const [destino, setDestino] = React.useState<string | null>(null);
  // Renombrar en sitio (doble clic sobre el nombre, como en un explorador de archivos).
  const [renombrando, setRenombrando] = React.useState<{ tipo: "doc" | "carpeta"; clave: string } | null>(
    null,
  );
  const [valorRen, setValorRen] = React.useState("");
  const enRenRef = React.useRef(false);

  // Documentos de la marca activa global (sin "Todas" -> sin filtro de marca). La búsqueda y
  // la jerarquía de carpetas son la única navegación.
  const docsQuery = useQuery({
    queryKey: ["texto", q, marcaActiva],
    queryFn: ({ signal }) =>
      api.texto({ q: q || undefined, marca: marcaActiva ?? undefined }, signal),
  });
  const papeleraQuery = useQuery({
    queryKey: ["texto-papelera"],
    queryFn: ({ signal }) => api.papeleraTexto(signal),
    enabled: enPapelera,
  });
  const marcasQuery = useQuery({
    queryKey: ["texto-marcas"],
    queryFn: ({ signal }) => api.marcasTexto(signal),
  });
  const areasQuery = useQuery({
    queryKey: ["texto-areas"],
    queryFn: ({ signal }) => api.areasTexto(signal),
  });

  const documentos = React.useMemo(() => docsQuery.data?.documentos ?? [], [docsQuery.data]);
  const buscando = q.trim().length > 0;

  // Agrupa por carpeta: la jerarquía ES la navegación. Raíz ("") primero, resto alfabético.
  const grupos = React.useMemo(() => {
    const m = new Map<string, DocumentoTexto[]>();
    for (const d of documentos) {
      const k = d.carpeta || "";
      const arr = m.get(k);
      if (arr) arr.push(d);
      else m.set(k, [d]);
    }
    return [...m.entries()].sort(([a], [b]) =>
      a === "" ? -1 : b === "" ? 1 : a.localeCompare(b, "es"),
    );
  }, [documentos]);

  // Carpetas existentes para el autocompletado del editor (mover un doc a una carpeta).
  function alternarCarpeta(c: string) {
    setCarpetasCerradas((prev) => {
      const s = new Set(prev);
      if (s.has(c)) s.delete(c);
      else s.add(c);
      return s;
    });
  }

  function filaDoc(d: DocumentoTexto, mostrarCarpeta: boolean) {
    // Todo es contexto: un solo icono, sin distinguir prompt/editorial en la navegación.
    const icono = <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
    const renom = renombrando?.tipo === "doc" && renombrando.clave === d.id;
    return (
      <li key={d.id}>
        {renom ? (
          <div className="flex w-full items-center gap-2 px-3 py-2">
            {icono}
            {inputRenombre(() => confirmarRenDoc(d.id))}
          </div>
        ) : (
          <button
            onClick={() => setSeleccionId(d.id)}
            onDoubleClick={() => iniciarRen("doc", d.id, d.titulo)}
            title={`${d.titulo} — doble clic para renombrar`}
            draggable
            onDragStart={(e) => {
              setArrastrando(d.id);
              e.dataTransfer.effectAllowed = "move";
            }}
            onDragEnd={() => {
              setArrastrando(null);
              setDestino(null);
            }}
            className={`flex w-full items-start gap-2 px-3 py-2 text-left text-sm hover:bg-muted ${
              d.id === seleccionId ? "bg-muted font-medium" : ""
            } ${arrastrando === d.id ? "opacity-50" : ""}`}
          >
            {icono}
            <span className="min-w-0 flex-1">
              <span className="line-clamp-2 block break-words leading-snug">{d.titulo}</span>
              {mostrarCarpeta && d.carpeta ? (
                <span className="mt-0.5 block truncate text-xs text-muted-foreground">{d.carpeta}</span>
              ) : null}
            </span>
          </button>
        )}
      </li>
    );
  }
  const seleccion = documentos.find((d) => d.id === seleccionId) ?? null;

  // --- Borrador del editor (copia de trabajo, sincronizada al cambiar de documento) ---
  const [borrador, setBorrador] = React.useState<DocumentoTexto | null>(null);
  React.useEffect(() => {
    if (seleccion) {
      // Oculta el bloque de frontmatter del cuerpo al editar; se readjunta al guardar.
      const { oculto, visible } = separarFrontmatter(seleccion.cuerpo);
      setBorrador({ ...seleccion, cuerpo: visible });
      setFrontmatterOculto(oculto);
    } else {
      setBorrador(null);
      setFrontmatterOculto("");
    }
    setLanzarAbierto(false);
    setHistorialAbierto(false);
  }, [seleccionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const guardarTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const guardarMut = useMutation({
    mutationFn: ({ id, cuerpo }: { id: string; cuerpo: Partial<DocumentoTexto> }) =>
      api.guardarDocumento(id, cuerpo),
    onSuccess: (r) => {
      // El id puede cambiar (renombrado/carpeta): re-sincroniza la selección.
      if (r.documento.id !== seleccionId) setSeleccionId(r.documento.id);
      qc.invalidateQueries({ queryKey: ["texto"] });
    },
  });

  // Mover un documento a otra carpeta (cambia su carpeta; el id cambia, lo resincronizamos).
  const moverMut = useMutation({
    mutationFn: ({ id, carpeta }: { id: string; carpeta: string }) =>
      api.guardarDocumento(id, { carpeta }),
    onSuccess: (r, vars) => {
      if (vars.id === seleccionId) setSeleccionId(r.documento.id);
      qc.invalidateQueries({ queryKey: ["texto"] });
    },
  });
  function moverDoc(id: string, carpeta: string) {
    const d = documentos.find((x) => x.id === id);
    if (!d || (d.carpeta || "") === carpeta) return;
    moverMut.mutate({ id, carpeta });
  }

  // Renombrar una carpeta = re-filar todos sus documentos (y los anidados) a la nueva ruta.
  const renombrarCarpetaMut = useMutation({
    mutationFn: async ({ de, a }: { de: string; a: string }) => {
      const afectados = documentos.filter((d) => d.carpeta === de || d.carpeta.startsWith(de + "/"));
      for (const d of afectados) {
        await api.guardarDocumento(d.id, { carpeta: a + d.carpeta.slice(de.length) });
      }
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["texto"] }),
  });
  // --- Renombrar en sitio (doble clic) ---
  function iniciarRen(tipo: "doc" | "carpeta", clave: string, valor: string) {
    enRenRef.current = true;
    setRenombrando({ tipo, clave });
    setValorRen(valor);
  }
  // Cierra el modo renombrar UNA sola vez (Enter/blur confirman; Escape cancela). El ref
  // evita el doble disparo (Enter dispara mutate y el blur subsiguiente lo repetiría).
  function terminarRen(commit: boolean, onConfirmar: () => void) {
    if (!enRenRef.current) return;
    enRenRef.current = false;
    setRenombrando(null);
    if (commit) onConfirmar();
  }
  function confirmarRenDoc(id: string) {
    const t = valorRen.trim();
    if (t) guardarMut.mutate({ id, cuerpo: { titulo: t } });
  }
  function confirmarRenCarpeta(de: string) {
    const a = valorRen.trim();
    if (a && a !== de) {
      setSeleccionId(null); // los ids cambian; evita una selección colgada
      renombrarCarpetaMut.mutate({ de, a });
    }
  }
  function inputRenombre(onConfirmar: () => void) {
    return (
      <input
        autoFocus
        value={valorRen}
        onChange={(e) => setValorRen(e.target.value)}
        onClick={(e) => e.stopPropagation()}
        onDoubleClick={(e) => e.stopPropagation()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            terminarRen(true, onConfirmar);
          } else if (e.key === "Escape") {
            e.preventDefault();
            terminarRen(false, onConfirmar);
          }
        }}
        onBlur={() => terminarRen(true, onConfirmar)}
        className="w-full rounded border border-input bg-background px-1 py-0.5 text-sm"
      />
    );
  }

  function editar(parcial: Partial<DocumentoTexto>) {
    if (!borrador) return;
    const siguiente = { ...borrador, ...parcial };
    setBorrador(siguiente);
    if (guardarTimer.current) clearTimeout(guardarTimer.current);
    guardarTimer.current = setTimeout(() => {
      guardarMut.mutate({
        id: borrador.id,
        cuerpo: {
          titulo: siguiente.titulo,
          // Readjunta el frontmatter oculto para no perderlo del fichero.
          cuerpo: frontmatterOculto + siguiente.cuerpo,
          carpeta: siguiente.carpeta,
          clase: siguiente.clase,
          marcas: siguiente.marcas,
          estado: siguiente.estado,
          etiquetas: siguiente.etiquetas,
          pipelines: siguiente.pipelines,
          rol: siguiente.rol,
          prioridad: siguiente.prioridad,
        },
      });
    }, 600);
  }

  const crearMut = useMutation({
    mutationFn: (tipo: "prompt" | "editorial") =>
      api.crearDocumento({ titulo: tipo === "prompt" ? "Nuevo prompt" : "Nuevo editorial", tipo }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      setSeleccionId(r.documento.id);
    },
  });
  const eliminarMut = useMutation({
    mutationFn: (id: string) => api.eliminarDocumento(id),
    onSuccess: () => {
      if (seleccionId) setSeleccionId(null);
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-papelera"] });
    },
  });
  const restaurarMut = useMutation({
    mutationFn: (id: string) => api.restaurarDocumento(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      qc.invalidateQueries({ queryKey: ["texto-papelera"] });
    },
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 md:flex-row">
      {/* ───────── Sidebar ───────── */}
      {/* En móvil el explorador se apila arriba (ancho completo) con su lista
          acotada; en escritorio es una columna fija a la izquierda. */}
      <aside className="flex w-full shrink-0 flex-col gap-3 md:w-64">
        <Input placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button size="sm" variant="outline" onClick={() => crearMut.mutate("editorial")}>
          <Plus className="mr-1 h-3.5 w-3.5" /> Nuevo documento
        </Button>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border max-md:max-h-[45vh]">
          {docsQuery.isPending ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : documentos.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">
              {buscando ? "Sin resultados." : "No hay documentos. Crea uno arriba."}
            </p>
          ) : buscando ? (
            // Buscando: lista plana (resultados de todas las carpetas), con la carpeta como pista.
            <ul className="divide-y divide-border">{documentos.map((d) => filaDoc(d, true))}</ul>
          ) : (
            // Navegación por carpetas: raíz suelta arriba, luego cada carpeta plegable.
            // Arrastra un documento sobre una carpeta para moverlo; el lápiz la renombra.
            <div className="divide-y divide-border">
              {arrastrando ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDestino("");
                  }}
                  onDragLeave={() => setDestino((d) => (d === "" ? null : d))}
                  onDrop={() => {
                    moverDoc(arrastrando, "");
                    setDestino(null);
                  }}
                  className={`border-b border-dashed border-border px-3 py-1.5 text-center text-xs text-muted-foreground ${
                    destino === "" ? "ring-2 ring-inset ring-primary" : ""
                  }`}
                >
                  Soltar aquí para quitar de la carpeta
                </div>
              ) : null}
              {grupos.map(([carpeta, docs]) =>
                carpeta === "" ? (
                  <ul key="__raiz__" className="divide-y divide-border">
                    {docs.map((d) => filaDoc(d, false))}
                  </ul>
                ) : (
                  <div key={carpeta}>
                    <div
                      onDragOver={(e) => {
                        if (arrastrando) {
                          e.preventDefault();
                          setDestino(carpeta);
                        }
                      }}
                      onDragLeave={() => setDestino((d) => (d === carpeta ? null : d))}
                      onDrop={() => {
                        if (arrastrando) moverDoc(arrastrando, carpeta);
                        setDestino(null);
                      }}
                      className={`flex items-center gap-1.5 bg-muted/40 px-2 py-1.5 text-xs font-medium text-muted-foreground ${
                        destino === carpeta ? "ring-2 ring-inset ring-primary" : ""
                      }`}
                    >
                      {renombrando?.tipo === "carpeta" && renombrando.clave === carpeta ? (
                        <div className="flex min-w-0 flex-1 items-center gap-1.5">
                          <Folder className="h-3.5 w-3.5 shrink-0" />
                          {inputRenombre(() => confirmarRenCarpeta(carpeta))}
                        </div>
                      ) : (
                        <button
                          onClick={() => alternarCarpeta(carpeta)}
                          onDoubleClick={() => iniciarRen("carpeta", carpeta, carpeta)}
                          title="Doble clic para renombrar la carpeta"
                          className="flex min-w-0 flex-1 items-center gap-1.5 text-left hover:text-foreground"
                        >
                          {carpetasCerradas.has(carpeta) ? (
                            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                          ) : (
                            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                          )}
                          <Folder className="h-3.5 w-3.5 shrink-0" />
                          <span className="truncate">{carpeta}</span>
                        </button>
                      )}
                      <span className="shrink-0 tabular-nums">{docs.length}</span>
                    </div>
                    {!carpetasCerradas.has(carpeta) ? (
                      <ul className="divide-y divide-border">
                        {docs.map((d) => filaDoc(d, false))}
                      </ul>
                    ) : null}
                  </div>
                ),
              )}
            </div>
          )}
        </div>

        <Button size="sm" variant="ghost" onClick={() => setEnPapelera((v) => !v)}>
          <Trash2 className="mr-1 h-3.5 w-3.5" /> Papelera
        </Button>
        {enPapelera ? (
          <div className="max-h-40 overflow-y-auto rounded-md border border-border p-2 text-sm">
            {(papeleraQuery.data?.papelera ?? []).length === 0 ? (
              <p className="text-muted-foreground">Vacía.</p>
            ) : (
              papeleraQuery.data?.papelera.map((p) => (
                <div key={p.id} className="flex items-center gap-2 py-1">
                  <span className="truncate">{p.titulo}</span>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="ml-auto h-6 w-6"
                    onClick={() => restaurarMut.mutate(p.id)}
                    aria-label="Restaurar"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))
            )}
          </div>
        ) : null}
      </aside>

      {/* ───────── Editor ───────── */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
        {!borrador ? (
          <div className="flex flex-1 items-center justify-center text-center text-muted-foreground">
            <div>
              <p className="text-lg font-medium">Texto de prompts y línea editorial</p>
              <p className="text-sm">Selecciona un documento o crea uno nuevo.</p>
            </div>
          </div>
        ) : (
          <>
            {/* Barra mínima: título + estado + Lanzar (prompt) + historial + borrar. La marca y
                la organización salen de la CARPETA (explorador del lateral); no hay metadatos. */}
            <div className="flex flex-wrap items-center gap-2">
              <Input
                value={borrador.titulo}
                onChange={(e) => editar({ titulo: e.target.value })}
                className="min-w-[12rem] flex-1 text-base font-medium"
                placeholder="Título"
              />
              <Select value={borrador.estado || "activo"} onValueChange={(v) => editar({ estado: v })}>
                <SelectTrigger className="h-8 w-28 text-xs" title="Estado"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {ESTADOS_DOC.map((s) => (
                    <SelectItem key={s} value={s}>{s}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {borrador.tipo === "prompt" ? (
                <Button variant="brand" size="sm" onClick={() => setLanzarAbierto(true)}>
                  <Send className="mr-1 h-3.5 w-3.5" /> Lanzar
                </Button>
              ) : null}
              <Button
                size="sm"
                variant="outline"
                onClick={() => setHistorialAbierto(true)}
                title="Historial de versiones"
              >
                <History className="mr-1 h-3.5 w-3.5" /> Historial
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="Eliminar documento"
                title="Eliminar (mover a la papelera)"
                className="text-muted-foreground hover:text-destructive"
                onClick={async () => {
                  if (await confirmar({ mensaje: "¿Mover este documento a la papelera?", destructivo: true, textoConfirmar: "Mover" }))
                    eliminarMut.mutate(borrador.id);
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            {/* Cuerpo: WYSIWYG (escribes con formato aplicado). El cuerpo se guarda como markdown. */}
            <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
              <EditorWysiwyg
                value={borrador.cuerpo}
                onContenido={(md) => editar({ cuerpo: md })}
                placeholder={
                  borrador.tipo === "prompt"
                    ? "Escribe el prompt…"
                    : "Escribe la pieza editorial (voz, reglas, plataforma…)…"
                }
              />
            </div>
            <p className="text-xs text-muted-foreground">
              {guardarMut.isPending ? "Guardando…" : `Actualizado ${borrador.actualizado || "—"}`}
            </p>
          </>
        )}
      </main>

      {/* ───────── Lanzar (popup, solo prompts) ───────── */}
      {borrador?.tipo === "prompt" ? (
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

      {/* ───────── Historial de versiones (git) ───────── */}
      {borrador ? (
        <DialogHistorial
          key={`hist-${borrador.id}`}
          docId={borrador.id}
          open={historialAbierto}
          onOpenChange={setHistorialAbierto}
          onRevertido={() => {
            qc.invalidateQueries({ queryKey: ["texto"] });
            setHistorialAbierto(false);
          }}
        />
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Historial de versiones (git)                                                //
// --------------------------------------------------------------------------- //

function DialogHistorial({
  docId,
  open,
  onOpenChange,
  onRevertido,
}: {
  docId: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onRevertido: () => void;
}) {
  const [verSha, setVerSha] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!open) setVerSha(null);
  }, [open]);

  const histQuery = useQuery({
    queryKey: ["texto-historial", docId],
    queryFn: ({ signal }) => api.historialTexto(docId, signal),
    enabled: open,
  });
  const versionQuery = useQuery({
    queryKey: ["texto-version", docId, verSha],
    queryFn: ({ signal }) => api.versionTexto(docId, verSha as string, signal),
    enabled: open && !!verSha,
  });
  const revertirMut = useMutation({
    mutationFn: (sha: string) => api.revertirTexto(docId, sha),
    onSuccess: onRevertido,
  });

  const historial = histQuery.data?.historial ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-3xl flex-col gap-3 overflow-hidden">
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
                      className={`w-full px-3 py-2 text-left text-xs hover:bg-muted ${
                        v.sha === verSha ? "bg-muted" : ""
                      }`}
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
              <p className="text-sm text-muted-foreground">
                Elige una versión para verla y, si quieres, restaurarla.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Versión {verSha.slice(0, 8)}</span>
                  <Button
                    size="sm"
                    variant="outline"
                    className="ml-auto"
                    disabled={revertirMut.isPending}
                    onClick={async () => {
                      if (
                        await confirmar({
                          mensaje: "¿Restaurar esta versión? Se guarda como un cambio nuevo (no se pierde el historial).",
                          textoConfirmar: "Restaurar",
                        })
                      )
                        revertirMut.mutate(verSha);
                    }}
                  >
                    <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restaurar
                  </Button>
                </div>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
                  {versionQuery.isPending ? (
                    <Skeleton className="h-24 w-full" />
                  ) : (
                    <Markdown>{versionQuery.data?.documento.cuerpo || "_Sin contenido_"}</Markdown>
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

// --------------------------------------------------------------------------- //
// Panel de lanzamiento                                                         //
// --------------------------------------------------------------------------- //

function PanelLanzar({
  promptId,
  salida,
  marcas,
  areas,
  open,
  onOpenChange,
}: {
  promptId: string;
  salida: string;
  marcas: { id: string; nombre: string }[];
  areas: { id: string; nombre: string }[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  // La marca la manda el switch GLOBAL: no hay selector de marca propio. Lanzar EXIGE marca
  // concreta, así que si el switch está en "Todas" (`marcaActiva === null`) el botón se
  // deshabilita con el tooltip compartido. Solo lanzamos contra marcas del catálogo.
  const { marcaActiva } = useMarcaActiva();
  const marca = marcaActiva && marcas.some((m) => m.id === marcaActiva) ? marcaActiva : "";
  const [adjuntos, setAdjuntos] = React.useState<Set<string>>(new Set());
  const [tipoTarget, setTipoTarget] = React.useState<TipoTarget>("contenido");
  const [valorTarget, setValorTarget] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);

  // Modo PIEZAS: si el prompt declara salida=piezas, ofrecemos el selector de redes y
  // el lanzamiento crea borradores por red (copy) en vez de un documento markdown.
  const esPiezas = salida === "piezas";
  const [redes, setRedes] = React.useState<Set<string>>(new Set());

  const { generacion, ejecutando, cancelando, iniciar, cancelar } = useGeneracion("keni:texto-lanzar");

  // "Pensando…" con cronómetro: el modelo puede tardar ~1-2 min en RAZONAR antes de emitir
  // el primer token (la fase de thinking NO se transmite a `salida`), así que mientras corre
  // sin salida la UI parecía colgada. Contamos los segundos para señalar que sigue vivo.
  const pensando = ejecutando && !generacion?.salida && !generacion?.error;
  const [pensandoSeg, setPensandoSeg] = React.useState(0);
  React.useEffect(() => {
    if (!pensando) return;
    setPensandoSeg(0);
    const t = setInterval(() => setPensandoSeg((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, [pensando]);

  // Línea editorial auto-resuelta por marca (selección inicial = todas).
  const editorialesQuery = useQuery({
    queryKey: ["texto-editoriales", marca],
    queryFn: ({ signal }) => api.editorialesTexto(marca, undefined, signal),
    enabled: !!marca,
  });
  // Diagnóstico de los 4 pilares editoriales de la marca elegida: avisa si la línea
  // editorial está incompleta ANTES de lanzar (no bloquea, solo advierte).
  const validacionQuery = useQuery({
    queryKey: ["texto-validacion", marca],
    queryFn: ({ signal }) => api.validacionTexto(marca, signal),
    enabled: !!marca,
  });
  const validacion = validacionQuery.data;
  React.useEffect(() => {
    const ids = (editorialesQuery.data?.editoriales ?? []).map((d) => d.id);
    setAdjuntos(new Set(ids));
  }, [editorialesQuery.data]);

  // Redes disponibles (catálogo de publicaciones); preselección = todas, solo en piezas.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: esPiezas,
  });
  const opcionesRedes = React.useMemo(
    () => (opcionesQuery.data?.redes ?? []).map((r) => ({ id: r.id, nombre: r.nombre })),
    [opcionesQuery.data],
  );
  React.useEffect(() => {
    if (esPiezas) setRedes(new Set(opcionesRedes.map((r) => r.id)));
  }, [esPiezas, opcionesRedes]);

  const lanzarMut = useMutation({
    mutationFn: () => {
      const adj = [...adjuntos];
      const redesArr = esPiezas ? [...redes] : undefined;
      if (esPiezas && redesArr && redesArr.length === 0) {
        throw new Error("Elige al menos una red para generar las piezas.");
      }
      if (tipoTarget === "archivo") {
        if (!archivo) throw new Error("Adjunta un archivo o cambia de target.");
        return api.lanzarTextoArchivo(archivo, marca, {
          prompt_id: promptId,
          adjuntos: adj,
          redes: redesArr,
        });
      }
      const target: TargetLanzamiento =
        tipoTarget === "contenido"
          ? { tipo: "contenido", valor: valorTarget }
          : tipoTarget === "url"
            ? { tipo: "url", valor: valorTarget }
            : tipoTarget === "area"
              ? { tipo: "area", valor: valorTarget }
              : { tipo: "ninguno" };
      return api.lanzarTexto({
        prompt_id: promptId,
        marca,
        adjuntos: adj,
        target,
        redes: redesArr,
      });
    },
    onSuccess: (r) => iniciar(r.generacion),
  });

  const editoriales = editorialesQuery.data?.editoriales ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[88vh] max-w-2xl flex-col gap-3 overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4" /> Lanzar prompt
          </DialogTitle>
        </DialogHeader>

      {marca && validacion ? (
        validacion.completa ? (
          <div className="flex items-center gap-2 rounded-md border border-emerald-600/30 bg-emerald-600/5 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>Línea editorial completa: cubre los 4 pilares (marca, voz, tropicalización y plataforma).</span>
          </div>
        ) : (
          <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/5 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{validacion.recomendacion}</span>
          </div>
        )
      ) : null}

      {marca ? (
        <div className="space-y-1">
          <Label>Línea editorial adjunta</Label>
          <div className="flex flex-wrap gap-1">
            {editoriales.length === 0 ? (
              <span className="text-xs text-muted-foreground">Sin editorial para esta marca.</span>
            ) : (
              editoriales.map((d) => {
                const activo = adjuntos.has(d.id);
                return (
                  <Badge
                    key={d.id}
                    variant={activo ? "default" : "outline"}
                    className="cursor-pointer"
                    onClick={() =>
                      setAdjuntos((prev) => {
                        const s = new Set(prev);
                        if (s.has(d.id)) s.delete(d.id);
                        else s.add(d.id);
                        return s;
                      })
                    }
                  >
                    {d.titulo}
                    {activo ? <X className="ml-1 h-3 w-3" /> : null}
                  </Badge>
                );
              })
            )}
          </div>
        </div>
      ) : null}

      {esPiezas ? (
        <SelectorRedMultiple
          opciones={opcionesRedes}
          seleccionadas={redes}
          onCambio={(red, marcada) =>
            setRedes((prev) => {
              const s = new Set(prev);
              if (marcada) s.add(red);
              else s.delete(red);
              return s;
            })
          }
          disabled={ejecutando || lanzarMut.isPending}
        />
      ) : null}

      <div className="space-y-1">
        <Label>Sobre qué</Label>
        <Select value={tipoTarget} onValueChange={(v) => setTipoTarget(v as TipoTarget)}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="contenido">Contenido (pegar texto)</SelectItem>
            <SelectItem value="url">URL</SelectItem>
            <SelectItem value="area">Sección de la Consola</SelectItem>
            <SelectItem value="archivo">Archivo</SelectItem>
            <SelectItem value="ninguno">Nada (solo el prompt)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {tipoTarget === "contenido" ? (
        <AutoTextarea
          value={valorTarget}
          onChange={(e) => setValorTarget(e.target.value)}
          maxHeight={340}
          placeholder="Pega aquí la nota, transcripción o texto…"
          className="min-h-[160px] w-full text-sm"
        />
      ) : tipoTarget === "url" ? (
        <Input value={valorTarget} onChange={(e) => setValorTarget(e.target.value)} placeholder="https://…" />
      ) : tipoTarget === "area" ? (
        <Select value={valorTarget} onValueChange={setValorTarget}>
          <SelectTrigger><SelectValue placeholder="Elige sección" /></SelectTrigger>
          <SelectContent>
            {areas.map((a) => (
              <SelectItem key={a.id} value={a.id}>{a.nombre}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : tipoTarget === "archivo" ? (
        <Input type="file" onChange={(e) => setArchivo(e.target.files?.[0] ?? null)} />
      ) : null}

      <Tooltip label={!marca ? MENSAJE_MARCA_REQUERIDA : ""} className="w-full">
        <Button
          variant="brand"
          className="w-full"
          onClick={() => lanzarMut.mutate()}
          disabled={!marca || ejecutando || lanzarMut.isPending}
        >
          {ejecutando || lanzarMut.isPending ? (
            <Loader2 className="mr-1 h-4 w-4 animate-spin" />
          ) : (
            <MarcaIA className="mr-1" />
          )}
          Lanzar
        </Button>
      </Tooltip>
      {lanzarMut.isError ? (
        <p className="text-xs text-destructive">{(lanzarMut.error as Error).message}</p>
      ) : null}

      {/* C: el progreso aparece en cuanto ARRANCA el lanzamiento (estado intermedio
          "Lanzando…"), sin esperar a que el POST devuelva `r.generacion`. En cuanto
          llega la generación, el panel ya está montado y empieza a pintar el stream. */}
      {generacion || lanzarMut.isPending ? (
        <div className="min-h-0 flex-1 space-y-2 border-t border-border pt-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Resultado</span>
            {ejecutando ? (
              <Button size="sm" variant="ghost" className="ml-auto" onClick={cancelar} disabled={cancelando}>
                {cancelando ? "Cancelando…" : "Cancelar"}
              </Button>
            ) : null}
          </div>
          {!generacion ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Lanzando…</span>
            </div>
          ) : generacion.error ? (
            <p className="text-sm text-destructive">{generacion.error}</p>
          ) : pensando ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>Pensando… {pensandoSeg}s</span>
            </div>
          ) : (
            <>
              <Markdown>{generacion.salida}</Markdown>
              {/* MODO PIEZAS: el copy NO se queda aquí, se guarda como borradores por red en
                  la Parrilla. Lo decimos al completar para que no se busque en este panel. */}
              {esPiezas && !ejecutando && generacion.salida ? (
                <p className="text-xs text-muted-foreground">
                  El copy se guardó como borradores en la Parrilla (uno por red), listos para revisar.
                </p>
              ) : null}
            </>
          )}
        </div>
      ) : null}
      </DialogContent>
    </Dialog>
  );
}
