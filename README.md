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

### Definitions

Define `docker-compose.libsonnet`:

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

## Installation

Installation is only two steps:
 1. Install [`jsonnet`](https://github.com/google/go-jsonnet/releases/latest) to PATH
 2. Install [`dcp`](https://github.com/MatthewScholefield/docker-compose-plus/blob/main/bin/docker-compose-plus) to PATH

```bash
install_dir_str='$HOME/opt/docker-compose-plus'

eval install_dir="$install_dir_str"
git clone https://github.com/MatthewScholefield/docker-compose-plus "$install_dir"
latest_artifact_url=$(curl -fsSL https://api.github.com/repos/google/go-jsonnet/releases/latest | jq -r '.assets[] | select(.name | endswith("_linux_amd64.tar.gz")) | .browser_download_url' | head -n1)
curl -fsSL "$latest_artifact_url" | gzip -dc | tar xf - -C "$install_dir/bin"
echo 'PATH=$PATH:'"$install_dir_str"'/bin' >> ~/.bashrc
```

This allows for easy future upgrades by pulling via git (`cd ~/opt/docker-compose-plus && git pull`).
