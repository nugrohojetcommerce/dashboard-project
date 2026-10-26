from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()


class ProductCategoryMapping(models.Model):
    key_id = models.BigAutoField(primary_key=True)
    brand_group = models.CharField(max_length=150, db_index=True)
    sku_code = models.CharField(max_length=150, db_index=True)
    product_category = models.CharField(max_length=150, db_index=True)
    pic = models.CharField(max_length=150)
    last_updated = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "product_category_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["brand_group", "sku_code"],
                name="unique_brand_group_sku",
            )
        ]

    def __str__(self):
        return f"{self.brand_group} | {self.sku_code} -> {self.product_category}"
