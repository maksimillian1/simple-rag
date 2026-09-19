<!--
Vendored from report-kit — do not edit here.
Source: src/report_kit/templates/methodology.md
Version: v0.2 — the tag pinned in requirements.txt, so the cited section numbers and the
checker that enforces them name the same release. The body is byte-identical to that tag's template.
Vendored: 2026-09-22
Edit upstream and re-copy. The report cites section numbers, and an upstream edit renumbers them.
-->

# Methodology

Why the structure is shaped this way. Read once; the templates encode the rest.
Basic filling logic is in `README.md`.

---

## 1. One report, one question

A report is defined by the decision it supports, not by the ground it covers. One subject,
one document, however many executions it took to measure.

The failure mode is splitting it by measurement campaign — "Part 1: ingestion", "Part 2:
queries". Each half then answers half a question, neither is publishable alone, and the
second half never ships. Areas not yet measured belong in the coverage register (§11), not
in a separate document.

**The section list is fixed by the template; what varies is which sections have material.**
A report with three of eight sections filled is a complete report with declared coverage —
not a draft.

| | Report | Article or talk |
| :--- | :--- | :--- |
| Boundary | the whole subject, coverage stated | one finding, told well |
| Audience | decision makers, and the author in a year | the public |
| Lifetime | revisions | once |

The article does not have to cover the whole report, and nobody notices that it did not.
Confusing the two is what turns a finished measurement into an unpublished one.

---

## 2. Given versus measured

The single test that decides where anything lives:

> **Is it under test?**

Not "is it shared", not "is it technical". A model version, a frozen parameter, an instance
type, a rate card, an input fixture — all givens. The moment one becomes an axis it leaves
the givens and becomes an execution's input; the winner returns as a given next revision.

**A given never lives in a Plan.** Changing one is preparation — a new freeze commit and a
journal note — not a run. In the full profile givens sit in `00-baseline` §2; in the minimal
profile they get their own section, frozen before the Plan is written.

### The metric register

Every metric is defined **exactly once**, in the execution that uses it, and carries a ref.
Definitions neither inherit nor get copied: a ref is cited from anywhere by path. What is
global is the ref namespace, not a second definition.

The **values** those refs produce are a separate concern and are not governed by this rule. A
report whose executions share a floor, a rate or a denominator needs one place where each
number is resolved and checked, and `formats.md` defines it. Keeping definitions local and
values central is deliberate: a definition that moves invalidates measurements already taken,
while a value is expected to be revised as data is re-read.

| Ref | Class | Mark on the figure | What `Source` holds |
| :--- | :--- | :--- | :--- |
| `M⟨n⟩` | Measured | *(unmarked)* | the exposed metric name and its selector |
| `D⟨n⟩` | Derived | ᴰ | the formula, written over other refs |
| `R⟨n⟩` | Recorded | ᴿ | the moment it was written down, and by whom |
| `E⟨n⟩` | Estimated | ᴱ | the basis, and the reference value it is judged against |

The letter is the class, so the register needs no provenance column and a row copied into
the report needs no lookup. Numbering is a single sequence per execution — `M1, M2, D3, R4` —
never one counter per letter, so a mistyped letter fails to resolve instead of quietly
naming a second live metric. **A number is never reused**, including by a dropped ref: raw
data files and published revisions already point at it.

Inside its own execution the bare ref is enough. From outside, cite the path:
`00-baseline/M2`, `01-frontier/D6`.

Three rules follow, and they are the whole of the register's discipline:

1. **Name confirmation is the gate.** A target can be up while the string in the table was
   copied from chart documentation — the query then returns nothing on a healthy endpoint,
   and the failure reads as a missing scrape. An `M` ref carries the date its name was
   checked against the live endpoint; until it does, its status is `unconfirmed` and it
   cannot appear in a Plan. Scrape health is transient and belongs to preflight, not here.
2. **Refs are lettered, runs are numbered.** `M4` is a metric; `#04` is a run. One
   identifier never means both.
3. **The register holds no explanations.** Why a series lies, which exporter flag its label
   dimensions depend on, what changed between minor versions — those are mechanisms of the
   system and live in `concepts.md` as `K⟨n⟩`, cited from the register's Notes cell. A
   register that explains itself stops being scannable, which is the only thing it is for.

Two executions may read the same exposed name under different selectors. That is two refs,
not a conflict — each is defined where it is used. The later row names the earlier one in
Notes, so a reader comparing the two figures sees at once that they are not the same number.

### The value registry

The register says what a number *means*. `figures.yaml`, at the report root, holds what it
currently *is* — one file per report, whatever the executions. A figure is either a leaf, a
value with a source, or a formula over other figures. The letters are the register's own,
prefixed so the two namespaces never collide: `FM` measured · `FR` recorded · `FD` derived ·
`FE` estimated.

Four habits are what make it worth having. Without them it is a second place to be wrong:

1. **Register before writing the sentence.** A number worked out while writing is one nothing
   can check afterwards. Arithmetic belongs in a formula; prose prints its result.
2. **Append, never insert.** Refs are assigned by a tool, which is what makes reclassifying a
   figure free. Deleting one is not free: every later ref of that letter shifts down, while
   the marks already written into documents keep naming the old numbers.
3. **Retire a superseded value rather than deleting it.** The old digits stay listed beside
   what replaced them, so a scan still finds them wherever they survived — a sentence, a
   table, or a run-data file nobody thought to revisit.
4. **Declare where a figure has to appear.** Then a check reports that a headline went missing
   during a rewrite, instead of leaving it to whoever reads the draft last.

All of it exists to make one question mechanical: *does the number on the page still equal the
number the registry resolves?* `formats.md` is what makes that question askable — how a ref
attaches to the digits, which shapes a scan ignores on purpose, and the three states a number
can be in. A number outside the contract is not an error; a number that looks checked and is
not is the failure worth engineering against.

---

## 3. An execution is the unit of work, not of publication

Where a result lands is decided at Close, against the finished report:

| Destination | When |
| :--- | :--- |
| the whole report | it is the only execution |
| a report section, table inline | significant, and it fits |
| a benchmark, cited from a section | too detailed for the report, or needed as the regression unit |
| the givens | it is a constant with two or more consumers |
| **nothing** | measured, and insignificant against the rest — or the hypothesis did not hold |

**"Insignificant" is a finding.** A module worth a few percent of cost has earned its way
*out* of an executive report, and the run is what proved it. The record stays in the
execution; the coverage register carries the result so the question is not re-asked next
revision.

**Every execution that ran is named in the report header**, `abandoned` ones included. An
execution that disappears takes with it the evidence that the question was ever asked.

---

## 4. Start minimal, promote on the second consumer

One function, one run, one report is the default shape. Everything else appears when a
second consumer forces it:

| File | Created when |
| :--- | :--- |
| `executions/00-baseline/` | a second execution would copy the system description |
| `executions/NN-⟨name⟩/` | a second execution exists — then numbering |
| `concepts.md` · `metrics.md` | the block outgrows one screen inside `index.md` |
| `assets/` | the first rendered chart exists |

Why shared material cannot simply live in the first benchmark: the second one starts
depending on it, and you cannot add the second without editing something already frozen.
That property — **adding an execution rewrites nothing** — is what the layout protects.

**The single exception is the minimal→full migration.** It happens once, before the second
execution runs, and it is the price of starting minimal. Paying it is still cheaper than
building the full tree for a report that turns out to need one run.

---

## 5. What makes a figure credible

Five properties. A figure missing any of them will be questioned, and the question will be
correct.

**A denominator.** Total spend supports no decision; cost per unit supports several. Choose
the unit once, state the exact moment it counts as done, and never change it.

On a batch path the denominator is frozen with the fixture; on a serving path it is produced
by each run. Both are denominators — what must not vary is the definition of the unit.

> **One denominator per cost curve, not per report.** A second unit appears only for a
> physically different path — ingestion priced per document, queries per query. Then each
> unit gets its own contract block and its own tables, and no table, chart or headline row
> mixes them. A conversion between the two is never published: it depends on an arrival
> ratio nobody measured. Two denominators over the *same* path is the actual failure.

**A reference value.** An absolute number decides nothing. Every headline figure carries
something it is compared against — a target, an alternative, a previous revision.

**A boundary.** The conditions under which it holds, stated forward-looking, before anyone
asks. A reader who cannot falsify a number does not trust any number.

**A provenance mark.** Measured is unmarked so the exceptions are visible at a glance: ᴰ
derived, ᴿ recorded, ᴱ estimated. The mark sits on the figure rather than in a column, so a
row copied into the report carries it. In the register the class is already the ref's first
letter (§2); the mark carries it to a reader who will never open a register — which is why
the report states the legend once, in its header, and nowhere else.

**A resolvable value.** The mark says where a number came from; it does not say the number is
still right. A figure printed in more than one place drifts the moment one of them is revised,
and nothing about a correct-looking table reveals it. So a figure also carries a ref into the
report's one registry of values, and what is printed is checked against the registry rather than
assumed equal to it. `formats.md` defines the ref, how it attaches to the digits, and which
numbers sit outside the contract on purpose. The discipline underneath it is that **a sentence
never computes**: a number worked out while writing is one nothing can check, which is why
arithmetic lives in the registry and prose only prints its results.

**A path to the raw data.** Report → section or benchmark → file under an execution's
`data/`. Always resolvable. A rendered chart names the data file it came from; both are
committed.

---

## 6. Recorded before, not after

Some things cannot be reconstructed once the moment passes. They are the only genuinely
urgent items in any project.

| Class | Why it is unrecoverable |
| :--- | :--- |
| Dated price snapshot | rates change; an undated basis makes every derived figure unverifiable |
| Input profile and exact count | the input can be overwritten and cannot be re-derived from the report |
| Run windows | the backend does not know when a run began; a window guessed later is a different run |
| Saturation judgement | no query returns "component X was the bottleneck" |
| Hypothesis | written afterwards it is worthless, and everyone can tell |
| Attribution setup | usually forward-only, and often delayed by hours |

**The hypothesis rule is the one people skip.** Record what you expect, dated, before the
first run — which is why a Plan is frozen and not edited. This applies to the baseline too:
a floor capture has an expectation, and it is the one most often wrong. If the result inverts
it, the inversion stays in the report. An unrecorded hypothesis lets you rationalise any
outcome, and readers assume you did.

### The run ledger

One row per run, not per point. `#` is the execution sequence — monotonic, never reused, so
a re-run of a point is a new row rather than an edit to the old one. `Point` is the axis
identity, and the same string names the file under `data/` and the row in the results matrix.
Rows sit in the order the runs happened, which under coarse-to-fine is not the order of the
axis.

**A row is completed when its run ends, not at Close.** Two of its columns hold things this
section calls unrecoverable. `Signal` is the saturation judgement — what the instruments
showed while the run was live: the component sitting at its ceiling, or headroom. Nothing
queried afterwards returns it, and the results matrix asks for it at Close, by which point it
can only be inferred. `Exported` is bounded by telemetry retention, not by the end of the
execution: a sweep that spans more days than the retention window loses its early runs while
the later ones are still going, so batching export to Close is a checklist item that cannot
be honestly ticked.

The row is therefore the per-run discipline, and it needs no separate checklist: a blank cell
among filled ones is visible, which is what a table is for. Prose is written only where a run
has something to say; a clean run needs no paragraph.

A closing checklist covers the opposite case — what fails **silently**. An unresolved
saturation judgement, an unmarked figure, an expectation never compared: none of these leaves
a hole anyone would notice. Anything already carried by a field or a column stays out of the
checklist, or the two definitions drift and the checklist becomes the one that lies. For the
same reason an execution has no opening checklist: its preparation is fields — `Expected`,
`Plan frozen`, the register's confirmation status — and a field filled after the fact is not
forgetfulness but a forgery. A baseline does have one, because its preflight produces files
and external state that no field in the document would reveal as missing.

### What the tooling holds, and what it does not

Two of the unrecoverable classes are mechanical enough to be enforced rather than remembered,
and the runner enforces them. A window comes from the process that applied the load, so it is
observed rather than reconstructed from memory. Export happens at each point's close rather
than being batched toward the end, and a series that came back empty exits non-zero — which
makes a retention gap loud on the day it happens, when the window can still be re-exported,
instead of at Close, when it cannot.

A third is recorded rather than enforced: each point carries the `kit_version` that
produced it, because the measurement tooling is a dependency with a life of its own and
nothing else in the record would say which code produced the numbers.

`Signal` is deliberately not among them. What the instruments showed is a judgement, not a
reading, and a tool that inferred it would produce a confident sentence nobody checked. The
runner records only what the judgement is made from — the peak, whether a configured ceiling
was touched, which tier never left its floor — and stops there. The column belongs to the
author and is filled while the run is live. A blank cell is visible; an inferred one is not.

---

## 7. Sweep coarse to fine

When the finding is a curve, do not sweep linearly. Take the two ends of the range and one
point between them first, then place the rest by the shape those three produce.

| What three points show | What it means |
| :--- | :--- |
| minimum in the middle | refine on both sides |
| minimum on a range boundary | **not proven** — no descending branch on one side |
| still falling at the top | **the range was wrong** — extend it |

A linear sweep spends its whole budget before revealing the last row. Coarse-to-fine reveals
it on the third run, and reads as a refinement pass rather than a mistake.

---

## 8. Constraint ladders

A ladder is the order in which ceilings are hit. A tier counts as proven only when the
previous one was **actually relieved** and a new saturation was then observed — never
because its numbers looked close.

Sweeping the main axis relieves tiers on its own: if component A is the ceiling at low
concurrency, at high concurrency there is more of A and that ceiling is gone. Whatever
saturates instead is a genuinely proven second tier.

**Never claim a tier beyond what was observed.** An unproven tier weakens the tiers that
were proven, and a reader who catches one speculative claim discounts the rest. An unproven
tier is a coverage row, not a paragraph — which is why the templates carry one tier block
and you add the second only after it exists.

---

## 9. Cost has exactly two terms

```
Cost = Floor + ( Marginal_per_unit × Volume )
```

**The floor is measured with the system idle**, and split three ways rather than totalled:

| Block | What it is | Disappears if the subject is deleted |
| :--- | :--- | :--- |
| **A · Shared** | platform lines the subject consumes but does not cause | no |
| **B · Dedicated** | lines that exist only because this subject does — **the headline** | yes |
| **C · Total** | `A + B`, the whole idle bill | — |

B is the number quoted first. A alone inflates it into a platform bill. Dividing A by an
assumed number of co-tenant features is refused: the divisor is invented, and a headline
built on an invented divisor is not defensible against anyone who picks a different one. A
"cost standing alone" figure has the same defect and is not what C means. C is arithmetic
over A and B and therefore carries no line of its own and no fixed/variable attribute.

**The marginal cost excludes every floor line by definition.** Mixing them inflates the
coefficient and silently corrupts any build comparison downstream.

**Amortization is arithmetic, not a run.** The volume at which floor share drops below half
is the lower bound of where the design makes economic sense.

**A build comparison needs the realistic alternative**, not the dramatic one. If the platform
exists regardless, the alternative is a different mode on the same platform.

---

## 10. Guardrails, not recommendations

A recommendation is prose and gets forgotten. A guardrail is a config value, sourced from a
number in the report, that can be committed to a file.

The test: **if it cannot be committed, it does not belong in the table.** Rows whose source
number does not survive the runs are deleted, not left blank.

---

## 11. Declared scope beats silent omission

Every report has boundaries. Stating them is what separates an engineering document from a
student one.

**Scope has exactly one register: the Coverage table.** Measured, derived, declared-not-
measured and out-of-scope are statuses in that one table, not separate sections. A closing
"future work" list is the failure mode: it duplicates the register, drifts out of sync, and
reads as apology rather than as scope. A measurement blind spot is a row here too — an area
the instrumentation could not reach is an area not covered, whatever the reason.

Write the rows **before** measuring and let the statuses resolve at Close. A row reading
*declared, not measured* is what lets a report ship at partial coverage without pretending
to be complete — and what stops the subject from being split into two documents that each
answer half a question. An execution that ran and proved insignificant is a row here too,
with its finding: "measured, contributed under n % of cost, omitted" is a result, and it
stops the question being asked again next revision.

Each row names what the omission would have supported. A reader who sees a deliberate
boundary trusts the inside of it; a reader who discovers an accidental one trusts nothing.

---

## 12. Revisions, not parts

A report is reissued, not extended. Each revision carries `Supersedes` and a one-line
`Changes` summary — the two lines a returning reader actually reads.

**Executions are immutable once closed.** A re-run under changed conditions is a new numbered
execution, never an edit to the old one — the old numbers are what the regression is computed
against, and editing them deletes the comparison. Only the baseline is re-captured in place,
and then as a new revision with its own `Supersedes`.

From the second revision onward, regression against the previous one is usually the strongest
section available. It cannot exist at all in a structure split into parts, because parts are
never compared to each other.

---

## 13. Where a sentence lives

The kit's own failure mode is instruction leaking into the deliverable. One test:

> **Who is this sentence addressed to?**

| Addressed to | Example | Lives in |
| :--- | :--- | :--- |
| the **reader** of the report | how to read a mark, what a status means | `report.md` |
| the **author** filling a template | "write the rows before measuring", "one row per run, not per point" | `methodology.md` |
| an engineer new to the **system** | why a series lies, what an exporter flag changes | `concepts.md` as `K⟨n⟩` |

The report must read as a standalone document. Guidance to the person filling it in is not
part of the argument, and a decision maker who encounters it stops reading the argument and
starts reading the process.

**The templates therefore carry no guidance at all** — not as prose, not as commented-out
prose. A working file holds headings, tables and `⟨angle-bracket⟩` placeholders. Instructions
kept inside the artifact get copied forward, edited into half-truths, and eventually
contradict this file; instructions kept here are read once and stay correct. The rendered
page and the source say the same thing, which is the point.

The legend is the one thing that looks like a note and is not. It tells a reader how to
interpret a number in front of them — the same role as a key on a map. It appears once, in
the report header, in one line.
