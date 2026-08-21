# Puzzles & Conquest Chat Automation Sub-Plan

## 1. Purpose

This document owns automated in-game chat behavior, including both deterministic non-LLM replies and LLM-backed social replies.

It is intentionally separate from:

- [PNC_TASK_SUBPLAN.md](/c:/Users/lebel/pnc/PNC_TASK_SUBPLAN.md), which owns the broader feature-planning model,
- [PNC_SCREEN_FLOW_ARCHITECTURE.md](/c:/Users/lebel/pnc/PNC_SCREEN_FLOW_ARCHITECTURE.md), which owns reusable navigation and chat-screen access flows,
- [PNC_AUTOMATION_IMPLEMENTATION.md](/c:/Users/lebel/pnc/PNC_AUTOMATION_IMPLEMENTATION.md), which remains the primary platform architecture plan.

This file should answer one class of questions only:

- what chat automation modes we support,
- how incoming chat is converted into canonical reply decisions,
- where deterministic policy ends and LLM behavior begins,
- how prompt iteration, context injection, and safety constraints are handled.

## 2. Current confirmed context

From the current Python automation codebase:

- incoming Kingdom Chat polling already exists through the canonical `collect_kingdom_chat` task,
- visible player chat rows are already normalized and archived,
- direct alliance and world chat sending already exists through canonical chat-send tasks,
- chat monitoring and chat writing are therefore already separated enough to support one reply-decision layer between them.

This means the current planning problem is not "how do we automate chat from scratch", but rather "how do we introduce one canonical responder layer without duplicating chat capture or chat send behavior."

## 3. Scope

This sub-plan should own:

- deterministic chat triggers and prerecorded replies,
- LLM-backed reply generation and reply classification,
- per-user or per-scenario prompt specialization,
- short-term memory and context injection rules,
- safety, cooldown, and deduplication policy,
- validation strategy for reply quality and runtime safety.

This sub-plan should not own:

- low-level chat-screen navigation,
- selector refinement for chat tabs or input fields,
- raw OCR extraction details,
- a second parallel chat ingestion pipeline.

## 4. Use-case inventory

The current target use cases are:

### Non-LLM deterministic modes

- naive mode: when a particular user speaks, post one prerecorded sentence,
- scenario mode: when a recognized event or system announcement appears, post one generic canned sentence,
- spammy or ambient mode: optionally drop lightweight kingdom-chat filler lines under strict cooldown policy.

### LLM-backed modes

- general social mode: interact normally and match the surrounding social setting,
- user-targeted mode: use a dedicated prompt for one particular user and inject prior conversation context,
- context-aware mode: read recent chat, infer what is being discussed, and post a relevant response through the existing chat-send flow.

## 5. Recommended ownership model

Chat automation should keep one canonical pipeline:

1. observe or collect chat,
2. extract only newly relevant chat events,
3. run canonical reply policy,
4. optionally call an LLM,
5. validate the proposed reply,
6. send through the existing chat-send task.

Recommended canonical concepts:

- `ObservedChatEvent`: one new incoming row or event worth evaluating,
- `AutoChatDecision`: typed result such as `skip`, `reply`, or `escalate`,
- `AutoChatPolicy`: deterministic eligibility, cooldown, deny-list, and routing rules,
- `AutoChatResponder`: pluggable responder contract,
- `RuleBasedResponder`: canned deterministic responder,
- `LlmResponder`: structured LLM-backed responder,
- `ConversationMemoryStore`: bounded recent context and per-user memory source.

The key design constraint is that chat capture and chat send should remain canonical and unchanged in ownership. This feature should introduce only one decision layer between them.

## 6. Delivery model

Recommended rollout:

### Phase 1: deterministic responder

- build event extraction on top of archived or freshly collected chat rows,
- support exact user triggers, keyword triggers, and simple scenario triggers,
- send prerecorded responses using existing chat-send tasks,
- add cooldowns, dedupe, self-message suppression, and audit logging.

### Phase 2: LLM classification only

- keep final reply text deterministic,
- use the LLM only to classify intent, tone, target user, or whether a reply is appropriate,
- prove prompt quality and safety before enabling freeform generated text.

### Phase 3: constrained LLM generation

- allow the LLM to generate reply text,
- require structured output with `should_reply`, `reason`, `tone`, and `reply_text`,
- reject invalid or policy-breaking outputs,
- fall back to `skip` or canned replies on uncertainty.

### Phase 4: targeted persona and memory

- support user-specific prompt overlays,
- inject recent thread context and selected longer-term facts,
- add per-user conversation continuity without turning the system into open-ended autonomous roleplay.

## 7. Library recommendation

The default recommendation is to use the official OpenAI Python SDK directly, not a higher-level orchestration framework.

Why:

- the use case is narrow and the pipeline is already owned locally,
- direct SDK usage keeps the architecture small and explicit,
- prompt iteration, structured outputs, retry policy, and logging remain under our control,
- introducing LangChain, LlamaIndex, or similar orchestration frameworks would add abstraction before the actual requirements are stable.

Recommended rule:

- use the OpenAI SDK directly for model calls,
- keep the provider behind one small local interface so another provider can be swapped later if needed,
- do not introduce a framework dependency until the local pipeline proves genuinely insufficient.

## 8. Model-training recommendation

Partial retraining or fine-tuning should not be part of the first implementation plan.

Recommended stance:

- do not retrain for the current use cases,
- first solve behavior with prompting, structured outputs, bounded memory, and deterministic policy,
- only revisit fine-tuning after we have a meaningful corpus of accepted and rejected chat decisions.

Reasons:

- current needs are mostly style, tone, and local-context handling rather than domain-general knowledge gaps,
- prompt and context iteration will be faster and cheaper than model training,
- moderation and failure modes must be understood before freezing behavior into a trained artifact,
- there is not yet a clearly curated dataset for high-quality supervised tuning.

Fine-tuning becomes worth reconsidering only if:

- prompt size becomes too large,
- style consistency remains poor after prompt refinement,
- we accumulate a validated dataset of reply decisions and desired outputs,
- inference cost or latency from long prompts becomes operationally significant.

## 9. Prompting strategy

Prompt design should be treated as a versioned runtime asset, not scattered hardcoded strings.

Recommended prompt layers:

### Base system prompt

- defines identity, tone, safety boundaries, and the fact that the agent is speaking in an in-game social setting,
- defines hard prohibitions such as no hostile spam, no personal claims, no out-of-game secrets, no revealing automation.

### Mode prompt

- general social mode,
- helper mode,
- ambient filler mode,
- user-targeted mode.

### Scenario prompt overlay

- kingdom chat,
- alliance chat,
- reaction to announcement,
- direct interaction with a known player.

### Context payload

- recent visible chat turns,
- relevant per-user conversation summary,
- selected durable facts,
- current policy flags and cooldown state.

### Output contract

- structured JSON-like response with explicit fields,
- no direct freeform output accepted without validation.

Prompt iteration should be done by storing prompt versions, sample conversations, expected decisions, and observed failures in one dedicated prompt-evaluation folder or artifact set.

## 10. Context-injection model

Context should be explicitly bounded and layered. The system should not dump the full transcript into the model.

Recommended context sources:

### Short-term visible context

- last N visible player messages,
- speaker names,
- channel,
- current event type if one is recognized.

### Per-user short memory

- last few exchanges with the same user,
- compact summary of recurring relationship or tone,
- recent unanswered question if still relevant.

### Durable facts

- configured persona facts,
- allow-list or deny-list markers,
- specific user notes when intentionally configured,
- kingdom or alliance-specific factual snippets that are safe to repeat.

### Runtime policy context

- cooldown timers,
- whether this sender already triggered a reply recently,
- whether the message looks like OCR noise or unsupported content,
- whether the scenario permits chat output at all.

Recommended memory rules:

- keep raw recent turns small,
- periodically summarize older context,
- never inject unbounded transcripts,
- keep sender-scoped memory separate from global social context,
- prefer explicit summaries over retrieval from large raw logs for the first version.

## 11. Reply decision policy

Every candidate reply should pass deterministic policy before any send occurs.

Minimum required checks:

- message is not from self,
- message is not a duplicate of a previously handled event,
- sender and scenario are allowed by policy,
- channel is allowed,
- cooldown permits a reply,
- proposed reply length is within bounds,
- reply does not contain blocked phrases,
- reply does not violate a configured anti-spam interval.

Recommended decision result types:

- `skip_no_trigger`
- `skip_on_cooldown`
- `skip_policy_blocked`
- `skip_low_confidence`
- `reply_canned`
- `reply_generated`

These typed outcomes should be logged so prompt and policy iteration can happen from evidence rather than guesses.

## 12. Safety and product constraints

Chat automation should fail closed.

Required safety rules:

- if parsing fails, send nothing,
- if structured LLM output is invalid, send nothing,
- if the LLM is uncertain, prefer `skip`,
- if OCR quality is ambiguous, send nothing,
- do not reply repeatedly to the same user in a short window,
- do not let the system free-chat indefinitely without explicit product intent.

Recommended additional controls:

- per-channel enable flags,
- per-user allow-list mode for early rollout,
- dry-run mode that logs intended replies without sending,
- daily send caps,
- reply jitter so messages do not look perfectly robotic.

## 13. Suggested implementation slices

### Slice A: canonical event extraction

- define the exact "new chat event" model from archived or in-memory chat deltas,
- add deterministic dedupe and handled-event tracking,
- validate with transcript-driven unit tests.

### Slice B: rule-based responder

- support user-specific triggers,
- support keyword and announcement scenario triggers,
- support canned response selection with cooldowns,
- validate end to end with dry-run and live send smoke coverage.

### Slice C: LLM client and structured decision contract

- add one provider interface and one OpenAI-backed implementation,
- define structured request and response models,
- add parsing, validation, retry, timeout, and logging behavior,
- keep generation disabled until classification quality is acceptable.

### Slice D: prompt asset management

- create versioned prompt files,
- add representative transcript fixtures,
- document expected output contracts and failure examples.

### Slice E: memory and context injection

- add bounded recent-turn loading,
- add per-user summary storage,
- add context builders that compose only the relevant slices for a given event.

### Slice F: constrained generation rollout

- enable generated replies only for narrow channels or allow-listed users,
- monitor logs,
- expand scope only after observed stability.

## 14. Validation strategy

The feature should be validated at three levels.

### Pure logic validation

- event extraction from transcript deltas,
- dedupe and cooldown policy,
- trigger matching,
- prompt-context assembly,
- structured response validation.

### Transcript fixture validation

- feed representative archived chat snippets into the responder,
- assert expected `skip` versus `reply` decisions,
- keep a prompt-regression set for future model or prompt changes.

### Live validation

- dry-run first with no send,
- limited live send against an allow-listed test context,
- verify that chat navigation and send behavior remain canonical and stable.

## 15. Open design questions to resolve during iteration

- whether the first LLM mode should classify only or classify plus generate,
- whether per-user memory should be raw-turn based, summary based, or hybrid,
- what the first supported channels should be,
- how much ambient filler behavior is desirable before it becomes spammy,
- whether announcement-triggered replies belong in the same responder pipeline as player-message replies,
- what exact persona constraints should be enforced in the base prompt.

## 16. Immediate recommended next steps

1. Start with one deterministic `auto_chat` tracer bullet that reacts to one allow-listed player and one announcement scenario.
2. Add handled-event persistence, cooldown policy, and dry-run logging before any LLM dependency is introduced.
3. Introduce one small OpenAI-backed responder interface with structured outputs only.
4. Build prompt fixtures and transcript-based evaluation before enabling generated replies.
5. Defer fine-tuning or retraining until prompt-plus-context quality is clearly insufficient and we have a curated dataset.
