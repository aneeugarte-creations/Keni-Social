import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Check, Link2, ListChecks, Loader2, Sparkles, Upload } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { usePropuestaParrilla } from "@/hooks/use-propuesta-parrilla";
import { api, mensajeError } from "@/lib/api";
import { formatearFecha } from "@/lib/fecha";
import { cn } from "@/lib/utils";
import type { CatalogosContenido, OperacionCrearEvento, OperacionCrearTarea } from "@/types";

import { CLAVE_TAREAS } from "./claves";

const SIN_RESPONSABLE = "__libre__";

type Modo = "evento" | "tarea";

const esUrl = (s: string) => /^https?:\/\/\S+/i.test(s.trim());

/**
 * Añadir a la lista de Tareas:
 *  - Evento: pega un ENLACE, suelta/sube un DOCUMENTO o PDF (Excel/imagen también), o
 *    escribe una FRASE y la IA propone los eventos → revisas → «Aceptar» los crea. O
 *    escríbelo a mano (un solo evento). Sirve para cualquier cosa: partido, concierto,
 *    rueda de prensa, estreno…
 *  - Tarea: un encargo suelto (sin evento), que puedes asignar a alguien ahí mismo. Igual que
 *    Evento, acepta la MISMA caja inteligente (pega enlace / sube documento / escribe frase y la
 *    IA propone las tareas → revisas → «Aceptar»), pero el modo `tareas` extrae ENCARGOS, no
 *    eventos. NO va al calendario de Turnos; vive solo en el tablero de Cobertura (Panorama / Mis tareas).
 *
 * La diferencia es de DESTINO: un evento es una unidad de cobertura con fecha/hora que
 * cae en la rejilla del calendario (`crearEventoRota`); una tarea es trabajo suelto que
 * el equipo coge o se reparte (`crearContenido`, clase='tarea'), nunca en el calendario.
 */
export function DialogoCrearTarea({
  abierto,
  onOpenChange,
  catalogos,
  marca,
}: {
  abierto: boolean;
  onOpenChange: (abierto: boolean) => void;
  catalogos: CatalogosContenido | undefined;
  marca: string | undefined;
}) {
  const queryClient = useQueryClient();
  const [modo, setModo] = React.useState<Modo>("evento");
  const [arrastrando, setArrastrando] = React.useState(false);
  // Manual.
  const [titulo, setTitulo] = React.useState("");
  const [fecha, setFecha] = React.useState("");
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [prioridad, setPrioridad] = React.useState("media");
  const [responsable, setResponsable] = React.useState(SIN_RESPONSABLE);
  // Import inteligente.
  const [pegado, setPegado] = React.useState("");
  const [archivo, setArchivo] = React.useState<File | null>(null);
  const [propuestaId, setPropuestaId] = React.useState<string | null>(null);

  const usuarios = catalogos?.usuarios ?? [];
  const prioridades = catalogos?.prioridades ?? ["alta", "media", "baja"];

  const { propuesta, generando } = usePropuestaParrilla(propuestaId);
  const ops = propuesta?.operaciones ?? [];
  // La IA propone eventos (modo Evento) o tareas (modo Tarea); filtramos por el tipo del modo.
  const eventosPropuestos = ops.filter(
    (o): o is OperacionCrearEvento => o.tipo === "crear_evento",
  );
  const tareasPropuestas = ops.filter(
    (o): o is OperacionCrearTarea => o.tipo === "crear_tarea",
  );
  const propuestos: (OperacionCrearEvento | OperacionCrearTarea)[] =
    modo === "evento" ? eventosPropuestos : tareasPropuestas;
  const etiquetaTipo = modo === "evento" ? "evento" : "tarea";

  const reiniciar = () => {
    setTitulo("");
    setFecha("");
    setHora("");
    setContenido("");
    setPrioridad("media");
    setResponsable(SIN_RESPONSABLE);
    setPegado("");
    setArchivo(null);
    setArrastrando(false);
    setPropuestaId(null);
  };
  const cerrar = () => {
    reiniciar();
    onOpenChange(false);
  };

  // --- Import: analizar (pega enlace/texto o sube documento) → propuesta ---
  const analizar = useMutation({
    mutationFn: async () => {
      const texto = pegado.trim();
      const res = await api.importarEventos({
        archivo: archivo ?? undefined,
        url: !archivo && esUrl(texto) ? texto : undefined,
        texto: !archivo && texto && !esUrl(texto) ? texto : undefined,
        marca: marca || undefined,
        modo: modo === "tarea" ? "tareas" : "eventos",
      });
      return res.propuesta_id;
    },
    onSuccess: (id) => setPropuestaId(id),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const aceptar = useMutation({
    mutationFn: () => api.aplicarPropuestaParrilla(propuestaId!),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      const n = propuestos.length;
      const plural = modo === "evento" ? "eventos añadidos" : "tareas añadidas";
      const singular = modo === "evento" ? "evento añadido" : "tarea añadida";
      toast.success(`${n} ${n === 1 ? singular : plural} a la lista.`);
      cerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  const descartar = useMutation({
    mutationFn: () => api.descartarPropuestaParrilla(propuestaId!),
    onSuccess: () => setPropuestaId(null),
    onError: (e) => toast.error(mensajeError(e)),
  });

  // --- Manual: crear un evento (calendario) o una tarea (solo tablero) ---
  const crear = useMutation({
    mutationFn: async () => {
      if (modo === "evento") {
        await api.crearEventoRota({
          titulo: titulo.trim(),
          fecha,
          hora: hora || undefined,
          contenido: contenido.trim() || undefined,
          prioridad: prioridad as never,
          tipo_cobertura: "transmision",
          marca: marca || undefined,
        });
        return;
      }
      await api.crearContenido({
        clase: "tarea",
        titulo: titulo.trim(),
        descripcion: contenido.trim() || undefined,
        prioridad: prioridad as never,
        fecha_objetivo: fecha || undefined,
        responsable_id: responsable === SIN_RESPONSABLE ? undefined : responsable,
        marca: marca || undefined,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_TAREAS });
      toast.success(
        modo === "evento"
          ? `"${titulo.trim()}" añadido: está en «Por cubrir».`
          : `"${titulo.trim()}" creado.`,
      );
      cerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const incompletoManual = !titulo.trim() || (modo === "evento" && !fecha);
  const nadaQueAnalizar = !archivo && !pegado.trim();
  const enRevision = propuestaId !== null;

  // Selectores reutilizados: en evento la prioridad cabalga junto a Día/Hora (una fila
  // menos = el diálogo entra sin scroll); en tarea va junto a la fecha.
  const campoPrioridad = (
    <div className="space-y-1.5">
      <Label>Prioridad</Label>
      <Select value={prioridad} onValueChange={setPrioridad}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {prioridades.map((p) => (
            <SelectItem key={p} value={p}>
              {p.charAt(0).toUpperCase() + p.slice(1)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
  const campoResponsable = (
    <div className="space-y-1.5">
      <Label>Asignar a</Label>
      <Select value={responsable} onValueChange={setResponsable}>
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={SIN_RESPONSABLE}>Por coger</SelectItem>
          {usuarios.map((u) => (
            <SelectItem key={u.id} value={u.id}>
              {u.usuario}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );

  return (
    <Dialog open={abierto} onOpenChange={(o) => (o ? onOpenChange(o) : cerrar())}>
      <DialogContent className="gap-3">
        <DialogHeader>
          <DialogTitle>Añadir a la lista</DialogTitle>
        </DialogHeader>

        {/* Revisión de la propuesta del import (ocupa el diálogo mientras está activa). */}
        {enRevision ? (
          <div className="space-y-3">
            {generando || !propuesta ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Analizando… esto puede tardar un momento.
              </div>
            ) : propuesta.estado === "error" ? (
              <p className="py-4 text-sm text-red-700 dark:text-red-300">
                No pude leerlo: {propuesta.error || "inténtalo con otro enlace o documento."}
              </p>
            ) : propuestos.length === 0 ? (
              <p className="py-4 text-sm text-muted-foreground">
                No encontré {etiquetaTipo === "evento" ? "eventos" : "tareas"} ahí. Prueba con otro
                enlace/documento o escríbelo a mano.
              </p>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">
                  Encontré <span className="font-medium text-foreground">{propuestos.length}</span>{" "}
                  {propuestos.length === 1 ? etiquetaTipo : `${etiquetaTipo}s`}. Revisa y acepta:
                </p>
                <div className="max-h-72 space-y-1.5 overflow-y-auto">
                  {propuestos.map((op, i) => (
                    <div
                      key={`${op.titulo}-${i}`}
                      className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                    >
                      {op.tipo === "crear_evento" ? (
                        <CalendarDays className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      ) : (
                        <ListChecks className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      )}
                      {/* min-w-0 + flex-1: sin esto, un título largo con `truncate` (nowrap) NO
                          encoge en el flex y estira la fila más allá del diálogo, empujando el botón
                          «Aceptar y añadir» fuera de pantalla (había que deslizar a la derecha). */}
                      <span className="min-w-0 flex-1 truncate font-medium">{op.titulo}</span>
                      <span className="shrink-0 whitespace-nowrap text-muted-foreground">
                        {op.tipo === "crear_evento"
                          ? `${op.fecha ? formatearFecha(op.fecha) : ""}${op.hora ? ` · ${op.hora}` : ""}`
                          : op.fecha_objetivo
                            ? formatearFecha(op.fecha_objetivo)
                            : ""}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => (propuesta && !generando ? descartar.mutate() : setPropuestaId(null))}
                disabled={aceptar.isPending || descartar.isPending}
              >
                Volver
              </Button>
              {propuestos.length > 0 && !generando && (
                <Button variant="secondary" onClick={() => aceptar.mutate()} disabled={aceptar.isPending}>
                  <Check className="mr-1 h-4 w-4" />
                  {aceptar.isPending ? "Añadiendo…" : "Aceptar y añadir"}
                </Button>
              )}
            </DialogFooter>
          </div>
        ) : (
          <>
            {/* Qué se añade. Segmentado claro (píldora blanca sobre pista gris), no bloque negro. */}
            <div className="inline-flex rounded-md border border-border bg-muted p-0.5">
              {(["evento", "tarea"] as Modo[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => {
                    setModo(m);
                    // Una propuesta es de UN tipo (evento o tarea): al cambiar de modo se
                    // descarta el import a medias para no mezclar tipos en la revisión.
                    setPropuestaId(null);
                    setPegado("");
                    setArchivo(null);
                  }}
                  className={cn(
                    "rounded-[5px] px-3 py-1 text-sm transition-colors",
                    modo === m
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m === "evento" ? "Evento" : "Tarea"}
                </button>
              ))}
            </div>

            {/* La distinción que pidió el equipo: un evento aterriza en el calendario de
                Turnos; una tarea no, solo vive en el tablero de Cobertura. */}
            <p className="text-xs text-muted-foreground">
              {modo === "evento"
                ? "Va al calendario de Turnos y a «Por cubrir»."
                : "No va al calendario: solo en Panorama y Mis tareas."}
            </p>

            {/* Caja inteligente: en AMBOS modos. En Evento la IA propone eventos; en Tarea
                propone encargos sueltos (mismo flujo: pega/sube/escribe → revisa → acepta). */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setArrastrando(true);
              }}
              onDragLeave={() => setArrastrando(false)}
              onDrop={(e) => {
                e.preventDefault();
                setArrastrando(false);
                const f = e.dataTransfer.files?.[0];
                if (f) {
                  setArchivo(f);
                  return;
                }
                const texto =
                  e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain");
                if (texto) setPegado(texto.trim());
              }}
              className={cn(
                "space-y-2 rounded-lg border border-dashed p-3 transition-colors",
                arrastrando ? "border-foreground/40 bg-muted" : "border-border",
              )}
            >
              <div className="flex items-center gap-1.5 text-sm font-medium">
                <Sparkles className="h-4 w-4 text-primary" />
                Pega un enlace, suelta un documento o PDF, o escribe una frase y lo creo solo
              </div>
              <Textarea
                value={pegado}
                onChange={(e) => setPegado(e.target.value)}
                placeholder={
                  modo === "evento"
                    ? "Pega un enlace, o escribe el evento en una frase…"
                    : "Pega un enlace, o escribe la tarea en una frase…"
                }
                rows={2}
              />
              <div className="flex flex-wrap items-center gap-2">
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-sm hover:bg-accent">
                  <Upload className="h-3.5 w-3.5" />
                  {archivo ? archivo.name : "Subir documento"}
                  <input
                    type="file"
                    className="hidden"
                    accept=".pdf,.png,.jpg,.jpeg,.webp,.xlsx,.xls,.csv,.docx,.txt"
                    onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                  />
                </label>
                {archivo && (
                  <button
                    type="button"
                    className="text-xs text-muted-foreground underline-offset-2 hover:underline"
                    onClick={() => setArchivo(null)}
                  >
                    quitar
                  </button>
                )}
                <Button
                  size="sm"
                  variant="secondary"
                  className="ml-auto"
                  onClick={() => analizar.mutate()}
                  disabled={nadaQueAnalizar || analizar.isPending}
                >
                  {analizar.isPending ? (
                    <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                  ) : esUrl(pegado) ? (
                    <Link2 className="mr-1 h-3.5 w-3.5" />
                  ) : (
                    <Sparkles className="mr-1 h-3.5 w-3.5" />
                  )}
                  Analizar
                </Button>
              </div>
            </div>

            <div className="relative py-1 text-center text-xs text-muted-foreground">
              — o escríbelo a mano —
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="tarea-titulo">
                  {modo === "evento" ? "Qué evento" : "Qué hay que hacer"}
                </Label>
                <Input
                  id="tarea-titulo"
                  value={titulo}
                  onChange={(e) => setTitulo(e.target.value)}
                  placeholder={
                    modo === "evento"
                      ? "Final de la Copa, un concierto, una rueda de prensa…"
                      : "Editar el clip del gol, subir fotos del entreno…"
                  }
                />
              </div>

              {modo === "evento" ? (
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="tarea-fecha">Día</Label>
                    <Input
                      id="tarea-fecha"
                      type="date"
                      value={fecha}
                      onChange={(e) => setFecha(e.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="tarea-hora">Hora</Label>
                    <Input
                      id="tarea-hora"
                      type="time"
                      value={hora}
                      onChange={(e) => setHora(e.target.value)}
                    />
                  </div>
                  {campoPrioridad}
                </div>
              ) : (
                // Tarea: «Asignar a» cabalga en la MISMA fila que Para cuándo/Prioridad (3 col)
                // en vez de una fila aparte, para que el diálogo entre sin scroll (igual altura
                // que Evento). Etiquetas cortas → los campos alinean.
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="tarea-fecha">Para cuándo</Label>
                    <Input
                      id="tarea-fecha"
                      type="date"
                      value={fecha}
                      onChange={(e) => setFecha(e.target.value)}
                    />
                  </div>
                  {campoPrioridad}
                  {campoResponsable}
                </div>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="tarea-desc">
                  {modo === "evento" ? "Qué sacar (opcional)" : "Detalle (opcional)"}
                </Label>
                <Textarea
                  id="tarea-desc"
                  value={contenido}
                  onChange={(e) => setContenido(e.target.value)}
                  placeholder={
                    modo === "evento"
                      ? "Reacciones, ambiente, momentos clave…"
                      : "Notas, lugar, qué se espera entregar…"
                  }
                  rows={2}
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={cerrar} disabled={crear.isPending}>
                Cancelar
              </Button>
              <Button
                variant="secondary"
                onClick={() => crear.mutate()}
                disabled={crear.isPending || incompletoManual}
              >
                {crear.isPending
                  ? "Añadiendo…"
                  : modo === "evento"
                    ? "Añadir evento"
                    : "Crear tarea"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
