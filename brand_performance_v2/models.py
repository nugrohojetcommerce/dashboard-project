from django.db import models


class OrderMartSummary(models.Model):
    key_id = models.BigIntegerField(primary_key=True)
    create_order_date_time_date = models.DateField(blank=True, null=True)
    brand = models.TextField()
    brand_group = models.TextField()
    platform = models.TextField()
    total_nmv = models.BigIntegerField(null=True, blank=True)
    total_gmv = models.BigIntegerField(null=True, blank=True)
    net_orders = models.BigIntegerField(null=True, blank=True)
    gross_orders = models.BigIntegerField(null=True, blank=True)
    net_quantity = models.BigIntegerField(null=True, blank=True)
    gross_quantity = models.BigIntegerField(null=True, blank=True)
    platform_discount = models.BigIntegerField(null=True, blank=True)
    seller_discount = models.BigIntegerField(null=True, blank=True)
    total_seller_voucher = models.BigIntegerField(null=True, blank=True)
    total_platform_voucher = models.BigIntegerField(null=True, blank=True)
    page_view = models.BigIntegerField(null=True, blank=True)
    visitors = models.BigIntegerField(null=True, blank=True)
    target = models.BigIntegerField(null=True, blank=True)
    store_pic = models.TextField()

    class Meta:
        managed = False
        db_table = "order_mart_summary"

    def __str__(self):
        return f"{self.brand} ({self.platform}) - {self.create_order_date_time_date}"


class ProductMartSummary(models.Model):
    key_id = models.BigIntegerField(primary_key=True)
    date = models.DateField(blank=True, null=True)
    brand = models.TextField()
    brand_group = models.TextField()
    platform = models.TextField()
    sku_code = models.TextField()
    product_name = models.TextField()

    gmv = models.BigIntegerField(null=True, blank=True)
    gross_order = models.BigIntegerField(null=True, blank=True)
    gross_quantity = models.BigIntegerField(null=True, blank=True)
    nmv = models.BigIntegerField(null=True, blank=True)
    net_order = models.BigIntegerField(null=True, blank=True)
    net_quantity = models.BigIntegerField(null=True, blank=True)
    total_rsp = models.BigIntegerField(null=True, blank=True)
    min_rsp = models.BigIntegerField(null=True, blank=True)
    max_rsp = models.BigIntegerField(null=True, blank=True)
    total_selling_price = models.BigIntegerField(null=True, blank=True)
    min_selling_price = models.BigIntegerField(null=True, blank=True)
    max_selling_price = models.BigIntegerField(null=True, blank=True)
    total_platform_discount = models.BigIntegerField(null=True, blank=True)
    min_platform_discount = models.BigIntegerField(null=True, blank=True)
    max_platform_discount = models.BigIntegerField(null=True, blank=True)
    total_seller_discount = models.BigIntegerField(null=True, blank=True)
    min_seller_discount = models.BigIntegerField(null=True, blank=True)
    max_seller_discount = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "product_mart_summary"

