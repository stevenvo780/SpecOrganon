# Candidato 0.2.0rc3.dev3: admisión corregible dentro del presupuesto

La cohorte `native-reliability-01` sigue ejecutando dev2 con sus fuentes congeladas.
Este candidato es independiente: no reabre sus fallos, no los reemplaza y no cambia
el denominador. Una mejora de infraestructura no demuestra mayor fiabilidad nativa.

## Problemas observados y cambios

El primer intento de RangeAudit y el segundo de LedgerFold excedieron la admisión
de bytes en `compare`. El controlador rechazaba el candidato antes de escribir,
pero terminaba aunque quedara una intervención de autor dentro de la cuota.

La política **schema12** ofrece `admission_repair=True` explícito. Un paquete de
autor cerrado, con procedencia y snapshot válidos, rechazado únicamente por el
límite privado de recursos queda archivado como `rejected_resource_admission`.
Cuenta como una llamada de autor y una llamada total. Otro paquete redactado por
el autor puede ocupar solamente los huecos restantes: dos autores por fase, tres
en build y cuarenta roles totales. El motor no recorta ni completa el contenido.
Los límites de seis ítems, 6000 bytes por fase y 20000 bytes de archivos continúan.
Los errores de formato, integridad, transporte y recuperación `applying` detienen
el flujo. Las fases, revisiones independientes y recibos de tests son obligatorios.

```python
Controller(case, new_private_run_root, transport, contract=contract,
           mandate=mandate, executor=transport, author_format='items-v1',
           admission_repair=True)
```

El valor predeterminado es `False`; todos los runs nuevos ligan esa elección a
su política. Schema12 rechaza directorios de runs schema11, incluso vacíos.
El driver y registro de la cohorte anterior no habilitan esta opción. Antes de
medir el candidato deberá registrarse otra cohorte prospectiva y otra ruta.

El primer LedgerFold falló además en el adaptador Codex: el proceso original
terminó con código cero, sin timeout, después de cuatro mensajes `Reconnecting...`
y de un `item.completed` seguido de `turn.completed`. El adaptador confundía los
avisos con una terminación fallida. La excepción nueva admite solamente la forma
observada `Reconnecting... N/5 (...)`, con N entre 1 y 5 creciente dentro del mismo
turno y antes de su única respuesta final. Exige JSON final válido, cierre del
turno y los controles externos de código de retorno, timeout y truncación. Los
errores arbitrarios, `turn.failed`, herramientas o formatos desconocidos siguen
rechazados. Conserva contador y hash de cada aviso en `native_reconnections`.
No crea otro proceso ni repite una petición al modelo.

Los [tipos oficiales del SDK](https://github.com/openai/codex/blob/main/sdk/typescript/src/events.ts)
describen `error` como fatal. Esta excepción restringida se funda en el transcript
observado de CLI 0.160.0, revisado estáticamente; no generaliza a otros errores o
versiones. El reanálisis offline verifica parser y gramática de tres ítems del
paquete original: no lo incorpora a un caso ni cambia el fallo histórico.

La revisión también detectó que `tests_executed=false` no se exigía mecánicamente.
Ahora el adaptador y el controlador lo exigen antes de aplicar una revisión o
aprobación de texto. Un juicio de texto no acredita haber ejecutado pruebas.

## Verificación y límites

193 controles pasaron en el host y contra el wheel instalado en Docker, con red
desactivada y sin perfiles de proveedores. Incluyen límites, consumo de intentos,
recuperación de paquetes cerrados, rechazo de alteraciones, reconexiones y juicios
que inventan ejecución. El smoke instalado comprobó CLI, 24 herramientas MCP por
stdio real, persistencia, paridad CLI/MCP y rechazo de escrituras obsoletas y rutas
externas. Los hashes de todos los módulos instalados coinciden con este candidato.

Codex revisó las fuentes por texto: primero rechazó dos problemas y después aceptó
la corrección. No ejecutó tests ni verificó eficacia nativa. Se conservan el error
inicial de preparación de pytest, una aserción antigua de schema11 y un smoke vacío
por falta de stdin: ninguno se presenta como éxito de runtime.

Los recibos, fuentes revisadas, logs y controles están en
[`../evidence/bounded-admission-01/`](../evidence/bounded-admission-01/).
La suite completa del host conserva sus fallos conocidos; estos controles no la
sustituyen. El candidato todavía no tiene una cohorte nativa nueva, comparación
reservada competente con libre/SDD ni réplica. La meta continúa activa.
