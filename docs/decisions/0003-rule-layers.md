# ADR 0003: Rule layers: generic engine, source profiles, locale profiles


**Status:** accepted (2026-11-23); documentation now, code extraction deferred

## Context
The changelog-oracle decision (confidence is never compared by Overture's changelog) is true of **Overture**, not
of map data in general. Source-specific rules need to be identified as such, with a data-product-agnostic
ruleset alongside, because each future dataset brings its own nuances. Review of the contract found three kinds
of rule, not two: some rules are specific to **South Africa** (region codes, phone format), not to Overture.

It also found an overclaim in ADR 0001: "Stage A is the only Overture-specific stage" is false; the §9 oracle and
the meaning of lifecycle fields are source-specific too.

## Decision
1. Every contract rule carries one tag: `[generic]`, `[source: overture]` or `[locale: ZA]` (contract §0 lists
   each rule and its layer).
2. A new source or locale must define a profile using the contract §0 checklist before it is compared; rules are
   never borrowed from another profile by default.
3. **Code is not refactored now.** Both profiles stay inline in `src/geotrustops/pipeline.py` until a second source or
   locale exists; the extraction is a recorded follow-up, paired with ADR 0001's
   "second adapter" step.

## Why not build a rules framework now
- With one source and one locale, any abstraction is a guess about which rules generalise; the second source is
  what reveals the real seams.
- It would cost a refactor, re-tests and another independent review with no change in results.
- Documenting the layers now is cheap and removes the overclaim immediately; the code boundary follows evidence later.

## Consequences
- No behaviour, output or test changes (CONTRACT_VERSION stays 0.3).
- In short: the engine is source-agnostic by design; source and locale rules are explicitly profiled;
  only the Overture/ZA profile is implemented, and it isn't yet separated in code.
