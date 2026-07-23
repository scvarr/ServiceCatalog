from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0004_list_view_preference"),
    ]

    operations = [
        migrations.AlterField(
            model_name="listviewpreference",
            name="page_key",
            field=models.CharField(
                choices=[
                    ("service_list", "Список услуг"),
                    ("instance_list", "Список экземпляров"),
                    ("service_membership_list", "Состав услуги"),
                ],
                max_length=32,
                verbose_name="страница",
            ),
        ),
    ]
