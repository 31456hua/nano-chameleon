"""Generate offline Plotly and a numerical angular-scattering figure."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import miepython
import numpy as np
from plotly.offline import get_plotlyjs


root = Path(__file__).resolve().parent / "demo_web"
root.mkdir(exist_ok=True)
(root / "plotly.min.js").write_text(get_plotlyjs(), encoding="utf-8")
theta = np.linspace(0, 2*np.pi, 361)
parallel, perpendicular = miepython.intensities(2.35-.015j, 260, 550, np.cos(theta), norm="one")
intensity = (parallel + perpendicular) / 2
fig, ax = plt.subplots(figsize=(4, 3), subplot_kw={"projection": "polar"}, dpi=160)
fig.patch.set_facecolor("#f4f6f5")
ax.set_facecolor("#f4f6f5")
ax.plot(theta, intensity, color="#127767", linewidth=2)
ax.fill(theta, intensity, color="#127767", alpha=.12)
ax.set_theta_zero_location("N")
ax.set_yticklabels([])
ax.tick_params(labelsize=8, colors="#646e68")
ax.grid(color="#d5ddd8", linewidth=.5)
ax.spines["polar"].set_color("#d5ddd8")
fig.tight_layout(pad=1.1)
fig.savefig(root / "angular-scattering.png")
plt.close(fig)
