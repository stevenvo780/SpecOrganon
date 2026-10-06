# CSVShape v1: protocolo prospectivo de ingeniería

Estado: propuesta; no habilita generación sin registro congelado y revisión.
Identidad única `csvshape-delivery-v1`; caso nuevo `cases/csvshape_v1`.
No reemplaza ningún caso o celda anterior. Esta entrega es un hito de ingeniería,
no una nueva campaña N/S/T ni evidencia de superioridad metodológica.

## Autoridad y roles

Se aplica el mandato existente de software autónomo del operador. Codex escogió
CSVShape como decisión técnica delegada; el usuario no escogió personalmente la
tarea o arquitectura. La aprobación local `human:owner` registra esa delegación,
sin autenticar identidad. Autor nativo Gemini 3.8 Flash (Medium), perfil original
`/home/stev/.gemini`; revisor nativo Codex gpt-6.1-sol, esfuerzo low, volumen original
`specorganon-lab_codex-home`. Cada llamada usa un contenedor separado y sólo el
perfil propio del proveedor. Los perfiles no se copian ni se cambian por fallos.
El controlador externo aplica decisiones y ejecuta pruebas, no escribe los
argumentos ni inventa la aceptación. El evaluador contractual no usa modelos.

Los roles reciben contrato, mandato, estado, reporte, tarea y datos públicos
actuales. No reciben recetas reservadas, respuestas esperadas ni diarios privados.
Las pruebas propias usan un contenedor sin credenciales/red con entrega readonly.
Las invocaciones reservadas sólo reciben código y stdin/argv: el host conserva
expectativas, recetas y recibos fuera de los montajes. El operador y el daemon de
Docker son autoridad confiable; el aislamiento no constituye certificación frente
a un operador hostil ni prueba de independencia estadística entre modelos.

## Condiciones previas y presupuesto

Revisión independiente de contrato, protocolo, controlador de admisión y evaluador
antes de registrar. Congelar hashes de los cuatro documentos públicos, todos los
módulos de src/specorganon, scripts ejecutados, evaluador, tests pertinentes,
catálogo público y revisión. Registrar imágenes inmutables y rutas originales
antes de inicializar caso o generar artefactos. Consultar cuotas actuales y catálogo
antes de delegar; cuotas ausentes quedan desconocidas, sin habilitar sondeo local
Codex ni cambiar cuentas. Admisión con observación de cuota de antigüedad <=600s.
Una cuota explícitamente agotada o lectura vencida pausa antes de nuevas llamadas;
obtener otra observación no renueva tiempos, presupuesto ni llamadas consumidas.

Controlador schema7: <=40 llamadas nativas; <=2 autores por fase excepto build
<=3 (programa, tests, reparación sólo tras fallo/rechazo real); <=2 revisiones por
fase; <=2 juicios de conformidad de aprobación por fase, contados separadamente.
El recorrido sin rechazos requiere unas 23 llamadas (9 autores, 9 revisores,
3 conformidades, segundo autor build y auditoría final); 40 permite correcciones acotadas, no éxito
garantizado. <=6000s desde primera admisión, <=180s por llamada nativa, <=120s
por prueba propia y <=2 pruebas, segunda sólo con Python/argv ejecutable cambiado.
<=128000 bytes UTF-8 de prompt renderizado por llamada; <=3145728 acumulados.
<=6 artefactos y <=6000 bytes de contribución JSON escapada por fase; <=20000
bytes de contribución JSON escapada de todos los archivos; <=4000 bytes escapados
de salida de pruebas. Estos límites mantienen contexto y entrega pequeños; no
están calibrados para demostrar ventaja y pueden ocasionar fallo de generación.
Los roles deben contar la serialización y producir argumentos breves sustantivos.
No se aumentarán estos límites tras ver outputs. Tokens y dinero desconocidos
permanecen null; bytes, duraciones, códigos y uso declarado se registran aparte.

## Criterios de las nueve fases

Cada fase necesita aceptación real del revisor separado, trazas vigentes y ausencia
de contradicciones abiertas. El revisor debe juzgar estos criterios, no sólo forma
JSON. Debe rechazar evidencia ausente, argumentos circulares o mediciones inventadas.

1. Frame: problema operativo preimportación, actor delegado y frontera explícita
   (estructura local, no semántica, demanda o utilidad comercial demostrada).
2. Critique: norma basada en actor/problema, supuesto discutible, dos encuadres
   distintos; confrontar inspección previa versus reparación silenciosa, declarar
   límites de la necesidad delegada. No aprobar utilidad de campo por etiqueta.
3. Study: pregunta falsable sobre conformidad técnica, hipótesis, protocolo que
   fija población/colección/comparación/incertidumbre; indicador(es) para los tres
   criterios siguientes, unidades y fuentes. Puede compartir métrica porcentual
   de comprobaciones cumplidas con denominadores específicos F/D/M; no mezclar
   poblaciones ni compensar criterios. Evidencia documental y la observación real
   de seis probes públicos del parser fundamentan el indicador antes de specify.
   La medición del parser no es medición de CSVShape/D/M; no inventar valores.
   Recetas reservadas no accesibles.
4. Observe: evidencia publicada/observada accesible con source/date/locator y
   enlace al protocolo; inferencia vinculada. Fuente primaria pública Python3.12
   csv y contrato delegado sustentan elección de validación estructural. No afirmar
   usuarios reales ni mejoras observadas; si no existen, registrar ese límite.
5. Explain: síntesis que separa garantías del parser, obligaciones añadidas y
   errores detectables; incertidumbre por corpus finito y demanda no estudiada.
6. Compare: >=2 opciones sustantivas vinculadas a norma/síntesis, comparación que
   refiere ambas y riesgo. Incluir opción viable sin software nuevo, por ejemplo
   revisión manual con una herramienta existente; justificar decisión por criterios
   técnicos, no superioridad ya medida. No basta renombrar variantes idénticas.
7. Specify: decisión trazada a comparación/norma/evidencia; requirement(s) y tres
   criterios trazados a problema/norma/evidencia/protocolo/decisión/indicador.
   Deben registrarse antes de medir: F conformidad contractual, D documentación,
   M método/trazas. F: propia suite realmente pasada y contrato/ejemplos correctos,
   sin inferir aceptación reservada todavía. D: README reproduce ambos ejemplos
   y documenta instalación/argv/errores/límites/semántica, checklist 8/8. M: 9/9
   fases revisadas separadamente, trazas vigentes, alternativas reales, recibos
   verificados y ninguna cuestión abierta. Umbrales no compensables; rechazar
   incumplimiento y declarar no_demostrado ante incertidumbre. El umbral reservado
   externo posterior es 100% de recetas, ambos ejemplos y documentación 8/8.
8. Build: programa y README reales como primera etapa; tests reales como segunda.
   Un único implementation actualizado, un único test con argv absoluto, ligados
   a requisitos/criterios. Tests cubren éxitos, errores y límites, invocando el CLI
   real; el controlador mide y registra recibos, nunca acepta passed del autor.
   Posible tercera etapa de reparación sólo tras fallo o rechazo semántico actual.
9. Validate: baseline/result con valores realmente suministrados y alcance explícito,
   assessments vinculados a criterio, baseline, result y riesgo; incertidumbre,
   efectos adversos y coste desconocido. Sólo F puede tener un juicio decisivo
   apoyado por pruebas propias reales: cada assessment decisivo debe trazar UN
   criterio, UN baseline y UN result, con test pasado que refiera directamente ese
   criterio e implementación. No combinar tres criterios en ese result; superaría
   las obligaciones del motor. D y M quedan no_demostrado en el ledger si no existe
   una medición propia pertinente. La auditoría separada posterior emite sus juicios
   D/M sin completar retrospectivamente el ledger. M9/9 todavía no se ha medido
   dentro de validate; no afirmar la aceptación futura de esta fase. Una proporción
   absoluta de conformidad no es una diferencia causal; baseline del parser conserva
   otra población y se usa sólo como contexto, sin imputar una baseline de programa
   inexistente. La reserva posterior puede refutar F y se conserva aparte.

Checklist D fijado: (1) Python3.12/stdlib/instalación sin dependencias; (2) stdin y
forma exacta argv/delimitadores; (3) comando ejecutable y resultado ejemplo1;
(4) comando ejecutable y resultado ejemplo2; (5) exit2/stdout vacío/error exacto;
(6) límites de bytes/filas/columnas/campos; (7) vacíos/distintos/Unicode exacto;
(8) alcance y uso real de tests. Revisor puntuará cada punto, no una media subjetiva.
Tras la puerta de paquete, una llamada nativa separada del mismo revisor, dentro
del techo40 y reloj6000s, debe emitir D8/8 y checklist M6/6 estructurados sobre
archivos, ledger, historia y recibos reales. Un punto ausente/incierto falla, sin
otra generación o reparación; la auditoría se conserva aun si rechaza. No sustituye
ejecutar ambos ejemplos, incluido en las 48 recetas después del cierre. El evaluator
externo exige auditoría positiva, nueve fases y reserva48/48 para completed_technical.

## Pruebas y cierre

Matriz reservada nueva, definida antes de generación en `reserved.py`: entradas
vacías, encabezados y anchuras, delimitadores/argv, CSV estricto/citas/nuevas líneas,
UTF-8/BOM/NUL, nombres/límites, filas/campos/bytes en límite y límite+1, valores
vacíos y Unicode sin normalización. Incluye dos ejemplos públicos identificados
por separado. Expectativas explícitas, sin invocar el programa entregado ni
consultar sus outputs para construir el oráculo. No corpus seleccionado por éxito.
Por receta un contenedor readonly/networknone/2CPU/1GiB, timeout3s, stream2MiB.
Misma identidad lógica sólo reutiliza recibo cerrado; cambio de receta o entrega
se rechaza antes de ejecutar. Timeout de sujeto es fallo contractual; incertidumbre
de montaje/lanzamiento/recibo es inconcluso. Todas las recetas quedan contabilizadas
si no hay programa, si falta una o si la infraestructura impide cerrar la ejecución.

Parada: error de proveedor, formato, techo, rechazo persistente, recibo incierto
o fuente modificada cierra esta identidad; no reemplazar, renovar o repetir hasta
ganar. Pausa de cuota/boot antes de nuevo despacho conserva el mismo pendiente,
presupuesto y artefactos; sólo continuidad probada permite proseguir. Interrupción
del observador se reconcilia con el mismo handle, jamás nueva llamada. Incluso
entrega fallida conserva programa parcial/ledger/recibos y recibe evaluación
reservada sin reparar después de ver recetas. Resultado: completed_technical sólo
con 9 fases, puerta de paquete, F/D/M y reserva completa; delivery_failed,
infra_inconclusive o not_started en otro caso. Publicar también fallos y límites.

Después de este caso siguen pendientes comparación prospectiva nueva de varios
tipos y dos familias con repeticiones/ablación, instalación limpia de versión
integrada y actualización de Vercel. CSVShape no satisface por sí solo toda la goal.
