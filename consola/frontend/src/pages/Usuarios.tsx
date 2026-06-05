import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Network,
  ShieldAlert,
  Trash2,
  UserPlus,
  Users,
} from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import "@/components/organigrama/org-tree.css";
import { Badge } from "@/components/ui/badge";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { formatearFecha as fmtFechaCdmx } from "@/lib/fecha";
import {
  cabezaDeArea,
  descendientes,
  hexAlpha,
  hijosPorManager,
  iniciales,
  indexarPorId,
  type IndiceUsuarios,
  metaZona,
  nombreVisible,
  raices,
  ZONA_DIRECCION,
  zonaDe,
  zonasOrdenadas,
} from "@/lib/organigrama";
import {
  CARGOS_ORDENADOS,
  type CargoUsuario,
  ETIQUETA_CARGO,
  etiquetaCargo,
  type MarcaDisponible,
  type RolUsuario,
  type UsuarioAdmin,
} from "@/types";

const CLAVE_USUARIOS = ["usuarios"] as const;
const CLAVE_OPCIONES_MARCAS = ["usuarios", "opciones", "marcas"] as const;

const CABECERA = {
  titulo: "Organigrama",
  descripcion:
    "El equipo como árbol jerárquico, con cada área definida por marca. Edita una persona " +
    "para cambiar su nombre, cargo, marcas y a quién reporta. Solo para administradores.",
};

const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

const ROLES: RolUsuario[] = ["editor", "admin"];

/** Centinelas de Select (shadcn no admite SelectItem con value=""). */
const SIN_CARGO = "__sin_cargo__";
const SIN_SUPERIOR = "__sin_superior__";

const MIN_PASSWORD = 8;

// Fecha en CDMX (instantes UTC del backend); ver `@/lib/fecha`.
const formatearFecha = (iso: string | null): string => fmtFechaCdmx(iso) || "—";

/**
 * Página del Organigrama (rediseño de "Usuarios"). Pinta el equipo como un árbol top-down
 * con las áreas coloreadas por marca, derivadas de la cabeza de cada área. Al hacer clic en
 * una persona se abre un panel para editar su perfil (nombre, cargo, rol, superior, marcas,
 * cobertura, coordinación), resetear su contraseña o eliminarla. El backend devuelve 403 si
 * quien entra no es admin (el nav ya oculta la página, pero avisamos si se llega por URL).
 */
export default function Usuarios() {
  const { usuario: actual } = useSesion();
  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
  });

  // Catálogo de marcas (canónico) para chips y el editor de marcas.
  const marcasQuery = useQuery({
    queryKey: CLAVE_OPCIONES_MARCAS,
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
    select: (data) => data.marcas,
    staleTime: 5 * 60 * 1000,
  });
  const catalogoMarcas = marcasQuery.data ?? [];

  const esProhibido =
    query.isError && query.error instanceof ApiError && query.error.status === 403;

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={
          !esProhibido && !query.isError ? (
            <DialogoCrearUsuario />
          ) : undefined
        }
      />

      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
          texto="Solo los administradores pueden ver y editar el organigrama."
        />
      ) : query.isPending ? (
        <Skeleton className="h-80 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudo cargar el organigrama"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : query.data.usuarios.length === 0 ? (
        <EstadoVacio
          icono={Users}
          titulo="No hay personas"
          texto="Crea la primera cuenta con el botón de arriba."
        />
      ) : (
        <OrganigramaArbol
          usuarios={query.data.usuarios}
          idActual={actual?.id ?? null}
          catalogoMarcas={catalogoMarcas}
        />
      )}
    </>
  );
}

// --- Árbol vertical (indentado) ----------------------------------------------

function OrganigramaArbol({
  usuarios,
  idActual,
  catalogoMarcas,
}: {
  usuarios: UsuarioAdmin[];
  idActual: string | null;
  catalogoMarcas: MarcaDisponible[];
}) {
  const porId = React.useMemo(() => indexarPorId(usuarios), [usuarios]);
  const hijos = React.useMemo(() => hijosPorManager(usuarios), [usuarios]);
  const cima = React.useMemo(() => raices(usuarios, porId), [usuarios, porId]);

  // Zonas presentes (para la leyenda): las marcas/transversal que tengan a alguien.
  const zonasPresentes = React.useMemo(() => {
    const set = new Set<string>();
    for (const u of usuarios) {
      const z = zonaDe(u, porId);
      if (z !== ZONA_DIRECCION) set.add(z);
    }
    return set;
  }, [usuarios, porId]);

  const [seleccionado, setSeleccionado] = React.useState<string | null>(null);
  const usuarioSel = seleccionado ? (porId.get(seleccionado) ?? null) : null;

  return (
    <div className="space-y-4">
      <Leyenda zonas={zonasPresentes} />

      <div className="org-v overflow-x-auto rounded-lg border bg-muted/20">
        <ul className="org-v-root">
          {cima.map((raiz) => {
            // Hijos del director ordenados por ÁREA (marca) para que cada zona quede
            // contigua; cada cabeza lleva su zona para colorear su rama.
            const areas = zonasOrdenadas(hijos.get(raiz.id) ?? []);
            return (
              <li key={raiz.id} className="org-v-node">
                <TarjetaMiembro
                  usuario={raiz}
                  zona={ZONA_DIRECCION}
                  esYoMismo={raiz.id === idActual}
                  onAbrir={setSeleccionado}
                />
                {areas.length > 0 && (
                  <ul className="org-v-children">
                    {areas.flatMap(({ zona, cabezas }) =>
                      cabezas.map((cabeza) => (
                        <NodoVertical
                          key={cabeza.id}
                          nodo={cabeza}
                          zona={zona}
                          hijos={hijos}
                          idActual={idActual}
                          onAbrir={setSeleccionado}
                        />
                      )),
                    )}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      </div>

      <DialogoMiembro
        usuario={usuarioSel}
        usuarios={usuarios}
        porId={porId}
        hijos={hijos}
        idActual={idActual}
        catalogoMarcas={catalogoMarcas}
        onCerrar={() => setSeleccionado(null)}
      />
    </div>
  );
}

/**
 * Nodo recursivo del árbol vertical: una tarjeta-fila y, indentado debajo, el subárbol de
 * sus reportes directos. `zona` (marca) se hereda hacia abajo y colorea la rama (conector
 * y acento de la tarjeta), así cada área se distingue por color.
 */
function NodoVertical({
  nodo,
  zona,
  hijos,
  idActual,
  onAbrir,
}: {
  nodo: UsuarioAdmin;
  zona: string;
  hijos: Map<string, UsuarioAdmin[]>;
  idActual: string | null;
  onAbrir: (id: string) => void;
}) {
  const reportes = hijos.get(nodo.id) ?? [];
  const meta = metaZona(zona);
  return (
    <li
      className="org-v-node"
      style={{ "--vline": meta.color } as React.CSSProperties}
    >
      <TarjetaMiembro
        usuario={nodo}
        zona={zona}
        esYoMismo={nodo.id === idActual}
        onAbrir={onAbrir}
      />
      {reportes.length > 0 && (
        <ul className="org-v-children">
          {reportes.map((r) => (
            <NodoVertical
              key={r.id}
              nodo={r}
              zona={zona}
              hijos={hijos}
              idActual={idActual}
              onAbrir={onAbrir}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

/** Tarjeta de una persona. Clic = abrir el panel de edición. */
function TarjetaMiembro({
  usuario,
  zona,
  esYoMismo,
  onAbrir,
}: {
  usuario: UsuarioAdmin;
  zona: string;
  esYoMismo: boolean;
  onAbrir: (id: string) => void;
}) {
  const meta = metaZona(zona);
  const marcas = usuario.marcas ?? [];
  const nombre = nombreVisible(usuario);

  return (
    <button
      type="button"
      onClick={() => onAbrir(usuario.id)}
      className="org-tarjeta flex w-[21rem] items-start gap-2.5 rounded-md border bg-card py-2 pl-2.5 pr-2 text-left shadow-sm transition-shadow hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ borderLeftColor: meta.color, borderLeftWidth: 4 }}
      aria-label={`Editar a ${nombre}`}
    >
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
        style={{ backgroundColor: meta.color }}
        aria-hidden
      >
        {iniciales(nombre)}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold leading-tight">
          {nombre}
          {esYoMismo && (
            <span className="ml-1 text-xs font-normal text-muted-foreground">(tú)</span>
          )}
        </span>
        <span className="block truncate text-xs text-muted-foreground">
          {etiquetaCargo((usuario.cargo ?? "") as CargoUsuario)}
        </span>
      </span>

      <span className="flex max-w-[8.5rem] shrink-0 flex-wrap justify-end gap-1">
        {usuario.rol === "admin" && (
          <Badge variant="default" className="h-5 px-1.5 text-[10px] font-medium">
            Admin
          </Badge>
        )}
        {usuario.cobertura && (
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
            Turnos
          </Badge>
        )}
        {usuario.puede_coordinar && (
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-normal">
            Coord.
          </Badge>
        )}
        {marcas.map((m) => (
          <Badge
            key={m}
            variant="outline"
            className="h-5 px-1.5 text-[10px] font-normal"
            style={{ borderColor: hexAlpha(metaZona(m).color, 0.5), color: metaZona(m).color }}
          >
            {metaZona(m).etiqueta}
          </Badge>
        ))}
      </span>
    </button>
  );
}

/** Leyenda de las áreas/marcas presentes en el organigrama. */
function Leyenda({ zonas }: { zonas: Set<string> }) {
  const ids = [...zonas];
  if (ids.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1.5">
        <Network className="h-3.5 w-3.5" /> Áreas:
      </span>
      {ids.map((z) => {
        const meta = metaZona(z);
        return (
          <span key={z} className="inline-flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {meta.etiqueta}
          </span>
        );
      })}
    </div>
  );
}

// --- Panel de edición de un miembro -----------------------------------------

/**
 * Panel para editar a una persona. Cada control guarda al instante (PATCH del campo que
 * cambia), igual que la antigua tabla, e invalida la query para redibujar el árbol. Incluye
 * el selector de SUPERIOR (organigrama), que excluye a la propia persona y a sus
 * descendientes para no ofrecer un cambio que cerraría un ciclo (el backend también lo
 * rechaza). Abajo, una zona de acciones sensibles: resetear contraseña y eliminar.
 */
function DialogoMiembro({
  usuario,
  usuarios,
  porId,
  hijos,
  idActual,
  catalogoMarcas,
  onCerrar,
}: {
  usuario: UsuarioAdmin | null;
  usuarios: UsuarioAdmin[];
  porId: IndiceUsuarios;
  hijos: Map<string, UsuarioAdmin[]>;
  idActual: string | null;
  catalogoMarcas: MarcaDisponible[];
  onCerrar: () => void;
}) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });

  // Estado local del nombre (edición libre, se guarda al salir del campo).
  const [nombre, setNombre] = React.useState("");
  React.useEffect(() => {
    setNombre((usuario?.nombre ?? "").trim());
  }, [usuario]);

  const guardar = useMutation({
    mutationFn: (cuerpo: Parameters<typeof api.actualizarUsuario>[1]) =>
      api.actualizarUsuario(usuario!.id, cuerpo),
    onSuccess: () => {
      invalidar();
      toast.success("Cambios guardados");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const eliminar = useMutation({
    mutationFn: () => api.eliminarUsuario(usuario!.id),
    onSuccess: () => {
      invalidar();
      toast.success(`${usuario ? nombreVisible(usuario) : "Usuario"} eliminado`);
      onCerrar();
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const resetear = useMutation({
    mutationFn: (password: string) => api.actualizarUsuario(usuario!.id, { password }),
    onSuccess: () => toast.success("Contraseña restablecida"),
    onError: (e) => toast.error(mensajeError(e)),
  });

  const [password, setPassword] = React.useState("");
  const [confirmarBorrado, setConfirmarBorrado] = React.useState(false);
  React.useEffect(() => {
    setPassword("");
    setConfirmarBorrado(false);
  }, [usuario]);

  if (usuario === null) {
    return <Dialog open={false} onOpenChange={() => onCerrar()} />;
  }

  const esYoMismo = usuario.id === idActual;
  const cargoActual = (usuario.cargo ?? "") as CargoUsuario;
  const marcasUsuario = new Set(usuario.marcas ?? []);
  const superiorActual = (usuario.manager_id ?? "") || SIN_SUPERIOR;

  // Candidatos a superior: todos menos uno mismo y sus descendientes (evita ciclos).
  const prohibidos = descendientes(usuario.id, hijos);
  const candidatos = usuarios
    .filter((u) => u.id !== usuario.id && !prohibidos.has(u.id))
    .sort((a, b) => nombreVisible(a).localeCompare(nombreVisible(b), "es"));

  const cabeza = cabezaDeArea(usuario, porId);
  const zona = zonaDe(usuario, porId);
  const meta = metaZona(zona);

  const guardarNombre = () => {
    const limpio = nombre.trim();
    if (limpio !== (usuario.nombre ?? "").trim()) guardar.mutate({ nombre: limpio });
  };

  return (
    <Dialog open onOpenChange={(v) => (!v ? onCerrar() : undefined)}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: meta.color }}
            />
            {nombreVisible(usuario)}
          </DialogTitle>
          <DialogDescription>
            @{usuario.usuario} · {meta.etiqueta}
            {cabeza && cabeza.id !== usuario.id ? ` · área de ${nombreVisible(cabeza)}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-1">
          {/* Nombre */}
          <div className="space-y-1.5">
            <Label htmlFor="m-nombre">Nombre</Label>
            <Input
              id="m-nombre"
              value={nombre}
              placeholder={usuario.usuario}
              maxLength={120}
              onChange={(e) => setNombre(e.target.value)}
              onBlur={guardarNombre}
              onKeyDown={(e) => {
                if (e.key === "Enter") (e.target as HTMLInputElement).blur();
              }}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Cargo */}
            <div className="space-y-1.5">
              <Label>Cargo</Label>
              <Select
                value={cargoActual === "" ? SIN_CARGO : cargoActual}
                onValueChange={(v) =>
                  guardar.mutate({ cargo: (v === SIN_CARGO ? "" : v) as CargoUsuario })
                }
              >
                <SelectTrigger className="h-9">
                  <SelectValue placeholder={etiquetaCargo("")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={SIN_CARGO}>{etiquetaCargo("")}</SelectItem>
                  {CARGOS_ORDENADOS.map((c) => (
                    <SelectItem key={c} value={c}>
                      {ETIQUETA_CARGO[c]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Rol de permisos */}
            <div className="space-y-1.5">
              <Label>Rol (permisos)</Label>
              <Select
                value={usuario.rol}
                onValueChange={(v) => guardar.mutate({ rol: v as RolUsuario })}
                disabled={esYoMismo}
              >
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {ROL_LABEL[r]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Superior (organigrama) */}
          <div className="space-y-1.5">
            <Label>Reporta a (superior)</Label>
            <Select
              value={superiorActual}
              onValueChange={(v) =>
                guardar.mutate({ manager_id: v === SIN_SUPERIOR ? "" : v })
              }
            >
              <SelectTrigger className="h-9">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={SIN_SUPERIOR}>Sin superior (raíz)</SelectItem>
                {candidatos.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {nombreVisible(u)}
                    {u.cargo ? ` · ${etiquetaCargo(u.cargo)}` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Define el árbol. La marca (área) sale de quién encabeza la cadena de reporte.
            </p>
          </div>

          {/* Marcas */}
          <div className="space-y-1.5">
            <Label>Marcas (verticales)</Label>
            <div className="grid grid-cols-2 gap-x-3 gap-y-2 rounded-md border p-3">
              {catalogoMarcas.length === 0 ? (
                <p className="col-span-2 text-sm text-muted-foreground">
                  No hay catálogo de marcas.
                </p>
              ) : (
                catalogoMarcas.map((m) => {
                  const id = `m-marca-${m.id}`;
                  return (
                    <div key={m.id} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={marcasUsuario.has(m.id)}
                        onCheckedChange={(v) => {
                          const nuevas = new Set(marcasUsuario);
                          if (v) nuevas.add(m.id);
                          else nuevas.delete(m.id);
                          guardar.mutate({ marcas: [...nuevas] });
                        }}
                      />
                      <Label htmlFor={id} className="cursor-pointer text-sm font-normal">
                        {m.nombre}
                      </Label>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Flags */}
          <div className="flex flex-wrap gap-x-6 gap-y-2">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={Boolean(usuario.cobertura)}
                onCheckedChange={(v) => guardar.mutate({ cobertura: Boolean(v) })}
              />
              Entra en la rota de turnos
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={Boolean(usuario.puede_coordinar)}
                onCheckedChange={(v) => guardar.mutate({ puede_coordinar: Boolean(v) })}
              />
              Puede coordinar
            </label>
          </div>

          <p className="text-xs text-muted-foreground">
            Alta: {formatearFecha(usuario.creado)} · Último acceso:{" "}
            {formatearFecha(usuario.ultimo_acceso)}
          </p>

          {/* Zona sensible */}
          <div className="space-y-3 rounded-md border border-destructive/30 bg-destructive/5 p-3">
            <p className="text-sm font-medium">Acciones sensibles</p>
            <div className="flex flex-wrap items-end gap-2">
              <div className="flex-1 space-y-1">
                <Label htmlFor="m-pass" className="text-xs">
                  Nueva contraseña
                </Label>
                <Input
                  id="m-pass"
                  type="password"
                  value={password}
                  autoComplete="new-password"
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={`Mínimo ${MIN_PASSWORD} caracteres`}
                />
              </div>
              <Button
                variant="outline"
                disabled={password.length < MIN_PASSWORD || resetear.isPending}
                onClick={() => {
                  resetear.mutate(password);
                  setPassword("");
                }}
              >
                {resetear.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                Resetear
              </Button>
            </div>

            {confirmarBorrado ? (
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm">¿Eliminar a {nombreVisible(usuario)}?</span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmarBorrado(false)}
                    disabled={eliminar.isPending}
                  >
                    Cancelar
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => eliminar.mutate()}
                    disabled={eliminar.isPending}
                  >
                    {eliminar.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    Eliminar
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:text-destructive"
                disabled={esYoMismo}
                onClick={() => setConfirmarBorrado(true)}
              >
                <Trash2 className="h-4 w-4" />
                {esYoMismo ? "No puedes eliminar tu propia cuenta" : "Eliminar persona"}
              </Button>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onCerrar}>
            Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// --- Crear usuario ----------------------------------------------------------

function DialogoCrearUsuario() {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);
  const [usuario, setUsuario] = React.useState("");
  const [nombre, setNombre] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [rol, setRol] = React.useState<RolUsuario>("editor");

  function reiniciar() {
    setUsuario("");
    setNombre("");
    setPassword("");
    setRol("editor");
  }

  const crear = useMutation({
    mutationFn: () =>
      api.crearUsuario({
        usuario: usuario.trim(),
        password,
        rol,
        nombre: nombre.trim() || undefined,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });
      toast.success("Usuario creado");
      setAbierto(false);
      reiniciar();
    },
    onError: (e) => {
      if (e instanceof ApiError && e.status === 409) {
        toast.error("Ya existe un usuario con ese nombre de cuenta.");
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const puedeEnviar =
    usuario.trim().length > 0 && password.length >= MIN_PASSWORD && !crear.isPending;

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setAbierto(v);
        if (!v) reiniciar();
      }}
    >
      <Button onClick={() => setAbierto(true)}>
        <UserPlus className="h-4 w-4" />
        Nueva persona
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva persona</DialogTitle>
          <DialogDescription>
            Crea una cuenta de acceso. Tras crearla, ábrela en el organigrama para asignarle
            cargo, marcas y a quién reporta. Deberá cambiar su contraseña al entrar.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeEnviar) crear.mutate();
          }}
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="nuevo-nombre">Nombre (organigrama)</Label>
            <Input
              id="nuevo-nombre"
              value={nombre}
              onChange={(e) => setNombre(e.target.value)}
              autoComplete="off"
              maxLength={120}
              placeholder="Opcional, p. ej. Diana Ramos"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nuevo-usuario">Usuario (login)</Label>
            <Input
              id="nuevo-usuario"
              value={usuario}
              onChange={(e) => setUsuario(e.target.value)}
              autoComplete="off"
              maxLength={120}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nuevo-password">Contraseña inicial</Label>
            <Input
              id="nuevo-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
            />
            <p className="text-xs text-muted-foreground">Mínimo {MIN_PASSWORD} caracteres.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nuevo-rol">Rol</Label>
            <Select value={rol} onValueChange={(v) => setRol(v as RolUsuario)}>
              <SelectTrigger id="nuevo-rol">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r}>
                    {ROL_LABEL[r]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!puedeEnviar}>
              {crear.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <UserPlus className="h-4 w-4" />
              )}
              Crear persona
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
