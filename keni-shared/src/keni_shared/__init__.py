"""keni-shared: definiciones canonicas compartidas del monorepo keni-social.

Capa MAS BAJA: SIN dependencias de keni-metricas ni keni-consola. La fuente UNICA
importable de lo que antes estaba espejado (con guards) entre modulos:

  - `cliente`             paquete de cliente declarativo (`clientes/*.toml`): la
                          fuente de marcas/cuentas, externalizada a config.
  - `marcas`              catalogo canonico de marca (id, id_metricas, etiqueta).
  - `limites_plataforma`  limites tecnicos de caracteres por plataforma.
  - `cuentas`             cuenta principal de deportes y sus cuentas hermanas.
  - `io_atomico`          `escribir_atomico`: escritura atomica de texto a fichero.
  - `metricas`            `engagement_pct`: la formula unica de engagement.
  - `esquema_yaml`        `migrar`/`sellar`: versionado de esquema de los YAML.
  - `estados`             allowlists canonicas del tablero de contenido (estados,
                          clases y flujos; las re-exporta `keni_consola.estados`).
  - `video`               presets de formato + validador de la composicion de video.

Tanto keni-metricas como keni-consola dependen de este paquete e importan de el;
los guards de skills y del frontend verifican contra esta fuente unica.
"""

from __future__ import annotations

from . import cliente, cuentas, esquema_yaml, estados, io_atomico, limites_plataforma, marcas, metricas, video
from .cliente import Cliente, ClienteInvalido, cargar_cliente
from .esquema_yaml import migrar, sellar
from .io_atomico import escribir_atomico
from .marcas import MARCAS, Marca
from .metricas import engagement_pct

__all__ = [
    "MARCAS",
    "Cliente",
    "ClienteInvalido",
    "Marca",
    "cargar_cliente",
    "cliente",
    "cuentas",
    "engagement_pct",
    "escribir_atomico",
    "esquema_yaml",
    "estados",
    "io_atomico",
    "limites_plataforma",
    "marcas",
    "metricas",
    "migrar",
    "sellar",
    "video",
]
