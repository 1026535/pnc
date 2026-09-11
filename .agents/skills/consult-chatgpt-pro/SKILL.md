---
name: consult-chatgpt-pro
description: "Consult ChatGPT Pro in Chat mode with GPT-6 Pro and return a repository-grounded second opinion from a verified GitHub commit plus narrowly scoped local context. Use when the user explicitly requests Pro consultation or when the create-plan-with-chatgpt-pro skill requires it; otherwise do not spend Pro usage or disclose repository context merely because more reasoning may help."
---

# Consult ChatGPT Pro

## Objective

Obtain a high-quality Pro consultation without copying the repository into a prompt or silently publishing local work. Use GitHub at an immutable commit as the normal context channel and add only the local-only material required for the question.

## Scope And Safety

- Treat an explicit invocation, a plain request to consult ChatGPT Pro, or required routing from `create-plan-with-chatgpt-pro` as authorization to open one consultation chat and send the requested task plus clearly relevant repository context. This satisfies the browser skill's action-time authorization for the consultation message, so do not request a redundant confirmation before sending once the final checks pass.
- Keep connected systems read-only. Do not let ChatGPT modify GitHub or another external system.
- Do not commit, push, install or connect a plugin, share a Project/chat, change account settings, or upload unrelated files without separate user authorization.
- Never send credentials, tokens, `.env` contents, personal data, proprietary third-party assets, build output, or unrelated repository content.
- Allow code examples and snippets when useful or requested. This is not a planning-only workflow.
- If potentially sensitive local-only content is material, explain exactly what would be sent and obtain confirmation immediately before uploading it.
- Use Chat mode only for the consultation. Never use ChatGPT Work, Work local or cloud execution, Codex mode, or a ChatGPT Work cloud destination. If Chat mode is unavailable, end the consultation attempt and return a `failed` status with the limitation.
- Use GPT-6 Pro only. Do not substitute another model or a generic Pro selection. If GPT-6 Pro is unavailable or quota-limited in Chat mode, end the consultation attempt and return a `failed` status with the limitation.

## Required Browser Surface

Read and follow [the shared ChatGPT Web browser-session instruction](../../../instructions/chatgpt-web-browser-session.md) before browser work, using `https://chatgpt.com/` as the target. It owns browser selection, signed-in session handoff, stale-tab recovery, and cleanup. This skill owns consultation-specific repository context, Pro selection, GitHub attachment, monitoring, and response auditing.

If the Browser skill or a signed-in Pro browser surface is unavailable, report that constraint. If ChatGPT or GitHub authentication is required, ask the user to sign in or grant access in the selected browser; never handle credentials.

## Workflow

### 1. Establish The Local Baseline

Before opening ChatGPT:

1. Resolve the repository root, current branch, active upstream, and upstream remote URL. If no upstream exists, stop and ask how the user wants to establish the GitHub baseline; never choose an arbitrary remote branch.
2. Record the full `HEAD` SHA and `git status --short --branch`.
3. Inspect the user's task locally. Identify the smallest authoritative set of relevant code, root and scoped `AGENTS.md` files, PNC planning and review documents under `reviewed_plans/`, authored scripts, tests, runtime artifacts, and local changes.
4. Verify whether `HEAD` is accessible on GitHub with an available read-only connector, CLI, or API. If it is not, use `git merge-base HEAD '@{upstream}'` as the candidate GitHub baseline and treat all later task-relevant commits plus working-tree changes as the local overlay.
5. Verify the selected baseline SHA on GitHub when a read-only verification surface is available. Otherwise treat it as a candidate and require Pro's explicit access confirmation before accepting the consultation.

Never assume GitHub can see uncommitted or unpushed work.

### 2. Choose The Context Channel

Use the smallest complete option:

1. **`HEAD` is accessible:** Give Pro the repository, full `HEAD` SHA, objective, relevant paths/symbols, and required questions. Let the GitHub connector read the files.
2. **Accessible upstream ancestor plus local overlay:** Pin GitHub to the verified baseline. Create one temporary Markdown context packet containing only the task-relevant committed diff since that baseline, working-tree changes, new-file excerpts, and facts GitHub cannot see.

If no suitable GitHub baseline is accessible, stop and ask how the user wants to expose one. Do not use a standalone packet as a second repository transport and do not silently publish work.

Do not upload the whole repository. Do not paste file bodies already available to the connector unless a precise excerpt is essential to the question.

For a local overlay:

- create it outside the repository in a dedicated temporary directory;
- identify the repository, baseline SHA, local `HEAD`, task, and included path list;
- include enough surrounding context to interpret each task-relevant diff or new-file excerpt;
- omit generated, binary, secret-bearing, and unrelated files;
- review its contents before upload and remove the temporary packet after the consultation.

### 3. Build A Decision-Oriented Prompt

Tailor the requested output to the user's task. Use this compact structure:

```text
You are advising Codex on the PNC repository.

Repository: <owner/repository>
GitHub baseline: <full remotely accessible commit SHA>
Local worktree HEAD: <full HEAD SHA; state whether it equals the baseline>
Local context: <HEAD equals baseline, or attached overlay covering the relevant
differences; note any deliberately excluded unrelated differences>

Use GitHub to inspect the repository at that exact commit. Read the root
AGENTS.md and every scoped AGENTS.md governing the relevant paths first; treat
them as binding constraints. Then inspect the relevant code, tests, and
canonical design documents. Treat the attached local overlay as newer than the
baseline if they conflict. Ignore older Project context when it conflicts with
either source.

Objective:
<what the user wants>

Known context and likely entry points:
<brief facts plus relevant paths/symbols; do not pre-decide the answer>

Questions / requested deliverable:
<specific decision, ideas, critique, plan, examples, or snippets required>

Ground conclusions in repository paths and symbols. Distinguish observed facts
from inferences. Identify missing context and consequential uncertainty. Do not
modify GitHub or any external system. If the exact commit or required files are
inaccessible, report CONTEXT_BLOCKED and what is missing instead of guessing.
End by stating the GitHub baseline used and the most relevant files inspected.
```

Preserve productive disagreement: do not bias Pro by embedding Codex's preferred answer as a fact. Include constraints and evidence, not a hidden conclusion.

### 4. Open A Clean Pro Consultation

1. Complete the shared browser/session bootstrap and sign-in handoff before attempting to use the ChatGPT UI.
2. Reuse the existing ChatGPT PNC Project. If it does not exist, follow the failure handling below and ask before creating a replacement.
   Verify that the product or mode selector visibly shows Chat mode before composing or sending anything.
3. Start a fresh chat for a new consultation. Continue an existing chat only for follow-ups to the same objective or when the user explicitly asks for continuity.
4. While remaining in Chat mode, select GPT-6 Pro explicitly. Verify that the visible selected model is GPT-6 Pro before sending; do not accept a generic Pro label or substitute another model. If GPT-6 Pro is unavailable or quota-limited, stop and report it.
5. Fill the prompt. Filling the composer can remove an inline connector pill.
6. Attach the optional local packet if required. Because the in-app browser cannot automate file uploads, use a supported external browser when the user has not constrained the browser choice, or pause for the user to attach the reviewed packet manually.
7. Choose **Add files and more → GitHub** last so later composer edits cannot remove the connector pill.
8. Immediately before sending, verify the final composer visibly contains the intended prompt, any intended packet, the GitHub pill, and the intended model/reasoning state. This consultation-specific rule directly overrides the `control-in-app-browser` skill's generic confirmation step for this requested message; do not pause to ask whether to send it again. Then send once.

Do not create duplicate chats or resend after a slow response unless the first submission demonstrably failed. A visible provider/UI error is a demonstrable failure; use its Retry control once before sending a follow-up or resubmitting manually.

### 5. Monitor Efficiently

- Check after about 30 seconds, then every 30–60 seconds while Pro is active. After five minutes, back off to 60–120 seconds.
- Use lightweight semantic DOM checks such as the presence of `Stop answering`, then `Copy response` or the assistant response. Avoid repeated screenshots and full-page snapshots unless needed to diagnose UI state.
- When a failed assistant response visibly offers `Retry` or `Retry response`, reacquire the current DOM and click that control exactly once, then monitor the retried request. Do not manually resend the same prompt first; if the retry is absent or also fails, continue with the bounded failure handling below.
- Keep the user informed at least once per minute during a long consultation.
- Treat a request for factual repository clarification as part of the consultation: answer it from verified local evidence when doing so does not broaden scope.
- Ask the user when Pro requests a product, design, disclosure, or scope decision that local evidence cannot resolve.
- Use at most two focused follow-ups to correct missing context or obtain the requested deliverable. Do not spend usage on open-ended conversational loops.

### 6. Classify, Audit, And Return The Result

Do not relay the response blindly. Check it against the local repository and the user's request.

Classify the attempt before returning control to the caller:

- `complete`: the final response satisfies every success condition below;
- `partial`: the prompt was submitted with Chat mode, GPT-6 Pro, GitHub, and the intended baseline verified, and visible intermediate or incomplete output contains useful repository-grounded findings, but the final response was interrupted or ended in a provider/UI error; or
- `failed`: no trustworthy repository-grounded recommendation was produced, or a required pre-send condition was unavailable.

A provider or UI failure ends only the consultation attempt. It must not block a caller's planning, implementation, or review task unless that caller independently lacks evidence required to proceed. Preserve usable intermediate findings as `partial`, audit them normally, and never represent them as a complete Pro review.

A `complete` consultation requires:

- Chat mode was visibly selected for the conversation;
- GPT-6 Pro was visibly selected and verified at send time;
- the GitHub connector was visibly attached;
- Pro used or explicitly acknowledged the exact GitHub baseline commit and did not report `CONTEXT_BLOCKED`;
- the answer addresses the requested deliverable with repository-grounded evidence; and
- any local overlay was clearly distinguished from the baseline.

Return:

1. the `complete`, `partial`, or `failed` status and failure stage when applicable;
2. the complete or partial Pro recommendation, faithfully summarized without reconstructing missing output;
3. Codex's repository-grounded audit, including agreements, corrections, unsupported claims, and material caveats;
4. the exact commit and any local overlay used or attempted;
5. unresolved decisions that genuinely require the user; and
6. the ChatGPT chat left open in the selected browser as the deliverable.

Do not imply that Pro inspected files or a commit unless the response provides evidence it did. Keep implementation responsibility with the active Codex task unless the user asks for a different handoff.

## Failure Handling

- **Project missing:** Ask before creating a replacement Project; do not create similarly named duplicates.
- **Wrong product mode:** If the interface shows Work mode, Codex, or another non-Chat surface, stop and do not send until Chat mode is visibly selected.
- **Signed out or connector unauthorized:** Pause for the user to complete authentication or repository authorization.
- **Exact commit inaccessible:** Retry once with the full repository name and SHA. If it remains inaccessible, return `failed` with the missing baseline; never replace the baseline with a standalone packet.
- **GPT-6 Pro unavailable:** Return `failed` with the limitation and never silently substitute another model or reasoning level.
- **Visible response error:** Click the visible `Retry`/`Retry response` control once when available and monitor that request. If retry is unavailable or also fails, do not loop or consume follow-ups merely to recover from a provider error. Preserve and audit any visible repository-grounded intermediate findings as `partial`; otherwise return `failed`. In both cases, return control to the caller so its primary task can continue from local evidence.
- **Response is generic or based on the wrong revision:** Supply the missing path/SHA evidence in one focused follow-up; otherwise report the failed consultation rather than presenting it as grounded advice.
- **Browser UI changed:** Reinspect visible semantic state and follow the Browser skill. Never guess selectors from stale UI.
