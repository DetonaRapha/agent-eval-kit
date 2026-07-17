# agent-eval-kit — Especificação v1 (Roadmap)

Documento de construção. A v0 já está entregue e mergeada: o esqueleto que roda
ponta a ponta, com juiz mock determinístico, métricas, scorecard, CLI, testes e
CI. Esta spec descreve o próximo ciclo. Você implementa. Aqui estão o escopo, os
contratos, a Definition of Done e a ordem de construção. O corpo das funções é
seu.

O texto está em português; **código, identificadores de métrica, nomes de flag e
mensagens de CLI permanecem em inglês** (são a superfície pública e precisam
casar com a saída do kit).

---

## O que já existe (baseline v0)

Não refazer. É o ponto de partida:

- Contratos: `Example`/`load_golden`, `SUTResult`/`SUT`, `Judge`/`JudgeScores`.
- Juízes: `MockJudge` (determinístico, padrão) e `AnthropicJudge` (opt-in, lazy).
- Métricas determinísticas: `exact_match`, `keyword_recall`, `groundedness_proxy`.
- `runner.evaluate`, `Scorecard` (markdown/json/tabela), CLI com exit code.
- Exemplo `tiny_rag` + `golden.jsonl`, 21 testes, CI no GitHub Actions.

---

## Princípios que se mantêm (não negociáveis)

Toda mudança da v1 respeita o que fez a v0 valer:

1. **Mock-first / reprodutibilidade por padrão.** Nada que a v1 adicione pode
   exigir rede ou API key para o caminho padrão rodar, testar e passar no CI.
2. **Núcleo sem dependência obrigatória.** Novas dependências entram como
   `optional-dependencies` (extras) e com import lazy. Rede e SDKs continuam
   opt-in.
3. **Contratos desacoplados.** SUT e Judge continuam plugáveis por interface. Não
   acoplar o kit a nenhum provedor específico.
4. **Menor fatia completa.** Cada item anda ponta a ponta e commita antes do
   próximo. Sem refatoração especulativa.

---

## Duas trilhas

A v1 tem duas trilhas independentes. **A Trilha A é prioridade** (baixo esforço,
alto sinal de maturidade). A Trilha B é sob demanda — só quando o produto pedir.

- **Trilha A — Maturidade.** Rigor de engenharia sobre a superfície que já existe.
- **Trilha B — Futuro.** Ampliação de escopo deliberadamente adiada na v0.

---

# Trilha A — Maturidade (prioridade)

## A1. Lint + format (ruff) e type checking (mypy)

**Objetivo.** Tornar o rigor verificável por máquina, não por boa vontade.

**Dentro:**
- `ruff` como linter e formatter, configurado no `pyproject.toml`.
- `mypy` em modo estrito sobre o pacote `agent_eval/`.
- Ambos rodando no CI, como gate (falha o build se reprovar).
- Um alvo local reproduzível (`ruff check .`, `ruff format --check .`,
  `mypy agent_eval`). Opcional: um `Makefile` ou script `scripts/check.*`.

**Fora:** pre-commit hooks (pode virar item futuro), outras ferramentas
(black/isort/flake8 — o ruff cobre).

**Contrato/config (esboço, em inglês no arquivo):**

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.10"
strict = true
files = ["agent_eval"]
```

**DoD:**
- `ruff check .`, `ruff format --check .` e `mypy agent_eval` passam limpos.
- CI roda os três como steps próprios, antes do pytest.
- Zero `# type: ignore` sem justificativa em comentário ao lado.
- Nenhum reparo de lint mudou comportamento (testes continuam verdes).

## A2. Teste de integração real do `AnthropicJudge`

**Objetivo.** Provar o caminho real do juiz Claude sem quebrar a regra de "CI sem
rede".

**Dentro:**
- Um teste marcado `@pytest.mark.integration` que instancia o `AnthropicJudge`
  de verdade e faz uma chamada real, validando que o retorno parseia num
  `JudgeScores` com todos os eixos em `0..1`.
- O marker é registrado no `pyproject.toml` e o teste é **pulado por padrão**
  quando `ANTHROPIC_API_KEY` não está no ambiente (`pytest.mark.skipif`).
- Uma asserção de sanidade discriminante: numa resposta claramente fiel e
  relevante, as notas ficam acima de uma resposta claramente ruim (barra frouxa,
  pra não ficar flaky com variação do modelo).

**Fora:** snapshot exato de nota (não-determinístico), múltiplas chamadas caras,
qualquer teste real ligado no gate padrão do CI.

**Contrato/config:**

```toml
[tool.pytest.ini_options]
markers = ["integration: makes real network calls; needs ANTHROPIC_API_KEY"]
```

Invocação: `pytest -m integration` (opt-in). Default (`pytest`) continua pulando.

**DoD:**
- `pytest` (default) passa e **pula** o teste de integração, imprimindo o motivo.
- `pytest -m integration` com key presente roda e passa.
- Nenhuma key no repositório; documentação de como rodar no README/DESENV.

## A3. Cobertura de testes + badges no README

**Objetivo.** Tornar visível a saúde do repo já na primeira tela.

**Dentro:**
- `pytest-cov` como extra de dev; step no CI gerando cobertura.
- Um piso de cobertura razoável (ex.: `--cov-fail-under=85`) — calibrar pelo
  número real, sem inflar com testes vazios.
- Badges no topo do README: status do CI e (se houver serviço) cobertura.

**Fora:** integração paga de cobertura obrigatória; perseguir 100%.

**DoD:**
- CI reporta cobertura e falha abaixo do piso definido.
- README exibe o badge de CI verde.
- O piso reflete a cobertura real medida, documentado no DESIGN se relevante.

## A4. Expandir golden dataset + segundo SUT de exemplo

**Objetivo.** Demonstrar o valor central do kit — **discriminar qualidade entre
sistemas** — de forma visível.

**Dentro:**
- Ampliar `examples/golden.jsonl` (ex.: 10–12 itens), mantendo pelo menos um
  item difícil/fora-de-base por categoria de falha (alucinação, evasão,
  fora-de-domínio).
- Um segundo SUT de exemplo, melhor que o `tiny_rag` (ex.: recuperação por
  sobreposição de conteúdo com síntese simples de múltiplos documentos), para
  comparar dois sistemas no mesmo dataset.
- Um trecho no README (ou script `examples/compare.py`) mostrando os dois
  scorecards lado a lado e o segundo ganhando onde deve.

**Fora:** dataset gigante, benchmark público, gerar dados com LLM.

**DoD:**
- Ambos os SUTs rodam via CLI no dataset ampliado.
- Existe um teste provando que o SUT melhor supera o `tiny_rag` em relevância
  agregada (com MockJudge, determinístico).
- README mostra a comparação como "prova social" do que o kit faz.

---

# Trilha B — Futuro (sob demanda, só quando o produto pedir)

Estes itens são escopo adiado conscientemente, não dívida. Cada um só entra
quando houver necessidade real de produto. Aqui ficam registrados com a direção
de design para não serem improvisados depois.

## B1. Múltiplos provedores de LLM

- **Direção:** manter `Judge` como a interface; cada provedor é uma implementação
  nova (`OpenAIJudge`, etc.) atrás de seu próprio extra opcional e import lazy.
  Fábrica `make_judge` ganha os novos nomes. A rubrica e o parsing de JSON são
  reaproveitados; só muda o cliente.
- **Não fazer:** abstração de "provider" genérica antes de existir o segundo
  provedor real. Adicionar quando o segundo chegar, não antes.

## B2. Persistência / banco de resultados

- **Direção:** o `Scorecard` já serializa para JSON. Persistência começa como
  "escrever runs versionados em disco" (ex.: `runs/<timestamp>.json`) e comparar
  duas rodadas (regressão de qualidade entre commits). Banco de verdade só se o
  volume justificar.
- **Não fazer:** subir Postgres/ORM na v1. Arquivo versionado resolve o primeiro
  caso de uso (detecção de regressão).

## B3. Datasets grandes / benchmarks públicos

- **Direção:** o `load_golden` lê JSONL linha a linha (streaming-friendly). Para
  volume, adicionar carregamento preguiçoso e amostragem. Adaptadores para
  formatos de benchmark público entram como conversores para o formato `Example`.
- **Não fazer:** casar o kit com o schema de um benchmark específico.

## B4. Concorrência, cache e otimização de custo

- **Direção:** o `runner` roda itens em sequência hoje. Concorrência entra como
  execução paralela dos itens (o SUT e o juiz por item são independentes), atrás
  de uma flag `--concurrency N`, preservando resultado determinístico na
  agregação. Cache de chamadas do juiz por hash de (pergunta, resposta,
  contextos, referência) evita recomputar em reprocessos.
- **Não fazer:** otimizar antes de ter um dataset grande o suficiente para doer.
  Medir primeiro.

## B5. UI / dashboard web

- **Direção:** o dashboard consome os relatórios JSON já produzidos; nada de
  acoplar renderização ao núcleo. Provavelmente um app separado que lê `runs/`.
- **Não fazer:** embutir servidor web no pacote `agent_eval`.

---

## Ordem de construção (na ordem)

Menor fatia que roda, uma por vez, commitando entre elas:

1. **A1 (ruff + mypy no CI).** Maior sinal de maturidade, menor esforço. Faz o
   repo "se policiar". Commita quando os três checks estiverem verdes.
2. **A3 (cobertura + badge).** Aproveita o CI recém-endurecido; deixa a saúde
   visível. Commita.
3. **A2 (teste de integração do juiz).** Fecha a lacuna do caminho real sem
   quebrar o CI offline. Commita.
4. **A4 (dataset + segundo SUT + comparação).** Transforma o kit numa demo de
   comparação entre sistemas. Commita.
5. **Trilha B:** só quando o produto pedir. Ao pegar um item B, escrever a fatia
   mínima seguindo a direção registrada acima, e atualizar esta spec.

Só passa de um passo para o outro quando o anterior roda e commita.

---

## Definition of Done da v1 (Trilha A)

A v1 está pronta quando:

- `ruff check .`, `ruff format --check .` e `mypy agent_eval` passam, e o CI os
  aplica como gate.
- Cobertura medida no CI com piso que reflete o valor real; badge de CI no README.
- Teste de integração do `AnthropicJudge` existe, é opt-in por marker e é pulado
  sem key — o `pytest` padrão continua offline e verde.
- Dataset ampliado e segundo SUT de exemplo demonstrando comparação entre
  sistemas, com teste determinístico provando a discriminação.
- Nenhum princípio da v0 violado: caminho padrão sem rede, núcleo sem dependência
  obrigatória, nenhum segredo commitado.

---

## O que NÃO fazer

- Não puxar itens da Trilha B "de brinde" enquanto faz a Trilha A.
- Não deixar nenhum check novo (lint/type/cobertura) apenas local — se não está
  no CI, não conta.
- Não ligar chamadas reais de LLM no gate padrão do CI.
- Não adicionar dependência obrigatória ao núcleo. Extra opcional + import lazy.
- Não inflar cobertura com testes sem asserção só para bater o piso.
- Não comitar key. `.env` segue no `.gitignore`.
