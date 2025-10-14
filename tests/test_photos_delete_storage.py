import os

import pytest

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from core.models import Photo, Property


@pytest.mark.django_db
def test_delete_removes_file_from_storage(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    prop = Property.objects.create(title="Тест", address="Москва")
    photo = Photo.objects.create(property=prop)
    photo.image.save("single.jpg", ContentFile(b"data"), save=True)

    image_path = photo.image.path
    assert os.path.exists(image_path)

    photo.delete()

    assert not os.path.exists(image_path)


@pytest.mark.django_db
def test_bulk_delete_removes_files(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    prop = Property.objects.create(title="Тест", address="Москва")
    photos = []
    paths = []
    for idx in range(3):
        photo = Photo.objects.create(property=prop)
        photo.image.save(f"bulk_{idx}.jpg", ContentFile(b"data"), save=True)
        photos.append(photo)
        paths.append(photo.image.path)

    Photo.objects.filter(id__in=[photos[0].id, photos[1].id]).delete()

    assert not os.path.exists(paths[0])
    assert not os.path.exists(paths[1])
    assert os.path.exists(paths[2])


@pytest.mark.django_db
def test_replace_image_removes_old_file(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    prop = Property.objects.create(title="Тест", address="Москва")
    photo = Photo.objects.create(property=prop)
    photo.image.save("old.jpg", ContentFile(b"old"), save=True)
    old_path = photo.image.path

    photo.image = SimpleUploadedFile("new.jpg", b"new", content_type="image/jpeg")
    photo.save()
    photo.refresh_from_db()

    assert not os.path.exists(old_path)
    assert os.path.exists(photo.image.path)
