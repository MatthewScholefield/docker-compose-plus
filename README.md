# Docker Compose Plus

*Docker compose, but with support for jsonnet and automatic environment handling*

Docker compose is a great method for deploying software stacks (collections of services packaged as docker containers). However, using it in a production setting has a few pitfalls. Notably:

 - Docker swarm has a few different fields than docker compose
 - Environment variables and deployed services may differ for production and dev
 - Using environment variable overrides, config overrides, and namespaces creates a long ugly prefix to every docker compose command like `docker compose -f docker-compose.yml -f docker-compose.dev.yml --env-file .env.dev -p my-app-dev ...`

Docker compose plus is a simple wrapper around `docker-compose` that solves these issues by performing the following behavior:

 - Allowing you to provide a `docker-compose.jsonnet` and `.env.dev.jsonnet`
   - Jsonnet's rich syntax allows runtime customization of the docker compose deployment based on env and whether `useSwarm` (an injected variable) is true
 - Automatically including a `.env.dev` or `.env.dev.jsonnet` file

## Usage

`docker-compose.jsonnet`:

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

`.env.dev.jsonnet`:

```jsonnet
local dc = import 'docker-compose.yml';
dc.MyAppDeployment(env='dev')
```

## Installation

A simple way to install is to clone this repo somewhere and add it to your PATH:

```
install_dir_str='$HOME/opt/docker-compose-plus'
eval install_dir=$install_dir_str

mkdir -p "$install_dir"

git clone https://github.com/MatthewScholefield/docker-compose-plus "$install_dir"
echo 'PATH=$PATH:'"$install_dir_str"/bin >> ~/.bashrc  # Use .zshrc for zsh
```

This allows for easy future upgrades by pulling via git.

