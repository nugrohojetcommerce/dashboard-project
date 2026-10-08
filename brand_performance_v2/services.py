from __future__ import annotations

import calendar
import operator
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import lru_cache, reduce
from typing import Any

from dateutil.relativedelta import relativedelta
from django.db.models import Max, Q, Sum

from dashboard.models import User, UserBrand
from .models import OrderMartSummary


@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int) -> tuple[str, ...]:
    return tuple(
        UserBrand.objects.filter(user_id=user_id)
        .exclude(brand__name__iexact="Finetoday")
        .values_list("brand__name", flat=True)
    )

@lru_cache(maxsize=1)
def get_all_brand_variants() -> list[str]:
    return list(
        OrderMartSummary.objects.exclude(brand__isnull=True)
        .exclude(brand="")
        .values_list("brand", flat=True)
        .distinct()
    )


def get_user_brands(user: User) -> list[str]:
    if not user.is_authenticated:
        return []
    if user.is_superuser:
        return sorted(get_all_brand_variants())
    user_brands = get_user_brands_cached(user.id)
    if not user_brands:
        return []
    return sorted(
        [
            brand
            for brand in get_all_brand_variants()
            if any(
                brand.lower().startswith(user_brand.lower())
                for user_brand in user_brands
            )
        ]
    )


def get_brand_variants(user: User) -> list[str]:
    return get_user_brands(user)


def apply_brand_access_filter(queryset, user: User):
    """Filter queryset to only brands user has access to (prefix match or exact)."""
    if not user.is_authenticated:
        return queryset.none()
    if user.is_superuser:
        return queryset
    user_brands = get_user_brands(user)
    if not user_brands:
        return queryset.none()
    return queryset.filter(brand__in=user_brands)


def get_filter_options(user: User) -> dict[str, Any]:
    """Retrieve distinct dropdown options for filters and latest available date."""
    base_qs = apply_brand_access_filter(OrderMartSummary.objects.all(), user)

    # Cutoff defaults to yesterday (H-1) because today is still ongoing / incomplete
    completed_yesterday = date.today() - timedelta(days=1)
    max_d = base_qs.aggregate(max_d=Max("create_order_date_time_date"))["max_d"]
    if max_d:
        latest_date = min(max_d, completed_yesterday)
    else:
        latest_date = completed_yesterday

    brand_groups = sorted(
        list(
            base_qs.exclude(brand_group__isnull=True)
            .exclude(brand_group="")
            .values_list("brand_group", flat=True)
            .distinct()
        )
    )

    brands = get_user_brands(user)

    platforms = sorted(
        list(
            base_qs.exclude(platform__isnull=True)
            .exclude(platform="")
            .values_list("platform", flat=True)
            .distinct()
        )
    )

    return {
        "latest_date": latest_date.isoformat(),
        "brand_groups": brand_groups,
        "brands": brands,
        "platforms": platforms,
    }


def calc_growth(curr: float | int | None, base: float | int | None) -> float | None:
    if curr is None or base is None or base == 0:
        return None
    return round(((curr - base) / base) * 100, 2)


def calc_derived_metrics(d: dict[str, float]) -> dict[str, float]:
    """Computes CVR, CR, ABS, AOV, ASP, Target Achievement from raw metrics dict."""
    nmv = d.get("total_nmv", 0.0)
    gmv = d.get("total_gmv", 0.0)
    target = d.get("target", 0.0)
    net_order = d.get("net_orders", 0.0)
    gross_order = d.get("gross_orders", 0.0)
    net_qty = d.get("net_quantity", 0.0)
    gross_qty = d.get("gross_quantity", 0.0)
    page_view = d.get("page_view", 0.0)
    visitors = d.get("visitors", 0.0)
    v_plat = d.get("total_platform_voucher", 0.0)
    v_seller = d.get("total_seller_voucher", 0.0)
    d_plat = d.get("platform_discount", 0.0)
    d_seller = d.get("seller_discount", 0.0)

    cvr = (net_order / visitors * 100) if visitors > 0 else 0.0
    cr = ((gross_order - net_order) / gross_order * 100) if gross_order > 0 else 0.0
    abs_val = (net_qty / net_order) if net_order > 0 else 0.0
    aov = (nmv / net_order) if net_order > 0 else 0.0
    asp = (nmv / net_qty) if net_qty > 0 else 0.0
    target_ach = (nmv / target * 100) if target > 0 else 0.0

    return {
        "target": target,
        "nmv": nmv,
        "gmv": gmv,
        "voucher_paid_by_platform": v_plat,
        "voucher_paid_by_seller": v_seller,
        "discount_from_platform": d_plat,
        "discount_from_seller": d_seller,
        "net_order": net_order,
        "gross_order": gross_order,
        "net_quantity": net_qty,
        "gross_quantity": gross_qty,
        "page_views": page_view,
        "visitors": visitors,
        "cvr": round(cvr, 2),
        "cr": round(cr, 2),
        "abs": round(abs_val, 2),
        "aov": round(aov, 0),
        "asp": round(asp, 0),
        "target_achievement": round(target_ach, 1),
    }


def get_summary_performance_data(
    user: User,
    as_of_date_str: str | None = None,
    selected_brand_group: str | list[str] | None = None,
    selected_brand: str | list[str] | None = None,
    selected_platform: str | list[str] | None = None,
) -> dict[str, Any]:
    """Core calculation engine for Brand Performance v2 Summary matrix."""
    base_qs = apply_brand_access_filter(OrderMartSummary.objects.all(), user)

    # 1. Determine "Today" (anchor date: completed date defaults to H-1)
    if as_of_date_str:
        try:
            today = datetime.fromisoformat(as_of_date_str).date()
        except ValueError:
            today = None
    else:
        today = None

    if not today:
        completed_yesterday = date.today() - timedelta(days=1)
        latest_d = base_qs.aggregate(max_d=Max("create_order_date_time_date"))["max_d"]
        if latest_d:
            today = min(latest_d, completed_yesterday)
        else:
            today = completed_yesterday

    # 2. Date windows
    prev_day = today - timedelta(days=1)
    prev_7d_start = today - timedelta(days=7)
    prev_7d_end = today - timedelta(days=1)
    prev_month_day = today - relativedelta(months=1)
    mtd_start = today.replace(day=1)
    prev_mtd_start = (today - relativedelta(months=1)).replace(day=1)
    prev_mtd_end = today - relativedelta(months=1)

    min_fetch_date = min(prev_mtd_start, prev_7d_start)
    max_fetch_date = today

    # 3. Filter query
    filtered_qs = base_qs.filter(
        create_order_date_time_date__range=[min_fetch_date, max_fetch_date]
    )

    if selected_brand_group and selected_brand_group != "All":
        filtered_qs = filtered_qs.filter(brand_group=selected_brand_group)

    if selected_brand:
        if isinstance(selected_brand, (list, tuple, set)):
            b_list = [b for b in selected_brand if b and b != "All"]
            if b_list:
                filtered_qs = filtered_qs.filter(brand__in=b_list)
        elif selected_brand != "All":
            if "," in selected_brand:
                b_list = [b.strip() for b in selected_brand.split(",") if b.strip() and b.strip() != "All"]
                if b_list:
                    filtered_qs = filtered_qs.filter(brand__in=b_list)
            else:
                filtered_qs = filtered_qs.filter(brand=selected_brand)

    if selected_platform:
        if isinstance(selected_platform, (list, tuple, set)):
            p_list = [p for p in selected_platform if p and p != "All"]
            if p_list:
                filtered_qs = filtered_qs.filter(platform__in=p_list)
        elif selected_platform != "All":
            if "," in selected_platform:
                p_list = [p.strip() for p in selected_platform.split(",") if p.strip() and p.strip() != "All"]
                if p_list:
                    filtered_qs = filtered_qs.filter(platform__in=p_list)
            else:
                filtered_qs = filtered_qs.filter(platform=selected_platform)

    # Fetch required rows into memory (typically < 3,000 rows, executes in < 150ms)
    fields_to_fetch = [
        "create_order_date_time_date",
        "brand",
        "brand_group",
        "platform",
        "store_pic",
        "target",
        "total_nmv",
        "total_gmv",
        "net_orders",
        "gross_orders",
        "net_quantity",
        "gross_quantity",
        "platform_discount",
        "seller_discount",
        "total_seller_voucher",
        "total_platform_voucher",
        "page_view",
        "visitors",
    ]
    records = list(filtered_qs.values(*fields_to_fetch))

    metric_cols = [
        "target",
        "total_nmv",
        "total_gmv",
        "net_orders",
        "gross_orders",
        "net_quantity",
        "gross_quantity",
        "platform_discount",
        "seller_discount",
        "total_seller_voucher",
        "total_platform_voucher",
        "page_view",
        "visitors",
    ]

    # Data structures for aggregation
    # Key: (brand_group, brand, platform)
    row_grouped = defaultdict(
        lambda: {
            "today": defaultdict(float),
            "prev_day": defaultdict(float),
            "prev_7d": defaultdict(float),
            "prev_month_day": defaultdict(float),
            "mtd": defaultdict(float),
            "prev_mtd": defaultdict(float),
        }
    )

    # Key: (brand_group, brand) for "All" platforms aggregated
    all_brand_grouped = defaultdict(
        lambda: {
            "today": defaultdict(float),
            "prev_day": defaultdict(float),
            "prev_7d": defaultdict(float),
            "prev_month_day": defaultdict(float),
            "mtd": defaultdict(float),
            "prev_mtd": defaultdict(float),
        }
    )

    # Daily trend tracking: {day_num: {'mtd': {...}, 'prev_mtd': {...}}}
    current_day_num = today.day
    daily_trend_map = defaultdict(
        lambda: {
            "mtd": defaultdict(float),
            "prev_mtd": defaultdict(float),
        }
    )

    # Brand-level tracking for Leaderboard and Top/Bottom performer
    brand_perf_map = defaultdict(
        lambda: {
            "today": defaultdict(float),
            "prev_day": defaultdict(float),
            "prev_7d": defaultdict(float),
            "prev_month_day": defaultdict(float),
            "mtd": defaultdict(float),
            "prev_mtd": defaultdict(float),
            "brand_group": "Other",
        }
    )

    # Global KPI sums
    global_kpi = {
        "today": defaultdict(float),
        "prev_day": defaultdict(float),
        "prev_7d": defaultdict(float),
        "mtd": defaultdict(float),
        "prev_mtd": defaultdict(float),
    }

    for r in records:
        row_date = r["create_order_date_time_date"]
        b_group = r["brand_group"] or "Other"
        brand_name = r["brand"]
        plat = r["platform"] or "Other"
        row_key = (b_group, brand_name, plat)
        all_key = (b_group, brand_name)

        brand_perf_map[brand_name]["brand_group"] = b_group

        is_today = (row_date == today)
        is_prev_day = (row_date == prev_day)
        is_7d = (prev_7d_start <= row_date <= prev_7d_end)
        is_prev_m_day = (row_date == prev_month_day)
        is_mtd = (mtd_start <= row_date <= today)
        is_prev_mtd = (prev_mtd_start <= row_date <= prev_mtd_end)

        # Populate daily trend for Day 1..current_day_num
        if is_mtd:
            d_idx = row_date.day
            for m in ["total_nmv", "total_gmv", "net_orders", "visitors", "target"]:
                daily_trend_map[d_idx]["mtd"][m] += float(r.get(m) or 0)

        if is_prev_mtd and row_date.day <= current_day_num:
            d_idx = row_date.day
            for m in ["total_nmv", "total_gmv", "net_orders", "visitors", "target"]:
                daily_trend_map[d_idx]["prev_mtd"][m] += float(r.get(m) or 0)

        for m in metric_cols:
            val = float(r.get(m) or 0)

            if is_today:
                row_grouped[row_key]["today"][m] += val
                all_brand_grouped[all_key]["today"][m] += val
                brand_perf_map[brand_name]["today"][m] += val
                global_kpi["today"][m] += val

            if is_prev_day:
                row_grouped[row_key]["prev_day"][m] += val
                all_brand_grouped[all_key]["prev_day"][m] += val
                brand_perf_map[brand_name]["prev_day"][m] += val
                global_kpi["prev_day"][m] += val

            if is_7d:
                row_grouped[row_key]["prev_7d"][m] += val
                all_brand_grouped[all_key]["prev_7d"][m] += val
                brand_perf_map[brand_name]["prev_7d"][m] += val
                global_kpi["prev_7d"][m] += val

            if is_prev_m_day:
                row_grouped[row_key]["prev_month_day"][m] += val
                all_brand_grouped[all_key]["prev_month_day"][m] += val
                brand_perf_map[brand_name]["prev_month_day"][m] += val

            if is_mtd:
                row_grouped[row_key]["mtd"][m] += val
                all_brand_grouped[all_key]["mtd"][m] += val
                brand_perf_map[brand_name]["mtd"][m] += val
                global_kpi["mtd"][m] += val

            if is_prev_mtd:
                row_grouped[row_key]["prev_mtd"][m] += val
                all_brand_grouped[all_key]["prev_mtd"][m] += val
                brand_perf_map[brand_name]["prev_mtd"][m] += val
                global_kpi["prev_mtd"][m] += val

    # Normalize 7-day sum to daily average (/ 7)
    for row_key, periods in row_grouped.items():
        for m in metric_cols:
            periods["prev_7d"][m] = periods["prev_7d"][m] / 7.0

    for all_key, periods in all_brand_grouped.items():
        for m in metric_cols:
            periods["prev_7d"][m] = periods["prev_7d"][m] / 7.0

    for b_name, periods in brand_perf_map.items():
        for m in metric_cols:
            periods["prev_7d"][m] = periods["prev_7d"][m] / 7.0

    for m in metric_cols:
        global_kpi["prev_7d"][m] = global_kpi["prev_7d"][m] / 7.0

    # 4. Target Calculation directly from OrderMartSummary (aggregated MTD target up to cutoff date)
    total_target_nmv = float(global_kpi["mtd"].get("target") or 0.0)

    # If no target data in database, fallback to 1.15x previous MTD
    if total_target_nmv == 0:
        total_target_nmv = float(int(global_kpi["prev_mtd"]["total_nmv"] * 1.15) or 1000000000)

    # 5. Executive Cards
    actual_nmv = global_kpi["mtd"]["total_nmv"]
    prev_mtd_nmv = global_kpi["prev_mtd"]["total_nmv"]
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    achievement_pct = (actual_nmv / total_target_nmv * 100) if total_target_nmv > 0 else 0.0
    runrate_nmv = (actual_nmv / current_day_num * days_in_month) if current_day_num > 0 else actual_nmv
    full_month_target = (total_target_nmv / current_day_num * days_in_month) if current_day_num > 0 else total_target_nmv
    mtd_growth_pct = calc_growth(actual_nmv, prev_mtd_nmv)

    cards = {
        "target_nmv": total_target_nmv,
        "full_month_target": round(full_month_target, 0),
        "actual_nmv": actual_nmv,
        "achievement_pct": round(achievement_pct, 1),
        "runrate_nmv": round(runrate_nmv, 0),
        "mtd_growth_pct": mtd_growth_pct,
    }

    # 6. Top & Bottom Performers (Today GMV)
    brand_ranks = []
    for b_name, p_data in brand_perf_map.items():
        t_gmv = p_data["today"]["total_gmv"]
        t_nmv = p_data["today"]["total_nmv"]
        p_gmv = p_data["prev_day"]["total_gmv"]
        growth = calc_growth(t_gmv, p_gmv)
        brand_ranks.append({
            "brand": b_name,
            "today_gmv": t_gmv,
            "today_nmv": t_nmv,
            "growth": growth,
        })

    brand_ranks_sorted = sorted(brand_ranks, key=lambda x: x["today_gmv"], reverse=True)

    if brand_ranks_sorted:
        top_perf = brand_ranks_sorted[0]
        # Bottom performer: brand with non-zero or lowest GMV / steepest drop
        bottom_perf = brand_ranks_sorted[-1]
    else:
        top_perf = {"brand": "-", "today_gmv": 0, "today_nmv": 0, "growth": 0}
        bottom_perf = {"brand": "-", "today_gmv": 0, "today_nmv": 0, "growth": 0}

    top_performers = {
        "top": top_perf,
        "bottom": bottom_perf,
    }

    # 7. Anomaly / Issues Detection
    anomalies = []
    # a. Behind MTD Cutoff Target (< 80% achievement)
    low_target_items = []
    for b_name, p_data in brand_perf_map.items():
        b_actual = p_data["mtd"]["total_nmv"]
        b_target = p_data["mtd"]["target"]
        b_group = p_data.get("brand_group", "Other")
        if b_target > 0:
            b_ach = round((b_actual / b_target * 100), 1)
            if b_ach < 80.0:
                low_target_items.append({
                    "brand": b_name,
                    "brand_group": b_group,
                    "actual_nmv": round(b_actual, 0),
                    "target_nmv": round(b_target, 0),
                    "achievement_pct": b_ach,
                    "gap": round(max(b_target - b_actual, 0), 0),
                })
        else:
            b_prev = p_data["prev_mtd"]["total_nmv"]
            b_growth = calc_growth(b_actual, b_prev)
            if b_growth is not None and b_growth < -20.0:
                low_target_items.append({
                    "brand": b_name,
                    "brand_group": b_group,
                    "actual_nmv": round(b_actual, 0),
                    "target_nmv": round(b_prev, 0),
                    "achievement_pct": round(max(100.0 + b_growth, 0), 1),
                    "gap": round(max(b_prev - b_actual, 0), 0),
                })

    low_target_items.sort(key=lambda x: x["achievement_pct"])
    low_target_brands = [x["brand"] for x in low_target_items]

    anomalies.append({
        "id": "behind_target",
        "issue": "Behind MTD Target",
        "affected_brands": ", ".join(low_target_brands[:6]) if low_target_brands else "None",
        "total_brands": len(low_target_items),
        "threshold": "< 80.0% ach",
        "severity": "Critical",
        "items": low_target_items,
    })

    # b. CVR Drop vs Yesterday
    cvr_drop_items = []
    for b_name, p_data in brand_perf_map.items():
        t_net = p_data["today"]["net_orders"]
        t_vis = p_data["today"]["visitors"]
        p_net = p_data["prev_day"]["net_orders"]
        p_vis = p_data["prev_day"]["visitors"]
        b_group = p_data.get("brand_group", "Other")
        cvr_t = (t_net / t_vis * 100) if t_vis > 0 else 0.0
        cvr_p = (p_net / p_vis * 100) if p_vis > 0 else 0.0
        delta = round(cvr_t - cvr_p, 2)
        if delta <= -0.50 and p_vis > 0:
            cvr_drop_items.append({
                "brand": b_name,
                "brand_group": b_group,
                "today_cvr": round(cvr_t, 2),
                "prev_cvr": round(cvr_p, 2),
                "delta_cvr": delta,
                "today_visitors": int(t_vis),
                "today_orders": int(t_net),
            })

    cvr_drop_items.sort(key=lambda x: x["delta_cvr"])
    cvr_drop_brands = [x["brand"] for x in cvr_drop_items]

    anomalies.append({
        "id": "cvr_drop",
        "issue": "CVR Drop vs Yesterday",
        "affected_brands": ", ".join(cvr_drop_brands[:6]) if cvr_drop_brands else "None",
        "total_brands": len(cvr_drop_items),
        "threshold": "Δ ≤ -0.50%",
        "severity": "Warning",
        "items": cvr_drop_items,
    })

    # c. High Cancellation / Return Rate (CR >= 20%)
    high_cr_items = []
    for b_name, p_data in brand_perf_map.items():
        t_net = p_data["today"]["net_orders"]
        t_gross = p_data["today"]["gross_orders"]
        b_group = p_data.get("brand_group", "Other")
        if t_gross >= 10:
            cr = round(((t_gross - t_net) / t_gross * 100), 1)
            if cr >= 20.0:
                high_cr_items.append({
                    "brand": b_name,
                    "brand_group": b_group,
                    "cr_pct": cr,
                    "gross_orders": int(t_gross),
                    "net_orders": int(t_net),
                    "cancelled_orders": int(t_gross - t_net),
                })

    high_cr_items.sort(key=lambda x: x["cr_pct"], reverse=True)
    high_cr_brands = [x["brand"] for x in high_cr_items]

    anomalies.append({
        "id": "high_cr",
        "issue": "High Cancellation / Return Rate",
        "affected_brands": ", ".join(high_cr_brands[:6]) if high_cr_brands else "None",
        "total_brands": len(high_cr_items),
        "threshold": "≥ 20.0%",
        "severity": "Critical",
        "items": high_cr_items,
    })

    # 8. Today KPI Overview Table
    t_der = calc_derived_metrics(global_kpi["today"])
    p_der = calc_derived_metrics(global_kpi["prev_day"])
    p7_der = calc_derived_metrics(global_kpi["prev_7d"])
    m_der = calc_derived_metrics(global_kpi["mtd"])
    pm_der = calc_derived_metrics(global_kpi["prev_mtd"])

    def diff_pt(curr, base):
        return round(curr - base, 2) if base is not None else None

    today_kpi_overview = [
        {
            "kpi": "Target (IDR)",
            "today": t_der["target"],
            "vs_yesterday_pct": calc_growth(t_der["target"], p_der["target"]),
            "vs_7d_avg_pct": calc_growth(t_der["target"], p7_der["target"]),
            "mtd": m_der["target"],
            "vs_last_mtd_pct": calc_growth(m_der["target"], pm_der["target"]),
            "is_curr": True,
        },
        {
            "kpi": "Target Ach.",
            "today": t_der["target_achievement"],
            "vs_yesterday_pct": diff_pt(t_der["target_achievement"], p_der["target_achievement"]),
            "vs_7d_avg_pct": diff_pt(t_der["target_achievement"], p7_der["target_achievement"]),
            "mtd": m_der["target_achievement"],
            "vs_last_mtd_pct": diff_pt(m_der["target_achievement"], pm_der["target_achievement"]),
            "is_curr": False,
            "is_pct": True,
        },
        {
            "kpi": "GMV (IDR)",
            "today": t_der["gmv"],
            "vs_yesterday_pct": calc_growth(t_der["gmv"], p_der["gmv"]),
            "vs_7d_avg_pct": calc_growth(t_der["gmv"], p7_der["gmv"]),
            "mtd": m_der["gmv"],
            "vs_last_mtd_pct": calc_growth(m_der["gmv"], pm_der["gmv"]),
            "is_curr": True,
        },
        {
            "kpi": "NMV (IDR)",
            "today": t_der["nmv"],
            "vs_yesterday_pct": calc_growth(t_der["nmv"], p_der["nmv"]),
            "vs_7d_avg_pct": calc_growth(t_der["nmv"], p7_der["nmv"]),
            "mtd": m_der["nmv"],
            "vs_last_mtd_pct": calc_growth(m_der["nmv"], pm_der["nmv"]),
            "is_curr": True,
        },
        {
            "kpi": "Orders",
            "today": t_der["net_order"],
            "vs_yesterday_pct": calc_growth(t_der["net_order"], p_der["net_order"]),
            "vs_7d_avg_pct": calc_growth(t_der["net_order"], p7_der["net_order"]),
            "mtd": m_der["net_order"],
            "vs_last_mtd_pct": calc_growth(m_der["net_order"], pm_der["net_order"]),
            "is_curr": False,
        },
        {
            "kpi": "Visitors",
            "today": t_der["visitors"],
            "vs_yesterday_pct": calc_growth(t_der["visitors"], p_der["visitors"]),
            "vs_7d_avg_pct": calc_growth(t_der["visitors"], p7_der["visitors"]),
            "mtd": m_der["visitors"],
            "vs_last_mtd_pct": calc_growth(m_der["visitors"], pm_der["visitors"]),
            "is_curr": False,
        },
        {
            "kpi": "Conversion Rate",
            "today": t_der["cvr"],
            "vs_yesterday_pct": diff_pt(t_der["cvr"], p_der["cvr"]),
            "vs_7d_avg_pct": diff_pt(t_der["cvr"], p7_der["cvr"]),
            "mtd": m_der["cvr"],
            "vs_last_mtd_pct": diff_pt(m_der["cvr"], pm_der["cvr"]),
            "is_curr": False,
            "is_pct": True,
        },
        {
            "kpi": "AOV (IDR)",
            "today": t_der["aov"],
            "vs_yesterday_pct": calc_growth(t_der["aov"], p_der["aov"]),
            "vs_7d_avg_pct": calc_growth(t_der["aov"], p7_der["aov"]),
            "mtd": m_der["aov"],
            "vs_last_mtd_pct": calc_growth(m_der["aov"], pm_der["aov"]),
            "is_curr": True,
        },
        {
            "kpi": "NMV / GMV",
            "today": round((t_der["nmv"] / t_der["gmv"] * 100), 2) if t_der["gmv"] > 0 else 0,
            "vs_yesterday_pct": diff_pt(
                (t_der["nmv"] / t_der["gmv"] * 100) if t_der["gmv"] > 0 else 0,
                (p_der["nmv"] / p_der["gmv"] * 100) if p_der["gmv"] > 0 else 0
            ),
            "vs_7d_avg_pct": diff_pt(
                (t_der["nmv"] / t_der["gmv"] * 100) if t_der["gmv"] > 0 else 0,
                (p7_der["nmv"] / p7_der["gmv"] * 100) if p7_der["gmv"] > 0 else 0
            ),
            "mtd": round((m_der["nmv"] / m_der["gmv"] * 100), 2) if m_der["gmv"] > 0 else 0,
            "vs_last_mtd_pct": diff_pt(
                (m_der["nmv"] / m_der["gmv"] * 100) if m_der["gmv"] > 0 else 0,
                (pm_der["nmv"] / pm_der["gmv"] * 100) if pm_der["gmv"] > 0 else 0
            ),
            "is_curr": False,
            "is_pct": True,
        },
    ]

    # 9. Chart Data
    # a. NMV Share by Brand (and Brand Group)
    brand_nmv_map = defaultdict(float)
    bg_nmv_map = defaultdict(float)
    # b. Platform Contribution
    plat_nmv_map = defaultdict(float)

    for (b_group, b_name, plat), periods in row_grouped.items():
        brand_nmv_map[b_name] += periods["mtd"]["total_nmv"]
        bg_nmv_map[b_group] += periods["mtd"]["total_nmv"]
        plat_nmv_map[plat] += periods["mtd"]["total_nmv"]

    # c. Daily Trend Line Chart (Day 1..current_day_num)
    daily_trend_list = []
    for day_i in range(1, current_day_num + 1):
        day_str = f"Day {day_i}"
        m_vals = daily_trend_map[day_i]["mtd"]
        pm_vals = daily_trend_map[day_i]["prev_mtd"]
        daily_trend_list.append({
            "day": day_str,
            "mtd": {
                "nmv": m_vals["total_nmv"],
                "target": m_vals["target"],
                "gmv": m_vals["total_gmv"],
                "net_order": m_vals["net_orders"],
                "visitors": m_vals["visitors"],
            },
            "prev_mtd": {
                "nmv": pm_vals["total_nmv"],
                "target": pm_vals["target"],
                "gmv": pm_vals["total_gmv"],
                "net_order": pm_vals["net_orders"],
                "visitors": pm_vals["visitors"],
            },
        })

    def get_delta(m_name: str, curr: float | int | None, base: float | int | None):
        if m_name in ("cvr", "cr", "target_achievement"):
            return diff_pt(curr, base)
        return calc_growth(curr, base)

    # 10. Complete Columnar Table (Pivot Rows grouped by Platform)
    def build_metric_row(b_group: str, b_name: str, periods: dict) -> dict[str, Any]:
        t_calc = calc_derived_metrics(periods["today"])
        pd_calc = calc_derived_metrics(periods["prev_day"])
        p7_calc = calc_derived_metrics(periods["prev_7d"])
        pm_calc = calc_derived_metrics(periods["prev_month_day"])
        m_calc = calc_derived_metrics(periods["mtd"])
        pmd_calc = calc_derived_metrics(periods["prev_mtd"])
        return {
            "brand_group": b_group,
            "brand": b_name,
            "metrics": {
                metric_name: {
                    "today": t_calc[metric_name],
                    "vs_prev_day": get_delta(metric_name, t_calc[metric_name], pd_calc[metric_name]),
                    "vs_7d_avg": get_delta(metric_name, t_calc[metric_name], p7_calc[metric_name]),
                    "vs_prev_month_day": get_delta(metric_name, t_calc[metric_name], pm_calc[metric_name]),
                    "mtd": m_calc[metric_name],
                    "vs_prev_mtd": get_delta(metric_name, m_calc[metric_name], pmd_calc[metric_name]),
                }
                for metric_name in [
                    "target", "target_achievement", "nmv", "gmv", "voucher_paid_by_platform", "voucher_paid_by_seller",
                    "discount_from_platform", "discount_from_seller", "net_order",
                    "gross_order", "net_quantity", "gross_quantity", "page_views",
                    "visitors", "cvr", "cr", "abs", "aov", "asp"
                ]
            }
        }

    all_rows = [
        build_metric_row(bg, b_name, periods)
        for (bg, b_name), periods in sorted(all_brand_grouped.items(), key=lambda x: (x[0][0], x[0][1]))
    ]

    unique_platforms = sorted(list({key[2] for key in row_grouped.keys()}))

    pivot_by_platform: dict[str, list[dict[str, Any]]] = {
        "All": all_rows,
    }
    for p in unique_platforms:
        p_rows = [
            build_metric_row(bg, b_name, periods)
            for (bg, b_name, plat), periods in sorted(row_grouped.items(), key=lambda x: (x[0][0], x[0][1]))
            if plat == p
        ]
        pivot_by_platform[p] = p_rows

    # 11. Leaderboard Table
    leaderboard_rows = []
    sorted_brands = sorted(
        brand_perf_map.items(),
        key=lambda item: item[1]["mtd"]["total_nmv"],
        reverse=True
    )

    for rank_idx, (b_name, periods) in enumerate(sorted_brands, start=1):
        b_group = periods["brand_group"]
        t_calc = calc_derived_metrics(periods["today"])
        pd_calc = calc_derived_metrics(periods["prev_day"])
        p7_calc = calc_derived_metrics(periods["prev_7d"])
        pm_calc = calc_derived_metrics(periods["prev_month_day"])
        m_calc = calc_derived_metrics(periods["mtd"])
        pmd_calc = calc_derived_metrics(periods["prev_mtd"])

        leaderboard_rows.append({
            "rank": rank_idx,
            "brand": b_name,
            "brand_group": b_group,
            "metrics": {
                metric_name: {
                    "today": t_calc[metric_name],
                    "vs_prev_day": get_delta(metric_name, t_calc[metric_name], pd_calc[metric_name]),
                    "vs_7d_avg": get_delta(metric_name, t_calc[metric_name], p7_calc[metric_name]),
                    "vs_prev_month_day": get_delta(metric_name, t_calc[metric_name], pm_calc[metric_name]),
                    "mtd": m_calc[metric_name],
                    "vs_prev_mtd": get_delta(metric_name, m_calc[metric_name], pmd_calc[metric_name]),
                }
                for metric_name in ["target", "target_achievement", "nmv", "gmv", "net_order", "visitors", "cvr"]
            }
        })

    return {
        "as_of_date": today.isoformat(),
        "cards": cards,
        "top_performers": top_performers,
        "anomalies": anomalies,
        "today_kpi_overview": today_kpi_overview,
        "charts": {
            "brand_share": dict(sorted(brand_nmv_map.items(), key=lambda x: x[1], reverse=True)),
            "brand_group_share": dict(sorted(bg_nmv_map.items(), key=lambda x: x[1], reverse=True)),
            "platform_share": dict(sorted(plat_nmv_map.items(), key=lambda x: x[1], reverse=True)),
            "comparison": {
                "gmv": m_der["gmv"],
                "nmv": m_der["nmv"],
            },
            "daily_trend": daily_trend_list,
        },
        "pivot_table": all_rows,
        "pivot_by_platform": pivot_by_platform,
        "platforms_in_data": (
            unique_platforms
            if len(unique_platforms) == 1
            else (["All"] + unique_platforms if unique_platforms else ["All"])
        ),
        "leaderboard": leaderboard_rows,
    }
