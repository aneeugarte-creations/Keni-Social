import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Send, ShieldAlert, Trash2, Webhook as WebhookIcon } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
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
  DialogTrigger,
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
import { api, ApiError } from "@/lib/api";
import type {
  CuerpoCrearWebhook,
  FormatoWebhook,
  TipoEventoInterno,
  Webhook,
} from "@/types";

const CLAVE = ["webhooks"] as const;

const CABECERA = {
  titulo: "Webhooks",
  descripcion:
    "Avisa a un canal (Slack u otro endpoint) cuando pasa algo en el tablero: una pieza " +
    "se aprueba, se publica o un contenido vence. Solo para administradores.",
};

/** Etiqueta humana de cada tipo de evento. */
const ETIQUETA_EVENTO: Record<TipoEventoInterno, string> = {
  "pieza.aprobada": "Pieza aprobada",
  "pieza.publicada": "Pieza publicada",
  "contenido.vencido": "Contenido vencido",
};

const ETIQUETA_FORMATO: Record<FormatoWebhook, string> = {
  generico: "Genérico (JSON)",
  slack: "Slack",
};

function mensajeError(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFechaHora(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("es-MX", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function Webhooks() {
  const query = useQuery({
    queryKey: CLAVE,
    queryFn: ({ signal }) => api.webhooks(signal),
  });

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;

  const catalogo = query.data?.catalogo;

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          !esProhibido && !query.isError && catalogo ? (
            <DialogoCrearWebhook
              eventos={catalogo.eventos}
              formatos={catalogo.formatos}
            />
          ) : undefined
        }
      />

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
          texto="Crea uno para que el equipo reciba un aviso cuando se aprueba, publica o vence contenido."
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

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
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
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => probar.mutate()}
              disabled={probar.isPending}
              title="Enviar un evento de prueba"
            >
              <Send className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => eliminar.mutate()}
              disabled={eliminar.isPending}
              title="Borrar webhook"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
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
        <span className="ml-auto flex items-center gap-2">
          {webhook.ultimo_estado && (
            <span className="text-xs text-muted-foreground">
              Última entrega: {webhook.ultimo_estado}
            </span>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={() => alternar.mutate()}
            disabled={alternar.isPending}
          >
            {webhook.activo ? "Pausar" : "Activar"}
          </Button>
        </span>
      </CardContent>
    </Card>
  );
}

function DialogoCrearWebhook({
  eventos,
  formatos,
}: {
  eventos: TipoEventoInterno[];
  formatos: FormatoWebhook[];
}) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);
  const [nombre, setNombre] = React.useState("");
  const [url, setUrl] = React.useState("");
  const [secreto, setSecreto] = React.useState("");
  const [formato, setFormato] = React.useState<FormatoWebhook>("slack");
  const [seleccion, setSeleccion] = React.useState<TipoEventoInterno[]>([]);

  const reset = () => {
    setNombre("");
    setUrl("");
    setSecreto("");
    setFormato("slack");
    setSeleccion([]);
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
      setAbierto(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const alternarEvento = (ev: TipoEventoInterno) => {
    setSeleccion((prev) =>
      prev.includes(ev) ? prev.filter((x) => x !== ev) : [...prev, ev],
    );
  };

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4" />
          Nuevo webhook
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo webhook</DialogTitle>
          <DialogDescription>
            La Consola hará un POST a esta URL cuando se dispare uno de los eventos. Para
            Slack, usa la URL de un Incoming Webhook.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label htmlFor="wh-nombre">Nombre</Label>
            <Input
              id="wh-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              placeholder="Canal de redes (Slack)"
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="wh-url">URL</Label>
            <Input
              id="wh-url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
            />
          </div>
          <div className="grid gap-1.5">
            <Label>Formato</Label>
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
          </div>
          <div className="grid gap-1.5">
            <Label>Eventos</Label>
            <p className="text-xs text-muted-foreground">
              Sin marcar ninguno, el webhook escucha todos.
            </p>
            <div className="grid gap-2">
              {eventos.map((ev) => (
                <label key={ev} className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={seleccion.includes(ev)}
                    onCheckedChange={() => alternarEvento(ev)}
                    aria-label={ETIQUETA_EVENTO[ev] ?? ev}
                  />
                  {ETIQUETA_EVENTO[ev] ?? ev}
                </label>
              ))}
            </div>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="wh-secreto">Secreto (opcional)</Label>
            <Input
              id="wh-secreto"
              value={secreto}
              onChange={(e) => setSecreto(e.target.value)}
              placeholder="Para firmar cada entrega (X-Keni-Signature)"
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            onClick={() => crear.mutate()}
            disabled={crear.isPending || !url.trim()}
          >
            Crear webhook
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
