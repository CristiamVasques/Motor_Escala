"""Consolida as estatisticas das Tabelas 7.6 e 7.8 do Capitulo de Resultados.

Le os arquivos produzidos por `experimentos.py a` e por `exp_e.py` e imprime,
nos mesmos termos em que aparecem no texto, as medias, os desvios-padrao, os
coeficientes de variacao, os intervalos de confianca de 95% e os testes de
postos sinalizados de Wilcoxon para amostras pareadas.

Requer scipy apenas para os testes de hipotese. Sem scipy, o script ainda
imprime as estatisticas descritivas e informa quantas instancias favorecem
cada lado, o que basta para reproduzir as colunas da Tabela 7.6.
"""
import json
import os
import statistics as st

try:
    from scipy import stats as _scipy
except ImportError:  # pragma: no cover - ambiente sem scipy
    _scipy = None

AQUI = os.path.dirname(os.path.abspath(__file__))

CAMPOS = [
    ("custo_F", "Custo F(X)"),
    ("f_balanceamento", "f_balanceamento"),
    ("f_atendimento", "f_atendimento"),
    ("amplitude_media_por_equipe", "Amplitude media por equipe (h)"),
    ("desvio_padrao_medio_por_equipe", "Desvio-padrao medio por equipe (h)"),
    ("alocacoes", "Alocacoes"),
]
# t de Student, 95%, 29 graus de liberdade
T_29 = 2.0452


def carregar(nome):
    with open(os.path.join(AQUI, nome), encoding="utf-8") as fh:
        return json.load(fh)


def _ic95(amostra):
    return T_29 * st.stdev(amostra) / len(amostra) ** 0.5


def _p_wilcoxon(a, b):
    if _scipy is None:
        return None
    return _scipy.wilcoxon(a, b).pvalue


def tabela_robustez():
    dados = carregar("exp_a_multisemente.json")
    print("=" * 78)
    print("TABELA 7.6 - Comportamento do motor sobre trinta instancias")
    print("=" * 78)
    for cfg, rotulo in (("identicos", "Pesos identicos"), ("lambda08", "lambda = 0,8")):
        print(f"\n  {rotulo}")
        print(f"  {'Indicador':<36}{'Media':>10}{'DP':>9}{'CV':>8}{'IC95':>9}")
        for chave, nome in CAMPOS:
            motor = [l[cfg]["motor"][chave] for l in dados]
            media, desvio = st.fmean(motor), st.stdev(motor)
            cv = 100 * desvio / media if media else 0.0
            print(
                f"  {nome:<36}{media:>10.2f}{desvio:>9.2f}"
                f"{cv:>7.1f}%{_ic95(motor):>9.2f}"
            )
        tempos = [l[cfg]["tempo_s"] for l in dados]
        print(f"  {'Tempo de execucao (s)':<36}{st.fmean(tempos):>10.2f}"
              f"{st.stdev(tempos):>9.2f}")

        print(f"\n  {'Variacao sobre a escala manual':<36}{'Media':>10}{'DP':>9}"
              f"{'p':>12}{'Favoravel':>12}")
        for chave, nome in CAMPOS:
            motor = [l[cfg]["motor"][chave] for l in dados]
            manual = [l[cfg]["manual"][chave] for l in dados]
            dif = [100 * (m - n) / n for m, n in zip(motor, manual)]
            favoraveis = sum(1 for m, n in zip(motor, manual) if m < n)
            p = _p_wilcoxon(motor, manual)
            p_txt = "   (sem scipy)" if p is None else f"{p:>12.1e}"
            print(f"  {nome:<36}{st.fmean(dif):>+10.2f}{st.stdev(dif):>9.2f}"
                  f"{p_txt}{favoraveis:>9} de 30")

        validas = sum(1 for l in dados if l[cfg]["valida"])
        superq = [l[cfg]["motor"]["alocacoes_superqualificadas"] for l in dados]
        viol = max(l[cfg]["motor"]["violacoes_rigidas"] for l in dados)
        print(f"\n  Escalas validas: {validas} de {len(dados)}"
              f" | violacoes rigidas (max): {viol:.0f}"
              f" | alocacoes superqualificadas: {min(superq):.0f} a {max(superq):.0f}")


def tabela_dominancia():
    dados = carregar("exp_e_dominancia.json")
    print("\n" + "=" * 78)
    print("TABELA 7.8 - Posicao do motor em relacao a escala manual")
    print("=" * 78)
    print(f"  {'Indicador':<40}" + "".join(f"{f'lambda={l}':>13}"
                                           for l in ("0.85", "0.9", "0.95")))
    linhas = {
        "Variacao de f_atendimento (%)": ("f_atendimento", True),
        "Variacao de f_balanceamento (%)": ("f_balanceamento", True),
        "Amplitude media por equipe (h)": ("amplitude_media_por_equipe", False),
    }
    for nome, (chave, percentual) in linhas.items():
        celulas = []
        for lam in ("0.85", "0.9", "0.95"):
            motor = [l[lam]["motor"][chave] for l in dados]
            if percentual:
                manual = [l[lam]["manual"][chave] for l in dados]
                dif = [100 * (m - n) / n for m, n in zip(motor, manual)]
                celulas.append(f"{st.fmean(dif):>+7.2f}+-{st.stdev(dif):.2f}")
            else:
                celulas.append(f"{st.fmean(motor):>13.2f}")
        print(f"  {nome:<40}" + "".join(f"{c:>13}" for c in celulas))

    for nome, chave in (("Significancia p - atendimento", "f_atendimento"),
                        ("Significancia p - balanceamento", "f_balanceamento")):
        celulas = []
        for lam in ("0.85", "0.9", "0.95"):
            motor = [l[lam]["motor"][chave] for l in dados]
            manual = [l[lam]["manual"][chave] for l in dados]
            p = _p_wilcoxon(motor, manual)
            celulas.append("(sem scipy)" if p is None else f"{p:.3f}")
        print(f"  {nome:<40}" + "".join(f"{c:>13}" for c in celulas))

    celulas = []
    for lam in ("0.85", "0.9", "0.95"):
        dom = sum(
            1 for l in dados
            if l[lam]["motor"]["f_atendimento"] <= l[lam]["manual"]["f_atendimento"]
            and l[lam]["motor"]["f_balanceamento"] < l[lam]["manual"]["f_balanceamento"]
        )
        celulas.append(f"{dom} de 30")
    print(f"  {'Instancias em que o motor domina':<40}"
          + "".join(f"{c:>13}" for c in celulas))


if __name__ == "__main__":
    tabela_robustez()
    tabela_dominancia()
    if _scipy is None:
        print("\nAviso: scipy nao encontrado; os valores de p nao foram calculados.")
