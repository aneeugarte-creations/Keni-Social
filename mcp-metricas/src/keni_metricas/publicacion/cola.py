"""Cola/agendador minimo de publicaciones aprobadas.

Meta no agenda Instagram nativamente via API, asi que el agendado vive aqui: un
humano APRUEBA un `Borrador`, lo encola con una hora opcional, y
`publicar_pendientes(ahora)` dispara los que ya vencieron.

SEGURIDAD: hereda el dry-run del adaptador. `publicar_pendientes(..., dry_run=True)`
es el defecto y NO toca la red. Solo con `dry_run=False` (y token real en el
adaptador) se publica de verdad. La cola es en memoria (sin persistencia): es un
andamiaje, no un broker de produccion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .meta import AdaptadorPublicacionMeta, ResultadoPublicacion
from .modelos import Borrador


@dataclass
class ItemCola:
    """Un borrador aprobado en espera, con hora de publicacion opcional.

    `publicar_en=None` => listo para disparar de inmediato. `publicado=True` tras
    un envio efectivo (real). En dry-run el item NO se marca como publicado: un
    ensayo no consume la cola.
    """

    borrador: Borrador
    publicar_en: datetime | None = None
    publicado: bool = False

    def vencido(self, ahora: datetime) -> bool:
        """¿Toca publicarlo ya? (sin hora = siempre; con hora = cuando ahora >= hora)."""
        if self.publicado:
            return False
        return self.publicar_en is None or self.publicar_en <= ahora


@dataclass
class ColaPublicacion:
    """Cola en memoria de borradores aprobados, ordenada por hora de publicacion."""

    adaptador: AdaptadorPublicacionMeta
    items: list[ItemCola] = field(default_factory=list)

    def encolar(self, borrador: Borrador, publicar_en: datetime | None = None) -> ItemCola:
        """Anade un borrador aprobado (opcionalmente agendado) a la cola."""
        item = ItemCola(borrador=borrador, publicar_en=publicar_en)
        self.items.append(item)
        return item

    def pendientes(self, ahora: datetime) -> list[ItemCola]:
        """Items aun no publicados y ya vencidos a la hora `ahora`."""
        return [it for it in self.items if it.vencido(ahora)]

    def publicar_pendientes(
        self, ahora: datetime, dry_run: bool = True
    ) -> list[ResultadoPublicacion]:
        """Dispara los items vencidos. DRY-RUN POR DEFECTO (no toca la red).

        Devuelve un `ResultadoPublicacion` por item disparado, en orden de hora.
        Solo con `dry_run=False` se marca `publicado=True` (un ensayo no consume
        la cola).
        """
        # Orden estable: primero los sin hora, luego por hora ascendente.
        vencidos = sorted(
            self.pendientes(ahora),
            key=lambda it: it.publicar_en or datetime.min,
        )
        resultados: list[ResultadoPublicacion] = []
        for item in vencidos:
            res = self.adaptador.publicar(item.borrador, dry_run=dry_run)
            if not res.dry_run:
                item.publicado = True
            resultados.append(res)
        return resultados
