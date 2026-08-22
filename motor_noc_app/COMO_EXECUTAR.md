# Como executar o motor

Guia de demonstração. Todos os tempos abaixo foram medidos; nenhum comando
precisa de internet, instalação ou permissão especial.

---

## 1. Requisitos

**Python 3.10 ou superior. Só isso.**

O protótipo usa exclusivamente a biblioteca padrão da linguagem — não há `pip
install`, `requirements.txt`, ambiente virtual nem dependência externa. Se a
máquina abre um terminal e tem Python, o motor roda.

Para conferir a versão:

```bash
python3 --version
```

No Windows, troque `python3` por `python` em todos os comandos deste guia.

## 2. Onde executar

Todos os comandos são disparados **de dentro da pasta `motor_noc_app`**, que é a
que contém o diretório `motor_noc`:

```bash
cd motor_noc_app
```

Se aparecer `No module named motor_noc`, o terminal está na pasta errada. Confira
com `ls` (ou `dir` no Windows): você deve enxergar as pastas `motor_noc` e
`tests`.

## 3. Verificação rápida

```bash
python3 -m motor_noc.cli --help
```

Lista os seis comandos disponíveis. Se isso funcionar, todo o resto funciona.

---

## 4. Roteiro de demonstração (cerca de 4 minutos)

A sequência abaixo cobre o trabalho inteiro, do resultado principal às métricas
de validação, e cabe no tempo de uma arguição.

### Passo 1 — A escala otimizada (3,5 s)

```bash
python3 -m motor_noc.cli executar --dias 28 --grade --saida saida/
```

É o comando principal. Produz o relatório completo em tela e grava sete arquivos
em `saida/`.

**O que apontar na tela:**

- A tabela **Evolução por Estágio** mostra o custo caindo de 0,4685 para 0,2993
  ao longo dos quatro estágios, com a coluna `Viol.` em zero desde o primeiro.
  Esse zero é o argumento central: a busca nunca sai da região factível.
- A seção **Componentes da Função Objetivo** exibe os valores brutos e
  normalizados lado a lado — útil se perguntarem como critérios em unidades
  diferentes (horas, contagens, alertas) foram combinados.
- A **grade visual** ao final mostra os 31 analistas agrupados por equipe fixa,
  com um caractere por dia. Cada analista só aparece no turno do seu grupo, o que
  torna a restrição de turno fixo visível a olho nu.

**O que mostrar em disco** (`ls saida/`):

| Arquivo | Conteúdo |
|---|---|
| `escala.csv` | A escala completa, uma linha por alocação — é o que a gerência usaria |
| `grade.txt` | A grade visual em texto |
| `cargas.csv` | Carga horária por analista |
| `ganho_por_estagio.csv` | Métrica 5.1(b) |
| `curva_convergencia.csv` | Métrica 5.1(d), pronta para plotar |
| `relatorio.txt` | O relatório de tela, salvo |
| `resumo.json` | Tudo em JSON, para consumo programático |

O `escala.csv` costuma ser o mais convincente: abre no Excel e é uma escala de
verdade, com data, dia da semana, turno, horário, analista, nível e volume de
alertas.

### Passo 2 — Contra a escala manual (3,6 s)

```bash
python3 -m motor_noc.cli comparar --dias 28
```

Compara o motor com uma escala montada por rodízio, que reproduz a prática
manual. Corresponde à métrica 5.1(a) e à Seção de Resultados do TCC.

**Diga antes que perguntem:** o motor melhora a equidade (amplitude de carga por
equipe cai de 77,4 h para 27,1 h) e **piora a cobertura de alertas em 70,5%**.
Isso não é falha — é a troca que a ponderação escolhida determina, e a fronteira
de compromisso no TCC mostra que existe ponto de operação melhor que o manual em
ambos os critérios. Assumir isso de saída é mais forte do que ser confrontado.

### Passo 3 — O motor acerta o ótimo (0,6 s)

```bash
python3 -m motor_noc.cli gap
```

Numa instância pequena, o espaço de soluções factíveis é percorrido por
enumeração exaustiva e o resultado do motor é confrontado com o ótimo global.

**O que apontar:** `enumeracao_exaustiva: True`, `espacos_compativeis: True`,
`ressalvas: []` e `gap_percentual` na ordem de 10⁻¹¹ — que é ruído de ponto
flutuante, ou seja, a mesma solução. Vale destacar que o relatório só afirma
`motor_atingiu_otimo: True` quando as duas primeiras condições valem; se a
enumeração truncasse, o campo viria `None` e a ressalva apareceria.

### Passo 4 — Os pesos mudam a resposta (5,1 s)

```bash
python3 -m motor_noc.cli sensibilidade --dias 14 --passo 0.5
```

Mostra que equidade e cobertura são objetivos conflitantes: privilegiar um piora
o outro de forma sistemática. É o que justifica calibrar os pesos por AHP em vez
de arbitrá-los.

### Passo 5 (opcional) — A calibração por AHP

```bash
python3 -m motor_noc.cli ahp --eq-sen 3 --eq-cob 0.5 --sen-cob 0.25
```

Converte julgamentos pareados da gerência em pesos, verificando a razão de
consistência. Os três números são comparações par a par na escala de Saaty:
`--eq-sen 3` significa que equidade é moderadamente mais importante que
senioridade; `--eq-cob 0.5` significa que equidade é *menos* importante que
cobertura.

A saída traz `RC: 0,0158` e a mensagem `Julgamentos CONSISTENTES (RC ≤ 0,10)`.
Para mostrar a verificação funcionando, informe julgamentos contraditórios — por
exemplo `--eq-sen 9 --eq-cob 9 --sen-cob 9` — e o RC estoura o limite.

Os pesos obtidos alimentam o comando `executar`:

```bash
python3 -m motor_noc.cli executar --dias 28 --alpha 0.32 --delta 0.12 --lam 0.56
```

---

## 5. Se pedirem para ver os testes

```bash
python3 -m pytest tests/ -q
```

37 testes, cerca de **1 minuto**. É longo demais para rodar durante a arguição —
se for mostrar, dispare antes e deixe o resultado na tela.

Se o `pytest` não estiver instalado, funciona também com a biblioteca padrão:

```bash
python3 -m unittest discover -s tests -q
```

## 6. Se pedirem o teste de estresse

```bash
python3 -m motor_noc.cli benchmark
```

Executa horizontes de 7, 14, 28 e 56 dias e reporta tempo e memória. Leva cerca
de **1 minuto**, sendo que só o caso de 56 dias responde por 40 s. Também é
melhor rodar antes.

---

## 7. Tabela de tempos

| Comando | Tempo | Serve para demo ao vivo? |
|---|---|---|
| `--help` | instantâneo | sim |
| `gap` | 0,6 s | sim |
| `executar --dias 7` | 1,5 s | sim |
| `executar --dias 28 --grade --saida saida/` | 3,5 s | sim |
| `comparar --dias 28` | 3,6 s | sim |
| `sensibilidade --dias 14 --passo 0.5` | 5,1 s | sim |
| `ahp ...` | instantâneo | sim |
| `pytest tests/ -q` | 63 s | rodar antes |
| `benchmark` | 62 s | rodar antes |

---

## 8. Perguntas prováveis

**"Os resultados são reproduzíveis?"**
Sim, integralmente. Rode o mesmo comando duas vezes: a saída é idêntica. O
gerador de instâncias e todos os sorteios da busca derivam de uma semente fixa,
declarada por `--seed`. Mude a semente e você obtém outra instância; mantenha e
obtém sempre o mesmo resultado. Isso é verificado por teste automatizado.

**"Isso funciona com dados reais?"**
O `escala.csv` já sai no formato que a operação usaria. A entrada, hoje, é
sintética: a estrutura de turnos, equipes e competências reproduz a operação
real, mas os volumes de alertas são sorteados em torno de médias por turno, e
não extraídos do histórico da plataforma de ITSM. Isso está declarado na seção
de validade externa do TCC, e a validação sobre histórico real consta como
trabalho futuro.

**"Por que não usar um solver pronto, como o OR-Tools?"**
Porque o objetivo não se esgota em obter a escala. Um solver entregaria o
resultado e suprimiria o objeto de estudo, que é comparar empiricamente o
comportamento de cada família algorítmica sobre o mesmo problema — a curva de
convergência, o ganho incremental por estágio, o efeito da vizinhança. A
comparação com método exato continua existindo, mas como referência de qualidade
no comando `gap`, e não como método de resolução.

**"Quanto tempo leva numa escala real?"**
Onze segundos para o horizonte de 28 dias, com menos de 1 MB de memória, medido
pelo `benchmark`. Isso viabiliza uso interativo: a gerência pode testar várias
configurações de peso antes de fixar a escala do mês.

**"E se o volume de alertas dobrar?"**
```bash
python3 -m motor_noc.cli executar --dias 28 --volume 2.0
```
O parâmetro `--volume` multiplica a demanda de alertas. Útil para demonstrar
comportamento sob pico.

---

## 9. Se algo der errado

| Sintoma | Causa provável | Solução |
|---|---|---|
| `No module named motor_noc` | terminal na pasta errada | `cd` até a pasta que contém `motor_noc/` |
| `python3: command not found` | Windows | use `python` no lugar de `python3` |
| `SyntaxError` na importação | Python anterior à 3.10 | atualize o Python |
| Acentos saem quebrados no Windows | terminal em code page antiga | rode `chcp 65001` antes |

Nenhum comando escreve fora da pasta indicada por `--saida`, e nenhum acessa a
rede. Rodar o motor não altera nada no sistema.
