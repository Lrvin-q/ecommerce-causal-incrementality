import sys, time
sys.path.insert(0, "src")
import numpy as np
from causal_growth import dgp
from causal_growth.config import load_config
from causal_growth.estimate.cate import design_matrix
from causal_growth.estimate.obs import estimate_all

cfg = load_config()
for lam in (0.0, 0.5):
    t0 = time.perf_counter()
    pop = dgp.build("L3", cfg, 0, lam=lam)
    pop, _ = dgp.assign_observational(cfg, pop, lam=lam, index=0)
    X = design_matrix(pop)
    t = pop.treatment.astype(int)
    _, pi_obs = pop.potential.observed(t)
    t1 = time.perf_counter()
    est = estimate_all(pi_obs, t, X, cfg, alpha=0.05, seed=0)
    t2 = time.perf_counter()
    print("lam=%s build=%.2fs estimate=%.2fs -> %.2fs/rep" % (lam, t1 - t0, t2 - t1, t2 - t0))
print("projected total for 7 lambda x 100 reps: %.1f min" % ((7 * 100) * 0.33 / 60))
