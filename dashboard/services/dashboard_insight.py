from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta

# from matplotlib.dates import relativedelta
from dateutil.relativedelta import relativedelta

import pandas as pd
from django.db.models import Max, Sum
from django.db.models.functions import ExtractWeekDay, TruncDate

from dashboard.models import OrderMartDashboardInsight, ProductInsight

# Reuse the same access-control + brand-matching helpers used across the
# other dashboard pages, so brand access behaves identically everywhere.
from .dashboard_performance import brand_filter, get_user_brands

TOP_N = 10
PARETO_N = 15
DONUT_TOP_N = 8  # brands/categories beyond this are grouped into "Others"

# Product-level constants. Product cardinality can be in the thousands, so
# we cap how much raw detail we ship to the frontend and guard rate-based
# rankings (ATC rate, bounce rate) against noisy low-traffic products.
PRODUCT_TOP_N = 15
PRODUCT_PARETO_N = 20
PRODUCT_QUADRANT_LIMIT = 50
PRODUCT_TABLE_LIMIT = 200
MIN_VISITORS_FOR_RATE = 30  # minimum traffic before a product's rate (ATC/bounce) is trusted enough to rank

# NOTE: Conversion-rate thresholds below are a reasonable e-commerce default
# (>=3% healthy, 1-3% borderline, <1% unhealthy). Adjust to match your
# actual internal benchmark if different.
CR_GOOD_THRESHOLD = 3.0
CR_WARN_THRESHOLD = 1.0

WEEKDAY_NAMES = {
    1: "Sun", 2: "Mon", 3: "Tue", 4: "Wed", 5: "Thu", 6: "Fri", 7: "Sat",
}
# Django's ExtractWeekDay: 1=Sunday ... 7=Saturday. We display Mon -> Sun.
WEEKDAY_DISPLAY_ORDER = [2, 3, 4, 5, 6, 7, 1]


def get_insight_brand_variants(user):
    """Analogous to get_ads_brand_variants(), sourced from OrderMartDashboardInsight."""
    user_brands = get_user_brands(user)

    all_brands = list(
        OrderMartDashboardInsight.objects.values_list("brand", flat=True).distinct()
    )

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


def get_insight_platforms() -> list[str]:
    return sorted(
        [
            p
            for p in OrderMartDashboardInsight.objects.values_list(
                "platform", flat=True
            ).distinct()
            if p
        ]
    )


def get_insight_categories() -> list[str]:
    return sorted(
        [
            c
            for c in OrderMartDashboardInsight.objects.values_list(
                "category", flat=True
            ).distinct()
            if c
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
    selected_categories=None,
):
    qs = OrderMartDashboardInsight.objects.filter(date_time__range=[start_date, end_date])

    if selected_brands:
        qs = qs.filter(brand__in=selected_brands)
    else:
        qs = brand_filter(qs, get_user_brands(user))

    if selected_platforms:
        qs = qs.filter(platform__in=selected_platforms)

    if selected_categories:
        qs = qs.filter(category__in=selected_categories)

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


def _safe_div(numerator: float, denominator: float) -> float:
    return (numerator / denominator) if denominator else 0.0


def _compute_metric_summary(queryset) -> dict:
    agg = queryset.aggregate(
        total_pv=Sum("page_views"),
        total_uv=Sum("visitors"),
        total_gross_orders=Sum("gross_order_qty"),
        total_net_orders=Sum("net_order_qty"),
        total_gross_sales_qty=Sum("gross_sales_qty"),
        total_net_sales_qty=Sum("net_sales_qty"),
        total_gmv=Sum("gmv"),
        total_nmv=Sum("nmv"),
    )
    total_pv = float(agg["total_pv"] or 0)
    total_uv = float(agg["total_uv"] or 0)
    total_gross_orders = float(agg["total_gross_orders"] or 0)
    total_net_orders = float(agg["total_net_orders"] or 0)
    total_gross_sales_qty = float(agg["total_gross_sales_qty"] or 0)
    total_net_sales_qty = float(agg["total_net_sales_qty"] or 0)
    total_gmv = float(agg["total_gmv"] or 0)
    total_nmv = float(agg["total_nmv"] or 0)

    return {
        "total_pv": total_pv,
        "total_uv": total_uv,
        "total_gross_orders": total_gross_orders,
        "total_net_orders": total_net_orders,
        "total_gross_sales_qty": total_gross_sales_qty,
        "total_net_sales_qty": total_net_sales_qty,
        "total_gmv": total_gmv,
        "total_nmv": total_nmv,
        "conversion_rate": _safe_div(total_net_orders, total_uv) * 100,
        "aov": _safe_div(total_nmv, total_net_orders),
        "items_per_order": _safe_div(total_net_sales_qty, total_net_orders),
        "cancellation_rate": max(
            0.0, _safe_div(total_gross_orders - total_net_orders, total_gross_orders) * 100
        ),
        "gmv_leakage_rate": max(0.0, _safe_div(total_gmv - total_nmv, total_gmv) * 100),
        "pv_per_uv": _safe_div(total_pv, total_uv),
    }


DELTA_METRICS = [
    "total_nmv", "total_gmv", "total_net_orders", "total_uv", "total_pv",
    "conversion_rate", "aov", "items_per_order", "cancellation_rate", "gmv_leakage_rate",
]


def _aggregate_by(queryset, group_field: str) -> pd.DataFrame:
    """Full-metric group-by used for brand_group / platform / category / brand
    segment breakdowns. Adds conversion rate, AOV, items/order, cancellation
    rate, GMV leakage rate, and PV-per-UV (engagement) columns."""
    rows = queryset.values(group_field).annotate(
        page_views=Sum("page_views"),
        visitors=Sum("visitors"),
        gross_order_qty=Sum("gross_order_qty"),
        net_order_qty=Sum("net_order_qty"),
        gross_sales_qty=Sum("gross_sales_qty"),
        net_sales_qty=Sum("net_sales_qty"),
        gmv=Sum("gmv"),
        nmv=Sum("nmv"),
    )
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df

    df = df.fillna(0)
    df["conversion_rate"] = df.apply(
        lambda r: (r["net_order_qty"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
    )
    df["aov"] = df.apply(
        lambda r: (r["nmv"] / r["net_order_qty"]) if r["net_order_qty"] else 0, axis=1
    )
    df["items_per_order"] = df.apply(
        lambda r: (r["net_sales_qty"] / r["net_order_qty"]) if r["net_order_qty"] else 0, axis=1
    )
    df["cancellation_rate"] = df.apply(
        lambda r: max(0.0, (r["gross_order_qty"] - r["net_order_qty"]) / r["gross_order_qty"] * 100)
        if r["gross_order_qty"] else 0,
        axis=1,
    )
    df["gmv_leakage_rate"] = df.apply(
        lambda r: max(0.0, (r["gmv"] - r["nmv"]) / r["gmv"] * 100) if r["gmv"] else 0, axis=1
    )
    df["pv_per_uv"] = df.apply(
        lambda r: (r["page_views"] / r["visitors"]) if r["visitors"] else 0, axis=1
    )
    return df


def _df_to_records(df: pd.DataFrame, group_field: str, key_name: str | None = None) -> list[dict]:
    if df is None or df.empty:
        return []
    key_name = key_name or group_field
    records = []
    for _, row in df.iterrows():
        records.append({
            key_name: row[group_field],
            "page_views": int(row["page_views"]),
            "visitors": int(row["visitors"]),
            "gross_order_qty": int(row["gross_order_qty"]),
            "net_order_qty": int(row["net_order_qty"]),
            "gross_sales_qty": int(row["gross_sales_qty"]),
            "net_sales_qty": int(row["net_sales_qty"]),
            "gmv": float(row["gmv"]),
            "nmv": float(row["nmv"]),
            "conversion_rate": float(row["conversion_rate"]),
            "aov": float(row["aov"]),
            "items_per_order": float(row["items_per_order"]),
            "cancellation_rate": float(row["cancellation_rate"]),
            "gmv_leakage_rate": float(row["gmv_leakage_rate"]),
            "pv_per_uv": float(row["pv_per_uv"]),
        })
    return records


def _donut_with_others(df: pd.DataFrame, group_field: str, value_field: str, top_n: int = DONUT_TOP_N) -> list[dict]:
    """Sort a group-by dataframe by `value_field` desc, keep the top N, and
    bucket the remainder into a single "Others" slice so brand/category
    donuts stay readable even with dozens of distinct values."""
    if df is None or df.empty:
        return []
    sorted_df = df.sort_values(by=value_field, ascending=False)
    head = sorted_df.head(top_n)
    tail = sorted_df.iloc[top_n:]
    records = [
        {group_field: row[group_field], value_field: float(row[value_field])}
        for _, row in head.iterrows()
    ]
    tail_sum = float(tail[value_field].sum()) if not tail.empty else 0.0
    if tail_sum > 0:
        records.append({group_field: "Others", value_field: tail_sum})
    return records


# ---------------------------------------------------------------------------
# Product Insight helpers (postgre_product_insight_mart_dwd_df)
# ---------------------------------------------------------------------------

def _build_product_queryset(
    user,
    start_date,
    end_date,
    selected_brands=None,
    selected_platforms=None,
    selected_categories=None,
):
    qs = ProductInsight.objects.filter(date__range=[start_date, end_date])

    if selected_brands:
        qs = qs.filter(brand__in=selected_brands)
    else:
        qs = brand_filter(qs, get_user_brands(user))

    if selected_platforms:
        qs = qs.filter(platform__in=selected_platforms)

    if selected_categories:
        qs = qs.filter(category__in=selected_categories)

    return qs


def _compute_product_summary(queryset) -> dict:
    agg = queryset.aggregate(
        total_product_visitors=Sum("product_visitors"),
        total_product_page_views=Sum("product_page_views"),
        total_bounce_visitors=Sum("product_bounce_visitors"),
        total_add_to_cart_units=Sum("add_to_cart_units"),
    )
    total_visitors = float(agg["total_product_visitors"] or 0)
    total_pv = float(agg["total_product_page_views"] or 0)
    total_bounce = float(agg["total_bounce_visitors"] or 0)
    total_atc = float(agg["total_add_to_cart_units"] or 0)

    return {
        "total_product_visitors": total_visitors,
        "total_product_page_views": total_pv,
        "total_bounce_visitors": total_bounce,
        "total_add_to_cart_units": total_atc,
        "atc_rate": _safe_div(total_atc, total_visitors) * 100,
        "bounce_rate": _safe_div(total_bounce, total_visitors) * 100,
        "pv_per_visitor": _safe_div(total_pv, total_visitors),
    }


PRODUCT_DELTA_METRICS = [
    "total_product_visitors", "total_product_page_views",
    "total_add_to_cart_units", "atc_rate", "bounce_rate",
]


def _aggregate_products(queryset) -> pd.DataFrame:
    """Group at (product_id, platform) level — the same product can live on
    multiple platforms with very different traffic. product_name / brand /
    category / brand_group / parent_sku can drift slightly across rows for
    the same product_id (renames, backfills, etc.), so we just pick one
    consistently via Max()."""
    rows = queryset.values("product_id", "platform").annotate(
        product_name=Max("product_name"),
        brand=Max("brand"),
        category=Max("category"),
        brand_group=Max("brand_group"),
        parent_sku=Max("parent_sku"),
        visitors=Sum("product_visitors"),
        page_views=Sum("product_page_views"),
        bounce_visitors=Sum("product_bounce_visitors"),
        add_to_cart_units=Sum("add_to_cart_units"),
    )
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df

    df = df.fillna(0)
    df["atc_rate"] = df.apply(
        lambda r: (r["add_to_cart_units"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
    )
    df["bounce_rate"] = df.apply(
        lambda r: (r["bounce_visitors"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
    )
    df["pv_per_visitor"] = df.apply(
        lambda r: (r["page_views"] / r["visitors"]) if r["visitors"] else 0, axis=1
    )
    return df


def _df_to_product_records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    records = []
    for _, row in df.iterrows():
        records.append({
            "platform": row["platform"],
            "product_id": row["product_id"],
            "product_name": row["product_name"] or row["product_id"] or "-",
            "brand": row["brand"],
            "category": row["category"],
            "brand_group": row["brand_group"],
            "parent_sku": row["parent_sku"],
            "page_views": int(row["page_views"]),
            "visitors": int(row["visitors"]),
            "bounce_visitors": int(row["bounce_visitors"]),
            "bounce_rate": float(row["bounce_rate"]),
            "add_to_cart_units": int(row["add_to_cart_units"]),
            "atc_rate": float(row["atc_rate"]),
            "pv_per_visitor": float(row["pv_per_visitor"]),
        })
    return records


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def get_insight_dashboard_data(
    user,
    start_date=None,
    end_date=None,
    selected_brands=None,
    selected_platforms=None,
    selected_categories=None,
):
    start_date = start_date or date_cls.today().replace(day=1).isoformat()
    end_date = end_date or date_cls.today().isoformat()

    queryset = _build_queryset(
        user, start_date, end_date, selected_brands, selected_platforms, selected_categories,
    )

    # ===== Period-over-period comparison (previous period, same length) =====
    prev_start_date, prev_end_date = _prev_period(start_date, end_date)
    prev_queryset = _build_queryset(
        user, prev_start_date, prev_end_date, selected_brands, selected_platforms, selected_categories,
    )

    cards = _compute_metric_summary(queryset)
    prev_cards = _compute_metric_summary(prev_queryset)
    cards["deltas"] = {m: _pct_change(cards[m], prev_cards[m]) for m in DELTA_METRICS}
    cards["prev"] = prev_cards

    # ===== Brand Group segment (table + top-N charts + spotlight + quadrant + pareto) =====
    df_brand_group = _aggregate_by(queryset, "brand_group")
    df_brand_group_sorted = (
        df_brand_group.sort_values(by="nmv", ascending=False)
        if not df_brand_group.empty else df_brand_group
    )
    brand_group_table = _df_to_records(df_brand_group_sorted, "brand_group")

    top_brand_group_nmv = [
        {"brand_group": row["brand_group"], "nmv": row["nmv"]}
        for row in brand_group_table[:TOP_N]
    ]

    df_by_cr = (
        df_brand_group.sort_values("conversion_rate", ascending=False)
        if not df_brand_group.empty else df_brand_group
    )
    top_brand_group_cr = (
        [
            {"brand_group": row["brand_group"], "conversion_rate": row["conversion_rate"]}
            for _, row in df_by_cr.head(TOP_N).iterrows()
        ]
        if not df_by_cr.empty else []
    )

    if not df_brand_group.empty:
        top1_cr_row = df_by_cr.iloc[0]
        top1_nmv_row = df_brand_group.sort_values("nmv", ascending=False).iloc[0]
        cards["top_brand_group_by_cr"] = {
            "brand_group": top1_cr_row["brand_group"],
            "conversion_rate": float(top1_cr_row["conversion_rate"]),
        }
        cards["top_brand_group_by_nmv"] = {
            "brand_group": top1_nmv_row["brand_group"],
            "nmv": float(top1_nmv_row["nmv"]),
        }
    else:
        cards["top_brand_group_by_cr"] = {"brand_group": "-", "conversion_rate": 0}
        cards["top_brand_group_by_nmv"] = {"brand_group": "-", "nmv": 0}

    # ===== Efficiency Quadrant: Visitors (x) vs Conversion Rate (y), bubble = NMV =====
    if not df_brand_group.empty:
        efficiency_quadrant = [
            {
                "brand_group": row["brand_group"],
                "visitors": float(row["visitors"]),
                "conversion_rate": float(row["conversion_rate"]),
                "nmv": float(row["nmv"]),
            }
            for _, row in df_brand_group.iterrows()
        ]
        quadrant_medians = {
            "median_visitors": float(df_brand_group["visitors"].median()),
            "median_conversion_rate": float(df_brand_group["conversion_rate"].median()),
        }
    else:
        efficiency_quadrant = []
        quadrant_medians = {"median_visitors": 0.0, "median_conversion_rate": 0.0}

    # ===== Pareto: cumulative NMV contribution by brand group =====
    if not df_brand_group.empty:
        df_pareto = df_brand_group.sort_values("nmv", ascending=False).copy()
        total_nmv_all = df_pareto["nmv"].sum()
        df_pareto["cum_pct"] = (
            df_pareto["nmv"].cumsum() / total_nmv_all * 100 if total_nmv_all else 0
        )
        pareto = [
            {
                "brand_group": row["brand_group"],
                "nmv": float(row["nmv"]),
                "cumulative_pct": float(row["cum_pct"]),
            }
            for _, row in df_pareto.head(PARETO_N).iterrows()
        ]
    else:
        pareto = []

    # ===== Platform segment (table + PV/UV donuts) =====
    df_platform = _aggregate_by(queryset, "platform")
    df_platform_sorted = (
        df_platform.sort_values(by="nmv", ascending=False)
        if not df_platform.empty else df_platform
    )
    platform_performance = _df_to_records(df_platform_sorted, "platform")
    pv_by_platform = _donut_with_others(df_platform, "platform", "page_views", top_n=999)
    uv_by_platform = _donut_with_others(df_platform, "platform", "visitors", top_n=999)

    # ===== Brand segment (PV/UV donuts only, capped with "Others") =====
    df_brand = _aggregate_by(queryset, "brand")
    pv_by_brand = _donut_with_others(df_brand, "brand", "page_views", top_n=DONUT_TOP_N)
    uv_by_brand = _donut_with_others(df_brand, "brand", "visitors", top_n=DONUT_TOP_N)

    # ===== Daily Trend (full metrics) =====
    daily_rows = (
        queryset.annotate(day=TruncDate("date_time"))
        .values("day")
        .annotate(
            page_views=Sum("page_views"),
            visitors=Sum("visitors"),
            gross_order_qty=Sum("gross_order_qty"),
            net_order_qty=Sum("net_order_qty"),
            gross_sales_qty=Sum("gross_sales_qty"),
            net_sales_qty=Sum("net_sales_qty"),
            gmv=Sum("gmv"),
            nmv=Sum("nmv"),
        )
        .order_by("day")
    )
    df_daily = pd.DataFrame(list(daily_rows))
    if not df_daily.empty:
        df_daily = df_daily.fillna(0)
        df_daily["conversion_rate"] = df_daily.apply(
            lambda r: (r["net_order_qty"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
        )
        df_daily["aov"] = df_daily.apply(
            lambda r: (r["nmv"] / r["net_order_qty"]) if r["net_order_qty"] else 0, axis=1
        )
        df_daily["cancellation_rate"] = df_daily.apply(
            lambda r: max(0.0, (r["gross_order_qty"] - r["net_order_qty"]) / r["gross_order_qty"] * 100)
            if r["gross_order_qty"] else 0,
            axis=1,
        )
        df_daily["gmv_leakage_rate"] = df_daily.apply(
            lambda r: max(0.0, (r["gmv"] - r["nmv"]) / r["gmv"] * 100) if r["gmv"] else 0, axis=1
        )

        daily_trend = [
            {
                "date": row["day"].isoformat(),
                "page_views": int(row["page_views"]),
                "visitors": int(row["visitors"]),
                "gross_order_qty": int(row["gross_order_qty"]),
                "net_order_qty": int(row["net_order_qty"]),
                "gmv": float(row["gmv"]),
                "nmv": float(row["nmv"]),
                "conversion_rate": float(row["conversion_rate"]),
                "aov": float(row["aov"]),
                "cancellation_rate": float(row["cancellation_rate"]),
                "gmv_leakage_rate": float(row["gmv_leakage_rate"]),
            }
            for _, row in df_daily.iterrows()
        ]
    else:
        daily_trend = []

    # ===== Day-of-Week performance =====
    weekday_rows = (
        queryset.annotate(weekday=ExtractWeekDay("date_time"))
        .values("weekday")
        .annotate(
            page_views=Sum("page_views"),
            visitors=Sum("visitors"),
            net_order_qty=Sum("net_order_qty"),
            nmv=Sum("nmv"),
        )
    )
    df_weekday = pd.DataFrame(list(weekday_rows))
    day_of_week = []
    if not df_weekday.empty:
        df_weekday = df_weekday.fillna(0)
        df_weekday["conversion_rate"] = df_weekday.apply(
            lambda r: (r["net_order_qty"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
        )
        df_weekday = df_weekday.set_index("weekday")
        for wd in WEEKDAY_DISPLAY_ORDER:
            if wd in df_weekday.index:
                row = df_weekday.loc[wd]
                day_of_week.append({
                    "day": WEEKDAY_NAMES[wd],
                    "nmv": float(row["nmv"]),
                    "visitors": float(row["visitors"]),
                    "conversion_rate": float(row["conversion_rate"]),
                })
            else:
                day_of_week.append({"day": WEEKDAY_NAMES[wd], "nmv": 0.0, "visitors": 0.0, "conversion_rate": 0.0})

    # ===== Visitor -> Order Funnel: Visitors -> Gross Orders -> Net Orders =====
    funnel = {
        "visitors": cards["total_uv"],
        "gross_orders": cards["total_gross_orders"],
        "net_orders": cards["total_net_orders"],
        "order_rate": _safe_div(cards["total_gross_orders"], cards["total_uv"]) * 100,
        "fulfillment_rate": _safe_div(cards["total_net_orders"], cards["total_gross_orders"]) * 100,
    }

    # =========================================================================
    # PRODUCT INSIGHT (postgre_product_insight_mart_dwd_df) — same filters
    # =========================================================================
    product_queryset = _build_product_queryset(
        user, start_date, end_date, selected_brands, selected_platforms, selected_categories,
    )
    prev_product_queryset = _build_product_queryset(
        user, prev_start_date, prev_end_date, selected_brands, selected_platforms, selected_categories,
    )

    product_cards = _compute_product_summary(product_queryset)
    prev_product_cards = _compute_product_summary(prev_product_queryset)
    product_cards["deltas"] = {
        m: _pct_change(product_cards[m], prev_product_cards[m]) for m in PRODUCT_DELTA_METRICS
    }

    df_products = _aggregate_products(product_queryset)

    # ---- Top products by traffic ----
    df_products_by_visitors = (
        df_products.sort_values("visitors", ascending=False) if not df_products.empty else df_products
    )
    top_products_visitors = (
        [
            {"product_name": row["product_name"] or row["product_id"], "visitors": float(row["visitors"])}
            for _, row in df_products_by_visitors.head(PRODUCT_TOP_N).iterrows()
        ]
        if not df_products_by_visitors.empty else []
    )

    # ---- Top / bottom products by rate metrics (guarded against low-traffic noise) ----
    df_products_reliable = (
        df_products[df_products["visitors"] >= MIN_VISITORS_FOR_RATE]
        if not df_products.empty else df_products
    )

    top_products_atc_rate = (
        [
            {
                "product_name": row["product_name"] or row["product_id"],
                "atc_rate": float(row["atc_rate"]),
                "visitors": float(row["visitors"]),
            }
            for _, row in df_products_reliable.sort_values("atc_rate", ascending=False).head(PRODUCT_TOP_N).iterrows()
        ]
        if not df_products_reliable.empty else []
    )

    top_products_bounce_rate = (
        [
            {
                "product_name": row["product_name"] or row["product_id"],
                "bounce_rate": float(row["bounce_rate"]),
                "visitors": float(row["visitors"]),
            }
            for _, row in df_products_reliable.sort_values("bounce_rate", ascending=False).head(PRODUCT_TOP_N).iterrows()
        ]
        if not df_products_reliable.empty else []
    )

    # ---- Product efficiency quadrant: Visitors (x) vs ATC Rate (y), bubble = ATC units ----
    # Limited to the top-traffic products so the bubble chart stays legible.
    df_products_quadrant = df_products_by_visitors.head(PRODUCT_QUADRANT_LIMIT) if not df_products.empty else df_products
    if not df_products_quadrant.empty:
        product_quadrant = [
            {
                "product_name": row["product_name"] or row["product_id"],
                "visitors": float(row["visitors"]),
                "atc_rate": float(row["atc_rate"]),
                "add_to_cart_units": float(row["add_to_cart_units"]),
            }
            for _, row in df_products_quadrant.iterrows()
        ]
        product_quadrant_medians = {
            "median_visitors": float(df_products_quadrant["visitors"].median()),
            "median_atc_rate": float(df_products_quadrant["atc_rate"].median()),
        }
    else:
        product_quadrant = []
        product_quadrant_medians = {"median_visitors": 0.0, "median_atc_rate": 0.0}

    # ---- Product traffic Pareto: which products concentrate the visitor volume ----
    if not df_products.empty:
        df_product_pareto = df_products.sort_values("visitors", ascending=False).copy()
        total_visitors_all = df_product_pareto["visitors"].sum()
        df_product_pareto["cum_pct"] = (
            df_product_pareto["visitors"].cumsum() / total_visitors_all * 100 if total_visitors_all else 0
        )
        product_pareto = [
            {
                "product_name": row["product_name"] or row["product_id"],
                "visitors": float(row["visitors"]),
                "cumulative_pct": float(row["cum_pct"]),
            }
            for _, row in df_product_pareto.head(PRODUCT_PARETO_N).iterrows()
        ]
    else:
        product_pareto = []

    # ---- Daily product traffic & ATC-rate trend ----
    product_daily_rows = (
        product_queryset.annotate(day=TruncDate("date"))
        .values("day")
        .annotate(
            page_views=Sum("product_page_views"),
            visitors=Sum("product_visitors"),
            bounce_visitors=Sum("product_bounce_visitors"),
            add_to_cart_units=Sum("add_to_cart_units"),
        )
        .order_by("day")
    )
    df_product_daily = pd.DataFrame(list(product_daily_rows))
    if not df_product_daily.empty:
        df_product_daily = df_product_daily.fillna(0)
        df_product_daily["atc_rate"] = df_product_daily.apply(
            lambda r: (r["add_to_cart_units"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
        )
        df_product_daily["bounce_rate"] = df_product_daily.apply(
            lambda r: (r["bounce_visitors"] / r["visitors"] * 100) if r["visitors"] else 0, axis=1
        )
        product_daily_trend = [
            {
                "date": row["day"].isoformat(),
                "page_views": int(row["page_views"]),
                "visitors": int(row["visitors"]),
                "add_to_cart_units": int(row["add_to_cart_units"]),
                "atc_rate": float(row["atc_rate"]),
                "bounce_rate": float(row["bounce_rate"]),
            }
            for _, row in df_product_daily.iterrows()
        ]
    else:
        product_daily_trend = []

    # ---- Full product performance table (capped — product cardinality can be large) ----
    df_product_table = (
        df_products.sort_values("page_views", ascending=False).head(PRODUCT_TABLE_LIMIT)
        if not df_products.empty else df_products
    )
    product_table = _df_to_product_records(df_product_table)

    return {
        "selected_brands": selected_brands,
        "selected_platforms": selected_platforms,
        "selected_categories": selected_categories,
        "start_date": start_date,
        "end_date": end_date,
        "prev_start_date": prev_start_date,
        "prev_end_date": prev_end_date,
        "cards": cards,
        "brand_group_table_json": brand_group_table,
        "top_brand_group_nmv_json": top_brand_group_nmv,
        "top_brand_group_cr_json": top_brand_group_cr,
        "efficiency_quadrant_json": efficiency_quadrant,
        "quadrant_medians": quadrant_medians,
        "pareto_json": pareto,
        "platform_performance_json": platform_performance,
        "pv_by_platform_json": pv_by_platform,
        "uv_by_platform_json": uv_by_platform,
        "pv_by_brand_json": pv_by_brand,
        "uv_by_brand_json": uv_by_brand,
        "daily_trend_json": daily_trend,
        "day_of_week_json": day_of_week,
        "funnel_json": funnel,
        "product_cards": product_cards,
        "top_products_visitors_json": top_products_visitors,
        "top_products_atc_rate_json": top_products_atc_rate,
        "top_products_bounce_rate_json": top_products_bounce_rate,
        "product_quadrant_json": product_quadrant,
        "product_quadrant_medians": product_quadrant_medians,
        "product_pareto_json": product_pareto,
        "product_daily_trend_json": product_daily_trend,
        "product_table_json": product_table,
        "min_visitors_for_rate": MIN_VISITORS_FOR_RATE,
        "cr_good_threshold": CR_GOOD_THRESHOLD,
        "cr_warn_threshold": CR_WARN_THRESHOLD,
    }