He revisado el diseño experimental documentado en `contract.md` y `protocol.md` según los criterios que has especificado. Siguiendo tus instrucciones, no he escrito ningún archivo ni he delegado tareas.

### Veredicto: REJECT (con ruta clara hacia ACCEPT)
El diseño base es muy sólido, pragmático y aísla bien las variables para un piloto. Sin embargo, se rechaza en su estado actual por un **vector de contaminación crítico** y una **ambigüedad contractual** que podrían invalidar los resultados si no se resuelven antes del *freeze*.

---

### Evaluación de los criterios

1. **Contratos verificables / Ambigüedades**:
   El contrato es altamente verificable. Interfaz de CLI clara, uso de códigos de salida, JSON determinista en stdout, y rechazos específicos (rutas superpuestas, regex de IDs, protección de symlinks).
   *Ambigüedad detectada*: En la Etapa 2 (`--max-bytes N`), se indica que el límite aplica al "total de bytes de archivos regulares... (incluye metadata)". Si el implementador guarda metadata en la estructura de directorios, atributos extendidos o archivos no regulares, el cálculo será ambiguo.
2. **Independencia del evaluador**:
   **Fuerte**. El protocolo separa correctamente al evaluador automatizado: se ejecuta en un contenedor distinto, sin red, con el código candidato montado como solo lectura y usando casos de prueba (semillas) no expuestos al autor.
3. **Contaminación de brazos**:
   A nivel de entorno es correcta (sin herencia de skills/agentes en los brazos N y S, sesiones nuevas).
   *Bloqueo crítico*: El agente de **"revisión técnica externa"** es un vector de contaminación. Si este agente revisor tiene un *prompt* que conoce la metodología SpecOrganon o exige artefactos SDD al evaluar el brazo N (libre), filtrará la intervención a los grupos de control, invalidando la comparación.
4. **Presupuesto comparable**:
   **Aceptable para un piloto**. Usar un límite duro de tiempo de modelo (10 minutos/etapa) y un cupo de revisión compartido es una solución pragmática ante la incapacidad de la CLI de Codex de fijar límites exactos de tokens.
5. **Cambios de requisitos**:
   Bien diseñado. La introducción de `--max-bytes` en la etapa 2 obliga a adaptar código existente sin invalidar el estado (snapshots) previamente creado, midiendo fielmente la capacidad de adaptación.
6. **Separación revisión técnica vs medidas objetivas**:
   **Lograda**. Se distingue claramente entre el agente revisor (que actúa como un *gate* durante el desarrollo para dar "aprobación del mandato local") y el *harness* automatizado (que ejecuta pruebas a ciegas sobre bytes y estado final sin interactuar).
7. **Fuerza de la inferencia con n=6 por brazo**:
   **Estadísticamente responsable**. El protocolo prohíbe explícitamente declaraciones universales de superioridad o uso confirmatorio de p-valores, limitando las conclusiones a una "señal de piloto con variabilidad".

---

### Bloqueos concretos antes del freeze
1. El protocolo no aísla el comportamiento del agente revisor técnico. Su *prompt* podría sesgar a los grupos de control.
2. La definición de qué constituye el tamaño de almacenamiento en `--max-bytes` es ligeramente ambigua respecto a la metadata.

### Correcciones mínimas propuestas
Para cambiar el estado a **ACCEPT**, implementa las siguientes dos aclaraciones en los documentos:

1. **En `protocol.md` (Diseño)**: Especifica explícitamente que el agente de revisión técnica externa debe utilizar un **prompt estrictamente neutral, ciego al brazo que está evaluando**, y basar su revisión *exclusivamente* en los criterios funcionales de `contract.md` (sin exigir enfoques de SDD a N, ni métodos de SpecOrganon a N o S).
2. **En `contract.md` (Cambio común)**: Modifica la regla de `--max-bytes` para cerrar la ambigüedad. Por ejemplo: *"la suma del tamaño en bytes de todos los archivos regulares contenidos dentro del directorio del repositorio (toda metadata debe almacenarse en archivos regulares para ser contada)"*.
