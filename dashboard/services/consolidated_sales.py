from __future__ import annotations

from datetime import date as date_cls
from functools import lru_cache

import pandas as pd
from .dashboard_performance import (
    brand_filter,
    get_brand_variants,
)
from django.db.models import (
    BigIntegerField,
    CharField,
    Func,
    Max,
    OuterRef,
    Subquery,
    Sum,
    Q,
)
from django.db.models.functions import Cast, ExtractMonth, ExtractYear

from dashboard.models import OrderMartUnionDWSDF as OrderMartUnion
from dashboard.models import TargetData

# Reuse the same access-control + brand-matching helpers used by
# brand_performance so both pages behave identically re: which brands
# a user is allowed to see. `OrderMartUnionDWSDF` also has a `brand`
# field, so these helpers work as-is on this table too.
from .dashboard_performance import get_user_brands

TOP_N = 10


@lru_cache(maxsize=1)
def get_all_brand_variants():
    return list(OrderMartUnion.objects.values_list("brand", flat=True).distinct())

def get_consolidate_brand_groups(user):
    """Retrieves a sorted, distinct list of brand groups from OrderMartUnion 
    filtered by the user's allowed brand variants.
    """
    user_brands = get_brand_variants(user)
    
    if not user_brands:
        return []

    # Build dynamic OR conditions for prefix matching on the brand field
    query = Q()
    for user_brand in user_brands:
        if user_brand:
            query |= Q(brand__istartswith=user_brand)

    # Query distinct brand_group values
    brand_groups = list(
        OrderMartUnion.objects.filter(query)
        .exclude(brand_group__isnull=True)
        .exclude(brand_group="")
        .values_list("brand_group", flat=True)
        .distinct()
    )

    return sorted(brand_groups)


def get_consolidate_platforms() -> list[str]:
    return list(OrderMartUnion.objects.values_list("platform", flat=True).distinct())


class ToCharYYYYMM(Func):
    function = "TO_CHAR"
    template = "%(function)s(%(expressions)s, 'YYYYMM')"
    output_field = CharField()


def _shift_month(d: date_cls, delta: int) -> date_cls:
    """Return the first day of the month `delta` months away from d."""
    month_index = d.month - 1 + delta
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return date_cls(year, month, 1)


def get_consolidate_sales_data(
    user,
    start_date=None,
    end_date=None,
    selected_brands=None,
    selected_platforms=None,
):
    start_date = start_date or date_cls.today().replace(day=1).isoformat()
    end_date = end_date or date_cls.today().isoformat()

    target_subquery = TargetData.objects.filter(
        # Join Key 1: Brand Group harus sama (case-insensitive/sensitive disesuaikan)
        Brand_Group=OuterRef("brand_group"),
        # Join Key 2: Konversi date_time (OrderMartUnion) jadi YYYYMM, lalu cocokkan dengan Order_Date
        Order_Date=Cast(
            ToCharYYYYMM(OuterRef("date_time")), output_field=BigIntegerField()
        ),
    ).values("Target")[:1]

    base_queryset = OrderMartUnion.objects.filter(
        date_time__range=[start_date, end_date],
    ).annotate(target_sales=Subquery(target_subquery))
    # print("ini ordermartunion: ",list(OrderMartUnion.objects.values()))
    # print("ini base query set: ",base_queryset)

    if selected_brands:
        base_queryset = base_queryset.filter(brand_group__in=selected_brands)
    else:
        base_queryset = base_queryset.filter(brand_group__in=get_consolidate_brand_groups(user))

    if selected_platforms:
        base_queryset = base_queryset.filter(platform__in=selected_platforms)

    queryset = base_queryset
    # len()
    # ===== Score Cards =====
    # Table is already daily-level (no order_number to count distinct on),
    # so "orders" and "quantity" come straight from the pre-aggregated
    # net_order_qty / net_sales_qty columns.
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_orders=Sum("net_order_qty"),
        total_quantity=Sum("net_sales_qty"),
    )
    cards["total_nmv"] = float(cards["total_nmv"] or 0)
    cards["total_orders"] = float(cards["total_orders"] or 0)
    cards["total_quantity"] = float(cards["total_quantity"] or 0)

    # ===== Brand Group Table  =====

    queryset_with_month = queryset.annotate(
        data_year=ExtractYear("date_time"), data_month=ExtractMonth("date_time")
    )

    brand_group_monthly_rows = queryset_with_month.values(
        "brand_group", "data_year", "data_month"
    ).annotate(
        nmv=Sum("nmv"),
        orders=Sum("net_order_qty"),
        quantity=Sum("net_sales_qty"),
        # Di level per bulan ini, kita ambil Max biar data harian ga bikin target kegulung
        target_sales_monthly=Max("target_sales"),
    )

    df_monthly = pd.DataFrame(list(brand_group_monthly_rows))

    if df_monthly.empty:
        df_brand_group = pd.DataFrame(
            columns=["brand_group", "nmv", "orders", "quantity", "target_sales"]
        )
    else:
        if "target_sales_monthly" in df_monthly.columns:
            if df_monthly["target_sales_monthly"].dtype == "object":
                df_monthly["target_sales_monthly"] = df_monthly[
                    "target_sales_monthly"
                ].str.replace(",", "", regex=True)
            df_monthly["target_sales_monthly"] = pd.to_numeric(
                df_monthly["target_sales_monthly"], errors="coerce"
            ).fillna(0)

        df_brand_group = (
            df_monthly.groupby("brand_group")
            .agg(
                {
                    "nmv": "sum",
                    "orders": "sum",
                    "quantity": "sum",
                    "target_sales_monthly": "sum",  # Di-sum antar bulan!
                }
            )
            .reset_index()
            .rename(columns={"target_sales_monthly": "target_sales"})
        )

        df_brand_group = df_brand_group.sort_values(by="nmv", ascending=False).fillna(0)

        for col in ["nmv", "orders", "quantity", "target_sales"]:
            df_brand_group[col] = df_brand_group[col].astype(int)

        df_brand_group["target_ach"] = df_brand_group.apply(
            lambda row: row["nmv"] / row["target_sales"] if row["target_sales"] else 0,
            axis=1,
        )

    # ===== Monthly % Target Achievement Trend (line chart, per brand_group) =====
    # Always shows at least 2 calendar months for comparison — if the
    # selected filter only covers a single month, this pulls in the
    # previous month too. Doesn't affect any other card/chart/table,
    # which stay strictly scoped to the user's selected date filter.
    start_date_obj = date_cls.fromisoformat(str(start_date))
    end_date_obj = date_cls.fromisoformat(str(end_date))

    months_spanned = (
        (end_date_obj.year - start_date_obj.year) * 12
        + (end_date_obj.month - start_date_obj.month)
        + 1
    )

    trend_start_date = (
        _shift_month(start_date_obj, -1) if months_spanned < 2 else start_date_obj
    )

    trend_queryset = OrderMartUnion.objects.filter(
        date_time__range=[trend_start_date, end_date_obj],
    ).annotate(target_sales=Subquery(target_subquery))

    if selected_brands:
        trend_queryset = trend_queryset.filter(brand__in=selected_brands)
    else:
        trend_queryset = brand_filter(trend_queryset, get_user_brands(user))

    if selected_platforms:
        trend_queryset = trend_queryset.filter(platform__in=selected_platforms)

    trend_monthly_rows = (
        trend_queryset.annotate(
            data_year=ExtractYear("date_time"),
            data_month=ExtractMonth("date_time"),
        )
        .values("brand_group", "data_year", "data_month")
        .annotate(
            nmv=Sum("nmv"),
            target_sales_monthly=Max("target_sales"),
        )
    )

    df_trend_monthly = pd.DataFrame(list(trend_monthly_rows))

    if df_trend_monthly.empty:
        monthly_brand_group_ach = []
    else:
        if df_trend_monthly["target_sales_monthly"].dtype == "object":
            df_trend_monthly["target_sales_monthly"] = df_trend_monthly[
                "target_sales_monthly"
            ].str.replace(",", "", regex=True)
        df_trend_monthly["target_sales_monthly"] = pd.to_numeric(
            df_trend_monthly["target_sales_monthly"], errors="coerce"
        ).fillna(0)

        df_trend_monthly["target_ach_monthly"] = df_trend_monthly.apply(
            lambda row: (
                row["nmv"] / row["target_sales_monthly"]
                if row["target_sales_monthly"]
                else 0
            ),
            axis=1,
        )
        df_trend_monthly = df_trend_monthly.sort_values(["data_year", "data_month"])

        monthly_brand_group_ach = [
            {
                "brand_group": row["brand_group"],
                "period": f"{int(row['data_year'])}-{int(row['data_month']):02d}",
                "target_ach": float(row["target_ach_monthly"]),
            }
            for _, row in df_trend_monthly.iterrows()
        ]

    # ===== Overall NMV vs Target (for the NMV scorecard badge) =====
    if not df_brand_group.empty:
        cards["total_target"] = float(df_brand_group["target_sales"].sum())
    else:
        cards["total_target"] = 0.0
    cards["total_target_ach"] = (
        cards["total_nmv"] / cards["total_target"] if cards["total_target"] else 0.0
    )

    # ===== Top1 Brand Group spotlight cards =====
    if not df_brand_group.empty:
        top1_nmv_row = df_brand_group.iloc[0]
        top1_ach_row = df_brand_group.sort_values("target_ach", ascending=False).iloc[0]
        cards["top_brand_group_by_nmv"] = {
            "brand_group": top1_nmv_row["brand_group"],
            "nmv": int(top1_nmv_row["nmv"]),
        }
        cards["top_brand_group_by_ach"] = {
            "brand_group": top1_ach_row["brand_group"],
            "target_ach": float(top1_ach_row["target_ach"]),
        }
    else:
        cards["top_brand_group_by_nmv"] = {"brand_group": "-", "nmv": 0}
        cards["top_brand_group_by_ach"] = {"brand_group": "-", "target_ach": 0}

    brand_group_table = (
        [
            {
                "brand_group": row["brand_group"],
                "nmv": row["nmv"],
                "orders": row["orders"],
                "quantity": row["quantity"],
                "target_sales": row["target_sales"],
                "target_ach": (
                    row["nmv"] / row["target_sales"] if row["target_sales"] != 0 else 0
                ),
            }
            for _, row in df_brand_group.iterrows()
        ]
        if not df_brand_group.empty
        else []
    )

    # ===== Top Performing Brand Group by NMV =====
    top_brand_group_nmv = [
        {"brand_group": row["brand_group"], "nmv": row["nmv"]}
        for row in brand_group_table[:TOP_N]
    ]

    # ===== Top Performing Brand Group by % Target Achieved =====
    df_by_ach = (
        df_brand_group.sort_values("target_ach", ascending=False)
        if not df_brand_group.empty
        else df_brand_group
    )
    top_brand_group_target_ach = (
        [
            {"brand_group": row["brand_group"], "target_ach": row["target_ach"]}
            for _, row in df_by_ach.head(TOP_N).iterrows()
        ]
        if not df_by_ach.empty
        else []
    )

    # ===== Platform NMV Contribution (donut) =====
    platform_rows = (
        queryset.values("platform").annotate(nmv=Sum("nmv")).order_by("-nmv")
    )
    df_platform = pd.DataFrame(list(platform_rows))
    platform_nmv = (
        [
            {"platform": row["platform"], "nmv": row["nmv"]}
            for _, row in df_platform.iterrows()
        ]
        if not df_platform.empty
        else []
    )

    # ===== Net Order vs Net Quantity by Brand Group (double bar) =====
    brand_group_double_bar = [
        {
            "brand_group": row["brand_group"],
            "orders": row["orders"],
            "quantity": row["quantity"],
        }
        for row in brand_group_table
    ]

    return {
        "selected_brands": selected_brands,
        "selected_platforms": selected_platforms,
        "start_date": start_date,
        "end_date": end_date,
        "cards": cards,
        "brand_group_table_json": brand_group_table,
        "top_brand_group_nmv_json": top_brand_group_nmv,
        "top_brand_group_target_ach_json": top_brand_group_target_ach,
        "platform_nmv_json": platform_nmv,
        "brand_group_double_bar_json": brand_group_double_bar,
        "monthly_brand_group_ach_json": monthly_brand_group_ach,
    }
