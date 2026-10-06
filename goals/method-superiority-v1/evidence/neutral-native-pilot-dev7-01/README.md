# Piloto público dev7: corte parcial original, no comparación reservada

Plan admitido: `../neutral-native-admission-01/pilot-plan.json`, SHA
`ae62fd8daf0d592852aa1fff404585118b9b0a9d0120295a0fd0e90b19ae8827`.
Seis posiciones originales fijas, N/S y tres tipos. El driver instalado sigue
activo; este corte conserva las primeras dos posiciones cerradas y cuatro aún
sin resultado terminal en el reporte. No se repiten, sustituyen ni reparan esos
intentos. Los resultados públicos posteriores nunca retornan al autor.

| Posición original | Método/tarea | Gate del controlador | Funcionalidad pública | Recursos cobrados |
|---|---|---|---|---|
| 01 | N / RangeAudit | failed: solicitud excede presupuesto | 115/115 | 2 autores, 1 feedback, 1 medida propia |
| 02 | S / RangeAudit | failed: solicitud excede presupuesto | 115/115 | 1 plan, 1 revisión de plan, 1 programa; 0 medidas propias |

Ambos conservan fallo, sin auditoría D/G final acreditada ni entrega común.
115/115 es un resultado público de desarrollo; no es F reservado, no demuestra
competencia ni superioridad, y no transforma el gate fallido en completo.
El denominador planificado permanece seis. Este corte no registra cuatro fallos
ni cuatro éxitos adicionales: las posiciones pendientes se muestran aparte.

`report-01.stdout` proviene del comando report instalado y solo leyó el runtime:
status incomplete, dos cierres; no crea locks, dispatch ni otro intento. Sus
comandos y stderr se conservan. `closed-raw/` copia los archivos cuyo inventario
ya estaba sellado por cada outcome y closure, más esos dos archivos de cierre.
`closed-raw-index-01.json` fija todos los SHA y bytes; se comprobó antes y después
de copiar cada archivo. No contiene perfiles copiados. Un guard de cadenas con
forma de token sk-* no encontró coincidencias; no es una prueba universal de
que contenido arbitrario sea público seguro.

## Diagnóstico verificable del primer fallo

`diagnose_first_request.py` reconstruye en un subprocess de diagnóstico el
pedido base que la reserva 0005 rechazó antes de crear otra llamada. Usa solo
las cuatro generaciones originales cerradas. Omite en memoria el guard y el
render de prompt únicamente para medir los bytes rechazados; no modifica
fuentes, presupuesto del driver, registros originales ni procesos del piloto.
No despacha nada ni ejecuta un programa generado.

El resultado `first-request-diagnostic.json` registra **131968 bytes JSON**
frente al límite **110000**. Archivos actuales: 14924 bytes; documentos actuales:
5768 bytes, ambos dentro de sus límites. `history.json` incorpora 89938 bytes
antes de escapar el JSON externo: 30947 de paquetes de rol y 58708 de capturas,
además de su estructura. Los snapshots repiten contenido que también aparece
como archivos/documentos actuales. Esta serialización comprobada explica la
parada; no se concluye causalidad sobre la eficacia del método.

La corrección siguiente debe preservar todos los originales físicos y sus
bindings, deduplicar contenido de solicitudes sin eliminar información útil,
aplicar el cambio a N/S y comprobar regresiones/recuperación. No ampliar el
presupuesto de este plan ni retocarlo tras resultados. Otra versión y registro
se evalúan prospectivamente; ninguna nueva corrida sustituye estas posiciones.
La integración T común, F externo, freeze completo, diez T propios >=9/10,
primaria reservada y réplica continúan pendientes. La meta permanece activa.
