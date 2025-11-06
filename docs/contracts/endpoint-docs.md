# Endpoint Documentation References

This catalog lists primary documentation sources for every external service used by the AOP MCP. Use it alongside `docs/contracts/endpoint-matrix.md` when troubleshooting connectivity or onboarding new environments.

## AOP-Wiki SPARQL
- **Service description & mirror:** OpenRiskNet catalog — [https://openrisknet.org/e-infrastructure/services/133/](https://openrisknet.org/e-infrastructure/services/133/)
  - Notes: includes Virtuoso deployment at `http://aopwiki-rdf.prod.openrisknet.org/sparql` and contact information for the BiGCaT maintainers.
- **REST API companion (Swagger + examples):** VHP4Safety tutorial — [https://docs.vhp4safety.nl/en/latest/tutorials/aopwikiapi/aopwikiapi.html](https://docs.vhp4safety.nl/en/latest/tutorials/aopwikiapi/aopwikiapi.html)

## AOP-DB SPARQL
- **SPARQL data model & FAIR overview:** “The AOP-DB RDF” (Frontiers in Toxicology, 2022) — [https://pmc.ncbi.nlm.nih.gov/articles/PMC8915825/](https://pmc.ncbi.nlm.nih.gov/articles/PMC8915825/)
- **Self-hosting instructions & sample queries:** BiGCaT AOP-DB-RDF repository — [https://github.com/BiGCAT-UM/AOP-DB-RDF](https://github.com/BiGCAT-UM/AOP-DB-RDF)

## CompTox / CTX API
- **API landing page:** EPA CTX API hub — [https://www.epa.gov/comptox-tools/computational-toxicology-and-exposure-apis](https://www.epa.gov/comptox-tools/computational-toxicology-and-exposure-apis)
- **User guide (v1.1):** Figshare download — [https://epa.figshare.com/articles/online_resource/CTX_APIs_v1_0_0_User_Guide/28892738](https://epa.figshare.com/articles/online_resource/CTX_APIs_v1_0_0_User_Guide/28892738)

## MediaWiki Action API (AOP-Wiki publish path)
- **Authentication & CSRF tokens:** MediaWiki API docs — [https://www.mediawiki.org/wiki/API:Tokens](https://www.mediawiki.org/wiki/API:Tokens)
- **General login/edit workflow:** MediaWiki API main page — [https://www.mediawiki.org/wiki/API:Main_page](https://www.mediawiki.org/wiki/API:Main_page)

## AOPOntology Triple Store (GraphDB)
- **TLS configuration & certificate trust:** GraphDB documentation — [https://graphdb.ontotext.com/documentation/10.0/encryption.html](https://graphdb.ontotext.com/documentation/10.0/encryption.html)
- **Repository endpoint:** `https://ontology.aopkb.org/repositories/aopo` (requires trusted certificate or mutual agreement with AOPO maintainers).

## Usage notes
- Keep a local mirror of critical docs (PDFs, HTML exports) under `docs/contracts/reference/` if external hosting becomes unavailable.
- Update this file whenever endpoints change domains, mirrors, or authentication requirements.
- Live connectivity verification is tracked via `scripts/check_endpoints.py` and documented in `docs/contracts/endpoint-matrix.md`.

