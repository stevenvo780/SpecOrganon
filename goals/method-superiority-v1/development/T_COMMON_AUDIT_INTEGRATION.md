# Integración pendiente de T con la auditoría común

Estado: diseño de ingeniería derivado de lectura del código actual, no implementado
ni admitido. No cambia las fuentes fijadas por el plan público N/S dev7 ni las
cohortes cerradas. Implementarlo exige otra versión completa y nuevos registros.

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
2. Capturar de manera durable criterios de operationalize y sus ancestros antes
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
