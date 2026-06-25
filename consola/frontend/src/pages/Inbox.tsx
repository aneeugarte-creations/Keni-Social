/**
 * Inbox (solo lectura): los mensajes directos y los comentarios de la audiencia en
 * Facebook e Instagram, para que el equipo los lea y actúe con criterio. No se responde
 * ni se escribe desde aquí (la respuesta vive fuera de la consola).
 *
 * La marca la MANDA el switch global de la barra superior (igual que Analíticas): no hay
 * selector propio. Sin marca concreta ("Todas", solo admin) no hay buzón que mostrar, así
 * que se pide enfocar una marca. La marca viaja a la API en forma id_metricas (guion_bajo).
 */
import { useQuery } from "@tanstack/react-query";
import { Inbox as IconoInbox, MessageSquare, MessagesSquare } from "lucide-react";
import * as React from "react";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { marcaMetricasDesdeCanonica } from "@/components/comunes/selectores";
import { Spinner } from "@/components/ui/spinner";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api } from "@/lib/api";

import { PanelComentarios } from "./inbox/PanelComentarios";
import { PanelConversaciones } from "./inbox/PanelConversaciones";

/** Ventanas ofrecidas para los comentarios (días). El backend acepta 1..30 (def 7). */
const DIAS_OPCIONES: Array<{ valor: string; etiqueta: string }> = [
  { valor: "1", etiqueta: "Último día" },
  { valor: "7", etiqueta: "Últimos 7 días" },
  { valor: "14", etiqueta: "Últimos 14 días" },
  { valor: "30", etiqueta: "Últimos 30 días" },
];

/** Espera centrada y tolerante a segundos (los comentarios se trocean por día en el backend). */
function Cargando({ nota }: { nota?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 py-16 text-muted-foreground">
      <Spinner className="h-6 w-6" />
      <p className="text-sm">Cargando…</p>
      {nota && <p className="text-xs">{nota}</p>}
    </div>
  );
}

function VistaConversaciones({ marca }: { marca: string }) {
  const consulta = useQuery({
    queryKey: ["inbox", "conversaciones", marca],
    queryFn: ({ signal }) => api.inboxConversaciones({ marca }, signal),
  });

  if (consulta.isPending) return <Cargando />;
  if (consulta.isError) {
    return (
      <BloqueError
        titulo="No se pudieron cargar los mensajes"
        mensaje={consulta.error instanceof Error ? consulta.error.message : undefined}
        onReintentar={() => consulta.refetch()}
        cargando={consulta.isFetching}
      />
    );
  }
  return <PanelConversaciones porRed={consulta.data.por_red} />;
}

function VistaComentarios({ marca }: { marca: string }) {
  const [dias, setDias] = React.useState("7");
  const consulta = useQuery({
    queryKey: ["inbox", "comentarios", marca, dias],
    queryFn: ({ signal }) => api.inboxComentarios({ marca, dias }, signal),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Periodo</span>
        <Select value={dias} onValueChange={setDias}>
          <SelectTrigger className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DIAS_OPCIONES.map((o) => (
              <SelectItem key={o.valor} value={o.valor}>
                {o.etiqueta}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {consulta.isPending ? (
        <Cargando nota="Reunir los comentarios de varios días puede tardar unos segundos." />
      ) : consulta.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los comentarios"
          mensaje={consulta.error instanceof Error ? consulta.error.message : undefined}
          onReintentar={() => consulta.refetch()}
          cargando={consulta.isFetching}
        />
      ) : (
        <PanelComentarios porRed={consulta.data.por_red} />
      )}
    </div>
  );
}

export default function Inbox() {
  // La marca activa global (id canónico, o null = "Todas"). El buzón es por marca.
  const { marcaActiva } = useMarcaActiva();
  const [tab, setTab] = React.useState("mensajes");

  if (!marcaActiva) {
    return (
      <EstadoVacio
        icono={IconoInbox}
        titulo="Elige una marca"
        texto="El buzón muestra los mensajes y comentarios de una marca. Selecciona una marca concreta en el control de arriba para verlos."
      />
    );
  }

  const marca = marcaMetricasDesdeCanonica(marcaActiva);

  // El título de la sección lo pinta la subnav del hub («Buzón») en la barra superior; el cuerpo va
  // a ancho completo, como Métricas y Campañas (sin cabecera ni columna centrada propias).
  return (
    <div className="space-y-4">
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="mensajes">
            <MessagesSquare className="h-4 w-4" aria-hidden="true" />
            Mensajes directos
          </TabsTrigger>
          <TabsTrigger value="comentarios">
            <MessageSquare className="h-4 w-4" aria-hidden="true" />
            Comentarios
          </TabsTrigger>
        </TabsList>
        <TabsContent value="mensajes">
          <VistaConversaciones marca={marca} />
        </TabsContent>
        <TabsContent value="comentarios">
          <VistaComentarios marca={marca} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
