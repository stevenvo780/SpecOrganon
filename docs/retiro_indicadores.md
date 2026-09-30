# Retirar un indicador sustituido

Un indicador que se dividió en varias métricas puede conservar su identificador,
versiones y rechazo técnico sin seguir siendo una obligación activa de la fase.
El retiro registra explícitamente cuáles indicadores lo reemplazan.

```bash
organon retire-indicator /ruta/al/caso i_rows \
  --replacements '{"i_rental_fraction":1,"i_return_fraction":1}' \
  --expected-version 3 --expected-review-seq 52 \
  --reason 'El par se expresa mediante dos métricas escalares con evidencia propia' \
  --actor agent:analista
```

MCP expone `retire_indicator` con los mismos argumentos: `path`, `id`,
`replacements`, `expected_version`, `expected_review_seq`, `reason` y `actor`.
Los guards son obligatorios y las versiones deben ser enteros positivos.

## Condiciones

El indicador debe estar vigente, sin contradicciones ni consumidores actuales,
y tener una revisión negativa independiente en la secuencia indicada. Su único
error puede ser ese rechazo. Cada reemplazo debe tener evidencia numérica de su
métrica/unidad, una cadena válida de protocolo/problema/norma, y estar vigente.
La unión de reemplazos debe conservar todos los problemas y normas del origen.
En casos firmados se consideran también los autores históricos del indicador.

La conservación del grafo prueba vínculos estructurales. El motivo del retiro
explica la decisión técnica; la equivalencia semántica requiere revisión competente.
Esta operación no concede aprobación humana de normas o decisiones.

## Historia y vigencia

`status` conserva el indicador con `issues`, `retired`, `retirement_status`,
`retirement_issues` y `retirement_history`. El historial global aparece en
`indicator_retirement_history`. El retiro efectivo se omite de las obligaciones
activas y de los mínimos; los reemplazos siguen evaluándose normalmente.

Revisar un reemplazo, rechazarlo, cuestionarlo, dañar su archivo o añadir un
consumidor del origen invalida el retiro. El historial sigue legible y el rechazo
del origen vuelve a bloquear. No se reescriben consumidores ni se resuelven desafíos.
Un indicador con retiro declarado sobre su versión actual no puede reemplazar
otro, aunque su propio retiro ya haya perdido vigencia.

Los cambios de ciclo registrados en el ledger cambian el snapshot de `study` y
exigen una revisión de fase vigente. El actor del retiro cuenta como autor de
esa fase para la independencia de firmas. Un segundo retiro sobre un origen
todavía retirado se rechaza sin añadir eventos; si la declaración anterior perdió
vigencia, puede registrarse una nueva con guards y reemplazos actuales.

El motor comprueba los archivos al leer el estado. Restaurar sus bytes exactos
sin un evento duradero puede recuperar el snapshot y los avances anteriores;
la lectura no conserva memoria de una alteración transitoria. El estado técnico
recuperado no autentica la custodia externa del archivo.

Los manifests del runner mantienen acciones `put` y `advance`. El retiro se
ejecuta mediante CLI/MCP; después, `next_task` y el workflow utilizan su vigencia.
