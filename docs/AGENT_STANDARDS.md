# GROKBOT COMMERCE — Agent & Workflow Standards

Standards every agent and workflow specification must follow. These keep the
system modular, auditable, and safe.

## Agent specification standards

An agent spec is a YAML file in `src/grokbot/specs/agents/` that validates
against `agent_spec.schema.json`.

Required fields: `id`, `name`, `version`, `role`, `division`, `status`,
`description`, `default_permission`, `inputs`, `outputs`.

Rules:

1. **Stable id.** Lowercase `^[a-z][a-z0-9_-]*$`, unique across the registry.
2. **Structured I/O.** Declare `inputs` and `outputs` as typed fields so other
   agents can consume outputs deterministically. Use `consumes_from` to name the
   upstream agents whose outputs this agent reads.
3. **Correct permission.** Set `default_permission` to the class of this agent's
   primary action. Drafting/research is `AUTONOMOUS`; anything that publishes,
   spends, commits to suppliers, launches, or messages customers is
   `APPROVAL_REQUIRED`.
4. **Evidence discipline.** List `evidence_requirements`. Outputs must preserve
   sources; facts that cannot be sourced stay **UNKNOWN**. Never fabricate.
5. **Escalation.** List `escalation_triggers` for conditions that must go to the
   human owner (insufficient evidence, disputes, refunds, IP risk, anomalies).
6. **Lifecycle.** Use `status`: `planned` (no behavior yet), `draft`, `active`,
   `deprecated`. Foundation-phase agents are `planned` or `draft`.

## Workflow specification standards

A workflow spec is a YAML file in `src/grokbot/specs/workflows/` that validates
against `workflow_spec.schema.json`.

Rules:

1. **DAG integrity.** Stage ids are unique; `depends_on` must reference existing
   stages; the graph must be acyclic. The loader enforces all three.
2. **Stage types.**
   - `action` — requires an `agent` and a `permission` class.
   - `validation_gate` — requires `validation.criteria` and an `on_fail` policy
     (`halt`, `request_more_research`, `escalate`, `reject`).
   - `approval_gate` — requires `approval.approver: human_owner` and a
     `description`.
3. **Gate placement.** Put a validation gate after research/validation stages to
   stop bad opportunities early. Put an approval gate before any material
   external action (e.g. building/launching a store).
4. **Structured hand-off.** Use `produces` to name the outputs a stage passes
   downstream.

## Output standards (structured, sourced, honest)

- Prefer structured objects/arrays over free text so downstream agents can parse
  them.
- Attach sources to any claim where practical. Represent unverified values as
  `UNKNOWN` in project state (`ProjectState.record_evidence` enforces that
  `verified` requires a source).
- Never assert legal conclusions, completed external actions, or fabricated
  figures.

## Before you commit

Run the control-system checks locally:

```bash
grokbot validate        # schema + cross-reference validation, no external actions
python -m pytest        # full test suite
```

Both must pass. `grokbot validate` also confirms every agent referenced by a
workflow exists in the registry.
