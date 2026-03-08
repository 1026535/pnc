# BotBattle AGENTS Guidelines

## Coding
- Make minimal, well-reasoned changes. Avoid duplicating existing code or logic.
- When new requirements arrive, do not patch a now-wrong design with more code. Re-evaluate the design and refactor so the result stays minimal, DRY, and easy to maintain.
- Prefer using existing, authoritative interfaces instead of reimplementing behavior.
- Prioritize clarity, documentation, and maintainability;
- Avoid duplicating logic / re-hardcoding logic at ALL COST.
- Always first make sure everything makes sense and that you have a very deep understanding of the intricacies of the context. Take time to analyze the codebase and current architecture. Take time to make sure we have a very clean and logical solution, with DRY code and a clean architecture, that integrates well with the current designs.
- Throw on unexpected conditions: do not silently swallow exceptions or ignore unexpected inputs—prefer throwing or asserting so issues surface during development and testing.

## General Architecture Requirements
1. Single canonical implementation per concept.
2. No duplicated logic (DRY).
3. Open-Closed extension model.
4. Fail-fast validation for invalid content.
5. Minimal boilerplate and complexity.
6. Strong types are preferred

## Documentation Requirements
- Add XML documentation for every class and function we add or modify, including private helpers when they contain meaningful logic.
- Keep documentation high value and concise: explain responsibility, important interactions/ownership, non-obvious behavior, invariants, and relevant limitations.
- Add brief in-code comments for complex logic when the intent or constraint would not be obvious from the code and XML docs alone.
- Do not write comments that only restate the signature.

## Non-negotiables (MUST)
- MUST avoid duplicating logic: no “same concept, different place” helpers.
- MUST refactor when requirements shift responsibilities (ownership changes).
- MUST delete obsolete code after refactors; do not keep parallel APIs.
- MUST fail fast on unexpected conditions; do not silently swallow invalid states.
- MUST prefer porting everything to the current format and never add support for old legacy code/serializations; update scenes/assets as needed so all data uses the latest schema.

## Project Overview
- Work happens in **BotBattleV2** only.
	- The legacy project at `E:\Thomas\Prog\Games\BotBattle\BotBattle` (old TBS framework) exists for **read-only reference** when comparing behaviors or older tooling.
- Unity project using Turn-Based Strategy (TBS) Framework
	- TBS docs: https://github.com/mzetkowski/tbsf-unity-docs
- Core framework scripts under `Assets/TBSFramework/Scripts`. Avoid modifying framework code; it may be overwritten on framework upgrades.
- Game-specific code lives under `Assets/BotBattle` and is structured by asset type (Art/Scripts/Prefabs/etc) then by feature (Units/Tiles/etc.)

## Coding Style
- C# code uses 4 spaces indentation and UTF-8 BOM encoding as per `.editorconfig`
- Non-public instance fields use `m_` prefix (see `.editorconfig`)
- Place `using` directives at the top and sort System first
- Favour `var` for built-in and apparent types
- Keep methods concise and document with XML comments when appropriate
- Prefer concise expression style across the codebase (for example, use short single-line `if`/`return` and compact expressions when clear), favoring readability and brevity.
- Prefer compact conditional blocks for simple cases: `if (cond) return;`, `if (cond) throw ...;`, `if (cond) DoThing(); else DoOther();` (keep braces for multi-line blocks).
- Prefer enums over hard-coded strings for identifiers (abilities, behaviour trees, etc.) whenever practical.
- Do not implement heuristics that guess or probe for multiple field/property names. Always determine and use the precise, intended symbol name or a well-defined interface. Avoid adding code that attempts multiple possible names - this increases complexity and hides intent.
- Avoid the null-forgiving operator (`!`) in Core code. If a value can be null, guard it explicitly (e.g., `if (AssertUtil.AssertIfNull(value)) return;`) or assert+throw; never silently continue without at least an assert.
- Prefer using established libraries over reimplementing low-level logic, but always verify the APIs exist in Unity's .NET compatibility level.
- Do not edit `.csproj` files under `Assets/` (Unity-owned). Editing external test projects like `Tests/CoreTests/CoreTests.csproj` is OK.

## Development Tips
- Prefabs and assets live under `Assets` and use `.meta` files tracked by Git
- Scripts compile dotnet build; Unity DLL references come from Directory.Build.props.
- We do not indent code inside namespace declarations. Always keep namespace braces at column 0 (e.g., files end with } on its own line).  CODEX often assumes indented namespaces and will omit a } if this style isn’t followed.
- Unity test/editor runs can auto-generate workspace changes (`BotBattle.Core.csproj`, `BotBattle.Simulation.csproj`, `BotBattleV2.sln`, and folder `.meta` files under `Assets/...`). Treat these as expected generated changes, not blockers.
- If unrelated workspace changes already exist, continue the requested task and do not stop for those changes; never revert unrelated files unless the user explicitly asks.

## Testing
- Automated tests exist, CoreTests must be runnable headless (no Unity dependencies).
- Standard Unity test execution (use this by default):
  - Always use `Tools/run-unity-editmode-tests.ps1` unless you are explicitly debugging the runner script itself.
  - This runner is the canonical path for Unity EditMode tests in this repository.
  - To avoid focus-stealing console flashes, invoke scripts in the current PowerShell session with the call operator (`& Tools/run-unity-editmode-tests.ps1 ...`) instead of spawning a nested host via `pwsh Tools/...`.
- Unity runner commands:
  - Full suite: `pwsh Tools/run-unity-editmode-tests.ps1`
  - Targeted test (fast): `pwsh Tools/run-unity-editmode-tests.ps1 -TestFilter "BotBattle.Tests.Unity.PerformanceDiagnosticsUnityTests.GigaBattle_PerformanceDiagnostics_HeroesWinWithoutLosses" -RunTimeoutSeconds 30`
- Use targeted runs when explicitly debugging one test; use full-suite runs for final validation.
- `-SkipWarmup` is only for repeat runs after a successful warm-up in the same environment. If no XML is produced, rerun without `-SkipWarmup`.
- If `$Env:UNITY_EDITOR` contains a placeholder path (for example `<version>`), resolve the executable from `ProjectSettings/ProjectVersion.txt` and run that exact editor version.

### Unity test failure handling (required)
- Treat the runner output (`RESULT: ...`) and `TestResults/editmode.xml` as the authoritative pass/fail source.
- For test failures, read per-test message + stack trace + output from `TestResults/editmode.xml`, then use `TestResults/editmode.log` for surrounding context.
- If no XML is produced, treat it as compile/runner failure and use compiler errors extracted from `TestResults/editmode.log` (the runner script already does this).
- If a run exits too quickly or looks stale, verify no background `Unity.exe` is still attached to this project, then rerun without `-SkipWarmup`.

### Validation workflow (required)
- **Fast structural check (Unity assemblies):** run `pwsh Tools/validate-asmdefs.ps1`.
	- This catches missing/invalid `.asmdef` references (a common source of Unity compile errors) that VS Code / Roslyn error lists may not surface reliably.
- **Pure C# headless tests (no Unity editor):** run `dotnet test Tests/CoreTests/CoreTests.csproj`.
	- This compiles the *same* simulation + framework-common source files (linked, not copied) and runs NUnit tests directly.
- **Core build check:** run `dotnet build BotBattle.Core.csproj` to mirror Rider/Unity project compilation and catch missing assembly references.
- **Core dependency sanity check:** when touching `Assets/BotBattle/Scripts/Core`, ensure no Unity-only namespaces or APIs are referenced and run the CoreTests to catch missing assemblies early.
- **Unity API compatibility:** Core targets Unity's .NET Standard profile; avoid APIs that only exist in newer .NET runtimes (e.g., `System.Text.Json`, `Convert.ToHexString`) unless verified as available in Unity.
- **Adding external libs (Core):** import the plugin DLL into Unity by placing it under `Assets/Plugins/` (Unity creates a `PluginImporter` `.meta`), reference it via `overrideReferences` + `precompiledReferences` in the Core `.asmdef`, add the matching NuGet package in `Tests/CoreTests/CoreTests.csproj`, then run CoreTests. Example: for Newtonsoft.Json, place `Assets/Plugins/Newtonsoft.Json.dll` and add `Newtonsoft.Json` to CoreTests.

### Notes
- The VS Code Problems view (and the `get_errors` tool) can miss Unity-specific issues (e.g., `.asmdef` reference graph problems) because Unity’s compilation pipeline isn’t the same as the .NET SDK pipeline.
- Unity EditMode tests can still be run in batchmode if needed, but our default goal is: **tests run via `dotnet test` without launching Unity**.
  For Unity runs, use `pwsh Tools/run-unity-editmode-tests.ps1` and inspect both editmode.log and editmode.xml; editmode.xml remains authoritative for pass/fail.

## DRY enforcement checklist (required)

Before you finish:
- Confirm there is exactly one canonical implementation per concept.
- Confirm there are no duplicated predicates/formatters/parsers.
- Confirm obsolete code paths/interfaces were removed.
- Confirm naming reflects ownership (policy vs consumer).
