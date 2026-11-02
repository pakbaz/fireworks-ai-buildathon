"""Classifier (code) and business dial."""
import math
from .domain import num

def raw_risk(features, agree=True):
    """Uncalibrated risk from harness features; the scorer calibrates on dev."""
    if features["n_issues"]:
        return 0.98
    r = 0.03
    if features["n_unreadable"]:
        r = 0.5 if agree else 0.65
    if features["arith_off"]:
        r = max(r, 0.3)
    return r

CAT_DEFAULT = {"medical_device": 25, "medical_consumable": 3, "consumer": 1}

def cost_of_miss(at_risk_usd, wiki, policy, case_items=None):
    w = (policy or {}).get("category_weights") or CAT_DEFAULT
    cats = [it.get("category") for it in (wiki or {}).get("items") or []] if wiki else []
    cat_w = max([w.get(c, 1) for c in cats] or [1])
    sup = (wiki or {}).get("supplier") if wiki else None
    sup_w = 1.0
    if sup and num(sup.get("past_problem_rate")) is not None:
        lo, hi = (policy or {}).get("supplier_weight_range", [0.5, 2])
        sup_w = min(hi, max(lo, 0.5 + 15 * num(sup.get("past_problem_rate"))))
    return at_risk_usd * cat_w * sup_w

def decide(risk, at_risk_usd, wait, wiki, policy):
    """Escalate when expected loss from paying beats the cost of a review."""
    if wait and risk < 0.5:
        return "WAIT"
    review = float((policy or {}).get("review_cost_usd", 10))
    miss = cost_of_miss(max(at_risk_usd, 0.0), wiki, policy)
    return "ESCALATE" if risk * miss > (1 - risk) * review else "PAY"
