# Changelog

## 0.2.0

- New `exclude` option: gitignore-style patterns for files and folders to keep
  out of the published site. Excluded pages are neither linkable nor
  searchable.
- A build that would produce no landing page now fails with an explanation
  instead of serving a 404 at the ingress entry point.
- Editing an option that affects the output now rebuilds on the next sync,
  instead of waiting for the next commit in the documentation repository.

## 0.1.0

First release.

- Renders a Git repository of Markdown files as a MkDocs Material site.
- Home Assistant ingress with a sidebar entry, available to non-admin users.
- Read-only Git synchronisation over SSH with a self-generated deploy key.
- Periodic upstream checks, rebuilding only when the repository changed.
- Status page with the public deploy key and actionable error messages.
