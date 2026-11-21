# ASUFC Finance roadmap

| Phase | Status and acceptance criteria |
| --- | --- |
| Public Pages | The dedicated workflow builds a fictional demo and deploys only the compiled bundle. Verify the current artifact at the public URL in Chromium, including demo entry, seed balances, the expense flow, reload reset, console errors and backend isolation. |
| Repository review | Review each source, test, deployment and documentation file. Record evidence, resolve verified regressions and review dependency locks, reproducible builds and configuration consistency. |
| Staff interface | The private development profile and overview are implemented. Continue improving financial forms, tables and error recovery. Expand keyboard and responsive verification across screens. |
| Receipt files | Staff-only image and PDF storage, duplicate detection, replacement history and encrypted recovery are implemented. Confirm the institution's retention policy before using real records. |
| Financial analysis | The Financial insights page uses scoped, deterministic ledger queries for spending, budgets, funding and alerts. |
| AI assistant and extraction | The offline assistant classifies common questions locally and uses authorized ledger calculations. It offers topic selection if a question is unclear. Receipt extraction and external model access remain separate milestones. |
| Forecasts | A labeled next-month estimate uses six consecutive complete months of recorded spending, or shows why an estimate is unavailable. |
| Release verification and documentation | The university handover, diagrams, staff manual and presentation are under `docs/`. Record current CI and onsite acceptance evidence before handover. |
| Offline distribution | The workflow builds Windows, macOS and Linux artifacts and tests the runtime they ship. Encrypted backup and fresh-profile recovery are implemented. Complete institutional signing and the designated computer's disconnected installation, upgrade and recovery drill. |
| Production | Obtain stakeholder approval for hosting, institutional access, policy and key custody. Verify the authorized environment and recovery before opening staff access. |

Keep source-specific grant terms and unconfirmed academic reporting cutoffs explicit. Receipt retention, live record migration and third-party data processing require separate decisions.
