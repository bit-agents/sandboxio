# ADR-0013 — Complement OpenAI's `SandboxClient`, do not compete with it

**Status:** Accepted
**Date:** 2026-09-19
**Related:** [ADR-0001](0001-ports-and-adapters.md), [hazards](../hazards.md#market-hazards)

## Context

OpenAI Agents SDK v2 ships `SandboxConfig` with clients for Blaxel, Cloudflare, Daytona,
E2B, Modal, Runloop and Vercel plus a Manifest workspace abstraction. It is the most
important prior art: same problem, same language, backed by the largest agent ecosystem.

It is, however, coupled to that SDK. LangChain's `langchain_e2b` / `_modal` / `_daytona`
have the same shape and the same coupling. The open niche is the framework-agnostic,
self-hostable Python layer spanning local and managed-cloud backends — but "framework ships
a good-enough sandbox layer" is the highest-likelihood market risk on the board.

## Decision

Treat the framework layers as **distribution channels, not competitors**:

- Ship `sbx.integrations.openai_agents` in **both directions**: sbx as a plain tool, and
  `SbxSandboxClient` exposing sbx backends **as** a `SandboxClient` pluggable into
  `SandboxRunConfig`.
- Same posture for LangGraph, Pydantic AI and CrewAI: the adapter returns the framework's
  **native** tool object, is under 100 lines, and contains no logic that belongs in core.
- Differentiate on what the framework layers do not do: framework-agnosticism, security
  depth (deny-by-default, isolation tiers, audit), offline testing via `FakeBackend`, and
  the contract suite.
- **Pre-committed pivot:** if `SandboxClient` becomes the de facto multi-provider standard,
  retarget — sbx backends become `SandboxClient` implementations and that adapter becomes
  the main product surface. This is a planned outcome, not a defeat.

## Consequences

- Integration adapters are a standing maintenance cost across framework versions, tested in
  a weekly CI matrix with documented supported ranges.
- Being inside those ecosystems is worth more than standalone stars, and it hedges the
  absorption risk: if the framework layer wins, we are already part of it.
- It also constrains us. Our port protocols should stay close enough in shape to
  `SandboxClient` that the bidirectional adapter remains thin; a large impedance mismatch is
  a signal worth investigating before it calcifies.
