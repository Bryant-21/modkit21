# Quest Papyrus coverage

`modkit esp quest-papyrus` produces a supported, read-only inventory from plugins
and complete PSC sources. It does not require a quest-name prefix, a database
export, or a separate CSV-building script.

```powershell
modkit.exe --game fo4 --output quest-audit.json esp quest-papyrus B21_Example.esp B21_MainQuest --source-root stock-source --source-root generated-source --source-root merged-source --generated-source-root generated-source --asset-root Data --fail-on-incomplete
```

Quest selectors accept EditorIDs, hexadecimal FormIDs and `Plugin:LocalID` keys.
Several selectors share the plugin, reverse-reference and source indexes.
`--master-search-path` and a read-only `--load-order` file select plugin resolution.
Later plugins win overrides; stale references from overridden records are excluded.

## Sources and output resolution

Supply source roots in increasing priority: stock imports, generated sources,
then merged repair sources. A script named `B21:QuestController` resolves to
`B21/QuestController.psc` under each root. The last root wins. All candidates and
the winning path are reported. Duplicate names within one root are ambiguous.

The command expects **complete, already-merged PSC files**. It validates their
`Scriptname` declarations and uses the native Papyrus parser, including named
states, inherited members and property accessors. Method-only repair patches
are not full source files; stage them through the conversion workflow first.
This command neither merges patches nor changes generated mod files.

PEX resolution uses the same `--asset-root` and `--archive` options as
`esp explain`: loose files precede archives, and later roots/archives win within
each category. Without asset options, the plugin directory and its `data`
directory are searched. Installed game archives are not assumed to be present.

## Report contract (schema version 1)

The default `data` array has one report per requested root quest. A report contains:

| Field | Evidence |
| --- | --- |
| `records`, `edges` | Winning record identity and the reason each record or script entered the closure. |
| `scripts` | Source path, SHA-256, parse errors, parent/import/type/static-call dependencies, member bodies and property declarations. |
| `bindings` | VMAD record/alias/fragment context, inherited implementations, callbacks and property use sites. Fragment rows share their container's property bindings. |
| `quests` | Ordered stages and stage items for every quest reached. Includes flags, notes, retained SCFC source, conditions, exact VMAD callback names/bodies, and incoming stage producers. |
| `stage_producers` | `SetStage`/`SetCurrentStageID` source call sites and native SCQS/TIQS stage setters. Source calls retain member, state, path, line and expression. Helper calls without a known script instance have a null binding path. |
| `issues`, `limits` | Missing records, incomplete VMAD decoding, unmatched callbacks, undecoded stages, dynamic form lookups, and pending work when a limit is reached. |
| `freshness` | Counts of source comparisons and PEX status; detailed hashes and paths are on each script. |

Callback statuses distinguish `covered`, `empty`, `missing` and
`incomplete_source`. A member marked `implemented` has parsed statements; this
does not establish that those statements implement the intended quest behavior.
Native declarations are identified separately. An empty derived script can have
working inherited behavior. Property coverage distinguishes declared/used,
declared/unused and undeclared bindings, and records source-only properties too.

Stage producers resolve literal arguments, initial VMAD/default property values,
immutable local initializers, self/parent quests, owning quests, alias quest
objects, and literal `Game.GetFormFromFile` calls. A resolved initial value is
not a claim that the property never changes. Unknown receivers, runtime values
and targets that do not resolve to QUST remain unresolved. It also checks whether
a resolved stage exists on an inspected quest (`missing_stage` when absent).
`target_stage_declared` is null when the target stage inventory is unavailable.
The report inventories potential call sites; it does not prove they execute or
analyze call conditions.

Stage items are matched by the VMAD stage number **and item index**, never by
guessing a function name. A stage without a callback remains in the inventory.
SCFC text is retained as designer evidence, not treated as executable merged PSC.

## Closure and completeness

The static closure follows all schema-known forward record references, reverse
references to each reached QUST (including decoded VMAD objects), DIAL child INFO
groups, and source parent/import/type/static-call dependencies. Literal source
form lookups feed back into the record walk. Cycles terminate by identity. This
can reach other quests, generic scripts and records with unrelated EditorIDs.
It does not traverse every reverse reference to every non-quest record or model
the engine's dynamic discovery of world objects and event recipients.

Reverse VMAD indexing and dialogue traversal require fully loaded plugins. The
global VMAD scan occurs once per invocation, even with small per-quest limits.
An undecodable VMAD anywhere in that scan makes reverse-attachment completeness
unknown; the affected record is named in `REVERSE_VMAD_INCOMPLETE`.

`completeness` separates records, sources, callbacks, property declarations and
stage-target resolution. `complete` is their conjunction **for this static
scope**. It is independent of output freshness and runtime correctness. There
is no proof of arbitrary dynamic dispatch, interprocedural value flow, native
implementation behavior, alias fill success, stage reachability or save recovery.

`--max-records` and `--max-scripts` default to 10,000 per quest. Zero removes the
corresponding limit. Limits leave an explicit pending inventory and an incomplete
result. Missing records count as attempted records against the record limit.
`--fail-on-incomplete` exits 1 after emitting the report. It always evaluates
all requested quests before display filtering or pagination.

## Freshness means evidence, not an inferred rebuild

`--generated-source-root` compares generated PSC bytes with selected merged PSC
bytes: `identical`, `different`, `missing` or `ambiguous`. It does not compare
modification times to infer content equality.

PEX status is `missing`, `unreadable`, `older_than_source`, or `unverified`.
Available PEX files carry a SHA-256; loose outputs also carry timestamps. A newer
PEX or an archive member remains **unverified** because neither establishes which
source produced it. `bytecode_matches_source` remains `unverified`; compiler
verification and runtime tests are separate operations.

## Focused queries

Global report options precede `esp`. `--items` flattens an inventory across root
quests while keeping `root_quest` on each row.

```powershell
# Empty VMAD callbacks, with complete metadata retained after filtering.
modkit.exe --items bindings --where callback_status=empty --fields root_quest,record,script,fragment,callbacks esp quest-papyrus B21_Example.esp B21_MainQuest --source-root merged-source

# Every conditional item of a particular stage.
modkit.exe --items stages --where stage=1900 esp quest-papyrus B21_Example.esp B21_MainQuest --source-root merged-source

# Unresolved stage-producing call sites.
modkit.exe --items stage_producers --where status=unresolved esp quest-papyrus B21_Example.esp B21_MainQuest --source-root merged-source

# Summary without suppressing audit work or changing completeness.
modkit.exe --fields quest,counts,completeness,freshness esp quest-papyrus B21_Example.esp B21_MainQuest --source-root merged-source
```

Other `--items` values are `scripts`, `records`, `edges` and `issues`. JSON, JSONL,
table output, `--output`, predicates, projection, grouping and pagination use the
normal CLI report machinery. The output path cannot overwrite inspected plugins,
PSC files or resolved script assets.

## Brotherhood validation

The September 15, 2026 integration run used all 14 requested Brotherhood roots,
stock FO4 sources, converted sources, the 100 staged merged repair sources, and
200 attempted records per root. It recovered all **813 root stage entries and
686 root stage callbacks**. All five Conscience stage 1900 items matched their
individual callback bodies. All 686 root callbacks matched supplied source.
The run correctly remained incomplete due to traversal limits and unresolved
references/VMADs. It does not certify the Brotherhood repairs or deployment.
