# Plan de análisis expuesto · residuos de comedor escolar

**Fijado:** 2026-09-26 UTC, antes de inspeccionar los valores de resultado del XLSX en este proyecto. Es un análisis de desarrollo, no un registro prospectivo externo ni una reserva confirmatoria.

## Fuente y alcance

El [depósito primario de Zenodo](https://zenodo.org/records/20825233), DOI 10.5281/zenodo.20825233, atribuido a Arja Kuusisto, Jenni Latva y Ella Wilén, publica bajo CC BY 4.0 mediciones diarias de un centro escolar finlandés. Su descripción anuncia 155 días: 135 de línea base y 20 de intervención; registra comensales, menú cíclico de 25 días, residuos de cocina y servicio (KSW) y residuos de plato (PW). El archivo descargado para esta preparación tiene SHA-256 2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624 y MD5 3f7e610fedc1810f7e8bc1bd47103ee7, coincidente con el depósito. Solo se inspeccionaron encabezados, tipos y faltantes: una fila carece de KSW kg.

La pregunta descriptiva es si el residuo **total** por comensal cambia entre períodos y si sus componentes se mueven en sentidos opuestos. Ninguna cifra de la escuela se extrapolará al caso del mango, de panificadoras o a una cadena producción→consumo. El material no registra producción, almacenamiento, transporte, compras de insumos, inocuidad, costes ni un grupo contemporáneo no tratado.

## Reglas fijadas antes del cálculo

1. Leer solo la hoja food waste school meals 2024-25 y las primeras ocho columnas. Ignorar filas sin datos en esas columnas; exigir exactamente 155 filas activas, fechas únicas y crecientes, menú entero de 1 a 25, comensales enteros positivos y masas numéricas no negativas cuando estén presentes. Las primeras 135 filas son línea base y las últimas 20 intervención, como declara el depósito; no elegir cortes por el resultado.
2. Recalcular gramos por comensal desde PW kg, KSW kg y DINERS usando aritmética decimal. Las columnas calculadas del XLSX se usarán solo para control de consistencia y se informarán sus discrepancias; no se corregirá un valor fuente sin dejar registro.
3. Para PW, usar todos los días válidos. Para KSW y PW+KSW, usar solo días con ambos componentes; informar fechas y cantidad de exclusiones sin imputar. El estimador principal de cada período es 1000 × suma(kg) / suma(comensales) en su conjunto de días. Reportar diferencia intervención menos línea base en g/comensal y porcentaje respecto de la línea base, por separado para PW, KSW y total. Si el denominador es cero, el porcentaje queda indefinido.
4. Sensibilidad de menú: para cada menú observado durante la intervención y también en la línea base, calcular la media diaria de g/comensal en cada período y su diferencia; promediar esas diferencias con igual peso por menú. Informar número de menús emparejados, rango de diferencias y menús sin par. Aplicar la regla por separado a PW, KSW y total, conservando faltantes.
5. Describir la distribución de comensales, cobertura temporal, menús y faltantes en ambos períodos. No convertir ausencia de datos en cero. No usar significación estadística ni IC causal: un solo centro, 20 días de intervención, serie temporal y posible estacionalidad impiden atribuir el contraste a la intervención sin supuestos adicionales. La variación por menú y el rango de diferencias son sensibilidad descriptiva, no incertidumbre causal completa.

## Resultado esperado y condición de parada

Se conservarán el XLSX original, un script reproducible y una salida JSON con hashes y denominadores. Cualquier violación de esquema detendrá el cálculo antes de informar un efecto. Si la suma por comensal baja pero PW sube, se informará explícitamente el desplazamiento observado. Ninguna dirección del contraste aprobará el criterio 3: faltan la cadena completa, línea base comparable para una intervención nuestra, costes, perjuicios, seguridad y diseño de atribución.
