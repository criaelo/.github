# GitHub Actions runners

## Política

Os workflows Criaelo devem usar **GitHub-hosted runners como padrão** para CI, build, publicação e automação GitOps quando não houver dependência de rede privada. Os scale sets ARC (`criaelo-ci` e `criaelo-build`) ficam reservados para:

- fallback operacional;
- acesso a serviços/endereços privados do cluster;
- operações que dependem explicitamente de recursos internos;
- workloads que comprovadamente não cabem no runner GitHub-hosted padrão.

Não implementar fallback automático com `if: failure()`: isso pode repetir uma falha real de código e mascarar o diagnóstico. O fallback é uma decisão operacional explícita.

## Reusable workflows

Os workflows reutilizáveis desta organização usam `ubuntu-latest` por padrão e preservam o input `runner` para override:

```yaml
jobs:
  validate:
    uses: criaelo/.github/.github/workflows/node-validate.yml@main
    with:
      runner: ${{ vars.CRIAELO_RUNNER_CI || 'ubuntu-latest' }}
```

Para builds Docker, use `CRIAELO_RUNNER_BUILD`; para jobs leves/GitOps, use `CRIAELO_RUNNER_CI`.

## Variáveis de contingência

A configuração recomendada no nível da organização é:

```text
CRIAELO_RUNNER_CI=ubuntu-latest
CRIAELO_RUNNER_BUILD=ubuntu-latest
```

Em contingência, trocar temporariamente para:

```text
CRIAELO_RUNNER_CI=criaelo-ci
CRIAELO_RUNNER_BUILD=criaelo-build
```

Jobs com requisito permanente de rede interna devem continuar declarando diretamente `runs-on: criaelo-ci` (ou um label self-hosted específico), sem depender da variável de contingência.

## Estado operacional validado — 2026-08-31

A migração foi concluída nas branches de desenvolvimento efetivas. Auditoria após a migração:

- 25 repositórios ativos verificados;
- 70 workflows verificados nas branches operacionais (`dev` quando existe, senão a default);
- 1 referência self-hosted explícita restante: `shop-api/.github/workflows/refresh-db-hml.yml`, mantida em `criaelo-ci` porque acessa PostgreSQL interno real;
- Backstage validado em `ubuntu-latest` com Playwright/Chrome, E2E, testes, build backend, Docker Buildx/GHCR e GitOps;
- APIs com PostgreSQL descartável em `services:` validadas em GitHub-hosted;
- promoção GitOps cross-repo centralizada em `criaelo/deploy/.github/workflows/promote-service.yml`, acionada por GitHub App com `Actions: write`.

Branches `hml`/`main` que ainda carreguem cópias antigas de workflows devem receber a mudança pelo fluxo normal de promoção do produto, sem commits administrativos que burlem `dev → hml → main`.

## Migração

Prioridade de migração:

1. lint, testes, typecheck, docs, Sonar e releases;
2. GitOps que opera apenas via GitHub API/Git;
3. Docker Buildx + GHCR após piloto por serviço;
4. workloads pesados, somente após medir tempo, memória e custo;
5. manter operações internas (Postgres/cluster privado) no ARC.
