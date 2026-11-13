"""Reviewable additive migration, never executed by app startup.

Only the checked disposable harness invokes UP in this stage. DOWN is destructive
and requires an export of documents/dossiers/draft references before any future use.
"""

UP = (
    "CREATE TABLE kiki_evidence_control (id INTEGER PRIMARY KEY CHECK (id = 1))",
    "INSERT INTO kiki_evidence_control (id) VALUES (1)",
    "CREATE TABLE kiki_evidence_documents (id VARCHAR(80) PRIMARY KEY, version INTEGER NOT NULL, body JSON NOT NULL, digest VARCHAR(64) NOT NULL, history JSON NOT NULL)",
    "CREATE INDEX kiki_evidence_documents_variant ON kiki_evidence_documents ((body->>'associated_ecomm_id'))",
    "CREATE TABLE kiki_evidence_dossiers (ecomm_id VARCHAR(120) PRIMARY KEY, version INTEGER NOT NULL, identity JSON NOT NULL, identity_digest VARCHAR(64) NOT NULL, facts JSON NOT NULL, history JSON NOT NULL)",
)
DOWN = (
    "DROP TABLE kiki_evidence_dossiers",
    "DROP TABLE kiki_evidence_documents",
    "DROP TABLE kiki_evidence_control",
)
