/**
 * Cajones del día — insumos diarios del equipo de redes.
 *
 * El equipo vuelca material en los cajones del día (UnoTV: Portal/SMS, Corresponsales,
 * Reporteros, Eventos Claro · Claro Sports: Notas, Indicaciones). Haiku los parsea y produce ítems limpios,
 * ordenados y listos para curar: el auto-feed lleva las historias relevantes
 * al feed automáticamente; aquí se descarta lo que no sirva o se empuja algo
 * de inmediato con "Empujar ya".
 *
 * Contrato: docs/maquina-contenido/01-insumos-del-dia.md
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Calendar,
  CalendarPlus,
  CheckCircle2,
  Clock,
  Edit2,
  EyeOff,
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
import { confirmar } from "@/components/comunes/confirmar";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useGeneracion } from "@/hooks/use-generacion";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { hoyCDMX } from "@/lib/fecha";
import { ProgresoGeneracion } from "@/components/generaciones/ProgresoGeneracion";
import type { CajonInsumo, CajonConItems, InsumoItem, InsumoLote } from "@/types";

// ── Constantes de los 4 cajones ───────────────────────────────────────────────

interface DescripcionCajon {
  id: CajonInsumo;
  titulo: string;
  descripcion: string;
  aceptaArchivo: string;
  placeholderTexto: string;
  /**
   * Marca (id canónico) a la que pertenece el cajón: cada buzón es de UNA marca. Portal/SMS,
   * Corresponsales y Reporteros son de UnoTV; Eventos Claro (la parrilla), Notas y las
   * Indicaciones son de Claro Sports. Los cajones visibles se filtran por la marca activa del
   * switch global (en "Todas" se ven todos).
   */
  marca: string;
}

const CAJONES: DescripcionCajon[] = [
  {
    id: "portal",
    titulo: "Portal / SMS",
    descripcion: "Lista numerada de Portal o SMS (1.- TITULAR ... cuerpo).",
    aceptaArchivo: ".txt,.pdf",
    placeholderTexto: "Pega aquí la lista numerada de notas del portal o SMS...",
    marca: "unotv",
  },
  {
    id: "corresponsales",
    titulo: "Corresponsales",
    descripcion: 'El "así vamos": VOSOT ESTADO (REPORTERO) TITULAR - Tengo/Espero material y guión.',
    aceptaArchivo: ".txt,.pdf",
    placeholderTexto: "Pega aquí el resumen de corresponsales...",
    marca: "unotv",
  },
  {
    id: "reporteros",
    titulo: "Reporteros (agenda PDF)",
    descripcion: "PDF de agenda de coberturas (tabla con REPORTERO, HORA Y LUGAR, ASIGNACIÓN...).",
    aceptaArchivo: ".pdf",
    placeholderTexto: "O pega el texto exportado del PDF...",
    marca: "unotv",
  },
  {
    id: "eventos_claro",
    titulo: "Eventos Claro (Excel/CSV)",
    descripcion: "",
    aceptaArchivo: ".xlsx,.xls,.csv",
    placeholderTexto: "O pega el contenido del CSV...",
    marca: "claro-sports",
  },
  {
    id: "notas",
    titulo: "Notas y links",
    descripcion: "Volcado de WhatsApp: notas, links, tweets, texto de PDFs. Una pieza por noticia.",
    aceptaArchivo: ".txt,.pdf",
    placeholderTexto: "Pega aquí lo del grupo de WhatsApp (notas, links, tweets)...",
    marca: "claro-sports",
  },
  {
    id: "contexto",
    titulo: "Indicaciones",
    descripcion: "",
    aceptaArchivo: ".txt",
    placeholderTexto: "Pega aquí las indicaciones o correcciones (no se publican)...",
    marca: "claro-sports",
  },
];

// ── Utilidades ────────────────────────────────────────────────────────────────

/** Hoy en ISO YYYY-MM-DD, en zona CDMX. */
function hoyIso(): string {
  return hoyCDMX();
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

/** Clave completa para una combinación fecha+filtro+marca. */
const CLAVE_INSUMOS = (fecha: string, soloFrescos: boolean, marca: string | null) =>
  ["insumos", "listar", fecha, soloFrescos, marca ?? ""] as const;
/** Prefijo para invalidar todas las variantes de un día (independientemente del filtro). */
const CLAVE_INSUMOS_PREFIJO = (fecha: string) => ["insumos", "listar", fecha] as const;
const CLAVE_DIAS = ["insumos", "dias"] as const;

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

  // Resincroniza cuando cambia el ítem (por si se abre con otro)
  React.useEffect(() => {
    setTitulo(item.titulo);
    setResumen(item.resumen);
    setLinea(item.linea);
    setHora(item.hora);
    setLugar(item.lugar);
  }, [item]);

  const mutacion = useMutation({
    mutationFn: () =>
      api.insumos.editarItem(item.id, {
        titulo,
        resumen,
        linea,
        hora,
        lugar,
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
          <div>
            <Label htmlFor="di-linea">Línea</Label>
            <Input
              id="di-linea"
              value={linea}
              onChange={(e) => setLinea(e.target.value)}
              className="mt-1"
            />
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
  const esCaducado = item.frescura === "caduco";
  // Los ítems del cajón Eventos Claro (programación de TV) se convierten en EVENTOS de
  // la rota (no en piezas del feed): muestran "Crear evento" en vez de "Enviar al feed".
  // El evento creado se gestiona luego en Fuentes › Eventos.
  const esEvento = item.cajon === "eventos_claro" || item.tipo === "evento";
  // Las indicaciones (cajón contexto) son guía editorial: no van al tablero ni al feed. Se
  // muestran como referencia, sin acción de publicar (el back las frena con un backstop 400).
  const esContexto = item.tipo === "contexto";

  const usarMut = useMutation({
    mutationFn: () => api.insumos.usarItem(item.id, { generar: true }),
    onSuccess: (resp) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
      // Toast HONESTO: solo prometemos "Copy en marcha" si el back confirma que el job
      // arrancó (`copy_en_proceso`). Si la pieza se creó pero el copy NO se lanzó (p. ej.
      // ítem sin marca), avisamos para que se relance desde la pieza en vez de mentir.
      if (resp.copy_en_proceso) {
        toast.success("Copy en marcha");
      } else {
        toast.warning("Pieza creada en el feed; el copy no arrancó: lánzalo desde la pieza.");
      }
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const crearEventoMut = useMutation({
    mutationFn: () => api.insumos.crearEvento(item.id, {}),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
      toast.success("Evento creado en la rota.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Descarte por ítem (lo que promete el explainer): borra el apunte y el back
  // aparta su gemela del pool para que el auto-feed no la convierta en pieza.
  const descartarMut = useMutation({
    mutationFn: () => api.insumos.descartarItem(item.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
      toast.success("Ítem descartado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function onGuardado() {
    void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
  }

  return (
    <>
      <div
        className={`rounded-md border p-3 text-sm ${item.usado ? "bg-muted/40" : esCaducado ? "bg-amber-50/60 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800" : "bg-card"}`}
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
                  variant="outline"
                  className="h-7 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
                  onClick={async () => {
                    // Confirmación ligera: el descarte borra el apunte (la gemela del
                    // pool se aparta en el back para que el auto-feed no la recoja).
                    if (
                      await confirmar({
                        mensaje: `¿Descartar "${item.titulo || "(sin título)"}"?`,
                        destructivo: true,
                        textoConfirmar: "Descartar",
                      })
                    )
                      descartarMut.mutate();
                  }}
                  disabled={descartarMut.isPending}
                  aria-label="Descartar ítem"
                  title="Descartar (no entra al feed)"
                >
                  {descartarMut.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <Trash2 className="h-3 w-3" />
                  )}
                </Button>
                {esContexto ? (
                  // Vigencia de 7 días: el back marca `indicacion_vigente=false` cuando la guía
                  // caducó. `undefined` (campo opcional, aún sin desplegar) cuenta como vigente.
                  item.indicacion_vigente === false ? (
                    <Badge
                      variant="outline"
                      className="text-xs text-muted-foreground opacity-70"
                      title="Ya no guía el copy: vuelve a pegarla para reactivarla."
                    >
                      Caducada
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-xs"
                      title="Guía al equipo y a la IA al redactar (no se publica). Caduca a los 7 días."
                    >
                      Guía
                    </Badge>
                  )
                ) : esEvento ? (
                  <Button
                    size="sm"
                    className="h-7 gap-1 px-2 text-xs"
                    onClick={() => crearEventoMut.mutate()}
                    disabled={crearEventoMut.isPending}
                    aria-label="Crear evento"
                  >
                    {crearEventoMut.isPending ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <CalendarPlus className="h-3 w-3" />
                    )}
                    Crear evento
                  </Button>
                ) : (
                  <>
                    <Badge variant="secondary" className="text-xs">En el pool</Badge>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-7 gap-1 px-2 text-xs text-muted-foreground"
                      onClick={() => usarMut.mutate()}
                      disabled={usarMut.isPending}
                      aria-label="Empujar ya (fuerza al feed)"
                      title="Forzar al feed ahora"
                    >
                      {usarMut.isPending ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Send className="h-3 w-3" />
                      )}
                      Empujar ya
                    </Button>
                  </>
                )}
              </>
            )}
            {item.usado && esEvento && (
              <Badge variant="ok" className="gap-1">
                <CheckCircle2 className="h-3 w-3" />
                Evento creado
              </Badge>
            )}
            {/* Badge HONESTO de la pieza (lo deriva el back, igual que en el pool de
                noticias): "usado" = pieza creada, no necesariamente visible en el feed. */}
            {item.usado && !esEvento && (
              item.pieza_estado === "generando" ? (
                <Badge
                  variant="aviso"
                  className="gap-1"
                >
                  <Loader2 className="h-3 w-3 animate-spin" />
                  Generando…
                </Badge>
              ) : item.pieza_estado === "en_cola" ? (
                <Badge
                  variant="aviso"
                  className="gap-1"
                  title="Pieza en cola, esperando copy"
                >
                  <Clock className="h-3 w-3" />
                  En cola
                </Badge>
              ) : (
                <Badge variant="ok" className="gap-1">
                  <CheckCircle2 className="h-3 w-3" />
                  En el feed
                </Badge>
              )
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
          {esCaducado && (
            <Badge
              variant="aviso"
              className="gap-1"
              data-testid="badge-caducado"
            >
              <EyeOff className="h-3 w-3" />
              Caducado
            </Badge>
          )}
          {(item.hora || item.lugar) && (
            <Badge variant="outline" className="gap-1">
              <MapPin className="h-3 w-3" />
              {[item.hora, item.lugar].filter(Boolean).join(" · ")}
            </Badge>
          )}
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
  // Marca activa global: se estampa en el lote al aportar para que los ítems sin
  // marca reconocida por la IA hereden la marca del contexto (y el filtro por marca
  // del cajón los encuentre, en vez de dejarlos "sueltos" fuera de toda marca).
  const { marcaActiva } = useMarcaActiva();
  const [texto, setTexto] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const archivoRef = React.useRef<HTMLInputElement>(null);

  // Seguimiento de la generación en curso (el worker parsea el cajón con IA).
  const { generacion: genActual, ejecutando: genEjecutando, iniciar: iniciarGen, cancelar: cancelarGen, cancelando: cancelandoGen } = useGeneracion();

  const aportarMut = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.set("cajon", def.id);
      form.set("fecha", fecha);
      // Marca del lote: la activa del switch global; en "Todas" (null, admin) cae a la
      // marca DUEÑA del cajón (cada buzón es de una marca), no a un lote sin marca cuyos
      // ítems quedarían sueltos del filtro por marca.
      form.set("marca", marcaActiva ?? def.marca);
      if (texto.trim()) form.set("texto", texto.trim());
      if (archivo) form.set("archivo", archivo);
      return api.insumos.aportar(form);
    },
    onSuccess: (data) => {
      // El parseo corre ASÍNCRONO en el worker: el lote nace "parseando". Si el back
      // devuelve la generación, arrancamos el sondeo para mostrar el stream en vivo.
      if (data.generacion) iniciarGen(data.generacion);
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
      setTexto("");
      setArchivo(null);
      if (archivoRef.current) archivoRef.current.value = "";
      toast.success(`Cajón "${def.titulo}" en proceso…`);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Al completarse la generación, refrescamos para que aparezcan los ítems parseados.
  React.useEffect(() => {
    if (!genActual || genEjecutando) return;
    if (genActual.estado === "completado" || genActual.estado === "error") {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [genActual?.estado, genEjecutando]);

  const borrarLoteMut = useMutation({
    mutationFn: (id: string) => api.insumos.borrarLote(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_INSUMOS_PREFIJO(fecha) });
      toast.success("Lote eliminado.");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const items = datos?.items ?? [];
  const lotes = datos?.lotes ?? [];

  // Lotes con error para mostrar aviso
  const lotesError = lotes.filter((l) => l.estado === "error");
  // Lotes realmente en proceso: el worker aún corre Haiku y todavía no insertó ítems.
  // Un lote `parseando` que YA tiene ítems está ATASCADO (el worker murió entre el INSERT de
  // los ítems y el UPDATE final del lote): el parseo SÍ produjo resultado, así que NO
  // mostramos "Procesando con Haiku…" por él (antes se quedaba atascado para siempre). El
  // limpiador del back lo reconciliará a `listo`. Comparamos por `lote_id` de los ítems.
  const idsLotesConItems = new Set(items.map((it) => it.lote_id));
  const lotesParseando = lotes.filter(
    (l) => l.estado === "parseando" && !idsLotesConItems.has(l.id),
  );

  const puedeEnviar = (texto.trim().length > 0 || archivo !== null) && !aportarMut.isPending;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <Inbox className="h-4 w-4 text-muted-foreground" />
          {def.titulo}
        </CardTitle>
        {def.descripcion && (
          <p className="text-xs text-muted-foreground">{def.descripcion}</p>
        )}
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

        {/* Lotes en proceso (el worker corre Haiku; mostramos el stream en vivo si está disponible) */}
        {lotesParseando.map((l) => (
          <div
            key={l.id}
            className="rounded-md border bg-muted/40 p-2 text-xs text-muted-foreground"
            data-testid="lote-parseando"
          >
            {genActual && genEjecutando ? (
              <div className="space-y-2">
                <p className="flex items-center gap-2 font-medium">
                  <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                  Procesando con IA…
                </p>
                <ProgresoGeneracion
                  generacion={genActual}
                  onCancelar={cancelarGen}
                  cancelando={cancelandoGen}
                />
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" />
                <span className="flex-1">Procesando con Haiku…</span>
              </div>
            )}
          </div>
        ))}

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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-medium text-muted-foreground">
                {items.length} ítem{items.length !== 1 ? "s" : ""}
              </p>
              {/* Botón de borrar lote completo (solo lotes terminales `listo`). Van en su
                  propio contenedor con `flex-wrap`: si hay varios lotes (p.ej. tras reenvíos),
                  los botones BAJAN de línea en vez de salirse por el lateral de la pantalla. */}
              {lotes.some((l) => l.estado === "listo") && (
                <div className="flex flex-wrap justify-end gap-1">
                  {lotes.filter((l) => l.estado === "listo").map((l: InsumoLote) => (
                    <Button
                      key={l.id}
                      size="sm"
                      variant="ghost"
                      className="h-6 shrink-0 gap-1 px-2 text-xs text-muted-foreground hover:text-destructive"
                      onClick={async () => {
                        // Borrar un lote arrastra TODOS sus apuntes (también los no usados):
                        // confirmación explícita antes del destructivo.
                        if (
                          await confirmar({
                            mensaje:
                              "¿Borrar este lote y todos sus apuntes?",
                            destructivo: true,
                            textoConfirmar: "Borrar lote",
                          })
                        )
                          borrarLoteMut.mutate(l.id);
                      }}
                      disabled={borrarLoteMut.isPending}
                      aria-label={`Borrar lote ${l.id}`}
                    >
                      <Trash2 className="h-3 w-3" />
                      Borrar lote
                    </Button>
                  ))}
                </div>
              )}
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
            Sin insumos
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function CajonesDia() {
  const { marcaActiva } = useMarcaActiva();
  const [fecha, setFecha] = React.useState<string>(hoyIso);
  // Default ON: ocultar caducados (especialmente útil para UnoTV)
  const [ocultarCaducados, setOcultarCaducados] = React.useState(true);

  // Días con insumos registrados (para el selector de historial)
  const diasQuery = useQuery({
    queryKey: CLAVE_DIAS,
    queryFn: ({ signal }) => api.insumos.dias(signal),
    staleTime: 2 * 60 * 1000,
  });

  // Datos del día seleccionado — filtrados por la marca activa (null = todas).
  // SONDEO: mientras haya lotes REALMENTE en proceso (parseando y SIN ítems aún), refrescamos
  // cada ~1.5 s para que los ítems aparezcan en cuanto el lote pase a "listo"/"error". Un lote
  // `parseando` que ya tiene ítems está ATASCADO (worker muerto a medias): no seguimos sondeando
  // por él indefinidamente (el limpiador del back lo reconcilia). Misma lógica que `lotesParseando`.
  const insumosQuery = useQuery({
    queryKey: CLAVE_INSUMOS(fecha, ocultarCaducados, marcaActiva),
    queryFn: ({ signal }) =>
      api.insumos.listar(fecha, signal, ocultarCaducados, marcaActiva ?? undefined),
    staleTime: 30 * 1000,
    refetchInterval: (q) =>
      (q.state.data?.cajones ?? []).some((c) => {
        const conItems = new Set(c.items.map((it) => it.lote_id));
        return c.lotes.some((l) => l.estado === "parseando" && !conItems.has(l.id));
      })
        ? 1500
        : false,
  });

  // Indexar cajones por id para acceso rápido
  const cajonPorId = React.useMemo<Partial<Record<CajonInsumo, CajonConItems>>>(() => {
    const m: Partial<Record<CajonInsumo, CajonConItems>> = {};
    for (const c of insumosQuery.data?.cajones ?? []) {
      m[c.cajon] = c;
    }
    return m;
  }, [insumosQuery.data]);

  // Cajones visibles según la marca activa del switch global: cada buzón es de UNA marca
  // (Portal/SMS, Corresponsales, Reporteros → UnoTV; Eventos Claro → Claro Sports). En "Todas"
  // (`marcaActiva === null`, admin) se ven todos.
  const cajonesVisibles = React.useMemo(
    () => (marcaActiva ? CAJONES.filter((c) => c.marca === marcaActiva) : CAJONES),
    [marcaActiva],
  );

  return (
    <>
      {/* Sección embebida en Fuentes → Internas: encabezado ligero (no es una página). */}
      <h2 className="mb-1 text-base font-semibold tracking-tight">Cajones del día</h2>

      {/* Explainer del pool */}
      <p className="mb-4 text-xs text-muted-foreground">
        Descarta insumos o empuja historias ya.
      </p>

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

        {/* Toggle: ocultar caducados */}
        <div className="flex items-center gap-2 ml-auto">
          <Switch
            id="cd-ocultar-caducados"
            checked={ocultarCaducados}
            onCheckedChange={setOcultarCaducados}
            aria-label="Ocultar caducados"
          />
          <Label
            htmlFor="cd-ocultar-caducados"
            className="flex items-center gap-1 cursor-pointer text-sm"
          >
            <EyeOff className="h-3.5 w-3.5 text-muted-foreground" />
            Ocultar caducados
          </Label>
        </div>
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
          {cajonesVisibles.map((c) => (
            <Skeleton key={c.id} className="h-64 w-full rounded-lg" />
          ))}
        </div>
      )}

      {/* Cajones de la marca activa */}
      {!insumosQuery.isLoading && !insumosQuery.isError && (
        <div className="grid gap-4 sm:grid-cols-2">
          {cajonesVisibles.map((def) => (
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
