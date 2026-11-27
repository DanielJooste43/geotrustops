# Security policy

## Reporting a vulnerability

Please report security problems **privately**, through GitHub's private vulnerability reporting: on this
repository, open **Security → Report a vulnerability**. Do not open a public issue for a security problem.

Include what you found, how to reproduce it, and what it could affect. You will get an acknowledgement within
seven days, and a fix or a decision with its reason as soon as the problem is understood.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x (latest release) | yes |
| earlier releases | no: upgrade to the latest release |

## Scope

In scope:
- the pipeline (`src/geotrustops/`) and its handling of downloaded files, configuration and SQL;
- the web map (`web/`), including how it reads and displays the published files;
- the GitHub Actions workflows (`.github/workflows/`), their permissions and the secrets they use, including the
  token that restores pinned extracts from the private archive;
- anything in the repository or its history that exposes a secret or personal data.

Out of scope: Overture Maps data itself (report data issues to Overture), and the third-party basemap and tile
services the web map loads.

## How the project protects itself

Secret scanning and push protection are enabled; dependency alerts are on; workflow actions are pinned by commit;
dependencies are pinned exactly; and the archive token is read only from the environment and is never sent on a
redirect or written to a message.
