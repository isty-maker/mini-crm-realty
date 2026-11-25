from django.db import migrations, models
from django.utils import timezone

from core.storage import YandexMediaStorage


class Migration(migrations.Migration):
    dependencies = [("core", "0006_safe_workspace_audit_diff")]

    operations = [
        migrations.RenameField("photo", "prop", "property"),
        migrations.RenameField("photo", "url", "full_url"),
        migrations.AddField("photo", "image", models.ImageField(
            upload_to="photos/%Y/%m/%d", storage=YandexMediaStorage(), null=True, blank=True,
        )),
        migrations.AddField("photo", "sort", models.PositiveIntegerField(default=0, db_index=True)),
        migrations.AddField("photo", "created_at", models.DateTimeField(auto_now_add=True, default=timezone.now),
                            preserve_default=False),
        migrations.AlterModelOptions("photo", options={"ordering": ["-is_default", "sort", "id"]}),
    ]
