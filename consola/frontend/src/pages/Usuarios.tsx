import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Loader2, Plus, ShieldAlert, Trash2, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { BloqueError } from "@/components/comunes/BloqueError";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tooltip } from "@/components/ui/tooltip";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, ApiError } from "@/lib/api";
import type { RolUsuario, UsuarioAdmin } from "@/types";

const CLAVE_USUARIOS = ["usuarios"] as const;

const CABECERA = {
  titulo: "Usuarios",
  descripcion: "Gestiona las cuentas que acceden a la consola. Solo disponible para administradores.",
};

const ROL_LABEL: Record<RolUsuario, string> = {
  admin: "Administrador",
  editor: "Editor",
};

const ROLES: RolUsuario[] = ["editor", "admin"];

/** Longitud mínima de contraseña (espejo de la pantalla de cambio). */
const MIN_PASSWORD = 8;

function mensajeError(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Ocurrió un problema inesperado. Vuelve a intentarlo.";
}

function formatearFecha(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("es-MX", { day: "numeric", month: "short", year: "numeric" });
}

/**
 * Página de administración de usuarios (solo admin). Lista las cuentas y permite
 * crear, cambiar el rol, resetear la contraseña y eliminar (con confirmación).
 * Las rutas del backend devuelven 403 si el usuario no es admin: aunque el nav
 * ya oculta esta página, mostramos un aviso claro si se llega por URL directa.
 */
export default function Usuarios() {
  const { usuario: actual } = useSesion();
  const query = useQuery({
    queryKey: CLAVE_USUARIOS,
    queryFn: ({ signal }) => api.usuarios(signal),
  });

  const esProhibido = query.isError && query.error instanceof ApiError && query.error.status === 403;

  return (
    <>
      <PageHeader
        {...CABECERA}
        acciones={!esProhibido && !query.isError ? <DialogoCrearUsuario /> : undefined}
      />

      {esProhibido ? (
        <EstadoVacio
          icono={ShieldAlert}
          titulo="No tienes permiso"
          texto="Solo los administradores pueden gestionar usuarios."
        />
      ) : query.isPending ? (
        <Skeleton className="h-64 w-full rounded-md" />
      ) : query.isError ? (
        <BloqueError
          titulo="No se pudieron cargar los usuarios"
          mensaje={mensajeError(query.error)}
          onReintentar={() => void query.refetch()}
          cargando={query.isFetching}
        />
      ) : query.data.usuarios.length === 0 ? (
        <EstadoVacio
          icono={Users}
          titulo="No hay usuarios"
          texto="Crea la primera cuenta con el botón de arriba."
        />
      ) : (
        <TablaUsuarios usuarios={query.data.usuarios} idActual={actual?.id ?? null} />
      )}
    </>
  );
}

// --- Listado ----------------------------------------------------------------

function TablaUsuarios({
  usuarios,
  idActual,
}: {
  usuarios: UsuarioAdmin[];
  idActual: string | null;
}) {
  return (
    <Card>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Usuario</TableHead>
              <TableHead>Rol</TableHead>
              <TableHead>Creado</TableHead>
              <TableHead>Último acceso</TableHead>
              <TableHead className="text-right">Acciones</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {usuarios.map((u) => (
              <FilaUsuario key={u.id} usuario={u} esYoMismo={u.id === idActual} />
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function FilaUsuario({ usuario, esYoMismo }: { usuario: UsuarioAdmin; esYoMismo: boolean }) {
  const queryClient = useQueryClient();
  const invalidar = () => void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });

  const cambiarRol = useMutation({
    mutationFn: (rol: RolUsuario) => api.actualizarUsuario(usuario.id, { rol }),
    onSuccess: () => {
      invalidar();
      toast.success("Rol actualizado");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <TableRow>
      <TableCell className="font-medium">
        {usuario.usuario}
        {esYoMismo && <span className="ml-2 text-xs text-muted-foreground">(tú)</span>}
      </TableCell>
      <TableCell>
        <Select
          value={usuario.rol}
          onValueChange={(v) => cambiarRol.mutate(v as RolUsuario)}
          disabled={cambiarRol.isPending || esYoMismo}
        >
          <SelectTrigger className="h-8 w-[10rem]" aria-label={`Rol de ${usuario.usuario}`}>
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
      </TableCell>
      <TableCell className="text-muted-foreground">{formatearFecha(usuario.creado)}</TableCell>
      <TableCell className="text-muted-foreground">
        {formatearFecha(usuario.ultimo_acceso)}
      </TableCell>
      <TableCell>
        <div className="flex items-center justify-end gap-1">
          <DialogoResetPassword usuario={usuario} />
          <DialogoEliminar usuario={usuario} esYoMismo={esYoMismo} />
        </div>
      </TableCell>
    </TableRow>
  );
}

// --- Crear usuario ----------------------------------------------------------

function DialogoCrearUsuario() {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);
  const [usuario, setUsuario] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [rol, setRol] = React.useState<RolUsuario>("editor");

  function reiniciar() {
    setUsuario("");
    setPassword("");
    setRol("editor");
  }

  const crear = useMutation({
    mutationFn: () =>
      api.crearUsuario({ usuario: usuario.trim(), password, rol }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });
      toast.success("Usuario creado");
      setAbierto(false);
      reiniciar();
    },
    onError: (e) => {
      // 409 = el usuario ya existe: mensaje claro pegado al campo.
      if (e instanceof ApiError && e.status === 409) {
        toast.error("Ya existe un usuario con ese nombre.");
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
        Nuevo usuario
      </Button>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nuevo usuario</DialogTitle>
          <DialogDescription>
            Crea una cuenta de acceso a la consola. La persona deberá cambiar su contraseña al
            entrar por primera vez.
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
            <Label htmlFor="nuevo-usuario">Usuario</Label>
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
                <Plus className="h-4 w-4" />
              )}
              Crear usuario
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Resetear contraseña ----------------------------------------------------

function DialogoResetPassword({ usuario }: { usuario: UsuarioAdmin }) {
  const [abierto, setAbierto] = React.useState(false);
  const [password, setPassword] = React.useState("");

  const resetear = useMutation({
    mutationFn: () => api.actualizarUsuario(usuario.id, { password }),
    onSuccess: () => {
      toast.success(`Contraseña de ${usuario.usuario} restablecida`);
      setAbierto(false);
      setPassword("");
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  const puedeEnviar = password.length >= MIN_PASSWORD && !resetear.isPending;

  return (
    <Dialog
      open={abierto}
      onOpenChange={(v) => {
        setAbierto(v);
        if (!v) setPassword("");
      }}
    >
      <Tooltip label="Resetear contraseña">
        <Button
          variant="ghost"
          size="icon"
          aria-label={`Resetear contraseña de ${usuario.usuario}`}
          onClick={() => setAbierto(true)}
        >
          <KeyRound className="h-4 w-4" />
        </Button>
      </Tooltip>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Resetear contraseña</DialogTitle>
          <DialogDescription>
            Establece una contraseña nueva para <strong>{usuario.usuario}</strong>.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (puedeEnviar) resetear.mutate();
          }}
          noValidate
        >
          <div className="space-y-1.5">
            <Label htmlFor="reset-password">Contraseña nueva</Label>
            <Input
              id="reset-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              autoFocus
            />
            <p className="text-xs text-muted-foreground">Mínimo {MIN_PASSWORD} caracteres.</p>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!puedeEnviar}>
              {resetear.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Guardar contraseña
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// --- Eliminar usuario -------------------------------------------------------

function DialogoEliminar({
  usuario,
  esYoMismo,
}: {
  usuario: UsuarioAdmin;
  esYoMismo: boolean;
}) {
  const queryClient = useQueryClient();
  const [abierto, setAbierto] = React.useState(false);

  const eliminar = useMutation({
    mutationFn: () => api.eliminarUsuario(usuario.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });
      toast.success(`Usuario ${usuario.usuario} eliminado`);
      setAbierto(false);
    },
    onError: (e) => toast.error(mensajeError(e)),
  });

  return (
    <Dialog open={abierto} onOpenChange={setAbierto}>
      <Tooltip label={esYoMismo ? "No puedes eliminar tu propia cuenta" : "Eliminar"}>
        <span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={`Eliminar a ${usuario.usuario}`}
            className="text-muted-foreground hover:text-destructive"
            onClick={() => setAbierto(true)}
            disabled={esYoMismo}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </span>
      </Tooltip>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Eliminar usuario</DialogTitle>
          <DialogDescription>
            ¿Seguro que quieres eliminar a <strong>{usuario.usuario}</strong>? Perderá el acceso a
            la consola. Esta acción no se puede deshacer.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setAbierto(false)} disabled={eliminar.isPending}>
            Cancelar
          </Button>
          <Button
            variant="destructive"
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
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
