---
name: consult-chatgpt-pro
description: Consult ChatGPT Pro in Chat mode with GPT-6 Pro using a verified GitHub commit and minimal local context. Use only for an explicit Pro request or when create-plan-with-chatgpt-pro routes here.
---

# Consult ChatGPT Pro

Obtain a repository-grounded second opinion without publishing local work or sending unnecessary context.

## Boundaries

- The explicit request or planning-skill route authorizes one consultation message and ordinary setup. Do not ask again before sending once the checks below pass.
- Use Chat mode with GPT-6 Pro. Do not substitute Work, Codex mode, the API, another model, or a generic Pro label.
- Keep GitHub and other connected systems read-only. Do not commit, push, share, install/connect plugins, change settings, or create a replacement Project without separate authorization.
- Never send credentials, personal data, unrelated repository content, generated output, or proprietary third-party material.
- If sensitive local-only content is essential, show what would be sent and obtain confirmation before upload.

Read [the shared browser-session instructions](../../../instructions/chatgpt-web-browser-session.md) before browser work. They own browser selection, authentication handoff, tab recovery, and cleanup.

## Repository Context

1. Record the repository, branch, upstream, full `HEAD` SHA, status, and the smallest relevant paths.
2. Verify that the chosen commit is accessible on GitHub. Prefer `HEAD`; otherwise use a verified upstream ancestor plus a local overlay.
3. If an overlay is needed, create one temporary Markdown packet outside the repository containing only relevant diffs, new-file excerpts, and facts unavailable at the baseline. Review it before upload and remove it afterward.
4. If no suitable GitHub baseline is accessible, stop and ask how the user wants to expose one. Do not upload the repository as a substitute.

## Consultation

1. Reuse the existing ChatGPT PNC Project and start a fresh chat for a new objective.
2. Verify Chat mode and GPT-6 Pro before composing.
3. Send a concise prompt with the exact repository and commit, objective, relevant paths, hard constraints, and decision questions. Ask Pro to distinguish repository facts from inference and report inaccessible context.
4. Attach the reviewed overlay only when needed, then attach GitHub last. Verify the final prompt, model, commit, connector, and attachment once; send once.
5. Monitor with lightweight semantic checks. Do not duplicate the chat or submission because a response is slow. Use one visible Retry for a provider error and at most two focused follow-ups for missing context or the requested deliverable.

If authentication, the PNC Project, GitHub access, or GPT-6 Pro is unavailable, report the limitation rather than substituting another workflow.

## Audit And Return

Check the response against the local repository and task. Classify it:

- `complete`: the exact commit was acknowledged and the requested grounded deliverable was produced;
- `partial`: useful grounded output exists but the response was interrupted or incomplete;
- `failed`: required context or a trustworthy grounded recommendation is missing.

Return the status, a faithful summary, Codex's corrections or caveats, the commit and overlay used, and material unresolved decisions. Do not imply that Pro inspected a file or revision without evidence. Leave the consultation chat open as the deliverable.
