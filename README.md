# agent-eval-kit

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

### Ligar o juiz Claude de verdade (opcional)

```bash
pip install "agent-eval-kit[anthropic]"
export ANTHROPIC_API_KEY=sk-...            # nunca comite isso
python -m agent_eval --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer --judge anthropic
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
Scorecard - PASS (6 example(s))
------------------------------------------------
  faithfulness            1.000   >= 0.250  [ok ]
  keyword_recall          0.667   >= 0.400  [ok ]
  not_hallucinated        1.000   >= 0.250  [ok ]
  relevance               0.436   >= 0.250  [ok ]
  exact_match             0.333   (no threshold)
  groundedness_proxy      1.000   (no threshold)
  latency_ms              0.000   (no threshold)
------------------------------------------------
```

O SUT de exemplo é um "RAG" de sobreposição de palavras-chave que papagaia o
documento mais parecido. Ele é medíocre **de propósito**: repare que ele tira
`relevance` 0,68 na pergunta sobre sono, que consegue responder, mas `0,00` na
pergunta sobre vitamina D, fora da sua base de conhecimento. Essa queda
localizada é o eval pegando uma fraqueza — um SUT perfeito não provaria nada
sobre o kit.

## Futuro (fora do escopo da v0, de propósito)

A v0 é a menor fatia completa que roda ponta a ponta. Adiado deliberadamente:

- UI web / dashboard.
- Persistência / banco de dados de resultados.
- Múltiplos provedores de LLM como backend.
- Datasets grandes ou benchmarks públicos.
- Concorrência, cache e otimização de custo.

## Desenvolvimento

```bash
pip install -e ".[dev]"
pytest
```

A suíte de testes roda inteiramente no juiz mock — sem rede, sem key — e o teste
mais importante garante que um SUT sabidamente ruim tira nota *menor* que um
decente. Se o eval não distingue bom de ruim, não é eval.

## Licença

MIT — veja [LICENSE](LICENSE).
