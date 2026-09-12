"""Causal optional January warm-up: battery idle, residual balanced online."""
from .question2 import config as cfg


def control_start_soc(initialization_mode, annual):
    if initialization_mode == "feb1_control_start":
        return cfg.CONTROL_START_SOC_KWH
    if initialization_mode != "jan1_continuous":
        raise ValueError("unknown initialization mode")
    if tuple(annual.dates[:31]) != cfg.ANNUAL_DATES[:31]:
        raise ValueError("January continuous initialization requires Jan 1-31")
    # No future observation is needed for a battery-idle policy.
    # Every January executed charge/discharge is zero, thus SOC remains 6000.
    current_soc = cfg.CONTROL_START_SOC_KWH
    for _day in annual.dates[:31]:
        for _slot in range(144):
            current_soc += cfg.ETA_CHARGE*0. - 0./cfg.ETA_DISCHARGE
    return current_soc


def warmup_rows(annual):
    control_start_soc("jan1_continuous",annual)
    return [dict(date=str(day), initial_soc_kwh=6000., terminal_soc_kwh=6000., charge_kwh=0., discharge_kwh=0.,
                 policy="battery_idle_online_grid_balance", formal_evaluation=False) for day in annual.dates[:31]]
