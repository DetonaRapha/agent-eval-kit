# Contribuindo com o agent-eval-kit

Obrigado pelo interesse! Este guia cobre o essencial para contribuir. Ele é a
versão pública e enxuta do nosso fluxo interno de engenharia.

## Princípios do projeto

Toda contribuição respeita quatro invariantes:

1. **Mock-first / reprodutibilidade por padrão.** O caminho default roda sem rede
   e sem API key. Nada pode quebrar isso.
2. **Núcleo sem dependência obrigatória.** Dependências novas de runtime entram
   como *extras* opcionais (`optional-dependencies`) com import lazy.
3. **Contratos desacoplados.** `SUT` e `Judge` são plugáveis por interface; o kit
   não conhece os internos do sistema avaliado.
4. **Menor fatia completa que roda.** Prefira uma fatia vertical que funcione de
   ponta a ponta a uma refatoração grande.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Rodando os checks

São exatamente os gates que o CI aplica. Rode todos antes de abrir o PR:

```bash
pytest                                          # testes (offline, juiz mock)
ruff check .                                    # lint
ruff format --check .                           # formatação
mypy agent_eval                                 # tipos (strict)
pytest --cov=agent_eval --cov-fail-under=85     # cobertura (piso 85%)
```

Os testes que chamam o Claude de verdade são **opt-in** e ficam fora do run
padrão:

```bash
export ANTHROPIC_API_KEY=sk-...
pytest -m integration
```

## Padrões de código

- Código, identificadores e docstrings **em inglês**; documentação de leitura
  (README, DESIGN) **em português**.
- Type hints em tudo (checados por `mypy --strict`).
- Métricas na escala `0..1`, maior é melhor; normalização de texto centralizada
  em `agent_eval/text.py`.
- Toda mudança de comportamento vem com teste. O teste mais importante do repo
  garante que um SUT ruim pontua *menos* que um bom — mantenha essa propriedade.

## Fluxo de Pull Request

1. Crie uma branch a partir da `main`: `feat/`, `fix/`, `docs/`, `chore/` ou
   `refactor/` + descrição curta.
2. Faça commits pequenos e com mensagem que explica o **porquê**.
3. Rode todos os checks localmente.
4. Abra o PR para `main` descrevendo o que muda e como verificar.
5. O CI (lint, tipos, testes em Python 3.10–3.12, cobertura) precisa passar.

## Segurança

Nunca commite segredos. A key do Claude vive em variável de ambiente; `.env`
está no `.gitignore`. Se encontrar uma vulnerabilidade, abra uma issue sem expor
detalhes sensíveis publicamente.

## Licença

Ao contribuir, você concorda que sua contribuição será licenciada sob a licença
MIT do projeto.
