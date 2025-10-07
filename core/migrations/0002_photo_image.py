from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="photo",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="photos/%Y/%m/%d"),
        ),
        migrations.AlterField(
            model_name="photo",
            name="full_url",
            field=models.URLField(blank=True, verbose_name="URL изображения"),
        ),
    ]
