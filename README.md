# Docker Compose Plus

*Docker compose + jsonnet + environments*

Docker compose is a great method for deploying software stacks (collections of services packaged as docker containers). However, using it in a production setting has a few pitfalls. Specifically:

 - **Swarm vs compose fields:** Docker swarm has a few different fields than docker compose
 - **YAML is too primitive:** Avoiding repeated definitions and brittle env setups require multiple overlayed configs resulting in long compose commands like `docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev -p my-app-dev ...`

Docker compose plus is a simple wrapper around `docker-compose` that solves these issues by allowing definitions defined using jsonnet. It works as follows:

 - Your `docker-compose.libsonnet` defines a function, `MyAppDeployment(envOne, envTwo="foo"): {...}`
 - Your `.env.dev.jsonnet` / `.env.prod.jsonnet` imports this function and materializes it by providing actual secrets and env arg values

## Usage

`dcp dev|prod ...` is the same as `docker compose`, loading vars from `.env.dev.jsonnet` or `.env.prod.jsonnet`.

*Special case: Deploy is equivalent to `docker stack deploy`*

Compose project names use `<folder>-<env>`. The folder name is lowercased,
characters other than ASCII letters, digits, underscores, and hyphens are removed,
and leading underscores and hyphens are stripped. For example,
`.foo_worktree-1/` becomes `foo_worktree-1-dev` for `dcp dev`.
Already-valid folder names are unchanged; names that normalize to an empty string
are rejected. Swarm deployment uses the same normalized folder name without the
environment suffix.

Different folders can normalize to the same project name (for example, `.foo`
and `foo`), so use distinct normalized folder names for independent stacks.

### Definitions

Define `docker-compose.libsonnet`:

> [!TIP]
> You can make this definition even simpler using [docker-compose-jsonnet](https://github.com/MatthewScholefield/docker-compose-jsonnet)

```jsonnet
local useSwarm = std.extVar('useSwarm');

local DeploymentConfig(config) = if useSwarm then config else {};

{
  MyAppDeployment(env): {
    version: '3.8',
    services: {
      'mongo': {
        image: 'mongo:latest',
        volumes: ['mongo-volume:/data/db'],
      }
    },
    volumes: {
      'mongo-volume': {},
    },
    deploy: DeploymentConfig({
      update_config: {
        order: 'stop-first',
        failure_action: 'rollback',
        delay: '10s',
      },
      rollback_config: {
        parallelism: 0,
        order: 'stop-first',
      },
    }),
  },
}
```

Define `.env.dev.jsonnet`:

```jsonnet
local dc = import 'docker-compose.libsonnet';
dc.MyAppDeployment(env='dev')
```

Deploy dev:
```bash
dcp dev up -d --build
```

Deploy prod:
```bash
dcp prod build  # Build images
dcp prod push  # Push to registry
dcp prod deploy  # Deploy stacks
```

Deploy only selected services:
```bash
dcp prod deploy api
dcp prod deploy api worker
```

Service names match the keys in the generated `services` object. With no service
arguments, `deploy` deploys the entire stack. With service arguments, it deploys
only those services under the same stack name, leaving other services untouched.
Unknown names and Jsonnet rendering errors fail before Docker is invoked.

Targeted deployments retain only referenced top-level networks, volumes, secrets,
and configs, including a declared default network when needed. They remove
`depends_on` and do not deploy dependencies automatically; deploy those separately
if they are not already running. Shared resources still follow Swarm rules:
existing networks cannot simply be reconfigured, and secrets/configs are immutable.
Deploy does not build or push images, and Docker returns before rollout completes
by default. Targeted deployments never use `--prune`, which would remove omitted
services.

## Installation

Installation is only two steps:
 1. Install [`jsonnet`](https://github.com/google/go-jsonnet/releases/latest) to PATH
 2. Install [`dcp`](https://github.com/MatthewScholefield/docker-compose-plus/blob/main/bin/docker-compose-plus) to PATH

```bash
install_dir_str='$HOME/opt/docker-compose-plus'

eval "install_dir=\"$install_dir_str\""
git clone https://github.com/MatthewScholefield/docker-compose-plus "$install_dir"
latest_artifact_url=$(curl -fsSL https://api.github.com/repos/google/go-jsonnet/releases/latest | jq -r '.assets[] | select(.name | endswith("_linux_amd64.tar.gz")) | .browser_download_url' | head -n1)
curl -fsSL "$latest_artifact_url" | gzip -dc | tar xf - -C "$install_dir/bin"
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do [ -f "$rc" ] && printf '%s\n' 'PATH="$PATH:'"$install_dir_str"'/bin"' >> "$rc"; done
```

Update a Git-clone installation from any directory:
```bash
dcp self-update
```

This resolves the installed script (including symlinks) and runs `git pull --ff-only`
in its repository. Standalone or nonstandard installations receive an error instead.
Git errors are returned unchanged; divergent branches are not automatically merged.
This updates the wrapper, not the separately installed Jsonnet binary.
