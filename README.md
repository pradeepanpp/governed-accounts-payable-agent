# Governed Autonomous Accounts Payable Agent

[![CI](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/pradeepanpp/governed-accounts-payable-agent/actions/workflows/ci.yml)

A research-oriented AI engineering project for evaluating governance and human oversight in an autonomous accounts payable workflow.

## Research question

How much does each governance layer reduce policy-unsafe autonomous payment decisions, and what does that cost in automation, human review, latency, and LLM usage?

## Planned workflow

```text
Invoice package
    ↓
LLM extraction
    ↓
Deterministic checks
    ↓
LLM guardrail
    ↓
History and sequence checks
    ↓
Policy engine
    ↓
LLM decision recommendation
    ↓
Deterministic enforcement gate
    ↓
AUTO_APPROVE | ESCALATE | BLOCK