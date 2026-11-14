# Workflow format (experimental)

`apiVersion: tetravite.dev/workflow/v1alpha1` and `kind: Workflow` identify a **new proposed** workflow document. This is separate from the existing `tetravite.dev/v1alpha1` Tool manifest.

Required fields: `steps` (1–32 unique IDs, each with `id`, `uses`, and object-valued `with`) and `output` (JSON value). Optional `metadata.name` and `inputSchema` (relative JSON Schema path). Each `uses` value refers to an alias in a **local, explicit registry JSON file**, not to a remote URL.

References must occupy the **entire JSON string**: `${input.name}`, `${steps.first.result.greeting}`. Array indices may be addressed as numeric path components. References are resolved as values (preserving types); embedded string interpolation, conditions, loops, retries, dynamic agent selection, and arbitrary expressions are intentionally unsupported. Dependencies are inferred from references and executed in topological order. Cycles and unknown steps fail validation. Step errors stop the workflow; no rollback is attempted.

The output envelope is `{status, workflow, steps, result}`. Step results are available internally as the runtime envelope `{status, package, version, result}`. Intermediate full results are not returned in the final response unless explicitly selected in `output`.
