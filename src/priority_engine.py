"""
StockSage AI - Priority Engine (Phase 6B)

Determines retail management priority by scoring inventory risk, sales anomalies,
and financial impact estimates using pure deterministic rules.
"""

import copy
import math
from typing import Optional, Dict, Any, List


PRIORITY_CONFIG = {
    "weights": {
        "severity": 0.35,
        "impact": 0.30,
        "urgency": 0.25,
        "confidence": 0.10
    }
}

# Monetary Impact Bands (in INR ₹) mapping to Impact Scores (0–100)
IMPACT_BANDS = [
    (0.0, 0),
    (1.0, 20),
    (1000.0, 40),
    (3000.0, 60),
    (6000.0, 75),
    (10000.0, 90),
    (20000.0, 100)
]


def validate_priority_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validate and merge priority weights configuration.
    Enforces non-negative weights summing to 1.0 within floating point tolerance.
    Raises ValueError if weights are invalid.
    """
    merged = copy.deepcopy(PRIORITY_CONFIG)
    if config and "weights" in config:
        merged["weights"].update(config["weights"])

    weights = merged["weights"]
    required_keys = ["severity", "impact", "urgency", "confidence"]
    for key in required_keys:
        if key not in weights:
            raise ValueError(f"Missing priority weight for key: '{key}'.")
        val = weights[key]
        if not isinstance(val, (int, float)):
            raise ValueError(f"Weight for '{key}' must be numeric, got {type(val)}.")
        if val < 0.0 or val > 1.0:
            raise ValueError(f"Weight for '{key}' must be between 0.0 and 1.0, got {val}.")

    total_weight = sum(weights[k] for k in required_keys)
    if not math.isclose(total_weight, 1.0, abs_tol=1e-5):
        raise ValueError(f"Priority weights must sum to 1.0, got {total_weight:.4f}.")

    return merged


def get_priority_label(score: float) -> str:
    """
    Map final priority score (0–100) to Priority Level Label.
    Boundary rules:
      80.00 – 100.00 -> Critical Priority
      65.00 – 79.99  -> High Priority
      50.00 – 64.99  -> Medium Priority
      30.00 – 49.99  -> Low Priority
      0.00  – 29.99  -> Monitor
    """
    if score >= 80.0:
        return "Critical Priority"
    elif score >= 65.0:
        return "High Priority"
    elif score >= 50.0:
        return "Medium Priority"
    elif score >= 30.0:
        return "Low Priority"
    else:
        return "Monitor"


def score_severity(
    issue_type: str,
    severity_level: Optional[str] = None,
    percentage_change: Optional[float] = None,
    is_overstock: bool = False
) -> float:
    """
    Pure helper function to compute deterministic Severity Score (0–100).
    """
    itype = str(issue_type).lower()

    if itype == "stockout_risk":
        s_level = str(severity_level).lower() if severity_level else ""
        if s_level == "critical":
            return 100.0
        elif s_level == "high":
            return 80.0
        elif s_level == "medium":
            return 60.0
        else:
            return 0.0

    elif itype == "overstock":
        s_level = str(severity_level).lower() if severity_level else ""
        if s_level == "severe":
            return 85.0
        elif s_level == "high":
            return 70.0
        elif s_level == "moderate":
            return 55.0
        elif is_overstock:
            return 65.0
        else:
            return 0.0

    elif itype == "non_moving":
        return 85.0

    elif itype == "slow_moving":
        return 55.0

    elif itype in ["sales_spike", "spike"]:
        if percentage_change is None:
            return 0.0
        pct = float(percentage_change)
        if pct >= 100.0:
            return 85.0
        elif pct >= 75.0:
            return 70.0
        elif pct >= 50.0:
            return 55.0
        else:
            return 0.0

    elif itype in ["sales_drop", "drop"]:
        if percentage_change is None:
            return 0.0
        pct = float(percentage_change)
        if pct <= -60.0:
            return 90.0
        elif pct <= -45.0:
            return 75.0
        elif pct <= -30.0:
            return 60.0
        else:
            return 0.0

    elif itype == "new_activity":
        return 50.0

    return 0.0


def score_business_impact(impact_value: Optional[float]) -> float:
    """
    Pure helper function to convert monetary business impact (in ₹) into 0–100 Impact Score.
    Uses fixed deterministic bands.
      <= 0 or None      -> 0
      ₹1–₹999.99        -> 20
      ₹1,000–₹2,999.99  -> 40
      ₹3,000–₹5,999.99  -> 60
      ₹6,000–₹9,999.99  -> 75
      ₹10,000–₹19,999.99-> 90
      ₹20,000 and above -> 100
    """
    if impact_value is None or impact_value <= 0:
        return 0.0

    val = float(impact_value)
    if val >= 20000.0:
        return 100.0
    elif val >= 10000.0:
        return 90.0
    elif val >= 6000.0:
        return 75.0
    elif val >= 3000.0:
        return 60.0
    elif val >= 1000.0:
        return 40.0
    elif val >= 1.0:
        return 20.0
    else:
        return 0.0


def score_urgency(
    issue_type: str,
    days_remaining: Optional[float] = None,
    coverage_days: Optional[float] = None,
    percentage_change: Optional[float] = None,
    is_overstock: bool = False
) -> float:
    """
    Pure helper function to compute deterministic Urgency Score (0–100).
    """
    itype = str(issue_type).lower()

    if itype == "stockout_risk":
        if days_remaining is None:
            return 0.0
        d = float(days_remaining)
        if d <= 1.0:
            return 100.0
        elif 1.0 < d < 3.0:
            return 95.0
        elif 3.0 <= d < 5.0:
            return 80.0
        elif 5.0 <= d < 7.0:
            return 60.0
        else:
            return 0.0

    elif itype == "overstock":
        cov = coverage_days if coverage_days is not None else days_remaining
        if cov is not None:
            c = float(cov)
            if c >= 90.0:
                return 75.0
            elif c >= 60.0:
                return 65.0
            elif c >= 45.0:
                return 55.0
            elif c >= 30.0:
                return 45.0
            else:
                return 0.0
        elif is_overstock:
            return 50.0
        else:
            return 0.0

    elif itype == "non_moving":
        return 60.0

    elif itype == "slow_moving":
        return 45.0

    elif itype in ["sales_drop", "drop"]:
        if percentage_change is None:
            return 0.0
        pct = float(percentage_change)
        if pct <= -60.0:
            return 80.0
        elif pct <= -45.0:
            return 70.0
        elif pct <= -30.0:
            return 60.0
        else:
            return 0.0

    elif itype in ["sales_spike", "spike"]:
        if percentage_change is None:
            return 0.0
        pct = float(percentage_change)
        if pct >= 100.0:
            return 70.0
        elif pct >= 75.0:
            return 65.0
        elif pct >= 50.0:
            return 55.0
        else:
            return 0.0

    elif itype == "new_activity":
        return 40.0

    return 0.0


def score_confidence(issue: Dict[str, Any]) -> float:
    """
    Pure helper function to compute Confidence Score (0–100) based on machine-readable
    data completeness and sufficiency metrics.
    """
    if "confidence_score" in issue and isinstance(issue["confidence_score"], (int, float)):
        c_score = float(issue["confidence_score"])
        if 0.0 <= c_score <= 100.0:
            return c_score

    itype = str(issue.get("issue_type", issue.get("anomaly_type", ""))).lower()

    # Anomaly detector output confidence
    if itype in ["sales_spike", "spike", "sales_drop", "drop"]:
        anomaly_type = issue.get("anomaly_type", itype)
        if anomaly_type == "low_baseline":
            return 40.0
        elif anomaly_type == "insufficient_data":
            return 20.0
        elif anomaly_type == "new_activity":
            return 60.0
        elif anomaly_type == "no_activity":
            return 50.0
        else:
            # Baseline availability check
            avail_weeks = issue.get("available_baseline_weeks", 6)
            if avail_weeks >= 6:
                return 90.0
            elif avail_weeks >= 3:
                return 75.0
            else:
                return 40.0

    elif itype == "new_activity":
        return 60.0

    elif itype == "low_baseline":
        return 40.0

    elif itype == "insufficient_data":
        return 20.0

    # Risk engine inventory issue confidence
    data_quality = issue.get("data_quality", {})
    is_sufficient = data_quality.get("is_sufficient_data", True) if isinstance(data_quality, dict) else True
    hist_days = issue.get("historical_days", 30)

    if is_sufficient and hist_days >= 30:
        return 95.0
    elif hist_days >= 14:
        return 75.0
    else:
        return 25.0


def calculate_priority_score(
    severity_score: float,
    impact_score: float,
    urgency_score: float,
    confidence_score: float,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Calculate weighted priority score from component scores (0–100).
    Raises ValueError if any component score is outside [0, 100].
    """
    cfg = validate_priority_config(config)
    weights = cfg["weights"]

    scores = {
        "severity": severity_score,
        "impact": impact_score,
        "urgency": urgency_score,
        "confidence": confidence_score
    }

    for name, s in scores.items():
        if not isinstance(s, (int, float)):
            raise ValueError(f"Component score '{name}' must be numeric, got {type(s)}.")
        if s < 0.0 or s > 100.0:
            raise ValueError(f"Component score '{name}' must be between 0 and 100, got {s}.")

    raw_score = (
        (severity_score * weights["severity"]) +
        (impact_score * weights["impact"]) +
        (urgency_score * weights["urgency"]) +
        (confidence_score * weights["confidence"])
    )

    clamped_raw = max(0.0, min(100.0, raw_score))
    display_score = int(round(clamped_raw))

    return {
        "raw_priority_score": round(clamped_raw, 4),
        "priority_score": display_score
    }


def normalize_issue_for_priority(
    issue: Dict[str, Any],
    impact_result: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Normalizes Phase 4 (risk) and Phase 5 (anomaly) issue structures into a standard
    machine-readable format for Phase 6B priority scoring.
    """
    norm = copy.deepcopy(issue)

    # Normalize issue_type & anomaly_type
    raw_type = norm.get("issue_type")
    if not raw_type and "classification" in norm and isinstance(norm["classification"], dict):
        raw_type = norm["classification"].get("anomaly_type")
    if not raw_type:
        raw_type = norm.get("anomaly_type", "")

    raw_type = str(raw_type).lower()
    if raw_type in ["spike", "sales_spike"]:
        issue_type = "sales_spike"
    elif raw_type in ["drop", "sales_drop"]:
        issue_type = "sales_drop"
    else:
        issue_type = raw_type

    norm["issue_type"] = issue_type
    if "anomaly_type" not in norm:
        norm["anomaly_type"] = raw_type

    # Extract percentage change if nested
    if norm.get("percentage_change") is None and "change" in norm and isinstance(norm["change"], dict):
        norm["percentage_change"] = norm["change"].get("percentage_change")

    # Extract baseline weeks if nested
    if norm.get("available_baseline_weeks") is None and "historical_baseline" in norm and isinstance(norm["historical_baseline"], dict):
        norm["available_baseline_weeks"] = norm["historical_baseline"].get("baseline_weeks", 6)

    # Extract days remaining / coverage
    days_rem = norm.get("days_of_stock_remaining", norm.get("days_remaining", None))
    norm["days_remaining"] = days_rem

    coverage = norm.get("coverage_days", norm.get("threshold_days", days_rem))
    norm["coverage_days"] = coverage

    # Extract impact value if provided via impact_result or direct issue
    impact_val = None
    impact_lbl = None
    impact_avail = True
    impact_reason = None

    if impact_result is not None:
        impact_val = impact_result.get("impact_value")
        impact_lbl = impact_result.get("impact_label")
        if impact_val is None:
            impact_avail = False
            impact_reason = "Monetary impact unavailable."
    elif "impact_value" in norm:
        impact_val = norm.get("impact_value")
        impact_lbl = norm.get("impact_label")
        if impact_val is None:
            impact_avail = False
            impact_reason = "Monetary impact unavailable."

    norm["impact_value"] = impact_val
    norm["impact_label"] = impact_lbl
    norm["impact_available"] = impact_avail
    norm["impact_reason"] = impact_reason

    return norm


def score_issue_priority(
    issue: Dict[str, Any],
    impact_result: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Score a single normalized issue and generate complete breakdown and explainable factors.
    """
    cfg = validate_priority_config(config)
    weights = cfg["weights"]
    norm = normalize_issue_for_priority(issue, impact_result)

    issue_type = norm["issue_type"]

    # Non-actionable issue check
    non_actionable_types = ["normal", "safe", "no_activity", "insufficient_data"]

    # Standalone low_baseline is non-actionable unless a separate valid risk exists
    is_standalone_low_baseline = (issue_type == "low_baseline")

    if issue_type in non_actionable_types or is_standalone_low_baseline:
        return {
            "issue_type": issue_type,
            "actionable": False,
            "severity_score": 0.0,
            "impact_score": 0.0,
            "urgency_score": 0.0,
            "confidence_score": 0.0,
            "raw_priority_score": 0.0,
            "priority_score": 0,
            "priority_label": "Monitor",
            "impact_available": norm.get("impact_available", True),
            "score_breakdown": {
                "severity": {"score": 0.0, "weight": weights["severity"], "weighted_score": 0.0},
                "impact": {"score": 0.0, "weight": weights["impact"], "weighted_score": 0.0},
                "urgency": {"score": 0.0, "weight": weights["urgency"], "weighted_score": 0.0},
                "confidence": {"score": 0.0, "weight": weights["confidence"], "weighted_score": 0.0}
            },
            "priority_factors": [
                {
                    "factor": "Non-Actionable",
                    "score": 0,
                    "reason": f"Issue condition '{issue_type}' is monitored but does not require active priority scoring."
                }
            ]
        }

    # Compute component scores
    sev_score = score_severity(
        issue_type=issue_type,
        severity_level=norm.get("severity"),
        percentage_change=norm.get("percentage_change"),
        is_overstock=norm.get("is_overstock", False)
    )

    imp_score = score_business_impact(norm.get("impact_value"))

    urg_score = score_urgency(
        issue_type=issue_type,
        days_remaining=norm.get("days_remaining"),
        coverage_days=norm.get("coverage_days"),
        percentage_change=norm.get("percentage_change"),
        is_overstock=norm.get("is_overstock", False)
    )

    conf_score = score_confidence(norm)

    calc = calculate_priority_score(sev_score, imp_score, urg_score, conf_score, cfg)
    raw_priority = calc["raw_priority_score"]
    priority_score = calc["priority_score"]
    priority_label = get_priority_label(raw_priority)

    w_sev = weights["severity"]
    w_imp = weights["impact"]
    w_urg = weights["urgency"]
    w_conf = weights["confidence"]

    weighted_sev = round(sev_score * w_sev, 4)
    weighted_imp = round(imp_score * w_imp, 4)
    weighted_urg = round(urg_score * w_urg, 4)
    weighted_conf = round(conf_score * w_conf, 4)

    # Formulate explainable rationale reasons
    if issue_type == "stockout_risk":
        sev_reason = f"Stock-out severity is {norm.get('severity', 'risk')}."
    elif issue_type in ["sales_spike", "sales_drop"]:
        pct = norm.get('percentage_change', 0.0)
        sev_reason = f"Sales change of {pct:+.2f}% evaluated under anomaly severity."
    else:
        sev_reason = f"{issue_type.replace('_', ' ').title()} severity score is {int(sev_score)}."

    if norm.get("impact_available") and norm.get("impact_value") is not None:
        imp_val = norm.get("impact_value")
        imp_lbl = norm.get("impact_label", "Financial Impact")
        imp_reason = f"{imp_lbl}: ₹{imp_val:,.2f} maps to impact score of {int(imp_score)}."
    else:
        imp_reason = "Monetary impact unavailable."

    if issue_type == "stockout_risk" and norm.get("days_remaining") is not None:
        urg_reason = f"Approximately {norm.get('days_remaining'):.2f} days of stock remain."
    elif issue_type == "overstock" and norm.get("coverage_days") is not None:
        urg_reason = f"Stock coverage is {norm.get('coverage_days'):.2f} days."
    else:
        urg_reason = f"Urgency score is {int(urg_score)}."

    conf_reason = f"Data reliability confidence score is {int(conf_score)}."

    return {
        "issue_type": issue_type,
        "actionable": True,
        "severity_score": sev_score,
        "impact_score": imp_score,
        "urgency_score": urg_score,
        "confidence_score": conf_score,
        "raw_priority_score": raw_priority,
        "priority_score": priority_score,
        "priority_label": priority_label,
        "impact_available": norm.get("impact_available", True),
        "score_breakdown": {
            "severity": {
                "score": sev_score,
                "weight": w_sev,
                "weighted_score": weighted_sev
            },
            "impact": {
                "score": imp_score,
                "weight": w_imp,
                "weighted_score": weighted_imp
            },
            "urgency": {
                "score": urg_score,
                "weight": w_urg,
                "weighted_score": weighted_urg
            },
            "confidence": {
                "score": conf_score,
                "weight": w_conf,
                "weighted_score": weighted_conf
            }
        },
        "priority_factors": [
            {
                "factor": "Severity",
                "score": sev_score,
                "reason": sev_reason
            },
            {
                "factor": "Impact",
                "score": imp_score,
                "reason": imp_reason
            },
            {
                "factor": "Urgency",
                "score": urg_score,
                "reason": urg_reason
            },
            {
                "factor": "Confidence",
                "score": conf_score,
                "reason": conf_reason
            }
        ]
    }


def sort_scored_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort scored issue dictionaries deterministically:
      1. raw_priority_score descending
      2. impact_value (or impact_score) descending
      3. urgency_score descending
      4. product_id ascending (if present)
      5. store_id ascending (if present)
    """
    def sort_key(item: Dict[str, Any]):
        raw_p = item.get("raw_priority_score", 0.0)
        imp_val = item.get("impact_value")
        if imp_val is None:
            imp_val = item.get("impact_score", 0.0)
        urg_s = item.get("urgency_score", 0.0)
        prod_id = item.get("product_id", 0)
        if not isinstance(prod_id, (int, float)):
            prod_id = 0
        st_id = item.get("store_id", 0)
        if not isinstance(st_id, (int, float)):
            st_id = 0
        return (-raw_p, -imp_val, -urg_s, prod_id, st_id)

    return sorted(issues, key=sort_key)
