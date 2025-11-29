# Local customizations on top of upstream ok-ww

- **Sheets/reporting**: `GoogleSheetClient.append_run_result` writes to `DailyRuns`/`StaminaRuns` with dedicated schemas (start stamina, daily points or projected daily stamina, decision/error). Sheet config reads tacet name/sets (not overflow flags).
- **Mailgun email**: email delivery uses the templated HTML at `templates/mailgun_run_summary.html` via `mailgun_send.py` with JSON variables; plain text fallback is still sent for robustness.
- **Stamina safety**: `auto_stamina.py` captures live stamina, projects stamina to the next daily window (configurable time placeholder), runs only if the projection exceeds 240, and burns down toward ~180 using single-spend Tacet runs (`Max Stamina to Spend`, `Prefer Single Spend`). Projected stamina is recorded to Sheets/email.
- **Task tweaks**: `src/task/BaseWWTask.use_stamina` accepts `prefer_single` to force single-spend when budgets are tight. `src/task/TacetTask` adds budget-related config keys and stops once the configured stamina has been consumed.

Keep these diffs in mind when pulling upstream updates.
