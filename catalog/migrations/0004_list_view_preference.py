from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_glpi_integration"),
    ]

    operations = [
        migrations.CreateModel(
            name="ListViewPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("page_key", models.CharField(choices=[("service_list", "Список услуг"), ("instance_list", "Список экземпляров")], max_length=32, verbose_name="страница")),
                ("visible_columns", models.JSONField(blank=True, default=list, verbose_name="видимые столбцы")),
                ("page_size", models.PositiveSmallIntegerField(default=25, verbose_name="строк на странице")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="list_view_preferences", to=settings.AUTH_USER_MODEL, verbose_name="пользователь")),
            ],
            options={"verbose_name": "настройка списка", "verbose_name_plural": "настройки списков"},
        ),
        migrations.AddConstraint(
            model_name="listviewpreference",
            constraint=models.UniqueConstraint(fields=("user", "page_key"), name="catalog_list_preference_unique"),
        ),
    ]
