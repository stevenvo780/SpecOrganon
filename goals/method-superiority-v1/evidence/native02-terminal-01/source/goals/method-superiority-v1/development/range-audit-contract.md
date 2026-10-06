# RangeAudit: desarrollo técnico público

Construir una CLI Python estándar, range_audit.py, que normaliza intervalos enteros semiabiertos [inicio, fin). El encargo técnico está delegado bajo la meta de mejorar SpecOrganon; no prueba efectos de campo ni superioridad.

Entrada: NDJSON por stdin, un objeto por línea no vacía, con exactamente la clave intervals. Su valor es una lista de hasta 2000 pares [inicio,fin]. Los extremos deben ser int JSON (no float ni bool), de valor absoluto <=10^12, con inicio<fin. Duplicados y orden arbitrario son válidos. Rechazar claves JSON duplicadas, claves extra, codificación no UTF-8, líneas vacías y JSON mal formado. Una entrada completamente vacía representa cero peticiones válidas. Tamaño máximo de todo stdin: 131072 bytes.

Salida por petición: un objeto con exactamente merged, covered, span y gaps. merged contiene los intervalos ordenados y fusionados por solapamiento o adyacencia; covered es la suma exacta de sus longitudes. span es [mínimo inicio,máximo fin], o null si la lista está vacía. gaps son los huecos entre intervalos fusionados, ordenados; el intervalo exterior no cuenta como hueco. Escribir una línea JSON UTF-8 por petición válida, seguida de newline. Orden de claves no significativo; enteros exactos, sin flotantes.

Si cualquier petición del lote es inválida: salida stdout completamente vacía, stderr exactamente "range-audit: invalid input\n", exit2. Validar todo el lote antes de emitir resultados. Si todo es válido: exit0, stderr vacío. Sólo biblioteca estándar, sin red, ficheros externos o modificación de entorno.

Ejemplos:
- {"intervals":[[1,3],[3,7],[10,12]]} -> {"merged":[[1,7],[10,12]],"covered":8,"span":[1,12],"gaps":[[7,10]]}
- {"intervals":[[4,8],[1,2],[2,6],[4,8]]} -> {"merged":[[1,8]],"covered":7,"span":[1,8],"gaps":[]}
- {"intervals":[]} -> {"merged":[],"covered":0,"span":null,"gaps":[]}
- {"intervals":[[-5,-2],[0,1]]} -> {"merged":[[-5,-2],[0,1]],"covered":4,"span":[-5,1],"gaps":[[-2,0]]}

Entrega: programa, README útil con instalación, NDJSON, ejemplos, errores/límites y comando de pruebas, además de test_range_audit.py con pruebas pertinentes. El programa/README se sella antes de escribir pruebas. El argv de pruebas comienza /opt/specorganon/venv/bin/python y usa /input/delivery/test_range_audit.py. El ejecutor aislado genera los recibos reales; el autor nunca declara passed o recibos.

Las nueve fases siguen requiriendo contenido, trazas, revisión independiente y aceptación vigente. Esta ejecución es desarrollo no reservado; las observaciones de referencia que se aporten deben etiquetarse como controles públicos de contrato, sin atribuirlas a trabajo libre, SDD o resultados nativos de este producto.
