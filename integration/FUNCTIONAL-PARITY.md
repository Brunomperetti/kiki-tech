# Paridad funcional: alcance comprobado en código

Inventario estático del 12/11/2026. No se accedió a producción. «Integrado» se refiere al backend aislado, no a un despliegue. Ninguna ruta o servicio original fue eliminado. Las herramientas históricas conservan su interfaz en la aplicación original; el demo bloquea sus llamadas por seguridad. No se afirma paridad total del nuevo panel.

## Pantallas originales y acciones

| Ruta original | Pantalla / acciones API utilizadas | Estado en 2.0 | Corrección mínima pendiente |
|---|---|---|---|
| `/dashboard-classic` | Dashboard: ecommMlPreview, ecommSavedEdits, ecommStageStatus, mlStatus | Parcial | Resumen y calidad integrados; conservar reportes históricos por ejecución. |
| `/pilot` | Pilot: ecommApiCatalog, ecommAutoStatus, ecommManualRefreshStart, ecommMlPreview, ecommStageStatus, mlStatus, tiendanubeReport | Parcial | Pilotos MAMA/Hileret disponibles; herramientas piloto originales permanecen en su interfaz. |
| `/cases` | CaseExplorer: ecommMlCases | Pendiente | Exponer casos históricos en el panel sin convertir identidades Excel en variantes API. |
| `/workspace` | ProductWorkspace: ecommAiLatest, ecommAiSuggest, ecommApiCatalog, ecommBrandHints, ecommConfirmMonthlyReview, ecommEanEvidence, ecommGetEdit, ecommMasterExport, ecommSaveEdit, ecommSavedEdits, ecommTaxonomy | Integrado para variantes API; parcial para históricos | Editor 18 campos, evidencias, propuestas e historial integrados. Conservar decisiones de registros históricos. |
| `/queue` | EnrichmentQueue: ecommAiLatest, ecommAiSuggest, ecommEanSummary, ecommGetEdit, ecommWorkQueue | Parcial | Cola API y lotes integrados; trasladar filtros históricos por ejecución cuando corresponda. |
| `/guia` | KikiGuide: ayuda/navegación | Pendiente | Conservar guía original; textos de ayuda del dashboard no sustituyen toda la guía. |
| `/propuestas-ia` | KikiAiInbox: ecommAiProposals | Parcial | Propuesta documental individual integrada; bandeja histórica de OpenAI no migrada completa. |
| `/work` | TaskCenter: enrichmentReviewQueue, finalPublicationQueue, inventoryLinkage, publicationReadiness, tiendanubeCommercialProposals, tiendanubeQualityAudit | Parcial | Operaciones editoriales persistentes integradas; conservar todas las tareas históricas. |
| `/work/details` | WorkQueue: brandNotApplicable, bulkApproveBrandProposals, bulkMarkGtinNotApplicable, catalogContinuity, duplicateReviewQueue, enrichmentReviewQueue, externalResearchQueue, finalPublicationQueue, internalDecisionHistory, inventoryLinkage, publicationReadiness, reconciliationReviewQueue, revokeInternalDecision, saveCatalogContinuityDecision, saveEnrichmentDecision, saveExternalResearch | Parcial | Selección API y cola persistente; decisiones históricas por ejecución no trasladadas. |
| `/channels` | Channels: mlAuthUrl, mlStatus, mlSync, tiendanubeReport | Parcial | Capturas, candidatos y validación por variante integrados. OAuth/sincronización siguen originales y bloqueados en pruebas. |
| `/products` | Products: products, tiendanubeReport | Parcial | Maestro API, faltantes y editor integrados; consultas históricas por ejecución conservadas en su interfaz. |
| `/readiness` | Readiness: inventoryLinkage, inventoryLinkageCandidates, markInventoryPendingEcomm, saveInventoryEcommAction, saveInventoryLinkageDecision, saveInventoryManualAssignment | Parcial | Completitud del editor y preparación visibles; reporte original de publicación no sustituido. |
| `/enrichment` | Enrichment: enrichmentPilot, enrichmentReviewQueue, saveEnrichmentDecision | Parcial | Propuestas respaldadas y revisión en panel; mantener revisión histórica de enriquecimiento. |
| `/external-research` | ExternalResearch: externalResearchQueue, saveExternalResearch | Parcial | Documentos locales, citas y revisión integrados; búsqueda real requiere dominios/autorización y conexión acotada. |
| `/prepublication` | Prepublication: finalPublicationQueue, prepublication, saveFinalPublicationApproval | Parcial | Preparación interna y evidencia de canales; cola histórica de prepublicación no migrada completa. |
| `/images` | ImageReview: prepublicationImages, savePrepublicationImages | Parcial | URLs de imágenes/videos y procedencia en editor; revisión especializada histórica permanece separada. |
| `/metadata` | MetadataReview: analyzePendingMetadata, analyzePrepublicationMetadata, prepublicationMetadata, savePrepublicationMetadata, validateConditionalMetadata | Parcial | Categoría, subcategoría y SEO editables; análisis y decisiones masivas históricas no migradas. |
| `/review` | Review: reconciliationReviewQueue, saveReconciliationReviewDecision | Parcial | Revisión por campo y canales API; conservar conciliación histórica por ejecución. |
| `/duplicate-review` | DuplicateReview: duplicateReviewQueue, saveDuplicateReviewDecision, saveDuplicateVariantsBatch | Parcial | EAN/SKU repetidos y familias filtrables, sin fusión. Resoluciones de grupos históricas no migradas. |
| `/tiendanube` | Imports: imports, tiendanubeAiDraft, tiendanubeAiOfflinePreview, tiendanubeAiReview, tiendanubeAiSaved, tiendanubeAssistedMatches, tiendanubeBulkPreview, tiendanubeBulkReject, tiendanubeCommercialProposals, tiendanubeDuplicateSkus, tiendanubeImageAudit, tiendanubeMatchDecision, tiendanubePriceStockAudit, tiendanubeQualityAudit, tiendanubeReport, tiendanubeSeoGuidelineAudit, upload, uploadTiendanube, uploadTiendanubeImages | Pendiente | CSV/Excel históricos conservados. No habilitar importación real en el demo ni reemplazar catálogo API. |
| `/imports` | Imports: imports, tiendanubeAiDraft, tiendanubeAiOfflinePreview, tiendanubeAiReview, tiendanubeAiSaved, tiendanubeAssistedMatches, tiendanubeBulkPreview, tiendanubeBulkReject, tiendanubeCommercialProposals, tiendanubeDuplicateSkus, tiendanubeImageAudit, tiendanubeMatchDecision, tiendanubePriceStockAudit, tiendanubeQualityAudit, tiendanubeReport, tiendanubeSeoGuidelineAudit, upload, uploadTiendanube, uploadTiendanubeImages | Pendiente | CSV/Excel históricos conservados. No habilitar importación real en el demo ni reemplazar catálogo API. |

## Contratos backend originales y adaptaciones

Todas las operaciones siguientes se inventariaron por sus decoradores; su presencia no demuestra disponibilidad de red ni autorización.

| Método / ruta | Implementación | Uso en dashboard y límites |
|---|---|---|
| `POST /api/auth/login` | `auth.py:35` · `login` | Reutilizado; credenciales/sesiones de pruebas sólo en arnés, nunca trasladadas a producción. |
| `GET /api/auth/me` | `auth.py:65` · `me` | Reutilizado; credenciales/sesiones de pruebas sólo en arnés, nunca trasladadas a producción. |
| `POST /api/auth/logout` | `auth.py:70` · `logout` | Reutilizado; credenciales/sesiones de pruebas sólo en arnés, nunca trasladadas a producción. |
| `POST /api/tiendanube/import-csv` | `catalog.py:110` · `import_tiendanube_csv` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/match-decision` | `catalog.py:134` · `tiendanube_match_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/matches/bulk-preview` | `catalog.py:157` · `tiendanube_matches_bulk_preview` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/matches/bulk-reject` | `catalog.py:169` · `tiendanube_matches_bulk_reject` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/ai/draft` | `catalog.py:187` · `tiendanube_ai_draft` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/ai/saved` | `catalog.py:208` · `tiendanube_ai_saved` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/ai/review` | `catalog.py:217` · `tiendanube_ai_review` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/ai/offline-preview` | `catalog.py:231` · `tiendanube_ai_offline_preview` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/seo-guideline-audit` | `catalog.py:243` · `tiendanube_seo_guideline_audit` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/commercial-proposals` | `catalog.py:261` · `tiendanube_commercial_proposals` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/assisted-matches` | `catalog.py:269` · `tiendanube_assisted_matches` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/duplicate-skus` | `catalog.py:274` · `tiendanube_duplicate_skus` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/price-stock-audit` | `catalog.py:279` · `tiendanube_price_stock_audit` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/quality-audit` | `catalog.py:284` · `tiendanube_quality_audit` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/tiendanube/images/import-csv` | `catalog.py:289` · `import_tiendanube_image_csv` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/images/audit` | `catalog.py:306` · `tiendanube_image_audit` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/tiendanube/reconciliation` | `catalog.py:311` · `tiendanube_reconciliation` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/imports/{source}` | `catalog.py:320` · `import_catalog` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/reconciliations` | `catalog.py:361` · `analyze` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/dashboard` | `catalog.py:376` · `dashboard` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/inventory-linkage` | `catalog.py:388` · `inventory_linkage` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/inventory-linkage/candidates` | `catalog.py:399` · `inventory_linkage_candidates` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/inventory-linkage/ecomm-action` | `catalog.py:420` · `inventory_linkage_ecomm_action` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/inventory-linkage/pending-ecomm` | `catalog.py:439` · `inventory_linkage_pending_ecomm` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/inventory-linkage/manual-assignment` | `catalog.py:457` · `inventory_linkage_manual_assignment` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/inventory-linkage/decision` | `catalog.py:476` · `inventory_linkage_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/catalog-continuity` | `catalog.py:496` · `catalog_continuity` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/catalog-continuity/decision` | `catalog.py:510` · `catalog_continuity_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/publication-readiness` | `catalog.py:529` · `publication_readiness` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/enrichment-pilot` | `catalog.py:542` · `enrichment_pilot` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/enrichment-review-queue` | `catalog.py:557` · `enrichment_review_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-review-decisions` | `catalog.py:571` · `enrichment_review_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-review-decisions/bulk-brand` | `catalog.py:591` · `enrichment_bulk_brand_approval` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-review-decisions/brand-not-applicable` | `catalog.py:606` · `brand_not_applicable` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/enrichment-decisions/history` | `catalog.py:623` · `internal_decision_history` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-decisions/revoke` | `catalog.py:628` · `revoke_internal_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/gtin-candidates/{product_key:path}` | `catalog.py:640` · `get_gtin_candidates` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/external-gtin-candidates/{product_key:path}` | `catalog.py:651` · `get_external_gtin_candidates` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/gtin-batch-pilot` | `catalog.py:662` · `gtin_batch_pilot` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/enrichment-external-research` | `catalog.py:673` · `enrichment_external_research_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-external-research` | `catalog.py:687` · `enrichment_external_research_save` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/enrichment-external-research/bulk-gtin-not-applicable` | `catalog.py:711` · `enrichment_external_research_bulk_gtin_not_applicable` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/products` | `catalog.py:735` · `products` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/imports` | `catalog.py:774` · `imports` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/ecomm-app/workspace/{ecomm_id}/evidence` | `documental_workspace.py:46` · `evidence` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/evidence/extract` | `documental_workspace.py:57` · `extract` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/evidence/facts/{fact_id}/review` | `documental_workspace.py:72` · `review_fact` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/documents/import` | `documental_workspace.py:93` · `incorporate` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/documents/{document_id}/provenance` | `documental_workspace.py:110` · `provenance` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `GET /api/ecomm-app/workspace/{ecomm_id}/documents/{document_id}/original/{version}` | `documental_workspace.py:123` · `original` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `GET /api/ecomm-app/workspace/{ecomm_id}/proposals` | `documental_workspace.py:136` · `proposals` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/proposals/generate` | `documental_workspace.py:155` · `generate` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/proposals/{draft_id}/review` | `documental_workspace.py:167` · `review_proposal` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `GET /api/ecomm-app/workspace/{ecomm_id}/proposals/generation-context` | `documental_workspace.py:186` · `generation_context` | Integrado: evidencia/propuesta por ID, CSRF, versiones; generación determinista. |
| `POST /api/duplicate-review/variants-batch` | `duplicate_review.py:29` · `duplicate_review_variants_batch` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/duplicate-review` | `duplicate_review.py:50` · `duplicate_review_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/duplicate-review` | `duplicate_review.py:64` · `duplicate_review_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/ecomm-app/workspace/channels/listings` | `ecomm_api_channels.py:85` · `captured_listings` | Integrado: capturas, lectura y decisiones locales por ID. Sin escritura a canales. |
| `GET /api/ecomm-app/workspace/{ecomm_id}/channels` | `ecomm_api_channels.py:103` · `read_channels` | Integrado: capturas, lectura y decisiones locales por ID. Sin escritura a canales. |
| `POST /api/ecomm-app/workspace/{ecomm_id}/channels/review` | `ecomm_api_channels.py:113` · `review` | Integrado: capturas, lectura y decisiones locales por ID. Sin escritura a canales. |
| `GET /api/ecomm-app/workspace/ai-proposals` | `ecomm_api_workspace.py:79` · `ai_proposals` | Parcial: servicio conservado; consulta OpenAI/latest accesible, generación real bloqueada. |
| `GET /api/ecomm-app/workspace/ai/{ecomm_id}/latest` | `ecomm_api_workspace.py:97` · `latest_ai_suggestion` | Parcial: servicio conservado; consulta OpenAI/latest accesible, generación real bloqueada. |
| `POST /api/ecomm-app/workspace/ai/{ecomm_id}/suggest` | `ecomm_api_workspace.py:109` · `generate_ai_suggestion` | Parcial: servicio conservado; consulta OpenAI/latest accesible, generación real bloqueada. |
| `GET /api/ecomm-app/workspace/brand-hints/{ecomm_id}` | `ecomm_api_workspace.py:124` · `brand_hints` | Integrado |
| `GET /api/ecomm-app/workspace/queue` | `ecomm_api_workspace.py:137` · `work_queue` | Integrado |
| `GET /api/ecomm-app/workspace/ean-evidence/summary` | `ecomm_api_workspace.py:156` · `legacy_ean_summary` | Parcial: servicio conservado; consulta OpenAI/latest accesible, generación real bloqueada. |
| `GET /api/ecomm-app/workspace/ean-evidence/{ecomm_id}` | `ecomm_api_workspace.py:168` · `legacy_ean_candidate` | Integrado |
| `GET /api/ecomm-app/workspace/taxonomy` | `ecomm_api_workspace.py:181` · `internal_taxonomy` | Parcial: servicio conservado; consulta OpenAI/latest accesible, generación real bloqueada. |
| `GET /api/ecomm-app/workspace/master-export` | `ecomm_api_workspace.py:193` · `internal_master_export` | Integrado |
| `GET /api/ecomm-app/workspace/saved` | `ecomm_api_workspace.py:206` · `list_saved` | Integrado |
| `POST /api/ecomm-app/workspace/{ecomm_id}/confirm-review` | `ecomm_api_workspace.py:221` · `confirm_monthly_review` | Integrado |
| `GET /api/ecomm-app/workspace/{ecomm_id}` | `ecomm_api_workspace.py:237` · `get_edit` | Integrado |
| `POST /api/ecomm-app/workspace/{ecomm_id}` | `ecomm_api_workspace.py:249` · `save_edit` | Integrado |
| `GET /api/ecomm-app/status` | `ecomm_app.py:68` · `ecomm_app_status` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/preview` | `ecomm_app.py:78` · `ecomm_app_preview` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/lookup` | `ecomm_app.py:86` · `ecomm_app_lookup` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/catalog-audit` | `ecomm_app.py:94` · `ecomm_app_catalog_audit` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/auto/status` | `ecomm_app.py:113` · `ecomm_app_auto_status` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/auto/start` | `ecomm_app.py:142` · `ecomm_app_auto_start` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/auto/step` | `ecomm_app.py:163` · `ecomm_app_auto_step` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/manual/start` | `ecomm_app.py:196` · `ecomm_app_manual_refresh_start` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/status` | `ecomm_app.py:218` · `ecomm_app_stage_status` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/catalog` | `ecomm_app.py:226` · `ecomm_app_stage_catalog` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/ml-reconciliation-preview` | `ecomm_app.py:242` · `ecomm_app_ml_reconciliation_preview` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/ml-cases` | `ecomm_app.py:270` · `ecomm_app_ml_cases` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/next` | `ecomm_app.py:314` · `ecomm_app_stage_next` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/compare` | `ecomm_app.py:325` · `ecomm_app_stage_compare` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/hybrid-preview` | `ecomm_app.py:339` · `ecomm_app_hybrid_preview` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `POST /api/ecomm-app/stage/live-stock-check` | `ecomm_app.py:352` · `ecomm_app_live_stock_check` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/commercial-audit` | `ecomm_app.py:365` · `ecomm_app_commercial_audit` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/tn-brand-evidence` | `ecomm_app.py:382` · `ecomm_app_tn_brand_evidence` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/stage/ml-brand-evidence` | `ecomm_app.py:394` · `ecomm_app_ml_brand_evidence` | Parcial: captura/lectura del catálogo reutilizada; sync/actualizaciones/auditorías originales no habilitados en pruebas. |
| `GET /api/ecomm-app/editorial-batches` | `editorial_batches.py:81` · `listing` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `POST /api/ecomm-app/editorial-batches/preview` | `editorial_batches.py:91` · `preview` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `GET /api/ecomm-app/editorial-batches/{batch_id}` | `editorial_batches.py:100` · `detail` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `POST /api/ecomm-app/editorial-batches/{batch_id}/start` | `editorial_batches.py:111` · `start` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `POST /api/ecomm-app/editorial-batches/{batch_id}/step` | `editorial_batches.py:124` · `step` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `POST /api/ecomm-app/editorial-batches/{batch_id}/cancel` | `editorial_batches.py:140` · `cancel` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `POST /api/ecomm-app/editorial-batches/{batch_id}/retry` | `editorial_batches.py:152` · `retry` | Integrado: previsualización, confirmación, ejecución incremental y revisión humana, sin proveedores. |
| `GET /api/mercadolibre/status` | `mercadolibre.py:18` · `status` | Conservado en aplicación original; OAuth/callback/sync bloqueados en entorno aislado. |
| `POST /api/mercadolibre/auth-url` | `mercadolibre.py:23` · `auth_url` | Conservado en aplicación original; OAuth/callback/sync bloqueados en entorno aislado. |
| `GET /api/mercadolibre/callback` | `mercadolibre.py:31` · `callback` | Conservado en aplicación original; OAuth/callback/sync bloqueados en entorno aislado. |
| `POST /api/mercadolibre/sync` | `mercadolibre.py:43` · `sync` | Conservado en aplicación original; OAuth/callback/sync bloqueados en entorno aislado. |
| `GET /api/prepublication` | `prepublication.py:58` · `prepublication_report` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/prepublication/final-queue` | `prepublication.py:72` · `final_publication_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/final-queue` | `prepublication.py:86` · `save_final_publication_approval` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/prepublication/images` | `prepublication.py:105` · `image_review_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/images` | `prepublication.py:119` · `save_image_review` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/prepublication/metadata` | `prepublication.py:145` · `metadata_review_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/metadata/analyze` | `prepublication.py:159` · `analyze_metadata` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/metadata/validate-conditional` | `prepublication.py:181` · `validate_conditional_metadata` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/metadata/analyze-pending` | `prepublication.py:232` · `analyze_pending_metadata` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/prepublication/metadata` | `prepublication.py:247` · `save_metadata_review` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `GET /api/reconciliation-review` | `reconciliation_review.py:22` · `reconciliation_review_queue` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |
| `POST /api/reconciliation-review` | `reconciliation_review.py:36` · `reconciliation_review_decision` | Conservado en aplicación original; traslado completo al panel pendiente. No habilitado por el demo. |

Total inventariado: 118 operaciones HTTP en los módulos de rutas existentes. También permanecen los endpoints declarados en `app/main.py` (salud), inventariados abajo.

| Método / ruta adicional | Función | Estado |
|---|---|---|
| `GET /health` | `health` (línea 63) | Conservado; no se habilitan escrituras históricas/productivas en el arnés. |

Operaciones adicionales en app/main.py: 1. Inventario total de decoradores HTTP: 119.

## Acciones comerciales transversales

| Función | Backend reutilizado | Ubicación / alcance | Pendiente concreto |
|---|---|---|---|
| EAN, SKU, conflictos y familias | `api_variant_row`, `compare_family_skus`, cola workspace | Calidad del catálogo, identidad de tabla, Canales | Candidatos no resuelven duplicados; conservar decisiones históricas separadas. |
| Catálogo y capturas ML/TN | `CatalogSnapshot`, `build_channel_coverage`, decisiones de vinculación existentes | Cinco vistas + Canales | Capturas auténticas sólo cuando integración autorizada las provea; sin conexión productiva en esta entrega. |
| Contenido, categorías, SEO, fotos y videos | `EcommApiProductWorkspace`, `CommercialBackofficeFields` | Ficha de 18 campos + faltantes | Verificación de derechos multimedia y validez específica de cada canal; no renderizar recursos externos en pruebas. |
| Investigación documental | `documental.Research`, `LocalDocuments`, lector/recolector 2G–2I | Evidencias y acción guiada | Búsqueda real deshabilitada; falta unir conector autorizado y descubrimiento real acotado. |
| IA y consumo | `EcommAiEditor`, `KikiEcommAiDailySlot`, drafts existentes | IA: consulta de estado/cuota y contrato; propuesta documental determinista | Cliente histórico produce título/descripción/preguntas. Falta adaptar salida completa con citas a hechos aprobados, validar costos/modelo y obtener autorización. |
| Revisión y guardado | `documental.Proposals`, mismo workspace/versionado | IA → decisión por campo → guardado → Historial | Aprobaciones de tests identificadas como automatizadas, nunca aprobación efectiva del cliente. |
| Procesamiento masivo | `editorial_batches`, cola workspace | Operaciones: selección, análisis, confirmación, trabajo backend, reanudar/cancelar | Investigación/IA pagada masivas bloqueadas; no aprobaciones/publicaciones automáticas. |
| Historial, revisión 30 días, exportación | `list_saved`, `confirm_review`, `export_master` | Historial global, ficha/Historial, Configuración | Exportación JSON interna, no CSV publicable ni publicación ejecutada. |
| Configuración | Settings original + preferencias de sesión | Configuración del dashboard | Preferencias visuales integradas; secretos, integraciones y presupuesto real permanecen en configuración original. |

La conservación de archivos/rutas no equivale a que la nueva interfaz dé acceso operativo a cada herramienta histórica. El build demo intercepta esas llamadas deliberadamente. Para la presentación, mostrar únicamente los recorridos integrados y mantener explícita esta diferencia. No apuntar los builds de prueba a producción para solventarla.
