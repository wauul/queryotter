# QueryOtter

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Developers and analysts who need to understand an unfamiliar database, turn a business question into a reviewed native query, and investigate performance. Audience emphasis is inferred from the implemented query editor, schema explorer and benchmark reports; the user explicitly delegated ordinary product and design decisions.

## Product Purpose

Connect databases, generate schema-grounded queries, execute only on an explicit Run action, and distinguish evidence-backed optimization from suggestions.

## Operating Context

React 19, TypeScript and Vite frontend on Vercel; Python API and worker on Railway; account and workspace data in Neon. Groq provides the model. Hash routes and existing API contracts must remain compatible. The original PostgreSQL experiment portfolio remains available alongside the multi-engine assistant.

## Capabilities and Constraints

Nine engine adapters and thirteen provider presets. The support matrix distinguishes local/emulator tests from hosted verification. Read-only controls, bounded results, cancellation, schema discovery, conversational refinement, saved queries, history, retention, exports, local connectors and account deletion are implemented. Capabilities differ by engine. A generated query never executes automatically. Production connections are never modified for benchmarks. GitHub, Google and Microsoft sign-in are configured; Microsoft organizational access may require publisher verification.

## Brand Commitments

Keep the QueryOtter name and the original artwork and colors in web/Otter.tsx unchanged. The user expressly requested a complete redesign, three different directions chosen autonomously, both themes, accessible controls and purposeful mobile layouts. Rewrite interface copy without changing factual meaning. No fabricated claims, customer evidence, legal contacts or certifications.

## Evidence on Hand

public/adapter-verification.json, public/deployed-postgresql-benchmark.json, public/deployed-copy-benchmark.json, public/deployed-copy-benchmark-no-gain.json and public/deployed-ui-verification.json contain actual verification evidence. Benchmark improvements describe their measured fixture and correctness scope, never a universal performance promise. Documentation and legal copy already describe actual retention and data processing.

## Product Principles

1. Ground queries in actual metadata.
2. Make review and Run separate actions.
3. Show measurement, variability and correctness scope together.
4. Keep capability limitations and verification status visible.
5. Give users control over connections, history and deletion.

## Accessibility & Inclusion

Keyboard operation, visible focus, labelled native controls, managed modal focus, readable text, both themes, reduced motion and mobile touch targets are explicit requirements. Dense tables may scroll within their own containers. Never shrink the whole interface to fit a phone.
