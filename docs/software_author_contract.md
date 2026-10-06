# Contrato de autor: candidato 0.2.0rc3.dev2

Esta mejora de ingeniería declara de forma compacta la gramática de autor en
`author-manifest-contract.json`. Los campos obligatorios/opcionales se derivan
de las mismas constantes que usa el parser, los IDs usan `engine.ITEM_ID` y los
tipos de artefacto corresponden a la fase actual. El autor recibe explícitamente
`op=put` y pasos no vacíos, también durante construcción. Tratamiento y ablación
reciben el mismo documento; libre/SDD conservan su contrato sin pasos del motor.

La guía es consultiva. El controlador conserva la validación de contenido,
dependencias, fases, presupuestos y evidencias. No completa respuestas inválidas,
crea contenido, acepta pruebas declaradas ni repite llamadas nativas rechazadas.
Los diagnósticos preservan categorías del parser sin repetir valores arbitrarios
del autor. El estado, los archivos y las salidas medidas permanecen íntegros.

El controlador utiliza política 11 y las celdas básicas política 5, vinculadas
al código del contrato y del parser. Ejecuciones anteriores se rechazan en vez
de reanudarlas bajo una política distinta. Use un run nuevo: no migre una campaña
cerrada ni vuelva a aplicar sus paquetes rechazados.

Para evitar exceder los límites de entrada, los revisores no reciben gramática
de autor redundante y los autores no reciben sintaxis de juicio de revisor. Las
pruebas cubren los contextos máximos de ambos roles con el límite original de
110000 bytes, sin truncar el estado o ampliar los presupuestos.

El diagnóstico de los paquetes originales de v3 identifica siete errores de
gramática y tres respuestas sin pasos. La campaña y sus resultados siguen
cerrados. Las pruebas de guardas y el transporte instalado no establecen que
esta guía reduzca errores nativos ni que el método supere a libre/SDD. Ese efecto
requiere casos nuevos y evaluación reservada posterior.

El modo nuevo explícito `items-v1` recibe únicamente `schema`, `items`, `files`
y `reason`; cada item tiene exactamente `id`, `kind`, `text`, `refs` y `data`.
El toolkit construye el esquema del manifiesto, `op=put` y las guardas de versión
desde el snapshot persistido y verificado. Rechaza campos extra, contenido vacío,
IDs/referencias inválidos y recibos declarados. No elige IDs ni inventa contenido.
El adaptador valida el formato solicitado antes de llamar al modelo y no cambia
de formato según su respuesta. El SDK conserva `manifest-v1` como valor inicial
para clientes existentes; los clientes nuevos T/A seleccionan `items-v1`.

El journal conserva el paquete original, el manifiesto derivado, sus hashes y el
formato. El archivo derivado distingue campos del autor de metadatos del toolkit
y no declara aceptación. La recuperación compara ambos hashes y el snapshot;
una modificación o enlace ausente bloquea el replay. El preview de las últimas
tres acciones omite solamente nuevos hashes/rutas de ensamblaje; el journal y
el estado suministrado permanecen completos. No hay reintentos nativos añadidos.

Los resultados de este modo se reportarán por versión/formato y no se mezclarán
con v3. Una comparación histórica no identifica el efecto causal del ensamblaje.
