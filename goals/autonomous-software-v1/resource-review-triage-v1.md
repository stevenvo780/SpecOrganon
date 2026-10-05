# Propuesta de recursos: revisión recibida, implementación pendiente

Gemini 3.1 Pro High revisó el texto por la ruta primaria existente, access=text,
job `032cdd837e4246e49fedb6f12b07c7e8`,41 segundos. Se conserva su respuesta
original. Emitió `accept_proposal` con tres correcciones: no es aceptación de
una implementación, de un caso o del protocolo comparativo.

Se acepta el hallazgo alto: la segunda autoría debe añadir pruebas conservando
los bytes de programa/README cerrados en la primera. La nueva versión del
artefacto implementación se necesita para vincular el árbol conjunto que añade
tests; eso no permite sustituir el programa sin registrar una reparación.
Se debe guardar y verificar la huella de los archivos de etapa1 al admitir y
aplicar la etapa2, incluida reanudación tras SIGKILL.

Antes de implementar hay que resolver una tensión adicional: dos autorías de
build consumen el techo actual de dos por fase, dejando cero autorías para
reparar una medición fallida. No se fingirá que esa tercera llamada ya cabe.
La próxima decisión debe elegir explícitamente entre detener build al primer
fallo o autorizar prospectivamente una única autoría adicional de reparación
en schema6, incluida en el mismo techo total de llamadas. Esa decisión no
cambia los límites/veredictos del IntervalDesk terminal ni inicia otro caso.

Si se elige reparación, su transición debe exigir un fallo real cerrado o
rechazo semántico, nueva versión de implementación/test y cambio ejecutable
para otra medición; conservar etapa1, primera entrega y recibos como historia.
No reiniciar el reloj, reaprobar fases por etiqueta ni repetir llamadas inciertas.
Todos los métodos deben tener los mismos recursos totales, con diferencias
de proceso declaradas en el tratamiento antes de generar.

Se acepta también la prueba de máxima carga: construir un estado sintético de
validate con ocho fases previas al límite, IDs/refs, dos etapas de archivos y
recibos/streams reales o claramente sintéticos. Medir el request completo y su
prompt renderizado. Los caps6000/20000 siguen siendo hipótesis de diseño hasta
pasar esa prueba; hay que contabilizar escapes JSON y máximos de resultados.
Un exceso permanece fallo controlado sin recortar premisas. No se presentará
una media de tamaños como garantía de todos los inputs admisibles.

La revisión nombra contexto/timeout como causas del agotamiento observado.
El hecho demostrado es el límite de entrada y el timeout terminal; no hay
evidencia de una causa remota específica para la lentitud de construcción.
Se conserva esa distinción y el diagnóstico de configuración como diagnóstico,
sin inferir tokens, coste, cuota o esfuerzo efectivo remoto.

Siguiente: decisión de diseño versionada y revisión en el caso de ingeniería,
máquina de estados explícita, pruebas de admisión/huellas/SIGKILL y revisión
separada de código. Después, contratos/evaluador/harness/presupuesto comparativo
congelados antes de cualquier solución reservada. Cero celdas nuevas generadas.
