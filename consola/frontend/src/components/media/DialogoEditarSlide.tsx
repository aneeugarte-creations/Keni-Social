/**
 * Editor de la PLACA de UN slide del carrusel: reusa el editor de placa de la portada
 * (`EditorPlacaInline`, un solo hueco) sobre la PROCEDENCIA del slide (foto + titular +
 * plantilla + reencuadre). Al guardar, HORNEA la placa en el servidor (`componer-slide`) y
 * devuelve el slide actualizado (nuevo `objeto` + procedencia) para que el carrusel lo fije.
 *
 * A diferencia de la portada (autoguardado por receta on-demand), aquí el re-render es explícito
 * («Guardar slide»): cada composición corre el renderer Node, así que no se dispara en cada
 * arrastre. Solo aplica a slides de IMAGEN con procedencia (carruseles editoriales nuevos).
 */
import * as React from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { EditorPlacaInline } from "@/components/media/EditorPlacaInline";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { GaleriaPlantillas } from "@/editor/GaleriaPlantillas";
import type { Documento } from "@/editor/documento";
import { api, mensajeError, type PlantillaDiseno } from "@/lib/api";
import type { SlideCarrusel } from "@/lib/carrusel";
import type { FotoCollage } from "@/lib/placa/docPieza";
import { parsearEncuadre, serializarEncuadre } from "@/lib/placa/encuadre";

export function DialogoEditarSlide({
  slide,
  indice,
  marca,
  publicacionId,
  plantillas,
  copy = "",
  onCerrar,
  onGuardado,
}: {
  /** Slide a editar (null = diálogo cerrado). Debe ser de tipo imagen con procedencia. */
  slide: SlideCarrusel | null;
  /** Número de slide en el carrusel publicado (para el título). */
  indice: number;
  marca: string;
  publicacionId: string;
  /** Plantillas del estudio de la marca (para resolver el documento y la galería). */
  plantillas: PlantillaDiseno[];
  /** Copy del post: sugerencia del prompt al generar foto con IA. */
  copy?: string;
  onCerrar: () => void;
  /** Devuelve el slide con su nuevo `objeto` horneado + procedencia actualizada. */
  onGuardado: (slide: SlideCarrusel) => void;
}) {
  const abierto = slide !== null;
  // --- Receta editable del slide (sembrada al abrir) --- //
  const [fotos, setFotos] = React.useState<FotoCollage[]>([{ objeto: "", foco: null, zoom: 0 }]);
  const [copyIn, setCopyIn] = React.useState("");
  const [plantillaId, setPlantillaId] = React.useState("");
  const [sinPlantilla, setSinPlantilla] = React.useState(false);
  const [galeria, setGaleria] = React.useState(false);
  const [guardando, setGuardando] = React.useState(false);

  React.useEffect(() => {
    if (!slide) return;
    const enc = parsearEncuadre(slide.fotoEncuadre);
    setFotos([{ objeto: slide.foto ?? "", foco: enc?.foco ?? null, zoom: enc?.zoom ?? 0 }]);
    setCopyIn(slide.titular ?? "");
    setPlantillaId(slide.plantillaId ?? "");
    setSinPlantilla(false);
    setGaleria(false);
  }, [slide]);

  // Plantilla efectiva (igual que la portada): la elegida, o la "Placa de marca" / primera de la marca.
  const idPlacaDeMarca =
    plantillas.find((p) => p.nombre === "Placa de marca")?.id ?? plantillas[0]?.id ?? "";
  const idEfectivo = plantillaId || idPlacaDeMarca;
  const documentoSel = React.useMemo<Documento | null>(() => {
    if (sinPlantilla) return null;
    const p = plantillas.find((x) => x.id === idEfectivo);
    return (p?.documento as Documento | undefined) ?? null;
  }, [sinPlantilla, plantillas, idEfectivo]);

  const hueco0 = fotos[0];
  // Sin plantilla, el slide ES la foto cruda: exige foto. Con placa, basta foto o titular.
  const puedeGuardar = sinPlantilla
    ? !!hueco0?.objeto?.trim()
    : !!hueco0?.objeto?.trim() || !!copyIn.trim();

  const guardar = async () => {
    if (!slide || !puedeGuardar) return;
    const foco0 = hueco0?.foco ?? null;
    const zoom0 = hueco0?.zoom && hueco0.zoom > 0 ? hueco0.zoom : 1;
    const fotoEncuadre = foco0 ? serializarEncuadre({ foco: foco0, zoom: zoom0 }) : "";
    setGuardando(true);
    try {
      const resp = await api.componerSlide(publicacionId, {
        foto: hueco0?.objeto ?? "",
        titular: copyIn,
        plantilla_id: sinPlantilla ? "" : plantillaId,
        foto_encuadre: fotoEncuadre,
        sin_plantilla: sinPlantilla,
      });
      onGuardado({
        tipo: "imagen",
        objeto: resp.id,
        foto: hueco0?.objeto?.trim() ? hueco0.objeto : undefined,
        titular: copyIn.trim() ? copyIn : undefined,
        plantillaId: !sinPlantilla && plantillaId ? plantillaId : undefined,
        fotoEncuadre: fotoEncuadre || undefined,
      });
      onCerrar();
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setGuardando(false);
    }
  };

  return (
    <Dialog open={abierto} onOpenChange={(o) => !o && !guardando && onCerrar()}>
      <DialogContent className="max-h-dvh h-dvh max-w-full overflow-y-auto rounded-none sm:h-auto sm:max-h-[90vh] sm:max-w-lg sm:rounded-lg">
        <DialogHeader>
          <DialogTitle>Editar slide {indice}</DialogTitle>
          <DialogDescription>
            Cambia la foto, el titular o la plantilla; se recompone al guardar.
          </DialogDescription>
        </DialogHeader>

        <EditorPlacaInline
          marca={marca}
          publicacionId={publicacionId}
          documento={documentoSel}
          copyIn={copyIn}
          onCopyInCambio={setCopyIn}
          copy={copy}
          fotos={fotos}
          onFotosCambio={setFotos}
          sinPlantilla={sinPlantilla}
          onAlternarSinPlantilla={() => setSinPlantilla((v) => !v)}
          onAbrirGaleria={() => setGaleria(true)}
        />

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={onCerrar} disabled={guardando}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => void guardar()} disabled={!puedeGuardar || guardando}>
            {guardando && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Guardar slide
          </Button>
        </DialogFooter>

        {galeria && (
          <GaleriaPlantillas
            plantillas={plantillas}
            onCargar={(p) => {
              setPlantillaId(p.id);
              setSinPlantilla(false);
              setGaleria(false);
            }}
            onCerrar={() => setGaleria(false)}
            tipoFijo="foto"
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
