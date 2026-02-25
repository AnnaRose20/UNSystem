Technical Assignment: UN Organizations Document Intelligence Pipeline
Conceptual Foundation
As a starting point for understanding the structure of the United Nations system, please use the following article:
https://de.wikipedia.org/wiki/Vereinte_Nationen
From this overview, you are expected to derive:
- A structured model of UN main organs, subsidiary organs, programs, funds, and specialized agencies
- A crawling and consolidation strategy that reflects this organizational hierarchy
Additionally, we provide
a seed list of UN-related URLs that can be used as a starting point for scraping (you are free to expand or refine it if you identify better sources). You may either use this list directly or design your own improved seed selection strategy.
And an Entity relationship model, which you can use as an initial understanding of the UNO on conceptual level
Objective
Design and implement a system that:
1. Represents the UNO and extracts publicly available documents from UN organizations

2. Consolidates and normalizes them

3. Organizes them into a clean, professional data schema

4. Stores them in a locally hosted database

5. Provides structured access through an API endpoint

6. Bonus: think about you cases (Dashboard, Chatbot, ….)
Required Scope
1) Data Extraction & Crawling Strategy
Define a clear crawling model based on the UN organizational structure
Explain:
How sources are identified
How hierarchy is preserved
How updates and versioning are handled
Extract:
Documents
Metadata (title, publication date, language, organization, document type, source URL, etc.)
Store raw files and metadata separately
There is no right or wrong. We are particularly interested in your architectural reasoning here.
2) Data Model & Schema Design
Design a normalized schema that may include:
- UN Organizations (hierarchy-aware)
- Documents
- Topics / Tags (if extracted)
- Relationships between organizations and thematic areas
- Versioning / checksums
- Optional: semantic embeddings storage
Please document your schema design and trade-offs.
3) Implementation
Provide a working implementation including:
Extraction pipeline
Data cleaning & normalization
Local database setup (Postgres, SQLite, or similar)
Migration / schema definition
Clear reproducibility via README
4) API Endpoint
Provide a structured query interface (e.g., FastAPI, REST, or GraphQL) supporting queries such as:
List documents by organization
Filter by time range
Filter by document type
Search by keyword
Optional: semantic search
Bonus (AI Enrichment & Semantic Intelligence)
This is strongly encouraged but optional.
We explicitly allow — and encourage — the use of AI tools to assist your development process. We are interested in how you leverage AI productively and methodologically.

Your structured explanation of how AI was used — both in development and in the data pipeline — will be part of the evaluation.
Deliverables, please provide:
A concise architectural overview (max. 5 pages)
Well organised code repository
Database schema
API implementation
Setup instructions (README)
Optional: demonstration of AI usage to find trends in UNO
