# Rotinas de análise do Capítulo 7

Scripts que produziram os dados do capítulo de Resultados Obtidos do TCC, e os
dados brutos resultantes. Existem para que qualquer número do capítulo possa ser
recalculado e qualquer figura, regerada.

## Como reexecutar

Todos os comandos são disparados **da raiz do repositório** (a pasta que contém
`motor_noc_app/` e `analise/`), com o pacote visível ao Python:

```bash
export PYTHONPATH=$PWD/motor_noc_app     # Windows: set PYTHONPATH=%CD%\motor_noc_app

python3 analise/experimentos.py c        # estágios, convergência e cargas (E1)
python3 analise/experimentos.py b        # fronteira de compromisso, 11 pontos (E1)
python3 analise/experimentos.py a        # robustez, 30 instâncias (E2)
python3 analise/exp_e.py                 # dominância em lambda 0,85/0,90/0,95 (E2)
python3 analise/exp_d.py                 # escalabilidade, 8 horizontes (E4)
python3 analise/estatisticas.py          # Tabelas 7.6 e 7.8, a partir de a e exp_e
python3 analise/figuras.py               # as seis figuras, em analise/figuras/
```

Tempos aproximados: `c` 10 s, `b` 40 s, `a` 4 min, `exp_e` 5 min, `exp_d` 4 min,
`estatisticas.py` e `figuras.py` instantâneos. Os experimentos `a`, `b` e `exp_e`
usam dois processos.

Cada script grava seus dados nesta pasta, qualquer que seja o diretório de onde
for chamado. `estatisticas.py` consome os arquivos de `a` e de `exp_e`, então
depende de os dois terem rodado antes.

## Dependências

Os experimentos usam apenas a biblioteca padrão do Python 3.10 ou superior.
Duas exceções: `figuras.py` exige `matplotlib`, e `estatisticas.py` usa `scipy`
para os testes de hipótese — sem ele, ainda imprime as estatísticas descritivas e
avisa que os valores de *p* não foram calculados.

## Correspondência com o capítulo

| Arquivo de dados | Alimenta |
|---|---|
| `exp_c_convergencia.json` | Tabelas 7.3 e 7.4; Figuras 7.1, 7.2 e 7.3 |
| `exp_a_multisemente.json` | Tabela 7.6; Figura 7.4 |
| `exp_b_fronteira.json` | Tabela 7.7; Figura 7.5 |
| `exp_e_dominancia.json` | Tabela 7.8 |
| `exp_d_escalabilidade.json` | Tabela 7.11; Figura 7.6 |

A numeração de tabelas e figuras segue a compilação de referência e pode
deslocar-se caso o texto seja alterado.

## Conjuntos experimentais

- **E1** — instância de referência, semente 42, 28 dias.
- **E2** — trinta instâncias independentes, sementes 1 a 30, 28 dias.
- **E3** — instância reduzida para o gap de otimalidade (comando `gap` da CLI).
- **E4** — oito horizontes, de 7 a 84 dias.

Toda execução é determinística: fixada a semente, a saída se repete. Os tempos de
processamento, por dependerem da máquina, são a única grandeza que não se
reproduz exatamente.
