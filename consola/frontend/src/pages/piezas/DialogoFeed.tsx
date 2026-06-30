import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { PostFeed } from "@/pages/feed/PostFeed";
import type { Pieza } from "@/types";

/**
 * Popup que muestra una pieza COMO SE VERÁ EN EL FEED: la misma tarjeta `PostFeed` (carrusel
 * deslizable incluido) que en la Lista del Feed, NO el editor. Lo abre el clic en una pieza del
 * calendario de programación; reprogramar/editar/desprogramar viven en su menú contextual.
 *
 * El carrusel se desliza aunque la pieza ya esté publicada (la tarjeta es de solo lectura
 * visual); tocar un slide abre el editor por su cuenta, que es donde se decide si se puede tocar.
 */
export function DialogoFeed({
  pieza,
  onCerrar,
}: {
  pieza: Pieza | null;
  onCerrar: () => void;
}) {
  return (
    <Dialog open={pieza !== null} onOpenChange={(o) => !o && onCerrar()}>
      {/* La tarjeta trae su propio borde/sombra: el diálogo solo la centra (sin chrome propio). */}
      <DialogContent className="max-w-md border-none bg-transparent p-0 shadow-none">
        {/* Título accesible que exige Radix; la tarjeta ya rotula la pieza visualmente. */}
        <DialogTitle className="sr-only">{pieza?.titulo ?? "Vista del feed"}</DialogTitle>
        {pieza && <PostFeed pieza={pieza} />}
      </DialogContent>
    </Dialog>
  );
}
