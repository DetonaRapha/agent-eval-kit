# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto adota [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado

- **Trilha B**: `OpenAIJudge` e `GeminiJudge` (provedores opt-in, import lazy);
  persistência de rodadas (`--save-run`/`--baseline`) com detecção de regressão;
  datasets grandes (`--limit`/`--sample`/`iter_golden`); concorrência
  (`--concurrency`) e cache de juiz (`--cache`); relatório HTML autocontido.
- **Persistência em SQLite** (stdlib) via `--save-run-db` e a API `*_sqlite`.
- **Dashboard estático multi-rodada** (`python -m agent_eval.dashboard`).
- **Adapters de dataset** (`from_records`, `from_csv`) para importar formatos
  externos sem acoplar a nenhum benchmark.

## [0.1.0] - 2026-07-16

Primeira versão. Entrega o esqueleto completo que roda ponta a ponta (v0) mais a
Trilha A de maturidade (v1).

### Adicionado

- **Núcleo de avaliação**: carregamento de golden dataset (`datasets`), contrato
  de System Under Test (`sut`), juízes (`judges`), métricas determinísticas
  (`metrics`), runner (`runner`) e scorecard com veredito pass/fail
  (`scorecard`).
- **Juiz mock determinístico** como padrão — roda sem rede e sem API key — e
  **`AnthropicJudge`** opcional (opt-in, import lazy) atrás do extra `anthropic`.
- **Métricas**: `exact_match`, `keyword_recall`, `groundedness_proxy` e as notas
  do juiz `faithfulness`, `relevance`, `not_hallucinated` (escala 0..1).
- **CLI** (`python -m agent_eval` e `agent-eval`): import dinâmico do SUT via
  `module:function`, relatórios em Markdown e JSON, e exit code para CI.
- **Exemplos**: `tiny_rag` (SUT ingênuo de propósito), `better_rag` (SUT menos
  ingênuo) e `compare` para comparar dois sistemas na mesma régua.
- **Qualidade**: lint e formatação com `ruff`, checagem de tipos `mypy --strict`,
  cobertura com piso de 85% — todos aplicados como gate no CI.
- **Testes**: suíte offline determinística e testes de integração opt-in do juiz
  real (marker `integration`).
- **CI**: GitHub Actions rodando lint, tipos e testes em Python 3.10–3.12.
- **Documentação**: README e DESIGN (em português), LICENSE (MIT).

[Não lançado]: https://github.com/DetonaRapha/agent-eval-kit/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/DetonaRapha/agent-eval-kit/releases/tag/v0.1.0
