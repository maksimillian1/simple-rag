# Baseline — Metrics

Refs are cited from outside this execution by path: `00-baseline/M1`. Confirm every name
against the live endpoint before writing a query. A wrong name returns NO DATA, which is
indistinguishable from a missing scrape target.

| Ref | What it measures | Source | Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| M1 | idle spend by service over the idle window | Cost Explorer · daily granularity · `TAG:feature=simple-rag` present | ⟨confirmed YYYY-MM-DD⟩ | every floor line resolves to a row of this |
| M2 | share of idle spend arriving with no attribution tag | same source, tag absent | ⟨confirmed YYYY-MM-DD⟩ | gate at under 5 %, resolved before the A / B split is trusted |
| M3 | node inventory during the idle window | `kube_node_labels` | ⟨confirmed YYYY-MM-DD⟩ | proof of idleness — `apps-compute` at zero for the whole window. Selector on `label_karpenter_sh_nodepool`; unfiltered it counts the Qdrant node as elastic capacity |
| R4 | Qdrant resident memory at teardown | `kubectl top pod`, once, at ⟨moment⟩ · ⟨who⟩ | active | confirms the instance class against D6 |
| D5 | Block C | `A + B` | active | arithmetic over the blocks; carries no line and no fixed/variable attribute |
| D6 | Qdrant vector memory | `dims × bytes_per_dim × points × (1 + index overhead)` | active | sizing arithmetic, not a finding; no run varies it |
| E7 | always-on alternative to the floor | ⟨basis⟩ against Block B | active | the reference value §2 Floor is judged against |
