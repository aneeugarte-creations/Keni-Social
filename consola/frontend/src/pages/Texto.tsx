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
  ChevronDown,
  ChevronRight,
  FileText,
  Folder,
  History,
  Lock,
  Plus,
  RotateCcw,
  Send,
  Trash2,
  Zap,
} from "lucide-react";
import * as React from "react";

import { confirmar } from "@/components/comunes/confirmar";
import { EditorWysiwyg } from "@/components/editor/EditorWysiwyg";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";
import type { DocumentoTexto } from "@/types";

import { DialogHistorial } from "./texto/DialogHistorial";
import { separarFrontmatter } from "./texto/lib";
import { PanelLanzar } from "./texto/PanelLanzar";

const ESTADOS_DOC = ["activo", "borrador", "archivado"] as const;

// Etiqueta humana de cada pipeline/etapa (mismo vocabulario que la vista Pipelines y el back
// `_ETAPAS`): para mostrar "se inyecta en la etapa …" en los editoriales con un nombre que el
// equipo ya reconoce, no la clave técnica.
const ETAPA_LABEL: Record<string, string> = {
  fusion: "Fusión",
  editorial: "Editorial",
  ci: "Selección",
  qa: "Validación",
  copy: "Copy",
  cd: "Copy",
  arte: "Arte",
  evergreen: "Evergreen",
};

// Pestañas del estudio: PROMPTS (los que inyectamos en los agentes) separados de los
// documentos editoriales, y estos a su vez en MARCA (marca/voz: la cara de cada marca) y
// REGLAS (reglas/plataforma/tropicalización: lo transversal). Catch-all: cualquier editorial
// que no sea marca/voz cae en "reglas", así ningún documento queda oculto.
type Pestana = "prompts" | "marca" | "reglas";
const CLASES_MARCA = new Set(["marca", "voz"]);
function pestanaDeDoc(d: DocumentoTexto): Pestana {
  if (d.tipo === "prompt") return "prompts";
  return CLASES_MARCA.has(d.clase || "") ? "marca" : "reglas";
}

// Marcadores `{{VARIABLE}}` que la consola SUSTITUYE al inyectar el prompt (el tema, la ruta del
// archivo, el roster…). Se detectan en el cuerpo para mostrarlos y resaltarlos.
const RE_VARIABLE = /\{\{[A-Z_]+\}\}/g;

/** Vista de LECTURA de un prompt: el texto LITERAL que se inyecta, con sus variables resaltadas.
 *  No es markdown renderizado: muestra exactamente lo que recibe el modelo (incluidos los `{{…}}`). */
function PromptLeible({ texto }: { texto: string }) {
  const partes = texto.split(/(\{\{[A-Z_]+\}\})/g);
  return (
    <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-relaxed">
      {partes.map((p, i) =>
        /^\{\{[A-Z_]+\}\}$/.test(p) ? (
          <code key={i} className="rounded bg-keni/15 px-1 py-0.5 font-medium text-keni">
            {p}
          </code>
        ) : (
          <React.Fragment key={i}>{p}</React.Fragment>
        ),
      )}
    </pre>
  );
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
  const [pestana, setPestana] = React.useState<Pestana>("prompts");
  const [enPapelera, setEnPapelera] = React.useState(false);
  const [seleccionId, setSeleccionId] = React.useState<string | null>(null);
  // Config avanzada (estado, etiquetas, clase/marcas, atribución) plegada tras el engranaje.
  const [historialAbierto, setHistorialAbierto] = React.useState(false);
  const [carpetasCerradas, setCarpetasCerradas] = React.useState<Set<string>>(new Set());
  const [lanzarAbierto, setLanzarAbierto] = React.useState(false);
  // Candado de los prompts protegidos: la edición arranca BLOQUEADA y hay que forzarla (popup).
  const [forzarEdicion, setForzarEdicion] = React.useState(false);
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
  // Documentos VISIBLES en la pestaña activa (las búsquedas/lookups del editor siguen sobre
  // `documentos`, la lista completa, para no perder la selección al cambiar de pestaña).
  const docsVista = React.useMemo(
    () => documentos.filter((d) => pestanaDeDoc(d) === pestana),
    [documentos, pestana],
  );

  // Agrupa por carpeta: la jerarquía ES la navegación. Raíz ("") primero, resto alfabético.
  const grupos = React.useMemo(() => {
    const m = new Map<string, DocumentoTexto[]>();
    for (const d of docsVista) {
      const k = d.carpeta || "";
      const arr = m.get(k);
      if (arr) arr.push(d);
      else m.set(k, [d]);
    }
    return [...m.entries()].sort(([a], [b]) =>
      a === "" ? -1 : b === "" ? 1 : a.localeCompare(b, "es"),
    );
  }, [docsVista]);

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
    setForzarEdicion(false); // cada documento arranca bloqueado si está protegido
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
          descripcion: siguiente.descripcion ?? "",
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

  // --- Candado de prompts ---
  // Un prompt está PROTEGIDO si el catálogo lo marca como inyectado/usado en la IA (`procesos`):
  // se inyecta directo a un agente, así que no debe editarse a la ligera. Arranca en LECTURA;
  // editar requiere forzar el candado (popup). Los documentos editoriales y los prompts propios
  // (sin procesos) se editan como siempre.
  const esPrompt = borrador?.tipo === "prompt";
  const protegido = esPrompt && (borrador?.procesos?.length ?? 0) > 0;
  const editable = !protegido || forzarEdicion;
  // Variables `{{…}}` que la consola sustituye al inyectar (para mostrarlas en la vista de lectura).
  const variablesPrompt = React.useMemo(
    () => Array.from(new Set(borrador?.cuerpo.match(RE_VARIABLE) ?? [])),
    [borrador?.cuerpo],
  );
  const onForzarEdicion = async () => {
    const ok = await confirmar({
      titulo: "Editar un prompt protegido",
      mensaje:
        "Este prompt se inyecta directamente en la IA en los procesos indicados arriba. Editarlo " +
        "cambia el comportamiento del sistema en producción. ¿Seguro que quieres editarlo?",
      textoConfirmar: "Sí, forzar edición",
      textoCancelar: "Cancelar",
    });
    if (ok) setForzarEdicion(true);
  };

  return (
    <div className="flex h-full min-h-0 flex-col gap-4 md:flex-row">
      {/* ───────── Sidebar ───────── */}
      {/* En móvil el explorador se apila arriba (ancho completo) con su lista
          acotada; en escritorio es una columna fija a la izquierda. */}
      <aside className="flex w-full shrink-0 flex-col gap-3 md:w-64">
        <Tabs value={pestana} onValueChange={(v) => setPestana(v as Pestana)}>
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="prompts" title="Prompts que inyectamos en los agentes">
              Prompts
            </TabsTrigger>
            <TabsTrigger value="marca" title="Documentos de marca (marca y voz)">
              Marca
            </TabsTrigger>
            <TabsTrigger value="reglas" title="Reglas, plataforma y tropicalización">
              Reglas
            </TabsTrigger>
          </TabsList>
        </Tabs>
        <Input placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button
          size="sm"
          variant="outline"
          onClick={() => crearMut.mutate(pestana === "prompts" ? "prompt" : "editorial")}
        >
          <Plus className="mr-1 h-3.5 w-3.5" />
          {pestana === "prompts" ? "Nuevo prompt" : "Nuevo documento"}
        </Button>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border max-md:max-h-[45vh]">
          {docsQuery.isPending ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : docsVista.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">
              {buscando ? "Sin resultados." : "No hay documentos en esta pestaña. Crea uno arriba."}
            </p>
          ) : buscando ? (
            // Buscando: lista plana (resultados de todas las carpetas), con la carpeta como pista.
            <ul className="divide-y divide-border">{docsVista.map((d) => filaDoc(d, true))}</ul>
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
            {/* Cabecera: título (editable o, si está protegido y en lectura, solo texto) + badge
                de candado + estado + Lanzar (prompt) + historial + borrar. Las acciones de EDICIÓN
                (título, estado, borrar) se ocultan en un prompt protegido hasta forzar el candado. */}
            <div className="flex flex-wrap items-center gap-2">
              {editable ? (
                <Input
                  value={borrador.titulo}
                  onChange={(e) => editar({ titulo: e.target.value })}
                  className="min-w-[12rem] flex-1 text-base font-medium"
                  placeholder="Título"
                />
              ) : (
                <h2 className="min-w-[12rem] flex-1 truncate text-base font-medium" title={borrador.titulo}>
                  {borrador.titulo}
                </h2>
              )}
              {protegido ? (
                <span
                  className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
                  title="Prompt del sistema: protegido contra ediciones accidentales"
                >
                  <Lock className="h-3 w-3" /> Protegido
                </span>
              ) : null}
              {editable ? (
                <Select value={borrador.estado || "activo"} onValueChange={(v) => editar({ estado: v })}>
                  <SelectTrigger className="h-8 w-28 text-xs" title="Estado"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ESTADOS_DOC.map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : null}
              {esPrompt ? (
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
              {editable ? (
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
              ) : null}
            </div>

            {/* Descripción HUMANA: qué es el doc y para qué. NO se inyecta en la IA (a diferencia
                del cuerpo); solo orienta al equipo en la Biblioteca. */}
            {editable ? (
              <Input
                value={borrador.descripcion ?? ""}
                onChange={(e) => editar({ descripcion: e.target.value })}
                className="h-8 text-xs text-muted-foreground"
                placeholder="Descripción: qué es y para qué (no se inyecta en la IA)"
              />
            ) : borrador.descripcion ? (
              <p className="text-xs text-muted-foreground">{borrador.descripcion}</p>
            ) : null}

            {/* Editoriales: indicador de DÓNDE se inyecta, con el vocabulario de etapas del
                producto. El editorial es material de referencia que entra en la etapa Copy de su
                marca (o las etapas que declare `pipelines`). Los prompts lo muestran en su panel. */}
            {!esPrompt ? (
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span>Se inyecta en la etapa:</span>
                {(borrador.pipelines && borrador.pipelines.length > 0
                  ? borrador.pipelines.map((p) => ETAPA_LABEL[p] ?? p)
                  : ["Copy"]
                ).map((etapa) => (
                  <span
                    key={etapa}
                    className="rounded-full bg-keni/10 px-2 py-0.5 font-medium text-keni"
                  >
                    {etapa}
                  </span>
                ))}
              </div>
            ) : null}

            {/* Panel de INYECCIÓN (solo prompts): el objetivo de esta vista es ENTENDER qué se
                inyecta y DÓNDE. Sale del catálogo en código (`procesos`), no del contenido editable. */}
            {esPrompt ? (
              <div className="rounded-lg border border-border bg-card text-sm">
                <div className="border-b border-border px-4 py-2.5">
                  <div className="flex items-center gap-1.5 font-semibold">
                    <Zap className="h-4 w-4 text-keni" />
                    {protegido ? "Dónde entra a la IA" : "Prompt propio"}
                  </div>
                  {protegido ? (
                    <ul className="mt-1.5 space-y-1">
                      {borrador.procesos!.map((p) => (
                        <li key={p} className="flex gap-2 text-foreground">
                          <span className="text-keni">→</span>
                          <span>{p}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-xs text-muted-foreground">
                      No está cableado a ningún proceso automático: se ejecuta a mano con «Lanzar».
                    </p>
                  )}
                </div>
                {variablesPrompt.length > 0 ? (
                  <div className="px-4 py-2.5">
                    <div className="text-xs font-medium text-muted-foreground">
                      Variables que la consola sustituye al inyectar
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {variablesPrompt.map((v) => (
                        <code key={v} className="rounded bg-keni/10 px-1.5 py-0.5 text-xs font-medium text-keni">
                          {v}
                        </code>
                      ))}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}

            {/* Cuerpo. Prompt protegido = LECTURA por defecto (ves el texto LITERAL que se inyecta,
                con sus variables resaltadas); editar exige forzar el candado. El resto: editor WYSIWYG. */}
            {editable ? (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
                  <EditorWysiwyg
                    value={borrador.cuerpo}
                    onContenido={(md) => editar({ cuerpo: md })}
                    placeholder={
                      esPrompt
                        ? "Escribe el prompt…"
                        : "Escribe la pieza editorial (voz, reglas, plataforma…)…"
                    }
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  {protegido ? "⚠️ Edición forzada — afecta a lo que se inyecta en la IA. " : ""}
                  {guardarMut.isPending ? "Guardando…" : `Actualizado ${borrador.actualizado || "—"}`}
                </p>
              </>
            ) : (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border bg-muted/20 p-4">
                  <PromptLeible texto={borrador.cuerpo} />
                </div>
                <div className="flex items-center gap-2">
                  <Button size="sm" variant="outline" onClick={() => void onForzarEdicion()}>
                    <Lock className="mr-1 h-3.5 w-3.5" /> Editar (forzar)
                  </Button>
                  <p className="text-xs text-muted-foreground">
                    Prompt protegido en modo lectura. Edítalo solo si sabes qué cambias.
                  </p>
                </div>
              </>
            )}
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
