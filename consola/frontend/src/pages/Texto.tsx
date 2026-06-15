/**
 * Biblioteca de Prompts: el corazón editorial del sistema, organizado alrededor de las
 * TRES MÁQUINAS del ADR 0011 + la Estrategia de marca.
 *
 * Pestañas principales (estado en la URL: `?vista=`, `?doc=`, `?filtro=`):
 *   - Investigación (default) · Producción · Importación: la línea de SU máquina
 *     (GET /api/texto/maquina, riel GLOBAL), etapas `prompt` como tarjetas clicables y
 *     etapas `mecanica` como nodos fantasma; el evergreen aparte como anexo «Taller».
 *   - Estrategia de marca: el espacio editorial de la marca activa (EstrategiaMarca).
 *   - Documentos: tabla plana para gestión/búsqueda (filtros + papelera + sin publicar).
 *
 * Header global (sobre las pestañas): búsqueda (salta a Documentos), «Nuevo documento»,
 * badge de cambios sin publicar (→ Documentos filtrado) y solicitudes (admins, bandeja).
 *
 * Detalle de documento (`?doc=`): ocupa la página; al cerrar vuelve a la pestaña de
 * origen (la `vista` queda intacta en la URL).
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
import { EstrategiaMarca } from "./texto/estrategia/EstrategiaMarca";
import { RielMaquina } from "./texto/RielMaquina";
import { TablaDocumentos } from "./texto/TablaDocumentos";

/** Las pestañas principales: las tres máquinas + estrategia + gestión. */
const VISTAS = ["investigacion", "produccion", "importacion", "estrategia", "documentos"] as const;
type Vista = (typeof VISTAS)[number];
const VISTA_DEFECTO: Vista = "investigacion";

const ETIQUETA_VISTA: Record<Vista, string> = {
  investigacion: "Investigación",
  produccion: "Producción",
  importacion: "Importación",
  estrategia: "Estrategia de marca",
  documentos: "Documentos",
};

function vistaDe(param: string | null): Vista {
  return (VISTAS as readonly string[]).includes(param ?? "") ? (param as Vista) : VISTA_DEFECTO;
}

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
  const { marcaActiva, marcasParaSwitch, esMultiMarca, puedeTodas, cambiarMarca } =
    useMarcaActiva();

  // ── Estado en la URL: vista, documento abierto y filtro "sin publicar". ──
  const [searchParams, setSearchParams] = useSearchParams();
  const vista = vistaDe(searchParams.get("vista"));
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
  const irAVista = React.useCallback(
    (v: Vista) => mutarParams({ vista: v === VISTA_DEFECTO ? null : v }),
    [mutarParams],
  );
  const abrirDoc = React.useCallback((id: string) => mutarParams({ doc: id }), [mutarParams]);
  const cerrarDoc = React.useCallback(() => mutarParams({ doc: null }), [mutarParams]);

  const [q, setQ] = React.useState("");

  // ── Datos: listado de la marca (tabla, búsqueda y títulos de la línea), la línea GLOBAL
  //    de las tres máquinas y las solicitudes pendientes (admins). ──
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
    queryKey: ["texto-maquina"],
    queryFn: ({ signal }) => api.maquinaTexto(signal),
  });
  const solicitudesQuery = useQuery({
    queryKey: claveSolicitudes("abierta"),
    queryFn: ({ signal }) => api.solicitudesTexto("abierta", signal),
    enabled: esAdmin,
  });
  const numSolicitudes = solicitudesQuery.data?.solicitudes.length ?? 0;
  const [bandejaAbierta, setBandejaAbierta] = React.useState(false);

  // Título legible de los docs de la línea (las tarjetas muestran el nombre del prompt).
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

  // ── Vista detalle: ocupa la página entera. Al cerrar (`doc` fuera de la URL) se
  //    vuelve a la pestaña de origen: la `vista` nunca se toca al abrir un doc. ──
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

  const maquinaActiva =
    vista === "investigacion" || vista === "produccion" || vista === "importacion"
      ? maquinaQuery.data?.maquinas.find((m) => m.id === vista)
      : undefined;

  return (
    <div className="flex h-full min-h-0 flex-col gap-4">
      {/* ───────── Header global (sobre las pestañas) ───────── */}
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            // Buscar es gestionar: la búsqueda vive en Documentos, no en las líneas.
            if (e.target.value && vista !== "documentos") irAVista("documentos");
          }}
          placeholder="Buscar documentos…"
          className="h-9 w-full sm:w-64"
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
              onClick={() => mutarParams({ vista: "documentos", filtro: "sin-publicar" })}
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

      {/* ───────── Pestañas principales ───────── */}
      <Tabs value={vista} onValueChange={(v) => irAVista(vistaDe(v))}>
        <TabsList>
          <TabsTrigger value="investigacion" title="El motor de noticias">
            {ETIQUETA_VISTA.investigacion}
          </TabsTrigger>
          <TabsTrigger value="produccion" title="La máquina de contenido">
            {ETIQUETA_VISTA.produccion}
          </TabsTrigger>
          <TabsTrigger value="importacion" title="Insumos del equipo">
            {ETIQUETA_VISTA.importacion}
          </TabsTrigger>
          <TabsTrigger value="estrategia" title="Configuración editorial">
            {ETIQUETA_VISTA.estrategia}
          </TabsTrigger>
          <TabsTrigger value="documentos" title="Gestión y búsqueda">
            {ETIQUETA_VISTA.documentos}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      {/* ───────── Vista activa ───────── */}
      {vista === "documentos" ? (
        <TablaDocumentos
          documentos={filtrados}
          cargando={docsQuery.isPending}
          soloSinPublicar={soloSinPublicar}
          onCambioSinPublicar={(v) => mutarParams({ filtro: v ? "sin-publicar" : null })}
          onAbrir={abrirDoc}
        />
      ) : vista === "estrategia" ? (
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          {esMultiMarca ? (
            <div className="mb-4">
              <SelectorMarca
                marcas={marcasParaSwitch}
                valor={marcaActiva ?? MARCA_TODAS}
                onCambio={(v) => cambiarMarca(marcaParam(v) ?? null)}
                incluirTodas={puedeTodas}
                className="w-[200px]"
                ariaLabel="Marca de la estrategia"
              />
            </div>
          ) : null}
          <EstrategiaMarca marca={marcaActiva ?? ""} onAbrirDoc={abrirDoc} />
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          {maquinaQuery.isError ? (
            <p className="text-sm text-muted-foreground">{mensajeError(maquinaQuery.error)}</p>
          ) : (
            <RielMaquina
              maquina={maquinaActiva}
              cargando={maquinaQuery.isPending}
              tituloDe={(id) => tituloPorId.get(id)}
              onAbrir={abrirDoc}
              onIrAEstrategia={
                vista === "produccion" ? () => irAVista("estrategia") : undefined
              }
            />
          )}
        </div>
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
