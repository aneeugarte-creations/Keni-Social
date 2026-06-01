import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  Eye,
  FileText,
  Link2,
  Loader2,
  Pencil,
  Send,
  ShieldCheck,
  Sprout,
  XCircle,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BarraFormato } from "@/components/editor/BarraFormato";
import { ContadorCaracteres } from "@/components/editor/ContadorCaracteres";
import { HerramientasHashtags } from "@/components/hashtags/HerramientasHashtags";
import { EditorImagen } from "@/components/media/EditorImagen";
import { SelectorPlantilla } from "@/components/plantillas/SelectorPlantilla";
import { VistaPreviaRed } from "@/components/preview/VistaPreviaRed";
import { ConstructorUtm } from "@/components/utm/ConstructorUtm";
import { AutoTextarea } from "@/components/ui/auto-textarea";
import { Button } from "@/components/ui/button";
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
import type { CuerpoActualizarPublicacion, EstadoOpcion, EstadoPublicacion, Publicacion } from "@/types";

import { CLAVE_PUBLICACIONES } from "./claves";
import { GestionHashtags } from "./GestionHashtags";
import { EtiquetaRed } from "./insignias";
import { datetimeLocalAIso, isoADatetimeLocal, metaRed } from "./meta";
import { agregarEnlace } from "./plantillas";

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

/**
 * Estados que el equipo elige A MANO en el desplegable de edición. La APROBACIÓN
 * (`en_revision` → `aprobado`) NO se elige aquí: se decide por la CADENA de aprobación
 * (botones Enviar a revisión / Aprobar / Rechazar), única vía de aprobación. Así nadie
 * salta la revisión poniendo el estado a mano. `programado`/`publicado` siguen disponibles.
 */
const ESTADOS_DECISION_CADENA = new Set(["en_revision", "aprobado"]);

/**
 * Panel de APROBACIÓN de una publicación: la cadena multinivel expresada para una pieza
 * suelta (cadena simple). Mantiene la aprobación ACCESIBLE desde la UI de Publicaciones:
 *  - `borrador`     → botón "Enviar a revisión" (crea la cadena y deja la pieza en revisión).
 *  - `en_revision`  → botones "Aprobar" / "Rechazar" (deciden el nivel actual; revisor != autor).
 *  - `aprobado`     → aviso de que ya está aprobada (lista para programar con su fecha).
 * Reusa los endpoints `/api/aprobacion/*`, que forwardean a la cadena.
 */
function PanelAprobacion({ publicacion }: { publicacion: Publicacion }) {
  const queryClient = useQueryClient();

  const tras = (mensaje: string) => () => {
    void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
    toast.success(mensaje);
  };
  const onError = (e: unknown) => toast.error(mensajeError(e));

  const enviar = useMutation({
    mutationFn: () => api.enviarARevision(publicacion.id),
    onSuccess: tras("Enviada a revisión."),
    onError,
  });
  const aprobar = useMutation({
    mutationFn: () => api.aprobarPublicacion(publicacion.id),
    onSuccess: tras("Publicación aprobada."),
    onError,
  });
  const rechazar = useMutation({
    mutationFn: () => api.rechazarPublicacion(publicacion.id),
    onSuccess: tras("Devuelta a borrador."),
    onError,
  });
  const ocupado = enviar.isPending || aprobar.isPending || rechazar.isPending;

  return (
    <div className="space-y-2 rounded-md border border-border bg-muted/20 p-3">
      <div className="flex items-center gap-2 text-sm font-medium">
        <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
        Aprobación
      </div>
      {publicacion.estado === "borrador" && (
        <>
          <p className="text-xs text-muted-foreground">
            Envíala a revisión para que otra persona la apruebe antes de programarla.
          </p>
          <Button size="sm" onClick={() => enviar.mutate()} disabled={ocupado}>
            {enviar.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            Enviar a revisión
          </Button>
        </>
      )}
      {publicacion.estado === "en_revision" && (
        <>
          <p className="text-xs text-muted-foreground">
            En revisión. Quien aprueba no puede ser el autor (salvo admin).
          </p>
          <div className="flex gap-2">
            <Button size="sm" onClick={() => aprobar.mutate()} disabled={ocupado}>
              {aprobar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Check className="h-4 w-4" />
              )}
              Aprobar
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => rechazar.mutate()}
              disabled={ocupado}
            >
              {rechazar.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              Rechazar
            </Button>
          </div>
        </>
      )}
      {(publicacion.estado === "aprobado" ||
        publicacion.estado === "programado" ||
        publicacion.estado === "publicado") && (
        <p className="text-xs text-muted-foreground">
          {publicacion.revisor_nombre
            ? `Aprobada por ${publicacion.revisor_nombre}.`
            : "Aprobada."}{" "}
          Ya puedes programarla eligiendo el estado “Programado” y su fecha.
        </p>
      )}
    </div>
  );
}

/** Diálogo de edición de una publicación: título, contenido, estado y fecha. */
export function DialogoEditar({
  publicacion,
  estados,
  onCerrar,
}: {
  publicacion: Publicacion | null;
  estados: EstadoOpcion[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const [titulo, setTitulo] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [estado, setEstado] = React.useState<EstadoPublicacion>("borrador");
  const [evergreen, setEvergreen] = React.useState(false);
  const [fechaLocal, setFechaLocal] = React.useState("");
  // Imagen: nombre del archivo + url para previsualizar.
  const [imagen, setImagen] = React.useState("");
  const [imagenUrl, setImagenUrl] = React.useState("");
  const [vista, setVista] = React.useState<"editar" | "lectura" | "previa">("editar");
  const [gestionHashtags, setGestionHashtags] = React.useState(false);
  const [utmAbierto, setUtmAbierto] = React.useState(false);
  const areaRef = React.useRef<HTMLTextAreaElement>(null);

  // Catálogo de marcas para la gestión de grupos de hashtags.
  const opcionesQuery = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    enabled: publicacion !== null,
  });
  const marcas = opcionesQuery.data?.marcas ?? [];

  // Cargamos los valores cada vez que se abre con una publicación nueva.
  React.useEffect(() => {
    if (!publicacion) return;
    setTitulo(publicacion.titulo);
    setContenido(publicacion.contenido);
    setEstado(publicacion.estado);
    setEvergreen(publicacion.evergreen ?? false);
    setFechaLocal(isoADatetimeLocal(publicacion.fecha_programada));
    setImagen(publicacion.imagen ?? "");
    setImagenUrl(publicacion.imagen_url ?? "");
    setVista("editar");
  }, [publicacion]);

  const limite = publicacion ? metaRed(publicacion.red).limite : null;
  const programado = estado === "programado";

  // El desplegable de estado NO ofrece los estados de la cadena de aprobación
  // (`en_revision`/`aprobado`): esos se alcanzan SOLO por los botones del panel de
  // aprobación. Si la pieza YA está en uno de ellos, lo dejamos visible (deshabilitado de
  // hecho por no estar en la lista de cambios) para no romper el Select controlado.
  const estadosElegibles = React.useMemo(
    () => estados.filter((e) => !ESTADOS_DECISION_CADENA.has(e.id) || e.id === estado),
    [estados, estado],
  );

  const guardar = useMutation({
    mutationFn: () => {
      if (!publicacion) throw new Error("Sin publicación");
      const cuerpo: CuerpoActualizarPublicacion = {
        titulo: titulo.trim(),
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
      void queryClient.invalidateQueries({ queryKey: CLAVE_PUBLICACIONES });
      toast.success("Publicación actualizada");
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const faltaFecha = programado && !fechaLocal;
  const puedeGuardar =
    !!publicacion && titulo.trim().length > 0 && contenido.trim().length > 0 && !faltaFecha && !guardar.isPending;

  return (
    <Dialog open={publicacion !== null} onOpenChange={(o) => !o && onCerrar()}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Editar publicación</DialogTitle>
          <DialogDescription className="flex items-center gap-2">
            {publicacion && (
              <>
                <EtiquetaRed red={publicacion.red} nombre={publicacion.red_nombre} />
                <span className="text-muted-foreground">· {publicacion.marca_nombre}</span>
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={vista} onValueChange={(v) => setVista(v as "editar" | "lectura" | "previa")}>
          <TabsList>
            <TabsTrigger value="editar" className="gap-1.5">
              <Pencil className="h-4 w-4" />
              Editar
            </TabsTrigger>
            <TabsTrigger value="lectura" className="gap-1.5">
              <FileText className="h-4 w-4" />
              Vista
            </TabsTrigger>
            <TabsTrigger value="previa" className="gap-1.5">
              <Eye className="h-4 w-4" />
              Previa
            </TabsTrigger>
          </TabsList>

          <TabsContent value="editar" className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="editar-titulo">Título</Label>
              <Input
                id="editar-titulo"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                maxLength={200}
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label htmlFor="editar-contenido">Contenido</Label>
                <ContadorCaracteres caracteres={contenido.length} limite={limite} />
              </div>
              <AutoTextarea
                ref={areaRef}
                id="editar-contenido"
                value={contenido}
                onChange={(e) => setContenido(e.target.value)}
                maxHeight={420}
                className="min-h-[10rem] font-mono text-sm"
              />
              {publicacion && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <SelectorPlantilla
                    marca={publicacion.marca}
                    red={publicacion.red}
                    onUsar={setContenido}
                  />
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
              )}
            </div>

            {publicacion && (
              <HerramientasHashtags
                contenido={contenido}
                onContenido={setContenido}
                marca={publicacion.marca}
                red={publicacion.red}
                onGestionar={() => setGestionHashtags(true)}
              />
            )}

            <EditorImagen
              imagen={imagen}
              imagenUrl={imagenUrl}
              onCambio={(nombre, url) => {
                setImagen(nombre);
                setImagenUrl(url);
              }}
              idPrefijo="editar"
              publicacionId={publicacion?.id}
              marca={publicacion?.marca}
              red={publicacion?.red}
              copy={contenido}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="editar-estado">Estado</Label>
                <Select value={estado} onValueChange={(v) => setEstado(v as EstadoPublicacion)}>
                  <SelectTrigger id="editar-estado">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {estadosElegibles.map((e) => (
                      <SelectItem key={e.id} value={e.id}>
                        {e.nombre}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {programado && (
                <div className="space-y-1.5">
                  <Label htmlFor="editar-fecha">Fecha y hora programada</Label>
                  <Input
                    id="editar-fecha"
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

            {publicacion && <PanelAprobacion publicacion={publicacion} />}

            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/20 p-3">
              <Checkbox
                id="editar-evergreen"
                checked={evergreen}
                onCheckedChange={setEvergreen}
                aria-label="Marcar como perenne"
                className="mt-0.5"
              />
              <div className="space-y-0.5">
                <Label
                  htmlFor="editar-evergreen"
                  className="flex cursor-pointer items-center gap-1.5 font-normal"
                >
                  <Sprout className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  Contenido perenne
                </Label>
                <p className="text-xs text-muted-foreground">
                  Marca esta publicación como reutilizable para reciclarla y volver a publicarla
                  más adelante.
                </p>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="lectura">
            <div className="rounded-md border border-border bg-muted/20 p-4">
              {contenido.trim() ? (
                <Markdown>{contenido}</Markdown>
              ) : (
                <p className="text-sm italic text-muted-foreground">Sin contenido todavía.</p>
              )}
            </div>
          </TabsContent>

          <TabsContent value="previa">
            {publicacion && (
              <VistaPreviaRed
                red={publicacion.red}
                marca={publicacion.marca_nombre}
                contenido={contenido}
                imagen_url={imagenUrl || imagen}
              />
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar} disabled={guardar.isPending}>
            Cancelar
          </Button>
          <Button onClick={() => guardar.mutate()} disabled={!puedeGuardar}>
            {guardar.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Guardar cambios
          </Button>
        </DialogFooter>

        <GestionHashtags
          abierto={gestionHashtags}
          onCerrar={() => setGestionHashtags(false)}
          marcas={marcas}
        />

        <ConstructorUtm
          abierto={utmAbierto}
          onCerrar={() => setUtmAbierto(false)}
          onInsertar={(enlace) => setContenido((prev) => agregarEnlace(prev, enlace))}
        />
      </DialogContent>
    </Dialog>
  );
}
