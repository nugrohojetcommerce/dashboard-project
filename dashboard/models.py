from django.db import models, connection
from django.contrib.auth.models import User

class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

class UserBrand(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('user', 'brand')

class OrderMartDashboardBrandDF(models.Model):
    # Text / Character Fields (Menggunakan CharField atau TextField)
    brand = models.TextField(null=True, blank=True)
    brand_group = models.TextField(null=True, blank=True)
    category = models.TextField(null=True, blank=True)
    platform = models.TextField(null=True, blank=True)
    province = models.TextField(null=True, blank=True)
    shipping_company = models.TextField(null=True, blank=True)
    delivery_option = models.TextField(null=True, blank=True)
    payment_method = models.TextField(null=True, blank=True)
    cod_status = models.TextField(null=True, blank=True)
    username = models.TextField(null=True, blank=True)
    order_number = models.TextField(null=True, blank=True)
    order_status = models.TextField(null=True, blank=True)
    return_status = models.TextField(null=True, blank=True)
    product_name = models.TextField(null=True, blank=True)
    user_access = models.TextField(null=True, blank=True)
    sku_reference_no = models.TextField(null=True, blank=True)
    parent_sku_no = models.TextField(null=True, blank=True)
    campaign_name = models.TextField(null=True, blank=True)
    campaign_type = models.TextField(null=True, blank=True)
    payment_type = models.TextField(null=True, blank=True)
    extracted_sku = models.TextField(null=True, blank=True)
    product_name_margins = models.TextField(null=True, blank=True)
    product_type_alt = models.TextField(db_column='Product_Type', null=True, blank=True) # Pakai db_column karena CamelCase
    sku = models.TextField(null=True, blank=True)
    sub_brand = models.TextField(null=True, blank=True)
    rrp = models.TextField(null=True, blank=True)
    sku_match = models.TextField(null=True, blank=True)
    date_update = models.TextField(null=True, blank=True)

    # Date & Timestamp Fields
    # Jika tabel lu gak punya primary key 'id', kita pasang primary_key=True di filter_date atau date 
    # agar Django tidak komplain. Di sini gua asumsikan filter_date aman jadi jangkar primary key.
    filter_date = models.DateField(primary_key=True) 
    date = models.DateField(null=True, blank=True)
    first_transaction = models.DateTimeField(null=True, blank=True)
    prev_transaction = models.DateTimeField(null=True, blank=True)

    # BigInt Fields (Cocok untuk nominal uang besar / IDR di Postgres)
    rsp = models.BigIntegerField(null=True, blank=True)
    selling_price = models.BigIntegerField(null=True, blank=True)
    quantity = models.BigIntegerField(null=True, blank=True)
    is_nmv = models.BigIntegerField(null=True, blank=True) # Karena di data lu bigint, bukan boolean
    voucher_paid_by_seller = models.BigIntegerField(null=True, blank=True)
    voucher_paid = models.BigIntegerField(null=True, blank=True)
    rbp = models.BigIntegerField(null=True, blank=True)
    rsp_jetcom = models.BigIntegerField(null=True, blank=True)
    nmv = models.BigIntegerField(null=True, blank=True)
    gmv = models.BigIntegerField(null=True, blank=True)

    # Integer Fields
    is_new_buyer = models.IntegerField(null=True, blank=True)
    is_new_buyer_in_year = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = False  # WAJIB: Biar Django ga bikin file migrasi/ngubah isi database asli
        db_table = 'order_mart_dashboard_brand_df' # Nama tabel asli di PostgreSQL