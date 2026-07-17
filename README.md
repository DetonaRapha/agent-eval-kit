# agent-eval-kit

[![CI](https://github.com/DetonaRapha/agent-eval-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/DetonaRapha/agent-eval-kit/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/DetonaRapha/agent-eval-kit/branch/main/graph/badge.svg)](https://codecov.io/gh/DetonaRapha/agent-eval-kit)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Aponte para qualquer coisa que responde uma pergunta — um RAG, um agente, uma
chamada pura de LLM — e receba de volta um **scorecard de qualidade**
(faithfulness, relevância, detecção de alucinação, mais métricas
determinísticas) com um **veredito pass/fail** que você pluga direto no CI.

## Por que isso existe

O teste tradicional assume uma saída determinística: dada a entrada X, verifique
que o resultado é igual a Y. Sistemas de LLM quebram essa premissa — o mesmo
prompt gera respostas diferentes e não-literais, todas potencialmente corretas.
`assert answer == "..."` ou fica instável (flaky) ou não testa nada.

Então qualidade precisa de *avaliação*, não de igualdade: pontuar cada resposta
em eixos estilo rubrica, agregar sobre um golden dataset e reprovar a rodada
quando a qualidade cai abaixo de um limiar. É isso que este kit faz, e ele trata
avaliação como uma camada de teste de primeira classe, não como um notebook
avulso.

## A abordagem em três linhas

1. Carrega um **golden dataset** (perguntas + respostas de referência) e roda o
   sistema sob teste em cada item.
2. Pontua cada resposta com **métricas determinísticas** (sem LLM) e um
   **LLM-as-judge** (faithfulness / relevância / não-alucinado).
3. Agrega num **scorecard**, compara com os thresholds, gera Markdown + JSON e
   sai com código diferente de zero se a qualidade estiver abaixo da barra.

## Mock-judge-first

Por padrão o kit roda com um **juiz mock determinístico** — sem API key, sem
rede, resultados idênticos em qualquer lugar. Clona, um comando, CI verde. Ligue
o juiz Claude de verdade com uma variável de ambiente quando quiser.
Reprodutibilidade é o padrão; o LLM é o upgrade.

## Como rodar

```bash
# Juiz mock determinístico — não precisa de API key.
python -m agent_eval \
  --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer \
  --judge mock \
  --report out/
```

`--sut` é uma referência `module:function` importada dinamicamente, então você
aponta o kit para o seu próprio sistema sem tocar no código dele. O comando
imprime um scorecard, escreve `out/report.md` e `out/report.json`, e sai com `0`
em caso de aprovação / `1` em caso de reprovação — pronto para CI.

### Ligar um juiz LLM de verdade (opcional)

O kit traz dois provedores opt-in, cada um atrás do seu extra e com import lazy:

```bash
# Claude (Anthropic)
pip install "agent-eval-kit[anthropic]"
export ANTHROPIC_API_KEY=sk-...            # nunca comite isso
python -m agent_eval --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer --judge anthropic

# OpenAI
pip install "agent-eval-kit[openai]"
export OPENAI_API_KEY=sk-...
python -m agent_eval --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer --judge openai
```

O modelo tem como padrão um modelo Claude atual e é sobrescrevível com
`AGENT_EVAL_JUDGE_MODEL`. O SDK `anthropic` é um extra opcional — nunca é
necessário para rodar o kit.

## Métricas

Toda nota é `0..1`, **maior é melhor**. Latência é reportada, não pontuada.

| Métrica | O que mede |
| --- | --- |
| `exact_match` | 1 se a resposta normalizada é igual à referência normalizada. |
| `keyword_recall` | Fração dos termos obrigatórios de `must_include` presentes na resposta. |
| `groundedness_proxy` | Fração dos tokens de conteúdo da resposta encontrados nos contextos recuperados — um proxy barato de alucinação, sem LLM. |
| `faithfulness` (juiz) | A resposta é sustentada pelos contextos recuperados? |
| `relevance` (juiz) | A resposta de fato responde à pergunta? |
| `not_hallucinated` (juiz) | 1 = nada inventado, 0 = conteúdo fabricado. |
| `latency_ms` | Tempo de parede reportado pelo SUT (reportado, não pontuado). |

## Decisões de design

A arquitetura e o raciocínio de "por que não fazer de outro jeito" estão no
[DESIGN.md](DESIGN.md): mock-judge-first, um contrato de SUT desacoplado e
métricas determinísticas ao lado do juiz.

## Resultado

Uma rodada contra o SUT `examples/tiny_rag`, propositalmente ingênuo:

```
Scorecard - PASS (12 example(s))
------------------------------------------------
  faithfulness            1.000   >= 0.250  [ok ]
  keyword_recall          0.667   >= 0.400  [ok ]
  not_hallucinated        1.000   >= 0.250  [ok ]
  relevance               0.412   >= 0.250  [ok ]
  exact_match             0.167   (no threshold)
  groundedness_proxy      1.000   (no threshold)
  latency_ms              0.000   (no threshold)
------------------------------------------------
```

O SUT de exemplo é um "RAG" de sobreposição de palavras-chave que papagaia o
documento mais parecido. Ele é medíocre **de propósito**: em perguntas fora da
base de conhecimento (vitamina D, antibiótico, capital da França) ele devolve
com confiança um documento irrelevante, e o `relevance` despenca nesses itens.
Essa queda localizada é o eval pegando uma fraqueza — um SUT perfeito não
provaria nada sobre o kit.

### Comparando dois sistemas

O verdadeiro valor do kit é **distinguir sistemas na mesma régua**. O
`examples/better_rag` é uma versão menos ingênua: recupera por palavras de
conteúdo e **admite quando a pergunta está fora do domínio** em vez de chutar.
Rode a comparação:

```bash
python -m examples.compare
```

```
metric                    tiny_rag    better_rag
------------------------------------------------
exact_match                  0.167         0.167
keyword_recall               0.667         0.750
groundedness_proxy           1.000         0.833
faithfulness                 1.000         0.938
relevance                    0.412         0.464
not_hallucinated             1.000         0.938
```

O `better_rag` ganha em `relevance` e `keyword_recall` — recupera melhor e não
inventa resposta fora do domínio. Em troca, cai um pouco em `groundedness` e
`faithfulness`: ao declinar honestamente, ele responde sem contextos, então
esses itens não têm o que "sustentar". É um tradeoff real, e o scorecard o
expõe — que é exatamente o trabalho de um kit de avaliação.

## Recursos avançados

Além do fluxo básico, o kit oferece:

```bash
# Datasets grandes: só os N primeiros, ou uma amostra determinística
python -m agent_eval --dataset big.jsonl --sut m:f --limit 100
python -m agent_eval --dataset big.jsonl --sut m:f --sample 50 --seed 7

# Concorrência (acelera juízes LLM reais) e cache de veredito
python -m agent_eval --dataset examples/golden.jsonl --sut m:f \
  --judge anthropic --concurrency 8 --cache

# Persistência e detecção de regressão entre rodadas (ótimo para CI)
python -m agent_eval --dataset examples/golden.jsonl --sut m:f \
  --save-run runs/ --run-name baseline
python -m agent_eval --dataset examples/golden.jsonl --sut m:f \
  --baseline runs/baseline.json --regression-tolerance 0.02
```

Com `--report DIR`, além de `report.md` e `report.json`, é gerado um
`report.html` autocontido (abre em qualquer navegador, sem servidor).

## Futuro

Ainda deliberadamente fora do escopo:

- Dashboard web completo (o `report.html` cobre o caso simples).
- Persistência em banco de dados (hoje é arquivo JSON versionado).
- Benchmarks públicos como adaptadores de dataset.
- Outros provedores de LLM além de Anthropic e OpenAI.

## Desenvolvimento

```bash
pip install -e ".[dev]"

pytest                      # testes (offline, no juiz mock)
ruff check .                # lint
ruff format --check .       # formatação
mypy agent_eval             # checagem de tipos (strict)
pytest --cov=agent_eval     # cobertura (piso de 85% no CI)
```

A suíte de testes roda inteiramente no juiz mock — sem rede, sem key — e o teste
mais importante garante que um SUT sabidamente ruim tira nota *menor* que um
decente. Se o eval não distingue bom de ruim, não é eval.

Os testes de integração que chamam o Claude de verdade são **opt-in** e ficam
fora do run padrão. Com uma key no ambiente:

```bash
export ANTHROPIC_API_KEY=sk-...
pytest -m integration
```

Sem a key, eles são pulados — o CI continua offline e verde. Lint, tipos e o piso
de cobertura são aplicados como gate no CI.

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para o fluxo de contribuição e
[CHANGELOG.md](CHANGELOG.md) para o histórico de versões.

## Licença

MIT — veja [LICENSE](LICENSE).
