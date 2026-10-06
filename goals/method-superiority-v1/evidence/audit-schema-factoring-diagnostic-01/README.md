# Diagnóstico offline de esquema compartido

La auditoría fallida original tenía14subesquemas D/G exactamente iguales y un esquema de respuesta de19698bytes. Representar esas14copias mediante referencias JSON Schema Draft7 a la misma definición reduce el esquema a3575bytes. El request, las instrucciones, los IDs, campos requeridos, hashes, localizadores permitidos, additionalProperties y condiciones pass permanecen íntegros.

Para el mismo request original, el envoltorio hipotético Gemini mide113441bytes en vez de131246, dentro del límite128000. Nueve vectores sintéticos de aceptación/rechazo dan la misma validación. No son juicios de auditoría ni pruebas nativas.

Es un prototipo de representación, todavía no aplicado al bridge ni a las imágenes instaladas. No repite ni reemplaza el fallo original, no cambia caps, fuentes o plan del piloto y no acredita readiness futura. Implementación completa, revisión independiente, instalación y admisión posteriores siguen pendientes.
