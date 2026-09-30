# Pan en Noruega: análisis documental y piloto pendiente

Este ensayo B-01 utiliza dos artículos locales expuestos de desarrollo. El ACV combina datos empresariales, bases y cálculos; la encuesta recoge descarte semanal doméstico declarado por personas. No enlazan un lote ni identifican a los compradores del pan del ACV. Reproducibilidad del cálculo, factibilidad del protocolo e impacto real son cuestiones distintas. Los hashes, pasajes, bases y fórmulas están en `sources.json`; no hubo red ni campo.

## Resultados y alcance

Se cotejaron las **17 cantidades** transcritas contra los PDF y las **siete filas** de la encuesta contra etiquetas, frecuencias y porcentajes. Coinciden. Esto es lectura de pasajes mediante `pdftotext`, separada de verificar bytes y SHA-256. El manifiesto suministrado carece de anclaje externo independiente; verificarlo no prueba custodia independiente.

Sobre **1 t de trigo**, la tabla 3 del ACV da **671 kg de harina refinada, 138 kg integral y 191 kg de salvado**: suma 1000 kg, residuo contable cero. Las fracciones físicas son 67,1/13,8/19,1%; los factores económicos 78,5/14,2/7,3% asignan inventario y no son pérdidas físicas ni precios. El salvado conserva masa y posible valor como coproducto. Sin precios, costes y ventas, la pérdida monetaria permanece `null`. Se conserva **129 kWh/t de harina**, sin atribuirlo a una tonelada de trigo ni resolver arbitrariamente su denominador.

La pieza pesa **736 g = 0,736 kg** tras horneado. **0,297 kWh eléctricos + 0,115 kWh de gas por pieza** equivalen a **0,403533 + 0,156250 = 0,559783 kWh/kg**. Es suma de energía declarada de ambos portadores, sin convertirla a energía primaria o emisiones.

La encuesta tiene **1000 respuestas**, **967 conocidas**, **33 desconocidas**, **19 abiertas** y **948 cerradas**. Interpretando rebanadas enteras, “más de 12” comienza en 13. La cota inferior es **1720 rebanadas/semana** para todas las respuestas y para las conocidas: medias mínimas **1,720000** y **1,778697**, respectivamente. Para las cerradas, el total está en **[1473, 2511]** y la media en **[1,553797; 2,648734]**, con denominador propio 948. No existe cota superior finita para todas ni para las conocidas. El cero que aporta el desconocimiento a una cota es un extremo matemático, no un descarte observado. Son restricciones sobre autodeclaraciones, no límites del desperdicio real pesado.

La metodología de la encuesta, p.3, dice 7–10 y más de 10; la tabla 1, p.4, contiene 7–9, 10–12 y más de 12. Se usa la tabla sin fingir resolver el cuestionario. No se convierten rebanadas a kg, ingesta ni porcentaje consumido.

El ACV, tabla 7, publica **3,3% panadería, 11,4% comercio y 8,2% hogar**, con base “pan que entra al sistema”; el último es cálculo secundario. No se multiplican como probabilidades condicionales sucesivas ni se presentan como seguimiento de una tonelada observada.

## Fronteras, actores y opciones

Producción recibe semillas, fertilizante, combustible y agua y entrega cereal y emisiones; secado y almacenamiento reciben grano y energía. Transporte mueve cereal e ingredientes hacia molienda y panadería, y pan hacia comercio y hogar. Molienda entrega las tres salidas anteriores; panificación transforma ingredientes/agua/energía en pan, evaporación, emisiones y descartes. Envase aporta materiales, protección, recipientes reutilizables y residuos. Comercio recibe pan y retorna sobrantes; hogar compra, almacena, eventualmente congela/tuesta y consume o descarta. El ACV modela pan descartado de panadería/comercio como alimento porcino y residuos domésticos con tratamientos municipales. Los coproductos y la recuperación cambian destinos y cargas; no restauran automáticamente valor alimentario humano.

Faltan flujos enlazables de producción/almacenamiento, humedad real, destino concreto del salvado, trazabilidad por lote, transacciones, compras y pesajes domésticos. Evitar descarte puede reducir alimentación animal disponible o trasladar energía, materiales y trabajo. Agricultores, molineros, panaderos, comerciantes, hogares, fabricantes, recuperadores y autoridades tienen intereses en ingreso, frescura, inocuidad, acceso, privacidad y carga laboral.

**Opción A: envase resellable con barrera adecuada.** Puede frenar desecación y exposición; requiere compatibilidad con línea y contacto alimentario, validación de cierre, humedad/moho, etiquetas y reciclabilidad. Desplaza costes y residuos hacia fabricante/hogar/municipio. Los ensayos de firmeza/frescura descritos en ACV §5.5 justifican una hipótesis, sin demostrar menor descarte causal.

**Opción B: mantener envase y ofrecer porcionado/congelación temprana.** Puede ajustar disponibilidad al uso; requiere capacidad de congelación, instrucciones y tiempo. Desplaza energía y trabajo al hogar y excluye a quienes carecen de equipo. La encuesta muestra asociaciones, no eficacia. Costes y aceptabilidad de ambas opciones siguen sin medirse.

Solo merece prepararse un **piloto condicionado**, sujeto a seguridad, costes y decisión humana; el despliegue no está autorizado.

## Protocolo prospectivo y autorización

Propuesta del ejecutor: hogares compradores del mismo pan, consentimiento voluntario y retiro sin penalización; asignación aleatoria oculta **1:1** por hogar, estratificada por comercio y composición familiar. Comparador contemporáneo: pan idéntico con envase actual; intervención: candidato, manteniendo provisión e instrucciones equivalentes. Ventana propuesta: **dos semanas basales y seis de seguimiento**, concurrentes.

Resultado primario: gramos de pan comestible descartado por hogar-semana asignado, mediante básculas calibradas y registros fechados; informar semanas faltantes y compras, sin imputarlas como cero. Medir también comercio, alimentación animal, bolsas adicionales, energía, material, precio, incidentes y tiempo por actor. Estimar intención de tratar ajustada por basal, intervalo **95%** con remuestreo por hogar y sensibilidad al patrón de faltantes. El tamaño exige varianza piloto y reducción mínima relevante δ acordada antes de resultados; no está determinado.

**Norma N-consent pendiente:** autoridad humana competente debe acordar consentimiento, privacidad, δ, topes de precio y perjuicios aceptables con responsables sanitarios y actores afectados. Necesita ensayos de material/barrera/moho, costes y consulta doméstica/laboral. **Requisito R-engineering pendiente, dependiente de N-consent:** ningún paquete ni enrolamiento antes de aprobación humana y verificaciones documentadas de seguridad, etiquetado, trazabilidad/retirada y permisos de datos.

Parar y retirar ante evento grave plausiblemente relacionado, fallo sanitario, vulneración de consentimiento/privacidad o límite aprobado excedido. Refuta la adopción un intervalo que excluya la reducción mínima δ o cargas/daños que excedan límites. Un intervalo compatible con cero es inconcluso. No se midieron efectos ni se aprobó intervención alguna.

## Ejecución local

`python3 analysis.py input > metrics.json` terminó con código 0. Python usa biblioteca estándar y requiere `pdftotext` local. `prototype_calls.jsonl` conserva comandos reales, salidas, códigos y hashes del estado; el grafo administra declaraciones y dependencias, sin validar autónomamente contenido o números. Las puertas solicitadas permanecen rechazadas por decisiones/fases pendientes. Esta corrida expuesta no cuenta entre 24 ensayos ni demuestra criterio 4.
