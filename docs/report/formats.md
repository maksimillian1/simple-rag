<!--
Vendored from report-kit — do not edit here.
Source: src/report_kit/templates/formats.md
Version: v0.2 — the tag pinned in requirements.txt, so the text and the checker that
enforces it name the same release. The body is byte-identical to that tag's template.
Vendored: 2026-09-22
Edit upstream and re-copy. The report cites section numbers, and an upstream edit renumbers them.
-->

# Number formats

How numbers are written so that a script can verify them. Companion to `methodology.md` §2:
definitions live in each execution's register, values live in one `figures.yaml` per report.

## Rule 0 — no arithmetic in prose

A sentence never computes. "$19,460 extra per 1M docs" is not a subtraction performed while
writing; it is a figure, resolved from the registry. This rule is what makes the rest
enforceable: a computed number that is not a figure cannot be verified by any convention,
because nothing knows what it should be.

## Three states, not two

| State | How | What it guarantees |
| :--- | :--- | :--- |
| **Verified** | carries a ref | the number here equals the registry's current value |
| **Excluded** | matches a declared shape below | nothing — it only keeps the scan quiet |
| **Uncovered** | everything else | nothing; not an error, just outside the contract |

The value of the system is proportional to how much is marked, not to how complete the
exclusion table is. Exclusions remove noise with a distinctive shape; they cannot certify that
what remains is harmless, because a number's shape never tells you its role — the same `2` is a
replica count, a multiplier inside a formula, a zone count or a figure.

## The ref

Four letters carry the same classes the metric register uses, prefixed so the two namespaces
never collide: `FM` measured · `FR` recorded · `FD` derived · `FE` estimated. The number is a
plain sequence and is never reused. The letter states where an error could originate and how
far to trust the number; the class of thing it is (a vendor price, a convention, a scenario
input) is recoverable from its `source`.

Changing a figure's class is a rename, done by the tool, not by hand: an estimate that becomes
a measurement is the normal direction of travel.

The trust marker is **computed, not typed**. A formula with an estimate anywhere upstream prints
ᴱ however many derived steps sit between it and the reader, so the weakest input decides the mark
and nobody has to remember to downgrade one by hand.

### Renumbering is safe until something is deleted

Refs are assigned by the tool, which is what makes reclassifying a figure cheap, and appending one
is equally cheap. **Deleting one is not**: every later ref of that letter shifts down by one, while
the marks already written into documents still name the old numbers. The tool renumbers the
registry and cannot rewrite the documents. So append rather than insert, and after any delete
re-run the check — the mark count is the only thing that will notice.

## Marking

The ref is glued to the digits, with no character in between, before any closing markup.

```
correct     | **552.91<!--FR12-->** |
correct     $553.83<!--FD7--> / month
correct     ~$0.51<!--FE4--> ᴱ
correct     0.2195<!--FM9--> GB/h
wrong       **552.91**<!--FR12-->      markup between number and ref
wrong       552.91 <!--FR12-->         a space
wrong       $0.3833/h<!--FR3-->        unit captured inside the pair
wrong       $553.83<!--FD07-->         zero-padded; the tool writes FD7
```

Units, currency words and suffixes stay outside the pair: the number and its ref are one
indivisible token, everything else is prose.

Where a reader benefits from seeing the handle, the visible form is an anchor too and needs no
comment: `**$554** ᴿ (FD7)`. Between the number and its ref only closing markup, a trust marker
and whitespace may sit — never a word. A ref separated from its number by prose is not a mark: it
reads like one, nothing checks it, and an unverified number that looks verified is worse than an
unmarked one.

Both forms must actually parse, and that is worth testing rather than assuming. The visible form
was documented here for a day while the checker silently skipped every anchor carrying bold or a
trust marker — which is to say, every anchor anyone would really write.

## Scope

Mark the report in full: it is the deliverable, and its numbers are the ones a reader acts on.
In execution documents mark what the registry already claims through `appears_in`. Do not
retrofit narrative evidence inside journal notes — a per-run cost quoted once to support a
sentence is evidence, not a figure, and registering it buys nothing.

## How a figure is written

| Rule | Write | Not |
| :--- | :--- | :--- |
| Thousands separator, always | `24,875` | `24875` |
| Decimal point | `0.00250` | `0,0025` |
| Currency sign against the digits | `$553.83` | `$ 553.83` |
| Approximation before the sign | `~$0.51` | `$~0.51` |
| A range is two marked numbers | `$866.79<!--FD1--> → $753.26<!--FD2-->` | one ref for both |
| No spaces inside a number | `1,166,534` | `1 166 534` |
| The trust marker stays visible | `$553.83<!--FR12--> ᴿ` | dropping ᴿ ᴰ ᴱ |

One figure may have more than one legal rendering — prose prints whole dollars, tables print
cents, a rate keeps the decimals that separate it from its neighbours — and all of them satisfy
the check for the same ref. The rule is that the number on the page must be what the figure
rounds to **at the precision the page chose**: `$554`, `553.83` and `553.8` all resolve to one
figure, and `552.91` resolves to none of them. Checking against a single stored precision instead
would reject most of a rate card, whose figures are written with four decimals and totalled to
two.

## Shapes the scan ignores

A marked number wins over every row here.

| Shape | Example |
| :--- | :--- |
| ISO date and timestamp | `2026-09-04`, `2026-09-05T12:58:01Z` |
| Clock time | `18:00`, `13:14:54Z` |
| Duration | `61.7 min`, `2425ms`, `10m` |
| Version | `v1.18.2`, `7.0.0`, `cpu-1.6` |
| Commit, digest, hash | `cfa0ab79`, `sha-404a267` |
| Cloud resource id | `i-08c951c87d0b77ad6`, `L-34B43A08` |
| File and line | `nodes.tf:72`, `deployment.yaml:52-55` |
| Section and metric reference | `§4.1`, `M9`, `D16`, `K1` |
| Kubernetes quantity | `768Mi`, `4Gi`, `250m` |
| Replica, node, point count | `30 replicas`, `2 nodes`, `3 AZ` |
| Config value in prose | `maxReplicaCount: 20`, `threshold 0.2` |
| Ratio, status class, percentile | `×4.1`, `5xx`, `p95` |

Fenced code blocks and inline code spans are skipped whole: queries, commands, manifests and
paths are full of digits that mean nothing to the report.

## What this cannot settle

Four classes stay semantic. Each needs a habit, not a pattern.

1. **A bare count that is a figure.** `84,018 points` is a figure, `30 replicas` is not, and
   nothing in their shape separates them. Bare counts the report reuses must be registered.
2. **A formula input stated in prose.** `2 × 50 GB` feeds a figure. Editing the prose does not
   change the money and no check sees a conflict. Quantities that enter a formula belong in the
   registry.
3. **Prose arithmetic.** "2.3× the previous point" is computed while writing. Rule 0 forbids it;
   only a reader catches a violation. If a sentence states a relationship between two figures,
   that relationship is itself a figure.
4. **Ranges derived from a pending input.** Both bounds are figures that resolve to `pending`
   until the input exists.

The first three share one shape: a number that should be in the registry and is not. The tool
reports it as unclassified rather than guessing; the fix is always to register it.
