# Motor Algorítmico para Escalonamento de Analistas em NOC

Protótipo funcional do TCC *Motor Algorítmico para Escalonamento de Analistas em
Centros de Operações de Rede: Modelagem por Restrições e Otimização Combinatória*
(Pós-Graduação em Tecnologias e Sistemas de Informação — UFABC).

Arquitetura híbrida sequencial:

```
Greedy  →  Hill Climbing  →  Simulated Annealing  →  CSP com Backtracking
(constrói)   (refina local)     (otimiza global)        (valida e repara)
```

Implementado exclusivamente com a **biblioteca padrão do Python 3.10+**. Sem
dependências externas, sem instalação.

---

## 1. Mapeamento código ↔ TCC

| Módulo | Seção do TCC | Conteúdo |
|---|---|---|
| `dominio.py` | 6.4 | Conjuntos `A` e `T`, turnos fixos (Eq. 6.1), parâmetros da CLT |
| `escala.py` | 6.6.2–6.6.4 | Matriz `X_{a,t}` e componentes de custo mantidas em O(1) |
| `restricoes.py` | 6.5 | Restrições rígidas (Eq. 6.3 a 6.6) e flexíveis (6.5.2) |
| `objetivo.py` | 6.6, 6.6.1 | `F(X)` (Eq. 6.7) e normalização min-max (Eq. 6.8) |
| `vizinhanca.py` | 6.1.3–6.1.4 | Movimentos: troca, realocação, substituição, inclusão, exclusão |
| `algoritmos/guloso.py` | 6.1.1 | Estágio 1 — construção gulosa |
| `algoritmos/hill_climbing.py` | 6.1.3 | Estágio 2 — busca local determinística |
| `algoritmos/simulated_annealing.py` | 6.1.4, 6.6.1 | Estágio 3 — recozimento e aquecimento |
| `algoritmos/csp.py` | 6.1.5–6.1.6 | Estágio 4 — CSP `(X, D, C)` com Backtracking e MRV |
| `algoritmos/pipeline.py` | 6.1.8 | Arquitetura híbrida e fotografia por estágio |
| `ahp.py` | 6.6.5 | Calibração de α, δ, λ por AHP com razão de consistência |
| `metricas.py` | 5.1 | Métricas (a) a (e) e simulação de estresse |
| `baseline.py` | 5.1(a) | Escala manual por rodízio, para comparação |
| `gerador.py` | — | Instâncias sintéticas de NOC 24x7 |
| `saida.py` / `cli.py` | Obj. Geral | Relatórios analíticos e interface de linha de comando |

---

> **Vai apresentar o trabalho?** O arquivo `COMO_EXECUTAR.md` traz um roteiro
> de demonstração de quatro minutos, com os tempos de cada comando medidos e as
> perguntas mais prováveis já respondidas.
>
> **Vai publicar no GitHub?** O arquivo `COMO_PUBLICAR.md` traz o passo a passo,
> incluindo autenticação por token e escolha de licença.

## 2. Uso

```bash
cd motor_noc

# Escala otimizada de 28 dias, com grade visual e artefatos em disco
python -m motor_noc.cli executar --dias 28 --grade --saida saida/

# Métrica 5.1(a) — motor versus escala manual por rodízio
python -m motor_noc.cli comparar --dias 28

# Métrica 5.1(c) — gap de otimalidade contra busca exaustiva
python -m motor_noc.cli gap

# Métrica 5.1(e) — sensibilidade aos pesos estruturais
python -m motor_noc.cli sensibilidade --dias 14 --passo 0.25 --saida saida/

# Objetivo específico (d) — tempo de processamento e consumo de memória
python -m motor_noc.cli benchmark --dias 7 14 28 56 --saida saida/

# Subseção 6.6.5 — calibração dos pesos por AHP
python -m motor_noc.cli ahp --eq-sen 3 --eq-cob 2 --sen-cob 0.5

# Suíte de testes (28 casos)
python -m unittest discover -s tests -v
```

Artefatos gravados em `--saida`: `escala.csv`, `cargas.csv`,
`curva_convergencia.csv` (métrica 5.1d), `ganho_por_estagio.csv` (métrica 5.1b),
`grade.txt`, `relatorio.txt` e `resumo.json`.

### Uso como biblioteca

```python
from motor_noc.gerador import gerar_instancia
from motor_noc.algoritmos.pipeline import executar
from motor_noc.objetivo import Pesos

inst = gerar_instancia(dias=28, seed=42)
resultado = executar(inst, pesos=Pesos(0.54, 0.16, 0.30), seed=42)

print(resultado.custo_final(), resultado.valida)
```

---

## 3. Decisões de implementação com reflexo no texto

Cinco pontos surgiram durante a codificação e merecem tratamento no documento.

**3.1 Mínimo teórico na normalização (Subseção 6.6.1).** O texto define `f_min`
e `f_max` a partir da amostra de aquecimento. Na prática isso degrada a busca:
quando a otimização alcança valores abaixo do `f_min` estimado, o truncamento da
Equação 6.8 os achata todos em 0 e a componente deixa de discriminar soluções —
o gradiente desaparece exatamente na região de melhor qualidade. Em teste
controlado, o Simulated Annealing ficou incapaz de melhorar sobre o Hill
Climbing por esse motivo. As três componentes têm zero como ínfimo matemático
(variância nula, nenhuma superqualificação, aderência exata entre capacidade e
volume), de modo que se adota `f_min = 0` e mantém-se a estimativa empírica
apenas para `f_max`. O comportamento original permanece disponível via
`Normalizador(usar_minimo_teorico=False)`, para a análise comparativa.

**3.2 Posição da fase de aquecimento.** O aquecimento é executado sobre a
solução gulosa, **antes** do Hill Climbing, e não no início do Simulated
Annealing. A razão é a métrica 5.1(b): comparar o custo dos estágios exige que
todos compartilhem a mesma escala de normalização. Sugere-se ajustar a redação
para "fase de aquecimento do motor" em vez de "do Simulated Annealing".

**3.3 Restrições legais acrescentadas.** Além das previstas na Subseção 6.5.1,
foram implementadas duas regras que apertam significativamente o espaço factível
em regime 24x7: o repouso semanal remunerado de 24 horas (art. 67 da CLT) e a
hora noturna reduzida de 52min30s (art. 73, §1º), que faz o turno noturno
consumir 9,14 horas legais do teto semanal, e não 8. Corrigiu-se também a base
do teto de 44 horas: art. 7º, XIII da CF/88, regulamentado pelos arts. 58 e 59
da CLT. O repouso semanal pode ser desativado com `--sem-repouso-semanal`, para
medir seu impacto isolado.

**3.4 Temperatura inicial do Simulated Annealing.** A literatura calibra `T0`
para taxa de aceitação inicial de 0,8, supondo início a partir de solução
aleatória. Aqui o SA recebe uma solução já refinada pelo Hill Climbing: com
`T0` alto ele desfaz esse refinamento antes de resfriar e degenera em caminhada
aleatória. Adotou-se alvo de 0,15, posicionando o estágio como intensificação, e
acrescentou-se retorno à melhor solução conhecida após estagnação prolongada.

**3.5 Verificação incremental versus reparo.** Todos os movimentos preservam a
factibilidade, de modo que a escala nunca sai do espaço admissível. O estágio de
CSP atua, portanto, como garantia final de consistência — e seu mecanismo de
reparo por Backtracking é exercitado nos testes contra escalas deliberadamente
corrompidas (`TestCSP`). Além do preenchimento de déficits, implementou-se
reparo dirigido por conflito: quando o domínio de um slot está vazio, o
impedimento costuma ser o bloqueio dos candidatos pela folga cascata, e não a
falta de pessoal; desfazer seletivamente uma alocação excedente de outro turno
resolve o déficit.

---

## 4. Resultados de referência

Instância sintética de 31 analistas, 14 dias, 52 turnos, semente 42, pesos
equilibrados (α = δ = λ = 1/3):

| Estágio | F(X) | Ganho | Violações rígidas |
|---|---|---|---|
| 1. Construção Gulosa | 0,3640 | — | 0 |
| 2. Hill Climbing | 0,2280 | +0,1360 | 0 |
| 3. Simulated Annealing | 0,2255 | +0,0025 | 0 |
| 4. CSP com Backtracking | 0,2255 | — | 0 |

**Métrica 5.1(a) — motor versus rodízio manual:** desvio padrão médio da carga
por equipe cai 62% (13,0 h → 4,9 h) e a amplitude cai 65% (34 h → 12 h). Observe-se
que, sob pesos iguais, o componente `f_atendimento` piora em relação à escala
manual: o motor adiciona analistas para equalizar cargas e, com isso, gera
ociosidade em turnos de baixo volume. É um resultado legítimo do modelo e um
bom material para a etapa de Análise e Escrita — a repriorização via AHP
desloca esse equilíbrio.

**Métrica 5.1(c) — gap de otimalidade:** em instância reduzida (7 analistas,
8 turnos, 4 dias), a busca exaustiva enumerou 6.561 soluções factíveis e o
pipeline heurístico atingiu **o ótimo global, com gap de 0,0%**. O motor é
executado em modo de cardinalidade fixa nessa métrica, para que percorra
exatamente o mesmo espaço da enumeração.

**Desempenho (objetivo específico d):** 2,2 s / 0,33 MB para 7 dias; 4,8 s /
0,41 MB para 14 dias; 7,4 s / 0,68 MB para 28 dias. O crescimento do tempo é
aproximadamente linear no número de turnos, e o consumo de memória permanece
irrelevante — resultado da avaliação incremental do custo em O(1) por movimento,
sem a qual as 20.000 iterações do recozimento seriam inviáveis em Python.

---

## 5. Estrutura

```
motor_noc/
├── motor_noc/
│   ├── dominio.py, escala.py, restricoes.py, objetivo.py, vizinhanca.py
│   ├── ahp.py, metricas.py, gerador.py, baseline.py, saida.py, cli.py
│   └── algoritmos/
│       ├── guloso.py, hill_climbing.py, simulated_annealing.py
│       └── csp.py, pipeline.py
├── tests/test_motor.py
└── README.md
```

---

## Correções aplicadas em 22/08/2026

Três itens da revisão do protótipo (`claude/revisao-codigo-motor.md` no projeto):

**1. `metricas.gap_otimalidade` não afirma mais otimalidade sem lastro.**
O relatório passou a distinguir enumeração exaustiva de truncada. Quando a
busca para no limite, `motor_atingiu_otimo` vem `None`, a referência é rotulada
como "melhor solução conhecida" e uma ressalva explica que o gap calculado é
**limite inferior** do gap real — o ótimo verdadeiro é menor ou igual à
referência, logo o número subestima o afastamento.

**2. Espaços de busca alinhados.** O padrão de `extras_max` passou de 1 para 0,
igualando a enumeração ao espaço que o motor percorre em cardinalidade fixa. O
relatório informa as cardinalidades dos dois lados e sinaliza `espacos_compativeis`.
Na instância reduzida a enumeração agora fecha em 6.561 soluções sem truncar, e a
afirmação de otimalidade passa a ter lastro.

**3. Hora noturna calculada pela interseção real com a janela legal.**
`Turno.duracao_legal` aplicava o fator 60/52,5 ao turno inteiro. Agora
`_particao_noturna` separa a presença em parcelas noturna e diurna — período das
22h às 5h (art. 73, § 2º da CLT) mais a prorrogação prevista na Súmula 60, II do
TST —, e o fator incide apenas sobre a parcela noturna. O cálculo é memoizado por
`lru_cache`, já que é chamado a cada alocação.

Acompanham a mudança dois campos novos em `Turno`: `intervalo_horas` (intervalo
intrajornada, padrão 0,0) e a propriedade `duracao_trabalhada` (presença menos
intervalo). `duracao_horas` passa a significar **presença**, coerente com o
cálculo de `fim` que já existia. Com `intervalo_horas=0` o comportamento anterior
é preservado.

Verificação: a estrutura de turnos da Tabela 4 do TCC é reproduzida exatamente.

| Equipe | Horário | Presença | Trabalhada | Computada |
|---|---|---|---|---|
| Matutino | 05h40–15h28 | 9h48 | 8h48 | 8h48 |
| Comercial | 08h00–17h48 | 9h48 | 8h48 | 8h48 |
| Vespertino | 12h12–22h00 | 9h48 | 8h48 | 8h48 |
| Noturno | 21h40–06h00 | 8h20 | 7h20 | 8h20 |

**4. `gerador.JANELAS` alinhado à escala real.** Os quatro turnos genéricos de
8h (às 6h, 9h, 14h e 22h) foram substituídos pelos horários da tabela acima, com
intervalo intrajornada de uma hora. A cobertura permanece contínua: o noturno
encerra às 06h00 e o matutino inicia às 05h40.

Efeito medido no horizonte de 28 dias:

| | antes | depois |
|---|---|---|
| Jornada computada do noturno | 9h09 | 8h20 |
| Jornadas noturnas que cabem em 44h | 4 | **5** |
| Interjornada mínima praticada | 16h00 | 14h12 |
| Escala válida ao final | sim | sim |

O ganho principal é que a equipe noturna deixa de ser **estruturalmente**
limitada a quatro plantões por semana. Antes, aplicar o fator 60/52,5 ao turno
inteiro inflava a jornada computada para 9h09, e cinco plantões somavam 45,7h —
acima do teto. Agora somam 41h40 e o regime 5x2 é alcançável, como na operação
real. O limite passa a ser a demanda, não um artefato do cálculo.

A interjornada mínima praticada de 14h12 confirma o que o TCC afirma na
Subseção 6.5.1.3: a estrutura de turnos fixos já satisfaz o art. 66 da CLT por
construção, com folga de mais de três horas sobre o mínimo legal.

Suíte: 37 testes, 4 subtestes, todos passando.
