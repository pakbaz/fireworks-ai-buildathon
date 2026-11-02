# System flow

How one invoice moves through the system, from arrival to one of three outcomes. This is the production shape. The benchmark in [plan.md](plan.md) exercises everything inside the dashed box; the boxes outside it are described in the demo, not built today.

```mermaid
flowchart TB
    classDef code fill:#e8f0fe,stroke:#1a56db,color:#111
    classDef model fill:#fdf2e9,stroke:#d9480f,color:#111
    classDef human fill:#f3e8ff,stroke:#6f42c1,color:#111
    classDef out fill:#e6f4ea,stroke:#137333,color:#111
    classDef store fill:#fff8e1,stroke:#b26a00,color:#111

    subgraph IN["Inputs"]
        direction LR
        INV["Invoice<br/>(scan, PDF, e-invoice)"]
        PO["Purchase order<br/>(ERP)"]
        GR["Goods receipt<br/>(warehouse, often paper)"]
        SN["Shipping notice<br/>(optional)"]
        PAID[("Paid invoices<br/>for this PO")]
    end

    subgraph SYS["Reconciliation harness (built today)"]
        direction TB
        PKT["1 · Assemble case packet<br/>+ as-of date"]:::code
        LOOK["2 · Wiki lookup by ID<br/>supplier · items · warehouse · policy"]:::code
        NORM["3 · Normalize in code<br/>dates · numbers · currency<br/>pack sizes · aliases from wiki"]:::code
        EXT["4 · Extract to JSON<br/>small open model on Fireworks<br/>every field: ok / unreadable / absent"]:::model
        CHK{"5 · Deterministic checks<br/>qty × price = line total<br/>lines sum to subtotal<br/>PO ref matches across docs<br/>price within policy tolerance<br/>invoice qty = received qty<br/>invoice no. not already paid<br/>GR present, or notice in window"}:::code
        RR["6 · Targeted re-read<br/>only fields that failed or were unreadable<br/>large open model on Fireworks<br/>wiki hints · 3 reads · majority vote"]:::model
        DEC{"7 · Decide in code<br/>fail closed"}:::code
    end

    subgraph WIKI["Company wiki (typed JSON, written by humans)"]
        direction LR
        WS[("suppliers")]:::store
        WI[("items")]:::store
        WW[("warehouses")]:::store
        WP[("policy")]:::store
    end

    CLEAR(["CLEAR<br/>release for payment<br/>evidence attached"]):::out
    WAIT(["WAIT<br/>goods in transit<br/>re-check at notice date + window"]):::out
    ESC(["ESCALATE<br/>reason code + fields compared<br/>+ ranked candidate POs or receipts"]):::out

    AN["AP analyst queue<br/>sorted by probability × amount"]:::human
    ERP["ERP posts and pays"]:::code
    SCHED["Scheduler re-queues the case"]:::code
    FIX["Analyst resolves with supplier"]:::human
    NOTE["Analyst adds or updates a wiki page<br/>(reading hints only, never outcomes)"]:::human

    INV & PO & GR & SN & PAID --> PKT
    PKT --> LOOK
    WS & WI & WW & WP -.-> LOOK
    LOOK --> NORM --> EXT --> CHK
    CHK -- "all pass on readable fields" --> CLEAR
    CHK -- "any failure, or any unreadable critical field" --> RR
    RR --> DEC
    DEC -- "checks now pass" --> CLEAR
    DEC -- "mismatch on a clearly read field" --> ESC
    DEC -- "critical field still unreadable" --> ESC
    DEC -- "no GR, shipping notice within window" --> WAIT

    CLEAR --> ERP
    WAIT --> SCHED --> PKT
    ESC --> AN --> FIX
    FIX -. "learned pattern" .-> NOTE
    NOTE -. "human-approved page" .-> WIKI
```

## What each step guarantees

| Step | Who does it | Guarantee |
|---|---|---|
| 1 Assemble | code | Every arm and every run sees the same packet. Nothing is fetched later. |
| 2 Wiki lookup | code | Deterministic, by ID. No search, no retrieval error. Missing page is fine. |
| 3 Normalize | code | One canonical form for dates, numbers, units and names before any model sees them. |
| 4 Extract | small model | Structured JSON with a status per field. The model may not guess a value it cannot read. |
| 5 Checks | code | Arithmetic and cross-document comparison. This is the authority. A model never overrides it. |
| 6 Re-read | large model | Spends tokens only on fields that failed. Wiki pages tell it where to look and what is authoritative. |
| 7 Decide | code | Fail closed. The only path to CLEAR is every check passing on fields marked readable. |

## Where the model is and is not

The two orange boxes are the only places a model runs. It reads. It does not decide, approve, compute totals, invent conversions, or widen tolerances. Everything a judge or auditor would want to trace is in the blue boxes and is deterministic.

## The learning loop

The dotted path from the analyst back to the wiki is how the system gets better per company. A reviewer who clears a case because "this supplier writes the received count by hand" records that once, as a typed page with an author, approver and expiry. The next invoice from that supplier is read correctly and never reaches the queue. Nothing extracted from a document is ever written to the wiki automatically. This loop is described in the demo and is not built today.

## Three outcomes, three destinations

| Outcome | Goes to | Counts as a human escalation |
|---|---|---|
| CLEAR | ERP, posted and paid | No |
| WAIT | Scheduler, re-queued after the notice window | No |
| ESCALATE | Analyst queue, with reason code, fields compared, and candidate matches attached | Yes |

The benchmark measures how often agreeing invoices end up in the third row, while every real discrepancy must end up there.
