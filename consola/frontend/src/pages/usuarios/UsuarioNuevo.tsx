import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldAlert, UserPlus } from "lucide-react";
import * as React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { MedidorPassword } from "@/components/auth/MedidorPassword";
import { Campo } from "@/components/comunes/Campo";
import { EstadoVacio } from "@/components/comunes/EstadoVacio";
import { TituloPagina } from "@/components/layout/encabezado";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { useSesion } from "@/hooks/sesion-contexto";
import { ApiError, api, mensajeError } from "@/lib/api";
import { type RolUsuario } from "@/types";

import {
  CLAVE_CONFIG_USUARIOS,
  CLAVE_PASSWORD_MIN,
  CLAVE_USUARIOS,
  esInscripcionMfaRequerida,
  MIN_PASSWORD,
  ROL_LABEL,
  ROLES,
} from "./tipos";

/**
 * Subpágina de alta de una persona (`/usuarios/nuevo`). Porta el formulario del antiguo popup a
 * ancho completo: nombre (opcional), usuario, contraseña inicial con medidor de fortaleza y rol.
 * Al crear, navega al detalle de la persona recién creada. Solo superadmin (el backend devuelve
 * 403 como red de seguridad si se llega por URL).
 */
export default function UsuarioNuevo() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { usuario: actual, cargando } = useSesion();
  const esSuperadmin = actual?.es_superadmin === true;
  const volver = () => navigate("/usuarios");

  const [usuario, setUsuario] = React.useState("");
  const [nombre, setNombre] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [rol, setRol] = React.useState<RolUsuario>("editor");
  // El error solo se muestra tras un intento de crear (no mientras se escribe).
  const [intentado, setIntentado] = React.useState(false);

  // Mínimo de contraseña efectivo (config global). Cae a MIN_PASSWORD si aún no llegó.
  const configQuery = useQuery({
    queryKey: CLAVE_CONFIG_USUARIOS,
    queryFn: ({ signal }) => api.configuracionUsuarios(signal),
    select: (data) => data.ajustes,
    staleTime: 5 * 60 * 1000,
    enabled: esSuperadmin,
  });
  const minPassword = React.useMemo(() => {
    const ajuste = configQuery.data?.find((a) => a.clave === CLAVE_PASSWORD_MIN);
    return typeof ajuste?.valor === "number" ? ajuste.valor : MIN_PASSWORD;
  }, [configQuery.data]);

  const crear = useMutation({
    mutationFn: () =>
      api.crearUsuario({
        usuario: usuario.trim(),
        password,
        rol,
        nombre: nombre.trim() || undefined,
      }),
    onSuccess: (creado) => {
      void queryClient.invalidateQueries({ queryKey: CLAVE_USUARIOS });
      toast.success("Usuario creado");
      navigate(`/usuarios/${creado.id}`);
    },
    onError: (e) => {
      // 403 de MFA: el backend ya manda el mensaje en español (inscribe una passkey).
      if (esInscripcionMfaRequerida(e)) {
        toast.error(mensajeError(e));
      } else if (e instanceof ApiError && e.status === 409) {
        toast.error("Ya existe un usuario con ese nombre de cuenta.");
      } else {
        toast.error(mensajeError(e));
      }
    },
  });

  const errUsuario = !usuario.trim() ? "El usuario es obligatorio." : null;
  const hayErrores = Boolean(errUsuario) || password.length < minPassword;

  if (!cargando && !esSuperadmin) {
    return (
      <>
        <TituloPagina titulo="Nueva persona" icono={UserPlus} onAtras={volver} />
        <EstadoVacio icono={ShieldAlert} titulo="No tienes permiso" />
      </>
    );
  }

  return (
    <>
      <TituloPagina titulo="Nueva persona" icono={UserPlus} onAtras={volver} />

      <div className="mx-auto max-w-2xl pb-10">
        <Card>
          <CardHeader>
            <CardTitle>Nueva persona</CardTitle>
            <CardDescription>
              Crea una cuenta de acceso. El resto del perfil (cargo, marcas, organización) se
              configura después en su ficha.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                setIntentado(true);
                if (hayErrores) return;
                crear.mutate();
              }}
              noValidate
            >
              <Campo etiqueta="Nombre" htmlFor="nuevo-nombre">
                <Input
                  id="nuevo-nombre"
                  value={nombre}
                  onChange={(e) => setNombre(e.target.value)}
                  autoComplete="off"
                  maxLength={120}
                  placeholder="Opcional: Diana Ramos"
                />
              </Campo>
              <Campo
                etiqueta="Usuario"
                htmlFor="nuevo-usuario"
                error={intentado ? errUsuario : null}
              >
                <Input
                  id="nuevo-usuario"
                  value={usuario}
                  onChange={(e) => setUsuario(e.target.value)}
                  autoComplete="off"
                  maxLength={120}
                  aria-invalid={(intentado && Boolean(errUsuario)) || undefined}
                />
              </Campo>
              <div className="space-y-1.5">
                <Label htmlFor="nuevo-password">Contraseña inicial</Label>
                <Input
                  id="nuevo-password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                />
                <p className="text-xs text-muted-foreground">Mínimo {minPassword} caracteres.</p>
                <MedidorPassword password={password} />
              </div>
              <Campo etiqueta="Rol" htmlFor="nuevo-rol">
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
              </Campo>
              <div className="flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={volver}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={crear.isPending}>
                  {crear.isPending ? (
                    <Spinner className="h-4 w-4" />
                  ) : (
                    <UserPlus className="h-4 w-4" />
                  )}
                  Crear persona
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
