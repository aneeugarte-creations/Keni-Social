import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Eye,
  FileText,
  Link2,
  Loader2,
  Pencil,
  Save,
  Sprout,
  Trash2,
} from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { BarraFormato } from "@/components/editor/BarraFormato";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorImagen } from "@/components/media/EditorImagen";
import { SelectorPlantilla } from "@/components/plantillas/SelectorPlantilla";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { ConstructorUtm } from "@/components/utm/ConstructorUtm";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, ApiError } from "@/lib/api";
import type {
  CuerpoActualizarPublicacion,
  EstadoOpcion,
  EstadoPublicacion,
  Publicacion,
  RespuestaEjecutarSkill,
  Veredicto,
} from "@/types";

import { CLAVE_PUBLICACIONES } from "../publicaciones/claves";
import { GestionHashtags } from "../publicaciones/GestionHashtags";
import { BadgeEstado } from "../publicaciones/insignias";
import { datetimeLocalAIso, iconoRed, isoADatetimeLocal, metaRed, metaVeredicto, nombreRed } from "../publicaciones/meta";
import { agregarEnlace } from "../publicaciones/plantillas";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/** Modos del editor: textarea crudo, lectura Markdown y vista previa por red. */
type Vista = "editar" | "lectura" | "previa";

/** Toggle de modo del editor (Editar / Vista / Previa), compacto y reutilizable. */
function ToggleVista({ value, onChange }: { value: Vista; onChange: (v: Vista) => void }) {
  return (
    <Tabs value={value} onValueChange={(v) => onChange(v as Vista)}>
      <TabsList className="h-8">
        <TabsTrigger value="editar" className="gap-1.5 px-2.5 py-1 text-xs">
          <Pencil className="h-3.5 w-3.5" />
          Editar
        </TabsTrigger>
        <TabsTrigger value="lectura" className="gap-1.5 px-2.5 py-1 text-xs">
          <FileText className="h-3.5 w-3.5" />
          Vista
        </TabsTrigger>
        <TabsTrigger value="previa" className="gap-1.5 px-2.5 py-1 text-xs">
          <Eye className="h-3.5 w-3.5" />
          Previa
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}

/** Badge de veredicto editorial; no renderiza nada si no hay veredicto. */
function BadgeVeredicto({ veredicto }: { veredicto: Veredicto }) {
  const m = metaVeredicto(veredicto);
  if (!m) return null;
  return <Badge variant={m.variante}>{m.nombre}</Badge>;
}

/** Enlace de éxito a Publicaciones que se muestra en el toast. */
function EnlacePublicaciones() {
  return (
    <Link to="/publicaciones" className="inline-flex items-center gap-1 underline">
      Ver en Publicaciones
      <ExternalLink className="h-3 w-3" />
    </Link>
  );
}

/**
 * Panel de edición de UNA publicación ya creada (un borrador por red).
 *
 * Reutiliza la misma lógica de `DialogoEditar`: contenido editable con
 * "Guardar cambios" (`PUT`), selector de estado, fecha programada, imagen,
 * hashtags, UTM, vista previa y toggle de perenne. Añade además
 * Programar/Encolar (`POST encolar`) y Borrar (`DELETE`).
 */
function PanelPublicacion({
  publicacion,
  estados,
  onBorrada,
  onGestionarHashtags,
}: {
  publicacion: Publicacion;
  estados: EstadoOpcion[];
  onBorrada: (id: string) => void;
  onGestionarHashtags: () => void;
}) {
  const queryClient = useQueryClient();

  const [contenido, setContenido] = React.useState(publicacion.contenido);
  const [estado, setEstado] = React.useState<EstadoPublicacion>(publicacion.estado);
  const [evergreen, setEvergreen] = React.useState(publicacion.evergreen ?? false);
  const [fechaLocal, setFechaLocal] = React.useState(isoADatetimeLocal(publicacion.fecha_programada));
  const [imagen, setImagen] = React.useState(publicacion.imagen ?? "");
  const [imagenUrl, setImagenUrl] = React.useState(publicacion.imagen_url ?? "");
  const [vista, setVista] = React.useState<Vista>("editar");
  const [utmAbierto, setUtmAbierto] = React.useState(false);
  const [copiado, setCopiado] = React.useState(false);
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  const areaRef = React.useRef<HTMLTextAreaElement>(null);

  const red = publicacion.red;
  const limite = metaRed(red).limite;
  const programado = estado === "programado";
  const faltaFecha = programado && !fechaLocal;

  function invalidar() {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
  }

  const guardar = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoActualizarPublicacion = {
        contenido,
        estado,
        evergreen,
        // Solo mandamos fecha si está programado; al salir de programado, la limpiamos.
        fecha_programada: programado ? datetimeLocalAIso(fechaLocal) : null,
        imagen,
      };
      return api.actualizarPublicacion(publicacion.id, cuerpo);
    },
    onSuccess: () => {
      invalidar();
      toast.success("Cambios guardados", { description: <EnlacePublicaciones /> });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const alternarEvergreen = useMutation({
    mutationFn: (valor: boolean) =>
      api.actualizarPublicacion(publicacion.id, { evergreen: valor }),
    onSuccess: (_res, valor) => {
      invalidar();
      toast.success(valor ? "Marcada como perenne" : "Ya no es perenne");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const encolar = useMutation({
    mutationFn: () => api.encolarPublicacion(publicacion.id),
    onSuccess: (res) => {
      invalidar();
      const fecha = res?.publicacion?.fecha_programada;
      if (fecha) {
        setEstado(res.publicacion.estado);
        setFechaLocal(isoADatetimeLocal(fecha));
      }
      toast.success("Publicación añadida a la cola", { description: <EnlacePublicaciones /> });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const borrar = useMutation({
    mutationFn: () => api.eliminarPublicacion(publicacion.id),
    onSuccess: () => {
      setConfirmarBorrado(false);
      invalidar();
      onBorrada(publicacion.id);
      toast.success("Publicación borrada");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function cambiarEvergreen(valor: boolean) {
    setEvergreen(valor);
    alternarEvergreen.mutate(valor);
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(contenido);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  const puedeGuardar = contenido.trim().length > 0 && !faltaFecha && !guardar.isPending;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <BadgeEstado estado={estado} />
          <BadgeVeredicto veredicto={publicacion.veredicto} />
          {evergreen && (
            <Badge
              variant="outline"
              className="gap-1 border-emerald-500/40 font-normal text-emerald-700 dark:text-emerald-300"
            >
              <Sprout className="h-3 w-3" />
              Perenne
            </Badge>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <ContadorCaracteres caracteres={contenido.length} limite={limite} />
          <ToggleVista value={vista} onChange={setVista} />
        </div>
      </div>

      {vista === "editar" ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <SelectorPlantilla marca={publicacion.marca} red={red} onUsar={setContenido} />
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8"
              onClick={() => setUtmAbierto(true)}
            >
              <Link2 className="h-4 w-4" />
              Enlace UTM
            </Button>
            <BarraFormato refArea={areaRef} valor={contenido} onContenido={setContenido} />
          </div>
          <AutoTextarea
            ref={areaRef}
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            maxHeight={520}
            className="min-h-[12rem] font-mono text-sm leading-relaxed"
            aria-label={`Contenido para ${nombreRed(red)}`}
          />
          <HerramientasHashtags
            contenido={contenido}
            onContenido={setContenido}
            marca={publicacion.marca}
            red={red}
            onGestionar={onGestionarHashtags}
          />
          <EditorImagen
            imagen={imagen}
            imagenUrl={imagenUrl}
            onCambio={(nombre, url) => {
              setImagen(nombre);
              setImagenUrl(url);
            }}
            idPrefijo={`copy-${red}`}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`estado-${red}`}>Estado</Label>
              <Select value={estado} onValueChange={(v) => setEstado(v as EstadoPublicacion)}>
                <SelectTrigger id={`estado-${red}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {estados.map((e) => (
                    <SelectItem key={e.id} value={e.id}>
                      {e.nombre}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {programado && (
              <div className="space-y-1.5">
                <Label htmlFor={`fecha-${red}`}>Fecha y hora programada</Label>
                <Input
                  id={`fecha-${red}`}
                  type="datetime-local"
                  value={fechaLocal}
                  onChange={(e) => setFechaLocal(e.target.value)}
                />
                {faltaFecha && (
                  <p className="text-xs text-amber-600 dark:text-amber-400">
                    Elige una fecha para programar la publicación.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="flex items-start gap-2 rounded-md border border-border bg-muted/20 p-3">
            <Checkbox
              id={`evergreen-${red}`}
              checked={evergreen}
              onCheckedChange={cambiarEvergreen}
              disabled={alternarEvergreen.isPending}
              aria-label="Marcar como perenne"
              className="mt-0.5"
            />
            <div className="space-y-0.5">
              <Label
                htmlFor={`evergreen-${red}`}
                className="flex cursor-pointer items-center gap-1.5 font-normal"
              >
                <Sprout className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                Contenido perenne
              </Label>
              <p className="text-xs text-muted-foreground">
                Marca esta publicación como reutilizable para reciclarla y volver a publicarla más
                adelante.
              </p>
            </div>
          </div>
        </>
      ) : vista === "lectura" ? (
        <div className="rounded-md border border-border bg-muted/20 p-4">
          {contenido.trim() ? (
            <Markdown>{contenido}</Markdown>
          ) : (
            <p className="text-sm italic text-muted-foreground">Sin contenido todavía.</p>
          )}
        </div>
      ) : (
        <VistaPreviaRed
          red={red}
          marca={publicacion.marca_nombre}
          contenido={contenido}
          imagen_url={imagenUrl || imagen}
        />
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm" onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar cambios
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => encolar.mutate()}
          disabled={encolar.isPending}
          title="Programar/Encolar en la próxima franja libre"
        >
          {encolar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <CalendarPlus className="h-4 w-4" />
          )}
          Programar/Encolar
        </Button>
        <Button variant="outline" size="sm" onClick={() => void copiar()}>
          {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copiado ? "Copiado" : "Copiar"}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="ml-auto text-muted-foreground hover:text-destructive"
          onClick={() => setConfirmarBorrado(true)}
        >
          <Trash2 className="h-4 w-4" />
          Borrar
        </Button>
      </div>

      <ConstructorUtm
        abierto={utmAbierto}
        onCerrar={() => setUtmAbierto(false)}
        onInsertar={(enlace) => setContenido((prev) => agregarEnlace(prev, enlace))}
      />

      <Dialog open={confirmarBorrado} onOpenChange={setConfirmarBorrado}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Borrar publicación</DialogTitle>
            <DialogDescription>
              ¿Seguro que quieres borrar el borrador de {nombreRed(red)}? Esta acción no se puede
              deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setConfirmarBorrado(false)}
              disabled={borrar.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={() => borrar.mutate()}
              disabled={borrar.isPending}
            >
              {borrar.isPending ? "Borrando…" : "Borrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/**
 * Panel de respaldo para cuando la generación NO devolvió publicaciones (ni
 * piezas). Muestra el `resultado` en bruto y permite guardarlo a mano eligiendo
 * una red, vía `POST /api/skills/historial/{id}/guardar`.
 */
function PanelManual({
  resultado,
  historialId,
  redes,
}: {
  resultado: string;
  historialId: string;
  redes: { id: string; nombre: string }[];
}) {
  const queryClient = useQueryClient();
  const [red, setRed] = React.useState("");
  const [copiado, setCopiado] = React.useState(false);

  const guardar = useMutation({
    mutationFn: () => api.guardarHistorial(historialId, { red }),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      const n = data?.publicaciones?.length ?? 1;
      toast.success(`Se ${n === 1 ? "guardó" : "guardaron"} ${n} ${n === 1 ? "publicación" : "publicaciones"}`, {
        description: <EnlacePublicaciones />,
      });
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  async function copiar() {
    try {
      await navigator.clipboard.writeText(resultado);
      setCopiado(true);
      toast.success("Copiado al portapapeles");
      window.setTimeout(() => setCopiado(false), 2000);
    } catch {
      toast.error("No se pudo copiar. Selecciona el texto y cópialo a mano.");
    }
  }

  return (
    <div className="space-y-3">
      <div className="max-h-[28rem] overflow-auto rounded-md border border-border bg-muted/20 p-4 leading-relaxed">
        <Markdown>{resultado}</Markdown>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="guardar-red">Red</Label>
          <Select value={red} onValueChange={setRed}>
            <SelectTrigger id="guardar-red" className="w-44">
              <SelectValue placeholder="Elige una red" />
            </SelectTrigger>
            <SelectContent>
              {redes.map((r) => (
                <SelectItem key={r.id} value={r.id}>
                  {r.nombre}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button
          size="sm"
          onClick={() => guardar.mutate()}
          disabled={guardar.isPending || red === ""}
        >
          {guardar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Guardar como publicación
        </Button>
        <Button variant="outline" size="sm" onClick={() => void copiar()}>
          {copiado ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          {copiado ? "Copiado" : "Copiar"}
        </Button>
      </div>
    </div>
  );
}

/**
 * Resultado de la generación. Las piezas ya se guardaron como borradores
 * (`respuesta.publicaciones`), así que cada pestaña por red es un editor de la
 * publicación creada con controles completos (guardar, estado, programar,
 * perenne, imagen, hashtags, UTM, vista previa y borrar). Si no se creó nada,
 * se muestra el `resultado` en una sola pestaña "Todo" para guardarlo a mano.
 */
export function ResultadoRedes({
  respuesta,
}: {
  respuesta: RespuestaEjecutarSkill;
}) {
  const [gestionHashtags, setGestionHashtags] = React.useState(false);
  // Publicaciones locales: arrancan de la respuesta y se podan al borrar pestañas.
  const [publicaciones, setPublicaciones] = React.useState<Publicacion[]>(
    respuesta.publicaciones ?? [],
  );

  React.useEffect(() => {
    setPublicaciones(respuesta.publicaciones ?? []);
  }, [respuesta]);

  // Catálogo de opciones (marcas para hashtags, estados, redes para guardado manual).
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opcionesQuery.data?.marcas ?? [];
  const estados = opcionesQuery.data?.estados ?? [];
  const redes =
    opcionesQuery.data?.redes.map((r) => ({ id: r.id, nombre: r.nombre })) ?? [];

  const [activa, setActiva] = React.useState(publicaciones[0]?.red ?? "");

  React.useEffect(() => {
    if (publicaciones.length > 0 && !publicaciones.some((p) => p.red === activa)) {
      setActiva(publicaciones[0].red);
    }
  }, [publicaciones, activa]);

  function borrarPanel(id: string) {
    setPublicaciones((prev) => prev.filter((p) => p.id !== id));
  }

  const sinPublicaciones = publicaciones.length === 0;

  return (
    <Card>
      <CardHeader className="space-y-2 pb-3">
        <CardTitle className="text-base">Resultado por red</CardTitle>
        {sinPublicaciones ? (
          <Badge variant="aviso">Borrador · no guardado</Badge>
        ) : (
          <div className="flex items-center gap-1.5 rounded-md bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>
              Guardadas como borradores en{" "}
              <Link to="/publicaciones" className="inline-flex items-center gap-1 font-medium underline">
                Publicaciones
                <ExternalLink className="h-3 w-3" />
              </Link>
            </span>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {sinPublicaciones ? (
          <Tabs value="todo">
            <TabsList className="flex-wrap">
              <TabsTrigger value="todo">Todo</TabsTrigger>
            </TabsList>
            <TabsContent value="todo">
              <PanelManual
                resultado={respuesta.resultado}
                historialId={respuesta.historial_id}
                redes={redes}
              />
            </TabsContent>
          </Tabs>
        ) : (
          <Tabs value={activa} onValueChange={setActiva}>
            <TabsList className="flex-wrap">
              {publicaciones.map((p) => {
                const Icono = iconoRed(p.red);
                return (
                  <TabsTrigger key={p.id} value={p.red} className="gap-1.5">
                    <Icono className="h-4 w-4" />
                    {nombreRed(p.red)}
                  </TabsTrigger>
                );
              })}
            </TabsList>
            {publicaciones.map((p) => (
              <TabsContent key={p.id} value={p.red}>
                <PanelPublicacion
                  publicacion={p}
                  estados={estados}
                  onBorrada={borrarPanel}
                  onGestionarHashtags={() => setGestionHashtags(true)}
                />
              </TabsContent>
            ))}
          </Tabs>
        )}
      </CardContent>

      <GestionHashtags
        abierto={gestionHashtags}
        onCerrar={() => setGestionHashtags(false)}
        marcas={marcas}
      />
    </Card>
  );
}
