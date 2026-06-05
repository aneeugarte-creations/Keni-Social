/**
 * Cajones del día — insumos diarios del equipo AMX.
 *
 * El equipo vuelca material en 4 cajones (Portal/SMS, Corresponsales,
 * Reporteros y Eventos Claro). Haiku los parsea y produce ítems limpios,
 * ordenados y listos para llevar al tablero con un clic.
 *
 * Contrato: docs/maquina-contenido/01-insumos-del-dia.md
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Edit2,
  Inbox,
  Loader2,
  MapPin,
  Send,
  Trash2,
  UploadCloud,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { api, mensajeError } from "@/lib/api";
import type { CajonInsumo, CajonConItems, InsumoItem, InsumoLote } from "@/types";

// ── Constantes de los 4 cajones ───────────────────────────────────────────────

interface DescripcionCajon {
  id: CajonInsumo;
  titulo: string;
  descripcion: string;
  aceptaArchivo: string;
  placeholderTexto: string;
}

const CAJONES: DescripcionCajon[] = [
  {
    id: "portal",
    titulo: "Portal / SMS",
    descripcion: "Lista numerada de Portal o SMS (1.- TITULAR ... cuerpo).",
    aceptaArchivo: ".txt,.pdf",
    placeholderTexto: "Pega aquí la lista numerada de notas del portal o SMS...",
  },
  {
    id: "corresponsales",
    titulo: "Corresponsales",
    descripcion: 'El "así vamos": VOSOT ESTADO (REPORTERO) TITULAR - Tengo/Espero material y guión.',
    aceptaArchivo: ".txt,.pdf",
    placeholderTexto: "Pega aquí el resumen de corresponsales...",
  },
  {
    id: "reporteros",
    titulo: "Reporteros (agenda PDF)",
    descripcion: "PDF de agenda de coberturas (tabla con REPORTERO, HORA Y LUGAR, ASIGNACIÓN...).",
    aceptaArchivo: ".pdf",
    placeholderTexto: "O pega el texto exportado del PDF...",
  },
  {
    id: "eventos_claro",
    titulo: "Eventos Claro (Excel/CSV)",
    descripcion: "Excel o CSV de eventos y programación de TV de Claro Sports.",
    aceptaArchivo: ".xlsx,.xls,.csv",
    placeholderTexto: "O pega el contenido del CSV...",
  },
];

// ── Utilidades ────────────────────────────────────────────────────────────────

/** Hoy en ISO YYYY-MM-DD local. */
function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Convierte una fecha ISO a una etiqueta legible. */
function etiquetaFecha(fecha: string): string {
  if (!fecha) return "";
  try {
    return new Intl.DateTimeFormat("es-MX", {
      day: "numeric",
      month: "long",
      year: "numeric",
    }).format(new Date(`${fecha}T00:00:00`));
  } catch {
    return fecha;
  }
}

// ── Claves de React Query ─────────────────────────────────────────────────────

const CLAVE_INSUMOS = (fecha: string) => ["insumos", "listar", fecha] as const;
const CLAVE_DIAS = ["insumos", "dias"] as const;

// ── Componente: badge de estado de material ───────────────────────────────────

function BadgeEstadoMaterial({ estado }: { estado: InsumoItem["estado_material"] }) {
  if (!estado) return null;
  return (
    <Badge variant={estado === "tengo" ? "ok" : "aviso"} className="capitalize">
      {estado === "tengo" ? "Tengo" : "Espero"}
    </Badge>
  );
}

// ── Componente: dialogo de edición de ítem ────────────────────────────────────

interface PropsDialogoEditar {
  item: InsumoItem;
  abierto: boolean;
  onCerrar: () => void;
  onGuardado: (item: InsumoItem) => void;
}

function DialogoEditarItem({ item, abierto, onCerrar, onGuardado }: PropsDialogoEditar) {
  const [titulo, setTitulo] = React.useState(item.titulo);
  const [resumen, setResumen] = React.useState(item.resumen);
  const [linea, setLinea] = React.useState(item.linea);
  const [hora, setHora] = React.useState(item.hora);
  const [lugar, setLugar] = React.useState(item.lugar);
  const [estadoMaterial, setEstadoMaterial] = React.useState<InsumoItem["estado_material"]>(
    item.estado_material,
  );

  // Resincroniza cuando cambia el ítem (por si se abre con otro)
  React.useEffect(() => {
    setTitulo(item.titulo);
    setResumen(item.resumen);
    setLinea(item.linea);
    setHora(item.hora);
    setLugar(item.lugar);
    setEstadoMaterial(item.estado_material);
  }, [item]);

  const mutacion = useMutation({
    mutationFn: () =>
      api.insumos.editarItem(item.id, {
        titulo,
        resumen,
        linea,
        hora,
        lugar,
        estado_material: estadoMaterial,
      }),
    onSuccess: (resp) => {
      onGuardado(resp.item);
      onCerrar();
      toast.success("Ítem actualizado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={abierto} onOpenChange={(o) => { if (!o) onCerrar(); }}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Editar ítem</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label htmlFor="di-titulo">Título</Label>
            <Input
              id="di-titulo"
              value={titulo}
              onChange={(e) => setTitulo(e.target.value)}
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="di-resumen">Resumen</Label>
            <Textarea
              id="di-resumen"
              value={resumen}
              onChange={(e) => setResumen(e.target.value)}
              rows={3}
              className="mt-1"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="di-linea">Línea</Label>
              <Input
                id="di-linea"
                value={linea}
                onChange={(e) => setLinea(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="di-em">Estado material</Label>
              <Select
                value={estadoMaterial || "__vacio__"}
                onValueChange={(v) =>
                  setEstadoMaterial(v === "__vacio__" ? "" : (v as "tengo" | "espero"))
                }
              >
                <SelectTrigger id="di-em" className="mt-1">
                  <SelectValue placeholder="—" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__vacio__">—</SelectItem>
                  <SelectItem value="tengo">Tengo</SelectItem>
                  <SelectItem value="espero">Espero</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label htmlFor="di-hora">Hora</Label>
              <Input
                id="di-hora"
                value={hora}
                onChange={(e) => setHora(e.target.value)}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="di-lugar">Lugar</Label>
              <Input
                id="di-lugar"
                value={lugar}
                onChange={(e) => setLugar(e.target.value)}
                className="mt-1"
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={mutacion.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => mutacion.mutate()} disabled={mutacion.isPending}>
            {mutacion.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Componente: tarjeta de un ítem parseado ───────────────────────────────────

interface PropsItemCard {
  item: InsumoItem;
  fecha: string;
}

function ItemCard({ item, fecha }: PropsItemCard) {
  const queryClient = useQueryClient();
  const [editando, setEditando] = React.useState(false);

  const usarMut = useMutation({
    mutationFn: () => api.insumos.usarItem(item.id, { generar: true }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS(fecha) });
      toast.success("Ítem llevado al tablero.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function onGuardado() {
    void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS(fecha) });
  }

  return (
    <>
      <div
        className={`rounded-md border p-3 text-sm ${item.usado ? "bg-muted/40" : "bg-card"}`}
        data-testid="insumo-item"
      >
        <div className="flex items-start justify-between gap-2">
          <p className="font-medium leading-snug">{item.titulo || "(sin título)"}</p>
          <div className="flex shrink-0 items-center gap-1">
            {!item.usado && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs"
                  onClick={() => setEditando(true)}
                  aria-label="Editar ítem"
                >
                  <Edit2 className="h-3 w-3" />
                </Button>
                <Button
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  onClick={() => usarMut.mutate()}
                  disabled={usarMut.isPending}
                  aria-label="Llevar al tablero"
                >
                  {usarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Send className="h-3 w-3" />
                  )}
                  Llevar al tablero
                </Button>
              </>
            )}
            {item.usado && (
              <Badge variant="ok" className="gap-1">
                <CheckCircle2 className="h-3 w-3" />
                En tablero
              </Badge>
            )}
          </div>
        </div>

        {item.resumen && (
          <p className="mt-1 text-muted-foreground">{item.resumen}</p>
        )}

        <div className="mt-2 flex flex-wrap gap-1.5">
          {item.marca_nombre && (
            <Badge variant="secondary">{item.marca_nombre}</Badge>
          )}
          {item.linea && (
            <Badge variant="outline">{item.linea}</Badge>
          )}
          {(item.hora || item.lugar) && (
            <Badge variant="outline" className="gap-1">
              <MapPin className="h-3 w-3" />
              {[item.hora, item.lugar].filter(Boolean).join(" · ")}
            </Badge>
          )}
          <BadgeEstadoMaterial estado={item.estado_material} />
        </div>
      </div>

      {editando && (
        <DialogoEditarItem
          item={item}
          abierto={editando}
          onCerrar={() => setEditando(false)}
          onGuardado={() => {
            setEditando(false);
            onGuardado();
          }}
        />
      )}
    </>
  );
}

// ── Componente: tarjeta de cajón ──────────────────────────────────────────────

interface PropsTarjetaCajon {
  def: DescripcionCajon;
  datos: CajonConItems | undefined;
  fecha: string;
}

function TarjetaCajon({ def, datos, fecha }: PropsTarjetaCajon) {
  const queryClient = useQueryClient();
  const [texto, setTexto] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const archivoRef = React.useRef<HTMLInputElement>(null);

  const aportarMut = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.set("cajon", def.id);
      form.set("fecha", fecha);
      if (texto.trim()) form.set("texto", texto.trim());
      if (archivo) form.set("archivo", archivo);
      return api.insumos.aportar(form);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS(fecha) });
      setTexto("");
      setArchivo(null);
      if (archivoRef.current) archivoRef.current.value = "";
      toast.success(`Cajón "${def.titulo}" procesado.`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrarLoteMut = useMutation({
    mutationFn: (id: string) => api.insumos.borrarLote(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS(fecha) });
      toast.success("Lote eliminado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const items = datos?.items ?? [];
  const lotes = datos?.lotes ?? [];

  // Lotes con error para mostrar aviso
  const lotesError = lotes.filter((l) => l.estado === "error");

  const puedeEnviar = (texto.trim().length > 0 || archivo !== null) && !aportarMut.isPending;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Inbox className="h-4 w-4 text-muted-foreground" />
          {def.titulo}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{def.descripcion}</p>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Zona de entrada */}
        <Textarea
          placeholder={def.placeholderTexto}
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          rows={4}
          aria-label={`Texto para ${def.titulo}`}
        />
        <div className="flex items-center gap-2">
          <Input
            ref={archivoRef}
            type="file"
            accept={def.aceptaArchivo}
            onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
            className="flex-1 text-xs"
            aria-label={`Archivo para ${def.titulo}`}
          />
          <Button
            size="sm"
            className="shrink-0 gap-1"
            onClick={() => aportarMut.mutate()}
            disabled={!puedeEnviar}
            aria-label={`Procesar ${def.titulo}`}
          >
            {aportarMut.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <UploadCloud className="h-4 w-4" />
            )}
            {aportarMut.isPending ? "Procesando…" : "Procesar"}
          </Button>
        </div>

        {/* Errores de lotes */}
        {lotesError.map((l) => (
          <div
            key={l.id}
            className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 p-2 text-xs text-destructive"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span className="flex-1">{l.error || "Error al parsear el lote."}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
              onClick={() => borrarLoteMut.mutate(l.id)}
              disabled={borrarLoteMut.isPending}
              aria-label="Borrar lote con error"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        ))}

        {/* Ítems parseados */}
        {items.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted-foreground">
                {items.length} ítem{items.length !== 1 ? "s" : ""}
              </p>
              {/* Botón de borrar lote completo (solo si hay lotes listo/no-error) */}
              {lotes.filter((l) => l.estado === "listo").map((l: InsumoLote) => (
                <Button
                  key={l.id}
                  size="sm"
                  variant="ghost"
                  className="h-6 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
                  onClick={() => borrarLoteMut.mutate(l.id)}
                  disabled={borrarLoteMut.isPending}
                  aria-label={`Borrar lote ${l.id}`}
                >
                  <Trash2 className="h-3 w-3" />
                  Borrar lote
                </Button>
              ))}
            </div>
            <div className="space-y-2">
              {items.map((item) => (
                <ItemCard key={item.id} item={item} fecha={fecha} />
              ))}
            </div>
          </div>
        )}

        {items.length === 0 && lotes.length === 0 && (
          <p className="py-2 text-center text-xs text-muted-foreground">
            Sin insumos para este cajón en la fecha seleccionada.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function CajonesDia() {
  const [fecha, setFecha] = React.useState<string>(hoyIso);

  // Días con insumos registrados (para el selector de historial)
  const diasQuery = useQuery({
    queryKey: CLAVE_DIAS,
    queryFn: ({ signal }) => api.insumos.dias(signal),
    staleTime: 2 * 60 * 1000,
  });

  // Datos del día seleccionado
  const insumosQuery = useQuery({
    queryKey: CLAVE_INSUMOS(fecha),
    queryFn: ({ signal }) => api.insumos.listar(fecha, signal),
    staleTime: 30 * 1000,
  });

  // Indexar cajones por id para acceso rápido
  const cajonPorId = React.useMemo<Partial<Record<CajonInsumo, CajonConItems>>>(() => {
    const m: Partial<Record<CajonInsumo, CajonConItems>> = {};
    for (const c of insumosQuery.data?.cajones ?? []) {
      m[c.cajon] = c;
    }
    return m;
  }, [insumosQuery.data]);

  return (
    <>
      <PageHeader
        titulo="Cajones del día"
        descripcion="Vuelca el material diario en cada cajón y Haiku lo parsea y ordena. Luego lleva los ítems al tablero con un clic."
      />

      {/* Controles de fecha e historial */}
      <div className="mb-6 flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="cd-fecha" className="text-xs text-muted-foreground">
            Día editorial
          </Label>
          <Input
            id="cd-fecha"
            type="date"
            value={fecha}
            onChange={(e) => setFecha(e.target.value || hoyIso())}
            className="w-40"
            aria-label="Seleccionar fecha"
          />
        </div>

        {/* Selector de historial */}
        {diasQuery.data && diasQuery.data.dias.length > 0 && (
          <div className="space-y-1">
            <Label htmlFor="cd-historial" className="text-xs text-muted-foreground">
              Historial
            </Label>
            <Select
              value={fecha}
              onValueChange={(v) => setFecha(v)}
            >
              <SelectTrigger id="cd-historial" className="w-52" aria-label="Historial de días">
                <Calendar className="h-4 w-4" />
                <SelectValue placeholder="Ver día pasado…" />
              </SelectTrigger>
              <SelectContent>
                {diasQuery.data.dias.map((d) => (
                  <SelectItem key={d.fecha} value={d.fecha}>
                    {etiquetaFecha(d.fecha)} — {d.total} ítem{d.total !== 1 ? "s" : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* Error de carga */}
      {insumosQuery.isError && (
        <BloqueError
          titulo="No se pudieron cargar los insumos"
          mensaje={mensajeError(insumosQuery.error)}
          onReintentar={() => void insumosQuery.refetch()}
        />
      )}

      {/* Esqueleto de carga */}
      {insumosQuery.isLoading && (
        <div className="grid gap-4 sm:grid-cols-2">
          {CAJONES.map((c) => (
            <Skeleton key={c.id} className="h-64 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* 4 cajones */}
      {!insumosQuery.isLoading && !insumosQuery.isError && (
        <div className="grid gap-4 sm:grid-cols-2">
          {CAJONES.map((def) => (
            <TarjetaCajon
              key={def.id}
              def={def}
              datos={cajonPorId[def.id]}
              fecha={fecha}
            />
          ))}
        </div>
      )}
    </>
  );
}
