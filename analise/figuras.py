"""Gera as figuras do capítulo de Resultados Obtidos (PDF vetorial)."""
import json
import os
import random
import statistics as st

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

AQUI = os.path.dirname(os.path.abspath(__file__))
DEST = os.path.join(AQUI, "figuras")
os.makedirs(DEST, exist_ok=True)

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.serif": ["DejaVu Serif"],
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9.5,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linewidth": 0.5,
        "axes.axisbelow": True,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
    }
)

PRETO, CINZA, CLARO = "#1a1a1a", "#6e6e6e", "#b8b8b8"
LARG = 5.6  # polegadas ~ 14,2 cm


def milhar(x, _=None):
    return f"{x:,.0f}".replace(",", ".")


def dec(casas):
    def _f(x, _=None):
        return f"{x:.{casas}f}".replace(".", ",")

    return _f


def carregar(nome):
    with open(os.path.join(AQUI, nome)) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Figura 1 — ganho incremental por estágio nas duas configurações
# --------------------------------------------------------------------------
def fig_estagios():
    d = carregar("exp_c_convergencia.json")
    rot = ["1. Guloso", "2. HC", "3. SA", "4. CSP"]
    fig, eixos = plt.subplots(1, 2, figsize=(LARG, 2.6))
    for eixo, cfg, titulo in zip(
        eixos,
        ["identicos", "lambda08"],
        [
            r"Pesos idênticos ($\alpha=\delta=\lambda=1/3$)",
            r"Ponto de operação ($\lambda=0{,}8$)",
        ],
    ):
        custos = [e["custo_F"] for e in d[cfg]["estagios"]]
        ganhos = [e["ganho_percentual"] for e in d[cfg]["estagios"]]
        barras = eixo.bar(
            rot, custos, color=[CLARO, CINZA, PRETO, CINZA],
            edgecolor=PRETO, linewidth=0.6,
        )
        barras[3].set_hatch("///")
        for i, (b, g) in enumerate(zip(barras, ganhos)):
            if i:
                txt = "0,00%" if abs(g) < 5e-3 else f"$-${g:.2f}%".replace(".", ",")
                eixo.annotate(
                    txt,
                    (b.get_x() + b.get_width() / 2, b.get_height()),
                    textcoords="offset points", xytext=(0, (3, 14, 3)[i - 1]),
                    ha="center", fontsize=7.5,
                )
        eixo.set_title(titulo)
        eixo.set_ylim(0, max(custos) * 1.28)
        eixo.tick_params(axis="x", labelsize=7.6)
        eixo.yaxis.set_major_formatter(FuncFormatter(dec(1)))
    eixos[0].set_ylabel("$F(X)$ ao final do estágio")
    fig.subplots_adjust(wspace=0.3)
    fig.savefig(f"{DEST}/fig_estagios.pdf")
    plt.close(fig)


# --------------------------------------------------------------------------
# Figura 2 — convergência do Simulated Annealing
# --------------------------------------------------------------------------
def fig_convergencia():
    d = carregar("exp_c_convergencia.json")
    fig, eixos = plt.subplots(1, 2, figsize=(LARG, 2.4))
    for eixo, cfg, titulo in zip(
        eixos, ["identicos", "lambda08"], ["Pesos idênticos", r"$\lambda = 0{,}8$"]
    ):
        c = d[cfg]["convergencia"]
        it = [r["iteracao"] for r in c]
        eixo.plot(it, [r["custo_atual"] for r in c], color=CLARO, lw=0.7,
                  label="solução corrente")
        eixo.plot(it, [r["custo_melhor"] for r in c], color=PRETO, lw=1.3,
                  label="melhor solução")
        eixo.set_title(titulo)
        eixo.set_xlabel("iteração")
        eixo.xaxis.set_major_formatter(FuncFormatter(milhar))
        eixo.yaxis.set_major_formatter(FuncFormatter(dec(2)))
    eixos[0].set_ylabel("$F(X)$")
    eixos[0].legend(loc="upper right", frameon=False)
    fig.subplots_adjust(wspace=0.32)
    fig.savefig(f"{DEST}/fig_convergencia.pdf")
    plt.close(fig)


# --------------------------------------------------------------------------
# Figura 3 — fronteira de compromisso
# --------------------------------------------------------------------------
def fig_fronteira():
    d = carregar("exp_b_fronteira.json")
    pts = sorted(d["motor"], key=lambda p: p["f_balanceamento"])
    bal = [p["f_balanceamento"] for p in pts]
    ate = [p["f_atendimento"] for p in pts]
    man = d["manual"]
    fig, eixo = plt.subplots(figsize=(LARG, 3.4))
    eixo.fill_between(
        [-200, man["f_balanceamento"]], 500, man["f_atendimento"],
        color=CLARO, alpha=0.40, lw=0, zorder=0,
    )
    eixo.plot(bal, ate, "-o", color=PRETO, lw=1.1, ms=4, mfc="white",
              label="fronteira do motor", zorder=3)
    desloc = {0.0: (9, -2), 0.3: (9, 4), 0.5: (9, 4), 0.8: (2, 9), 0.9: (-4, 10),
              1.0: (-8, 10)}
    for p in pts:
        if p["lam"] in desloc:
            eixo.annotate(
                rf"$\lambda={p['lam']:.1f}$".replace(".", "{,}"),
                (p["f_balanceamento"], p["f_atendimento"]),
                textcoords="offset points", xytext=desloc[p["lam"]],
                fontsize=7.5, zorder=4,
            )
    eixo.plot(man["f_balanceamento"], man["f_atendimento"], "s", color=PRETO, ms=7,
              label="escala manual por rodízio", zorder=4)
    eixo.axvline(man["f_balanceamento"], color=CINZA, ls=":", lw=0.8, zorder=1)
    eixo.axhline(man["f_atendimento"], color=CINZA, ls=":", lw=0.8, zorder=1)
    eixo.annotate(
        "região de dominância sobre a escala manual",
        (1480, 700), fontsize=7.5, ha="center", color="#3a3a3a", zorder=4,
    )
    eixo.set_xlabel(r"$f_{\rm balanceamento}$ — desequilíbrio de carga (menor é melhor)")
    eixo.set_ylabel("$f_{\\rm atendimento}$ — desajuste\nde cobertura (menor é melhor)")
    eixo.set_xlim(-200, 3450)
    eixo.set_ylim(600, 3150)
    eixo.xaxis.set_major_formatter(FuncFormatter(milhar))
    eixo.yaxis.set_major_formatter(FuncFormatter(milhar))
    eixo.legend(loc="upper right", frameon=False)
    fig.savefig(f"{DEST}/fig_fronteira.pdf")
    plt.close(fig)


# --------------------------------------------------------------------------
# Figura 4 — distribuição da carga horária por equipe
# --------------------------------------------------------------------------
def fig_cargas():
    d = carregar("exp_c_convergencia.json")
    equipes = d["equipes"]
    ordem = ["MATUTINO", "COMERCIAL", "VESPERTINO", "NOTURNO"]
    series = [("manual", CLARO, "escala manual"),
              ("identicos", CINZA, "motor, pesos idênticos"),
              ("lambda08", PRETO, r"motor, $\lambda=0{,}8$")]
    rng = random.Random(7)
    fig, eixo = plt.subplots(figsize=(LARG, 2.9))
    for i, eq in enumerate(ordem):
        ids = equipes[eq]
        for j, (fonte, cor, _) in enumerate(series):
            cargas = [d[fonte]["cargas"][a] for a in ids]
            centro = i + (j - 1) * 0.27
            xs = [centro + rng.uniform(-0.06, 0.06) for _ in cargas]
            eixo.plot(xs, cargas, "o", ms=3.2, mfc=cor, mec=PRETO, mew=0.4,
                      ls="none", zorder=3)
            eixo.hlines(st.fmean(cargas), centro - 0.11, centro + 0.11,
                        color=PRETO, lw=1.4, zorder=4)
            eixo.vlines(centro, min(cargas), max(cargas), color=CINZA, lw=0.7, zorder=2)
    eixo.set_xticks(range(len(ordem)))
    eixo.set_xticklabels([e.capitalize() for e in ordem])
    eixo.set_xlim(-0.55, len(ordem) - 0.45)
    eixo.set_ylabel("carga horária no período (h)")
    maniq = [plt.Line2D([], [], marker="o", ls="none", ms=4, mfc=c, mec=PRETO, mew=0.4)
             for _, c, _ in series]
    eixo.legend([*maniq], [r for _, _, r in series], loc="lower left", frameon=False,
                ncol=3, columnspacing=1.0, handlelength=1.0,
                bbox_to_anchor=(-0.01, 1.0))
    fig.savefig(f"{DEST}/fig_cargas.pdf")
    plt.close(fig)


# --------------------------------------------------------------------------
# Figura 5 — robustez sobre trinta instâncias
# --------------------------------------------------------------------------
def fig_robustez():
    d = carregar("exp_a_multisemente.json")
    criterios = [
        ("amplitude_media_por_equipe", "amplitude\nde carga"),
        ("f_balanceamento", r"$f_{\rm balanceamento}$"),
        ("f_atendimento", r"$f_{\rm atendimento}$"),
        ("custo_F", "$F(X)$"),
    ]
    fig, eixo = plt.subplots(figsize=(LARG, 2.8))
    larg = 0.34
    for k, (cfg, cor, rot) in enumerate(
        [("identicos", CINZA, "pesos idênticos"), ("lambda08", PRETO, r"$\lambda=0{,}8$")]
    ):
        medias, erros = [], []
        for campo, _ in criterios:
            dif = [
                100 * (l[cfg]["motor"][campo] - l[cfg]["manual"][campo])
                / l[cfg]["manual"][campo]
                for l in d
            ]
            medias.append(st.fmean(dif))
            erros.append(st.stdev(dif))
        x = [i + (k - 0.5) * larg for i in range(len(criterios))]
        eixo.bar(x, medias, larg, yerr=erros, capsize=2.5, color=cor,
                 edgecolor=PRETO, linewidth=0.6, label=rot,
                 error_kw={"lw": 0.8, "ecolor": "#303030"})
        for xi, m in zip(x, medias):
            eixo.annotate(f"{m:+.1f}%".replace(".", ","), (xi, m),
                          textcoords="offset points", xytext=(0, 7 if m > 0 else -13),
                          ha="center", fontsize=7)
    eixo.axhline(0, color=PRETO, lw=0.8)
    eixo.set_xticks(range(len(criterios)))
    eixo.set_xticklabels([r for _, r in criterios])
    eixo.set_ylabel("variação sobre a escala manual (%)")
    eixo.set_ylim(-108, 95)
    eixo.yaxis.set_major_formatter(FuncFormatter(dec(0)))
    eixo.legend(loc="lower right", frameon=False)
    fig.savefig(f"{DEST}/fig_robustez.pdf")
    plt.close(fig)


# --------------------------------------------------------------------------
# Figura 6 — escalabilidade
# --------------------------------------------------------------------------
def fig_escalabilidade():
    d = carregar("exp_d_escalabilidade.json")
    turnos = [l["turnos"] for l in d]
    tempo = [l["tempo_s"] for l in d]
    mem = [l["memoria_pico_mb"] for l in d]
    fig, eixo = plt.subplots(figsize=(LARG, 2.8))
    eixo.plot(turnos, tempo, "-o", color=PRETO, lw=1.1, ms=4, mfc="white",
              label="tempo de processamento")
    eixo.set_xlabel("número de turnos no horizonte")
    eixo.set_ylabel("tempo de processamento (s)")
    eixo.set_ylim(-4, max(tempo) * 1.22)
    eixo.set_xlim(0, 340)
    gem = eixo.twinx()
    gem.plot(turnos, mem, "--^", color=CINZA, lw=1.0, ms=4, mfc="white",
             label="pico de memória")
    gem.set_ylabel("pico de memória (MB)")
    gem.set_ylim(-0.12, max(mem) * 1.22)
    gem.grid(False)
    gem.yaxis.set_major_formatter(FuncFormatter(dec(1)))
    for x, y, l in zip(turnos, tempo, d):
        if l["dias"] in (7, 28, 56, 84):
            eixo.annotate(f"{l['dias']} dias", (x, y), textcoords="offset points",
                          xytext=(3, -12), ha="left", fontsize=7.5)
    linhas = eixo.get_lines() + gem.get_lines()
    eixo.legend(linhas, [l.get_label() for l in linhas], loc="upper left",
                frameon=False)
    fig.savefig(f"{DEST}/fig_escalabilidade.pdf")
    plt.close(fig)


if __name__ == "__main__":
    for fn in (fig_estagios, fig_convergencia, fig_fronteira,
               fig_cargas, fig_robustez, fig_escalabilidade):
        fn()
        print("ok:", fn.__name__)
