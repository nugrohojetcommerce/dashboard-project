from ..models import OrderMartDashboardBrandDF
from django.db.models import Sum, Count, Q, QuerySet, F, Case, When, Value, CharField, Func
from django.db.models.functions import Lower, Length
from dashboard.models import (
    OrderMartDashboardBrandDF as OrderMart,
    User, UserBrand
)
from datetime import date
import pandas as pd
import operator
from functools import reduce
from functools import lru_cache


# from dashboard import models

class Replace(Func):
    function = 'REPLACE'
    template = "%(function)s(%(expressions)s, ' ', '')"

class Trim(Func):
    function = 'TRIM'

def brand_filter(queryset: QuerySet, brand_list: list[str]) -> QuerySet:
    """Filters a queryset using case-insensitive partial matching (OR logic)"""
    if not brand_list:
        return queryset.none()
    conditions = [Q(brand__istartswith=brand) for brand in brand_list]
    return queryset.filter(reduce(operator.or_, conditions))

def get_base_queryset(
    user: User,
) -> QuerySet[OrderMart]:
    # return OrderMart.objects.filter(brand__in=get_user_brands(user))
    user_brands = get_user_brands(user)
    return brand_filter(OrderMart.objects.all(), user_brands)

@lru_cache(maxsize=256)
def get_user_brands_cached(user_id: int):
    return tuple(
        UserBrand.objects.filter(user_id=user_id)
        .values_list("brand__name", flat=True)
    )

def get_user_brands(user: User) -> list[str]:
    return list(get_user_brands_cached(user.id))

@lru_cache(maxsize=1)
def get_all_brand_variants():
    return list(
        OrderMart.objects
        .values_list("brand", flat=True)
        .distinct()
    )

def get_brand_variants(user):
    user_brands = get_user_brands(user)

    return sorted([
        brand
        for brand in get_all_brand_variants()
        if any(
            brand.lower().startswith(user_brand.lower())
            for user_brand in user_brands
        )
    ])


def get_order_mart_dashboard_brand(user_brands):
    data = (
        OrderMartDashboardBrandDF.objects
        # filter(date__range=(start, end), brand__in=brands, is_nmv=1).values('date').annotate(gmv_sum=Sum('gmv')).order_by('date')
        .filter(brand__in=user_brands)
        .values()
        )
    # print("DATA: ",data)
    return data

def filter_data(data, start, end, brands, platforms):
    print("DEBUG: get_cards called with start =", start, "end =", end, "brands =", brands, "platforms =", platforms)
    # 1. Filter data secara manual di Python dari parameter `data`
    filtered_data = []
    data = data.filter()
    for item in data:
        # Filter date__range (start <= date <= end)
        if not (item['date'] and start <= item['date'] <= end):
            continue
            
        # Filter brand__in
        if item['brand'] not in brands:
            continue
            
        # Filter platform (kalau bukan "all")
        if platforms != "all" and item['platform'] != platforms:
            continue
            
        filtered_data.append(item)
    
    return filtered_data


def get_cards(filtered_data):
    total_gmv = sum(item['gmv'] for item in filtered_data if item['gmv'] is not None)
    total_nmv = sum(item['gmv'] for item in filtered_data if item['is_nmv'] == 1 and item['gmv'] is not None)
    total_net_order = len(set(item['order_number'] for item in filtered_data if item['order_number'] is not None))
    total_net_quantity = sum(item['quantity'] for item in filtered_data if item['quantity'] is not None)

    return {
        "total_gmv": total_gmv,
        "total_nmv": total_nmv,
        "total_net_order": total_net_order,
        "total_net_quantity": total_net_quantity
    }

def get_nmv_line(filtered_data):
    return [
        {"date": str(r['date']), "gmv": float(r['gmv_sum'])}
        for r in filtered_data
    ]

# ======= REFACTORED FROM HERE ==============

def get_brand_performance_data(user, start_date=None, end_date=None, selected_brands=None, selected_platforms=None):

    # if not start_date:
    #     start_date = date.today().replace(day=1).isoformat()
    start_date = start_date or date.today().replace(day=1).isoformat()
    # if not end_date:
    #     end_date = date.today().isoformat()
    end_date = end_date or date.today().isoformat()

    # user_brands = list(
    #     user.userbrand_set
    #     .values_list("brand__name", flat=True)
    #     .order_by("brand__name")
    #     .distinct()
    # )
    # print("kontol")
    # print("ordermart:",OrderMart.objects)
    base_queryset = (
        OrderMart.objects
        .filter(
            date__range=[start_date, end_date],
            # brand__in=user_brands
        )
    )

    # all_brands = list(
    #     base_queryset
    #     .values_list("brand", flat=True)
    #     .distinct()
    #     .order_by("brand")
    # )

    # all_platforms = list(
    #     base_queryset
    #     .values_list("platform", flat=True)
    #     .distinct()
    #     .order_by("platform")
    # )

    # selected_brands = selected_brands or all_brands
    # selected_platforms = selected_platforms or all_platforms
    
    print(selected_brands)
    # CASCADING BRANDS AND PLATFORMS
    # brands = list(
    #     base_queryset
    #     .filter(
    #         platform__in=selected_platforms
    #     )
    #     .values_list("brand", flat=True)
    #     .distinct()
    #     .order_by("brand")
    # )
    
    # platforms = list(
    #     base_queryset
    #     .filter(
    #         brand__in=selected_brands
    #     )
    #     .values_list("platform", flat=True)
    #     .distinct()
    #     .order_by("platform")
    # )

    if selected_brands:
        base_queryset = base_queryset.filter(brand__in=selected_brands)
        # print("Execution Time brand filter:")
        # print(queryset.query)
        # print(f"execute in :{time.time()-t1} s")
        # queryset = brand_filter(queryset,selected_brands)
    else:
        base_queryset = brand_filter(
        base_queryset,
        get_user_brands(user)
    )

    
    if selected_platforms:
        base_queryset = base_queryset.filter(platform__in=selected_platforms)
        # print("Execution Time platform filter:")
        # # print(queryset.query)
        # print(f"execute in :{time.time()-t1} s")
    print(
        base_queryset.explain(
            analyze=True,
            verbose=True,
            buffers=True,
        )
    )
    


    queryset = base_queryset
    # queryset = (
    #     base_queryset
    #     .filter(
    #         brand__in=selected_brands,
    #         platform__in=selected_platforms
    #     )
    # )
    # ===== Score Cards =====
    cards = queryset.aggregate(
        total_nmv=Sum("nmv"),
        total_gmv=Sum("gmv"),
        total_orders=Count("order_number",distinct=True, filter = Q(is_nmv=1)),
        total_quantity=Count("quantity")
    )

    cards["total_nmv"] = float(
        cards["total_nmv"] or 0
    )

    cards["total_gmv"] = float(
        cards["total_gmv"] or 0
    )

    cards["total_orders"] = float(
        cards["total_orders"] or 0
    )

    cards["total_quantity"] = float(
        cards["total_quantity"] or 0
    )

    # ===== NMV Trends =====

    rows = (
        queryset
        .values("date")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("date")
    )
    # print("CARDS: ",cards)
    # print("base query set: ",base_queryset)
    # print("query set: ",queryset)
    # print("rows buat cumsum",rows)

    trend = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["nmv"] or 0),
            "gmv": float(row["gmv"] or 0),
        }
        for row in (
            queryset
            .values("date")
            .annotate(
                nmv=Sum("nmv"),
                gmv=Sum("gmv"),
            )
            .order_by("date")
        )
    ]

    # ===== NMV Cum Trends =====

    df = pd.DataFrame(list(rows))
    df["cum_nmv"] = df["nmv"].cumsum()
    trend_cum = [
        {
            "date": row["date"].isoformat(),
            "nmv": float(row["cum_nmv"])
        }
        for _, row in df.iterrows()
    ]

    # print("trend_cum: ",trend_cum)

    # ===== Platform NMV Contribution =====
    platform_rows = (
        queryset
        .values("platform")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("-nmv")
    )
    df_platform = pd.DataFrame(list(platform_rows))

    platform_nmv = [
        {
        "platform": row["platform"],
        "nmv":row["nmv"]
        }
        for _, row in df_platform.iterrows()
    ]

    # print("platform nmv: ",platform_nmv)

    # ===== Brand NMV Contribution =====
    brand_rows = (
        queryset
        .values("brand")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("-nmv")
    )
    df_brand = pd.DataFrame(list(brand_rows))

    brand_nmv = [
        {
        "brand": row["brand"],
        "nmv":row["nmv"]
        }
        for _, row in df_brand.iterrows()
    ]

    # ===== Top Product by NMV =====
    product_rows = (
        queryset
        .values("sku_reference_no")
        .annotate(
            nmv=Sum("nmv")
        )
        .order_by("-nmv")
        [:10]
    )
    df_product = pd.DataFrame(list(product_rows))

    product_nmv = [
        {
        "product_name": row["sku_reference_no"],
        "nmv":row["nmv"]
        }
        for _, row in df_product.iterrows()
    ]

    # ===== Payment Type Contribution =====
    payment_type_rows = (
        queryset
        .values("payment_type")
        .annotate(
            orders=Count("order_number", distinct=True)
        )
        .order_by("-orders")
    )
    df_payment_type = pd.DataFrame(list(payment_type_rows))

    payment_type_orders = [
        {
        "payment_type": row["payment_type"],
        "orders":row["orders"]
        }
        for _, row in df_payment_type.iterrows()
    ]

    # ===== Delivery Option Contribution =====

    # Definisikan anotasi untuk kategori delivery_group
    delivery_group_case = Case(
        When(delivery_option_lower__contains="instan", then=Value("Instant")),
        
        When(
            Q(delivery_option_lower__contains="argo") | Q(delivery_option_lower__contains="jtr"), 
            then=Value("Kargo")
        ),
        
        When(
            Q(delivery_option_lower__contains="reg") | 
            Q(delivery_option_lower__contains="standar") | 
            (Q(delivery_option_lower__contains="expres") & ~Q(delivery_option_lower__contains="grab")), 
            then=Value("Regular")
        ),
        
        When(
            Q(delivery_option_lower__contains="econ") | 
            Q(delivery_option_lower__in=['hemat', 'spx hemat', 'sicepat gokil', 'sicepat halu']), 
            then=Value("Regular Hemat")
        ),
        
        When(delivery_option_lower__contains="same", then=Value("Same Day")),
        
        When(delivery_option_lower__contains="seller", then=Value("Shipped by Seller")),
        
        # BENERNYA GINI: Bungkus pakai Q object dengan lookup __exact
        When(
            Q(delivery_option_len_trim__exact=F("delivery_option_len_replace")),
            then=Value("Regular")
        ),
        
        default=Value("Others"),
        output_field=CharField(),
    )

    # Jalankan Queryset dengan mendaftarkan panjang karakternya dulu di .annotate()
    delivery_option_rows = (
        queryset
        .annotate(
            delivery_option_lower=Lower("delivery_option"),
            # Hitung panjang karakter trim asli & panjang karakter setelah spasi dihapus
            delivery_option_len_trim=Length(Trim("delivery_option")),
            delivery_option_len_replace=Length(Replace(Trim("delivery_option")))
        )
        .annotate(delivery_group=delivery_group_case)  
        .values("delivery_group")                      
        .annotate(orders=Count("order_number", distinct=True))        
        .order_by("-orders")                           
    )

    # delivery_option_rows = (
    #     queryset
    #     .values("delivery_option")
    #     .annotate(
    #         orders=Count("order_number")
    #     )
    #     .order_by("orders")
    # )
    df_delivery_option = pd.DataFrame(list(delivery_option_rows))

    delivery_option_orders = [
        {
        "delivery_option": row["delivery_group"],
        "orders":row["orders"]
        }
        for _, row in df_delivery_option.iterrows()
    ]

    # ===== New vs Existing Buyer =====
    new_existing_buyer_rows = (
        queryset
        .annotate(
            buyer_type=Case(
                When(is_new_buyer=1, then=Value("New Buyer")),
                When(is_new_buyer=0, then=Value("Existing Buyer")),
                default=Value("Unknown"),
                output_field=CharField(),
            )
        )
        .values("buyer_type")
        .annotate(
            total_buyers=Count("username", distinct=True)
        )
        .order_by("-total_buyers")
    )
    df_new_existing_buyer = pd.DataFrame(list(new_existing_buyer_rows))

    new_existing_buyer = [
        {
        "buyer_type": row["buyer_type"],
        "total_buyers":row["total_buyers"]
        }
        for _, row in df_new_existing_buyer.iterrows()
    ]

    # ===== Top Product Table =====
    product_table_rows = (
        queryset
        .values("sku_reference_no")
        .annotate(
            nmv=Sum("nmv"),
            orders=Count("order_number", distinct=True),
        )
        .order_by("-nmv")
        # [:10]
    )
    df_product_table = pd.DataFrame(list(product_table_rows))

    product_table_nmv = [
        {
        "product_name": row["sku_reference_no"],
        "nmv":row["nmv"],
        "orders":row["orders"]
        }
        for _, row in df_product_table.iterrows()
    ]    

    return {
            "brands": selected_brands,
            "platforms": selected_platforms,
            "selected_brands": selected_brands,
            "selected_platforms": selected_platforms,
            "start_date": start_date,
            "end_date": end_date,
            "cards": cards,
            "trend_json": trend,
            "trend_cum_json" : trend_cum,
            "platform_nmv_json" : platform_nmv,
            "brand_nmv_json" : brand_nmv,
            "product_nmv_json" : product_nmv,
            "payment_type_orders_json" : payment_type_orders,
            "delivery_option_orders_json" : delivery_option_orders,
            "new_existing_buyer_json" : new_existing_buyer,
            "product_table_nmv_json" : product_table_nmv,
        }
