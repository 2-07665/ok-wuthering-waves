# Local customizations on top of upstream ok-ww

- **Task tweaks**: `src/task/BaseWWTask.use_stamina` accepts `prefer_single` to force single-spend. `src/task/TacetTask` adds budget-related config keys and stops once the configured stamina has been consumed.

Keep these diffs in mind when pulling upstream updates.


# Codes managed by AI

- **Log filter**: `custom/log_filter`

- **Official API**: `custom/waves_api` adapted from WutheringWavesUID

- **Email**: `custom/email_sender` send run results via mailgun api

- **Fast farm 4C task**: `custom/task/my_FastFarmEchoTask`