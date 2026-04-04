# PegaSUS Project

**PegaSUS** is a disease-agnostic, code-aware, support-aware, hierarchical epidemiological discovery engine built to organize, compile, and scan large heterogeneous Brazilian public-health and socioeconomic data systems — especially DATASUS and SIDRA — for statistically material spatiotemporal structure.

The name combines **Pegasus** and **DATASUS**: it signals both the scale of the workload and the fact that the project is meant to fly above many separate systems without collapsing into one gigantic, unmanageable master table.

---

# 1. Executive summary

## 1.1 What PegaSUS is

PegaSUS is a system for:

1. **ingesting heterogeneous source data** from DATASUS and SIDRA,
2. **normalizing them into a common canonical record model**,
3. **treating disease/code systems as first-class ontologies**,
4. **compiling raw records into lawful epidemiological observables**,
5. **aligning those observables onto a common analysis lattice** (usually municipality × year),
6. **building a structured search frontier** over many observable families at once,
7. **scanning that frontier for stable spatiotemporal links**, and
8. **descending hierarchically only where signal survives**.

It is **not** a dashboard, **not** a static warehouse of indicators, **not** a disease-specific workflow, and **not** one giant city-year table.

It is a **general epidemiological search engine** over a latent structured state space.

## 1.2 What problem it solves

The motivating problem is this:

* DATASUS is rich but messy.
* SIDRA is rich but heterogeneous.
* Many epidemiological patterns are only visible when the right disease codes, support roles, subgroup branches, temporal alignments, denominators, and contextual variables are combined.
* A naïve strategy of flattening everything into one huge municipality-year table does not scale and becomes statistically unstable.

PegaSUS solves this by replacing “one gigantic explicit table” with **hierarchical materialization** of only the observable instances that are needed at each stage.

## 1.3 One-sentence definition

**PegaSUS is a disease-agnostic, code-centric, hierarchical statistical engine that compiles heterogeneous public-health records into typed observable families and searches them for stable spatiotemporal epidemiological structure across space, time, code hierarchies, subgroup strata, and support roles.**

---

# 2. Why this project exists

## 2.1 The naïve approach is structurally wrong

The simplest possible approach would be:

1. download many source tables,
2. aggregate all of them to municipality × year,
3. join everything into one master matrix,
4. run models, correlations, or scans.

This is wrong for three deep reasons.

### A. Combinatorial explosion

The true latent data space includes:

* source system,
* support role,
* disease code family,
* diagnosis/cause/anomaly code role,
* age,
* sex,
* race/color,
* education,
* maternal variables,
* continuous clinical variables,
* thresholded clinical conditions,
* time,
* space,
* and multiple representations of the same burden.

Fully tabulating all combinations produces a combinatorial object that is far larger than what is statistically or computationally sane.

### B. Semantic incoherence

The variables are not all of the same kind.

Some are:

* event counts,
* subset counts,
* denominators,
* context variables,
* repeated annotations,
* continuous measurements,
* disease code memberships,
* support-role indicators.

They cannot all be treated as ordinary columns in one flat matrix without violating their meaning.

### C. Statistical instability

At high granularity, many cells are sparse or empty.
Direct scanning of an explicit giant table becomes dominated by:

* low-count noise,
* denominator instability,
* false positives from multiple testing,
* broad confounding structure,
* and support mismatch artifacts.

So the correct architectural response is **not to explicitly materialize the full state space**. The correct response is to define that space formally and only materialize a controlled active frontier.

---

# 3. The project’s central theoretical idea

The core idea is that epidemiology, at least for this project, can be represented as a governed search problem over a latent high-dimensional state space with disciplined rules for:

* **support**,
* **support role**,
* **carrier/event type**,
* **code roles and ontologies**,
* **subgroup variables**,
* **continuous clinical attributes**,
* **annotation structures**,
* **measure transformations**,
* **uncertainty propagation**,
* **temporal/spatial operators**,
* and **hierarchical refinement**.

PegaSUS does **not** store this whole state space explicitly.
Instead, it acts as a **lazy hierarchical materializer** over it.

That is the central architectural move.

---

# 4. Design principles

## 4.1 Disease-agnostic, not disease-specific

The architecture is **not** organized around separate disease workflows.
Diseases are queried and explored as **code-defined regions** of a larger shared epidemiologic state space.

This is crucial.
PegaSUS should be able to examine syphilis, Zika, dengue, AIDS, congenital anomalies, violence notifications, chronic diseases, or cross-disease patterns using the same mathematical machinery.

## 4.2 Code systems are central

Space and time are central, but so are **code ontologies**.

ICD-like systems — and more generally condition, diagnosis, cause, anomaly, and procedure code systems — are among the engine’s main organizational axes.
They determine:

* what disease family is being hunted,
* how events are grouped,
* how coarse disease categories descend into finer ones,
* and how different datasets can be compared through common or linked code structures.

## 4.3 Support role is explicit

Residence, occurrence, notification, hospitalization, death occurrence, and birth occurrence are not interchangeable.

Support role must be explicit from the start, not patched in later.

## 4.4 Hierarchy is essential, not decorative

The hierarchy exists because the full explicit mega-table is the wrong computational object.

The system must begin with coarse but meaningful observables and descend only where:

* signal is stable,
* sparsity is tolerable,
* interpretability improves,
* and uncertainty remains acceptable.

## 4.5 Every transformation must be lawful

The engine is not allowed to arbitrarily manipulate data objects.

Aggregation, rate construction, context projection, latent disaggregation, standardization, thresholding, shrinkage, and refinement all have to obey explicit type laws.

## 4.6 Uncertainty is first-class

Sparse denominators, low counts, latent lifts, reporting issues, and support mismatch are not afterthoughts.
Each observable must carry uncertainty information that influences both scanning and refinement.

---

# 5. Source ecosystem the architecture is meant for

## 5.1 DATASUS

DATASUS source systems are typically row-oriented, source-specific registries or event systems.
They are not already organized as one clean analytical cube.
Instead, they contain:

* event-level or record-level data,
* source-specific schemas,
* code-bearing fields,
* subgroup variables,
* support fields,
* repeated code slots,
* continuous measurements,
* and varying semantics across systems.

Examples include SINAN, SIH, SIM, and SINASC.

## 5.2 SIDRA

SIDRA is closer to a native aggregate system and already has OLAP-like structure around geography, time, variables, and classifications. In effect, it already behaves like a source of aggregate observables, whereas DATASUS often requires compilation from raw records. The official SIDRA Agregados API is explicitly organized around aggregates, localities, periods, variables, and classifications. ([arXiv][1])

## 5.3 Architectural implication

PegaSUS must therefore unify **two source regimes**:

* **native aggregates** (SIDRA-like),
* **raw event/registry sources** (DATASUS-like).

Both eventually become members of the same observable universe, but the ingestion and semantic compilation paths are different.

---

# 6. Canonical data model

The architecture begins **before** cubes or indicators.

Every source row is normalized into a canonical record.

## 6.1 Canonical record schema

A normalized record is conceptually:

[
R_n = (u_n,\rho_n,s_n,e_n,\kappa_n,g_n,v_n,a_n,w_n,q_n,\omega_n).
]

Where:

* (u_n): base support coordinates,
* (\rho_n): support role,
* (s_n): source identity,
* (e_n): carrier/event type,
* (\kappa_n): code-role map,
* (g_n): categorical subgroup attributes,
* (v_n): continuous or ordinal attributes,
* (a_n): annotation multisets,
* (w_n): weight or contribution,
* (q_n): quality/inclusion state,
* (\omega_n): provenance and semantic metadata.

## 6.2 Meaning of each field

### Base support (u_n)

Usually some combination of:

* municipality,
* state,
* date,
* month,
* year.

### Support role (\rho_n)

Examples:

* residence,
* occurrence,
* hospitalization occurrence,
* notification residence,
* death occurrence,
* birth occurrence.

### Carrier/event type (e_n)

Examples:

* notification,
* hospitalization,
* birth,
* death,
* anomaly annotation,
* procedure,
* person,
* household.

### Code-role map (\kappa_n)

This is one of the most important fields.

It is **not** just “the code.”
It is a typed mapping from source fields to code roles and code systems.

Examples:

* notification condition,
* diagnosis code,
* cause of death,
* anomaly code,
* procedure code.

### Subgroup attributes (g_n)

Examples:

* sex,
* age band,
* race/color,
* education,
* maternal age,
* trimester,
* parity class.

### Continuous/ordinal attributes (v_n)

Examples:

* birth weight,
* Apgar,
* gestational age,
* prenatal visits,
* hospital length of stay.

### Annotation multisets (a_n)

These are repeated or non-exclusive code slots and similar structures.

Examples:

* multiple anomaly code slots,
* associated causes of death,
* secondary diagnoses.

These cannot be naively treated as ordinary partitions.

---

# 7. Code-role ontology layer

This is one of the defining features of PegaSUS.

## 7.1 Why code roles matter

Disease and health-process discovery in DATASUS depends heavily on code-bearing fields.
The same disease concept may appear under different roles across sources:

* a SINAN notification condition,
* an SIH diagnosis,
* a SIM cause of death,
* a SINASC anomaly code.

So the system must treat **code role** as a first-class concept.

## 7.2 Code-role examples

* `condition`
* `diagnosis`
* `cause_of_death`
* `anomaly`
* `procedure`

## 7.3 Ontology structure

For each role (r), define an ontology:

[
\mathcal O_r = (V_r, E_r, \preceq_r)
]

where:

* (V_r): code nodes,
* (E_r): hierarchy edges,
* (\preceq_r): ancestor-descendant relation.

For ICD-10-like systems this usually means:

* chapter,
* block,
* 3-character code,
* 4-character code.

This is the “mini-hierarchy” needed for descending over disease codes.

## 7.4 Code query semantics

A disease hunt begins as a query over a code ontology, not as a hand-built workflow.

If (h) is a code node, then the query usually means “any descendant of (h).”

For single-valued fields:

[
\chi_r(R_n;h)=\mathbf 1{c_r(R_n)\in \downarrow h}
]

For repeated annotation fields:

[
\chi_r(R_n;h)=\mathbf 1{C_r(R_n)\cap \downarrow h \neq \varnothing}
]

This lets the system ask things like:

* all ICD A50–A53 events,
* all Q00–Q07 anomaly births,
* all records under a specific disease family,
* all descendants of a coarse code parent.

## 7.5 Code hierarchy is part of the search grammar

Code descent is not just data filtering.
It is a **hierarchical refinement move**.

The system may start at:

* a coarse disease family,
* or an ICD block,
  and only descend to:
* 3-character,
* or 4-character codes
  if the statistics justify doing so.

---

# 8. Observable families and observable instances

This is the correct replacement for the simplistic “everything is just a cube” view.

## 8.1 Observable family

An observable family is the governed space of possible views of one carrier/source/code configuration.

Conceptually:

[
\mathfrak F = (e,\rho,\mathcal K,\mathcal G,\mathcal V,\tau_0,\mathfrak R_s,\mathfrak R_c,\mathfrak R_g,\mathfrak R_v,\mathfrak R_m,\mathfrak R_\eta,\omega).
]

Where:

* (e): carrier/event type,
* (\rho): support role,
* (\mathcal K): admissible code roles and ontology domains,
* (\mathcal G): subgroup grammar,
* (\mathcal V): clinical-attribute grammar,
* (\tau_0): root type law,
* (\mathfrak R_s): support refinements,
* (\mathfrak R_c): code refinements,
* (\mathfrak R_g): subgroup refinements,
* (\mathfrak R_v): continuous-attribute refinements,
* (\mathfrak R_m): measure refinements,
* (\mathfrak R_\eta): representation refinements,
* (\omega): semantic registry.

## 8.2 Observable instance

An active numerical object is one materialized instance from a family:

[
X = (U,\rho,h,\Pi,\Theta,m,\eta,\tau,x,\mathcal Q,\omega).
]

Where:

* (U): active support,
* (\rho): support role,
* (h): active code query or code node,
* (\Pi): active categorical partition schema,
* (\Theta): active clinical threshold/state,
* (m): measure definition,
* (\eta): numerical representation,
* (\tau): type law,
* (x): numerical values,
* (\mathcal Q): uncertainty object,
* (\omega): lineage/provenance.

## 8.3 Why this matters

The global architecture is **tree-like / DAG-like**.
Each family has many possible refinements.
But each materialized instance is still cube-like and can be stored as an array/tensor/matrix for computation.

So globally the system is a forest of observable family DAGs; locally it still computes on cube-like numerical objects.

---

# 9. Compilation: from raw records to observables

Compilation is the process that transforms normalized rows into aggregated epidemiological objects.

## 9.1 Generic count compilation

A subset count observable is conceptually:

[
x(u,\pi,\theta)
===============

\sum_{n=1}^{N}
w_n
\mathbf 1{u_n=u}
\mathbf 1{\Pi(g_n)=\pi}
\mathbf 1{\Theta(v_n,a_n)=\theta}
\mathbf 1{\chi_r(R_n;h)=1}
\mathbf 1{e_n \in e}
\mathbf 1{q_n=1}.
]

This is the general compilation rule.

## 9.2 Continuous clinical attributes

Continuous variables should not all become huge partition axes.

Instead, they should be compiled through lawful templates such as:

* threshold counts,
* mean/variance summaries,
* quantile-based bins,
* clinically meaningful grouped strata.

For example:

[
x_{\le \tau}(u,\pi)
===================

\sum_n
w_n
\mathbf 1{u_n=u}
\mathbf 1{\Pi(g_n)=\pi}
\mathbf 1{V_n \le \tau}
\mathbf 1{\chi_r(R_n;h)=1}.
]

This is how fields like birth weight or Apgar become epidemiologically usable without exploding the state space.

## 9.3 Annotation compilation

Repeated code slots should often generate existential or multiset-based observables:

[
x_{\text{any}}(u,\pi;h)
=======================

\sum_n
w_n
\mathbf 1{u_n=u}
\mathbf 1{\Pi(g_n)=\pi}
\mathbf 1{C_r(R_n)\cap \downarrow h \neq \varnothing}.
]

This avoids the artifact of treating repeated code slots as exclusive categories.

One of the synthetic POCs showed exactly why this matters: naïve slot-summing can inflate apparent burden.

---

# 10. Type law

Each observable must carry a type law that governs what is legal.

## 10.1 Type dimensions

A useful type decomposition is:

[
\tau = (\gamma,\delta,\sigma,\mu)
]

with:

* (\gamma): extensive / intensive / compositional / contextual
* (\delta): flow / stock
* (\sigma): full / subset / annotation-derived
* (\mu): count / mean / ratio / index / continuous

## 10.2 Why this matters

This determines whether you can:

* sum an object,
* average it with weights,
* divide it by a denominator,
* standardize it,
* disaggregate it,
* or only use it as context.

Without this layer, the engine cannot distinguish lawful from unlawful transformations.

---

# 11. Support algebra

Support algebra defines how observables are moved across supports.

## 11.1 Extensive pushforward

For counts and other extensive quantities:

[
(f_*x)(u_c)=\sum_{f(u_f)=u_c}x(u_f)
]

This is ordinary aggregation.

## 11.2 Intensive aggregation

For rates:

[
(f_*^{,m}r)(u_c)=
\frac{\sum_{f(u_f)=u_c} m(u_f)r(u_f)}
{\sum_{f(u_f)=u_c} m(u_f)}
]

This is exposure-weighted roll-up.

## 11.3 Contextual clone

For coarse context:

[
(f^\dagger y)(u_f)=y(f(u_f))
]

This attaches a coarse value to a finer support without pretending it became fine-scale measurement.

## 11.4 Latent lift

For model-based disaggregation:

[
\hat z
======

\arg\max_{z}
\Bigl{
\ell(Y\mid Az)
--------------

## \lambda_1 \mathcal R_1(z)

\lambda_2 \mathcal R_2(z;E,G)
\Bigr}
]

This is the correct place to formalize coarse-to-fine inference.

A key lesson from the POCs is that latent lift must always carry uncertainty forward.

---

# 12. Code algebra

Code hierarchies deserve their own algebra.

## 12.1 Code roll-up

Parent codes aggregate child codes for extensive quantities.

## 12.2 Code descent

Parent-to-child descent is not automatic.
It is a refinement move accepted only when it improves the search objective.

## 12.3 Linked code search

The engine must support discovery not only within one code family but across linked code families and roles.

Examples:

* infection notifications linked to congenital anomaly codes,
* diagnosis families linked to mortality cause families,
* notification families linked to downstream birth outcomes.

---

# 13. Measure algebra

Raw counts are not enough.

## 13.1 Denominator library

Let:

[
\mathcal E = {E^{(1)},\dots,E^{(m)}}
]

be denominator/universe objects such as:

* total population,
* subgroup population,
* total births,
* subgroup births,
* all admissions,
* all notifications.

## 13.2 Lawful derived measures

[
\mathcal N(X)
=============

\left{
\psi(X,\phi^\dagger D):
\mathrm{Adm}_\psi(X,D,\phi)=1
\right}
]

This includes:

* incidence,
* intensity,
* subset proportions,
* shares,
* standardization,
* residualized burdens,
* threshold prevalences.

## 13.3 Shrinkage matters

The POCs strongly suggested that raw ratios are often unstable.

So rates and proportions should frequently use shrinkage:

[
\tilde p = \frac{A+\alpha}{B+\alpha+\beta}
]

or

[
\tilde \lambda = \frac{Y+\alpha}{E+\beta}
]

This stabilizes sparse branches and helps prevent false refinement.

---

# 14. Representation family

Each observable may have multiple lawful numerical representations.

Examples:

* raw count
* log-count with offset
* shrunk rate
* log-rate
* logit of shrunk proportion
* standardized rate
* residualized burden
* compositional transform
* contextual standardized field

This is important because different kinds of observables do not live naturally in the same scan geometry.

One of the strongest POC lessons was that **typed representations are necessary** if the scanner is to see real structure rather than simple size effects.

---

# 15. Uncertainty model

Every observable instance carries an uncertainty object:

[
\mathcal Q = (\text{sampling law},\text{sparsity burden},\text{lift uncertainty},\text{quality flags},\text{stability metadata})
]

## 15.1 Sources of uncertainty

* low event counts,
* small denominators,
* underreporting,
* support mismatch,
* model-based disaggregation,
* code ambiguity,
* missingness,
* suppression,
* poor semantic resolution.

## 15.2 Why it matters

Uncertainty affects:

* edge weights,
* refinement acceptance,
* whether child nodes are trusted,
* whether latent lifts are downweighted,
* and whether fine code descent is statistically defensible.

The synthetic refinement POCs strongly supported uncertainty-aware penalties.

---

# 16. The main scan lattice

The main operational support is usually:

[
U^\star = \text{municipality} \times \text{year}
]

Sometimes municipality × month may be used upstream and rolled to year.

This does **not** mean all sources naturally live on that support.
It means that the active frontier is aligned to a common scan lattice through lawful support operators.

Support role remains part of the identity of each observable even after alignment.

---

# 17. The active frontier

The computational state of PegaSUS is not the whole latent state space.
It is the current **active frontier**:

[
A = {X_1,\dots,X_M}
]

Each (X_i) is one active observable instance from one family.

The frontier may include, simultaneously:

* notification burden families,
* admission families,
* mortality families,
* birth outcome families,
* anomaly families,
* contextual socioeconomic variables,
* latent-lifted contextual variables,
* multiple code branches,
* multiple subgroup branches,
* multiple measure representations.

This frontier is the true computational object of the search engine.

---

# 18. Statistical scanner

The scanner is the project’s hardest unresolved part, but the architecture now has a clear direction.

## 18.1 What the scanner must do

Given the frontier, the scanner must identify:

* pairwise candidate links,
* cross-source dependence,
* lagged relations,
* spatially localized structure,
* code-family links,
* and higher-order motifs or subgraphs.

## 18.2 What the scanner must avoid

It must avoid being dominated by:

* common-size effects,
* broad contextual confounding,
* duplicated signal across related observables,
* support-role artifacts,
* multiple-comparison inflation,
* and sparse-branch noise.

## 18.3 The current best theoretical direction

The best literature-backed direction is **not** “strip factors, then estimate a graph.”

The better direction is a **joint sparse + low-rank graph model**, where:

* the sparse part captures conditional dependence among observables,
* the low-rank part captures broad latent confounders,
* and the model is estimated jointly. Chandrasekaran, Parrilo, and Willsky give the canonical sparse-plus-low-rank latent-variable graph formulation. LTGL extends that idea to time-varying networks, and recent work also addresses latent effects together with correlated replicates. ([Project Euclid][2])

## 18.4 Why mixed-type graph modeling is needed

The frontier will mix:

* rates,
* proportions,
* counts or count-derived transforms,
* thresholded clinical variables,
* continuous context variables.

So a plain Gaussian graph is mathematically inadequate. The correct literature-backed direction is to use either a **mixed graphical model** when node types are known, or a **semiparametric exponential-family graphical model** when node types are heterogeneous or partially uncertain. Lee and Hastie develop mixed graphical models for continuous and discrete nodes; Chen, Witten, and Shojaie generalize this to different exponential-family conditionals; Yang, Ning, and Liu provide a semiparametric exponential-family graph model with edge testing that avoids fully specifying each node’s base measure. ([Hastie][3])

## 18.5 Dynamic count structure

Simple lagged correlations are too weak for the final engine.
For count-valued streams, the literature-backed direction is **count autoregression** and **time-varying count dynamics**, such as PARX, TVBINGARCH, and TV-PARX models, plus the broader multivariate count time-series literature reviewed by Fokianos. ([Pure][4])

## 18.6 Localized spatial anomaly detection

Not every discovery question is a graph question.
Sometimes the right question is: where is the connected hotspot?

For that, PegaSUS should include a separate **localized scan layer**, using multivariate scan statistics or graph scan statistics rather than forcing the graph layer to do everything. Kulldorff’s multivariate scan statistic, Neill and Lingwall’s NPSS, and graph-based scan approaches such as the Graph Fourier Scan Statistic are the right references here. ([Wiley Online Library][5])

---

# 19. Hierarchical refinement grammar

This is the mechanism that replaces full explicit tabulation.

## 19.1 Refinement axes

Each family has a refinement grammar over:

* support,
* code hierarchy,
* subgroup partitions,
* continuous clinical thresholds/strata,
* measure representation,
* temporal operator / lag structure.

Formally:

[
\mathfrak R
===========

\mathfrak R_s \square
\mathfrak R_c \square
\mathfrak R_g \square
\mathfrak R_v \square
\mathfrak R_m \square
\mathfrak R_\eta
]

## 19.2 Examples of refinement

### Code refinement

* ICD chapter → block → 3-char → 4-char
* coarse disease family → source-specific subtype

### Subgroup refinement

* all sexes → sex
* all ages → age bands
* broad maternal age → finer maternal age
* no education split → education split

### Clinical refinement

* all births → low birth weight
* all births → Apgar < 7
* raw anomaly family → CNS anomalies → microcephaly

### Representation refinement

* raw burden → rate
* crude rate → shrunk rate
* broad code family → leaf code-specific burden
* contemporaneous → lag-1 / lag-2 / accumulated exposure

---

# 20. ICD and code-hierarchy descent

The project explicitly needs a mini-hierarchy over ICD-like systems.

## 20.1 Why

Because many signals only appear:

* at a finer code level,
* or only at a coarser grouped level.

Fine descent also massively increases the multiplicity burden.
So descent cannot be done ad hoc.

## 20.2 Statistically principled descent

The best literature-backed direction is to combine:

* **hierarchical FDR control** for testing over trees,
* **TreeBH**-style multi-resolution error control,
* and optionally **tree-guided shrinkage / aggregation** so that effects can stop at an intermediate code level instead of always being forced to leaves. Yekutieli’s hierarchical FDR framework, TreeBH, and tree-guided group lasso/aggregation are the key references here. ([Matemática TAU][6])

## 20.3 Practical implication for PegaSUS

PegaSUS should not simply split every code parent into every child.
It should:

1. test coarse code nodes,
2. descend only for selected parents,
3. stabilize child estimates,
4. and stop descent when finer resolution adds instability rather than value.

---

# 21. Frontier search objective

The hierarchy needs an explicit objective, not just “go deeper if interesting.”

A conceptual search objective is:

[
J(A)
====

\operatorname{Stab}(\hat G_A)
+
\eta,\operatorname{Loc}(A)
+
\chi,\operatorname{CodeSpec}(A)
+
\zeta,\operatorname{Interp}(A)
+
\xi,\operatorname{Path}(A)
--------------------------

## \alpha,\operatorname{Comp}(A)

## \beta,\operatorname{Unc}(A)

\delta,\operatorname{Mult}(A).
]

Meaning:

* reward stability,
* reward localization,
* reward code specificity when justified,
* reward interpretability,
* reward coherent pathway motifs,
* penalize computational complexity,
* penalize uncertainty,
* penalize multiple-testing burden.

A child refinement is accepted only if it improves this objective.

---

# 22. What the synthetic POCs established

The proof-of-concept sequence gave several important lessons.

## 22.1 What survived

### A. Typed measures are necessary

Raw counts tend to rediscover size effects.
Rate/proportion constructions and typed transforms are essential.

### B. Annotation vs partition distinction is necessary

Repeated code slots cannot be treated naively as ordinary partitions.

### C. Support role matters materially

Residence vs occurrence can substantially change patterns, especially for hospitalizations and deaths.

### D. Contextual cloning and latent lift must remain distinct

A coarse variable copied to a fine lattice is not the same thing as a statistically disaggregated estimate.

### E. Sparse-denominator refinement needs penalties

Naïve refinement chases noisy small children.

### F. Simultaneous multi-source compilation is feasible

The synthetic syphilis + Zika environment showed that the front half of the architecture — source normalization, code-role handling, observable compilation, and support alignment — can survive a much more realistic mixed-source scenario.

## 22.2 What remains weakest

The **global scanner / graph engine** is still the bottleneck.

In the hard synthetic multi-source test, the modeling and compilation layers survived much better than the discovery engine itself.
That means the conceptual architecture is sounder than the current numerical scanner.

---

# 23. Literature-backed recommendations integrated into PegaSUS

This is the most important literature-to-architecture mapping.

## 23.1 Support misalignment and count-valued latent fields

For coarse-to-fine support alignment, count-valued survey/change-of-support, and multivariate spatiotemporal areal count modeling, the best references are Bradley, Wikle, and Holan on Bayesian change-of-support for count data and their multivariate spatiotemporal mixed-effects/count models. These papers support a latent Poisson/NB observational layer with explicit support operators. ([arXiv][1])

## 23.2 Small-area stabilization

For sparse municipality-level risk estimation, BYM2 remains one of the most useful building blocks because it stabilizes structured and unstructured spatial effects in an interpretable way. ([arXiv][7])

## 23.3 Mixed-type graph modeling

For the graph layer over mixed node types, the best guidance is:

* Lee & Hastie for mixed graphical models,
* Chen–Witten–Shojaie for exponential-family mixed graphical models,
* Yang–Ning–Liu for semiparametric exponential-family graphical models with edge testing. ([Hastie][3])

## 23.4 Latent confounding and dynamic graph structure

For broad shared confounding, the right move is sparse + low-rank graph estimation rather than ad hoc factor removal. Chandrasekaran et al. provide the canonical sparse-plus-low-rank formulation; LTGL extends the idea to time-varying networks; recent work on correlated replicates and unmeasured confounders is especially relevant for repeated municipality-year panels. ([Project Euclid][2])

## 23.5 Count time-series dynamics

For lagged disease processes, count-autoregressive and time-varying Poisson models are the correct mathematical substrate, including PARX, TVBINGARCH, TV-PARX, and the broader multivariate count time-series literature. ([Pure][4])

## 23.6 ICD-tree descent and multi-resolution selection

For code-hierarchy descent, the correct inferential tools are hierarchical FDR / TreeBH, possibly paired with tree-guided penalties so the model can stop at intermediate code levels when the data do not justify finer descent. ([Matemática TAU][6])

## 23.7 Localized hotspot discovery

For connected anomalous regions or outbreak-like clusters, PegaSUS should include multivariate scan statistics or graph scan statistics as a module separate from the main graph layer. ([Wiley Online Library][5])

---

# 24. What PegaSUS is expected to do

PegaSUS is expected to:

* organize DATASUS and SIDRA into one canonical search framework,
* let the user or system define disease families through code ontology queries,
* compile many observable families from raw rows and native aggregates,
* align them onto a common support,
* compare them in a type-aware, uncertainty-aware way,
* discover candidate cross-source spatiotemporal links,
* descend over ICD and subgroup branches,
* and return not just edges but interpretable refined motifs and subgraphs.

Examples of intended discoveries include:

* infectious notifications linked to later birth outcomes,
* disease burden co-concentrating with deprivation/metropolitan phenotypes,
* maternal-condition notifications linked to neonatal or congenital outcomes,
* code-family-specific mortality and hospitalization echoes,
* disease clusters with spatial coherence.

---

# 25. What PegaSUS is not expected to do

PegaSUS is **not** expected to:

* recover every true epidemiological link automatically,
* eliminate ecological fallacy,
* replace domain review,
* infer causality by default,
* or treat all support roles as interchangeable.

It is a **discovery engine** for disciplined statistical hypotheses and patterns, not a fully automatic scientific oracle.

---

# 26. Initial implementation model

## 26.1 First implementation goal

The first phase should **not** attempt the full graph engine.
It should focus on building the source and compilation architecture correctly.

## 26.2 Recommended first modules

### 1. Source catalog

A machine-readable registry of every source family:

* source name,
* system,
* file pattern,
* years,
* support fields,
* likely support roles,
* code-bearing fields,
* subgroup fields,
* continuous fields,
* annotation/repeated-slot fields.

### 2. Fetch/downloader

A robust ingestion layer that:

* locates files,
* downloads them,
* records provenance,
* versions fetches,
* stores raw files in a reproducible layout.

### 3. Parser/normalizer

A source-specific loader that:

* parses raw files,
* standardizes encodings,
* standardizes columns,
* harmonizes date/municipality fields,
* exposes source metadata.

### 4. Canonical record mapper

The first core architectural module.

It maps raw source columns into the canonical schema:

* support,
* support role,
* event type,
* code roles,
* subgroup fields,
* continuous fields,
* annotations,
* quality flags.

### 5. Code registry

A registry for:

* code roles,
* code systems,
* ICD hierarchy,
* source-specific condition hierarchies,
* descendant closure queries.

### 6. Support registry

A registry for:

* municipality resolution,
* time aggregation rules,
* support-role semantics,
* lawful aggregation/alignment operators.

### 7. Observable compiler

The first generic query engine:

* compile counts,
* compile code-query counts,
* compile subgroup counts,
* compile threshold counts,
* compile simple denominator-based rates.

Only after these modules exist should the full scanner be attempted.

---

# 27. Suggested development phases

## Phase 1 — Data organization

Build:

* source catalog,
* downloader,
* parser,
* canonical schema,
* code registry,
* support registry.

## Phase 2 — Observable compilation

Build:

* code-query compilation,
* subgroup compilation,
* threshold compilation,
* denominator-aware rates,
* lineage tracking.

## Phase 3 — Frontier materialization

Build:

* observable family definitions,
* instance materialization,
* refinement grammar,
* uncertainty bookkeeping.

## Phase 4 — Baseline scanner

Build:

* simple mixed-type graph baseline,
* temporal operator hooks,
* spatial neighborhood layer,
* stability selection.

## Phase 5 — Advanced scanner

Replace the baseline graph with:

* mixed exponential-family graph substrate,
* sparse + low-rank latent graph estimation,
* count-time dynamic refinement,
* scan-statistic submodule,
* hierarchical code descent with structured error control.

---

# 28. Open problems

Even after the current theoretical development, several hard problems remain open.

## 28.1 Final graph engine

This is still the main unresolved technical core.

The architecture now knows what kind of graph engine it needs, but the exact scalable implementation for:

* mixed data types,
* latent confounding,
* repeated municipality-year structure,
* many observable blocks,
* temporal evolution,

is still the hardest part.

## 28.2 Full code-tree descent policy

The statistical descent policy over large ICD or source-specific code trees still needs concrete implementation choices:

* testing strategy,
* aggregation penalties,
* stopping criteria,
* stability under sparse leaves.

## 28.3 Integration of localized spatial scan and graph discovery

The final engine may need both:

* graph/pathway discovery,
* and explicit connected-region hotspot detection.

The interaction between those layers still needs design work.

## 28.4 High-dimensional continuous clinical grammars

Birth weight, Apgar, gestational age, hospital stay, and similar variables need disciplined refinement grammars so that the engine can explore them without exploding.

---

# 29. Final definition

PegaSUS is best understood as follows:

> **PegaSUS is a disease-agnostic, code-centric, support-aware, uncertainty-aware hierarchical epidemiological search engine. It begins by normalizing heterogeneous public-health and socioeconomic sources into canonical records with explicit support roles and code roles. It organizes disease and health-process search through code ontologies rather than disease-specific workflows. It defines observable families with lawful support, code, subgroup, clinical, measure, and representation refinements, and materializes only a controlled frontier of observable instances rather than one giant flat table. It compiles those instances onto a common analysis lattice, usually municipality × year, propagates uncertainty explicitly, scans the active frontier for stable cross-source spatiotemporal structure, and descends only where code specificity, subgroup localization, temporal structure, and interpretability improve under controlled complexity and uncertainty.**

---

# 30. Short operational summary

If reduced to a practical sentence for implementation:

**PegaSUS will organize DATASUS and SIDRA into a canonical record system, compile code-aware epidemiological observables from them, and progressively search those observables for stable spatial, temporal, and cross-source structure without ever needing to materialize the full latent mega-table.**

[1]: https://arxiv.org/abs/1405.7227?utm_source=chatgpt.com "Bayesian Spatial Change of Support for Count-Valued Survey Data"
[2]: https://projecteuclid.org/journals/annals-of-statistics/volume-40/issue-4/Latent-variable-graphical-model-selection-via-convex-optimization/10.1214/11-AOS949.pdf?utm_source=chatgpt.com "latent variable graphical model selection via"
[3]: https://hastie.su.domains/Papers/structmgm_jcgs_rev2_2-15-2014.pdf?utm_source=chatgpt.com "Learning the Structure of Mixed Graphical Models"
[4]: https://pure.au.dk/ws/files/85025114/rp15_11.pdf?utm_source=chatgpt.com "Poisson autoregressions with exogenous covariates (PARX)"
[5]: https://onlinelibrary.wiley.com/doi/10.1002/sim.2818?utm_source=chatgpt.com "Multivariate scan statistics for disease surveillance - Kulldorff"
[6]: https://www.math.tau.ac.il/~yekutiel/papers/JASA%20FDR%20trees.pdf?utm_source=chatgpt.com "Hierarchical False Discovery Rate–Controlling Methodology"
[7]: https://arxiv.org/abs/1601.01180?utm_source=chatgpt.com "An intuitive Bayesian spatial model for disease mapping ..."
