# Handoff

**Next unfinished action: {{next_action.description}}**
Verify first: {{next_action.verification}}

Objective and definition of done: {{objective}} / {{completion_criteria}}
Checkpoint identity, timestamp, trigger: {{checkpoint_id}} / {{created_at}} / {{trigger}}
Project/task/repository identity and branch/commit: {{project_id}} / {{task_id}} / {{repository}}
Current user scope and corrections: {{authorization}} / {{scope}} / {{corrections}}

## Progress and evidence
{{completed}} / {{actual_test_commands_results_failures_and_unrun_checks}}

## Changed and preserved files
{{added_modified_deleted_staged_unstaged_untracked_files_and_binary_backups}}

## Decisions, blockers, prerequisites
{{decisions_with_reasons}} / {{issues_dependencies_questions}} / {{tools_environment_credentials_provisioned_separately}}

## Active work and next steps
{{jobs_external_operation_ids_and_uncertain_outcomes}}
{{ordered_next_steps_and_expected_results}}

## Transfer and receiving-agent prompt
{{source_history_dirty_snapshots_manifest_exports_path_mappings_and_known_gaps}}
Copy the prompt in resume-prompt.template.md. Transfer actual required files and verified source history together with checkpoint artifacts; HANDOFF.md alone is insufficient. Verify integrity, current permissions and exclusive ownership before continuing.
