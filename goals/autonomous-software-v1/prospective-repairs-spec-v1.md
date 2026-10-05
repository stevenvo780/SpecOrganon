# Reparaciones prospectivas v1

Estado: propuesta anterior a implementación. No modifica campañas cerradas ni
acepta una nueva entrega. Desarrollo separado: codex/prospective-software-repairs,
basado en 9f083afe; el checkout original y sus 48 fuentes permanecen intactos.

## R1: identidad de receta y ejecución aislada

La API ReservedDocker.run recibe el ID lógico de receta. Validar string no
vacío, UTF-8 estricto y coincidencia exacta con case.id antes de efectos. Derivar
un ID interno de ejecución ASCII hexadecimal de 64 caracteres mediante SHA256
del JSON canónico {namespace:specorganon.reserved.invocation.v3,id:ID_LOGICO}.
No normalizar Unicode ni recortar/reemplazar caracteres. Mantener separado el
ID original. El hash usa sólo la identidad lógica, no la receta mutable: una
receta cambiada debe encontrar el mismo handle y fallar por divergencia.

La petición/plan privado conserva ID lógico, ID opaco, hash de receta completa
e inventario de entrega. Si dos IDs confluyen por una colisión o corrupción,
esa identidad y los hashes deben impedir reutilizar o reemplazar el handle.
La receta o el resultado esperado nunca se montan al sujeto; los IDs/hashes de
procedencia no son una prueba de custodia ni autenticación.

Versionar política de ReservedDocker a schema3. Una raíz con política antigua
se rechaza antes de cualquier fixture o ejecución; no migra observaciones. La
campaña02 y sus seis invocaciones rechazadas no se reevalúan. Conservar los
límites de 3s por sujeto, aislamiento, recibos y prohibición de reinicio incierto.

Verificación: IDs con punto, Unicode, separadores y prefijos peligrosos quedan
en directorios opacos seguros y distintos; falta de identidad se rechaza sin
efectos; receta cambiada y colisión simulada no lanzan otro sujeto; sólo recibos
cerrados se reutilizan. Pruebas Docker con recetas técnicas nuevas y programa
de control explícito, sin emplear programas/recetas reservadas anteriores como
feedback o sustituir resultados. Una prueba de hash sola no basta.

## R2: presupuestos independientes por función

Versionar Controller a schema7. La política fija, por fase, dos contribuciones
de autor (tres en build), dos aprobaciones de conformidad con el mandato y dos
revisiones de fase. Conservar el techo global de 40 roles nativos y los límites
de documentos/archivos/tests. Contar el historial persistido por acción exacta;
aprobar una norma no consume una revisión técnica. Cambiar versiones/normas,
reabrir fases o reanudar procesos no renueva contadores ni permite obtener una
tercera intervención de la misma función.

Una corrección tras rechazo puede recibir la segunda revisión aunque exista
una aprobación previa. Rechazo persistente tras la segunda revisión, o más de
dos aprobaciones necesarias en una fase, termina el caso; no inventar aceptación.
Pendientes con recibo cerrado se reconcilian con la misma identidad y no se
reenviarán para renovar el presupuesto. Runs schema6 y anteriores se rechazan
sin migrar su ledger/historial. Las instrucciones del rol declaran schema7 y
los tres límites; no cambian el contrato de las nueve fases del motor.

Verificación: aprobación + rechazo + corrección + revisión nueva; rechazo
persistente; agotamiento de aprobaciones separado de revisión; contador global;
reanudación de la misma política y rechazo de schema6 antes de dispatch; ledgers
inmutables ante rechazo de presupuesto. Tests sintéticos son controles, no
revisión sustantiva ni aceptación de una entrega nueva.

## Revisión y límites de esta ingeniería

Una revisión independiente de texto de Gemini Pro, cuenta primaria original,
antes de implementar; máximo 300s y respuesta acotada. Codex coordina y escribe.
No se generan soluciones de estudio, no se cambia de cuenta ni se copian
credenciales. Después: controles de regresión, controles Docker nuevos, revisión
independiente del código final y especificación prospectiva de entrega nueva.
La aceptación del diseño no cumple la goal ni reabre la comparación truncada.
