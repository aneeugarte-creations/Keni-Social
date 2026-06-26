import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Pause,
  Play,
  Plus,
  Send,
  ShieldAlert,
  Trash2,
  Webhook as WebhookIcon,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { Campo } from "@/components/comunes/Campo";
import { confirmar } from "@/components/comunes/confirmar";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { FilaConAcciones } from "@/components/comunes/FilaConAcciones";
import type { EntradaMenuContextual } from "@/components/comunes/MenuContextual";
import { AccionesPagina, TituloPagina } from "@/components/layout/encabezado";
import { ItemMenu, MenuAcciones } from "@/components/layout/MenuAcciones";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFechaHoraCorta } from "@/lib/fecha";
import type {
  CuerpoCrearWebhook,
  FormatoWebhook,
  TipoEventoInterno,
  Webhook,
} from "@/types";

const CLAVE = ["webhooks"] as const;

/** Etiqueta humana de cada tipo de evento. */
const ETIQUETA_EVENTO: Record<TipoEventoInterno, string> = {
  "pieza.aprobada": "Pieza aprobada",
  "pieza.publicada": "Pieza publicada",
  "contenido.vencido": "Publicacion vencido",
  "pieza.bajo_rendimiento": "Pieza con bajo rendimiento",
};

const ETIQUETA_FORMATO: Record<FormatoWebhook, string> = {
  generico: "Genérico (JSON)",
  slack: "Slack",
};

// Fecha+hora en CDMX (los instantes del backend son UTC); ver `@/lib/fecha`.
const formatearFechaHora = (iso: string): string => formatearFechaHoraCorta(iso);

export default function Webhooks() {
  const [crearAbierto, setCrearAbierto] = React.useState(false);
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.webhooks(signal),
  });

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;

  const catalogo = query.data?.catalogo;
  const puedeCrear = !esProhibido && !query.isError && !!catalogo;

  return (
    <>
      <TituloPagina titulo="Webhooks" icono={WebhookIcon} />
      {puedeCrear && (
        <AccionesPagina>
          <MenuAcciones>
            <ItemMenu icono={Plus} onClick={() => setCrearAbierto(true)}>
              Nuevo webhook
            </ItemMenu>
          </MenuAcciones>
        </AccionesPagina>
      )}
      {catalogo && (
        <DialogoCrearWebhook
          abierto={crearAbierto}
          onAbierto={setCrearAbierto}
          eventos={catalogo.eventos}
          formatos={catalogo.formatos}
        />
      )}

      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
          texto="Solo los administradores pueden gestionar los webhooks."
        />
      ) : query.isPending ? (
        <Skeleton className="h-64 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los webhooks"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : query.data.webhooks.length === 0 ? (
        <EstadoVacio
          icono={WebhookIcon}
          titulo="Aún no hay webhooks"
          texto="Crea uno para avisar al equipo cuando se aprueba, publica o vence contenido."
        />
      ) : (
        <div className="mt-4 grid gap-3">
          {query.data.webhooks.map((wh) => (
            <TarjetaWebhook key={wh.id} webhook={wh} />
          ))}
        </div>
      )}

      {query.data && query.data.eventos_recientes.length > 0 && (
        <section className="mt-8">
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">
            Últimos eventos emitidos
          </h3>
          <div className="grid gap-1.5">
            {query.data.eventos_recientes.map((ev) => (
              <div
                key={ev.id}
                className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              >
                <span>
                  <Badge variant="secondary">{ETIQUETA_EVENTO[ev.tipo] ?? ev.tipo}</Badge>{" "}
                  <span className="text-muted-foreground">
                    {String(
                      (ev.payload as { titulo?: string; resumen?: string }).titulo ??
                        "",
                    )}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatearFechaHora(ev.creado)}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function TarjetaWebhook({ webhook }: { webhook: Webhook }) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE });

  const alternar = useMutation({
    mutationFn: () => api.actualizarWebhook(webhook.id, { activo: !webhook.activo }),
    onSuccess: invalidar,
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: () => api.eliminarWebhook(webhook.id),
    onSuccess: () => {
      toast.success("Webhook borrado.");
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const probar = useMutation({
    mutationFn: () => api.probarWebhook(webhook.id),
    onSuccess: (r) => {
      if (r.ok) toast.success(`Entrega de prueba correcta (${r.estado}).`);
      else toast.error(`La prueba falló: ${r.estado}.`);
      invalidar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const escuchaTodos = webhook.eventos.length === 0;

  const acciones: EntradaMenuContextual[] = [
    {
      etiqueta: "Probar",
      icono: Send,
      onClick: () => probar.mutate(),
      deshabilitado: probar.isPending,
    },
    {
      etiqueta: webhook.activo ? "Pausar" : "Activar",
      icono: webhook.activo ? Pause : Play,
      onClick: () => alternar.mutate(),
      deshabilitado: alternar.isPending,
    },
    { separador: true },
    {
      etiqueta: "Borrar",
      icono: Trash2,
      onClick: async () => {
        if (
          await confirmar({
            mensaje: `¿Borrar el webhook “${webhook.nombre || webhook.url}”? Esta acción no se puede deshacer.`,
            destructivo: true,
            textoConfirmar: "Borrar",
          })
        )
          eliminar.mutate();
      },
      destructivo: true,
      deshabilitado: eliminar.isPending,
    },
  ];

  return (
    <FilaConAcciones
      como="div"
      acciones={acciones}
      etiquetaAcciones={`Acciones del webhook “${webhook.nombre || webhook.url}”`}
      kebab="nunca"
      realce
      className="rounded-lg border border-border bg-card text-card-foreground shadow-sm"
    >
      <CardHeader className="pb-3 pr-10">
        <div className="min-w-0">
          <CardTitle className="flex items-center gap-2 text-base">
            {webhook.nombre || "(sin nombre)"}
            <Badge variant={webhook.activo ? "default" : "secondary"}>
              {webhook.activo ? "Activo" : "Pausado"}
            </Badge>
            <Badge variant="outline">{ETIQUETA_FORMATO[webhook.formato]}</Badge>
            {webhook.tiene_secreto && <Badge variant="outline">Firmado</Badge>}
          </CardTitle>
          <CardDescription className="mt-1 break-all">{webhook.url}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-2 text-sm">
        {escuchaTodos ? (
          <Badge variant="secondary">Todos los eventos</Badge>
        ) : (
          webhook.eventos.map((ev) => (
            <Badge key={ev} variant="secondary">
              {ETIQUETA_EVENTO[ev] ?? ev}
            </Badge>
          ))
        )}
        {webhook.ultimo_estado && (
          <span className="ml-auto text-xs text-muted-foreground">
            Última entrega: {webhook.ultimo_estado}
          </span>
        )}
      </CardContent>
    </FilaConAcciones>
  );
}

function DialogoCrearWebhook({
  abierto,
  onAbierto,
  eventos,
  formatos,
}: {
  abierto: boolean;
  onAbierto: (v: boolean) => void;
  eventos: TipoEventoInterno[];
  formatos: FormatoWebhook[];
}) {
  const queryClient = useQueryClient();
  const [nombre, setNombre] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [secreto, setSecreto] = React.useState("");
  const [formato, setFormato] = React.useState<FormatoWebhook>("slack");
  const [seleccion, setSeleccion] = React.useState<TipoEventoInterno[]>([]);
  // El error solo se muestra tras un intento de crear (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  const reset = () => {
    setNombre("");
    setUrl("");
    setSecreto("");
    setFormato("slack");
    setSeleccion([]);
    setIntentado(false);
  };

  const crear = useMutation({
    mutationFn: () => {
      const cuerpo: CuerpoCrearWebhook = {
        nombre: nombre.trim(),
        url: url.trim(),
        eventos: seleccion,
        formato,
        secreto: secreto.trim(),
        activo: true,
      };
      return api.crearWebhook(cuerpo);
    },
    onSuccess: () => {
      toast.success("Webhook creado.");
      void queryClient.invalidateQueries({ queryKey: CLAVE });
      reset();
      onAbierto(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const alternarEvento = (ev: TipoEventoInterno) => {
    setSeleccion((prev) =>
      prev.includes(ev) ? prev.filter((x) => x !== ev) : [...prev, ev],
    );
  };

  const errUrl = !url.trim() ? "La URL es obligatoria." : null;
  const hayErrores = Boolean(errUrl);

  const onCrear = () => {
    setIntentado(true);
    if (hayErrores) return;
    crear.mutate();
  };

  return (
    <Dialog open={abierto} onOpenChange={onAbierto}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo webhook</DialogTitle>
          <DialogDescription>
            POST a esta URL en eventos. Usa Incoming Webhook de Slack.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <Campo etiqueta="Nombre" htmlFor="wh-nombre">
            <Input
              id="wh-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Canal de redes (Slack)"
            />
          </Campo>
          <Campo etiqueta="URL" htmlFor="wh-url" error={intentado ? errUrl : null}>
            <Input
              id="wh-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
              aria-invalid={(intentado && Boolean(errUrl)) || undefined}
            />
          </Campo>
          <Campo etiqueta="Formato">
            <Select value={formato} onValueChange={(v) => setFormato(v as FormatoWebhook)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {formatos.map((f) => (
                  <SelectItem key={f} value={f}>
                    {ETIQUETA_FORMATO[f] ?? f}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Campo>
          <Campo etiqueta="Eventos" ayuda="Opcional: déjalo en blanco para escuchar todos.">
            <div className="grid gap-2">
              {eventos.map((ev) => (
                <Label key={ev} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={seleccion.includes(ev)}
                    onCheckedChange={() => alternarEvento(ev)}
                    aria-label={ETIQUETA_EVENTO[ev] ?? ev}
                  />
                  {ETIQUETA_EVENTO[ev] ?? ev}
                </Label>
              ))}
            </div>
          </Campo>
          <Campo etiqueta="Secreto (opcional)" htmlFor="wh-secreto">
            <Input
              id="wh-secreto"
              value={secreto}
              onChange={(e) => setSecreto(e.target.value)}
              placeholder="Para firmar cada entrega (X-Keni-Signature)"
            />
          </Campo>
        </div>

        <DialogFooter>
          <Button onClick={onCrear} disabled={crear.isPending}>
            Crear webhook
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
