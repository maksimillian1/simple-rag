# 00 · Baseline

- **Purpose** — system at rest: frozen constants, denominator, price basis, metric register, floor
- **Produces** — frozen config · price basis · metric register · floor baseline
- **Expected** — ⟨recorded ⟨date⟩, before capture⟩: Block B is dominated by the Qdrant On-Demand node and its gp3 volume; every other B line is under 10 % of B
- **Revision** — v1.0 (supersedes none)
- **Capture window** — ⟨YYYY-MM-DD HH:MM → HH:MM UTC⟩
- **Frozen at** — `⟨sha⟩` · by ⟨name⟩
- **Capture notes** — ⟨success · anomaly and how it was treated⟩

Mechanisms are in `./concepts.md` as `K⟨n⟩`. The register is in `./metrics.md`.

---

## 1 · Plan

### Preflight

- [ ] System frozen at a tagged commit; chunker and indexer image digests recorded below.
- [ ] Every `M` ref confirmed against a live endpoint and dated in `./metrics.md`.
- [ ] Every confirmed ref returns data with non-empty label dimensions under its selector.
- [ ] Cost attribution tags verified active in IaC (`terraform/`), including tags applied by Karpenter to the nodes it creates → K3.
- [ ] Untagged share of the idle bill measured and under 5 % → M2, K3.
- [ ] Price basis captured → `./data/price-⟨YYYY-MM-DD⟩.json`.
- [ ] Fixture profile captured → `./data/corpus-profile.txt`.
- [ ] Cluster identity captured → `./data/identity-⟨YYYY-MM-DD⟩.txt` (image digests, chart revisions, AMI IDs).
- [ ] Idle window scheduled: spans a full daily cycle, zero execution points, S3 event notification disabled → K1.
- [ ] Collection snapshot taken before any teardown → `./data/snapshot-⟨YYYY-MM-DD⟩/`.

### Metrics

Register in `./metrics.md`. Refs cited from elsewhere as `00-baseline/<ref>`.

---

## 2 · Results

### Configuration freeze

| Parameter | Value | Set in | Why frozen |
| :--- | :--- | :--- | :--- |
| `apps-compute` instance type | ⟨⟩ | Karpenter NodePool | makes `$/run` a product rather than a sum over types → `01-ingestion/D17` |
| `apps-compute` `consolidateAfter` | 30 s | Karpenter NodePool | sits inside the run window by construction → K7 |
| chunker requests / limits | ⟨cpu⟩ · ⟨mem⟩ | `deploy/k8s/apps/chunker` | sets worker packing density → K8 |
| indexer requests / limits | ⟨cpu⟩ · ⟨mem 2Gi⟩ | `deploy/k8s/apps/indexer` | packing density; the 2 GB limit is the guardrail under test |
| TEI replicas | ⟨n⟩ | `deploy/k8s/apps/tei` | a moving replica count makes the second constraint tier unattributable |
| Qdrant collection config | INT8 SQ on · 384 dims · sparse on | Helm values | changes write cost and RAM together → K4 |
| Image digests | chunker `⟨sha256:…⟩` · indexer `⟨sha256:…⟩` | | the one thing that must not move while the config commit does |

### Input fixture — the denominator → report §2

- **Unit of work** — one source document, complete when its last chunk is upserted and counted in Qdrant `points_count`
- **Exact unit count** — `⟨N⟩`
- **Distribution** — median ⟨X⟩ pages · p95 ⟨Y⟩ · total ⟨Z⟩ MB · formats ⟨pdf / md / txt split⟩
- **Profile source** — `./data/corpus-profile.txt`, frozen ⟨YYYY-MM-DD⟩ (`⟨sha⟩`)
- **Arrival** — bulk drop: the whole corpus uploaded at once, not a stream

### Price basis → report §4.3–4.4

- **Data file** — `./data/price-⟨YYYY-MM-DD⟩.json`
- **Rate type** — ⟨On-Demand list · Savings Plan · EDP⟩
- **Region & currency** — `⟨eu-central-1⟩` · USD
- **Covers** — EC2 On-Demand and Spot by type · EBS gp3 · EKS control plane · Fargate vCPU/GB · NAT hourly and per-GB · S3 storage and requests · SQS requests · Bedrock per 1K tokens
- **Spot basis** — historical average over ⟨window⟩, not the instantaneous quote. Representativeness against the actual run windows is checked in `01-ingestion` Retro

### Envelope → report §2

- **Platform** — ⟨region⟩ · EKS ⟨version⟩ · Karpenter ⟨version⟩ · pinned instance types, x86_64. Re-measure on any node-type or ARM64 change
- **Scale range** — one Qdrant node, collection under ⟨n⟩ points. Re-measure on sharded Qdrant
- **Input** — the frozen corpus profile above. Re-measure on a different format mix, especially the PDF share
- **Environment** — single-tenant cluster, no co-tenant load during any window. Re-measure on a shared cluster
- **Commercial** — ⟨rate type⟩ as of ⟨date⟩. Re-measure on any rate change
- **Outside** — multi-region, GPU inference, managed vector SaaS

### Floor → report §4.1

Captured over a full idle daily cycle with attribution active. What keeps running during the window — ArgoCD, Karpenter, Cilium, the monitoring stack — is floor, not contamination → K2.

| Line | Block | $/month | Fixed / variable |
| :--- | :--- | :--- | :--- |
| EKS control plane | A | ⟨73⟩ ᴰ | fixed |
| `core-on-demand` node group | A | ⟨⟩ | fixed |
| Karpenter on Fargate | A | ⟨⟩ | fixed |
| NAT gateway — hourly | A | ⟨⟩ ᴰ | fixed |
| NAT gateway — per GB | A | ⟨⟩ | variable |
| Monitoring stack — Prometheus, Loki, Grafana, EBS | A | ⟨⟩ | fixed → K2 |
| Qdrant node — On-Demand | B | ⟨⟩ | fixed |
| Qdrant gp3 volume | B | ⟨⟩ | fixed |
| TEI baseline replica | B | ⟨⟩ | fixed |
| Go API replica | B | ⟨⟩ | fixed |
| S3 — corpus at rest | B | ⟨⟩ | variable |
| SQS — idle | B | ⟨0⟩ | variable |

- **A · Shared** — ⟨$⟩
- **B · Dedicated** — ⟨$⟩ → report §1 BLUF
- **C · Total** — ⟨$⟩ ᴰ (`D5`)
- **Reference value** — ⟨always-on alternative⟩ ᴱ (`E7`) · the unqualified idle claim published in article 1 → K6
- **Raw data** — `./data/idle-⟨YYYY-MM-DD⟩.csv`

Never divided by an assumed number of co-tenant features: that divisor is invented → K2.

Derived alongside: Qdrant vector memory `D6` — sizing arithmetic, not a finding → K4. Measured Qdrant RSS at teardown: `R4`.

### Retro

- **Expectation** — ⟨held · inverted, and which line actually dominates B⟩
- **Cost against estimate** — ⟨actual vs budgeted capture cost⟩
- **Not observed** — ⟨line and why⟩ → report Coverage
