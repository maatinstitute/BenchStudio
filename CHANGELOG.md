# Changelog

## 0.1.0rc2 — unpublished cleanup candidate

- Define one 15-name supported root API and require direct module imports for specialist utilities.
- Remove dynamic root and integration re-exports, provider-specific checkpoint loading, task/CLI aliases, and the legacy process wrapper.
- Keep native inference configuration with the system owner; BenchStudio adds no provider defaults.
- Use one EvaluationConfig for engine settings and one result inspector for offline and native records.
- Require explicit dashboard study definitions; remove invented fallback studies.
- Update current examples and docs to the canonical Python, module-import, and CLI entry points.

The package and repository remain private and unpublished. No simulator, GPU, learned model, native qualification, or scientific confirmation was run for this cleanup.
