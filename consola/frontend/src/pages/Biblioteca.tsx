/**
 * Biblioteca: almacén único de PROMPTS + LÍNEA EDITORIAL con editor markdown a pantalla
 * completa (toggle editar/vista) y un panel para LANZAR un prompt sobre un target
 * (contenido pegado / URL / sección de la Consola / archivo), adjuntando la línea editorial
 * de la marca. El resultado llega por streaming (sondeo de la generación).
 *
 * Reemplaza la antigua página de "skills": aquí el contenido es markdown libre, no un
 * formulario rígido. Reutiliza el editor (AutoTextarea + BarraFormato + Markdown), el
 * selector de marca y el hook de generación existentes.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Eye,
  FileText,
  Loader2,
  Pencil,
  Plus,
  RotateCcw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { BarraFormato } from "@/components/editor/BarraFormato";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import type { DocumentoBiblioteca, TargetLanzamiento } from "@/types";

type Filtro = "todo" | "prompt" | "editorial";
type TipoTarget = TargetLanzamiento["tipo"] | "archivo";

const CLASES_EDITORIAL = ["marca", "voz", "plataforma", "tropicalizacion", "reglas"] as const;

export default function Biblioteca() {
  const qc = useQueryClient();

  // --- Navegación / lista ---
  const [filtro, setFiltro] = React.useState<Filtro>("todo");
  const [q, setQ] = React.useState("");
  const [enPapelera, setEnPapelera] = React.useState(false);
  const [seleccionId, setSeleccionId] = React.useState<string | null>(null);
  const [preview, setPreview] = React.useState(false);

  const docsQuery = useQuery({
    queryKey: ["biblioteca", filtro, q],
    queryFn: ({ signal }) =>
      api.biblioteca({ tipo: filtro === "todo" ? undefined : filtro, q: q || undefined }, signal),
  });
  const papeleraQuery = useQuery({
    queryKey: ["biblioteca-papelera"],
    queryFn: ({ signal }) => api.papeleraBiblioteca(signal),
    enabled: enPapelera,
  });
  const marcasQuery = useQuery({
    queryKey: ["biblioteca-marcas"],
    queryFn: ({ signal }) => api.marcasBiblioteca(signal),
  });
  const areasQuery = useQuery({
    queryKey: ["biblioteca-areas"],
    queryFn: ({ signal }) => api.areasBiblioteca(signal),
  });

  const documentos = docsQuery.data?.documentos ?? [];
  const seleccion = documentos.find((d) => d.id === seleccionId) ?? null;

  // --- Borrador del editor (copia de trabajo, sincronizada al cambiar de documento) ---
  const [borrador, setBorrador] = React.useState<DocumentoBiblioteca | null>(null);
  React.useEffect(() => {
    setBorrador(seleccion ? { ...seleccion } : null);
    setPreview(false);
  }, [seleccionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const areaRef = React.useRef<HTMLTextAreaElement>(null);
  const guardarTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  const guardarMut = useMutation({
    mutationFn: ({ id, cuerpo }: { id: string; cuerpo: Partial<DocumentoBiblioteca> }) =>
      api.guardarDocumento(id, cuerpo),
    onSuccess: (r) => {
      // El id puede cambiar (renombrado/carpeta): re-sincroniza la selección.
      if (r.documento.id !== seleccionId) setSeleccionId(r.documento.id);
      qc.invalidateQueries({ queryKey: ["biblioteca"] });
    },
  });

  function editar(parcial: Partial<DocumentoBiblioteca>) {
    if (!borrador) return;
    const siguiente = { ...borrador, ...parcial };
    setBorrador(siguiente);
    if (guardarTimer.current) clearTimeout(guardarTimer.current);
    guardarTimer.current = setTimeout(() => {
      guardarMut.mutate({
        id: borrador.id,
        cuerpo: {
          titulo: siguiente.titulo,
          cuerpo: siguiente.cuerpo,
          carpeta: siguiente.carpeta,
          clase: siguiente.clase,
          marcas: siguiente.marcas,
        },
      });
    }, 600);
  }

  const crearMut = useMutation({
    mutationFn: (tipo: "prompt" | "editorial") =>
      api.crearDocumento({ titulo: tipo === "prompt" ? "Nuevo prompt" : "Nuevo editorial", tipo }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["biblioteca"] });
      setSeleccionId(r.documento.id);
    },
  });
  const eliminarMut = useMutation({
    mutationFn: (id: string) => api.eliminarDocumento(id),
    onSuccess: () => {
      if (seleccionId) setSeleccionId(null);
      qc.invalidateQueries({ queryKey: ["biblioteca"] });
      qc.invalidateQueries({ queryKey: ["biblioteca-papelera"] });
    },
  });
  const restaurarMut = useMutation({
    mutationFn: (id: string) => api.restaurarDocumento(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["biblioteca"] });
      qc.invalidateQueries({ queryKey: ["biblioteca-papelera"] });
    },
  });

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* ───────── Sidebar ───────── */}
      <aside className="flex w-64 shrink-0 flex-col gap-3">
        <div className="flex items-center gap-2">
          <Tabs value={filtro} onValueChange={(v) => setFiltro(v as Filtro)} className="flex-1">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="todo">Todo</TabsTrigger>
              <TabsTrigger value="prompt">Prompts</TabsTrigger>
              <TabsTrigger value="editorial">Editorial</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <Input placeholder="Buscar…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="flex gap-2">
          <Button size="sm" variant="outline" className="flex-1" onClick={() => crearMut.mutate("prompt")}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Prompt
          </Button>
          <Button size="sm" variant="outline" className="flex-1" onClick={() => crearMut.mutate("editorial")}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Editorial
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border">
          {docsQuery.isPending ? (
            <div className="space-y-2 p-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : documentos.length === 0 ? (
            <p className="p-3 text-sm text-muted-foreground">No hay documentos. Crea uno arriba.</p>
          ) : (
            <ul className="divide-y divide-border">
              {documentos.map((d) => (
                <li key={d.id}>
                  <button
                    onClick={() => setSeleccionId(d.id)}
                    className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-muted ${
                      d.id === seleccionId ? "bg-muted font-medium" : ""
                    }`}
                  >
                    {d.tipo === "editorial" ? (
                      <BookOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    ) : (
                      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    )}
                    <span className="truncate">{d.titulo}</span>
                    {d.carpeta ? (
                      <span className="ml-auto truncate text-xs text-muted-foreground">{d.carpeta}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
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
              <p className="text-lg font-medium">Biblioteca de prompts y línea editorial</p>
              <p className="text-sm">Selecciona un documento o crea uno nuevo.</p>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <Input
                value={borrador.titulo}
                onChange={(e) => editar({ titulo: e.target.value })}
                className="text-base font-medium"
                placeholder="Título"
              />
              <Input
                value={borrador.carpeta}
                onChange={(e) => editar({ carpeta: e.target.value })}
                className="w-40"
                placeholder="carpeta/…"
              />
              <Button
                size="sm"
                variant="outline"
                onClick={() => setPreview((v) => !v)}
              >
                {preview ? <Pencil className="mr-1 h-3.5 w-3.5" /> : <Eye className="mr-1 h-3.5 w-3.5" />}
                {preview ? "Editar" : "Vista"}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                onClick={() => eliminarMut.mutate(borrador.id)}
                aria-label="Eliminar"
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            {borrador.tipo === "editorial" ? (
              <div className="flex flex-wrap items-center gap-2">
                <Select value={borrador.clase || "marca"} onValueChange={(v) => editar({ clase: v })}>
                  <SelectTrigger className="w-44"><SelectValue placeholder="Clase" /></SelectTrigger>
                  <SelectContent>
                    {CLASES_EDITORIAL.map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={borrador.marcas.join(", ")}
                  onChange={(e) =>
                    editar({ marcas: e.target.value.split(",").map((m) => m.trim()).filter(Boolean) })
                  }
                  placeholder="marcas (ids separados por coma)"
                  className="flex-1"
                />
              </div>
            ) : null}

            {!preview && <BarraFormato refArea={areaRef} valor={borrador.cuerpo} onContenido={(v) => editar({ cuerpo: v })} />}

            <div className="min-h-0 flex-1 overflow-y-auto rounded-md border border-border p-3">
              {preview ? (
                <Markdown>{borrador.cuerpo || "_Sin contenido_"}</Markdown>
              ) : (
                <AutoTextarea
                  ref={areaRef}
                  value={borrador.cuerpo}
                  onChange={(e) => editar({ cuerpo: e.target.value })}
                  className="min-h-[300px] w-full resize-none border-0 p-0 font-mono text-sm focus-visible:ring-0"
                  placeholder={
                    borrador.tipo === "prompt"
                      ? "Escribe el prompt en markdown…"
                      : "Escribe la pieza editorial (voz, reglas, plataforma…)…"
                  }
                />
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {guardarMut.isPending ? "Guardando…" : `Actualizado ${borrador.actualizado || "—"}`}
            </p>
          </>
        )}
      </main>

      {/* ───────── Panel de lanzar (solo prompts) ───────── */}
      {borrador?.tipo === "prompt" ? (
        <PanelLanzar
          promptId={borrador.id}
          marcas={marcasQuery.data?.marcas ?? []}
          areas={areasQuery.data?.areas ?? []}
        />
      ) : null}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Panel de lanzamiento                                                         //
// --------------------------------------------------------------------------- //

function PanelLanzar({
  promptId,
  marcas,
  areas,
}: {
  promptId: string;
  marcas: { id: string; nombre: string }[];
  areas: { id: string; nombre: string }[];
}) {
  const [marca, setMarca] = React.useState("");
  const [adjuntos, setAdjuntos] = React.useState<Set<string>>(new Set());
  const [tipoTarget, setTipoTarget] = React.useState<TipoTarget>("contenido");
  const [valorTarget, setValorTarget] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);

  const { generacion, ejecutando, cancelando, iniciar, cancelar } = useGeneracion("keni:biblioteca-lanzar");

  // Línea editorial auto-resuelta por marca (selección inicial = todas).
  const editorialesQuery = useQuery({
    queryKey: ["biblioteca-editoriales", marca],
    queryFn: ({ signal }) => api.editorialesBiblioteca(marca, signal),
    enabled: !!marca,
  });
  React.useEffect(() => {
    const ids = (editorialesQuery.data?.editoriales ?? []).map((d) => d.id);
    setAdjuntos(new Set(ids));
  }, [editorialesQuery.data]);

  const lanzarMut = useMutation({
    mutationFn: () => {
      const adj = [...adjuntos];
      if (tipoTarget === "archivo") {
        if (!archivo) throw new Error("Adjunta un archivo o cambia de target.");
        return api.lanzarBibliotecaArchivo(archivo, marca, { prompt_id: promptId, adjuntos: adj });
      }
      const target: TargetLanzamiento =
        tipoTarget === "contenido"
          ? { tipo: "contenido", valor: valorTarget }
          : tipoTarget === "url"
            ? { tipo: "url", valor: valorTarget }
            : tipoTarget === "area"
              ? { tipo: "area", valor: valorTarget }
              : { tipo: "ninguno" };
      return api.lanzarBiblioteca({ prompt_id: promptId, marca, adjuntos: adj, target });
    },
    onSuccess: (r) => iniciar(r.generacion),
  });

  const editoriales = editorialesQuery.data?.editoriales ?? [];

  return (
    <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto rounded-md border border-border p-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        <Send className="h-4 w-4" /> Lanzar prompt
      </h2>

      <div className="space-y-1">
        <Label>Marca</Label>
        <SelectorMarca marcas={marcas} valor={marca} onCambio={setMarca} incluirTodas={false} />
      </div>

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
          maxHeight={220}
          placeholder="Pega aquí la nota, transcripción o texto…"
          className="w-full text-sm"
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

      <Button
        onClick={() => lanzarMut.mutate()}
        disabled={!marca || ejecutando || lanzarMut.isPending}
      >
        {ejecutando || lanzarMut.isPending ? (
          <Loader2 className="mr-1 h-4 w-4 animate-spin" />
        ) : (
          <Send className="mr-1 h-4 w-4" />
        )}
        Lanzar
      </Button>
      {lanzarMut.isError ? (
        <p className="text-xs text-destructive">{(lanzarMut.error as Error).message}</p>
      ) : null}

      {generacion ? (
        <div className="min-h-0 flex-1 space-y-2 border-t border-border pt-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium">Resultado</span>
            {ejecutando ? (
              <Button size="sm" variant="ghost" className="ml-auto" onClick={cancelar} disabled={cancelando}>
                {cancelando ? "Cancelando…" : "Cancelar"}
              </Button>
            ) : null}
          </div>
          {generacion.error ? (
            <p className="text-sm text-destructive">{generacion.error}</p>
          ) : (
            <Markdown>{generacion.salida || (ejecutando ? "_Generando…_" : "")}</Markdown>
          )}
        </div>
      ) : null}
    </aside>
  );
}
