# Trading Framework: Thesis-Driven Options Positioning

*Elicited from: active trader, photonics/AI sector + precious metals*
*Session date: April 2026*
*Elicited by: Interviewer + Synthesizer agents via /elicit skill*

---

## Core Principles

1. **The thesis drives the hold. The EMA structure is the kill switch.** "Price needed to stay within the bounds in order for me to keep the thesis validated." These are two separate layers — conviction lives at the macro level; the EMA is the boundary condition that can invalidate it, not the reason to hold.

2. **Option structure (80Δ ~30 DTE) is not a preference — it's what keeps the Greeks from becoming an independent kill switch.** Deep ITM, sufficient DTE means theta and IV don't matter under normal conditions. This lets the EMA read cleanly as the actual signal.

3. **Cutting is sometimes just resetting the instrument, not abandoning the trade.** When you cut a compromised contract, you go to cash and monitor. The thesis stays alive; the vehicle changes.

4. **P&L context on the full series matters to the cut decision.** Cutting a loser on roll #8 after 100%+ profit is categorically different from cutting a fresh position. The same action means different things depending on the history behind it.

5. **Adding at a pullback requires both thesis conviction AND prior pattern recognition in the specific instrument.** It's not reproducible without both conditions.

6. **Position sizing scales with conviction + price confirmation.** It is not a fixed formula.

---

## The Two-Layer Framework

**Layer 1 — The Thesis:** Why this asset or sector should move in this direction. (Example: photonics stocks as AI infrastructure picks; gold's bull run to $5,000.) This is the reason to be in the trade at all.

**Layer 2 — The Price Boundary:** The EMA structure (20/50 EMA) defines the bounds within which the thesis is considered intact. As long as price respects these levels, the thesis remains valid. If price violates the key level, Layer 1 becomes irrelevant — exit regardless of conviction.

The two layers are not interchangeable. A strong thesis with broken price structure = exit. A weak-feeling moment with intact price structure = hold.

---

## Option Structure Setup

- **Target: ~80 delta, ~30 DTE deep ITM calls**
- At these parameters, theta and IV are manageable noise under normal price behavior
- This allows EMA levels to serve as the actual decision signal — not Greeks
- **When structure degrades** (short DTE + price drops to ATM/OTM), theta becomes lethal and acts as an independent kill switch. A correct thesis cannot save a structurally degraded contract.

---

## Hold & Add Logic

**Hold conditions:** Thesis intact AND price within EMA bounds. Both required.

**Add at the 50 EMA conditions** (both required):
1. High-conviction thesis
2. Prior pattern recognition in the specific instrument or sector — e.g., "I've seen this ticker (and others in photonics) shoot up 20-40%, retreat to the mean, and take off again"

The 50 EMA hold confirms the familiar cycle is intact. This is **not** averaging down. Averaging down is reactive — you add to reduce cost basis and hope for recovery. Adding at the 50 EMA is a second entry based on recognizing exactly where in the cycle the price is sitting.

> "The confidence wasn't 'I believe in this company generally.' It was 'I've seen this exact behavior before, and the price is sitting exactly where I'd expect it to sit mid-cycle.'"

---

## Position Sizing

- Start at **regular size**
- **Scale up deliberately** when two conditions are met simultaneously:
  - High-conviction thesis developed over time (watching the setup develop)
  - Price confirms with a significant move in the thesis direction
- Example: GLD at regular size through November/early December → significant jump the week of Christmas → deliberate scale-up to ~25% of portfolio
- Concentration at ~25% is an acceptable outcome of this logic when both conditions are met — it is not a ceiling that was accidentally breached

---

## Cut & Roll Decisions

**Roll when:** Thesis intact + option structure still workable (sufficient DTE, still reasonably ITM)

**Cut when:** Structure is compromised — short DTE + price drops to ATM/OTM → theta becomes lethal
- Cut even if the thesis is still fully intact
- The instrument can no longer survive long enough for the thesis to play out

**After cutting:** "Go to cash and monitor the price action for a little bit before re-entering." Not abandonment — reset.

**Roll limit:** There is a natural endpoint. After a significant run of rolls with substantial profit (e.g., 8 rolls, 100%+ on initial risk), the calculus for an additional roll shifts. At that point, cutting a degraded position and waiting for re-entry may be cleaner than extending further.

---

## Re-entry After a Cut

Re-entry is not discretionary. A specific price test must be met:

1. **Price reclaims the prior high** (the high it fell from when you cut)
2. **Price holds that level** — multi-day confirmation required

Observed confirmation pattern: gap up above prior high → holds next day → holds through end of week → re-enter.

During the wait: maintaining exposure to the thesis via a related instrument (e.g., keeping SLV open while cut from GLD) signals the thesis was not abandoned — only the compromised instrument was reset.

---

## Failure Modes

**Primary failure mode: Option structure degradation**

The thesis was correct. The 50 EMA held (or was close). But the contract was short DTE and dropped to ATM/OTM. Theta became lethal. The position had to be cut.

- GLD, December 29: 8 rolls in, 100%+ profit on initial risk, contracts expiring mid-January, price dropped to ATM/OTM at the wrong moment
- Cut for a loss on the final position despite a profitable overall series and intact thesis

**Prevention:** Maintain 80Δ ~30 DTE structure. Roll before DTE gets critically short. Don't let the contract get into a position where theta is the dominant force.

---

## Key Distinctions

| Common Conflation | What They Actually Are |
|---|---|
| Adding at EMA = averaging down | Adding at EMA is a *new entry* based on pattern recognition. Averaging down is reactive cost-basis reduction with no independent entry thesis. |
| Cutting = abandoning the thesis | Cutting is resetting the *instrument*. Thesis can remain fully intact. You go to cash and wait. |
| Thesis conviction = reason to hold regardless of price | Thesis is Layer 1. Price structure is Layer 2. Both must be intact to hold. Strong thesis + broken structure = exit. |
| Rolling = staying in a bad trade | Rolling extends the instrument's life while structure is workable. It has a natural endpoint determined by P&L context and structural integrity. |

---

## Open Questions

- **Initial entry criteria:** Not covered in depth — how a position *starts* vs. how it is managed were discussed, but the specific trigger for first entry was not elicited.
- **Maximum position sizing ceiling:** Whether ~25% represents a hard limit or is context-dependent was not explicitly resolved.

---

## Guidance Candidates (Memory Pipeline)

```json
[
  {
    "text": "When evaluating whether to hold an options position at a pullback: enforce the two-layer check — (1) is the thesis still intact AND (2) is price still within the EMA boundary; treat these as separate conditions, both required; avoid treating thesis conviction alone as sufficient justification to hold through a broken price structure",
    "type": "invariant",
    "confidence": 0.95,
    "source": "elicited"
  },
  {
    "text": "When entering deep ITM options for swing trades: enforce targeting ~80 delta and ~30 DTE to keep theta and IV from acting as independent kill switches; avoid contracts that are near ATM or short DTE where Greek exposure becomes the dominant risk factor",
    "type": "decision",
    "confidence": 0.92,
    "source": "elicited"
  },
  {
    "text": "When deciding to cut vs. roll an options position: enforce cutting when the contract has degraded to short DTE + ATM or OTM regardless of thesis conviction, because theta will destroy the position before the thesis can play out; avoid rolling a structurally compromised contract as a substitute for cutting",
    "type": "invariant",
    "confidence": 0.93,
    "source": "elicited"
  },
  {
    "text": "When adding contracts at a pullback to the 50 EMA: enforce requiring both (1) high-conviction thesis AND (2) prior pattern recognition in the specific ticker or sector (e.g., historical 20-40% run → mean reversion → continuation); avoid treating general thesis conviction alone as sufficient justification to add",
    "type": "invariant",
    "confidence": 0.90,
    "source": "elicited"
  },
  {
    "text": "When re-entering a position after cutting to cash: enforce waiting for price to reclaim the prior high AND hold it with multi-day confirmation (gap up → holds next session → holds through end of week); avoid re-entering on a single-day move above the prior high without confirmation of hold",
    "type": "invariant",
    "confidence": 0.88,
    "source": "elicited"
  },
  {
    "text": "When evaluating a cut decision on a position with multiple prior rolls: enforce factoring the full-series P&L into the decision — cutting a loser on roll 8 after 100%+ cumulative gain is a disciplined reset, not capitulation; avoid evaluating the final contract's P&L in isolation from the series that preceded it",
    "type": "decision",
    "confidence": 0.85,
    "source": "elicited"
  },
  {
    "text": "When scaling position size: enforce deliberate scaling only when two conditions are simultaneously met — (1) high-conviction thesis developed over time AND (2) price action confirms with a significant move in the thesis direction; avoid scaling up based on conviction alone without price confirmation",
    "type": "invariant",
    "confidence": 0.87,
    "source": "elicited"
  },
  {
    "text": "When cutting one instrument in a thesis trade: enforce distinguishing between cutting the instrument and abandoning the thesis — it is valid to cut GLD contracts while maintaining SLV exposure if the thesis (precious metals bull run) is intact but the specific contract is structurally compromised; avoid treating a contract cut as equivalent to a thesis exit",
    "type": "decision",
    "confidence": 0.83,
    "source": "elicited"
  }
]
```
