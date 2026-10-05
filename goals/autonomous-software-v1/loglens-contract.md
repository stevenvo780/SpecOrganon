# LogLens — contrato público previo a generación

Estado: encargo nuevo reservado para la transferencia del controlador; no hay
código generado ni veredicto de entrega. No es el estudio comparativo N/S/T.

El dueño encargó validar el método con un proyecto interesante y acotado,
ejecutado por agentes dentro del mandato local. La elección técnica delegada
es una CLI de Python que permite inspeccionar resultados JSONL sin convertir
un éxito de proceso en aceptación semántica. No autentica ejecuciones ni lee
credenciales. El autor debe completar el caso nuevo con argumentos, alternativas,
fuentes, protocolo, requisitos y criterios sustantivos; el contrato por sí solo
no satisface ninguna fase.

## Comportamiento público

La entrega funciona con Python 3.12 y biblioteca estándar, en una carpeta limpia
sin imports de SpecOrganon. El comando público es `python loglens.py INPUT.jsonl`.
Cada línea UTF-8 contiene un objeto con exactamente estas propiedades:

```json
{"job_id":"job-01","role":"review","status":"reject"}
```

`job_id` es una cadena ASCII de 1–64 caracteres del conjunto letras, números,
guion y subrayado. `role` pertenece a `author`, `review` o `test`; `status` a
`success`, `reject` o `inconclusive`. No se infiere la calidad del trabajo desde
estos rótulos declarados. Se rechazan propiedades adicionales, claves repetidas,
valores no finitos, objetos de tipos incorrectos, líneas vacías y BOM. Se permite
una última línea sin salto final y CRLF. El archivo vacío representa cero trabajos.

Dos registros iguales con el mismo ID representan un cierre duplicado: se cuenta
una vez y se incrementa `duplicate_records`. Un mismo ID con distinto rol o estado
es un conflicto y se rechaza; no se elige arbitrariamente el último resultado.

En éxito, stdout contiene exactamente un objeto JSON con `schema=1`,
`unique_jobs`, `duplicate_records`, `by_status` (las tres categorías, aun en cero)
y `by_role` (los tres roles, cada uno con sus tres estados). Los conteos son enteros
no negativos, independientes del orden de entrada; stderr está vacío y exit=0.

En entrada inválida, conflicto o problema de lectura: exit=2, stdout vacío,
stderr explica la categoría y, cuando procede, la línea. No se entrega un resumen
parcial como si hubiera completado el archivo. El CLI no modifica la entrada.
El límite público es 1 MiB por archivo y 10000 registros. Debe comprobarlos sin
consumir un archivo arbitrariamente grande antes de rechazarlo. Una opción
`--help` explica el uso y termina en exit=0; un uso CLI inválido termina en exit=2.

## Criterios antes de implementar o medir

- Éxito: resumen exacto de todas las combinaciones de rol/estado; archivo vacío,
  Unicode inválido y última línea sin salto tienen los resultados especificados.
- Duplicados: cierre idéntico no suma dos trabajos; conflicto del mismo ID
  produce el rechazo especificado y conserva la entrada.
- Errores: claves repetidas, no finitos, tipos/campos/rótulos/ID inválidos,
  línea vacía, BOM, archivo ausente y límites excedidos se rechazan con exit=2.
- Documentación: README útil con instalación, ejemplo copiable, formato,
  deduplicación, errores y límites; el ejemplo funciona desde carpeta limpia.
- Método: nueve fases vigentes con revisiones realmente separadas, requisitos
  y criterios trazados a problema/norma/evidencia/protocolo/decisión; pruebas
  pertinentes medidas externamente y veredicto explícito sin tesis causal.

El autor registra argv de las pruebas, pero no `passed` ni recibos inventados.
El ejecutor sin red ni perfiles mide las pruebas y el ejemplo público. Los
juicios semánticos corresponden al revisor separado. Se mantienen los presupuestos
y reglas de parada de `controller-specification.md`: 40 llamadas de rol, dos
respuestas de autor y dos juicios del revisor por fase (incluida conformidad de
mandato), 180 s por rol, 6000 s global, dos ejecuciones como máximo por test de
120 s; segunda ejecución sólo después de cambio material justificado.

## Fuentes accesibles y límites de su uso

Consultadas el 2026-10-05 antes de generación. Son documentación de formatos y
API, no observaciones de la futura entrega ni medidas de superioridad.

- [Python 3.12, módulo json](https://docs.python.org/3.12/library/json.html):
  `object_pairs_hook` permite inspeccionar pares de objetos y `parse_constant`
  permite interceptar las constantes especiales. La documentación describe
  límites de interoperabilidad y aconseja acotar el tamaño al decodificar.
- [RFC 8259](https://www.rfc-editor.org/info/rfc8259/): define la sintaxis JSON
  interoperable. La unicidad de nombres y la exclusión de valores no finitos
  motivan decisiones explícitas de validación; este contrato fija su rechazo.
- [JSON Lines](https://jsonlines.org/): describe UTF-8, un valor JSON por línea
  y terminadores de línea. Nuestro contrato restringe ese valor a un evento
  con esquema fijo; no afirma que esas restricciones sean universales del formato.

El estudio puede usar fixtures públicos nuevos etiquetados como sintéticos para
explorar riesgos. Un fallo observado del parser de biblioteca o del programa
debe tener argv, salida y recibo. Documentación y simulaciones no se presentan
como resultados de un proceso que no se ejecutó.
