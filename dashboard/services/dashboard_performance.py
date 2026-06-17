from django.db import connection
from ..models import OrderMartDashboardBrandDF
from django.db.models import Sum, Count, Q
# from dashboard import models

def get_order_mart_dashboard_brand(user_brands):
    data = (
        OrderMartDashboardBrandDF.objects
        # filter(date__range=(start, end), brand__in=brands, is_nmv=1).values('date').annotate(gmv_sum=Sum('gmv')).order_by('date')
        .filter(brand__in=user_brands)
        .values()
        )
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