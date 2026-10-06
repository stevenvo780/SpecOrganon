# Integración documental del driver instalado N/S

Código, contratos públicos e índice de casos publicados en main como ingeniería parcial. F06 (autonomía N y asimetría de planificación/revisión S), admisión nativa y competencia siguen pendientes. La meta continúa activa; no hay superioridad demostrada.

El recibo de ingeniería original documenta 143 pruebas seleccionadas, cuatro controles mecánicos Docker, 38 módulos instalados idénticos y cinco guards de consola. Esta publicación no vuelve a ejecutar pruebas, Docker, wheel, controladores ni modelos. Su revisión independiente aceptó un alcance limitado de ingeniería.

Desde main se ejecutó únicamente la auditoría offline de archivos `python goals/method-superiority-v1/evidence/neutral-pilot-driver-01/verify_evidence.py --check-source`: 126 archivos, 618064 bytes y 13 fuentes coincidentes. También se comprobaron todas las entradas de los SHA256SUMS versionados: 6262. Se conservan rechazos, errores y RAW exactos. La única excepción de git diff --check es docker-04.stdout, por espacios del pytest original.

No cambió website/, no hubo despliegue nuevo y permanecen las 94 descargas anteriores. El corte web 69f64d sigue siendo histórico válido. Dev4 permanece cerrado con 5/10 entregas y 543/543 comprobaciones públicas.

publication-receipt.json enlaza fuentes originales y commit de integración previo al recibo para evitar referencias autorreferenciales. verification.json contiene los hashes comprobados; archive-verification.stdout/.stderr conservan el resultado de la auditoría. El tag neutral-pilot-driver-partial-20261006 preserva la procedencia original, sin freeze completo ni release de wheel.
