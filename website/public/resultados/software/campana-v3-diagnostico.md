# Diagnóstico posterior de la campaña v3

Se conservan las 42 celdas originales y sus puntuaciones. Este diagnóstico resume los motivos de parada registrados; no prueba la causa profunda ni una mejora todavía.

| Motivo registrado | Libre | SDD | SpecOrganon | Ablación |
| --- | ---: | ---: | ---: | ---: |
| Respuesta con manifiesto inválido | 0 | 0 | 4 | 3 |
| Límite de tamaño de entrega común | 5 | 0 | 0 | 0 |
| Límite de tamaño por etapa | 0 | 9 | 0 | 0 |
| Pasos del motor incompatibles con la ruta | 2 | 3 | 0 | 0 |
| Rol nativo fallido o inconcluso | 1 | 0 | 0 | 1 |
| Límite de artefactos en encuadre | 0 | 0 | 0 | 1 |
| Registro de artefactos que no cumple el contrato | 0 | 0 | 3 | 0 |
| Presupuesto de roles agotado | 0 | 0 | 2 | 0 |
| Límite de artefactos en crítica | 0 | 0 | 0 | 1 |
| Límite de artefactos en especificación | 0 | 0 | 1 | 0 |

Trabajo libre: F75%; SDD: F0%; SpecOrganon: F16,7%; ablación: F0%. SpecOrganon entregó dos paquetes completos FractionMix; los otros métodos ninguno bajo todos los criterios comunes aplicables. Cinco programas parciales de trabajo libre pasaron F aunque su generación no terminó.

El informador primario falló por localizadores pass que resolvían stdout vacío en dos puntos G/g4. El complemento conserva las aserciones y aplica la regla previa de ausencia de evidencia=0. No se repitieron casos.

## Mejoras propuestas, aún no implementadas ni medidas

### Formato y registros estructurados

Automatizar identificadores, serialización y validación del manifiesto; el contenido sustantivo y las revisiones siguen siendo obligatorios.

### Corrección acotada dentro del presupuesto

Devolver errores concretos antes de la ejecución y permitir una reparación limitada, con llamadas y tiempo contabilizados para todos los métodos.

### Documentación y tamaños calibrados

Reducir información repetida y comprobar tamaños con casos de desarrollo independientes antes de fijar límites comunes de entrega.

### Revisiones y roles distribuidos

Examinar por qué se agotaron los roles y reservar margen para revisiones necesarias, manteniendo autor y revisor separados.

### Informe final tolerante a evidencia inválida

Integrar de forma prospectiva la regla de evidencia ausente, conservando aserción y estado verificado; impedir que una excepción oculte el conjunto.

## Siguiente validación

Nueva campaña reservada, protocolo y parada registrados antes de generar; controles de desarrollo separados, fuentes históricas intactas; una mejora no está demostrada por corregir formatos.

Mejorar el ejecutor puede aumentar la tasa de entrega, pero no garantiza superar trabajo libre o SDD. La comparación no aísla el efecto causal del método de sus prompts, restricciones y ejecución. El objetivo de ser mejor exige evidencia nueva y reproducible; no cambiar puntuaciones previas.
