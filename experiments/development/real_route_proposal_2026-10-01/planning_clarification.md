# Clarificación previa a las capturas

La lectura del compilador original (`plan_coordinated_development.py`,
`compile_schedule`) mostró que la identidad del modelo interviene en la
semilla derivada de cada estrato. La identidad de los inputs, incluido el
launcher del intérprete, interviene en IDs y orden de bloques. Por tanto,
la misma seed 122 no implica el mismo orden global para dos modelos o dos
intérpretes.

Se conservan las reglas del compilador publicado. Se comprobarán exactamente
los mismos doce pares caso/réplica/alternativa, roles, materiales y recursos.
Cada calendario conserva el orden derivado y su digest, sin forzarlo ni
seleccionarlo por resultados. Astra y Luna son opciones de configuración,
no dos brazos de una comparación. Sólo una ruta y un intérprete podrán
fijarse en el freeze real R1. Ningún dato ni resultado de R1 está disponible.

El plan inicial se conserva en su commit `3cf8700` y en `plan.md`; la exigencia
de igualdad de orden entre opciones se corrige aquí antes del build/verify.
No cambia GOAL, protocolo, matriz, criterios de aceptación ni fuentes selladas.
