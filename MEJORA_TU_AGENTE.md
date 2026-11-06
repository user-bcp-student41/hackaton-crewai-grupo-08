# Mejora tu agente

Los agentes de `agents/` parten con instrucciones mínimas. El flujo, las pausas humanas, los formatos de salida y los controles siguen funcionando. El ejercicio consiste en mejorar la responsabilidad, los entregables y las instrucciones del rol que te asignó el equipo.

1. Edita las instrucciones de tu archivo `agents/<rol>.py`. Puedes ampliar `INSTRUCTIONS` y, en CrewAI, el objetivo, contexto y salida de la tarea.
2. Especifica entregables verificables y evidencia para comprobarlos. Indica qué hacer con errores y observaciones. Prohíbe inventar pruebas o resultados.
3. Conserva firmas, claves de estado, imports, nombres de artefactos y formatos que consume el flujo.
4. Publica el cambio en tu rama y abre un PR para revisión del equipo.
5. Abre «Mi equipo» en el portal. Consulta el overview y ejecuta la evaluación de tu equipo sobre el código publicado en su rama principal.

El dashboard separa pruebas del flujo, cobertura de instrucciones por agente y total del equipo. El template básico puede aprobar el flujo y obtener una puntuación baja en instrucciones. Esa es la situación inicial esperada.

La rúbrica estática busca responsabilidades del rol, entregables, evidencia, honestidad y correcciones con feedback. Es orientativa: no mide las respuestas reales del modelo ni garantiza calidad del código generado. El instructor revisa los casos no reconocidos.


## De dónde partir según tu rol

Antes de escribir instrucciones, lean el mismo Issue, sus criterios de aceptación y el código del producto de los días anteriores. Identifiquen qué existe y qué falta. Amplíen `INSTRUCTIONS`, `goal`, `backstory` y `build_task` de su archivo; no cambien `KEY`, `SPEC_FILE`, `EXTRACT_CODE` ni la firma de `build_task`.

| Rol y archivo | Qué hace | Por dónde empezar | Qué debe pedir como entregable |
| --- | --- | --- | --- |
| Arquitectura, `agents/architect.py` | Define componentes, límites y contrato de API: entradas, respuestas y errores. Alinea la solución con los criterios de aceptación. | Lee el Issue y las interfaces existentes; escribe el recorrido de una petición y un ejemplo de petición y respuesta. Señala supuestos pendientes. | `user_story.md`: solución propuesta, contrato, criterios verificables y decisiones que necesitan Datos, Backend y Frontend. |
| Datos y persistencia, `agents/data.py` | Define tablas, relaciones, restricciones y migraciones. Incluye claves primarias y foráneas, nulabilidad, unicidad, índices necesarios y reglas de integridad. | Parte de la arquitectura aprobada y del esquema existente. Enumera entidades, cardinalidades y qué datos ya guardados deben conservarse. Si no hace falta persistencia, justifícalo. | `data_spec.md`: modelo y diccionario de datos, relaciones y restricciones; SQL de migración y estrategia de reversión o recuperación, con comprobaciones de integridad. SQL en bloques con primera línea `-- nombre.sql`, guardado en `output/db/`. No ejecuta migraciones. |
| Backend, `agents/backend.py` | Implementa servicios, endpoints, validaciones y acceso a datos según los contratos aprobados. | Parte de la API de Arquitectura y, cuando esté activo, del modelo de Datos. Traza un caso válido y un error desde la entrada hasta la persistencia. | `backend_spec.md` y código Java con nombres de archivo y paquetes esperados. Usa el contrato de Datos sin volver a diseñar tablas ni regenerar sus migraciones. En equipos de seis, Backend también cubre la persistencia necesaria. |
| Frontend, `agents/frontend.py` | Implementa la interacción y el consumo de API; contempla carga, vacío, errores y accesibilidad. | Parte del contrato de API y del recorrido del usuario. Lista campos, validaciones visibles, acciones y estados de la pantalla. | `frontend_spec.md` y código Angular en bloques con nombres de archivo. El cliente no reemplaza la validación ni la autorización del servidor. |
| Pruebas, `agents/testing.py` | Convierte criterios de aceptación en casos verificables: positivos, negativos, límites e integración. | Relaciona cada criterio con una entrada, una acción y un resultado esperado. Incluye integridad y migración si Datos las propone. | `testing_report.md`, pruebas y comandos reproducibles. Distingue resultados realmente ejecutados de propuestas marcadas NO EJECUTADO. La persona ejecuta las pruebas y conserva su salida. |
| Seguridad, `agents/security.py` | Revisa autenticación, autorización, entradas, secretos, datos sensibles e inyección; propone correcciones verificables. | Recorre la petición y sus fronteras de confianza; considera qué puede hacer un usuario sin permiso o con entradas manipuladas. | `security_report.md`: hallazgos con ubicación, impacto, corrección y comprobación; señala lo pendiente y evita afirmar seguridad sin evidencia. |
| Chapter, `agents/chapter.py` | Revisa la coherencia entre requerimiento, arquitectura, datos, código, pruebas y seguridad. Emite el veredicto final del agente. | Contrasta cada criterio de aceptación con las entregas aprobadas. Busca contratos incompatibles, pruebas pendientes y hallazgos sin resolver. | `chapter_review.md` con `VEREDICTO: APROBADO` o `VEREDICTO: RECHAZADO`, motivos y correcciones concretas. No reemplaza las aprobaciones humanas ni inventa ejecuciones. |

Datos se habilita solo para el grupo de siete en S1 CrewAI. La secuencia es Arquitectura → Datos → Backend → Frontend → Pruebas → Seguridad → Chapter; los equipos de seis omiten Datos. Cada etapa usa el contexto aprobado anteriormente. Una responsabilidad distinta no exige repetir la revisión de Backend.

Como primer ejercicio, tomen un solo criterio del Issue. Escriban en las instrucciones qué recibe su agente, qué decisión le corresponde, qué formato debe devolver y cómo comprobarlo. Por ejemplo, si el criterio exige un título único, Datos define la restricción y la migración; Backend traduce el conflicto a un error de API; Frontend muestra ese error; Pruebas verifica el duplicado; Seguridad revisa entradas y permisos; Chapter comprueba la coherencia de toda la entrega.
