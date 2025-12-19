# Local customizations on top of upstream ok-ww

- **Task tweaks**: `src/task/BaseWWTask.use_stamina` accepts `prefer_single` to force single-spend. `src/task/TacetTask` adds budget-related config keys and stops once the configured stamina has been consumed.

Keep these diffs in mind when pulling upstream updates.


# Codes managed by AI without human review

- **Auto login**: `custom/task/my_LoginTask`

- **Log filter**: `custom/log_filter`

- **Fast farm 4C task**: `custom/task/my_FastFarmEchoTask`

- **Auto 5 to 1 task**: `custom/task/my_FiveToOneTask`


# To-do list

- Rebuild email sender.