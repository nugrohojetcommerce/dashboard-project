from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta

# from matplotlib.dates import relativedelta
from dateutil.relativedelta import relativedelta

import pandas as pd
from django.db.models import Sum
from django.db.models.functions import ExtractWeekDay, TruncDate

from dashboard.models import AdsMart

# Reuse the same access-control + brand-matching helpers used across the
# other dashboard pages, so brand access behaves identically everywhere.
from .dashboard_performance import brand_filter, get_user_brands

TOP_N = 10
PARETO_N = 15

# NOTE: ROAS thresholds below are a reasonable e-commerce default
# (>=5 healthy, 3-5 borderline, <3 unhealthy). Adjust to match your
# actual internal benchmark if different.
ROAS_GOOD_THRESHOLD = 5
ROAS_WARN_THRESHOLD = 3

WEEKDAY_NAMES = {
    1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat",
}
# Django's ExtractWeekDay: 1=Sunday ... 7=Saturday. We display Mon -> Sun.
WEEKDAY_DISPLAY_ORDER = [2, 3, 4, 5, 6, 7, 1]


def get_ads_brand_variants(user):
    """Analogous to get_consolidate_brand_variants(), sourced from AdsMart."""
    user_brands = get_user_brands(user)

    all_brands = list(AdsMart.objects.values_list("brand", flat=True).distinct())

    return sorted(
        [
            brand
            for brand in all_brands
            if brand
            and any(
                brand.lower().startswith(user_brand.lower())
                for user_brand in user_brands
            )
        ]
    )


def get_ads_platforms() -> list[str]:
    return list(AdsMart.objects.values_list("platform", flat=True).distinct())


def get_ads_types() -> list[str]:
    return sorted(
        [
            t
            for t in AdsMart.objects.values_list("ads_type", flat=True).distinct()
            if t
        ]
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_queryset(
    user,
    start_date,
    end_date,
    selected_brands=None,
    selected_platforms=None,
    selected_ads_types=None,
):
    qs = AdsMart.objects.filter(date__range=[start_date, end_date])

    if selected_brands:
        qs = qs.filter(brand__in=selected_brands)
    else:
        qs = brand_filter(qs, get_user_brands(user))

    if selected_platforms:
        qs = qs.filter(platform__in=selected_platforms)

    if selected_ads_types:
        qs = qs.filter(ads_type__in=selected_ads_types)

    return qs


def _prev_period(start_date: str, end_date: str) -> tuple[str, str]:
    """Return the immediately-preceding period of the same length, used for
    period-over-period (PoP) deltas on the score cards."""
    start = date_cls.fromisoformat(start_date)
    end = date_cls.fromisoformat(end_date)
    span_days = (end - start).days + 1

    prev_end = end - relativedelta(months=1)
    prev_start = start - relativedelta(months=1)
    return prev_start.isoformat(), prev_end.isoformat()


def _pct_change(curr: float, prev: float) -> float | None:
    """None means "not comparable" (no prior-period data) instead of a
    misleading 0% or +inf, so the frontend can render an em dash."""
    if not prev:
        return None
    return (curr - prev) / prev * 100


def _compute_metric_summary(queryset) -> dict:
    agg = queryset.aggregate(
        total_expense=Sum("expense"),
        total_gmv=Sum("gmv"),
        total_impression=Sum("impression"),
        total_clicks=Sum("clicks"),
        total_conversions=Sum("conversions"),
    )
    total_expense = float(agg["total_expense"] or 0)
    total_gmv = float(agg["total_gmv"] or 0)
    total_impression = float(agg["total_impression"] or 0)
    total_clicks = float(agg["total_clicks"] or 0)
    total_conversions = float(agg["total_conversions"] or 0)

    return {
        "total_expense": total_expense,
        "total_gmv": total_gmv,
        "total_impression": total_impression,
        "total_clicks": total_clicks,
        "total_conversions": total_conversions,
        "overall_roas": (total_gmv / total_expense) if total_expense else 0.0,
        "overall_ctr": (total_clicks / total_impression * 100) if total_impression else 0.0,
        "overall_cpc": (total_expense / total_clicks) if total_clicks else 0.0,
        "overall_cpa": (total_expense / total_conversions) if total_conversions else 0.0,
        "overall_cvr": (total_conversions / total_clicks * 100) if total_clicks else 0.0,
        "overall_cpm": (total_expense / total_impression * 1000) if total_impression else 0.0,
        "aov": (total_gmv / total_conversions) if total_conversions else 0.0,
    }


DELTA_METRICS = [
    "total_expense", "total_gmv", "total_conversions",
    "overall_roas", "overall_ctr", "overall_cpc",
    "overall_cpa", "overall_cvr", "overall_cpm", "aov",
]


def _aggregate_by(queryset, group_field: str) -> pd.DataFrame:
    """Full-metric group-by used for brand_group / platform / ads_type
    segment breakdowns. Adds CTR, CVR, ROAS, CPC, CPA, CPM columns."""
    rows = queryset.values(group_field).annotate(
        impression=Sum("impression"),
        clicks=Sum("clicks"),
        conversions=Sum("conversions"),
        expense=Sum("expense"),
        gmv=Sum("gmv"),
    )
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df

    df = df.fillna(0)
    df["roas"] = df.apply(lambda r: r["gmv"] / r["expense"] if r["expense"] else 0, axis=1)
    df["ctr"] = df.apply(lambda r: (r["clicks"] / r["impression"] * 100) if r["impression"] else 0, axis=1)
    df["cvr"] = df.apply(lambda r: (r["conversions"] / r["clicks"] * 100) if r["clicks"] else 0, axis=1)
    df["cpc"] = df.apply(lambda r: (r["expense"] / r["clicks"]) if r["clicks"] else 0, axis=1)
    df["cpa"] = df.apply(lambda r: (r["expense"] / r["conversions"]) if r["conversions"] else 0, axis=1)
    df["cpm"] = df.apply(lambda r: (r["expense"] / r["impression"] * 1000) if r["impression"] else 0, axis=1)
    return df


def _df_to_records(df: pd.DataFrame, group_field: str, key_name: str | None = None) -> list[dict]:
    if df is None or df.empty:
        return []
    key_name = key_name or group_field
    records = []
    for _, row in df.iterrows():
        records.append({
            key_name: row[group_field],
            "impression": int(row["impression"]),
            "clicks": int(row["clicks"]),
            "ctr": float(row["ctr"]),
            "conversions": int(row["conversions"]),
            "cvr": float(row["cvr"]),
            "expense": float(row["expense"]),
            "gmv": float(row["gmv"]),
            "roas": float(row["roas"]),
            "cpc": float(row["cpc"]),
            "cpa": float(row["cpa"]),
            "cpm": float(row["cpm"]),
        })
    return records


def _normalize_series(series: pd.Series) -> pd.Series:
    """Min-max normalize to 0..1 for the radar chart. Flat series (all
    platforms tied, or only one platform) normalize to a neutral 0.5."""
    lo, hi = series.min(), series.max()
    if hi == lo:
        return series.apply(lambda _: 0.5)
    return (series - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_ads_dashboard_data(
    user,
    start_date=None,
    end_date=None,
    selected_brands=None,
    selected_platforms=None,
    selected_ads_types=None,
):
    start_date = start_date or date_cls.today().replace(day=1).isoformat()
    end_date = end_date or date_cls.today().isoformat()

    queryset = _build_queryset(
        user, start_date, end_date, selected_brands, selected_platforms, selected_ads_types,
    )

    # ===== Period-over-period comparison (previous period, same length) =====
    prev_start_date, prev_end_date = _prev_period(start_date, end_date)
    prev_queryset = _build_queryset(
        user, prev_start_date, prev_end_date, selected_brands, selected_platforms, selected_ads_types,
    )

    cards = _compute_metric_summary(queryset)
    prev_cards = _compute_metric_summary(prev_queryset)
    cards["deltas"] = {m: _pct_change(cards[m], prev_cards[m]) for m in DELTA_METRICS}
    cards["prev"] = prev_cards

    # ===== Brand Group segment (table + top-N charts + spotlight) =====
    df_brand_group = _aggregate_by(queryset, "brand_group")
    df_brand_group_sorted = (
        df_brand_group.sort_values(by="expense", ascending=False)
        if not df_brand_group.empty else df_brand_group
    )
    brand_group_table = _df_to_records(df_brand_group_sorted, "brand_group")

    top_brand_group_expense = [
        {"brand_group": row["brand_group"], "expense": row["expense"]}
        for row in brand_group_table[:TOP_N]
    ]

    df_by_roas = (
        df_brand_group.sort_values("roas", ascending=False)
        if not df_brand_group.empty else df_brand_group
    )
    top_brand_group_roas = (
        [
            {"brand_group": row["brand_group"], "roas": row["roas"]}
            for _, row in df_by_roas.head(TOP_N).iterrows()
        ]
        if not df_by_roas.empty else []
    )

    if not df_brand_group.empty:
        top1_roas_row = df_by_roas.iloc[0]
        top1_gmv_row = df_brand_group.sort_values("gmv", ascending=False).iloc[0]
        cards["top_brand_group_by_roas"] = {
            "brand_group": top1_roas_row["brand_group"],
            "roas": float(top1_roas_row["roas"]),
        }
        cards["top_brand_group_by_gmv"] = {
            "brand_group": top1_gmv_row["brand_group"],
            "gmv": float(top1_gmv_row["gmv"]),
        }
    else:
        cards["top_brand_group_by_roas"] = {"brand_group": "-", "roas": 0}
        cards["top_brand_group_by_gmv"] = {"brand_group": "-", "gmv": 0}

    # ===== Efficiency Quadrant: Expense (x) vs ROAS (y), bubble = GMV =====
    if not df_brand_group.empty:
        efficiency_quadrant = [
            {
                "brand_group": row["brand_group"],
                "expense": float(row["expense"]),
                "roas": float(row["roas"]),
                "gmv": float(row["gmv"]),
            }
            for _, row in df_brand_group.iterrows()
        ]
        quadrant_medians = {
            "median_expense": float(df_brand_group["expense"].median()),
            "median_roas": float(df_brand_group["roas"].median()),
        }
    else:
        efficiency_quadrant = []
        quadrant_medians = {"median_expense": 0.0, "median_roas": 0.0}

    # ===== Pareto: cumulative expense contribution by brand group =====
    if not df_brand_group.empty:
        df_pareto = df_brand_group.sort_values("expense", ascending=False).copy()
        total_expense_all = df_pareto["expense"].sum()
        df_pareto["cum_pct"] = (
            df_pareto["expense"].cumsum() / total_expense_all * 100
            if total_expense_all else 0
        )
        pareto = [
            {
                "brand_group": row["brand_group"],
                "expense": float(row["expense"]),
                "cumulative_pct": float(row["cum_pct"]),
            }
            for _, row in df_pareto.head(PARETO_N).iterrows()
        ]
    else:
        pareto = []

    # ===== Platform segment (table + donut + radar) =====
    df_platform = _aggregate_by(queryset, "platform")
    df_platform_sorted = (
        df_platform.sort_values(by="expense", ascending=False)
        if not df_platform.empty else df_platform
    )
    platform_performance = _df_to_records(df_platform_sorted, "platform")
    platform_expense = [
        {"platform": row["platform"], "expense": row["expense"]}
        for row in platform_performance
    ]

    if not df_platform.empty:
        df_radar = df_platform.copy()
        df_radar["efficiency_raw"] = df_radar.apply(
            lambda r: (1 / r["cpa"]) if r["cpa"] else 0, axis=1,
        )
        df_radar["ctr_norm"] = _normalize_series(df_radar["ctr"])
        df_radar["cvr_norm"] = _normalize_series(df_radar["cvr"])
        df_radar["roas_norm"] = _normalize_series(df_radar["roas"])
        df_radar["efficiency_norm"] = _normalize_series(df_radar["efficiency_raw"])
        platform_radar = [
            {
                "platform": row["platform"],
                "ctr_norm": float(row["ctr_norm"]),
                "cvr_norm": float(row["cvr_norm"]),
                "roas_norm": float(row["roas_norm"]),
                "efficiency_norm": float(row["efficiency_norm"]),
                "ctr": float(row["ctr"]),
                "cvr": float(row["cvr"]),
                "roas": float(row["roas"]),
                "cpa": float(row["cpa"]),
            }
            for _, row in df_radar.iterrows()
        ]
    else:
        platform_radar = []

    # ===== Ads Type segment (table + double bar) =====
    df_ads_type = _aggregate_by(queryset, "ads_type")
    df_ads_type_sorted = (
        df_ads_type.sort_values(by="expense", ascending=False)
        if not df_ads_type.empty else df_ads_type
    )
    ads_type_performance = _df_to_records(df_ads_type_sorted, "ads_type")
    ads_type_double_bar = [
        {"ads_type": row["ads_type"], "expense": row["expense"], "gmv": row["gmv"]}
        for row in ads_type_performance
    ]

    # ===== Daily Trend (full metrics: expense, gmv, ctr, cvr, roas, cpa, cpc, cpm) =====
    daily_rows = (
        queryset.annotate(day=TruncDate("date"))
        .values("day")
        .annotate(
            impression=Sum("impression"),
            clicks=Sum("clicks"),
            conversions=Sum("conversions"),
            expense=Sum("expense"),
            gmv=Sum("gmv"),
        )
        .order_by("day")
    )
    df_daily = pd.DataFrame(list(daily_rows))
    if not df_daily.empty:
        df_daily = df_daily.fillna(0)
        df_daily["roas"] = df_daily.apply(lambda r: r["gmv"] / r["expense"] if r["expense"] else 0, axis=1)
        df_daily["ctr"] = df_daily.apply(lambda r: (r["clicks"] / r["impression"] * 100) if r["impression"] else 0, axis=1)
        df_daily["cvr"] = df_daily.apply(lambda r: (r["conversions"] / r["clicks"] * 100) if r["clicks"] else 0, axis=1)
        df_daily["cpc"] = df_daily.apply(lambda r: (r["expense"] / r["clicks"]) if r["clicks"] else 0, axis=1)
        df_daily["cpa"] = df_daily.apply(lambda r: (r["expense"] / r["conversions"]) if r["conversions"] else 0, axis=1)
        df_daily["cpm"] = df_daily.apply(lambda r: (r["expense"] / r["impression"] * 1000) if r["impression"] else 0, axis=1)

        daily_trend = [
            {
                "date": row["day"].isoformat(),
                "impression": int(row["impression"]),
                "clicks": int(row["clicks"]),
                "conversions": int(row["conversions"]),
                "expense": float(row["expense"]),
                "gmv": float(row["gmv"]),
                "roas": float(row["roas"]),
                "ctr": float(row["ctr"]),
                "cvr": float(row["cvr"]),
                "cpc": float(row["cpc"]),
                "cpa": float(row["cpa"]),
                "cpm": float(row["cpm"]),
            }
            for _, row in df_daily.iterrows()
        ]
    else:
        daily_trend = []

    # ===== Day-of-Week performance =====
    weekday_rows = (
        queryset.annotate(weekday=ExtractWeekDay("date"))
        .values("weekday")
        .annotate(
            impression=Sum("impression"),
            clicks=Sum("clicks"),
            conversions=Sum("conversions"),
            expense=Sum("expense"),
            gmv=Sum("gmv"),
        )
    )
    df_weekday = pd.DataFrame(list(weekday_rows))
    day_of_week = []
    if not df_weekday.empty:
        df_weekday = df_weekday.fillna(0)
        df_weekday["roas"] = df_weekday.apply(lambda r: r["gmv"] / r["expense"] if r["expense"] else 0, axis=1)
        df_weekday["ctr"] = df_weekday.apply(lambda r: (r["clicks"] / r["impression"] * 100) if r["impression"] else 0, axis=1)
        df_weekday = df_weekday.set_index("weekday")
        for wd in WEEKDAY_DISPLAY_ORDER:
            if wd in df_weekday.index:
                row = df_weekday.loc[wd]
                day_of_week.append({
                    "day": WEEKDAY_NAMES[wd],
                    "expense": float(row["expense"]),
                    "gmv": float(row["gmv"]),
                    "roas": float(row["roas"]),
                    "ctr": float(row["ctr"]),
                })
            else:
                day_of_week.append({"day": WEEKDAY_NAMES[wd], "expense": 0.0, "gmv": 0.0, "roas": 0.0, "ctr": 0.0})

    # ===== Marketing Funnel: Impression -> Clicks -> Conversions =====
    funnel = {
        "impression": cards["total_impression"],
        "clicks": cards["total_clicks"],
        "conversions": cards["total_conversions"],
        "ctr": cards["overall_ctr"],
        "cvr": cards["overall_cvr"],
    }

    return {
        "selected_brands": selected_brands,
        "selected_platforms": selected_platforms,
        "selected_ads_types": selected_ads_types,
        "start_date": start_date,
        "end_date": end_date,
        "prev_start_date": prev_start_date,
        "prev_end_date": prev_end_date,
        "cards": cards,
        "brand_group_table_json": brand_group_table,
        "top_brand_group_expense_json": top_brand_group_expense,
        "top_brand_group_roas_json": top_brand_group_roas,
        "platform_expense_json": platform_expense,
        "platform_performance_json": platform_performance,
        "platform_radar_json": platform_radar,
        "ads_type_double_bar_json": ads_type_double_bar,
        "ads_type_performance_json": ads_type_performance,
        "daily_trend_json": daily_trend,
        "day_of_week_json": day_of_week,
        "funnel_json": funnel,
        "efficiency_quadrant_json": efficiency_quadrant,
        "quadrant_medians": quadrant_medians,
        "pareto_json": pareto,
        "roas_good_threshold": ROAS_GOOD_THRESHOLD,
        "roas_warn_threshold": ROAS_WARN_THRESHOLD,
    }