/**
 * PanelEventos — alta, filtrado y edición de los EVENTOS a cubrir de la rota.
 *
 * Extraído de `pages/Rota.tsx` (ola "Calendario = turnos / Fuentes = eventos"): la
 * gestión de eventos dejó de vivir en el Calendario y ahora habita en el hub de
 * Fuentes/Investigación (`pages/EventosCobertura.tsx`). El componente es autónomo y
 * reutiliza los endpoints existentes `/api/rota/eventos` (sin tocar coverage ni la
 * rejilla de turnos). Mantiene la persistencia de filtros en la URL.
 *
 * NO es destructivo: la lógica de cobertura (rejilla de turnos) sigue intacta en el
 * Calendario; aquí solo se reubica la superficie de gestión de eventos.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CalendarPlus,
  CheckCircle2,
  Copy,
  Loader2,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { MARCA_TODAS } from "@/components/comunes/selectores";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useMarcaActiva } from "@/hooks/marca-activa-contexto";
import { api, mensajeError } from "@/lib/api";
import { COBERTURA, COLOR_PRIORIDAD } from "@/lib/rota-calendario";
import type { EventoRota, PrioridadEvento, TipoCoberturaEvento } from "@/types";

// `TIPOS_COBERTURA` y `PRIORIDADES` son las opciones de los selects/chips. Antes
// vivían en Rota.tsx; las copiamos aquí para que el panel sea autónomo (la fuente de
// verdad de presentación `COBERTURA`/`COLOR_PRIORIDAD` sigue en rota-calendario).
const TIPOS_COBERTURA: { valor: TipoCoberturaEvento; etiqueta: string }[] = [
  { valor: "transmision", etiqueta: "Transmisión (con señal)" },
  { valor: "imagenes", etiqueta: "Solo imágenes / fotografías" },
  { valor: "no_cubrir", etiqueta: "No cubrir" },
];

const PRIORIDADES: { valor: PrioridadEvento; etiqueta: string }[] = [
  { valor: "alta", etiqueta: "Alta" },
  { valor: "media", etiqueta: "Media" },
  { valor: "baja", etiqueta: "Baja" },
];

// --- Utilidades de fecha/hora ---------------------------------------------

function formatearFechaCorta(s: string): string {
  if (!s) return "";
  const d = new Date(`${s}T00:00:00`);
  if (Number.isNaN(d.getTime())) return s;
  return d.toLocaleDateString("es-MX", { weekday: "short", day: "numeric", month: "short" });
}

/** Convierte "HH:MM" a minutos desde 00:00. Devuelve `null` si no parsea. */
function horaAMinutos(s: string): number | null {
  const m = s.match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  const h = Number(m[1]);
  const mi = Number(m[2]);
  if (!Number.isFinite(h) || !Number.isFinite(mi)) return null;
  if (h < 0 || h > 23 || mi < 0 || mi > 59) return null;
  return h * 60 + mi;
}

/** Hoy en formato ISO AAAA-MM-DD (hora local; usa `Date` del navegador). */
function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** ISO + N días (no recalcula la hora; se usa para "Duplicar último"). */
function diasSiguientes(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + n);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

/** Primer día del MES en curso, en ISO AAAA-MM-DD. */
function primerDiaMes(d: Date): string {
  const f = new Date(d.getFullYear(), d.getMonth(), 1);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, "0")}-01`;
}

/** Último día del MES en curso, en ISO AAAA-MM-DD. */
function ultimoDiaMes(d: Date): string {
  const f = new Date(d.getFullYear(), d.getMonth() + 1, 0);
  return `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, "0")}-${String(
    f.getDate(),
  ).padStart(2, "0")}`;
}

// --- Filtros (persistidos en la URL) --------------------------------------

/** Estado tri-estado del filtro "Cambiado" representado como string en la URL. */
type FiltroCambiado = "todos" | "si" | "no";

/** Lee y normaliza los filtros desde la URL (search params). Defaults = mes en curso. */
function leerFiltrosDesdeUrl(sp: URLSearchParams): {
  desde: string;
  hasta: string;
  tiposCobertura: TipoCoberturaEvento[];
  prioridades: PrioridadEvento[];
  cambiado: FiltroCambiado;
  q: string;
} {
  const hoy = new Date();
  const desde = sp.get("desde") ?? primerDiaMes(hoy);
  const hasta = sp.get("hasta") ?? ultimoDiaMes(hoy);
  const tiposCobertura = sp
    .getAll("tipo_cobertura")
    .filter((v): v is TipoCoberturaEvento => v === "transmision" || v === "imagenes" || v === "no_cubrir");
  const prioridades = sp
    .getAll("prioridad")
    .filter((v): v is PrioridadEvento => v === "alta" || v === "media" || v === "baja");
  const cambiadoCrudo = (sp.get("cambiado") ?? "").toLowerCase();
  const cambiado: FiltroCambiado =
    cambiadoCrudo === "true" || cambiadoCrudo === "si"
      ? "si"
      : cambiadoCrudo === "false" || cambiadoCrudo === "no"
        ? "no"
        : "todos";
  const q = sp.get("q") ?? "";
  return { desde, hasta, tiposCobertura, prioridades, cambiado, q };
}

/** Convierte los filtros a `URLSearchParams` (omite defaults para una URL limpia). */
function filtrosAUrl(args: {
  desde: string;
  hasta: string;
  tiposCobertura: TipoCoberturaEvento[];
  prioridades: PrioridadEvento[];
  cambiado: FiltroCambiado;
  q: string;
}): URLSearchParams {
  const sp = new URLSearchParams();
  const hoy = new Date();
  if (args.desde && args.desde !== primerDiaMes(hoy)) sp.set("desde", args.desde);
  if (args.hasta && args.hasta !== ultimoDiaMes(hoy)) sp.set("hasta", args.hasta);
  for (const t of args.tiposCobertura) sp.append("tipo_cobertura", t);
  for (const p of args.prioridades) sp.append("prioridad", p);
  if (args.cambiado === "si") sp.set("cambiado", "true");
  else if (args.cambiado === "no") sp.set("cambiado", "false");
  if (args.q.trim()) sp.set("q", args.q.trim());
  return sp;
}

/** Botón "marcar avisado": limpia el flag `cambiado` de un evento (PATCH cambiado:false). */
function BotonMarcarAvisado({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const marcar = useMutation({
    mutationFn: () => api.actualizarEventoRota(evento.id, { cambiado: false }),
    onSuccess: () => {
      toast.success("Marcado como avisado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-6 gap-1 px-1.5 text-[11px] text-amber-700 dark:text-amber-400"
      onClick={() => marcar.mutate()}
      disabled={marcar.isPending}
    >
      {marcar.isPending ? (
        <Loader2 className="h-3 w-3 animate-spin" />
      ) : (
        <CheckCircle2 className="h-3 w-3" />
      )}
      Marcar avisado
    </Button>
  );
}

/** Botón toggle de chip (multi-select). Reutiliza `Button` con dos variantes. */
function ChipToggle({
  activo,
  onClick,
  children,
}: {
  activo: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      size="sm"
      variant={activo ? "default" : "outline"}
      className="h-7 px-2.5 text-xs"
      onClick={onClick}
      aria-pressed={activo}
    >
      {children}
    </Button>
  );
}

function FiltrosEventos({
  estado,
  setEstado,
  onLimpiar,
  total,
}: {
  estado: ReturnType<typeof leerFiltrosDesdeUrl>;
  setEstado: (next: ReturnType<typeof leerFiltrosDesdeUrl>) => void;
  onLimpiar: () => void;
  total: number;
}) {
  const togglearCobertura = (t: TipoCoberturaEvento) => {
    const dentro = estado.tiposCobertura.includes(t);
    setEstado({
      ...estado,
      tiposCobertura: dentro
        ? estado.tiposCobertura.filter((x) => x !== t)
        : [...estado.tiposCobertura, t],
    });
  };
  const togglearPrioridad = (p: PrioridadEvento) => {
    const dentro = estado.prioridades.includes(p);
    setEstado({
      ...estado,
      prioridades: dentro
        ? estado.prioridades.filter((x) => x !== p)
        : [...estado.prioridades, p],
    });
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-3">
        <CardTitle className="text-base">Filtros</CardTitle>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>
            {total} evento{total === 1 ? "" : "s"}
          </span>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 gap-1 px-2 text-xs"
            onClick={onLimpiar}
          >
            <X className="h-3.5 w-3.5" /> Limpiar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="filtro-desde">Desde</Label>
            <Input
              id="filtro-desde"
              type="date"
              value={estado.desde}
              onChange={(e) => setEstado({ ...estado, desde: e.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filtro-hasta">Hasta</Label>
            <Input
              id="filtro-hasta"
              type="date"
              value={estado.hasta}
              onChange={(e) => setEstado({ ...estado, hasta: e.target.value })}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Cobertura</Label>
          <div className="flex flex-wrap gap-1.5">
            {TIPOS_COBERTURA.map((t) => (
              <ChipToggle
                key={t.valor}
                activo={estado.tiposCobertura.includes(t.valor)}
                onClick={() => togglearCobertura(t.valor)}
              >
                {COBERTURA[t.valor].etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Prioridad</Label>
          <div className="flex flex-wrap gap-1.5">
            {PRIORIDADES.map((p) => (
              <ChipToggle
                key={p.valor}
                activo={estado.prioridades.includes(p.valor)}
                onClick={() => togglearPrioridad(p.valor)}
              >
                {p.etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label>Cambiado</Label>
          <div className="flex flex-wrap gap-1.5">
            {(
              [
                { valor: "todos", etiqueta: "Todos" },
                { valor: "si", etiqueta: "Sí" },
                { valor: "no", etiqueta: "No" },
              ] as { valor: FiltroCambiado; etiqueta: string }[]
            ).map((opt) => (
              <ChipToggle
                key={opt.valor}
                activo={estado.cambiado === opt.valor}
                onClick={() => setEstado({ ...estado, cambiado: opt.valor })}
              >
                {opt.etiqueta}
              </ChipToggle>
            ))}
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="filtro-q">Buscar</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="filtro-q"
              value={estado.q}
              onChange={(e) => setEstado({ ...estado, q: e.target.value })}
              placeholder="Buscar en título y qué sacar…"
              className="pl-8"
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function NuevoEvento({
  onCreado,
  ultimoEventoUsuario,
  marcaDefecto,
}: {
  onCreado: () => void;
  /**
   * El último evento de la lista (el más reciente según la API). Si está presente, el
   * botón "Duplicar último" lo clona con fecha=hoy (o +1 si ya hay uno hoy).
   */
  ultimoEventoUsuario?: EventoRota | null;
  /** Marca activa del workspace: se usa como valor por defecto del campo marca. */
  marcaDefecto?: string | null;
}) {
  const { marcasParaSwitch } = useMarcaActiva();
  const [titulo, setTitulo] = React.useState("");
  // Fecha default = hoy (el caso típico es dar de alta el evento del día).
  const [fecha, setFecha] = React.useState<string>(() => hoyIso());
  const [hora, setHora] = React.useState("");
  const [contenido, setContenido] = React.useState("");
  const [tipoCobertura, setTipoCobertura] = React.useState<TipoCoberturaEvento>("transmision");
  const [prioridad, setPrioridad] = React.useState<PrioridadEvento>("media");
  // `marca`: arranca en la marca activa del workspace; "todas" = sin marca (MARCA_TODAS).
  const [marca, setMarca] = React.useState<string>(() => marcaDefecto ?? MARCA_TODAS);
  // Si la marca activa cambia desde fuera (el usuario cambia de workspace), actualizamos el default.
  React.useEffect(() => {
    setMarca(marcaDefecto ?? MARCA_TODAS);
  }, [marcaDefecto]);
  // Validación inline de hora HH:MM al submit. El campo permite texto libre para no
  // molestar mientras escribes; el error sale solo al intentar guardar y se borra al editar.
  const [errorHora, setErrorHora] = React.useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () =>
      api.crearEventoRota({
        titulo: titulo.trim(),
        fecha,
        hora: hora.trim(),
        contenido: contenido.trim(),
        tipo_cobertura: tipoCobertura,
        prioridad,
        marca: marca === MARCA_TODAS ? "" : marca,
      }),
    onSuccess: () => {
      toast.success("Evento creado.");
      setTitulo("");
      setHora("");
      setContenido("");
      setTipoCobertura("transmision");
      setPrioridad("media");
      setErrorHora(null);
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const duplicarUltimo = useMutation({
    mutationFn: () => {
      if (!ultimoEventoUsuario) return Promise.reject(new Error("Sin último evento"));
      // Si el último ya es de hoy, avanza un día para evitar duplicado idéntico.
      const fechaDestino =
        ultimoEventoUsuario.fecha === hoyIso()
          ? diasSiguientes(hoyIso(), 1)
          : hoyIso();
      return api.duplicarEventoRota(ultimoEventoUsuario.id, { fecha: fechaDestino });
    },
    onSuccess: () => {
      toast.success("Evento duplicado.");
      onCreado();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  function intentarCrear() {
    // Validación HH:MM: `horaAMinutos` admite el formato canónico; rechazamos lo demás.
    // La hora es OPCIONAL: si está vacía, se acepta tal cual (sin validar).
    const trimmed = hora.trim();
    if (trimmed && horaAMinutos(trimmed) === null) {
      setErrorHora("Formato HH:MM (ej. 16:30).");
      return;
    }
    setErrorHora(null);
    crear.mutate();
  }

  const puedeCrear = titulo.trim().length > 0 && fecha !== "" && !crear.isPending;

  return (
    <Card className="h-fit">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <CalendarPlus className="h-4 w-4" /> Nuevo evento
          </CardTitle>
          {ultimoEventoUsuario && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => duplicarUltimo.mutate()}
              disabled={duplicarUltimo.isPending}
              title={`Duplicar «${ultimoEventoUsuario.titulo}»`}
            >
              {duplicarUltimo.isPending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
              Duplicar último
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="ev-titulo">Evento / transmisión</Label>
          <Input
            id="ev-titulo"
            value={titulo}
            onChange={(e) => setTitulo(e.target.value)}
            placeholder="Ej. Cruz Azul vs América"
            maxLength={200}
          />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="ev-fecha">Fecha</Label>
            <Input id="ev-fecha" type="date" value={fecha} onChange={(e) => setFecha(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ev-hora">Hora</Label>
            <Input
              id="ev-hora"
              value={hora}
              onChange={(e) => {
                setHora(e.target.value);
                if (errorHora) setErrorHora(null);
              }}
              placeholder="16:00"
              maxLength={40}
              aria-invalid={errorHora ? true : undefined}
            />
            {errorHora && (
              <p className="text-xs text-destructive">{errorHora}</p>
            )}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Cobertura</Label>
            <Select
              value={tipoCobertura}
              onValueChange={(v) => setTipoCobertura(v as TipoCoberturaEvento)}
            >
              <SelectTrigger aria-label="Tipo de cobertura">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIPOS_COBERTURA.map((t) => (
                  <SelectItem key={t.valor} value={t.valor}>
                    {t.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Prioridad</Label>
            <Select value={prioridad} onValueChange={(v) => setPrioridad(v as PrioridadEvento)}>
              <SelectTrigger aria-label="Prioridad">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORIDADES.map((p) => (
                  <SelectItem key={p.valor} value={p.valor}>
                    {p.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {marcasParaSwitch.length > 0 && (
          <div className="space-y-1.5">
            <Label htmlFor="ev-marca">
              Marca <span className="font-normal text-muted-foreground">(opcional)</span>
            </Label>
            <SelectorMarca
              id="ev-marca"
              marcas={marcasParaSwitch}
              valor={marca}
              onCambio={setMarca}
              incluirTodas
              etiquetaTodas="Sin marca"
              className="w-full"
              ariaLabel="Marca del evento"
            />
          </div>
        )}
        <div className="space-y-1.5">
          <Label htmlFor="ev-contenido">
            Qué sacar <span className="font-normal text-muted-foreground">(opcional)</span>
          </Label>
          <Textarea
            id="ev-contenido"
            value={contenido}
            onChange={(e) => setContenido(e.target.value)}
            placeholder="Clip del gol, resumen 1 min, frase del DT…"
            rows={3}
            maxLength={2000}
          />
        </div>
        <div className="flex justify-end">
          <Button onClick={intentarCrear} disabled={!puedeCrear}>
            {crear.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Crear evento
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TarjetaEvento({ evento, onCambio }: { evento: EventoRota; onCambio: () => void }) {
  const borrar = useMutation({
    mutationFn: () => api.eliminarEventoRota(evento.id),
    onSuccess: () => {
      toast.success("Evento eliminado.");
      onCambio();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  // Edición inline de cobertura/prioridad (cambiar cobertura reprograma -> "Cambió").
  const editar = useMutation({
    mutationFn: (cuerpo: { tipo_cobertura?: TipoCoberturaEvento; prioridad?: PrioridadEvento }) =>
      api.actualizarEventoRota(evento.id, cuerpo),
    onSuccess: () => onCambio(),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const cob = COBERTURA[evento.tipo_cobertura] ?? COBERTURA.transmision;
  const IconoCob = cob.icono;

  return (
    <Card>
      <CardContent className="flex items-start justify-between gap-3 p-4">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium">{evento.titulo}</span>
            <Badge variant="outline" className={`gap-1 font-normal ${cob.chip}`}>
              <IconoCob className="h-3 w-3" /> {cob.etiqueta}
            </Badge>
            {evento.marca_nombre && (
              <Badge variant="secondary" className="font-normal">
                {evento.marca_nombre}
              </Badge>
            )}
            {evento.es_sabado && (
              <Badge variant="outline" className="font-normal">
                Sábado
              </Badge>
            )}
            {evento.cambiado && (
              <Badge variant="aviso" className="gap-1 font-normal">
                <BellRing className="h-3 w-3" /> Cambió
              </Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {formatearFechaCorta(evento.fecha)}
            {evento.hora ? ` · ${evento.hora}` : ""}
            {" · "}
            <span className={COLOR_PRIORIDAD[evento.prioridad]}>prioridad {evento.prioridad}</span>
          </div>
          {evento.contenido && (
            <div className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">Qué sacar: </span>
              {evento.contenido}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Select
              value={evento.tipo_cobertura}
              onValueChange={(v) => editar.mutate({ tipo_cobertura: v as TipoCoberturaEvento })}
              disabled={editar.isPending}
            >
              <SelectTrigger aria-label="Cambiar cobertura" className="h-8 w-[11rem] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIPOS_COBERTURA.map((t) => (
                  <SelectItem key={t.valor} value={t.valor}>
                    {t.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={evento.prioridad}
              onValueChange={(v) => editar.mutate({ prioridad: v as PrioridadEvento })}
              disabled={editar.isPending}
            >
              <SelectTrigger aria-label="Cambiar prioridad" className="h-8 w-[7rem] text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIORIDADES.map((p) => (
                  <SelectItem key={p.valor} value={p.valor}>
                    {p.etiqueta}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {evento.cambiado && <BotonMarcarAvisado evento={evento} onCambio={onCambio} />}
          </div>
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Borrar evento"
          className="text-muted-foreground hover:text-destructive"
          onClick={() => borrar.mutate()}
          disabled={borrar.isPending}
        >
          {borrar.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Trash2 className="h-4 w-4" />
          )}
        </Button>
      </CardContent>
    </Card>
  );
}

/**
 * Panel completo de eventos: formulario de alta + filtros (persistidos en URL) + lista.
 * Reutilizable: lo monta `pages/EventosCobertura.tsx` (hub de Fuentes). Antes vivía
 * inline en la pestaña "Eventos" del Calendario (`pages/Rota.tsx`).
 */
export function PanelEventos() {
  const queryClient = useQueryClient();
  const { marcaActiva } = useMarcaActiva();
  const [searchParams, setSearchParams] = useSearchParams();
  const estado = React.useMemo(() => leerFiltrosDesdeUrl(searchParams), [searchParams]);
  // Persistencia en URL: cada cambio refleja la URL (un refresh respeta el filtro).
  const setEstado = (next: ReturnType<typeof leerFiltrosDesdeUrl>) => {
    setSearchParams(filtrosAUrl(next), { replace: true });
  };
  const limpiar = () => setSearchParams(new URLSearchParams(), { replace: true });

  // La query depende de los filtros Y de la marca activa: se reejecuta cuando cambian.
  // `marcaActiva === null` → vista agregada "Todas" → sin filtro de marca.
  const clave = [
    "rota",
    "eventos",
    estado.desde,
    estado.hasta,
    estado.tiposCobertura.join(","),
    estado.prioridades.join(","),
    estado.cambiado,
    estado.q,
    marcaActiva ?? "",
  ] as const;
  const filtrosApi: Parameters<typeof api.rotaEventos>[0] = {
    desde: estado.desde || undefined,
    hasta: estado.hasta || undefined,
    tipo_cobertura: estado.tiposCobertura,
    prioridad: estado.prioridades,
    cambiado: estado.cambiado === "si" ? true : estado.cambiado === "no" ? false : undefined,
    q: estado.q || undefined,
    marca: marcaActiva ?? undefined,
  };
  const q = useQuery({
    queryKey: clave,
    queryFn: ({ signal }) => api.rotaEventos(filtrosApi, signal),
  });
  const eventos = q.data?.eventos ?? [];
  // "Último evento": heurística simple — el primero de la lista ordenada por la API
  // (más reciente). Se usa para "Duplicar último".
  const ultimoEventoUsuario = eventos[0] ?? null;
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: ["rota", "eventos"] });

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-[24rem_minmax(0,1fr)]">
        <NuevoEvento
          onCreado={invalidar}
          ultimoEventoUsuario={ultimoEventoUsuario}
          marcaDefecto={marcaActiva}
        />
        <div className="space-y-3">
          <FiltrosEventos
            estado={estado}
            setEstado={setEstado}
            onLimpiar={limpiar}
            total={eventos.length}
          />
          {q.isPending ? (
            <Skeleton className="h-40 w-full rounded-md" />
          ) : q.isError ? (
            <BloqueError
              titulo="No se pudieron cargar los eventos"
              mensaje={mensajeError(q.error)}
              onReintentar={() => void q.refetch()}
              cargando={q.isFetching}
            />
          ) : eventos.length === 0 ? (
            <EstadoVacio
              icono={CalendarPlus}
              titulo="Sin eventos"
              texto="Ajusta los filtros o da de alta nuevos eventos con el formulario."
            />
          ) : (
            eventos.map((e) => <TarjetaEvento key={e.id} evento={e} onCambio={invalidar} />)
          )}
        </div>
      </div>
    </div>
  );
}

export default PanelEventos;
