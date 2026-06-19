import { startRegistration } from "@simplewebauthn/browser";
import { Fingerprint, Loader2, ShieldCheck } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useSesion } from "@/hooks/sesion-contexto";
import { api, mensajeError } from "@/lib/api";

/**
 * Pantalla de inscripción de passkey FORZADA. Se muestra a pantalla completa (sin el shell)
 * cuando el usuario tiene `debe_inscribir_mfa = true`: el admin le exige segundo factor y aún
 * no tiene ninguna llave. Hasta registrar una passkey no puede usar la app.
 *
 * Flujo: pide opciones de registro -> ceremonia WebAuthn (Face ID / huella / llave) -> el
 * backend verifica y guarda la credencial. Al registrarla, refresca el `me` para que
 * `debe_inscribir_mfa` pase a `false` y la app continúe.
 */
export function PantallaInscribirMfa() {
  const { refrescar } = useSesion();
  const [nombre, setNombre] = React.useState("");
  const [registrada, setRegistrada] = React.useState(false);
  const [enviando, setEnviando] = React.useState(false);

  async function registrar(e: React.FormEvent) {
    e.preventDefault();
    if (enviando) return;
    setEnviando(true);
    try {
      const optionsJSON = await api.mfaRegistroOpciones();
      const credential = await startRegistration({
        optionsJSON: optionsJSON as unknown as Parameters<typeof startRegistration>[0]["optionsJSON"],
      });
      await api.mfaRegistroVerificar(credential, nombre.trim());
      setRegistrada(true);
      toast.success("Llave de acceso registrada.");
      await refrescar();
    } catch (err) {
      if (err instanceof DOMException && err.name === "NotAllowedError") {
        toast.error("Registro cancelado.");
      } else {
        toast.error(mensajeError(err));
      }
      setEnviando(false);
    }
  }

  return (
    <div className="flex min-h-dvh w-full items-center justify-center bg-background px-4 py-8">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1.5 text-center">
          <div className="flex justify-center">
            <ShieldCheck className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
          </div>
          <CardTitle className="text-xl">Registra una llave de acceso</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Tu cuenta necesita verificación en dos pasos. Registra una llave de acceso (Face
            ID, huella o llave de seguridad) para proteger tu cuenta y poder entrar.
          </p>
          <form className="space-y-3" onSubmit={registrar} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="inscribir-nombre-llave">Nombre de la llave</Label>
              <Input
                id="inscribir-nombre-llave"
                placeholder="Opcional: iPhone, laptop…"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                disabled={enviando || registrada}
              />
            </div>
            <Button type="submit" className="w-full" disabled={enviando || registrada}>
              {enviando ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Fingerprint className="h-4 w-4" />
              )}
              Registrar llave de acceso
            </Button>
          </form>
          <p className="text-xs text-muted-foreground">
            ¿Este equipo no te deja usar Face ID o Windows Hello? Cuando aparezca el diálogo, elige
            «usar otro dispositivo» o «teléfono» y escanea el código QR con tu móvil: la llave
            quedará en tu teléfono y podrás usarla aquí.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
