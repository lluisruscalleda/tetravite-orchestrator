# Security limitations — read before running

**Not a sandbox, not suitable for untrusted packages or untrusted workflow authors.** The orchestrator delegates to `tetravite-runtime`, which launches Python subprocesses with the privileges and network access of the current OS user. `--allow-execution` is an operator acknowledgment, not isolation. A malicious package can read files, access credentials, open sockets or execute programs. ZIP checks are not a security boundary.

The local registry explicitly maps aliases to paths; do not load arbitrary remote packages. Restrict who can edit the registry, workflows, ZIPs and installed dependencies. Run inside a dedicated container or VM with OS-level network policies, filesystem restrictions, resource quotas, timeouts, and no credentials. Verify package provenance and signatures before execution. The reference runtime limits elapsed time but does not bound process memory or streaming output reliably. Do not run this PoC as a publicly exposed multi-tenant service.

No LLM is called by the orchestrator; individual trusted Tetravites may use models if explicitly implemented. No prompt or model output can authorize additional code execution in this PoC.
