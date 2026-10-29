# Read-only readiness guide access

The stopped-maintenance classifier omitted `references/readiness.md` from its named document list. Both `maintenance.py ... docs --name readiness` and an exact installed-file `cat` were rejected. This patch adds the existing guide to that list and extends the instruction-read regression.

The change adds no executable maintenance verb. In particular, `readiness.py retry-preservation` remains outside the exception. It does not resume tasks, change ownership, alter reserve percentages, register hooks, or change native permissions.

Validation:

- All 13 focused maintenance tests passed, including instruction access, stopping/resumption, shell/path rejection, and ownership boundaries. The added explicit named-document and mutating-retry assertions are included in the final run.
- Eight checks against the installed classifier passed: readiness reads by normal and native command names are allowed; the existing reserve guide remains allowed; foreign paths, shell chains, wrong roots, and mutating retry remain denied.
- A direct installed-hook subprocess callback denied ordinary work, allowed the readiness read, retained the verified stop unchanged, and left ownership vacant. This is callback evidence, not native tool delivery.
- The native smoke test did not observe checkpoint interception: discovery found no checkpoint hook registered in the isolated fixture. The ordinary marker was created, so this is not counted as a native stopped-work pass. No hook was registered or trusted to compensate.
- The native CLI automatically added a temporary project trust entry. Only that fixture entry was removed, and the original configuration bytes were verified restored. Hook definitions were unchanged. No trust or permission change was retained.

The patch is committed on the existing public version line. It does not bundle unrelated local development changes or claim a new complete runtime release. Full native stopped-work confirmation requires a separately authorized, registered checkpoint fixture. A full owner-aware preservation-retry repair remains separate.
