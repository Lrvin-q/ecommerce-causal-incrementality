import sys
sys.path.insert(0, "src")
import numpy as np
from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.data.tables import build_analysis_frame

cfg = load_config()
for lvl in ("L0", "L1", "L2"):
    pop = dgp.assign_random(cfg, dgp.build(lvl, cfg, 0))
    t = pop.truth
    y_obs, pi_obs = pop.potential.observed(pop.treatment)
    print(
        lvl,
        "ate_profit=%.6f" % t.ate_profit,
        "ate_conv=%.6f" % t.ate_conversion,
        "A_ctrl=%.4f" % t.net_per_converted_control.mean(),
        "A_trt=%.4f" % t.net_per_converted_treated.mean(),
        "first_ctrl=%.4f" % t.net_per_order_control.mean(),
        "zero=%.4f" % float((pi_obs == 0).mean()),
        "sd=%.4f" % float(pi_obs.std(ddof=1)),
        "mean=%.4f" % float(pi_obs.mean()),
    )
    rep = pop.latent["repeat"]
    print("   repeat=%.4f all / %.4f among converted" % (float(rep.mean()), float(rep[y_obs == 1].mean())))

pop = dgp.assign_random(cfg, dgp.build("L1", cfg, 0))
df = build_analysis_frame(pop, cfg)
print("frame rows", len(df), "multi-order users", int((df["n_orders"] > 1).sum()))
print("conv rate", df.groupby("treatment")["converted"].mean().to_dict())
print("gmv per user", df.groupby("treatment")["gmv"].mean().to_dict())
print("profit per user", df.groupby("treatment")["net_profit"].mean().to_dict())
print("ITT profit = %.6f" % (df.loc[df.treatment == 1, "net_profit"].mean() - df.loc[df.treatment == 0, "net_profit"].mean()))
