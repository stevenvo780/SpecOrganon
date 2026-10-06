# Integración pendiente de T con la auditoría común

Estado: base de custodia implementada parcialmente en la candidata dev9;
adaptador y auditoría común todavía pendientes, sin admisión T. No cambia las
fuentes fijadas por los planes públicos N/S dev7/dev8 ni las cohortes cerradas.
La versión completa futura exige instalación, revisión y nuevos registros.

## Siguiente candidata dev10, parcial y prospectiva

La versión de trabajo dev10 factoriza el contrato D/G/H sin cambiar sus campos
ni juicios, limita el stdin real antes del preflight y exige recuperar la medida
original cerrada y verificar su journal antes de escribir `passed` en el engine.
La política del controlador pasa a schema14. Los controles sintéticos delimitados
pasaron; todavía no hay instalación, revisión independiente, admisión T ni
adaptador común completo. No modifica las fuentes o resultados originales dev8/dev9.
El recibo está en `../evidence/native-envelope-provenance-dev10-prospective-01/`.

## Base de custodia dev9

`t_measurement_custody` guarda criterios completos de `specify`, ancestros,
estado, archivos, batería y argv originales, ledger binario y reloj antes de
invocar la primera medida. La recuperación conserva la misma reserva y reloj;
las reparaciones conservan nombres y bytes de la batería y el argv originales.
El controlador archiva requests y fuentes antes del dispatch y exige
`transport.verify_role` para autorizar packets nativos. La etiqueta `native`
por sí sola no acredita ejecución. Estas guardas tienen pruebas sintéticas,
sin resultados nativos de T ni afirmaciones D/G/H.

Quedan pendientes las capturas completas de cada transición, la exportación del
snapshot común, la auditoría separada y cobrada, verificación de todos los
receipts/streams originales y el reloj que incluya preparación desde antes del
transporte. El reloj del sello previo sólo fecha ese sello; no mide el intento
entero. La auditoría no puede añadirse al contenido que ella misma auditó.

## Brecha actual comprobada

`common_review.checklist('T')` ya define los mismos D1–D8 y G1–G6 de N/S y las
nueve H propias de T. `common_evidence` admite method T, capturas físicas,
checkpoints encadenados y streams medidos. Sin embargo `SoftwareController` no
produce esa captura ni invoca una revisión D/G común: `package_gate()` comprueba
nueve fases aceptadas y actuales, trazas, implementación/batería selladas, recibos
reales y reviews build/validate vinculadas a los mismos archivos. Es un gate T,
no una medición del paquete común. No derivar D/G pass de esos campos.

## Contrato de adaptación propuesto

1. Registrar contrato funcional común y política comparable antes de generar.
   El mandato T y sus H se conservan aparte. Cada nueva versión debe fijar módulo
   adaptador, engine, driver, bridge, imágenes, perfiles y presupuestos.
2. Capturar de manera durable criterios de `specify` y sus ancestros antes
   de la primera medida propia. Capturar también cada versión previa de la
   entrega y los documentos; no reconstruir supuestos criterios originales a
   partir del ledger final ni usar notas posteriores como evidencia previa.
3. Exportar snapshot schema2 con contrato/política, archivos finales, documentos
   sustantivos del ledger, historia encadenada y captures por contenido. El
   último checkpoint debe referir los archivos/documentos finales exactos. Los
   streams completos de medida se ligan a sus recibos y presupuesto común.
4. Vincular cada receipt locator a verificación del journal/transport original,
   con input, argv, nonce/imagen, source capture y streams reales. Un SHA de un
   receipt JSON no acredita ejecución ni independencia. Resolver la operación
   existente en recuperación; una incertidumbre no permite otra invocación.
5. Invocar auditor independiente sobre ese snapshot usando common-audit-v1 y el
   checklist T. D/G usan exactamente la definición N/S. H exige sustancia y
   reviews actuales de las nueve fases: la aceptación del engine es necesaria,
   pero no se sustituye juicio sustantivo por conteo de items.
6. La auditoría consume presupuesto y tiempo total. Rechazo conserva motivos y
   permite reparación solo dentro de recursos previamente registrados; cualquier
   modificación invalida la auditoría y las medidas/reviews que dejó obsoletas.
   No conceder una revisión final gratis ni aplicar al T cuotas mayores después
   de observar que N/S entregaron mejor.
7. Mantener tres resultados separados: gate T/H, auditoría común D/G y F externo.
   La entrega completa común exige la definición registrada y evidencia actual;
   public checks no son F reservado y no completan fases ni paquete documental.

## Controles necesarios antes del freeze completo

- Gate T verdadero con D/G ausente debe permanecer sin paquete común acreditado.
- Criterios borrados, cambiados o solo presentes después de medida no pasan G2.
- Archivo/README/ledger alterado después de captura invalida binding y review.
- Receipt inventado, streams modificados o launcher/imagen cambiados se rechazan.
- Estado con fase aceptada pero artefactos obsoletos/contestado no pasa H ni gate T.
- Crash después de medir/revisar recupera la misma operación y conserva coste.
- Presupuestos y reloj incluyen preparación, auditoría, corrección y pruebas;
  boot distinto deja duración desconocida.
- Bootstrap instalado y Docker usan los bytes de la versión completa congelada;
  los diez T de calificación son nuevos, sin reutilizar dev2/dev4 ni este piloto.

Los límites futuros se justifican antes de resultados y se aplican a los tres
brazos. La modalidad de texto y las diferencias de formato deben declararse;
no presentar estos controles como agentes con herramientas irrestrictas.
La calificación propia >=9/10, las dos familias efectivas de autores, los tres
estratos, incertidumbre simultánea por generación, primaria reservada y réplica
permanecen requisitos de la GOAL.md original. Este documento no los satisface.
