# Criterios previos a ejecución propia

Estado observado: el contexto suministrado no contiene archivos previos, revisiones ni medidas. Este parche propone programa y README; no ejecuta pruebas. Se solicita revisión independiente antes de preparar y sellar la batería separada.

C1. Entrada y estructura: aceptar únicamente objetos con exactamente intervals y listas de 0 a 2000 pares de dos enteros JSON; excluir bool, float, cadenas, null y otros contenedores. Rechazar claves duplicadas incluso mediante escapes equivalentes. Comprobar extremos inclusivos ±10^12 y orden estricto.

C2. Framing y bytes: comprobar stdin vacío, LF, CRLF, última línea sin newline, líneas vacías iniciales/intermedias/finales adicionales, espacios, UTF-8 inválido, BOM, JSON incompleto, contenido adicional y constantes no estándar. Construir lotes válidos de exactamente 131072 bytes y rechazar 131073 bytes; contar bytes UTF-8, no caracteres.

C3. Semántica: comparar los cuatro ejemplos públicos y casos de anidación, duplicados, adyacencias, orden arbitrario, negativos y extremos grandes. Para casos pequeños, usar un oráculo basado en el conjunto de posiciones enteras cubiertas, reconstruyendo sus componentes contiguas sin reutilizar el algoritmo de ordenación y fusión. Exigir claves exactas y tipos enteros exactos, cobertura, span y gaps correctos.

C4. Atomicidad y protocolo: una petición válida seguida de una inválida debe producir stdout vacío, stderr exactamente range-audit: invalid input seguido de newline y exit 2. Para todos los casos válidos exigir exit 0, stderr vacío y exactamente una línea JSON terminada en newline por petición. Verificar lotes de varias peticiones, incluyendo listas vacías.

C5. Límites y robustez: aceptar 2000 intervalos y rechazar 2001; rechazar enteros fuera de rango, números muy largos y estructuras JSON profundamente anidadas sin traceback. No exigir aceptación de estructuras profundas que ya incumplen el esquema.

C6. Entrega y aislamiento: inspeccionar que el programa solo usa stdlib y streams estándar. La batería debe ser autocontenida, cargar el programa por ruta absoluta con runpy/importlib y ejecutarse con el argv fijo Python -I -B. El futuro manifiesto declarará todas las dependencias reales de pruebas y todos los archivos de entrega antes de medir. La batería se mantendrá inmutable desde esa primera medida.

C7. Evidencia: aceptar una medida propia únicamente a partir de su recibo real y resultados completos dentro del límite de streams; un recibo del host no establece por sí mismo aceptación semántica G. La auditoría independiente deberá evaluar pertinencia y suficiencia de los criterios y pruebas. No atribuir aprobación, F independiente, completitud probada ni superioridad sin evidencia.

Estrategia propuesta: lectura binaria acotada a máximo+1, decodificación UTF-8 estricta, separación por LF y validación JSON con detector de claves duplicadas. Validar intervalos antes de ordenar; fusionar con un barrido y derivar las métricas de los componentes. Serializar todo el lote antes de una única escritura de stdout. Revisión actual centrada en código, README, ambigüedades de framing y cobertura prevista; después preparar la batería separada y solicitar medida.
