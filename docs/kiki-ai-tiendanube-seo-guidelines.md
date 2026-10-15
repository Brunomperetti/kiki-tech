# KIKI AI — guía editorial SEO para Tiendanube (borradores internos)

Fuente: **Tiendanube, _SEO para e-commerce — Guía completa_**, PDF de 25 páginas facilitado por el cliente (2026-10-15). Referencias de página impresas en la guía; no es un contrato de API ni una política técnica de publicación.

## Recomendaciones SEO extraídas de la guía

- pp. 7–9: investigar palabras clave e incorporarlas de manera natural en nombres de productos y categorías; requiere investigación externa real, no suposiciones.
- p. 10: preferir URLs descriptivas y comprensibles. Nunca cambiar slugs publicados sin plan de redirección y aprobación humana.
- pp. 11–12: revisar duplicados/canonical. La guía dice que Tiendanube incorpora `rel=canonical` automáticamente; verificar la implementación actual antes de recomendar cambios.
- p. 12: producir descripciones originales; referencia editorial de **100–300 palabras**, sin rellenar ni inventar atributos.
- p. 13: alt text descriptivo y útil para accesibilidad; la guía sugiere **hasta 60 caracteres**. No asegurar qué hay en una imagen sin evidencia visual.
- p. 19: título SEO y meta descripción únicos, claros, distintos del nombre comercial cuando convenga. La guía recomienda **60** y **150 caracteres** respectivamente: metas orientativas, no límites técnicos rígidos.
- pp. 16–18 y 21–22: enlaces relevantes, redacción para personas e intención de búsqueda; necesitan evaluación del contenido y el contexto.
- pp. 14–15 y 20: velocidad, compatibilidad móvil y capacidad de rastreo son tareas de auditoría del sitio, no campos de una ficha.

## Reglas de seguridad KIKI (decisiones de producto, NO texto normativo de la guía)

1. Separar **nombre comercial**, **título SEO**, **meta descripción**, **descripción** y **alt text**.
2. Conservar marca, sabor, tamaño, cantidad y variante explícitos; no inferir beneficios sanitarios, certificaciones, ingredientes ni fabricante.
3. Marcas en conflicto o parcialmente identificadas: bloquear modificación automática y solicitar verificación.
4. Ausencia de datos, palabra clave investigada o evidencia visual: marcar `RESEARCH_REQUIRED`; no inventar.
5. Nunca ejecutar escrituras a Tiendanube, Ecomm-App ni Mercado Libre sin una etapa explícita y auditada de aprobación.
6. Las longitudes sugeridas en la guía generan **avisos**, no truncado automático.
7. El análisis textual no demuestra posicionamiento SEO ni veracidad comercial.

## Alcance inicial

Auditor local **sin IA paga, sin persistencia y sin efectos secundarios**, probado con casos unitarios. Integración al panel y uso del texto como contexto acotado de un modelo quedan para una PR posterior.
