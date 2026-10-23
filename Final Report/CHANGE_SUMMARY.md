# Change Summary – QAOA Dark Store Optimization Final Report

**Outputs**
- `QAOA_Dark_Store_Optimization_Final_Report.docx`: editable report, 63 pages (validated, 124 native Word equation objects)
- `QAOA_Dark_Store_Optimization_Final_Report.pdf`: PDF export, **63 pages** (7 front-matter + 56 body/references), no blank pages
- `supporting_runs/`: JSON outputs of the experiment re-runs and the pytest summary
- Original `report.qaoa.docx`: **unchanged** (byte-for-byte verified)

**Page count note:** WPS Office (the Word engine on this PC) rendered the original report at 50 pages, but you counted 47 in Word, so WPS runs about 6% longer. The final report should therefore come to about 59–60 pages in Microsoft Word.

## How the report was produced
The original DOCX was a PDF-to-Word conversion: every page was a separate section, the equations were images, and the code listings were broken across lines. Inserting 13 pages into it would have broken the layout. So the report was rebuilt from the original text, figures and tables, and it keeps the institutional format: A4 paper, the original margins, Times New Roman 12 pt at 1.5 line spacing, centred "CHAPTER N / TITLE" headings, roman page numbers for front matter and arabic numbers for the body.

## New and restructured chapters
| Chapter | Change |
|---|---|
| 1 Introduction | Expanded into 10 sections: background, dark stores and the delivery promise, inventory, motivation, quantum optimization, problem statement, objectives, scope, tools, organisation |
| 2 Literature Survey | Reorganised into 9 themed sections: base paper, facility location, inventory, QUBO, QAOA, classical methods, hybrid pipelines, gap. Table 2.1 kept |
| **3 System Analysis (new, complete)** | 3.1 Existing system, 3.2 Limitations, 3.3 Proposed system (with an implemented-vs-proposed table), 3.4 Feasibility (technical, economic, operational, schedule), 3.5 Hardware/software, 3.6 Functional, 3.7 Non-functional, 3.8 Constraints and assumptions, 3.9 Architecture. Absorbs old Ch. 4 |
| 4 System Design and Methodology | Combines the old Ch. 3 mathematics, old Ch. 5 flow charts and the conference paper: datasets/provenance, paper formulation, **implemented** formulation, QUBO, worked example, Ising/QAOA, baseline, metrics |
| 5 Modules | Old Ch. 6, corrected to match the code |
| 6 Implementation | Replaces old "Coding" Ch. 7. The old listings (`data_prep.py`, `qubo_builder.py`, …) **do not exist in the project**, so they were replaced with real excerpts from `backend/app/services`, plus the API, database, frontend and configuration |
| 7 Testing | The real 60-test suite, re-run: **60 passed in 17.30 s** |
| 8 Results and Discussion | Experiments A–E kept separate, with depth sensitivity, full-network classical run, scaling study, memory, discussion, limitations |
| 9 Conclusion and Future Scope | Rewritten around the verified results |

## Corrections made after checking the code (important)
1. **The objective is net margin (maximised), not total cost.** ₹14,716.14 is margin served − rider cost − opening cost. The paper's cost-minimisation model (y, x, z) is kept as the "conceptual formulation" (Eq. 4.2–4.7), and the implemented model (Eq. 4.8–4.18) is presented with a mapping table (Table 4.3).
2. Inventory is **derived** from the assignment, so there are no z_jk variables. Each zone is served by **at most** one store, not exactly one. The delivery limit is **structural**: links that break it are never created.
3. The QUBO uses a **compact encoding** (minimal violating subsets + AND gadgets) by default, not slack bits: 11 qubits vs 62 on the prototype. The penalty weight comes from Eq. 4.25.
4. The simulator is Qiskit's **StatevectorSampler**, not Qiskit Aer, with SciPy COBYLA. `qiskit_algorithms.QAOA` is not used.
5. The frontend uses **Recharts**, not Plotly. The live-order **fast path is design only**, not implemented. The prototype instance uses **demo values and straight-line travel estimates**, not OSRM.

## Equations
37 numbered display equations in Chapter 4 and 1 in Chapter 8, all native, editable Word (OMML) equations numbered at the right margin, plus inline math. The original equation images were replaced. Every symbol is defined in the text or in Table 4.2.

## New tables and figures
- **New figures:** sequential vs joint planning (3.1), implemented architecture and data flow (3.2), QAOA workflow (4.2), database ER diagram (6.1), depth sensitivity (8.3), runtime comparison (8.4)
- **New tables:** implementation status, existing vs proposed, software, hardware, functional requirements, non-functional requirements, constraints/assumptions, datasets/provenance, variables, formulation mapping, worked-example data, backend files, REST API, test suite, design-level test coverage, experiment overview, Experiments A/C/D, depth sweep, scaling study, memory, classical vs QAOA
- **Front matter:** auto-generated Table of Contents, List of Figures, List of Tables, List of Abbreviations

## Experimental values (verified)
| Exp. | Instance | Objective (both methods) | Notes |
|---|---|---|---|
| A | 3 demo stores × 3 areas × 3 products, 11 qubits | ₹14,716.14 | Brute force over 2,048 states agrees; 100% service; p=1/2 gave ₹10,846.00 |
| B | Supabase-backed | ₹101,374.45 | **Taken from your brief; no record found locally** |
| C | 4 OSM outlets × 4 zones × 25 products, 15 qubits | ₹100,704.01 | **50% service** (2 zones unreachable in 15 min); QAOA 18.58 s vs CBC 0.087 s recorded |
| D | 48 outlets × 46 zones × 25 products, classical only | ₹1,475,725.67 (B=₹20k, time limit hit) / ₹2,205,629.54 (B=₹100k, proven) | Run during report preparation |
| E | Earlier development scaling study (synthetic) | from `data/stage5_scaling.csv` | Different model; trends only |

## References
The original 10 references were kept and 21 verifiable standard references were added (Farhi et al. 2014; Lucas 2014; Glover et al. 2019; Boros & Hammer 2002; Hadfield et al. 2019; Zhou et al. 2020; Preskill 2018; Peruzzo et al. 2014; Powell 1994; Mitchell et al. 2011; Luxen & Vetter 2011; Haklay & Weber 2008; Javadi-Abhari et al. 2024; Owen & Daskin 1998; Melo et al. 2009; Church & ReVelle 1974; Daskin et al. 2002; Shen et al. 2003; Harris 1913; Land & Doig 1960; Kirkpatrick et al. 1983). The list is alphabetical and numbered, and every entry is cited in the text.

## Items needing your confirmation
1. **Experiment B (₹101,374.45):** the instance (stores/zones/products), qubits, service level and runtimes. They live in Supabase, which I did not access. Also: is this the run you meant as "later", and is the "separate larger run" Experiment C (₹100,704.01, 50% service)?
2. **Cover page, certificate, declaration, acknowledgement:** these are not in the supplied DOCX, so add your institution's pages in front.
3. **Table 2.1 sources** (Sinha 2026, Vanderbist 2026, Afrasiabi 2026, Li 2026, Tokar 2026, Tata Elxsi 2025, Vinci 2025, Nishimura 2025, Zalando 2025, Merali 2025, Ullah 2024, Ganz 2024, Wang 2023, Hedayatnia 2023, Bhattacharyya 2022) are cited author-year as in your original but **have no full entries in the reference list**. Supply the full details to add them.
4. **Development hardware:** CPU/RAM were measured on this PC (i5-1335U, 16 GB). Confirm it is the development machine and give the storage size.
5. **Supabase hosting tier** (for the economic feasibility section) and the **project timeline** (schedule feasibility).
6. **"MILP solved the full 48 × 163 network"** in the paper/abstract: no saved record was found. The report instead cites the verified Experiment D (48 outlets × 46 demand zones).
7. **The 1.38 s QAOA runtime** comes from the backend README, measured on the development machine. The re-run here took 7.31 s, and both are reported.
8. **Code finding:** when CBC hits its time limit, PuLP can still label the result "Optimal", and the backend's `proven_optimal` flag follows that label. This was seen in Experiment D (₹20k budget). Consider checking `prob.sol_status` in `classical_service.py`.
