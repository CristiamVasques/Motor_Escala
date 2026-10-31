"""Experimento D - escalabilidade, com a mesma metodologia da tabela aprovada."""
import json
import os

from motor_noc import metricas

SAIDA = os.path.dirname(os.path.abspath(__file__))
med = metricas.benchmark((7, 14, 21, 28, 42, 56, 70, 84))
linhas = [m.__dict__ for m in med]
for l in linhas:
    print(
        f"  {l['dias']:>3} dias | {l['turnos']:>3} turnos | {l['tempo_s']:6.2f}s"
        f" | {l['memoria_pico_mb']:.2f} MB | viol={l['violacoes_rigidas']}",
        flush=True,
    )
with open(f"{SAIDA}/exp_d_escalabilidade.json", "w") as fh:
    json.dump(linhas, fh, indent=1)
