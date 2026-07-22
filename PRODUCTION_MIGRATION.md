# Production Migration Roadmap

This document outlines the strategic migration path from the current hackathon prototype of the Redline Consensus Engine to the enterprise-grade production architecture specified in the original PRD. It maps the tactical shortcuts taken for the demonstration directly to their scalable targets.

### 1. Immutable Audit Ledger: SQLite → BigQuery
* **Current State:** Synchronous writes to a local SQLite `audit.db` with on-demand Python loops to verify the hash-chain.
* **Production Target:** Google BigQuery. 
* **Migration Strategy:** The ledger schema remains nearly identical (`entry_id`, `timestamp`, `entry_type`, `payload`, `payload_hash`, `prev_hash`). However, streaming inserts will be routed through **Cloud Pub/Sub** to decouple database write latency from the time-sensitive multi-agent evaluation pipeline. The hash-chain validation will shift from an on-demand application-level query to a scheduled BigQuery routine to monitor ledger integrity continuously at scale.

### 2. Vector Embeddings: `fastembed` → Vertex AI `text-embedding-004`
* **Current State:** Local, CPU-bound `fastembed` generation yielding 384-dimensional vectors for quick prototyping.
* **Production Target:** Vertex AI `text-embedding-004`.
* **Migration Strategy:** Transitioning to Vertex AI increases vector dimensions from 384 to 768. This is not a hot-swappable configuration change; it requires a complete re-embedding of all seed data within the Qdrant collections (Compliance, Commercial Risk, Historical Precedents) and recreating the Qdrant index schemas to accommodate the wider vectors.

### 3. Workflow Orchestration: Lyzr Automata → LangGraph on GKE
* **Current State:** Synchronous routing through Lyzr Automata.
* **Production Target:** LangGraph deployed on Google Kubernetes Engine (GKE) paired with Pub/Sub-driven fan-out.
* **Migration Strategy:** As defined in PRD Section 16, synchronous orchestration becomes a critical bottleneck when processing thousands of clauses concurrently. The architecture will move to **LangGraph**, which natively handles stateful, cyclic graphs and parallel asynchronous branches. A Pub/Sub topic will fan out clauses to the Regulatory, Commercial, Precedent, and Data Privacy agents simultaneously, reuniting the responses at the Consensus gateway.

### 4. User Experience & Access Control: Streamlit → React / OPA
* **Current State:** A monolithic Streamlit application that simulates role-based access control (RBAC) using superficial UI visibility toggles.
* **Production Target:** Four distinct, purpose-built React portals (Legal Counsel, Compliance Officer, Legal Ops Admin, Auditor).
* **Migration Strategy:** Role-gating will migrate from the presentation layer to the backend. **Open Policy Agent (OPA)** will be deployed at the API Gateway layer to enforce strict, server-side data isolation, ensuring stakeholders only receive API responses they are explicitly authorized to view.

### 5. LLM Invocation: Google ADK → AI Control Plane & Guardrails
* **Current State:** Agents execute via Google ADK (`LlmAgent` + `Runner` + `InMemorySessionService`) targeting `gemini-2.5-flash`, with behavior heavily reliant on individual system prompts.
* **Production Target:** Unified routing through the **Model Router & Guardrail Engine** (AI Control Plane layer).
* **Migration Strategy:** Before any agent interacts with the underlying model, all prompts and outputs will pass through a centralized guardrail layer. This ensures that PII redaction, prompt injection screening, and citation hallucination checks are enforced systematically at the platform level, rather than ad-hoc within each agent's execution code.
