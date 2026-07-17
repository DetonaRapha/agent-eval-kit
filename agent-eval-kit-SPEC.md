# agent-eval-kit — Especificação (v0)

Documento de construção. Você implementa. Aqui estão o escopo, os contratos, as métricas, a Definition of Done e a ordem de construção. O corpo das funções é seu.

---

## O que é e o que prova

Um kit que avalia a qualidade de um agente ou de uma função de LLM de forma automática e reprodutível. Você aponta ele pra qualquer "coisa que responde" (um RAG, um agente) e ele devolve um scorecard com faithfulness, relevância, detecção de alucinação e métricas determinísticas.

Prova a tua skill mais rara: avaliar IA, não só construir. E prova do jeito sênior, tratando qualidade de saída não-determinística com rubrica e LLM-as-judge. De quebra, exercita Python.

---

## Escopo v0 (a menor fatia completa)

Dentro:
- Carregar um golden dataset (perguntas + resposta de referência).
- Rodar o sistema sob teste em cada item.
- Aplicar avaliadores: uns determinísticos (sem LLM) e uns via juiz.
- Agregar num scorecard com pass/fail contra thresholds.
- Cuspir relatório em markdown e json.

Fora de propósito (não faça na v0, pra não virar framework genérico):
- UI ou dashboard web.
- Banco de dados.
- Suporte a vários provedores de LLM.
- Dataset gigante ou benchmark público.
- Paralelismo, cache, otimização de custo.

Se bater vontade de fazer qualquer um desses, anota numa seção "futuro" do README e segue. v0 é o esqueleto que roda.

---

## O princípio de design que define a sofisticação

**Mock-judge-first.** Por padrão o kit roda com um juiz mock determinístico. Isso significa: clona, um comando, roda, teste passa, CI verde, sem precisar de API key. Quem quiser o juiz de verdade liga o Claude com uma variável de ambiente.

Isso é o que faz o repo parecer nível Google/Anthropic: reprodutível, testável, sem dependência externa pra demonstrar, com o rationale visível. Sofisticação ali é clareza e rigor numa superfície pequena, não tamanho.

---

## Estrutura de pastas

```
agent-eval-kit/
├── README.md
├── DESIGN.md
├── LICENSE
├── .gitignore
├── pyproject.toml
├── agent_eval/
│   ├── __init__.py
│   ├── __main__.py         # permite `python -m agent_eval`
│   ├── datasets.py         # carrega o golden dataset
│   ├── sut.py              # tipo do "system under test" (contrato)
│   ├── judges.py           # protocolo de juiz + MockJudge + AnthropicJudge
│   ├── metrics.py          # métricas determinísticas (sem LLM)
│   ├── runner.py           # roda o SUT no dataset, aplica avaliadores, agrega
│   ├── scorecard.py        # agrega, decide pass/fail, formata relatório
│   └── cli.py              # parsing de argumentos e orquestração
├── examples/
│   ├── tiny_rag.py         # um SUT de demonstração, propositalmente ingênuo
│   └── golden.jsonl        # dataset de exemplo
├── tests/
│   └── test_eval.py
└── .github/workflows/ci.yml
```

---

## Componentes e contratos

Os contratos abaixo são o que cada peça expõe. A implementação é sua.

### 1. datasets.py

Carrega um arquivo JSONL num conjunto de exemplos.

```python
@dataclass
class Example:
    question: str
    reference: str                 # resposta de referência (ground truth)
    must_include: list[str] = field(default_factory=list)  # termos que a resposta deveria conter
    contexts: list[str] = field(default_factory=list)      # opcional: contextos ground-truth

def load_golden(path: str) -> list[Example]: ...
```

Comportamento: lê JSONL linha a linha, ignora linha vazia, valida que `question` e `reference` existem, erro claro se faltar.

### 2. sut.py (system under test)

Define o contrato do que está sendo avaliado. Um SUT é qualquer callable que recebe uma pergunta e devolve um resultado.

```python
@dataclass
class SUTResult:
    answer: str
    contexts: list[str] = field(default_factory=list)   # contextos que o SUT recuperou/usou
    latency_ms: float = 0.0

SUT = Callable[[str], SUTResult]
```

Regra: o kit não sabe nada sobre como o SUT funciona por dentro. Ele só chama `sut(question)` e lê o `SUTResult`. Isso é o que torna o kit reutilizável.

### 3. judges.py

Um juiz dá notas de 0 a 1 comparando resposta, contextos e referência.

```python
@dataclass
class JudgeScores:
    faithfulness: float        # a resposta é sustentada pelos contextos?
    relevance: float           # a resposta responde à pergunta?
    not_hallucinated: float    # 1 = sem alucinação, 0 = alucinou (inverso do risco)
    rationale: str = ""        # justificativa curta

class Judge(Protocol):
    def score(self, question: str, answer: str,
              contexts: list[str], reference: str) -> JudgeScores: ...
```

Duas implementações:

- **MockJudge** (padrão, determinístico): deriva as notas de sobreposição de texto simples entre resposta, contextos e referência. Não usa LLM. Serve pra CI e teste rodarem em qualquer lugar, sempre com o mesmo resultado. Não precisa ser perfeito, precisa ser estável.
- **AnthropicJudge** (opcional): manda pro Claude a pergunta, a resposta, os contextos e a referência, com uma rubrica pedindo JSON no formato de `JudgeScores`, e parseia. Só é importado quando escolhido, pra não obrigar a instalar o SDK. Modelo configurável por variável de ambiente (default sensato, comentado). Prompt e parsing são seus.

Convenção em tudo: **maior é melhor**, escala 0 a 1.

### 4. metrics.py (determinísticas, sem LLM)

Funções puras, sem chamada de rede. Cada uma recebe o `SUTResult` e o `Example`.

- `exact_match` → 1 se a resposta normalizada bate com a referência normalizada, senão 0.
- `keyword_recall` → fração dos termos de `must_include` presentes na resposta.
- `groundedness_proxy` → fração dos tokens de conteúdo da resposta que aparecem na união dos contextos recuperados. Proxy barato de alucinação: valor baixo sugere que a resposta inventou coisa fora do contexto.
- `latency_ms` → vem direto do `SUTResult`, reportada à parte (não é score 0-1).

Normalização (defina uma e reuse): minúsculo, sem pontuação, sem espaço extra.

### 5. runner.py

O coração. Roda tudo e devolve o scorecard.

```python
def evaluate(sut: SUT,
             dataset: list[Example],
             judge: Judge,
             thresholds: dict[str, float]) -> "Scorecard": ...
```

Comportamento por item: chama `sut(question)`, calcula as métricas determinísticas, chama `judge.score(...)`, junta tudo num resultado por item. No fim, agrega (média de cada métrica) e monta o `Scorecard`.

### 6. scorecard.py

```python
@dataclass
class Scorecard:
    per_item: list[dict]            # uma linha por exemplo, com todas as notas
    aggregate: dict[str, float]     # média de cada métrica
    thresholds: dict[str, float]
    passed: bool                    # aggregate bate os thresholds?

    def to_markdown(self) -> str: ...
    def to_json(self) -> str: ...
    def print_table(self) -> None: ...
```

`passed` é True quando cada métrica agregada com threshold definido fica acima do seu threshold. É isso que transforma o kit numa camada de teste de verdade: ele reprova qualidade ruim.

### 7. cli.py + __main__.py

Entrada de linha de comando:

```
python -m agent_eval \
  --dataset examples/golden.jsonl \
  --sut examples.tiny_rag:answer \
  --judge mock \
  --report out/
```

- `--sut` no formato `modulo:funcao`, importado dinamicamente.
- `--judge` aceita `mock` (default) ou `anthropic`.
- `--report` grava `report.md` e `report.json`.
- Imprime o scorecard na tela e sai com código 0 se passou, 1 se reprovou (bom pra CI).

---

## Golden dataset (formato)

JSONL, um exemplo por linha:

```json
{"question": "...", "reference": "...", "must_include": ["...", "..."]}
```

Comece com 5 ou 6 itens do teu domínio (saúde sintético). Inclua de propósito um item difícil, onde é fácil o modelo alucinar, pra mostrar o kit pegando isso.

---

## Exemplo de SUT (tiny_rag.py)

Um RAG propositalmente ingênuo: uma busca simples por palavra-chave sobre um punhado de documentos em memória, que devolve `SUTResult` com resposta e contextos. Ele deve ser meio ruim de propósito, porque o objetivo é o eval revelar as fraquezas dele. Um SUT perfeito não prova que teu kit funciona.

---

## Testes (o que provar)

O teste é a prova de que o kit é uma camada de qualidade, não enfeite:

1. O pipeline roda com o MockJudge no golden de exemplo e produz um scorecard com todas as chaves de métrica esperadas.
2. Um SUT sabidamente ruim (que responde "não sei" ou responde fora do tema) tira nota **menor** que o `tiny_rag` em relevância e faithfulness. Isso prova que o eval discrimina qualidade. É o teste mais importante do repo.
3. A lógica de threshold funciona: com threshold alto o scorecard reprova, com threshold baixo passa.

Tudo com o MockJudge, sem rede, determinístico.

---

## Definition of Done

O repo está pronto quando:
- Clona e roda com um comando (`python -m agent_eval ...` no modo mock).
- Tem teste e o teste passa.
- CI verde (GitHub Actions rodando o pytest).
- README completo e DESIGN.md presente.
- Nenhum segredo commitado (a key do Claude fica em variável de ambiente, e o `.gitignore` cobre `.env`).
- Escopo pequeno fechado ponta a ponta. Nada de TODO gigante no meio do código.

---

## README (estrutura a seguir, em inglês)

1. Título e uma linha do que o kit faz.
2. O problema e o porquê: teste tradicional assume saída determinística, LLM não é, então a qualidade precisa de eval.
3. A abordagem em três linhas.
4. Como rodar (modo mock, um comando) e como ligar o juiz Claude.
5. As métricas, cada uma em uma linha.
6. Decisões de design e tradeoff (aponta pro DESIGN.md).
7. Um bloco "resultado" com um exemplo de scorecard.
8. Seção "futuro" com o que ficou de fora de propósito.

Escreve em inglês, pra manter a porta do mercado em dólar aberta.

## DESIGN.md (o que colocar, em inglês)

Uma página, estilo RFC leve:
- Contexto: por que avaliar agente é diferente de testar software normal.
- Decisão: mock-judge-first, contrato de SUT desacoplado, métricas determinísticas mais juiz.
- Alternativas consideradas: usar Ragas/DeepEval prontos, ou só métricas determinísticas.
- Tradeoff: por que você escolheu esse desenho (controle, reprodutibilidade, didático) e o que abriu mão. Esse "por que não do outro jeito" é o sinal de senioridade.

---

## Ordem de construção (pra você fazer, na ordem)

Constrói na ordem da menor fatia que roda, não peça por peça isolada:

1. **Anda o esqueleto vazio primeiro.** Cria a estrutura de pastas, o `pyproject.toml`, o `.gitignore`, a LICENSE. Faz `python -m agent_eval --help` funcionar. Commita.
2. **Uma fatia vertical mínima.** Um golden com um item só, o `tiny_rag`, o MockJudge com uma métrica só (relevância), o runner e o scorecard imprimindo. Faz `python -m agent_eval` rodar de ponta a ponta e mostrar um número. Esse é o momento "roda ponta a ponta", o mais importante.
3. **Escreve o teste 2** (o SUT ruim tira nota menor). Se passar, teu eval discrimina qualidade. Commita.
4. **Adiciona as outras métricas determinísticas** (exact_match, keyword_recall, groundedness_proxy) e as outras notas do juiz (faithfulness, not_hallucinated).
5. **Relatório** em markdown e json, e o exit code pro CI.
6. **AnthropicJudge**, por último, atrás da variável de ambiente. O kit já tem que estar completo e testado sem ele.
7. **README e DESIGN.md.** Escreve como se um CEO e um engenheiro fossem ler, cada um pegando o que precisa.
8. **CI** rodando o pytest no push.

Só passa de um passo pro outro quando o anterior roda e commita. É a tua regra da menor fatia completa aplicada a você mesma.

---

## O que NÃO fazer

- Não comece pela arquitetura perfeita. Comece pela fatia que roda no passo 2.
- Não adicione provedor, cache, paralelismo nem UI na v0.
- Não deixe o AnthropicJudge virar dependência obrigatória.
- Não commite a key. `.env` no `.gitignore`.
- Não gold-plate o `tiny_rag`. Ele é pra ser meio ruim.
