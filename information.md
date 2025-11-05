Additional research:



"

Building an Adverse Outcome Pathway (AOP) “MCP -> 4” – Approach and Key Considerations







Understanding the AOP Framework



An Adverse Outcome Pathway (AOP) is a conceptual framework that links a molecular-level perturbation to an adverse outcome at the organism or population level . In practice, an AOP is a sequence of causally connected biological events: it starts with a Molecular Initiating Event (MIE) (e.g. a chemical interacting with a biomolecule) and progresses through intermediate Key Events (KEs) to culminate in an Adverse Outcome (AO) . Each step in the sequence is connected by a Key Event Relationship (KER) that describes the causal linkage between two events. By mapping how a stressor (such as a chemical) triggers changes from the molecular scale up through cells, tissues, organs, and ultimately to a health impairment, AOPs help us understand “the bigger picture” of toxicity . This framework organizes existing mechanistic knowledge in a transparent way, enabling better prediction of adverse health effects from mechanistic or in vitro data .



Key components of an AOP include:





Molecular Initiating Event (MIE): The initial biological interaction (often at the molecular level) that begins the pathway (e.g. a chemical binding to a receptor or inhibiting an enzyme).

Key Events (KEs): Measurable, essential biological changes that occur in sequence after the MIE. Each KE represents a step in the progression (e.g. protein degradation, cellular injury, organ impairment).

Adverse Outcome (AO): The final outcome of regulatory significance (e.g. disease, organism death, reproductive failure).

Key Event Relationships (KERs): The mechanistic linkages between consecutive KEs (including the MIE→KE1, KE1→KE2, …, KEn→AO). KERs capture the evidence that one event leads to the next.



Understanding these elements is crucial before building the AOP “MCP -> 4.” In the context of “MCP -> 4,” we interpret this as an AOP that leads to a particular adverse outcome (possibly denoted as “4”) from a starting perturbation (“MCP”). (If “MCP” is a specific initiating factor or pathway name, it will serve as the MIE or an early key event in this AOP.) The goal is to scientifically map out how MCP triggers a chain of biological events ending in the adverse outcome 4, using the AOP framework.







A Modular and Integrated Approach



When approaching the construction of this AOP, a modular strategy is recommended. AOPs are inherently modular: they consist of discrete key events and relationships that can be treated as building blocks . This modular structure facilitates expansion of the pathway and integration with other AOPs as needed . In practice, this means you should:





Identify all relevant key events from MCP to the final outcome. Compile a list of candidate events that have been reported in the literature between the initiating perturbation and the adverse outcome. Consider events at multiple levels of biology (molecular changes, cellular responses, tissue and organ effects, whole-organism outcomes).

Use existing AOP knowledge to inform your pathway. Before creating new descriptions for key events, search repositories like the AOP-Wiki for similar or related events. The international AOP knowledge base (AOP-Wiki) is a “virtual encyclopedia for AOP development”, where scientists catalogue and agree on key events and pathways . Leveraging existing key event descriptions from endorsed AOPs can save effort and ensure consistency across AOPs. For example, if MCP (the initiating mechanism) or any intermediate step has been described in another AOP, you can reuse that module. This avoids duplicating work and prevents redundancy by nesting previously characterized “sub-pathways” inside your AOP rather than reinventing them.



Now, regarding the approach “maybe all of them, or maybe an MCP with different MCPs inside,” this suggests you are considering whether to combine multiple pathways or sub-pathways into one AOP. Here’s how to decide:





Combining multiple sub-pathways (Integrated AOP Network): If there are several distinct mechanistic routes from the MIE to the adverse outcome, you can represent them as branches within a single AOP network. This is appropriate when the sub-pathways share key events or converge on the same outcome. By integrating them, you create a broader AOP that captures biological complexity. An example is AOP #296 for oxidative DNA damage, which was built to branch into two outcomes: one branch led to mutations and another to chromosomal aberrations, both stemming from a common upstream event . In that AOP, a single KE (inadequate DNA repair) splits into two routes: one route leads to increased mutations (Adverse Outcome 1) and the other to DNA strand breaks and chromosomal aberrations (Adverse Outcome 2) . This illustrates that a single AOP can accommodate multiple outcomes if they share upstream biology. Using such an integrated approach can be powerful – it highlights common steps and interactions between sub-pathways, and it minimizes redundancy by not treating each outcome as a completely separate pathway.

Keeping separate AOPs: On the other hand, if the routes from MCP to outcome “4” are highly divergent (sharing very few key events), it may make sense to develop them as separate AOPs that each lead to the same final outcome. You would then have parallel AOPs for each distinct mechanism, rather than one enormous pathway. In practice, these separate AOPs might still be linked as part of an AOP network at a higher level, but each would be easier to manage and review individually. The AOP framework allows for “networking” by connecting AOPs via shared key events – for instance, what is an MIE in one pathway could be a downstream key event in another . If you find that MCP actually encompasses multiple independent triggers, consider splitting them into distinct AOP entries and highlight any overlapping KEs among them. This keeps each AOP focused and avoids an unwieldy combined pathway.



Best practice: Start by drafting a comprehensive pathway including all plausible events (“all of them”), mapping every known step from MCP to outcome. This ensures you haven’t missed anything. Then critically evaluate which parts of that map truly need to be in one AOP. Where you see distinct branches that don’t interact until the outcome, you might compartmentalize those as separate AOPs (or clearly separated branches in one AOP). Where you see overlap or a common node, you consolidate. The result might be a master AOP with clearly delineated sub-pathways (modules) inside it – essentially an MCP with smaller MCPs inside, in the user’s words. Each sub-module can correspond to a known mechanism or subprocess. By structuring it this way, redundant steps (shared by multiple routes) are only documented once, and truly critical steps unique to each route are preserved.



In summary, an integrated network AOP is often preferable for closely related mechanisms leading to the same outcome, as it provides a holistic view. Just be sure to maintain clarity by using branching flow diagrams or a modular layout so readers can follow each path. If the complexity is too high, refactor into multiple AOPs for simplicity, but link them via common events to acknowledge the network.







Identifying Essential vs. Redundant Key Events



As you assemble the events, a crucial scientific exercise is to distinguish essential key events from those that might be optional or overlapping. Not every biological change observed under MCP exposure needs to be in the AOP – only those that are causally linked in driving the outcome should be included. Here’s how to refine the list:





Essential Key Events: These are events for which there is strong evidence that they must occur for the adverse outcome to happen. In AOP terminology, this is the essentiality of the KE – evidence that blocking or preventing that event prevents the downstream outcome . Focus on KEs that have demonstrated essentiality. For example, if MCP is known to cause outcome 4 only if it first triggers Event A, then Event A is essential. Any experiments where Event A was inhibited resulting in no adverse outcome would confirm its critical role. These essential KEs are the backbone of your pathway – the most important steps that define the AOP’s causality.

Supporting/Redundant Key Events: Some events may consistently accompany the pathway but are not strictly required or do not directly drive it. Others might be different manifestations of the same biological state. If two candidate KEs represent essentially the same biological change at different resolution (e.g., “cell injury” and “organ injury” might overlap), you might choose one as the representative KE or nest one under the other’s description. Redundant events can also be parallel processes: for instance, MCP might trigger two parallel signaling cascades that both end in the same next key event. In such a case, documenting both cascades separately could be redundant if they converge; instead, you might simplify by capturing the point of convergence as the KE. Always ask, “Does this event contribute new causal information, or is it covered by another event?” If an event can be removed with no loss of explanatory power (because another event on the pathway already covers that effect), then it may be redundant for the AOP narrative.



To determine essential vs. redundant, rely on the evidence:





Empirical support: Look for experimental or observational data showing the relationship of each KE to the outcome. Key considerations are the Bradford Hill criteria adapted for AOPs – namely temporal concordance (the upstream event occurs before the downstream outcome, and ideally if the upstream doesn’t happen, neither does the outcome), dose-response concordance (greater perturbation of the upstream event leads to more severe downstream outcome), and biological plausibility (it makes mechanistic sense that A leads to B). If a key event does not satisfy these, its role might be questionable. The weight-of-evidence evaluation in AOP development explicitly looks at dose, temporal and incidence concordance between KEs, and whether an upstream KE is required for a downstream KE (essentiality) . KEs that rank strongly on these criteria are your most important ones.

Weight of Evidence for KERs: For each KER (connection between events), gather the weight of evidence. Strong KERs support the inclusion of those events. If a presumed KER has very little empirical support or is very speculative, the upstream/downstream pair might not belong in the “core” pathway (at least not without flagging uncertainties). In a well-developed AOP, every adjacent pair of events is backed by some evidence or logical rationale . Additionally, consider non-adjacent evidence: sometimes experiments might link the MIE directly to the AO (skipping intermediate measures) – such evidence can bolster the overall pathway integrity . If a certain intermediate event has no observable impact on the final outcome (i.e. the outcome occurs even when that event is blocked or missing), that event may not be truly necessary – potentially a redundant side effect rather than a driver.

Biological logic: Use mechanistic understanding to decide if two events are actually distinct. For example, imagine MCP causes both Event X: increase in inflammatory cytokine and Event Y: activation of immune cells. If activating those immune cells is in fact a downstream consequence of the cytokine increase, then Event Y might not need to be listed separately – it could be considered a downstream manifestation of Event X. In contrast, if they are independent parallel events that both contribute to damage, you might keep both but show them as parallel branches converging later.



By critically reviewing each candidate KE with these considerations, you will refine the AOP to include only the most pertinent events. Redundant events (those that are duplicative or not causally impactful) can be pruned or merged, which makes the AOP clearer and more scientifically robust. The final set of key events should form a logically consistent chain from MCP to outcome, where removing any one essential event would break the progression (that’s a good test of essentiality).



It’s also worth documenting any uncertainties or data gaps as you do this. For instance, you might include a key event that is hypothesized but not yet well evidenced – it can remain, but you should note that the connection is tenuous. A rigorous AOP build will explicitly state such uncertainties and any inconsistent findings . This transparency is important for scientific credibility and helps focus future research (e.g. to confirm whether a suspected KE is truly important or not).







Stepwise Best Practices for Building “AOP MCP -> 4”



Bringing the above points together, here is a stepwise approach to build the AOP in a scientifically thorough way:





Define the Scope and Problem Formulation: Clearly state what adverse outcome “4” represents (e.g., a specific toxicity endpoint or disease) and what “MCP” represents as the initiator. Defining the scope ensures you target the right biological processes. Also consider the Domain of Applicability – i.e. the species, life stage, or context this AOP is relevant to. This will guide what information is needed (for example, an AOP for fish vs. humans may involve different specifics).

Gather All Candidate Information: Do an extensive literature survey on MCP’s mechanism and the outcome. Use databases (PubMed, etc.) and importantly the AOP-Wiki and AOP Knowledge Base. The AOP-Wiki search function can be extremely helpful – for example, Huliganga et al. (2022) describe searching the AOP-Wiki for key terms related to a new event to find if any existing KE could be adopted . Perform similar searches for MCP and any intermediate processes to see if they already exist as KEs or even as part of other AOPs. Record all potential KEs and KERs that you come across, even from disparate sources, to have a master list of “building blocks.”

Draft a Pathway Blueprint: Sketch a preliminary pathway from MCP to outcome 4 including all plausible steps (this could be a flowchart or just a written sequence). Don’t worry if it’s complex; include parallel routes or branching if literature suggests multiple ways the outcome can occur. At this stage, err on the side of inclusion – capture everything that might be relevant. Once sketched, verify that the sequence makes biological sense (check that upstream events logically lead to downstream ones). This is your chance to spot if certain events seem out of place or if there are gaps where a mechanism is missing.

Identify Redundancies and Merge Events if Needed: Review the draft and apply the redundancy test as discussed. If you find overlapping events, decide whether to merge them or choose one representative. If two pathways differ only in minor details, consider folding them together. Conversely, if the pathway seems to actually be two (or more) distinct networks that only share the start or end, decide if you will present them as one branched AOP or separate AOPs. This is also where you decide on the level of granularity of each key event – e.g., do you need two separate KEs for “enzyme inhibition” and “downstream metabolic buildup” if one causes the other, or is one KE sufficient to cover both? Aim for each KE to be a distinct, measurable step.

Research and Document the Evidence for Each KER: Now, for every linkage in the pathway (MCP → KE1, KE1 → KE2, …, last KE → AO), gather scientific evidence. This includes finding studies that demonstrate or support that relationship. Utilize systematic review principles if possible: for example, Huliganga et al. built an evidence map by systematically searching for studies on each KER in a data-rich case . You might not conduct a full systematic review for each link, but be methodical: search for dose-response data, temporal sequence data, and any known mechanism connecting the two events. Summarize the findings (e.g., “Chemical X activating pathway MCP leads to increased biomarker Y in multiple studies, which correlates with pathology Z”). Also note any contrary evidence (studies where the link didn’t hold). This exercise will highlight which steps are strongly supported and which are speculative. You may find some proposed KERs have almost no evidence – mark those as knowledge gaps or reconsider if they belong.

Weight-of-Evidence Assessment: Using the collected evidence, perform a weight-of-evidence evaluation for each KER and for the overall AOP. This is typically done following OECD’s guidance where you categorize support for biological plausibility, empirical support (dose/time concordance, consistency across studies), and essentiality of each KE . For example, if MCP -> KE1 has high biological plausibility and many consistent studies, it’s a high-confidence KER. If KE2 -> AO has sporadic evidence, mark it as moderate or low confidence. This structured assessment will help scientifically justify the inclusion of each step. It will also directly address which steps are “most important” – those with high weight of evidence – versus any that are more uncertain. If an event has only low support, but you keep it because it’s mechanistically reasonable, clearly note the uncertainty. By the end of this step, you should be able to answer: Which KEs are critical and well-supported? Which might be redundant or have weak support? Adjust the pathway if needed (for instance, you might decide to drop or combine a weakly supported redundant event here).

Assemble the AOP Document: Now, compile all of this into the formal AOP description. The standard format (as seen on AOP-Wiki or OECD AOP guidelines) includes sections for each of: MIE, individual KEs, the AO, and each KER between them. For each element, write a concise scientific description: what it is, how you detect/measure it, and summary of evidence for its role. Include citations to the literature for each key point. Also include an overall assessment section discussing the biological plausibility of the whole pathway, the domain of applicability (species, etc.), and the overall confidence in this AOP given the evidence. The document should read like a scientific report: be as precise and mechanistic as possible, cite experimental findings, and acknowledge uncertainties. The tone should be neutral and technical. For instance, “KE2: Mitochondrial dysfunction in liver cells – This event is characterized by a decline in ATP production and release of cytochrome c in hepatocytes. It has been observed following MCP exposure in multiple studies . Its occurrence is necessary for downstream cell death, as interventions that prevent mitochondrial depolarization also abrogate the later increase in apoptosis .” (Hypothetical example with citation structure). Such text ties the event to evidence and shows why it matters.

Peer Review and Iteration: Since AOP development is a global, collaborative effort, it’s valuable to get input from other experts. If possible, have colleagues or stakeholders review your AOP draft. They might point out missing literature or suggest that certain events are not needed. This peer feedback helps refine which components are truly the most important. Engaging with the AOP community (for example via the OECD’s AOP authorship groups or the AOP-Wiki forums) can also ensure your AOP aligns with current scientific consensus and uses consistent terminology.

Finalizing Structure – Nested MCPs if Applicable: If you opted for a complex AOP with sub-pathways (MCP with MCPs inside), double-check that the final write-up clearly delineates these. Often a figure or flowchart is crucial here. Create a schematic diagram of “AOP MCP -> 4” showing the flow of events. Indicate any branching points or convergences. This visual will help readers (and you) verify that the logic holds. Label the modules if needed (e.g., Module 1 could be one cascade, Module 2 another) and ensure the text explains each. If some sub-module was taken or adapted from an existing AOP, give credit or reference to that. The final structure should avoid any truly redundant duplication – e.g., if two sub-pathways share a KE, that KE should appear once in the diagram and serve as a junction. Each unique event should appear only once. This way the “nested” structure is efficient and scientifically clear.

Quality Check Against Standards: Cross-reference your AOP with the OECD AOP Handbook or guidance documents to ensure all required information is included. The OECD has outlined principles for AOP development (like using the guidance on assessing KER confidence, documenting uncertainties, etc.), and following those will add scientific rigor. For instance, check that for each KER you have described the biological plausibility and empirical evidence (and any known modulating factors or feedback loops that might alter it). Also verify that the naming of events is consistent with ontology (the AOP-Wiki provides suggested wording for common key events). Consistency and clarity here make the AOP more useful to others.



By following these steps, you effectively gather all the information needed to build the AOP and organize it in a scientifically robust manner. The key is thoroughness in literature research, critical thinking about what to include, and careful documentation of evidence.







Including Support for Editing/Writing AOPs



The user’s note about including support for editing/writing AOPs is very important. In a practical sense, once you have built this AOP, you want a system or platform that allows continuous improvement and collaboration – because scientific knowledge evolves. Here’s how to approach that:





Leverage AOP-Wiki or Similar Platforms: As mentioned, the AOP-Wiki is an established collaborative platform . It’s essentially a wiki-based system where each AOP (and each KE) has its own page that can be edited by registered contributors. If your project allows, contributing the AOP “MCP -> 4” to the AOP-Wiki would automatically provide an editing framework – you (and others) can update the pages as new data emerges. Even if you keep it internal, structuring your documentation like an AOP-Wiki entry is wise, since it aligns with community standards.

Designing an Editing Interface: If you are building a custom MCP tool or an internal knowledge base, consider creating an interface similar to a wiki or form-based editor for AOP elements. This means breaking down the AOP content into editable sections: one for the MIE, one for each KE, one for the AO, and fields for each KER evidence. A user (perhaps yourself or team members) should be able to go into the interface, select a key event, and modify its description or add new references. Likewise, adding a new key event or a new KER should be possible without rebuilding the whole thing from scratch. In software terms, your AOP could be represented as a database of objects (events and relationships) that can be created, edited, or deleted through a user-friendly UI. This modular data structure aligns with the modular nature of AOPs.

Version Control and Documentation: Scientific editing requires tracking changes. Ensure that your editing system keeps a history of revisions – who changed what and when – much like wiki version control. This is crucial for transparency and for reverting any changes if needed. It also aids in the peer-review process: one can see if new info was added and verify it. When you include support for writing AOPs, also include a way to attach citations and evidence easily (for instance, fields to paste reference DOI or links, and sections to summarize evidence quality). This encourages any updates to remain evidence-based.

Collaboration and Review Workflow: If multiple experts will contribute, implement a review or approval step. For example, one could allow free editing in a draft mode, but official changes to an “endorsed” AOP might need a review by a curator or a committee. This mirrors how OECD endorsement works for AOPs (where a panel reviews the AOP before it’s given status). Even if it’s just you initially, think ahead: as you “crowd-source” information or get input from colleagues, you might want an organized process to integrate that input.

Editing Support for Different Levels: Your system could also support editing at the key event level independently. Since key events are reused, editing a KE in one context could propagate to all AOPs using that KE. This is advanced but highly useful to avoid inconsistency. For example, if new research expands understanding of “MCP causes mitochondrial stress,” you update that KE’s page, and all AOPs containing that KE now have updated info. This was a design principle of the AOP-KB (Knowledge Base) to facilitate consistency across the network of AOPs . Make sure to implement safeguards here – one should be alerted that a change to a KE could affect multiple pathways.

User Guidance and Templates: Provide templates or guidelines within the editing interface so that contributors know what information to include. For instance, for each KER, prompt the user to fill in “Biological plausibility rationale,” “Empirical evidence summary,” “Uncertainties/inconsistencies,” etc. Pre-populating these sections (even if initially with “to be filled”) helps maintain a scientific writing style and ensures important aspects aren’t overlooked. Essentially, bake the scientific method into the editing tool.

Testing the System: Once editing support is in place, test it by actually writing up the AOP “MCP -> 4” with it. This will show whether the interface is intuitive and whether all necessary fields are present. You might realize you need an extra field for notes or a way to link to an external dataset, etc. Ensure that the final output (the assembled AOP report or page) reads well-formatted, as per the markdown or documentation standards the user needs. Short paragraphs, clear headings, and list formatting (as we are using in this answer) improve readability – your AOP content should ideally follow the same principles for clarity.



In essence, including support for editing/writing AOPs means acknowledging that the AOP is not static. As new scientific evidence comes, you (or others) will refine MCP’s pathway. A dynamic, collaborative platform like AOP-Wiki has proven effective for this purpose , so emulating its features is wise. This ensures the AOP “MCP -> 4” remains up-to-date and continuously vetted by the scientific community.







Conclusion



Building the AOP “MCP -> 4” will be a comprehensive task, but by approaching it systematically and scientifically, you can construct one of the “most important” AOPs with confidence. Start with a broad information gathering and pathway mapping, then streamline the pathway to focus on essential causative events. Utilize the modular nature of AOPs: incorporate existing knowledge modules and avoid redundancy by linking shared events rather than duplicating them. Throughout, apply scientific rigor – for each step, ask for evidence and document the cause-effect rationale using established criteria (biological plausibility, empirical support, essentiality).



The best approach is likely a hybrid strategy: create a master AOP that encompasses all known mechanisms from MCP to the adverse outcome, but structure it in clear modular segments (or branches) so that it’s digestible and not overly redundant. Identify which sub-pathways or events carry the most weight (these will be your focal points when communicating the AOP) and which are secondary. By doing so, you highlight the most important elements that drive the adverse outcome, aligning with the user’s emphasis on importance.



Finally, implement a robust way to edit and update the AOP. Science is ever-evolving, and an AOP, to remain relevant, should evolve with it. A collaborative platform or tool for writing the AOP ensures that new data on MCP or related events can be integrated, and that errors or gaps can be corrected by you or others. This not only improves the AOP’s quality over time but also encourages scientific consensus-building (since multiple experts can contribute and agree on the pathway). The AOP-Wiki model is a testament to how important community editing is for AOP development. Emulating that will lend your project credibility and longevity.



In summary, approach the AOP development like a scientific research project: hypothesize the pathway, gather evidence, refine the model (pathway) by distinguishing critical from redundant components, and document everything thoroughly with citations. By being as detailed and evidence-driven as possible, you will gather all the information needed to build the AOP “MCP -> 4” and do so in a way that is transparent, reproducible, and primed for future enhancements.



科学的アプローチで頑張ってください – good luck with your build, and ensure it remains a living document that grows with scientific knowledge! 



"





Can you evaluate this blueprint:

"Attribute

Description

Domain > Expert

Computational Toxicology / Knowledge Engineering > AOP Knowledge-Graph & MCP Systems Architect

Keywords

AOP-Wiki, AOPOntology, AOP-DB, MediaWiki Action API, SPARQL/GraphDB, PROV-O/BioLink

Goal

Design a production-grade architecture for an AOP MCP with bi‑directional read/write, ontology-normalized interop, and agentic querying; break into implementable tasks (V=5).

Assumptions

Target = human health NGRA; include eco endpoints where they inform exposure. Prioritize regulatory-aligned sources (OECD AOP‑KB/AOP‑Wiki), complement with EPA AOP‑DB & CompTox; require agent interop and editing support.

Methodology

Bottom‑up capability decomposition → reference APIs/ontologies → canonical data contracts → adapter/ETL plan → graph/semantic layer → MCP tools (read/write) → auth/audit → validation; reuse PBPK MCP patterns for auth/audit/async/CI. 









Executive blueprint — AOP MCP (read/write, ontology‑first, agent‑ready)







0) Why these sources and protocols



AOP‑Wiki / OECD AOP‑KB is the primary community/RegSci registry; it exposes content via a MediaWiki front‑end and has RDF/SPARQL mirrors for programmatic access. Use MediaWiki Action API for editing and SPARQL endpoints for query, giving both CRUD + graph traversal. 

AOP‑DB adds gene/chemical/disease linkages and stressor mappings (incl. CompTox/ToxCast ties) and is published with SPARQL mirrors; use for cross‑domain joins. 

AOPOntology (OWL) provides formal types for AOP entities/relations; anchor IDs/semantics to OWL/IRIs. 

CompTox Dashboard provides chemical identifiers and assay/bioactivity link‑outs to support stressor→AOP discovery. 



We’ll normalize everything to Biolink Model classes/relations (for interop with translators/agents) and capture edit provenance with W3C PROV‑O. 









1) Target capabilities (scope)



Read





Search/browse: AOPs, MIEs, KEs, KERs, AOs, stressors; species/lifestage applicability; assay links; references.

Graph reasoning: find_paths (MIE→AO), neighborhood expansion, branch detection, network overlays.

Evidence: retrieve KER weight‑of‑evidence facets (biological plausibility, temporal/dose concordance) where available.

Cross‑maps: chemicals (InChIKey/CAS) → stressors/AOPs (via AOP‑DB + CompTox); assays → MIE/KEs.



Write





Draft/edit: create/update KE, KER, AOP with references + applicability metadata; propose edits in a staging workspace.

Export/submit: generate MediaWiki Action API edits (requires login + CSRF) for AOP‑Wiki; generate OWL/RDF deltas for AOPOntology/graph stores; (optional) Effectopedia export packages. 



Interop





Ontology alignment: AOPOntology + Biolink (plus GO/CHEBI/MeSH CURIEs); provenance with PROV‑O. 



Agentic





Strict JSON Schemas for all tools; listable resources for caching; async jobs for heavy SPARQL/ingest; error taxonomy to aid self‑correction (reuse PBPK MCP patterns). 







2) Reference architecture (component view)

[Clients/Agents]

│ (MCP: list_tools, call_tool, list_resources)

▼

[ AOP MCP Server (FastAPI) ]

├─ Tool Layer (handlers, JSON schema, RBAC, audit)

├─ Resource Layer (paged, cacheable read-only listings)

├─ Job Service (async SPARQL/ingest/exports)

├─ Editors (MediaWiki Writer, OWL Writer)

├─ Graph API (Graph facade: SPARQL & Cypher adapters)

├─ Semantic Services (CURIE map, ID minting, validation)

└─ Provenance/Audit (PROV-O, hash-chained logs)

│

├─────────────── Integration Adapters ───────────────┐

│ │

▼ ▼

[AOP-Wiki SPARQL] [AOP-DB SPARQL] [CompTox API] [MediaWiki API] [AOPOntology store]

(VHP4Safety/OpenRiskNet) (read) (write) (OWL/RDF)



SPARQL sources: use VHP4Safety/OpenRiskNet endpoints for AOP‑Wiki and AOP‑DB; keep endpoint URLs configurable. 

Write surfaces: MediaWiki Action API for AOP‑Wiki edits; OWL write (AOPOntology) via OWLAPI/Tawny‑OWL pipeline. 



Pattern reuse from PBPK MCP: FastAPI scaffold, auth (JWT), audit trail (hash‑chained), async job framework, resource listings, CI/benchmarks—port as shared platform and add AOP‑specific adapters. 









3) Canonical data model (wire format)



Adopt Biolink (entities/associations) with AOPOntology class IRIs in category/semantic_type, CURIEs for cross‑refs, PROV-O blocks for provenance.







3.1 Core entities

// AOP (summary)

{

"id": "AOP:000296", // AOP-Wiki ID (CURIE/IRI resolvable)

"name": "Oxidative DNA damage leads to ...",

"category": "biolink:Pathway", // + "aopo:AdverseOutcomePathway"

"status": "OECD:UnderReview|Approved|Draft",

"key_events": ["KE:1234", "KE:5678"],

"kers": ["KER:111->222", "..."],

"adverse_outcome": "AO:4321",

"applicability": { "species": ["NCBITaxon:9606"], "life_stage": ["HsapDv:..."], "sex": ["PATO:..."] },

"stressor_refs": [{"chemical": "InChIKey:...", "source": "AOP-DB"}],

"evidence_summary": {"plausibility": "moderate", "temporal": "strong", "dose": "moderate"},

"provenance": { "prov:wasDerivedFrom": ["aopwiki:...#rev123"], "prov:generatedAtTime": "..." }

}

// Key Event (KE)

{

"id": "KE:1234",

"name": "Mitochondrial depolarization in hepatocyte",

"category": "biolink:BiologicalProcess", // + "aopo:KeyEvent"

"measurements": [{"assay_ref": "CompTox:TOXCAST_AID_..."}],

"taxon_applicability": ["NCBITaxon:9606","..."]

}

// Key Event Relationship (KER)

{

"id": "KER:1234->5678",

"upstream_ke": "KE:1234",

"downstream_ke": "KE:5678",

"relationship": "causally_upstream_of",

"biological_plausibility": "strong",

"temporal_concordance": "strong",

"dose_response_concordance": "moderate",

"uncertainties": "...",

"references": [{"doi":"10.1038/s41597-021-00962-3"}],

"provenance": { "prov:wasAttributedTo": "user:ivo", "prov:generatedAtTime": "..." }

}

Rationale: Biolink is designed for KG interop; PROV‑O expresses edit history and data lineage; AOPOntology provides domain semantics. 









4) Tool surface (MCP) — 

read & reason



Naming follows your PBPK MCP conventions (schemas, error taxonomy, resources, async). 



R1. search_aops

Inputs: { q?: string, filters?: { species?, outcome?, mie?, status? }, page?, page_size? }

Behavior: federated search over AOP‑Wiki SPARQL; returns AOP summaries with paging.



R2. get_aop

Inputs: { aop_id: "AOP:nnn" } → returns full AOP object + flattened KE/KER graph.



R3. list_key_events / get_key_event

List/search KEs; return detail (assay links, appplicability, references).



R4. list_kers / get_ker

Return KER with quantified evidence facets (if present).



R5. find_paths (graph reasoning)

Inputs: { from: {type:"MIE|KE|stressor", id/term}, to?: {type:"AO|KE", id/term}, max_hops?:int }

Executes SPARQL path queries over AOP‑Wiki / AOP‑DB to find mechanistic routes (branches). 



R6. map_chemical_to_aops

Inputs: { inchikey|cas|name } → uses CompTox and AOP‑DB stressor maps to return linked MIE/KE/AOPs. 



R7. map_assay_to_aops

Inputs: { assay_id } → maps to KE(s)/MIE(s) via AOP‑DB & CompTox assay associations. 



R8. get_applicability

Returns species/sex/lifestage applicability + notes.



R9. get_evidence_matrix

Returns per‑KER evidence flags (biological plausibility, temporal/dose concordance) + references; supports export (CSV/JSON).



R10. graph_query (advanced)

Inputs: { dialect:"SPARQL", query:string } (allow‑listed prefixes; time‑boxed; read‑only).









5) Tool surface (MCP) — 

write/edit



Writes are staged: local KG draft → review → publish to AOP‑Wiki (MediaWiki API) and/or AOPOntology OWL. 



W1. create_draft_aop

Inputs: { title, description, adverse_outcome, applicability, refs } → returns draft_id.



W2. add_or_update_ke

Inputs: { draft_id, ke: {...} } → upsert KE (de‑duplicate by label+semantic type; maintain KE reuse).



W3. add_or_update_ker

Inputs: { draft_id, ker: {...} } with upstream/downstream KE IDs; validates acyclicity + required evidence fields.



W4. link_stressor

Inputs: { draft_id, chemical_ref: {inchikey|cas}, source: "CompTox|AOP-DB" } → attaches stressor nodes with provenance. 



W5. validate_draft

Runs ontology & schema checks (AOPOntology class constraints, Biolink slot cardinality, ID CURIE validity, KE reuse policy).



W6. propose_publish

Prepares publish plan:





(a) MediaWiki: generate page edits (MIE/KE/KER/AOP pages) with CSRF token choreography and diff preview. 

(b) AOPOntology: OWL/RDF delta for triple store ingestion (OWLAPI/Tawny‑OWL). 



W7. publish

Executes the plan with RBAC; emits PROV‑O records and immutable audit entries (hash‑chain). (Reuse PBPK audit design.) 



W8. export_effectopedia (optional)

Emits an Effectopedia‑compatible package for manual import where automation is not available. 









6) Integration adapters (per source)



AOP‑Wiki SPARQL Adapter







Endpoints: configure VHP4Safety or OpenRiskNet mirrors. Support templated queries for AOP/KE/KER search and pathfinding. 

Rate‑limit; cache prepared statements; normalize IRIs to CURIEs.







AOP‑DB SPARQL Adapter







Aggregate gene/chemical/disease links; stressor lists; use for map_chemical_to_aops. 







MediaWiki Writer







Implement login→token→edit→watchlist flows; retries on edit conflicts; page section updates for KER tables; edit summaries include MCP job IDs. 







CompTox Adapter (read)







Resolve InChIKey/CAS, retrieve assay links where needed. (Use Dashboard web/API endpoints documented by EPA.) 







AOPOntology Writer







Build OWL serialization using OWLAPI (Java) or Tawny‑OWL; push to triple store (GraphDB/Blazegraph) or export RDF for load. 







7) Semantics & governance



ID strategy: Keep source IDs (AOP:####, KE:####, KER:####) + mint stable MCP IDs only for drafts/new entities; round‑trip mappings maintained.

Ontology: AOPOntology as domain types; Biolink for cross‑graph interop; additional CURIE spaces: GO, CHEBI, MeSH, NCBITaxon, HsapDv/Uberon as needed. 

Provenance: capture actor, activity, used sources, generated artifacts using PROV‑O. 

RBAC: read = public; write = author|reviewer|publisher roles (mirrors AOP community practices). Reuse JWT middleware patterns. 

Audit: immutable, hash‑chained logs with retention; same WORM storage hardening path as PBPK. 







8) Error taxonomy & agent‑friendly responses



UpstreamUnavailable (SPARQL endpoint down) → advisory with retry‑after.

AmbiguousMapping (chemical maps to multiple stressors) → return ranked candidates w/ hints.

EditorialConflict (wiki edit race) → supply latest revision and a merge plan.

SemanticViolation (ontology validation fail) → field‑level error.details entries (reuse PBPK enhancement). 







9) MVP → hardening (deliverable tasks)



Shape and sequencing mirror your PBPK MCP tasking style (architecture → scaffold → adapters → tools → agent workflows → auth/audit → perf). Where noted, items directly reuse your PBPK assets. 







Phase A — Foundations



Architecture & Tech Stack (AOP MCP) — doc ADRs; component + sequence diagrams; external endpoints catalog (SPARQL, MediaWiki); threat model extensions (write paths). (Reuse PBPK Task 1 patterns). 

Repo scaffold & CI — FastAPI server, JSON logging, /health, container, lint/test CI. (Reuse PBPK Task 2). 

Auth & Audit enablement — JWT roles (author|reviewer|publisher), audit middleware + hash chain; WORM backlog ADR. (Reuse PBPK Tasks 17, 18, 25). 

Resource pages — listable resources for aops/, kes/, kers/ (paged, cached). (Reuse PBPK Task 30). 







Phase B — Read adapters & tools



Adapter: AOP‑Wiki SPARQL — endpoint client, query templates, pagination, caching; compliance tests against VHP4Safety examples. 

Adapter: AOP‑DB SPARQL — stressor/gene joins; golden queries from OpenRiskNet examples. 

Adapter: CompTox — chemical resolver (InChIKey/CAS/name) + assay link retrieval. 

Tools: search_aops, get_aop, list_key_events, get_key_event, list_kers, get_ker — schemas, error mapping, tests.

Tool: find_paths — implement bounded SPARQL path queries; timeouts; explain plan. 

Tool: map_chemical_to_aops — federate AOP‑DB + CompTox; return ranked hits with provenance links. 

Tool: map_assay_to_aops — assay→KE/MIE mapping; returns AOP candidates with confidence.







Phase C — Semantics, validation, evidence



Semantic service — CURIE/IRI resolver, ID minting for drafts, synonym expansion; Biolink + AOPOntology validators. 

Evidence model — canonical KER evidence blocks; get_evidence_matrix; CSV/JSON exports.

Applicability service — normalize species/sex/lifestage to standard ontologies; expose via get_applicability.







Phase D — Write path (staging → publish)



Draft store — graph‑backed working copies; diff engine; PROV‑O capture. 

Edit tools — create_draft_aop, add_or_update_ke, add_or_update_ker, link_stressor, validate_draft.

Publish planners







MediaWiki plan generator (page names, sections, KER tables, CSRF choreography). 

AOPOntology OWL diff builder (OWLAPI/Tawny‑OWL). 







propose_publish & publish tools — RBAC gates, dry‑run, rollback on conflict; audit entries.







Phase E — Agent workflows & UX



LangGraph agent — planner → tool selector → confirmation (for write ops) → executor → summarizer; reuse PBPK LangGraph scaffolding and golden dialogues. 

Explanations — per result, return why matched (matched IRIs, path length, evidence highlights) to aid agent reasoning.

Docs & Quickstarts — “Find AOP for X”, “Map chemical→AOP”, “Propose a new KER”; API ref & examples. (Reuse PBPK Task 20 style). 







Phase F — Performance & hardening



Caching — query cache (keyed by SPARQL+prefix set), ETag/Last‑Modified; bounded result sets.

Async jobs — long SPARQL/ingest/export routed to JobService; progress polling. (Reuse PBPK Tasks 8–11, 23). 

Compliance harness — schema linting, unknown field rejection, transport checks for stdio/HTTP (reuse PBPK Task 31). 

Benchmarks — latency/throughput goals; SPARQL query cost tracking. (Reuse PBPK Task 19). 







10) Detailed JSON Schemas (snippets)

// search_aops.request

{

"type":"object",

"properties":{

"q":{"type":"string"},

"filters":{

"type":"object",

"properties":{

"species":{"type":"array","items":{"type":"string","pattern":"^[A-Za-z]+:\\S+$"}},

"outcome":{"type":"string"},

"mie":{"type":"string"},

"status":{"enum":["Draft","UnderReview","Approved"]}

}

},

"page":{"type":"integer","minimum":1,"default":1},

"page_size":{"type":"integer","minimum":1,"maximum":200,"default":50}

},

"additionalProperties":false

}

// publish.plan (MediaWiki)

{

"type":"object",

"properties":{

"target":"string",

"operations":{

"type":"array",

"items":{

"type":"object",

"properties":{

"page":"string",

"section":{"type":["string","null"]},

"content_patch":"string", // wikitext diff

"summary":"string"

},

"required":["page","content_patch"]

}

},

"csrf":"string"

},

"required":["target","operations"]

}







11) Validation & testing strategy



Unit: adapters (SPARQL queries snapshot‑tested), schema validation, semantic checks.

Integration: golden queries against AOP‑Wiki/AOP‑DB SPARQL; simulate MediaWiki edit conflict (409); CompTox lookups. 

E2E agent: dialogues for “find AO‑liver fibrosis paths”, “map chemical→AOP”, “propose KER → publish dry‑run”.

Security: RBAC matrix, token expiry/rotation, PII redaction in audits (reuse PBPK Task 17/18 tests). 







12) Additional research to de‑risk (short list)



Endpoint reliability: pick two SPARQL mirrors (VHP4Safety + OpenRiskNet) and test result/IRI parity; document failover. 

AOP‑Wiki write policy: confirm whether bulk automated edits are permitted under governance; if restricted, default to patch export + human submission. (MediaWiki API supports edits; site policy governs usage.) 

AOP‑DB schema drift: verify latest RDF graph (tables/IRIs) align with 2021 v2 paper; pin SPARQL templates per version. 

Assay mappings: catalogue trusted assay→KE mappings (AOP‑DB + specific consortia); decide confidence scoring and disambiguation policy. 

AOPOntology update cadence: confirm class IRIs and deprecations; define version pin + migration guide. 

CompTox API limits: confirm rate limits/keys and available endpoints for assay links and chemical resolution. 

Effectopedia IO: validate current import packaging; decide whether to support export only or bidirectional sync. 







13) Mapping to your PBPK MCP patterns (for the coding agent)



Server/CI: identical bootstrap, health endpoint, container, lint/tests. 

Async: reuse JobService abstractions; long SPARQL/ingest/export dispatched as jobs; unify get_job_status. 

Auth/Audit: transplant JWT roles + audit hash‑chain with minimal changes (new event types: SPARQL_QUERY, WIKI_EDIT, OWL_EXPORT). 

Agent: port LangGraph planner/confirm flow; mark write tools as critical, require HITL confirmation; extend prompts. 

Compliance harness: run existing MCP conformance + add SPARQL safety tests (prefix allow‑list, LIMIT required). 







14) “Most important first” (P0 set)



AOP‑Wiki SPARQL adapter + search_aops/get_aop/list_key_events/list_kers. 

find_paths graph traversal with guardrails. 

map_chemical_to_aops (AOP‑DB + CompTox). 

Draft store + create_draft_aop and validate_draft.

Publish dry‑run (plan only) for MediaWiki + OWL export.



With this, an agent can discover relevant AOPs, reason over pathways, link chemicals, and author drafts—covering the majority of NGRA mechanistic workflows.









15) Notes on redundancy & complementarity (for design)



AOP‑Wiki vs AOP‑DB: AOP‑Wiki is authoritative for curated AOP/KE/KER narrative; AOP‑DB adds omics/chemical/disease links and stressor lists; use AOP‑Wiki for semantic spine; enrich with AOP‑DB edges. 

AOPOntology: not a data source but the type system; use to validate and to generate OWL exports. 

CompTox: canonical chem resolver + assay context; do not duplicate in MCP store; query on demand and cache. 

Effectopedia: treat as optional export channel; do not rely on it for programmatic edits unless an API is stabilized. 







16) Security, compliance, and operations



SPARQL safety: enforce prefix allow‑list, LIMIT/OFFSET, max exec time; scrub user input to avoid injected SERVICE queries.

Write ops: require elevated roles; always stage; show diffs; include reCAPTCHA/human‑in‑the‑loop options for public deployments.

Ops: dual SPARQL endpoints (failover), health probes that run a cheap ASK query; SLOs captured in perf plan (reuse PBPK perf harness). 







17) What you’ll hand your coding agent (task cards)



/docs/adr/: Stack choice (FastAPI, SPARQLWrapper/HTTPx, OWLAPI bridge, MediaWiki client), endpoint config, failover policy.

/docs/contracts/: JSON Schemas for all tools; OpenAPI doc for transport wrapper.

/src/adapters/: aopwiki_sparql.py, aopdb_sparql.py, comptox.py, mediawiki.py, owl_writer/ (JNI or service).

/src/tools/: R*/W* handlers; error mapping utilities (with error.details). 

/tests/golden/: SPARQL query snapshots and response fixtures (from VHP4Safety tutorials); mediawiki edit conflict simulations. 

/docs/quickstarts/: “Find AOP”, “Map chemical”, “Draft & publish”.







Quick references for APIs & docs



AOP‑Wiki / AOP‑KB: overview & SPARQL service docs. 

AOP‑Wiki RDF/SPARQL publication (methods): peer‑reviewed description & endpoint. 

AOP‑DB (paper & milestones; SPARQL mirror). 

CompTox Dashboard (API/resource hub). 

MediaWiki Action API (read/write programmatic editing). 

AOPOntology / OWLAPI / Tawny‑OWL (ontology/write stack). 

Biolink Model (schema + toolkit). 

PROV‑O (provenance). 







Final checklist (before build)



Confirm SPARQL endpoints & credentials; record SLAs. 

Decide OWL writer path (JNI OWLAPI vs service) and triple‑store target. 

Validate AOP‑Wiki site policy for automation; if restricted, keep export‑only publish plan. 

Lock Biolink/AOPOntology versions; freeze CURIE maps. 

Port PBPK auth/audit/async modules; update error taxonomy to include SPARQL/Editorial classes. 



If you want, I can next generate concrete JSON Schemas for each tool and the first ten SPARQL templates (AOP list by AO, KE by label, KER by KE pair, shortest path MIE→AO, stressor→AOP via AOP‑DB), ready for copy‑paste into the repo."



Is this a good plan am i ready to start building?