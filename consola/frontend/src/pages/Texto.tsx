/**
 * Biblioteca de Prompts: el corazón editorial de la máquina de contenido.
 *
 * Tres superficies en una página (estado en la URL: `?vista=`, `?doc=`, `?filtro=`):
 *   - "La máquina" (default): el riel de pipelines en el ORDEN REAL de ejecución
 *     (GET /api/texto/maquina), con el ensamblaje editorial de la marca bajo la etapa
 *     de copy. Es el mapa del sistema: cada tarjeta abre su documento.
 *   - "Todos los documentos": tabla plana para gestión/búsqueda (filtros + papelera).
 *   - Detalle de documento: cabecera de estado (línea de deployment + publicar/solicitar),
 *     cuerpo SIEMPRE WYSIWYG con chips de variables, y panel lateral (versiones / uso /
 *     compilado / ficha). Sin candado: editar es libre, producción solo cambia al publicar.
 *
 * Header común: selector de vista, marca (reusa el estado GLOBAL del workspace), búsqueda,
 * "Nuevo documento", e indicadores de cambios sin publicar y solicitudes pendientes (admins).
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, FilePlus2, Inbox, Plus } from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BandejaSolicitudes } from "@/components/biblioteca/BandejaSolicitudes";
import { MenuFlotante } from "@/components/comunes/MenuContextual";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { MARCA_TODAS, marcaParam } from "@/components/comunes/selectores";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { claveSolicitudes, useEsAdmin } from "@/hooks/use-biblioteca";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { useMenuContextual } from "@/hooks/use-menu-contextual";
import { api, mensajeError } from "@/lib/api";
import type { DocumentoTexto } from "@/types";

import { DetalleDocumento } from "./texto/DetalleDocumento";
import { TablaDocumentos } from "./texto/TablaDocumentos";
import { VistaMaquina } from "./texto/VistaMaquina";

type Vista = "maquina" | "todos";

/** Filtro de búsqueda en cliente (título, descripción, carpeta, etiquetas y cuerpo). */
function coincide(d: DocumentoTexto, q: string): boolean {
  const t = q.toLowerCase();
  return (
    d.titulo.toLowerCase().includes(t) ||
    (d.descripcion ?? "").toLowerCase().includes(t) ||
    d.carpeta.toLowerCase().includes(t) ||
    (d.etiquetas ?? []).some((e) => e.toLowerCase().includes(t)) ||
    d.cuerpo.toLowerCase().includes(t)
  );
}

export default function Texto() {
  const qc = useQueryClient();
  const esAdmin = useEsAdmin();
  const { marcaActiva, nombreActiva, marcasParaSwitch, esMultiMarca, puedeTodas, cambiarMarca } =
    useMarcaActiva();

  // ── Estado en la URL: vista, documento abierto y filtro "sin publicar". ──
  const [searchParams, setSearchParams] = useSearchParams();
  const vista: Vista = searchParams.get("vista") === "todos" ? "todos" : "maquina";
  const docAbierto = searchParams.get("doc");
  const soloSinPublicar = searchParams.get("filtro") === "sin-publicar";
  const mutarParams = React.useCallback(
    (cambios: Record<string, string | null>) => {
      setSearchParams(
        (prev) => {
          const s = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(cambios)) {
            if (v === null) s.delete(k);
            else s.set(k, v);
          }
          return s;
        },
        { replace: false },
      );
    },
    [setSearchParams],
  );
  const abrirDoc = React.useCallback((id: string) => mutarParams({ doc: id }), [mutarParams]);
  const cerrarDoc = React.useCallback(() => mutarParams({ doc: null }), [mutarParams]);

  const [q, setQ] = React.useState("");

  // ── Datos: listado completo de la marca (búsqueda y filtros finos en cliente), el riel
  //    de la máquina, la validación editorial y las solicitudes pendientes (admins). ──
  const docsQuery = useQuery({
    queryKey: ["texto", "lista", marcaActiva],
    queryFn: ({ signal }) => api.texto({ marca: marcaActiva ?? undefined }, signal),
  });
  const documentos = React.useMemo(() => docsQuery.data?.documentos ?? [], [docsQuery.data]);
  const filtrados = React.useMemo(
    () => (q.trim() ? documentos.filter((d) => coincide(d, q.trim())) : documentos),
    [documentos, q],
  );
  const sinPublicar = React.useMemo(
    () => documentos.filter((d) => d.sin_publicar).length,
    [documentos],
  );

  const maquinaQuery = useQuery({
    queryKey: ["texto-maquina", marcaActiva],
    queryFn: ({ signal }) => api.maquinaTexto(marcaActiva ?? undefined, signal),
  });
  const validacionQuery = useQuery({
    queryKey: ["texto-validacion", marcaActiva],
    queryFn: ({ signal }) => api.validacionTexto(marcaActiva as string, signal),
    enabled: !!marcaActiva,
  });
  const solicitudesQuery = useQuery({
    queryKey: claveSolicitudes("abierta"),
    queryFn: ({ signal }) => api.solicitudesTexto("abierta", signal),
    enabled: esAdmin,
  });
  const numSolicitudes = solicitudesQuery.data?.solicitudes.length ?? 0;
  const [bandejaAbierta, setBandejaAbierta] = React.useState(false);

  // Título legible de los docs del riel (las tarjetas muestran el nombre del prompt).
  const tituloPorId = React.useMemo(
    () => new Map(documentos.map((d) => [d.id, d.titulo])),
    [documentos],
  );

  // ── Crear documento (menú: prompt o editorial). ──
  const menuNuevo = useMenuContextual();
  const botonNuevoRef = React.useRef<HTMLButtonElement>(null);
  const crearMut = useMutation({
    mutationFn: (tipo: "prompt" | "editorial") =>
      api.crearDocumento({
        titulo: tipo === "prompt" ? "Nuevo prompt" : "Nuevo documento editorial",
        tipo,
      }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["texto"] });
      abrirDoc(r.documento.id);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // ── Vista detalle: ocupa la página entera (el estado vive en la URL). ──
  if (docAbierto) {
    return (
      <DetalleDocumento
        key={docAbierto}
        docId={docAbierto}
        maquina={maquinaQuery.data}
        onCerrar={cerrarDoc}
        onIdCambiado={(id) => mutarParams({ doc: id })}
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      {/* ───────── Dashboard superior ───────── */}
      <div className="flex flex-wrap items-center gap-2">
        <Tabs
          value={vista}
          onValueChange={(v) => mutarParams({ vista: v === "todos" ? "todos" : null })}
        >
          <TabsList>
            <TabsTrigger value="maquina" title="El riel de pipelines en orden real de ejecución">
              La máquina
            </TabsTrigger>
            <TabsTrigger value="todos" title="Tabla plana de todos los documentos">
              Todos los documentos
            </TabsTrigger>
          </TabsList>
        </Tabs>
        {esMultiMarca ? (
          <SelectorMarca
            marcas={marcasParaSwitch}
            valor={marcaActiva ?? MARCA_TODAS}
            onCambio={(v) => cambiarMarca(marcaParam(v) ?? null)}
            incluirTodas={puedeTodas}
            className="w-[180px]"
            ariaLabel="Marca de la biblioteca"
          />
        ) : null}
        <Input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            // Buscar es gestionar: la búsqueda vive en la tabla, no en el riel.
            if (e.target.value && vista === "maquina") mutarParams({ vista: "todos" });
          }}
          placeholder="Buscar documentos…"
          className="h-9 w-full sm:w-56"
          aria-label="Buscar documentos"
        />
        <Button
          ref={botonNuevoRef}
          size="sm"
          variant="outline"
          onClick={(e) => menuNuevo.abrirEn(e, botonNuevoRef.current)}
        >
          <Plus className="mr-1 h-3.5 w-3.5" /> Nuevo documento
        </Button>
        {menuNuevo.abierto && menuNuevo.pos ? (
          <MenuFlotante
            pos={menuNuevo.pos}
            onClose={menuNuevo.cerrar}
            etiqueta="Nuevo documento"
            items={[
              {
                etiqueta: "Prompt",
                icono: FilePlus2,
                onClick: () => crearMut.mutate("prompt"),
              },
              {
                etiqueta: "Documento editorial",
                icono: FilePlus2,
                onClick: () => crearMut.mutate("editorial"),
              },
            ]}
          />
        ) : null}

        {/* Indicadores a la derecha. */}
        <div className="ml-auto flex items-center gap-2">
          {sinPublicar > 0 ? (
            <button
              type="button"
              onClick={() => mutarParams({ vista: "todos", filtro: "sin-publicar" })}
              className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-700 hover:bg-amber-500/25 dark:text-amber-300"
              title="Documentos cuyo borrador difiere de lo publicado. Clic para verlos."
            >
              <AlertTriangle className="h-3 w-3" aria-hidden />
              {sinPublicar} {sinPublicar === 1 ? "cambio" : "cambios"} sin publicar
            </button>
          ) : null}
          {esAdmin ? (
            <button
              type="button"
              onClick={() => setBandejaAbierta(true)}
              className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted"
              title="Solicitudes de publicación pendientes de revisar"
            >
              <Inbox className="h-3 w-3" aria-hidden />
              {numSolicitudes} {numSolicitudes === 1 ? "solicitud" : "solicitudes"}
            </button>
          ) : null}
        </div>
      </div>

      {/* ───────── Vista activa ───────── */}
      {vista === "maquina" ? (
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          <VistaMaquina
            grupos={maquinaQuery.data?.grupos ?? []}
            capas={maquinaQuery.data?.capas ?? []}
            validacion={validacionQuery.data}
            nombreMarca={marcaActiva ? nombreActiva : null}
            cargando={maquinaQuery.isPending}
            tituloDe={(id) => tituloPorId.get(id)}
            onAbrir={abrirDoc}
          />
        </div>
      ) : (
        <TablaDocumentos
          documentos={filtrados}
          cargando={docsQuery.isPending}
          soloSinPublicar={soloSinPublicar}
          onCambioSinPublicar={(v) => mutarParams({ filtro: v ? "sin-publicar" : null })}
          onAbrir={abrirDoc}
        />
      )}

      {/* ───────── Bandeja de solicitudes (admins) ───────── */}
      <Dialog
        open={bandejaAbierta}
        onOpenChange={(v) => {
          setBandejaAbierta(v);
          // Al cerrar tras aprobar/rechazar, el estado de publicación pudo cambiar.
          if (!v) qc.invalidateQueries({ queryKey: ["texto-maquina"] });
        }}
      >
        <DialogContent className="flex max-h-[85vh] max-w-2xl flex-col gap-3 overflow-hidden">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Inbox className="h-4 w-4" /> Bandeja de solicitudes
            </DialogTitle>
          </DialogHeader>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <BandejaSolicitudes />
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
