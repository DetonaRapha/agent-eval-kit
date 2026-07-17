# DESIGN — agent-eval-kit

Um RFC leve sobre por que o kit tem o formato que tem. Uma página. A parte
interessante não é o que ele faz, mas o que ele deliberadamente *não* faz.

## Contexto: avaliar um agente não é testar software

O teste de software normal se apoia em determinismo: a entrada X precisa produzir
a saída Y, então você verifica igualdade e segue. Sistemas de LLM violam isso na
raiz. A mesma pergunta gera um texto diferente toda vez, e "diferente" não é
"errado" — uma paráfrase pode estar perfeitamente correta. `assert answer ==
expected` portanto ou fica instável o tempo todo ou, suavizado para uma checagem
de substring, quase não testa nada.

A qualidade de um sistema não-determinístico precisa ser *medida*, não afirmada:
pontuar cada resposta contra uma rubrica, agregar sobre um dataset representativo
e usar o agregado como portão. Isso reposiciona a avaliação como uma camada de
teste — um quality gate de nível CI — em vez de um notebook exploratório. Tudo
abaixo decorre de levar esse reposicionamento a sério numa superfície pequena.

## Decisão

**1. Mock-judge-first.** O juiz padrão é determinístico e sem LLM, derivando as
notas de sobreposição de texto. Esta é a decisão que sustenta tudo. Significa que
o kit inteiro — incluindo o teste de "o eval discrimina qualidade?" — roda sem
API key, sem rede e com saída idêntica em qualquer máquina. O juiz Claude de
verdade é um upgrade opt-in, atrás de uma variável de ambiente e de uma
dependência opcional, nunca um requisito para demonstrar ou testar o kit.
Reprodutibilidade é o padrão; o LLM é o aprimoramento.

**2. Contrato de SUT desacoplado.** O sistema sob teste é qualquer callable
`question -> SUTResult`. O kit não sabe nada sobre os internos dele — recuperação,
prompting, escolha de modelo são todos opacos. Esse contrato de mão única é o que
torna o kit reutilizável entre um RAG, um agente ou uma chamada pura de LLM sem
modificação, e é por isso que `--sut module:function` pode apontar para código
arbitrário do usuário.

**3. Métricas determinísticas *e* um juiz, não um ou outro.** As métricas
determinísticas (exact match, keyword recall, groundedness proxy) são baratas,
rápidas e completamente estáveis, mas cegas ao significado — não conseguem dizer
se uma resposta é *fiel* ou apenas tem sobreposição de palavras. O juiz captura
os eixos semânticos que as métricas perdem. Nenhum é suficiente sozinho; o
scorecard reporta ambos e aplica threshold em qualquer um.

**4. O veredito por threshold é o produto.** Agregar notas é um relatório;
compará-las com thresholds e sair com código diferente de zero é um *teste*. O
veredito pass/fail exposto como exit code do processo é o que permite ao kit
bloquear saída ruim no CI — essa é a diferença entre um dashboard e um quality
gate.

## Alternativas consideradas

- **Usar Ragas / DeepEval prontos.** Maduros e cheios de recursos, mas puxam
  dependências pesadas, assumem que um LLM está sempre disponível e escondem a
  lógica de pontuação atrás de abstrações. Para um kit cujo propósito é
  *demonstrar* eval rigoroso e reprodutível numa superfície pequena, uma
  dependência opaca enfraquece a mensagem. Escrever um núcleo mínimo mantém a
  pontuação auditável e a demo rodável com zero setup. (Se isso crescer além da
  v0, adotar um deles como backend de juiz opcional seria o passo natural — os
  contratos de SUT/juiz foram desenhados para permitir isso.)

- **Só métricas determinísticas, sem juiz nenhum.** Totalmente reprodutível e
  sem dependências, mas incapaz de medir faithfulness ou alucinação de forma
  significativa — exatamente os eixos que mais importam para saída de LLM. Isso
  joga fora a metade mais difícil e mais valiosa do problema.

- **Só juiz LLM, sem mock.** Código mais simples, mas todo clone, teste e rodada
  de CI precisaria de API key e rede, e os resultados variariam de rodada para
  rodada. Isso falha na barra de reprodutibilidade que o projeto inteiro tenta
  modelar.

## Tradeoff — o que foi escolhido e do que se abriu mão

A escolha é **controle, reprodutibilidade e didática acima de amplitude
out-of-the-box**. As notas do juiz mock são heurísticas e não precisas em termos
absolutos — são estáveis e *discriminantes*, que é o que um quality gate precisa,
mas não substituem o entendimento semântico do juiz de verdade. As métricas
determinísticas são rasas por construção. E, ao permanecer sem dependências no
núcleo, o kit reimplementa uma fatia do que frameworks maduros já oferecem.

O que se compra com essas concessões: um repo que clona e roda em um comando, uma
suíte de testes que prova que o eval discrimina bom de ruim sem nenhum serviço
externo, e uma lógica de pontuação pequena o bastante para ser lida de ponta a
ponta. Numa v0 cujo trabalho é provar a *ideia* de eval-como-camada-de-teste,
esse trade é o ponto — sofisticação aqui é clareza e rigor numa superfície
pequena, não tamanho. O "por que não de outro jeito" acima é o verdadeiro
entregável.
