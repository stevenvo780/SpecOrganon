# Cohorte nativa de fiabilidad 01

Diez generaciones nuevas fijadas antes de observar sus resultados: cuatro
RangeAudit, tres LedgerFold y tres TopoPlan, en orden intercalado. Cada intento
parte de un caso nuevo; el caso RangeAudit anterior queda fuera del denominador.
Se reutiliza su contrato público. No hay evaluación reservada ni ceguera.

El driver automatiza la coordinación del controlador rc3.dev2 existente. No
cambia el core, sus nueve fases, mandatos, revisiones, límites ni correcciones
acotadas. No sustituye un intento fallido. Los productos se someten después a
115, 104 o 105 controles públicos independientes, respectivamente, sin reparar
la entrega a partir de sus resultados. La fiabilidad de generación y la
conformidad funcional independiente se informan por separado.

Se registran los SHA de fuentes, contratos y verificadores, imágenes Docker y
perfiles originales. No se copian credenciales ni se cambian cuentas. La cuota
del volumen Codex original es desconocida; la lectura de la app no se le atribuye.
Cada trabajo tiene su handle y recibo. Un proceso interrumpido se reconcilia por
ese handle y una llamada incierta no se repite. Un resultado cerrado exige sello
de outcome, inicio, caso y acciones; una adulteración impide el agregado. Un error
del informe guarda los resultados brutos como no verificados y conserva el
último informe válido. No se transforma evidencia ausente en éxito.

Preparación desde la raíz del repositorio con Docker y los perfiles autorizados:

```sh
uv sync --frozen --extra dev
uv run python goals/method-superiority-v1/development/register_native_cohort.py /ruta/nueva/registration.json --run-root /ruta/nueva/runtime
uv run python -m scripts.native_reliability run /ruta/nueva/registration.json --registration-sha256 SHA_DEL_REGISTRO
uv run python -m scripts.native_reliability report /ruta/nueva/registration.json --registration-sha256 SHA_DEL_REGISTRO
```

Estas rutas deben ser privadas, nuevas y ajenas a las campañas históricas. El
registro devuelve su digest. La operación `run` conserva la misma cohorte al
reanudar; crear otro registro produce otra cohorte y no reemplaza la anterior.
El ejecutor usa únicamente los modelos y perfiles fijados en ese registro.

Verificación de la infraestructura: 158 pruebas específicas y dos controles
Docker que rechazan productos sintéticos conocidos inválidos. No son generaciones
nativas ni resultados de esta cohorte. La revisión inicial rechazó defectos del
agregado, que se corrigieron con controles adversarios y revisión posterior.
La consulta Gemini de overhead agotó 240 segundos y se conserva como fallo.

La meta completa requiere además comparación reservada con trabajo libre y SDD
sólidos, funcionalidad no inferior, ventaja simultánea en paquetes completos,
tiempo práctico y réplica independiente. Cerrar esta cohorte no cumple esa meta.
