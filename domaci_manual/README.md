# Domácí manuál

Your household documentation, in Home Assistant.

Point this app at a private Git repository of Markdown files — heating, water,
electricity, the network, whatever you need to remember — and it renders them
as a searchable, mobile-friendly documentation site in the Home Assistant
sidebar. It works remotely through Nabu Casa, and everyone in the household can
read it, not just administrators.

The documentation repository stays a plain Markdown knowledge base: no MkDocs
files, no front matter, no special layout. It remains perfectly readable in
GitHub, Obsidian or any other Markdown editor.

Access to GitHub is **read-only**: the app generates its own SSH key and you
register it as a read-only deploy key. It never writes to your repository.

See the Documentation tab for setup instructions.
