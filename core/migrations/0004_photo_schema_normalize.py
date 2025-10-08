from django.db import migrations, models
import django.utils.timezone


def copy_url_to_full_url(apps, schema_editor):
    Photo = apps.get_model("core", "Photo")
    for photo in Photo.objects.all():
        url = getattr(photo, "url", None)
        full_url = getattr(photo, "full_url", None)
        if url and not full_url:
            photo.full_url = url
            photo.save(update_fields=["full_url"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_repair_photo_columns"),
    ]

    operations = [
        migrations.RenameField(
            model_name="photo",
            old_name="prop",
            new_name="property",
        ),
        migrations.AddField(
            model_name="photo",
            name="full_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.RunPython(copy_url_to_full_url, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="photo",
            name="url",
        ),
        migrations.AddField(
            model_name="photo",
            name="sort",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="photo",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="photo",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="photos/%Y/%m/%d"),
        ),
        migrations.AlterModelOptions(
            name="photo",
            options={"ordering": ["-is_default", "sort", "id"]},
        ),
    ]
