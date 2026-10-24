# Verification evidence archive

This directory contains dated audits, benchmark outputs, reconciliation reports,
and cutover evidence. These files document how particular releases were checked;
they are not current architecture or onboarding instructions.

Use these sources for current work:

1. `..\ark_nova_dashboard_handoff.md`
2. `C:\Users\ascri\Desktop\ark-nova-function\README.md`
3. `C:\Users\ascri\Desktop\ark-nova-function\contracts\dashboard-routes.v1.json`
4. the relevant page module and backend route adapter

Evidence files may contain phase/increment terminology, superseded generation
IDs, historical timings, or then-current deployment state. Do not copy those
statements into active documentation without re-verifying them against the
current code and production configuration.

Keep machine-readable evidence immutable when a test pins its hash. Add a new
report for a new release rather than rewriting evidence used by a regression
gate.
