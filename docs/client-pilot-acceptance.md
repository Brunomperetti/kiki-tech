# KIKI Tech — Protocolo de prueba con KIKI Market

## Objetivo

El cliente puede probar **un recorrido real y seguro** del producto, no una demostración ficticia de publicación masiva. Este documento define qué debe ocurrir, qué cuenta como aprobado y qué sigue bloqueado.

## Antes de la reunión

1. Confirmar que KIKI Tech se despliega en Render, backend y frontend. Abrir `/pilot` con la cuenta autorizada y verificar que el panel se actualiza.
2. Confirmar que el resumen del catálogo **histórico** Ecomm-App está cargado; la copia de API es **independiente**, `READ_ONLY_STAGE` y no es el inventario operativo de KIKI.
3. Confirmar que ML tenga conexión válida y mostrar la **fecha de última sincronización**; no confundir un snapshot con datos en vivo.
4. Confirmar si existe CSV Tiendanube. Si no existe o el servicio falla, se muestra «Pendiente» o «No se pudo comprobar», **no cero**.
5. Elegir un producto real, simple, con SKU y evidencia disponible, para poder demostrar un flujo sin necesitar inventar marcas, GTIN, relaciones de packs o resultados.

## Flujo de aceptación — 10 a 15 minutos de uso real (sin automatización de tiempos)

### A. Inicio y catálogo
- Entrar a `/pilot`; el menú principal también ofrece **Probar KIKI**.
- Verificar que el catálogo Ecomm histórico, la copia API, el estado de ML y el CSV de TN se presentan por separado, con advertencias de frescura cuando corresponda.
- Abrir **Productos** y localizar un producto por SKU.
- **Aprobación:** muestra ficha real y los datos disponibles; no llama producto «listo» solo por tener SKU.

### B. Pendiente real y decisión registrada
- Abrir el ejemplo propuesto en **Resolver un dato pendiente**, o usar `/work/details?focus=data`.
- Elegir una marca o GTIN que necesite comprobación. Guardar un **borrador** con la evidencia disponible; **no usar «Aceptar evidencia»** sin fuente y presentación verificadas.
- Volver a abrir el mismo producto y comprobar que la investigación persiste. Verificar la trazabilidad donde aplique.
- **Aprobación:** borrador accesible después de recargar; errores visibles y ningún cambio en Ecomm-App ni ML.
- **Falla:** el borrador desaparece, falla el guardado, la app adjudica marca/GTIN sin autorización, o una fuente ausente se muestra como cero.

### C. Preparación ML
- Entrar a **Preparación ML** desde el piloto.
- Mostrar estados de productos, motivos de bloqueo y controles pendientes. Evitar aprobar una ficha sin datos verificados.
- **Aprobación:** resultados coherentes con las fuentes de KIKI y no se genera publicación ML automáticamente.

### D. Tiendanube
- Abrir **Revisar Tiendanube** y comprobar que sus datos proceden del CSV, no de una API en vivo.
- La generación real con OpenAI **NO forma parte de esta prueba por defecto**: requiere confirmación explícita porque consume créditos.

## Qué se puede afirmar hoy

- KIKI reconcilia fuentes importadas, expone información, permite trabajo interno y conserva decisiones donde el flujo existente lo permite.
- La API Ecomm pública es **solo lectura** y la copia de inventario todavía **no reemplaza** el catálogo histórico. La composición real de combos tampoco viene en los endpoints actuales.
- Las familias SKU por prefijos son señales de negocio y **no prueban por sí solas variantes, composición, fabricante ni GTIN**.
- La publicación masiva ML/TN y sincronización automática de stock **siguen fuera del alcance de este piloto**.

## Condiciones para habilitar posteriormente integración operativa

- Resolver discrepancias sustanciales de SKU e IDs Ecomm y aprobar un plan de adopción del inventario API con precios, costos y marca preservados.
- Definir estrategia para GTIN compartidos, combos y variaciones con evidencia de composición, no solo el patrón SKU.
- Verificar la frescura de inventario ML y un mecanismo de revalidación antes de operaciones externas.
- Pruebas de publicación en canal con permisos expresos del cliente, idempotencia, revisión por lotes, estados de error y rollback/reconciliación según capacidades reales.

## Guía de comunicación

Decir: **«Probamos con un producto: encontramos la ficha, documentamos la evidencia, recuperamos la decisión y vemos cómo se prepara para el canal. La publicación externa se habilitará por etapas una vez validados los controles.»**

No decir: «Ya sincroniza stock», «ya publica solo en Mercado Libre», «ya completó automáticamente todas las marcas» ni «las familias SKU demuestran que los packs tienen el GTIN de su componente».
