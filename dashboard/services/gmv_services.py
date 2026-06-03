from django.db import connection

def get_gmv(start, end, brands):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT date, SUM(gmv)
            FROM order_mart_dashboard_brand_df
            WHERE date BETWEEN %s AND %s
            AND brand = ANY(%s)
            AND is_nmv = 1
            GROUP BY date
            ORDER BY date
        """, [start, end, brands])

        rows = cursor.fetchall()
        print(rows)
        # row.get
    return [
        {"date": str(r[0]), "gmv": float(r[1])}
        for r in rows
    ]