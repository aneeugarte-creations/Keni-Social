import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, UserPlus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
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
import { ApiError, api, mensajeError } from "@/lib/api";
import { type RolUsuario } from "@/types";

import { CLAVE_USUARIOS, MIN_PASSWORD, ROL_LABEL, ROLES } from "./tipos";

export function DialogoCrearUsuario({
  abierto,
  onAbierto,
}: {
  abierto: boolean;
  onAbierto: (v: boolean) => void;
}) {
  const queryClient = useQueryClient();
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
      onAbierto(false);
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
        onAbierto(v);
        if (!v) reiniciar();
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Nueva persona</DialogTitle>
          <DialogDescription>
            Crea una cuenta de acceso. Los detalles (cargo, marcas, superior) se asignan tras crearla en el organigrama.
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
            <Label htmlFor="nuevo-nombre">Nombre</Label>
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
