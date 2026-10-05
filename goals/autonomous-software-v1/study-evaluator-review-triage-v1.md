# Auditorías del evaluador reservado: alcance y cambios

MiniMax M3 job940b0b429d6c4603818cba2414d1affc terminó por timeout360s sin
veredicto. Se conserva el input y resultado; no se acepta ni reinicia esa llamada.
Los controles y borradores avanzaron mediante correcciones independientes.

Gemini3.1ProHigh job64e16892978443e38cfa0ab5c895a76f emitió accept_draft en
204.4s para oráculos, corpus y checker. No ejecutó tests ni aceptó transporte,
harness, protocolo, solución, campaña o tesis. Su input está conservado con SHA.

Se adoptaron ambos hallazgos bajos antes de congelar: campo extra en objeto
edge y valores faltantes de las opciones opcionales TreeMap. La limitación de
density es correcta: el caso128arcos source==target mide admisión, no coste de
búsqueda. Se añade un grafo completo de11nodos/110arcos, costes1, queryA->K,
esperado conocido directamente: cost>=1 por positividad y el arco directo de
cost1 es el único camino de ese coste; caminos de2+ arcos cuestan>=2. No se
ejecuta DFS sobre esa fixture densa ni se deriva el esperado de una solución.

La observación del revisor de que el checker asume un decodificador nativo no
se adopta como supuesto: se comparan streams JSON y tipos, independiente de
cómo el programa los construya. Espacios/orden de claves libres responden al
contrato, y no prescriben implementación interna del evaluado.

Los cambios son posteriores al accept_draft y requieren verificación y revisión
del protocolo final con sus bytes definitivos. No se ha generado una solución.

## Transporte: rechazo y reproducción

Gemini3.1ProHigh job75336349990b49a985bcf930d69a78a8 rechazó el transporte
en143.2s; no ejecutó tests. El verdict reject permanece como tal. Señaló mezcla
de stderr/traza, seguimiento CLONE_FS, substring de paths y una supuesta evasión
O_PATH. Control04 reprodujo dos defects reales: stderr fingiendo chdir ocultó
un readlink real (falsa aceptación), y abrir un archivo permitido en
`/tmp/fixture/root/probe.txt` fue falsamente atribuido al probe del input.

Se eliminó el fallback de stderr como evidencia de tracer: content_audit exige
un stream trace separado. El transporte actual todavía no lo recolecta, por
lo que Control05 produjo inconclusive en las tres invocaciones, conservando
recibos/streams. La medición de contenido queda pendiente, nunca se computa
como pass. No se adopta la sugerencia de usar un archivo en /tmp writable por
el mismo UID del sujeto: esa separación permitiría alterar la traza.

El match de opens ahora compara argumento/descriptores exactos, y CLONE_FS
deja relativas sin resolución observada inconclusas hasta verificar estado
compartido o resolverlas por descriptor decodificado. Sus checks unitarios
pasan; no equivale a validar un recolector aislado. Falta implementarlo y
comprobarlo con controles adversos antes del protocolo final.

El control O_PATH|O_NOFOLLOW más readlink de /proc/self/fd/N obtuvo el camino
/fixture/root/link, no su target probe.txt. Ese ejemplo concreto del reviewer
no demuestra lectura del target del link de input; no se añadirá una prohibición
arbitraria de acceso a metadata de symlinks. Se conserva el hallazgo y reproducción
como límite inspeccionado, sin convertir el rechazo del transporte en aceptación.

Exit137 conserva su observación, OOM y deadline de attachment por separado;
es compatible con SIGKILL por límite o salida137 authored. Los docs no afirman
causalidad exclusiva por timeout. Hashes y timestamps no son pruebas de custodia.
