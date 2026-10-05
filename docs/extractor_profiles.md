# Extractores PDF y entornos de instalación

El contrato histórico D100 fija un binario Poppler 24.02.0. Ese contrato y sus
resultados se conservan sin modificaciones. La instalación CachyOS actual
contiene Poppler 26.08.0; ejecutar el auditor sin selección explícita rechaza
sus bytes por no coincidir con el pin histórico.

La rama `codex/autonomous-software-v1` incorpora un perfil candidato
`cachyos-26.08.0-x86_64-v4`, pendiente de revisión independiente para una
release. La comparación diagnóstica obtiene las mismas 17 cifras, siete
filas y advertencias. El texto completo del artículo LCA cambia. Esto
acredita una revalidación acotada de transcripciones; no reproduce el
resultado histórico completo ni aprueba el método.

Selección explícita desde la raíz:

```sh
SPECORGANON_EXTRACTOR_PROFILE=cachyos-26.08.0-x86_64-v4 \
  python -m scripts.audit_bread_sources

python -m scripts.audit_bread_sources \
  --extractor-profile cachyos-26.08.0-x86_64-v4
```

El perfil fija `/usr/bin/pdftotext` a SHA-256
`47253257c7a7995ea6c8ad54b47b0edece8739dd4102c7bcd5a729472c386fb4`.
Los nombres desconocidos o vacíos se rechazan. No se calcula un nuevo pin
a partir del binario instalado. En la API de pasajes, un `ExtractorSpec`
explícito conserva prioridad sobre la variable de entorno y se verifica.

Los recibos del auditor conservan el hash del contrato histórico, el pin
efectivo y `extractor_selection.historical_binary_reproduced`. La selección
del perfil nuevo hace este último campo falso. Las bibliotecas compartidas
del host siguen fuera de la autenticación; el resultado lo declara.

La captura requiere Linux y un CPython compilado con `memfd_create` y las
constantes de sellado. Si faltan esas capacidades, devuelve un rechazo del
auditor. No sustituye el sellado por ejecución desde una ruta mutable.
La instalación de Python por sí sola no garantiza estas capacidades.

Este perfil depende de los bytes y la arquitectura x86_64_v4 indicados. No
es una imagen Docker portable. El [entorno Docker candidato](docker_release.md)
recupera el binario histórico mediante Ubuntu 24.04 y comprueba su hash durante
la construcción. Las revisiones independientes y los recibos de la goal
conservan sus alcances: revisión de código y pruebas técnicas no equivalen a
aceptación de la release ni a validación general del método.
