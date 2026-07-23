from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_listviewpreference_service_membership_list"),
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
                    ("glpi_computer_data", "Данные GLPI"),
                ],
                max_length=32,
                verbose_name="страница",
            ),
        ),
    ]
