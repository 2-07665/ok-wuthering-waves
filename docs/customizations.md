# Local customizations on top of upstream ok-ww

- **Task tweaks**: `src/task/BaseWWTask.use_stamina` accepts `prefer_single` to force single-spend. `src/task/TacetTask` adds budget-related config keys and stops once the configured stamina has been consumed.

Keep these diffs in mind when pulling upstream updates.


# Codes managed by AI without human review

- **Log filter**: `custom/log_filter`

- **Fast farm 4C task**: `custom/task/my_FastFarmEchoTask`

# To-do list

- Rebuild email sender.